from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, date, timedelta

from services.youtube_analytics_service import sync_youtube_revenue_periods

from database.db import (
    save_channel_revenue,
    update_channel_revenue,
    delete_channel_revenue,
    get_channel_revenue_entries,
    save_video_revenue,
    update_video_revenue,
    delete_video_revenue,
    get_video_revenue_entries,
    get_manual_revenue_summary,
    get_saved_videos,
    get_best_revenue_summary,
    get_best_channel_revenue_entries,
    get_best_video_revenue_entries,
    get_youtube_revenue_status,
    save_youtube_revenue_daily_rows,
    save_youtube_revenue_period_rows,
    log_youtube_revenue_sync,
    get_top_youtube_video_revenue,
    get_private_hidden_lifetime_adjustment,
    youtube_period_rows_count
)

router = APIRouter()

REVENUE_RUNTIME_CACHE = {
    "summary_created_at": None,
    "summary_payload": None,
    "status_created_at": None,
    "status_payload": None
}

REVENUE_RUNTIME_CACHE_SECONDS = 45


# YouTube Studio is currently showing revenue data through this date.
# Use this as the default cutoff for your first "baseline" revenue entries.
BASELINE_REVENUE_END_DATE = date(2026, 6, 17)

# Your new weekly tracking begins after the baseline cutoff.
# First tracked week: June 18, 2026 through Sunday June 21, 2026.
WEEKLY_TRACKING_START_DATE = date(2026, 6, 18)
FIRST_WEEKLY_UPDATE_DATE = date(2026, 6, 21)


REVENUE_PERIODS = [
    {"key": "7d", "label": "7 Days", "minimum_age_days": 7},
    {"key": "28d", "label": "28 Days", "minimum_age_days": 28},
    {"key": "90d", "label": "90 Days", "minimum_age_days": 90},
    {"key": "365d", "label": "365 Days", "minimum_age_days": 365},
    {"key": "lifetime", "label": "Lifetime", "minimum_age_days": 1},
]


class ChannelRevenueEntry(BaseModel):
    period_type: str
    amount: float
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


class VideoRevenueEntry(BaseModel):
    video_id: str = ""
    title: str = ""
    period_type: str = "lifetime"
    amount: float
    views: int = 0
    rpm: float = 0
    start_date: str = ""
    end_date: str = ""
    notes: str = ""


