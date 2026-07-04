from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime, timedelta, date

from database.db import (
    save_channel_revenue,
    save_video_revenue,
    get_channel_revenue_entries,
    get_video_revenue_entries
)

router = APIRouter()

# Baseline manual revenue data ends here because YouTube Studio is currently
# showing revenue through June 17, 2026.
BASELINE_REVENUE_END_DATE = date(2026, 6, 17)

# New weekly tracking starts the next day.
# First weekly update covers Tuesday June 18, 2026 through Sunday June 21, 2026.
TRACKING_START_DATE = date(2026, 6, 18)
FIRST_WEEKLY_UPDATE_DATE = date(2026, 6, 21)


class WeeklyVideoRevenueEntry(BaseModel):
    video_id: str = ""
    title: str
    amount: float = 0
    views: int = 0
    rpm: float = 0
    notes: str = ""


class WeeklyRevenueUpdate(BaseModel):
    week_ending: str = ""
    channel_amount: float = 0
    channel_notes: str = ""
    video_updates: list[WeeklyVideoRevenueEntry] = []


def parse_date(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).date()
    except Exception:
        return None


def get_first_tracking_sunday():
    return FIRST_WEEKLY_UPDATE_DATE


def get_next_sunday():
    today = datetime.now().date()
    first_sunday = get_first_tracking_sunday()

    if today <= first_sunday:
        return first_sunday.isoformat()

    days_since_first = (today - first_sunday).days
    weeks_since_first = (days_since_first // 7) + 1
    next_sunday = first_sunday + timedelta(days=weeks_since_first * 7)

    return next_sunday.isoformat()


def get_week_start(week_ending):
    end_date = datetime.fromisoformat(week_ending).date()

    # First tracked week is a short baseline transition week:
    # Thursday June 18 through Sunday June 21.
    if end_date == FIRST_WEEKLY_UPDATE_DATE:
        return TRACKING_START_DATE.isoformat()

    # After the first week, each Sunday update covers the previous Monday-Sunday.
    start_date = end_date - timedelta(days=6)
    return start_date.isoformat()


def format_week_range(week_ending):
    week_start = get_week_start(week_ending)

    return {
        "week_start": week_start,
        "week_ending": week_ending,
        "label": f"{week_start} to {week_ending}"
    }


@router.get("/weekly-revenue/next-sunday")
def next_sunday():
    week_ending = get_next_sunday()
    week_start = get_week_start(week_ending)

    return {
        "week_ending": week_ending,
        "week_start": week_start,
        "baseline_revenue_end_date": BASELINE_REVENUE_END_DATE.isoformat(),
        "tracking_start_date": TRACKING_START_DATE.isoformat(),
        "first_weekly_update_date": FIRST_WEEKLY_UPDATE_DATE.isoformat(),
        "message": "Enter weekly 7-day revenue every Sunday. First update covers June 18 through June 21, 2026."
    }


@router.post("/weekly-revenue/save")
def save_weekly_revenue(update: WeeklyRevenueUpdate):
    week_ending = update.week_ending or get_next_sunday()
    week_start = get_week_start(week_ending)

    saved_channel = False
    saved_videos = 0

    if update.channel_amount > 0:
        save_channel_revenue(
            period_type="7d",
            amount=update.channel_amount,
            start_date=week_start,
            end_date=week_ending,
            notes=update.channel_notes or f"Weekly Sunday update ending {week_ending}"
        )
        saved_channel = True

    for video in update.video_updates:
        if video.amount <= 0:
            continue

        save_video_revenue(
            video_id=video.video_id,
            title=video.title,
            period_type="7d",
            amount=video.amount,
            views=video.views,
            rpm=video.rpm,
            start_date=week_start,
            end_date=week_ending,
            notes=video.notes or f"Weekly Sunday update ending {week_ending}"
        )

        saved_videos += 1

    return {
        "message": "Weekly revenue update saved",
        "week_start": week_start,
        "week_ending": week_ending,
        "saved_channel_update": saved_channel,
        "saved_video_updates": saved_videos
    }


@router.get("/weekly-revenue/history")
def weekly_revenue_history():
    channel_entries = get_channel_revenue_entries()
    video_entries = get_video_revenue_entries()

    weekly_channel = [
        entry for entry in channel_entries
        if entry.get("period_type") == "7d" and parse_date(entry.get("end_date")) and parse_date(entry.get("end_date")) > BASELINE_REVENUE_END_DATE
    ]

    weekly_videos = [
        entry for entry in video_entries
        if entry.get("period_type") == "7d" and parse_date(entry.get("end_date")) and parse_date(entry.get("end_date")) > BASELINE_REVENUE_END_DATE
    ]

    tracked_channel_total = sum(
        float(entry.get("amount") or 0)
        for entry in weekly_channel
    )

    tracked_video_total = sum(
        float(entry.get("amount") or 0)
        for entry in weekly_videos
    )

    weekly_channel = sorted(
        weekly_channel,
        key=lambda x: x.get("end_date", "") or x.get("created_at", ""),
        reverse=True
    )

    weekly_videos = sorted(
        weekly_videos,
        key=lambda x: x.get("end_date", "") or x.get("created_at", ""),
        reverse=True
    )

    return {
        "baseline_revenue_end_date": BASELINE_REVENUE_END_DATE.isoformat(),
        "tracking_start_date": TRACKING_START_DATE.isoformat(),
        "first_weekly_update_date": FIRST_WEEKLY_UPDATE_DATE.isoformat(),
        "weekly_channel_entries": weekly_channel,
        "weekly_video_entries": weekly_videos,
        "tracked_channel_7d_total": round(tracked_channel_total, 2),
        "tracked_video_7d_total": round(tracked_video_total, 2),
        "channel_week_count": len(weekly_channel),
        "video_update_count": len(weekly_videos)
    }
