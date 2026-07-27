from datetime import date, timedelta
import time
from services.youtube_oauth import get_authenticated_service
from services.youtube_service import get_all_channel_videos

PERIOD_ORDER = ["lifetime", "365d", "90d", "28d", "7d"]


def _latest_available_analytics_date():
    return date.today() - timedelta(days=2)


def _clamp_end_date(value):
    try:
        requested = date.fromisoformat(str(value)[:10])
    except Exception:
        requested = _latest_available_analytics_date()

    return min(requested, _latest_available_analytics_date()).isoformat()


def _header_index_map(response):
    headers = response.get("columnHeaders", [])
    return {header.get("name"): index for index, header in enumerate(headers)}


def _safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def _safe_int(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _calculate_rpm(revenue, views):
    views = _safe_int(views)
    revenue = _safe_float(revenue)

    if views <= 0:
        return 0

    return round((revenue / views) * 1000, 4)


def query_youtube_analytics_report(
    analytics,
    start_date,
    end_date,
    metrics,
    dimensions=None,
    filters=None,
    sort=None,
    max_results=200
):
    request = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": metrics,
        "maxResults": max_results
    }

    if dimensions:
        request["dimensions"] = dimensions

    if filters:
        request["filters"] = filters

    if sort:
        request["sort"] = sort

    last_error = None

    # Google API clients otherwise inherit an effectively unbounded socket
    # timeout. A single stalled Analytics request must never freeze startup.
    try:
        if getattr(analytics, "_http", None) is not None:
            analytics._http.timeout = 25
    except Exception:
        pass

    for attempt in range(2):
        try:
            return analytics.reports().query(**request).execute()
        except Exception as error:
            last_error = error
            if attempt < 1:
                time.sleep(0.75)

    raise last_error


def fetch_channel_period_revenue(analytics, period_type, start_date, end_date):
    response = query_youtube_analytics_report(
        analytics=analytics,
        start_date=start_date,
        end_date=end_date,
        metrics="views,estimatedRevenue,estimatedMinutesWatched",
        max_results=1
    )

    indexes = _header_index_map(response)
    rows = response.get("rows", [])

    if not rows:
        return {
            "period_type": period_type,
            "start_date": start_date,
            "end_date": end_date,
            "video_id": "__CHANNEL__",
            "title": "Channel Total",
            "views": 0,
            "estimated_revenue": 0,
            "estimated_minutes_watched": 0,
            "rpm": 0
        }

    item = rows[0]
    views = _safe_int(item[indexes["views"]])
    estimated_revenue = _safe_float(item[indexes["estimatedRevenue"]])
    estimated_minutes = _safe_float(item[indexes["estimatedMinutesWatched"]])

    return {
        "period_type": period_type,
        "start_date": start_date,
        "end_date": end_date,
        "video_id": "__CHANNEL__",
        "title": "Channel Total",
        "views": views,
        "estimated_revenue": estimated_revenue,
        "estimated_minutes_watched": estimated_minutes,
        "rpm": _calculate_rpm(estimated_revenue, views)
    }


def fetch_single_video_period_revenue(analytics, period_type, start_date, end_date, video_id, title=""):
    response = query_youtube_analytics_report(
        analytics=analytics,
        start_date=start_date,
        end_date=end_date,
        metrics="views,estimatedRevenue,estimatedMinutesWatched",
        filters=f"video=={video_id}",
        max_results=1
    )

    indexes = _header_index_map(response)
    rows = response.get("rows", [])

    if not rows:
        return {
            "period_type": period_type,
            "start_date": start_date,
            "end_date": end_date,
            "video_id": video_id,
            "title": title,
            "views": 0,
            "estimated_revenue": 0,
            "estimated_minutes_watched": 0,
            "rpm": 0
        }

    item = rows[0]
    views = _safe_int(item[indexes["views"]])
    estimated_revenue = _safe_float(item[indexes["estimatedRevenue"]])
    estimated_minutes = _safe_float(item[indexes["estimatedMinutesWatched"]])

    return {
        "period_type": period_type,
        "start_date": start_date,
        "end_date": end_date,
        "video_id": video_id,
        "title": title,
        "views": views,
        "estimated_revenue": estimated_revenue,
        "estimated_minutes_watched": estimated_minutes,
        "rpm": _calculate_rpm(estimated_revenue, views)
    }


