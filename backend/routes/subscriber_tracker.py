from fastapi import APIRouter
from collections import defaultdict

from database.db import (
    get_saved_videos,
    get_manual_video_analytics_entries,
    get_best_video_revenue_entries,
)

router = APIRouter()


def safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def safe_int(value):
    try:
        return int(value or 0)
    except Exception:
        return 0


def safe_div(a, b):
    return round(a / b, 2) if b else 0


def normalize(value):
    return str(value or "").strip().lower()


def normalize_content_type(video):
    title = normalize(video.get("title"))
    content_type = normalize(video.get("content_type"))

    if content_type == "top 10" or "top 10" in title:
        return "Top 10"

    return "Solo Highlight"


def match_video(video, entry):
    video_id = normalize(video.get("video_id"))
    entry_video_id = normalize(entry.get("video_id"))

    title = normalize(video.get("title"))
    entry_title = normalize(entry.get("title"))

    if video_id and entry_video_id and video_id == entry_video_id:
        return True

    if title and entry_title and title == entry_title:
        return True

    return False


def get_analytics_for_video(video, analytics_entries):
    matched = [entry for entry in analytics_entries if match_video(video, entry)]

    subscribers_gained = sum(safe_int(e.get("subscribers_gained")) for e in matched)
    subscribers_lost = sum(safe_int(e.get("subscribers_lost")) for e in matched)
    impressions = sum(safe_int(e.get("impressions")) for e in matched)
    watch_time_hours = sum(safe_float(e.get("watch_time_hours")) for e in matched)
    end_screen_clicks = sum(safe_int(e.get("end_screen_clicks")) for e in matched)
    playlist_starts = sum(safe_int(e.get("playlist_starts")) for e in matched)

    ctr_values = [
        safe_float(e.get("ctr"))
        for e in matched
        if safe_float(e.get("ctr")) > 0
    ]

    average_ctr = round(sum(ctr_values) / len(ctr_values), 2) if ctr_values else 0

    return {
        "entries": len(matched),
        "subscribers_gained": subscribers_gained,
        "subscribers_lost": subscribers_lost,
        "net_subscribers": subscribers_gained - subscribers_lost,
        "impressions": impressions,
        "average_ctr": average_ctr,
        "watch_time_hours": round(watch_time_hours, 2),
        "end_screen_clicks": end_screen_clicks,
        "playlist_starts": playlist_starts,
    }


def build_revenue_lookup(revenue_entries):
    lookup = {}

    for entry in revenue_entries:
        video_id = normalize(entry.get("video_id"))
        title = normalize(entry.get("title"))
        period = normalize(entry.get("period_type") or entry.get("period"))

        if period not in ("lifetime", "365d", "90d", "28d", "7d"):
            continue

        revenue = safe_float(
            entry.get("amount")
            if entry.get("amount") is not None
            else entry.get("estimated_revenue")
        )
        views = safe_int(entry.get("views"))
        rpm = safe_float(entry.get("rpm"))

        for key in [("id", video_id), ("title", title)]:
            if not key[1]:
                continue

            if key not in lookup:
                lookup[key] = {"entries": 0, "periods": {}}

            lookup[key]["entries"] += 1
            lookup[key]["periods"][period] = {
                "revenue": revenue,
                "views": views,
                "rpm": rpm,
            }

    return lookup


def revenue_for_video(video, revenue_lookup):
    video_id = normalize(video.get("video_id"))
    title = normalize(video.get("title"))

    data = revenue_lookup.get(("id", video_id)) if video_id else None
    if not data and title:
        data = revenue_lookup.get(("title", title))

    if not data:
        return {"synced_revenue": 0, "synced_rpm": 0, "revenue_entries": 0, "revenue_period_used": "none"}

    for period in ["lifetime", "365d", "90d", "28d", "7d"]:
        item = data.get("periods", {}).get(period)
        if item:
            revenue = safe_float(item.get("revenue"))
            views = safe_int(item.get("views"))
            rpm = safe_float(item.get("rpm"))

            if rpm <= 0 and views > 0:
                rpm = revenue / views * 1000

            return {
                "synced_revenue": round(revenue, 2),
                "synced_rpm": round(rpm, 2),
                "revenue_entries": safe_int(data.get("entries")),
                "revenue_period_used": period,
            }

    return {"synced_revenue": 0, "synced_rpm": 0, "revenue_entries": safe_int(data.get("entries")), "revenue_period_used": "none"}