def normalize_period(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


def baseline_end_date_string():
    return BASELINE_REVENUE_END_DATE.isoformat()


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None


def video_age_days(video):
    published = parse_date(video.get("published", ""))

    if not published:
        return 9999

    return max(0, (datetime.now() - published).days)


def valid_periods_for_video(video):
    age = video_age_days(video)
    valid = []

    for period in REVENUE_PERIODS:
        if age >= period["minimum_age_days"]:
            valid.append(period)

    return valid


def normalize_title(value):
    return str(value or "").strip().lower()


def video_has_period(video, period_key, video_revenue_entries):
    video_id = str(video.get("video_id") or "")
    title = normalize_title(video.get("title", ""))

    for entry in video_revenue_entries:
        entry_video_id = str(entry.get("video_id") or "")
        entry_title = normalize_title(entry.get("title", ""))

        if normalize_period(entry.get("period_type")) != period_key:
            continue

        if video_id and entry_video_id and video_id == entry_video_id:
            return True

        if title and entry_title and title == entry_title:
            return True

    return False


def channel_has_period(period_key, channel_revenue_entries):
    for entry in channel_revenue_entries:
        if normalize_period(entry.get("period_type")) == period_key:
            return True

    return False


def apply_default_dates_to_channel_entry(entry: ChannelRevenueEntry):
    """
    Makes first baseline data easier to enter.

    If you leave end_date blank, CourtVision uses 2026-06-17,
    because that is your official baseline revenue cutoff.
    """
    end_date = entry.end_date or baseline_end_date_string()

    return {
        "period_type": normalize_period(entry.period_type),
        "amount": entry.amount,
        "start_date": entry.start_date,
        "end_date": end_date,
        "notes": entry.notes
    }


def apply_default_dates_to_video_entry(entry: VideoRevenueEntry):
    """
    Makes first baseline video data easier to enter.

    If you leave end_date blank, CourtVision uses 2026-06-17.
    Weekly Sunday entries should still be entered through the Weekly Revenue page.
    """
    end_date = entry.end_date or baseline_end_date_string()

    return {
        "video_id": entry.video_id,
        "title": entry.title,
        "period_type": normalize_period(entry.period_type),
        "amount": entry.amount,
        "views": entry.views,
        "rpm": entry.rpm,
        "start_date": entry.start_date,
        "end_date": end_date,
        "notes": entry.notes
    }


def build_revenue_checklist():
    """
    API-only sync health checklist.

    Synced revenue entry completeness is no longer used. The Revenue Tracker is
    considered healthy when YouTube Analytics period rows exist for the channel
    and synced videos.
    """
    summary = get_best_revenue_summary()
    status = get_youtube_revenue_status()
    channel_entries = get_best_channel_revenue_entries()
    video_entries = get_best_video_revenue_entries()

    required_periods = [period["key"] for period in REVENUE_PERIODS]
    synced_channel_periods = {
        normalize_period(entry.get("period_type"))
        for entry in channel_entries
    }

    missing_channel_periods = [
        {
            "period": period,
            "label": next((p["label"] for p in REVENUE_PERIODS if p["key"] == period), period),
            "reason": "YouTube Analytics API has not synced this channel period yet."
        }
        for period in required_periods
        if period not in synced_channel_periods
    ]

    videos = get_saved_videos()
    synced_video_ids = {
        str(entry.get("video_id") or "").strip()
        for entry in video_entries
        if str(entry.get("video_id") or "").strip()
    }

    videos_missing_api_revenue = [
        {
            "video_id": video.get("video_id", ""),
            "title": video.get("title", ""),
            "published": video.get("published", ""),
            "upload_year": video.get("upload_year", 0),
            "age_days": video_age_days(video),
            "views": video.get("views", 0),
            "missing_periods": []
        }
        for video in videos
        if str(video.get("video_id") or "").strip()
        and str(video.get("video_id") or "").strip() not in synced_video_ids
    ]

    total_videos = len(videos)
    synced_video_count = max(0, total_videos - len(videos_missing_api_revenue))
    completeness_percent = round((synced_video_count / total_videos) * 100, 1) if total_videos else 0

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "data_source": "youtube_analytics_api_revenue_tracker",
        "manual_revenue_enabled": False,
        "weekly_update_due": False,
        "required_periods": REVENUE_PERIODS,
        "summary": {
            "total_videos": total_videos,
            "complete_video_count": synced_video_count,
            "videos_missing_revenue": len(videos_missing_api_revenue),
            "missing_channel_periods": len(missing_channel_periods),
            "required_video_revenue_entries": 0,
            "missing_video_revenue_entries": 0,
            "revenue_completeness_percent": completeness_percent,
            "channel_revenue_rows": len(channel_entries),
            "video_revenue_rows": len(video_entries),
            "latest_sync": status.get("latest_sync")
        },
        "missing_channel_periods": missing_channel_periods,
        "missing_video_entries": sorted(
            videos_missing_api_revenue,
            key=lambda x: -int(x.get("views", 0) or 0)
        )[:25],
        "instructions": [
            "Revenue Tracker now uses synced YouTube Analytics API data only.",
            "Do not enter revenue manually.",
            "Use the YouTube Revenue Sync buttons to refresh channel and video revenue.",
            "If a video is missing revenue, run a full sync and allow Analytics API lag to catch up."
        ]
    }


def build_date_audit():
    """
    API-only date audit based on synced YouTube Analytics rows.
    """
    channel_entries = get_best_channel_revenue_entries()
    video_entries = get_best_video_revenue_entries()
    status = get_youtube_revenue_status()

    all_entries = []

    for entry in channel_entries:
        all_entries.append({
            "type": "channel",
            "id": entry.get("id"),
            "title": "Channel Revenue",
            "period_type": normalize_period(entry.get("period_type")),
            "amount": entry.get("amount"),
            "views": entry.get("views"),
            "rpm": entry.get("rpm"),
            "start_date": entry.get("start_date"),
            "end_date": entry.get("end_date"),
            "source": entry.get("source", "youtube_analytics_api")
        })

    for entry in video_entries:
        all_entries.append({
            "type": "video",
            "id": entry.get("id"),
            "video_id": entry.get("video_id"),
            "title": entry.get("title") or "Untitled Video",
            "period_type": normalize_period(entry.get("period_type")),
            "amount": entry.get("amount"),
            "views": entry.get("views"),
            "rpm": entry.get("rpm"),
            "start_date": entry.get("start_date"),
            "end_date": entry.get("end_date"),
            "source": entry.get("source", "youtube_analytics_api")
        })

    by_end_date = {}

    for entry in all_entries:
        end_date = entry.get("end_date") or "missing_end_date"
        by_end_date.setdefault(end_date, []).append(entry)

    return {
        "summary": {
            "total_entries": len(all_entries),
            "channel_entries": len(channel_entries),
            "video_entries": len(video_entries),
            "unique_end_dates": list(by_end_date.keys()),
            "mixed_end_dates": len(by_end_date.keys()) > 1,
            "latest_sync": status.get("latest_sync"),
            "data_source": "youtube_analytics_api_revenue_tracker",
            "manual_revenue_enabled": False
        },
        "by_end_date": by_end_date,
        "missing_end_date": [],
        "baseline_entries_not_ending_on_default": [],
        "weekly_7d_entries": [
            entry for entry in all_entries
            if normalize_period(entry.get("period_type")) == "7d"
        ],
        "recommendation": "Revenue dates now come from YouTube Analytics API sync rows. Run daily sync for normal updates or full sync after backend changes."
    }



