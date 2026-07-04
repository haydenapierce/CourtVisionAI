from fastapi import APIRouter
from datetime import datetime

from database.db import (
    get_saved_videos,
    get_best_video_revenue_entries,
    get_manual_video_analytics_entries,
)

router = APIRouter()

SOLO_KEYWORDS = [
    "dunk", "poster", "pass", "block", "clutch shot", "game winner",
    "buzzer beater", "highlight", "play"
]


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
        return 0

    return max(1, (datetime.now() - published).days)


def normalize_content_type(video):
    content_type = str(video.get("content_type") or "").strip()
    title = normalize(video.get("title"))

    if content_type.lower() == "top 10" or "top 10" in title:
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


def analytics_for_video(video, analytics_entries):
    matched = [entry for entry in analytics_entries if match_video(video, entry)]

    subscribers_gained = sum(safe_int(e.get("subscribers_gained")) for e in matched)
    subscribers_lost = sum(safe_int(e.get("subscribers_lost")) for e in matched)
    watch_time_hours = sum(safe_float(e.get("watch_time_hours")) for e in matched)
    impressions = sum(safe_int(e.get("impressions")) for e in matched)

    ctr_values = [
        safe_float(e.get("ctr"))
        for e in matched
        if safe_float(e.get("ctr")) > 0
    ]

    average_ctr = round(sum(ctr_values) / len(ctr_values), 2) if ctr_values else 0

    return {
        "entries": len(matched),
        "net_subscribers": subscribers_gained - subscribers_lost,
        "subscribers_gained": subscribers_gained,
        "subscribers_lost": subscribers_lost,
        "watch_time_hours": round(watch_time_hours, 2),
        "impressions": impressions,
        "average_ctr": average_ctr,
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

        keys = []
        if video_id:
            keys.append(("id", video_id))
        if title:
            keys.append(("title", title))

        for key in keys:
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

    data = None
    if video_id:
        data = revenue_lookup.get(("id", video_id))
    if not data and title:
        data = revenue_lookup.get(("title", title))

    if not data:
        return {"total_revenue": 0, "average_rpm": 0, "entries": 0, "period_type": "none"}

    periods = data.get("periods") or {}

    for period in ["lifetime", "365d", "90d", "28d", "7d"]:
        if period in periods:
            item = periods[period]
            revenue = safe_float(item.get("revenue"))
            rpm = safe_float(item.get("rpm"))
            views = safe_int(item.get("views"))

            if rpm <= 0 and views > 0:
                rpm = revenue / views * 1000

            return {
                "total_revenue": round(revenue, 2),
                "average_rpm": round(rpm, 2),
                "entries": data.get("entries", 0),
                "period_type": period,
            }

    return {"total_revenue": 0, "average_rpm": 0, "entries": data.get("entries", 0), "period_type": "none"}


def build_evergreen_score(video, analytics_entries, revenue_lookup):
    revenue_data = revenue_for_video(video, revenue_lookup)
    analytics = analytics_for_video(video, analytics_entries)

    views = safe_int(video.get("views"))
    age_days = video_age_days(video)

    revenue = safe_float(revenue_data.get("total_revenue"))
    rpm = safe_float(revenue_data.get("average_rpm"))
    subs = safe_int(analytics.get("net_subscribers"))
    watch_time = safe_float(analytics.get("watch_time_hours"))
    ctr = safe_float(analytics.get("average_ctr"))

    views_per_day = safe_div(views, age_days)
    revenue_per_day = safe_div(revenue, age_days)
    subs_per_1k_views = safe_div(subs * 1000, views)
    revenue_per_1k_views = safe_div(revenue * 1000, views)

    score = 0

    if age_days >= 365:
        score += 20
    elif age_days >= 180:
        score += 15
    elif age_days >= 90:
        score += 10
    elif age_days >= 30:
        score += 5

    if views_per_day >= 1000:
        score += 25
    elif views_per_day >= 500:
        score += 20
    elif views_per_day >= 150:
        score += 14
    elif views_per_day >= 50:
        score += 8

    if rpm >= 5:
        score += 20
    elif rpm >= 3:
        score += 16
    elif rpm >= 2:
        score += 12
    elif rpm >= 1:
        score += 6

    if revenue_per_day >= 3:
        score += 20
    elif revenue_per_day >= 1:
        score += 14
    elif revenue_per_day >= 0.25:
        score += 8

    if subs_per_1k_views >= 5:
        score += 10
    elif subs_per_1k_views >= 2:
        score += 7
    elif subs_per_1k_views >= 1:
        score += 4

    if ctr >= 8:
        score += 5
    elif ctr >= 5:
        score += 3

    score = min(100, score)

    if score >= 80:
        label = "Evergreen Winner"
    elif score >= 60:
        label = "Strong Evergreen"
    elif score >= 40:
        label = "Decent Evergreen"
    elif score >= 20:
        label = "Weak Evergreen"
    else:
        label = "Dead or Not Proven"

    if age_days >= 180 and views_per_day < 20 and revenue <= 10:
        recovery_status = "Dead Video Recovery Candidate"
    elif age_days >= 90 and rpm >= 2 and views < 25000:
        recovery_status = "High RPM Low Reach Candidate"
    elif score >= 60:
        recovery_status = "Build Around This"
    else:
        recovery_status = "Monitor"

    return {
        "title": video.get("title", ""),
        "video_id": video.get("video_id", ""),
        "player": video.get("player_name", "Unknown"),
        "content_type": normalize_content_type(video),
        "published": video.get("published", ""),
        "upload_year": video.get("upload_year", 0),
        "views": views,
        "age_days": age_days,
        "views_per_day": views_per_day,
        "synced_revenue": round(revenue, 2),
        "synced_rpm": round(rpm, 2),
        "revenue_period_used": revenue_data.get("period_type", "none"),
        "revenue_per_day": revenue_per_day,
        "revenue_per_1k_views": revenue_per_1k_views,
        "net_subscribers": subs,
        "subs_per_1k_views": subs_per_1k_views,
        "watch_time_hours": watch_time,
        "average_ctr": ctr,
        "evergreen_score": score,
        "evergreen_label": label,
        "recovery_status": recovery_status,
        "analytics_entries": analytics.get("entries", 0),
        "revenue_entries": safe_int(revenue_data.get("entries")),
    }


@router.get("/evergreen-score")
def evergreen_score():
    videos = get_saved_videos()
    analytics_entries = get_manual_video_analytics_entries()
    revenue_lookup = build_revenue_lookup(get_best_video_revenue_entries())

    rows = [
        build_evergreen_score(video, analytics_entries, revenue_lookup)
        for video in videos
    ]

    evergreen_winners = sorted(rows, key=lambda x: x["evergreen_score"], reverse=True)[:25]
    build_around = [v for v in rows if v["recovery_status"] == "Build Around This"][:25]
    dead_video_recovery = [v for v in rows if v["recovery_status"] == "Dead Video Recovery Candidate"][:25]
    high_rpm_low_reach = [v for v in rows if v["recovery_status"] == "High RPM Low Reach Candidate"][:25]

    old_still_working = sorted(
        [v for v in rows if v["age_days"] >= 365 and v["views_per_day"] >= 50],
        key=lambda x: x["views_per_day"],
        reverse=True,
    )[:25]

    insights = []

    if evergreen_winners:
        top = evergreen_winners[0]
        insights.append(
            f"Top evergreen video is '{top['title']}' with an Evergreen Score of {top['evergreen_score']}."
        )

    if build_around:
        insights.append(f"{len(build_around)} videos look strong enough to build future series around.")

    if dead_video_recovery:
        insights.append(f"{len(dead_video_recovery)} old low-performing videos may be recovery candidates.")

    if high_rpm_low_reach:
        insights.append(f"{len(high_rpm_low_reach)} videos have strong RPM but low reach.")

    if not insights:
        insights.append("Sync Revenue Tracker and YouTube analytics data to unlock stronger evergreen scoring.")

    recommendations = []

    if build_around:
        recommendations.append(
            f"Build more videos around '{build_around[0]['title']}' because it has proven long-term value."
        )

    if high_rpm_low_reach:
        recommendations.append(
            f"Improve thumbnail/title or consider remaking '{high_rpm_low_reach[0]['title']}' because it has strong RPM but low reach."
        )

    if dead_video_recovery:
        recommendations.append(
            f"Review '{dead_video_recovery[0]['title']}' as a possible reupload or remake candidate."
        )

    if not recommendations:
        recommendations.append("Sync more 28d/90d/lifetime revenue and analytics data to improve evergreen recommendations.")

    return {
        "summary": {
            "total_videos_scored": len(rows),
            "evergreen_winners": len([v for v in rows if v["evergreen_score"] >= 80]),
            "strong_evergreen": len([v for v in rows if v["evergreen_score"] >= 60]),
            "dead_video_recovery_candidates": len(dead_video_recovery),
            "high_rpm_low_reach_candidates": len(high_rpm_low_reach),
        },
        "evergreen_winners": evergreen_winners,
        "build_around": build_around,
        "dead_video_recovery": dead_video_recovery,
        "high_rpm_low_reach": high_rpm_low_reach,
        "old_still_working": old_still_working,
        "all_scores": rows,
        "insights": insights,
        "recommendations": recommendations,
    }
