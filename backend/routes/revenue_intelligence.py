from fastapi import APIRouter

from database.db import (
    get_saved_videos,
    get_manual_revenue_for_video,
    get_manual_player_revenue_summary,
    get_manual_channel_rpm
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


def revenue_per_1k(revenue, views):
    if views <= 0:
        return 0
    return round((revenue / views) * 1000, 2)


def classify_leak(video, channel_rpm):
    views = safe_int(video.get("views"))
    rpm = safe_float(video.get("manual_rpm"))
    revenue = safe_float(video.get("manual_revenue"))

    if views >= 100000 and rpm > 0 and rpm < 1:
        return "High views but weak RPM"

    if views >= 50000 and rpm > 0 and channel_rpm > 0 and rpm < channel_rpm * 0.5:
        return "RPM is far below channel average"

    if views >= 25000 and revenue <= 5:
        return "Good views but very low revenue"

    if views >= 10000 and rpm <= 0 and revenue <= 0:
        return "Views exist but no revenue entered yet"

    return ""


def opportunity_score(video, channel_rpm):
    views = safe_int(video.get("views"))
    rpm = safe_float(video.get("manual_rpm"))
    revenue = safe_float(video.get("manual_revenue"))

    score = 0

    if rpm >= 5:
        score += 35
    elif rpm >= 3:
        score += 28
    elif rpm >= 2:
        score += 20
    elif rpm >= 1:
        score += 12

    if revenue >= 500:
        score += 35
    elif revenue >= 250:
        score += 28
    elif revenue >= 100:
        score += 20
    elif revenue >= 25:
        score += 12

    if views >= 500000:
        score += 20
    elif views >= 250000:
        score += 16
    elif views >= 100000:
        score += 12
    elif views >= 25000:
        score += 8

    if channel_rpm > 0 and rpm > channel_rpm:
        score += 10

    return min(score, 100)


def build_video_row(video, channel_rpm):
    manual = get_manual_revenue_for_video(video)

    revenue = safe_float(manual.get("total_revenue"))
    rpm = safe_float(manual.get("average_rpm"))
    views = safe_int(video.get("views"))

    leak_reason = classify_leak({
        "views": views,
        "manual_rpm": rpm,
        "manual_revenue": revenue
    }, channel_rpm)

    return {
        "title": video.get("title", ""),
        "video_id": video.get("video_id", ""),
        "player": video.get("player_name", "Unknown"),
        "content_type": video.get("content_type", "Other"),
        "views": views,
        "manual_revenue": round(revenue, 2),
        "manual_rpm": round(rpm, 2),
        "revenue_per_1k_views": revenue_per_1k(revenue, views),
        "manual_entries": safe_int(manual.get("entries")),
        "published": video.get("published", ""),
        "upload_year": video.get("upload_year", 0),
        "leak_reason": leak_reason,
        "opportunity_score": opportunity_score({
            "views": views,
            "manual_rpm": rpm,
            "manual_revenue": revenue
        }, channel_rpm)
    }


def build_player_leak_rows(player_money):
    rows = []

    for player in player_money:
        total_videos = safe_int(player.get("total_videos"))
        manual_revenue_videos = safe_int(player.get("manual_revenue_videos"))
        total_revenue = safe_float(player.get("total_revenue"))
        average_rpm = safe_float(player.get("average_rpm"))
        average_revenue = safe_float(player.get("average_revenue"))
        total_views = safe_int(player.get("total_views"))

        coverage_percent = round((manual_revenue_videos / total_videos) * 100, 1) if total_videos else 0

        score = 0

        if average_rpm >= 5:
            score += 35
        elif average_rpm >= 3:
            score += 28
        elif average_rpm >= 2:
            score += 20
        elif average_rpm >= 1:
            score += 12

        if average_revenue >= 500:
            score += 35
        elif average_revenue >= 250:
            score += 28
        elif average_revenue >= 100:
            score += 20
        elif average_revenue >= 25:
            score += 12

        if total_videos <= 2 and average_rpm > 0:
            score += 20
        elif total_videos <= 5 and average_rpm > 0:
            score += 12

        reason = ""

        if total_videos >= 10 and average_revenue < 25:
            reason = "Many uploads but weak average revenue"
        elif total_videos <= 2 and average_rpm >= 2:
            reason = "Strong RPM with low upload count"
        elif manual_revenue_videos < total_videos:
            reason = "Not all videos have manual revenue entered"

        rows.append({
            "player": player.get("player", "Unknown"),
            "total_videos": total_videos,
            "manual_revenue_videos": manual_revenue_videos,
            "revenue_coverage_percent": coverage_percent,
            "total_views": total_views,
            "total_revenue": round(total_revenue, 2),
            "average_revenue": round(average_revenue, 2),
            "average_rpm": round(average_rpm, 2),
            "opportunity_score": min(score, 100),
            "reason": reason
        })

    return rows


@router.get("/revenue-intelligence")
def revenue_intelligence():
    videos = get_saved_videos()
    channel_rpm = get_manual_channel_rpm()

    enriched = [
        build_video_row(video, channel_rpm)
        for video in videos
    ]

    videos_with_revenue = [
        v for v in enriched
        if v["manual_revenue"] > 0 or v["manual_rpm"] > 0
    ]

    videos_missing_revenue = [
        v for v in enriched
        if v["views"] >= 10000 and v["manual_revenue"] <= 0 and v["manual_rpm"] <= 0
    ]

    revenue_leaks = [
        v for v in enriched
        if v["leak_reason"]
    ]

    high_views_low_rpm = [
        v for v in videos_with_revenue
        if v["views"] >= 10000 and v["manual_rpm"] > 0 and v["manual_rpm"] < 1
    ]

    high_rpm_low_views = [
        v for v in videos_with_revenue
        if v["manual_rpm"] >= 2 and v["views"] < 50000
    ]

    high_views_missing_revenue = [
        v for v in videos_missing_revenue
        if v["views"] >= 50000
    ]

    rpm_leaderboard = sorted(
        videos_with_revenue,
        key=lambda x: x["manual_rpm"],
        reverse=True
    )[:25]

    revenue_leaderboard = sorted(
        videos_with_revenue,
        key=lambda x: x["manual_revenue"],
        reverse=True
    )[:25]

    opportunity_videos = sorted(
        videos_with_revenue,
        key=lambda x: x["opportunity_score"],
        reverse=True
    )[:25]

    player_money = get_manual_player_revenue_summary(videos)

    player_money = [
        p for p in player_money
        if p.get("manual_revenue_videos", 0) > 0
    ]

    best_money_players = sorted(
        player_money,
        key=lambda x: x.get("total_revenue", 0),
        reverse=True
    )[:25]

    best_rpm_players = sorted(
        player_money,
        key=lambda x: x.get("average_rpm", 0),
        reverse=True
    )[:25]

    player_leaks = build_player_leak_rows(player_money)

    player_opportunities = sorted(
        player_leaks,
        key=lambda x: x["opportunity_score"],
        reverse=True
    )[:25]

    underperforming_players = [
        p for p in player_leaks
        if p["reason"] == "Many uploads but weak average revenue"
    ][:25]

    undercovered_players = [
        p for p in player_leaks
        if p["reason"] == "Strong RPM with low upload count"
    ][:25]

    content_map = {}

    for v in enriched:
        content_type = v["content_type"] or "Other"

        if content_type not in content_map:
            content_map[content_type] = {
                "content_type": content_type,
                "videos": 0,
                "views": 0,
                "manual_revenue": 0,
                "rpm_values": [],
                "manual_revenue_videos": 0
            }

        content_map[content_type]["videos"] += 1
        content_map[content_type]["views"] += v["views"]

        if v["manual_revenue"] > 0:
            content_map[content_type]["manual_revenue"] += v["manual_revenue"]
            content_map[content_type]["manual_revenue_videos"] += 1

        if v["manual_rpm"] > 0:
            content_map[content_type]["rpm_values"].append(v["manual_rpm"])

    content_patterns = []

    for item in content_map.values():
        avg_rpm = (
            round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2)
            if item["rpm_values"]
            else 0
        )

        content_patterns.append({
            "content_type": item["content_type"],
            "videos": item["videos"],
            "views": item["views"],
            "manual_revenue": round(item["manual_revenue"], 2),
            "average_revenue": safe_div(item["manual_revenue"], item["manual_revenue_videos"]),
            "average_rpm": avg_rpm,
            "manual_revenue_videos": item["manual_revenue_videos"]
        })

    content_patterns.sort(
        key=lambda x: (x["manual_revenue"], x["average_rpm"]),
        reverse=True
    )

    insights = []

    if not videos_with_revenue:
        insights.append("No manual video revenue data entered yet.")
        insights.append("Enter Revenue Tracker data to unlock RPM leaderboard, revenue leak detection, and money patterns.")
    else:
        if revenue_leaderboard:
            insights.append(
                f"Top money video is '{revenue_leaderboard[0]['title']}' with ${revenue_leaderboard[0]['manual_revenue']} manual revenue."
            )

        if rpm_leaderboard:
            insights.append(
                f"Top RPM video is '{rpm_leaderboard[0]['title']}' at ${rpm_leaderboard[0]['manual_rpm']} RPM."
            )

        if revenue_leaks:
            insights.append(
                f"{len(revenue_leaks)} revenue leak warnings were found."
            )

        if high_rpm_low_views:
            insights.append(
                f"{len(high_rpm_low_views)} videos have strong RPM but low views, which may signal hidden upside."
            )

        if high_views_missing_revenue:
            insights.append(
                f"{len(high_views_missing_revenue)} high-view videos still need manual revenue data entered."
            )

        if best_money_players:
            insights.append(
                f"Best money player so far is {best_money_players[0]['player']} with ${best_money_players[0]['total_revenue']} manual revenue."
            )

    recommendations = []

    if not videos_with_revenue:
        recommendations.append("Start by entering revenue for your top 10 viewed videos.")
        recommendations.append("For each video, enter at least 28d or lifetime revenue, views, and RPM.")
    else:
        if high_views_low_rpm:
            recommendations.append("Review high-view / low-RPM videos for copyright claims, poor ad suitability, or weak monetization.")
        if high_rpm_low_views:
            recommendations.append("Make more videos similar to high-RPM / low-view videos because they may have strong upside if given better thumbnails, titles, or reuploads.")
        if high_views_missing_revenue:
            recommendations.append("Enter revenue data for high-view videos first because they have the biggest impact on predictions.")
        if best_rpm_players:
            recommendations.append(f"Prioritize more videos similar to {best_rpm_players[0]['player']} because that player has your strongest manual RPM.")
        if undercovered_players:
            recommendations.append(f"Undercovered opportunity: {undercovered_players[0]['player']} has strong RPM but low upload count.")
        if content_patterns:
            recommendations.append(f"Best content type by manual money signal: {content_patterns[0]['content_type']}.")

    return {
        "summary": {
            "total_videos": len(videos),
            "videos_with_manual_revenue": len(videos_with_revenue),
            "manual_channel_rpm": round(channel_rpm, 2),
            "revenue_leak_count": len(revenue_leaks),
            "high_views_low_rpm_count": len(high_views_low_rpm),
            "high_rpm_low_views_count": len(high_rpm_low_views),
            "high_views_missing_revenue_count": len(high_views_missing_revenue),
            "underperforming_player_count": len(underperforming_players),
            "undercovered_player_count": len(undercovered_players)
        },
        "revenue_leaderboard": revenue_leaderboard,
        "rpm_leaderboard": rpm_leaderboard,
        "revenue_leaks": revenue_leaks[:25],
        "high_views_low_rpm": high_views_low_rpm[:25],
        "high_rpm_low_views": high_rpm_low_views[:25],
        "high_views_missing_revenue": high_views_missing_revenue[:25],
        "videos_missing_revenue": videos_missing_revenue[:25],
        "opportunity_videos": opportunity_videos,
        "best_money_players": best_money_players,
        "best_rpm_players": best_rpm_players,
        "player_opportunities": player_opportunities,
        "underperforming_players": underperforming_players,
        "undercovered_players": undercovered_players,
        "content_patterns": content_patterns,
        "insights": insights,
        "recommendations": recommendations
    }