@router.get("/revenue/setup")
def revenue_setup():
    return {
        "data_source": "youtube_analytics_api_revenue_tracker",
        "manual_revenue_enabled": False,
        "instructions": [
            "Revenue Tracker now uses synced YouTube Analytics API data only.",
            "Synced revenue entry is disabled.",
            "Use /revenue/youtube/sync?sync_type=daily for normal daily updates.",
            "Use /revenue/youtube/sync?sync_type=full&start_date=2022-10-09 to rebuild the full revenue table."
        ]
    }



@router.get("/revenue/summary")
def build_revenue_summary_uncached():
    return {
        "summary": get_best_revenue_summary()
    }


@router.get("/revenue/summary")
def revenue_summary():
    cached_at = REVENUE_RUNTIME_CACHE.get("summary_created_at")
    cached_payload = REVENUE_RUNTIME_CACHE.get("summary_payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=REVENUE_RUNTIME_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    payload = build_revenue_summary_uncached()
    REVENUE_RUNTIME_CACHE["summary_created_at"] = datetime.now()
    REVENUE_RUNTIME_CACHE["summary_payload"] = payload
    return payload


@router.get("/revenue/checklist")
def revenue_checklist():
    return {
        "checklist": build_revenue_checklist()
    }


@router.get("/revenue/date-audit")
def revenue_date_audit():
    return {
        "date_audit": build_date_audit()
    }


@router.get("/revenue/channel")
def get_channel_revenue():
    return {
        "channel_revenue": get_best_channel_revenue_entries()
    }


@router.post("/revenue/channel")
def create_channel_revenue(entry: ChannelRevenueEntry):
    return {
        "ok": False,
        "message": "Manual channel revenue entry is disabled. Run YouTube Analytics revenue sync instead.",
        "manual_revenue_enabled": False
    }



@router.put("/revenue/channel/{entry_id}")
def edit_channel_revenue(entry_id: int, entry: ChannelRevenueEntry):
    return {
        "ok": False,
        "message": "Manual channel revenue editing is disabled. Synced YouTube Analytics rows are the source of truth.",
        "id": entry_id,
        "manual_revenue_enabled": False
    }



@router.delete("/revenue/channel/{entry_id}")
def remove_channel_revenue(entry_id: int):
    return {
        "ok": False,
        "message": "Manual channel revenue deletion is disabled. Synced YouTube Analytics rows are the source of truth.",
        "id": entry_id,
        "manual_revenue_enabled": False
    }



@router.get("/revenue/videos")
def get_video_revenue():
    return {
        "video_revenue": get_best_video_revenue_entries()
    }


@router.post("/revenue/videos")
def create_video_revenue(entry: VideoRevenueEntry):
    return {
        "ok": False,
        "message": "Manual video revenue entry is disabled. Run YouTube Analytics revenue sync instead.",
        "manual_revenue_enabled": False
    }



@router.put("/revenue/videos/{entry_id}")
def edit_video_revenue(entry_id: int, entry: VideoRevenueEntry):
    return {
        "ok": False,
        "message": "Manual video revenue editing is disabled. Synced YouTube Analytics rows are the source of truth.",
        "id": entry_id,
        "manual_revenue_enabled": False
    }



@router.delete("/revenue/videos/{entry_id}")
def remove_video_revenue(entry_id: int):
    return {
        "ok": False,
        "message": "Manual video revenue deletion is disabled. Synced YouTube Analytics rows are the source of truth.",
        "id": entry_id,
        "manual_revenue_enabled": False
    }



@router.get("/revenue/youtube/status")
def build_youtube_revenue_status_uncached():
    return {
        "status": get_youtube_revenue_status()
    }


@router.get("/revenue/youtube/status")
def youtube_revenue_status():
    cached_at = REVENUE_RUNTIME_CACHE.get("status_created_at")
    cached_payload = REVENUE_RUNTIME_CACHE.get("status_payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=REVENUE_RUNTIME_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    payload = build_youtube_revenue_status_uncached()
    REVENUE_RUNTIME_CACHE["status_created_at"] = datetime.now()
    REVENUE_RUNTIME_CACHE["status_payload"] = payload
    return payload


@router.get("/revenue/youtube/private-adjustment")
def youtube_private_revenue_adjustment():
    return {
        "amount": get_private_hidden_lifetime_adjustment(),
        "applies_to": "lifetime_channel_revenue_only",
        "note": "No manual adjustment is currently added. Authenticated channel revenue from YouTube Analytics should include private/unlisted video revenue in the channel total."
    }




def build_youtube_period_ranges(end_date_value="", lifetime_start_date="2022-10-09"):
    today = date.today()

    if end_date_value:
        try:
            end = date.fromisoformat(end_date_value)
        except Exception:
            end = today - timedelta(days=1)
    else:
        # YouTube Studio revenue is normally reported through the last completed day.
        # Using yesterday keeps 7d/28d/90d/365d aligned with Studio ranges like Jun 14–20.
        end = today - timedelta(days=1)

    return {
        "lifetime": {
            "start_date": lifetime_start_date or "2022-10-09",
            "end_date": end.isoformat()
        },
        "365d": {
            "start_date": (end - timedelta(days=364)).isoformat(),
            "end_date": end.isoformat()
        },
        "90d": {
            "start_date": (end - timedelta(days=89)).isoformat(),
            "end_date": end.isoformat()
        },
        "28d": {
            "start_date": (end - timedelta(days=27)).isoformat(),
            "end_date": end.isoformat()
        },
        "7d": {
            "start_date": (end - timedelta(days=6)).isoformat(),
            "end_date": end.isoformat()
        }
    }

@router.post("/revenue/youtube/sync")
def sync_youtube_revenue(start_date: str = "", end_date: str = "", sync_type: str = "all_periods", periods=None):
    """
    Pulls exact YouTube Studio-style estimated revenue/RPM totals.

    Default:
      POST /revenue/youtube/sync
      Syncs lifetime, 365d, 90d, 28d, and 7d.

    Optional lifetime start:
      POST /revenue/youtube/sync?start_date=2022-10-01
    """
    period_ranges = build_youtube_period_ranges(
        end_date_value=end_date,
        lifetime_start_date=start_date or "2022-10-09"
    )

    try:
        result = sync_youtube_revenue_periods(period_ranges, periods=periods)

        channel_saved = save_youtube_revenue_period_rows(result.get("channel_rows", []))
        video_saved = save_youtube_revenue_period_rows(result.get("video_rows", []))

        # Keep support for old daily rows if a future service returns any.
        daily_channel_saved = save_youtube_revenue_daily_rows(result.get("channel_daily_rows", []))
        daily_video_saved = save_youtube_revenue_daily_rows(result.get("video_daily_rows", []))

        log_youtube_revenue_sync(
            sync_type=sync_type,
            start_date=period_ranges["lifetime"]["start_date"],
            end_date=period_ranges["lifetime"]["end_date"],
            channel_rows=channel_saved + daily_channel_saved,
            video_rows=video_saved + daily_video_saved,
            status="success",
            message=result.get("message", "")
        )

        return {
            "ok": True,
            "message": "YouTube revenue sync complete",
            "period_ranges": period_ranges,
            "channel_rows_saved": channel_saved,
            "video_rows_saved": video_saved,
            "daily_channel_rows_saved": daily_channel_saved,
            "daily_video_rows_saved": daily_video_saved,
            "result": result,
            "status": get_youtube_revenue_status(),
            "summary": get_best_revenue_summary()
        }

    except Exception as error:
        log_youtube_revenue_sync(
            sync_type=sync_type,
            start_date=period_ranges["lifetime"]["start_date"],
            end_date=period_ranges["lifetime"]["end_date"],
            channel_rows=0,
            video_rows=0,
            status="error",
            message=str(error)
        )

        return {
            "ok": False,
            "message": str(error),
            "period_ranges": period_ranges,
            "status": get_youtube_revenue_status()
        }


@router.get("/revenue/youtube/top-videos")
def youtube_top_earning_videos(period: str = "lifetime", limit: int = 50):
    return {
        "period": normalize_period(period),
        "top_videos": get_top_youtube_video_revenue(
            period_key=normalize_period(period),
            limit=limit
        )
    }


REVENUE_AUTO_SYNC_MAX_AGE_MINUTES = 720


def parse_datetime_safe(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None


def revenue_data_is_fresh(max_age_minutes=REVENUE_AUTO_SYNC_MAX_AGE_MINUTES):
    try:
        status = get_youtube_revenue_status() or {}
        latest = status.get("latest_sync") or {}
        latest_sync_value = latest.get("synced_at") if isinstance(latest, dict) else latest
        latest_sync = parse_datetime_safe(latest_sync_value)
        row_count = youtube_period_rows_count()

        if row_count <= 0 or not latest_sync:
            return False

        return datetime.now() - latest_sync <= timedelta(minutes=max_age_minutes)
    except Exception:
        return False


# =========================================================
# AUTO REVENUE SYNC SUPPORT
# Prevents duplicate YouTube revenue syncs while frontend auto-refreshes.
# =========================================================

_AUTO_REVENUE_SYNC_STATE = {
    "revenue_sync_running": False,
    "last_revenue_sync": "",
    "last_revenue_sync_result": None
}


@router.post("/revenue/youtube/auto-sync")
def auto_sync_youtube_revenue(force: bool = False):
    """
    Frontend-safe revenue auto sync.

    Fast path:
      If YouTube Analytics rows were synced recently, return the saved synced
      database summary immediately.

    Slow path:
      If data is stale/missing, refresh the recent YouTube Analytics periods.
    """
    if _AUTO_REVENUE_SYNC_STATE["revenue_sync_running"]:
        return {
            "ok": True,
            "already_running": True,
            "message": "Revenue sync already running",
            "last_result": _AUTO_REVENUE_SYNC_STATE.get("last_revenue_sync_result"),
            "status": get_youtube_revenue_status(),
            "summary": get_best_revenue_summary()
        }

    if not force and revenue_data_is_fresh():
        result = {
            "ok": True,
            "skipped": True,
            "fresh": True,
            "message": "Revenue data is already fresh. Loaded saved synced YouTube Analytics rows.",
            "status": get_youtube_revenue_status(),
            "summary": get_best_revenue_summary()
        }

        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync_result"] = result

        return {
            "ok": True,
            "already_running": False,
            "skipped": True,
            "message": "Revenue data already fresh",
            "revenue_sync": result,
            "last_revenue_sync": _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"],
            "status": result["status"],
            "summary": result["summary"]
        }

    _AUTO_REVENUE_SYNC_STATE["revenue_sync_running"] = True

    try:
        if _AUTO_REVENUE_SYNC_STATE.get("last_revenue_sync_result") and not force:
            result = _AUTO_REVENUE_SYNC_STATE["last_revenue_sync_result"]
        else:
            result = sync_youtube_revenue(sync_type="auto", periods=["28d", "7d"])

        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync_result"] = result

        inner_ok = bool(result.get("ok", False)) if isinstance(result, dict) else False

        return {
            "ok": inner_ok,
            "already_running": False,
            "message": "Auto revenue sync complete" if inner_ok else result.get("message", "Auto revenue sync failed"),
            "revenue_sync": result,
            "last_revenue_sync": _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"],
            "status": get_youtube_revenue_status(),
            "summary": get_best_revenue_summary()
        }

    except Exception as error:
        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_REVENUE_SYNC_STATE["last_revenue_sync_result"] = {
            "ok": False,
            "error": str(error)
        }

        return {
            "ok": False,
            "already_running": False,
            "message": "Auto revenue sync failed",
            "error": str(error),
            "last_revenue_sync": _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"],
            "status": get_youtube_revenue_status(),
            "summary": get_best_revenue_summary()
        }

@router.get("/revenue/youtube/auto-sync-status")
def auto_sync_youtube_revenue_status():
    return {
        "revenue_sync_running": _AUTO_REVENUE_SYNC_STATE["revenue_sync_running"],
        "last_revenue_sync": _AUTO_REVENUE_SYNC_STATE["last_revenue_sync"],
        "last_revenue_sync_result": _AUTO_REVENUE_SYNC_STATE["last_revenue_sync_result"],
        "status": get_youtube_revenue_status(),
        "summary": get_best_revenue_summary()
    }