def build_video_rows(videos, analytics_entries, revenue_lookup):
    rows = []

    for video in videos:
        analytics = get_analytics_for_video(video, analytics_entries)
        revenue_data = revenue_for_video(video, revenue_lookup)

        views = safe_int(video.get("views"))
        revenue = safe_float(revenue_data.get("synced_revenue"))
        net_subs = safe_int(analytics.get("net_subscribers"))

        rows.append({
            "title": video.get("title", ""),
            "video_id": video.get("video_id", ""),
            "player": video.get("player_name", "Unknown"),
            "content_type": normalize_content_type(video),
            "views": views,
            "synced_revenue": round(revenue, 2),
            "synced_rpm": safe_float(revenue_data.get("synced_rpm")),
            "revenue_entries": safe_int(revenue_data.get("revenue_entries")),
            "revenue_period_used": revenue_data.get("revenue_period_used", "none"),
            "analytics_entries": analytics["entries"],
            "subscribers_gained": analytics["subscribers_gained"],
            "subscribers_lost": analytics["subscribers_lost"],
            "net_subscribers": net_subs,
            "subs_per_1k_views": safe_div(net_subs * 1000, views),
            "revenue_per_sub": safe_div(revenue, net_subs),
            "impressions": analytics["impressions"],
            "average_ctr": analytics["average_ctr"],
            "watch_time_hours": analytics["watch_time_hours"],
            "end_screen_clicks": analytics["end_screen_clicks"],
            "playlist_starts": analytics["playlist_starts"],
            "published": video.get("published", ""),
            "upload_year": video.get("upload_year", 0),
        })

    return rows


def summarize_group(rows, key_name, label_name):
    grouped = defaultdict(lambda: {
        label_name: "",
        "videos": 0,
        "videos_with_subscriber_data": 0,
        "views": 0,
        "synced_revenue": 0,
        "net_subscribers": 0,
        "subscribers_gained": 0,
        "subscribers_lost": 0,
        "rpm_values": [],
    })

    for row in rows:
        key = row.get(key_name) or "Unknown"

        grouped[key][label_name] = key
        grouped[key]["videos"] += 1
        grouped[key]["views"] += row["views"]
        grouped[key]["synced_revenue"] += row["synced_revenue"]
        grouped[key]["net_subscribers"] += row["net_subscribers"]
        grouped[key]["subscribers_gained"] += row["subscribers_gained"]
        grouped[key]["subscribers_lost"] += row["subscribers_lost"]

        if row["analytics_entries"] > 0:
            grouped[key]["videos_with_subscriber_data"] += 1

        if row["synced_rpm"] > 0:
            grouped[key]["rpm_values"].append(row["synced_rpm"])

    output = []

    for item in grouped.values():
        avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0

        clean_item = dict(item)
        clean_item.pop("rpm_values", None)

        output.append({
            **clean_item,
            "synced_revenue": round(item["synced_revenue"], 2),
            "average_rpm": avg_rpm,
            "subs_per_1k_views": safe_div(item["net_subscribers"] * 1000, item["views"]),
            "revenue_per_sub": safe_div(item["synced_revenue"], item["net_subscribers"]),
        })

    return output


