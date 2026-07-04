from fastapi import APIRouter
from datetime import datetime
from database import db as database

router = APIRouter()


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


def safe_div(a, b):
    return round(a / b, 2) if b else 0


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

    return max(1, (datetime.now() - published).days)


def get_saved_videos_safe():
    return database.get_saved_videos()


def get_channel_rpm_safe():
    if hasattr(database, "get_best_channel_rpm"):
        return safe_float(database.get_best_channel_rpm())

    if hasattr(database, "get_manual_channel_rpm"):
        return safe_float(database.get_manual_channel_rpm())

    return 0


def get_video_money(video):
    """
    Uses the best available revenue source.
    Current CourtVision uses YouTube Analytics API revenue first, then old manual data only as a fallback.
    """
    if hasattr(database, "get_best_revenue_for_video"):
        try:
            money = database.get_best_revenue_for_video(video)
            return {
                "total_revenue": safe_float(
                    money.get("total_revenue")
                    or money.get("estimated_revenue")
                    or money.get("amount")
                ),
                "average_rpm": safe_float(
                    money.get("average_rpm")
                    or money.get("rpm")
                    or money.get("estimated_rpm")
                ),
                "entries": safe_int(money.get("entries") or money.get("periods_count")),
                "source": money.get("source", "youtube_analytics_api")
            }
        except Exception:
            pass

    if hasattr(database, "get_manual_revenue_for_video"):
        try:
            money = database.get_manual_revenue_for_video(video)
            return {
                "total_revenue": safe_float(money.get("total_revenue")),
                "average_rpm": safe_float(money.get("average_rpm")),
                "entries": safe_int(money.get("entries")),
                "source": "synced_fallback_disabled"
            }
        except Exception:
            pass

    return {
        "total_revenue": safe_float(video.get("estimated_revenue") or video.get("yt_estimated_revenue")),
        "average_rpm": safe_float(video.get("estimated_rpm") or video.get("yt_estimated_rpm")),
        "entries": 0,
        "source": "video_row"
    }


def expected_views_for_age(video):
    age_days = video_age_days(video)

    if age_days >= 365:
        return 35000
    if age_days >= 180:
        return 25000
    if age_days >= 90:
        return 15000

    return 8000


def recovery_score(video, money, channel_rpm):
    views = safe_int(video.get("views"))
    age_days = video_age_days(video)
    revenue = safe_float(money.get("total_revenue"))
    rpm = safe_float(money.get("average_rpm"))

    score = 0

    if age_days >= 730:
        score += 28
    elif age_days >= 365:
        score += 24
    elif age_days >= 180:
        score += 16
    elif age_days >= 90:
        score += 8

    expected_views = expected_views_for_age(video)

    if views < expected_views * 0.2:
        score += 28
    elif views < expected_views * 0.4:
        score += 22
    elif views < expected_views * 0.7:
        score += 14

    if rpm >= 5:
        score += 24
    elif rpm >= 3:
        score += 20
    elif rpm >= 2:
        score += 14
    elif channel_rpm > 0 and rpm >= channel_rpm:
        score += 10

    if revenue >= 100:
        score += 16
    elif revenue >= 25:
        score += 10
    elif revenue > 0:
        score += 6

    if str(video.get("player_name", "Unknown")) != "Unknown":
        score += 4

    return min(score, 100)


def classify_recovery(video, money, channel_rpm):
    views = safe_int(video.get("views"))
    age_days = video_age_days(video)
    revenue = safe_float(money.get("total_revenue"))
    rpm = safe_float(money.get("average_rpm"))
    player = video.get("player_name", "Unknown")
    expected_views = expected_views_for_age(video)

    if views >= 100000 and rpm > 0 and rpm < max(1, channel_rpm * 0.55 if channel_rpm else 1):
        return "Revenue Leak", "High views but weak RPM. Check monetization, copyright, title safety, and ad suitability."

    if age_days >= 365 and views < expected_views * 0.45 and rpm >= max(1.5, channel_rpm * 0.75 if channel_rpm else 1.5):
        return "Remake Candidate", "Old video with low reach but a strong RPM signal. This belongs in a fresh remake/reupload plan."

    if age_days >= 365 and views < expected_views * 0.45 and revenue > 0:
        return "Reupload Candidate", "Old low-reach video with proven revenue. Consider a stronger new version with updated title, thumbnail, and edit."

    if views < 50000 and rpm >= max(2, channel_rpm if channel_rpm else 2):
        return "High RPM / Low Reach", "Good RPM but not enough reach. Try title, thumbnail, playlist, end screen, and community post recovery first."

    if age_days >= 365 and views < 8000 and player != "Unknown":
        return "Dead Video Recovery", "Old upload with very low views and identifiable player/topic. Try a recovery update before deleting."

    return "Monitor", "Not a strong recovery or reupload candidate yet."


