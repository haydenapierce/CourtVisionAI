from fastapi import APIRouter
from database.db import (
    get_best_channel_revenue_entries,
    get_best_video_revenue_entries,
    get_best_revenue_summary,
    get_best_channel_rpm,
    get_saved_videos,
    get_best_revenue_for_video
)

router = APIRouter()

MIN_TREND_VIEWS = 500


def safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def safe_int(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def normalize_period(period):
    if period == "30d":
        return "28d"
    return period or "unknown"


def get_latest_by_period(entries):
    latest = {}

    for entry in entries:
        period = normalize_period(entry.get("period_type"))
        sort_value = entry.get("end_date", "") or entry.get("synced_at", "") or entry.get("created_at", "")

        if period not in latest:
            latest[period] = entry
            continue

        old_sort = (
            latest[period].get("end_date", "")
            or latest[period].get("synced_at", "")
            or latest[period].get("created_at", "")
        )

        if sort_value >= old_sort:
            latest[period] = entry

    return latest


def project_from_7d(amount):
    amount = safe_float(amount)

    return {
        "projected_7d": round(amount, 2),
        "projected_28d": round(amount * 4, 2),
        "projected_90d": round(amount * 12.85, 2),
        "projected_365d": round(amount * 52.14, 2),
        "projected_monthly": round(amount * 4.345, 2),
        "projected_yearly": round(amount * 52.14, 2)
    }


def trend_label(current, previous):
    current = safe_float(current)
    previous = safe_float(previous)

    if previous <= 0:
        return "No previous data"

    change = ((current - previous) / previous) * 100

    if change > 15:
        return "Strong growth"
    if change > 3:
        return "Slight growth"
    if change < -15:
        return "Big drop"
    if change < -3:
        return "Slight drop"

    return "Stable"


def normalize_format(value):
    text = str(value or "").lower()

    if "top 10" in text or "top ten" in text:
        return "Top 10"

    return "Solo Highlight"


def has_enough_views_for_trend(video):
    """
    Keeps small sample-size videos out of forecast/trend leaderboards.
    This does NOT affect total channel revenue, total views, saved videos, or sync counts.
    """
    return safe_int(video.get("views")) >= MIN_TREND_VIEWS


def read_video_money(video):
    """
    Pull real synced lifetime revenue/RPM for the card.
    Supports all key names used by Revenue Tracker / YouTube Analytics helpers.
    """
    try:
        money = get_best_revenue_for_video(video, "lifetime") or {}
    except TypeError:
        money = get_best_revenue_for_video(video) or {}
    except Exception:
        money = {}

    revenue = safe_float(
        money.get("total_revenue")
        or money.get("synced_revenue")
        or money.get("estimated_revenue")
        or money.get("amount")
        or video.get("synced_revenue")
        or video.get("estimated_revenue")
        or video.get("yt_estimated_revenue")
        or video.get("manual_revenue")
    )

    rpm = safe_float(
        money.get("average_rpm")
        or money.get("synced_rpm")
        or money.get("rpm")
        or money.get("estimated_rpm")
        or video.get("synced_rpm")
        or video.get("estimated_rpm")
        or video.get("yt_estimated_rpm")
        or video.get("manual_rpm")
    )

    views = safe_int(video.get("views"))
    if rpm <= 0 and revenue > 0 and views > 0:
        rpm = (revenue / views) * 1000

    return money, revenue, rpm


@router.get("/revenue-forecast")
def revenue_forecast():
    channel_entries = get_best_channel_revenue_entries()
    video_entries = get_best_video_revenue_entries()
    summary = get_best_revenue_summary()
    channel_rpm = safe_float(get_best_channel_rpm())
    videos = get_saved_videos()

    latest_channel = get_latest_by_period(channel_entries)

    channel_7d = safe_float(latest_channel.get("7d", {}).get("amount", 0))
    channel_28d = safe_float(latest_channel.get("28d", {}).get("amount", 0))
    channel_90d = safe_float(latest_channel.get("90d", {}).get("amount", 0))
    channel_365d = safe_float(latest_channel.get("365d", {}).get("amount", 0))
    channel_lifetime = safe_float(latest_channel.get("lifetime", {}).get("amount", 0))

    if channel_7d > 0:
        base_forecast = project_from_7d(channel_7d)
        forecast_source = "latest 7d revenue"
    elif channel_28d > 0:
        base_forecast = project_from_7d(channel_28d / 4)
        forecast_source = "latest 28d revenue"
    elif channel_90d > 0:
        base_forecast = project_from_7d(channel_90d / 12.85)
        forecast_source = "latest 90d revenue"
    else:
        base_forecast = project_from_7d(0)
        forecast_source = "not enough synced revenue data"

    weekly_entries = sorted(
        [e for e in channel_entries if normalize_period(e.get("period_type")) == "7d"],
        key=lambda x: x.get("end_date", "") or x.get("synced_at", "") or x.get("created_at", "")
    )

    previous_7d = safe_float(weekly_entries[-2].get("amount")) if len(weekly_entries) >= 2 else 0
    trend = trend_label(channel_7d, previous_7d)

    video_forecasts = []

    for video in videos:
        views = safe_int(video.get("views"))

        if views < MIN_TREND_VIEWS:
            continue

        money, revenue, rpm = read_video_money(video)

        if revenue <= 0 and rpm <= 0:
            continue

        estimated_next_10k = round((10000 / 1000) * rpm, 2) if rpm > 0 else 0
        estimated_next_100k = round((100000 / 1000) * rpm, 2) if rpm > 0 else 0

        video_forecasts.append({
            "title": video.get("title", ""),
            "video_id": video.get("video_id", ""),
            "thumbnail": video.get("thumbnail", ""),
            "player": video.get("player_name", "Unknown"),
            "player_name": video.get("player_name", "Unknown"),
            "content_type": normalize_format(f"{video.get('content_type', '')} {video.get('title', '')}"),
            "views": views,

            "synced_revenue": round(revenue, 2),
            "synced_rpm": round(rpm, 2),
            "revenue": round(revenue, 2),
            "rpm": round(rpm, 2),
            "estimated_revenue": round(revenue, 2),
            "estimated_rpm": round(rpm, 2),
            "manual_revenue": round(revenue, 2),
            "manual_rpm": round(rpm, 2),

            "estimated_next_10k_views_revenue": estimated_next_10k,
            "estimated_next_100k_views_revenue": estimated_next_100k,
            "next_10k_revenue": estimated_next_10k,
            "next_100k_revenue": estimated_next_100k,
            "source": money.get("source", "youtube_analytics_api_revenue_tracker")
        })

    video_forecasts.sort(
        key=lambda x: (x["synced_rpm"], x["synced_revenue"], x["views"]),
        reverse=True
    )

    insights = []

    if channel_7d > 0:
        insights.append(
            f"Based on synced 7d revenue of ${channel_7d:.2f}, projected monthly revenue is about ${base_forecast['projected_monthly']:.2f}."
        )
    elif channel_28d > 0:
        insights.append(
            f"Based on synced 28d revenue of ${channel_28d:.2f}, projected yearly revenue is about ${base_forecast['projected_yearly']:.2f}."
        )
    else:
        insights.append("Sync YouTube Analytics revenue to unlock live forecasts.")

    if trend != "No previous data":
        insights.append(f"Latest weekly revenue trend: {trend}.")

    if channel_rpm > 0:
        insights.append(f"Synced channel RPM is about ${channel_rpm:.2f}.")

    recommendations = []

    if video_forecasts:
        top = video_forecasts[0]
        recommendations.append(
            f"Prioritize topics similar to '{top['title']}' because it has the strongest synced RPM/revenue signal."
        )
    else:
        recommendations.append("Run Revenue Tracker sync so forecasts can use real YouTube Analytics revenue.")

    return {
        "summary": {
            "forecast_source": forecast_source,
            "channel_rpm": round(channel_rpm, 2),
            "manual_channel_rpm": round(channel_rpm, 2),
            "latest_7d_revenue": round(channel_7d, 2),
            "latest_28d_revenue": round(channel_28d, 2),
            "latest_90d_revenue": round(channel_90d, 2),
            "latest_365d_revenue": round(channel_365d, 2),
            "official_lifetime_revenue": round(channel_lifetime, 2),
            "weekly_trend": trend,
            "data_source": summary.get("data_source", "youtube_analytics_api_revenue_tracker"),
            "min_views_for_video_trends": MIN_TREND_VIEWS
        },
        "forecast": base_forecast,
        "top_video_forecasts": video_forecasts[:25],
        "insights": insights,
        "recommendations": recommendations,
        "video_revenue_rows_available": len(video_entries),
        "video_forecast_rows_after_view_filter": len(video_forecasts)
    }