@router.get("/subscriber-tracker")
def subscriber_tracker():
    videos = get_saved_videos()
    analytics_entries = get_manual_video_analytics_entries()
    revenue_lookup = build_revenue_lookup(get_best_video_revenue_entries())

    video_rows = build_video_rows(videos, analytics_entries, revenue_lookup)

    videos_with_subscriber_data = [v for v in video_rows if v["analytics_entries"] > 0]

    best_subscriber_videos = sorted(videos_with_subscriber_data, key=lambda x: x["net_subscribers"], reverse=True)[:25]
    best_subs_per_view_videos = sorted(videos_with_subscriber_data, key=lambda x: x["subs_per_1k_views"], reverse=True)[:25]

    revenue_but_weak_subs = [v for v in videos_with_subscriber_data if v["synced_revenue"] >= 25 and v["net_subscribers"] <= 0]
    subs_but_weak_revenue = [v for v in videos_with_subscriber_data if v["net_subscribers"] >= 10 and v["synced_revenue"] < 10]

    player_rows = summarize_group(video_rows, "player", "player")
    format_rows = summarize_group(video_rows, "content_type", "format")

    best_subscriber_players = sorted(
        [p for p in player_rows if p["videos_with_subscriber_data"] > 0],
        key=lambda x: x["net_subscribers"],
        reverse=True,
    )[:25]

    best_subscriber_formats = sorted(
        [f for f in format_rows if f["videos_with_subscriber_data"] > 0],
        key=lambda x: x["net_subscribers"],
        reverse=True,
    )[:25]

    total_views = sum(v["views"] for v in videos_with_subscriber_data)
    total_net_subs = sum(v["net_subscribers"] for v in videos_with_subscriber_data)
    total_revenue = sum(v["synced_revenue"] for v in videos_with_subscriber_data)

    insights = []

    if not videos_with_subscriber_data:
        insights.append("No subscriber analytics entries found yet. Sync or add subscriber gain/loss data to unlock subscriber conversion tracking.")
    else:
        if best_subscriber_videos:
            insights.append(
                f"Best subscriber video is '{best_subscriber_videos[0]['title']}' with {best_subscriber_videos[0]['net_subscribers']} net subscribers."
            )

        if best_subscriber_players:
            insights.append(
                f"Best subscriber player is {best_subscriber_players[0]['player']} with {best_subscriber_players[0]['net_subscribers']} net subscribers."
            )

        if best_subscriber_formats:
            insights.append(
                f"Best subscriber format is {best_subscriber_formats[0]['format']} with {best_subscriber_formats[0]['net_subscribers']} net subscribers."
            )

        if revenue_but_weak_subs:
            insights.append(f"{len(revenue_but_weak_subs)} videos make money but are weak at gaining subscribers.")

        if subs_but_weak_revenue:
            insights.append(f"{len(subs_but_weak_revenue)} videos gain subscribers but have weak revenue.")

    recommendations = []

    if not videos_with_subscriber_data:
        recommendations.append("Start by syncing subscriber analytics for your top videos.")
    else:
        if best_subscriber_players:
            recommendations.append(
                f"Make more videos around {best_subscriber_players[0]['player']} if subscriber growth is the goal."
            )

        if best_subscriber_formats:
            recommendations.append(
                f"Use more {best_subscriber_formats[0]['format']} videos if subscriber conversion is the goal."
            )

        if revenue_but_weak_subs:
            recommendations.append("For videos that make money but do not gain subscribers, improve subscribe prompts, pinned comments, and end screens.")

        if subs_but_weak_revenue:
            recommendations.append("For videos that gain subscribers but make weak revenue, use them as growth videos but pair them with higher-RPM uploads.")

    return {
        "summary": {
            "total_videos": len(videos),
            "videos_with_subscriber_data": len(videos_with_subscriber_data),
            "total_net_subscribers": total_net_subs,
            "total_subscribers_gained": sum(v["subscribers_gained"] for v in videos_with_subscriber_data),
            "total_subscribers_lost": sum(v["subscribers_lost"] for v in videos_with_subscriber_data),
            "total_views_with_subscriber_data": total_views,
            "total_revenue_with_subscriber_data": round(total_revenue, 2),
            "channel_subs_per_1k_views": safe_div(total_net_subs * 1000, total_views),
            "channel_revenue_per_sub": safe_div(total_revenue, total_net_subs),
        },
        "best_subscriber_videos": best_subscriber_videos,
        "best_subs_per_view_videos": best_subs_per_view_videos,
        "best_subscriber_players": best_subscriber_players,
        "best_subscriber_formats": best_subscriber_formats,
        "revenue_but_weak_subs": revenue_but_weak_subs[:25],
        "subs_but_weak_revenue": subs_but_weak_revenue[:25],
        "insights": insights,
        "recommendations": recommendations,
    }