def fetch_video_period_revenue_batch(analytics, period_type, start_date, end_date, videos):
    """
    Fast path: one Analytics API call per period using dimensions=video.
    Fallback: exact per-video query only if the batch query fails.
    """
    video_title_map = {
        str(video.get("video_id") or ""): video.get("title", "")
        for video in videos
        if video.get("video_id")
    }

    try:
        response = query_youtube_analytics_report(
            analytics=analytics,
            start_date=start_date,
            end_date=end_date,
            metrics="views,estimatedRevenue,estimatedMinutesWatched",
            dimensions="video",
            sort="-estimatedRevenue",
            max_results=500
        )

        indexes = _header_index_map(response)
        rows = response.get("rows", [])
        output = []

        for item in rows:
            video_id = str(item[indexes["video"]])
            views = _safe_int(item[indexes["views"]])
            estimated_revenue = _safe_float(item[indexes["estimatedRevenue"]])
            estimated_minutes = _safe_float(item[indexes["estimatedMinutesWatched"]])

            output.append({
                "period_type": period_type,
                "start_date": start_date,
                "end_date": end_date,
                "video_id": video_id,
                "title": video_title_map.get(video_id, ""),
                "views": views,
                "estimated_revenue": estimated_revenue,
                "estimated_minutes_watched": estimated_minutes,
                "rpm": _calculate_rpm(estimated_revenue, views)
            })

        return output, []

    except Exception as error:
        # Never fall back to hundreds of sequential per-video API requests
        # during startup. Existing verified database rows remain untouched and
        # can be used until the next successful batch refresh.
        return [], [{
            "period_type": period_type,
            "video_id": "__BATCH_QUERY__",
            "title": "Batch dimensions=video query failed; retained saved rows.",
            "error": str(error)
        }]


def sync_youtube_revenue_periods(period_ranges, periods=None, videos=None, progress_callback=None):
    """
    Pulls YouTube Studio-style estimated revenue/RPM.

    If videos are passed in, this avoids re-calling the YouTube Data API just to
    get the upload list.
    """
    youtube, analytics = get_authenticated_service()
    videos = videos if videos is not None else get_all_channel_videos()
    requested_periods = periods or PERIOD_ORDER

    channel_rows = []
    video_rows = []
    skipped_videos = []

    available_periods = [period for period in requested_periods if period in period_ranges]

    for period_index, period_type in enumerate(available_periods):
        if progress_callback:
            progress_callback(period_type, period_index, len(available_periods), "fetching")

        dates = period_ranges[period_type]
        start_date = dates["start_date"]
        end_date = _clamp_end_date(dates["end_date"])

        channel_rows.append(
            fetch_channel_period_revenue(
                analytics=analytics,
                period_type=period_type,
                start_date=start_date,
                end_date=end_date
            )
        )

        period_video_rows, skipped = fetch_video_period_revenue_batch(
            analytics=analytics,
            period_type=period_type,
            start_date=start_date,
            end_date=end_date,
            videos=videos
        )

        video_rows.extend(period_video_rows)
        skipped_videos.extend(skipped)

        if progress_callback:
            progress_callback(period_type, period_index + 1, len(available_periods), "complete")

    return {
        "message": "Fetched YouTube Analytics revenue rows.",
        "period_ranges": period_ranges,
        "periods_synced": requested_periods,
        "channel_rows": channel_rows,
        "video_rows": video_rows,
        "channel_row_count": len(channel_rows),
        "video_row_count": len(video_rows),
        "skipped_video_count": len(skipped_videos),
        "skipped_videos": skipped_videos[:10]
    }


def sync_youtube_revenue_analytics(start_date, end_date):
    return sync_youtube_revenue_periods({
        "lifetime": {
            "start_date": start_date,
            "end_date": end_date
        }
    })