def build_video_row(video, channel_rpm):
    money = get_video_money(video)

    views = safe_int(video.get("views"))
    revenue = safe_float(money.get("total_revenue"))
    rpm = safe_float(money.get("average_rpm"))
    age_days = video_age_days(video)
    category, reason = classify_recovery(video, money, channel_rpm)
    score = recovery_score(video, money, channel_rpm)

    estimated_revenue_if_50k_views = round((50000 / 1000) * rpm, 2) if rpm > 0 else 0
    estimated_revenue_if_100k_views = round((100000 / 1000) * rpm, 2) if rpm > 0 else 0

    projected_new_views = 0

    if category in ["Reupload Candidate", "Remake Candidate"]:
        projected_new_views = max(25000, min(150000, int(max(views, 1) * 4)))
    elif category == "High RPM / Low Reach":
        projected_new_views = max(15000, min(100000, int(max(views, 1) * 2.5)))
    elif category == "Dead Video Recovery":
        projected_new_views = max(10000, min(50000, int(max(views, 1) * 3)))

    projected_new_revenue = round((projected_new_views / 1000) * rpm, 2) if rpm > 0 else 0

    return {
        "title": video.get("title", ""),
        "video_id": video.get("video_id", ""),
        "player": video.get("player_name", "Unknown"),
        "content_type": video.get("content_type", "Solo Highlight"),
        "thumbnail": video.get("thumbnail", ""),
        "published": video.get("published", ""),
        "upload_year": video.get("upload_year", 0),
        "age_days": age_days,
        "views": views,

        "manual_revenue": round(revenue, 2),
        "manual_rpm": round(rpm, 2),
        "manual_entries": safe_int(money.get("entries")),
        "revenue_source": money.get("source", "youtube_analytics_api"),

        "views_per_day": safe_div(views, age_days),
        "recovery_score": score,
        "opportunity_score": score,
        "reupload_score": score if category in ["Reupload Candidate", "Remake Candidate"] else 0,
        "recovery_category": category,
        "reason": reason,

        "estimated_revenue_if_50k_views": estimated_revenue_if_50k_views,
        "estimated_revenue_if_100k_views": estimated_revenue_if_100k_views,
        "projected_new_views": projected_new_views,
        "projected_new_revenue": projected_new_revenue
    }


@router.get("/dead-video-recovery")
def dead_video_recovery():
    videos = get_saved_videos_safe()
    channel_rpm = get_channel_rpm_safe()

    rows = [
        build_video_row(video, channel_rpm)
        for video in videos
    ]

    candidates = [
        row for row in rows
        if row["recovery_category"] != "Monitor"
    ]

    candidates.sort(
        key=lambda x: (
            x.get("recovery_score", 0),
            x.get("projected_new_revenue", 0),
            x.get("manual_rpm", 0),
            x.get("manual_revenue", 0),
            x.get("views", 0)
        ),
        reverse=True
    )

    dead_video_candidates = [
        row for row in candidates
        if row["recovery_category"] == "Dead Video Recovery"
    ]

    reupload_candidates = [
        row for row in candidates
        if row["recovery_category"] == "Reupload Candidate"
    ]

    remake_candidates = [
        row for row in candidates
        if row["recovery_category"] == "Remake Candidate"
    ]

    high_rpm_low_reach = [
        row for row in candidates
        if row["recovery_category"] == "High RPM / Low Reach"
    ]

    revenue_leaks = [
        row for row in candidates
        if row["recovery_category"] == "Revenue Leak"
    ]

    remake_and_reupload = sorted(
        remake_candidates + reupload_candidates,
        key=lambda x: (
            x.get("reupload_score", 0),
            x.get("projected_new_revenue", 0),
            x.get("manual_rpm", 0),
            x.get("manual_revenue", 0)
        ),
        reverse=True
    )

    insights = []

    if candidates:
        top = candidates[0]
        insights.append(f"{len(candidates)} total recovery opportunities found.")
        insights.append(f"Top opportunity: '{top['title']}' with a {top['recovery_score']}/100 recovery score.")

    if remake_and_reupload:
        insights.append(f"{len(remake_and_reupload)} videos are strong remake/reupload candidates.")

    if high_rpm_low_reach:
        insights.append(f"{len(high_rpm_low_reach)} videos have high RPM but low reach.")

    if revenue_leaks:
        insights.append(f"{len(revenue_leaks)} videos may be leaking revenue because views are high but RPM is weak.")

    if not insights:
        insights.append("No strong recovery candidates yet. Sync revenue and keep monitoring older low-view uploads.")

    recommendations = []

    if remake_and_reupload:
        top = remake_and_reupload[0]
        recommendations.append(
            f"Remake or reupload '{top['title']}' first. It has the strongest mix of age, low reach, RPM, and proven revenue."
        )

    if high_rpm_low_reach:
        top = high_rpm_low_reach[0]
        recommendations.append(
            f"Recover '{top['title']}' with a better thumbnail/title before remaking it because RPM is strong but reach is low."
        )

    if revenue_leaks:
        top = revenue_leaks[0]
        recommendations.append(
            f"Check monetization/copyright status on '{top['title']}' because it has views but weak RPM."
        )

    if dead_video_candidates:
        top = dead_video_candidates[0]
        recommendations.append(
            f"Try a title/thumbnail refresh for '{top['title']}' because it is an old dead upload with an identifiable player."
        )

    if not recommendations:
        recommendations.append("Keep uploading new videos and revisit this tab after more revenue data is synced.")

    return {
        "summary": {
            "total_videos_scanned": len(rows),
            "total_recovery_candidates": len(candidates),
            "dead_video_candidates": len(dead_video_candidates),
            "reupload_candidates": len(reupload_candidates),
            "remake_candidates": len(remake_candidates),
            "remake_and_reupload_candidates": len(remake_and_reupload),
            "high_rpm_low_reach": len(high_rpm_low_reach),
            "revenue_leaks": len(revenue_leaks)
        },
        "top_candidates": candidates[:25],
        "dead_video_candidates": dead_video_candidates[:25],
        "reupload_candidates": reupload_candidates[:25],
        "remake_candidates": remake_candidates[:25],
        "remake_and_reupload_candidates": remake_and_reupload[:25],
        "high_rpm_low_reach": high_rpm_low_reach[:25],
        "revenue_leaks": revenue_leaks[:25],
        "all_scored_videos": rows,
        "insights": insights,
        "recommendations": recommendations
    }
