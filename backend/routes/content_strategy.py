from fastapi import APIRouter
from collections import defaultdict

from database.db import (
    get_saved_videos,
    get_best_revenue_for_video,
    get_best_player_revenue_summary,
    get_best_channel_rpm
)
from data.player_database import NBA_PLAYERS

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
    return (
        str(value or "")
        .lower()
        .replace("*", "")
        .replace(".", "")
        .replace("'", "")
        .replace("’", "")
        .replace("-", " ")
        .replace("–", " ")
        .replace("—", " ")
        .replace(",", "")
        .replace(":", " ")
        .replace("|", " ")
        .replace("(", " ")
        .replace(")", " ")
        .replace("/", " ")
        .replace("  ", " ")
        .strip()
    )


def player_lookup():
    lookup = {}

    for player in NBA_PLAYERS:
        name = player.get("name", "")
        key = normalize(name)

        if key:
            lookup[key] = player

    return lookup


def get_player_meta(player_name):
    lookup = player_lookup()
    return lookup.get(normalize(player_name), {})


def era_bucket_from_text(value):
    text = normalize(value)

    if "1960" in text or "60s" in text:
        return "1960s"
    if "1970" in text or "70s" in text:
        return "1970s"
    if "1980" in text or "80s" in text:
        return "1980s"
    if "1990" in text or "90s" in text:
        return "1990s"
    if "2000" in text or "00s" in text:
        return "2000s"
    if "2010" in text or "10s" in text:
        return "2010s"
    if "2020" in text or "modern" in text:
        return "2020s / Modern"

    return "Unknown"


def get_video_era(video):
    player = video.get("player_name", "Unknown")
    meta = get_player_meta(player)
    era = era_bucket_from_text(meta.get("era", ""))

    if era != "Unknown":
        return era

    upload_year = safe_int(video.get("upload_year"))

    if upload_year:
        return f"{str(upload_year)[:3]}0s Uploads"

    return "Unknown"


def enrich_video(video):
    manual = get_best_revenue_for_video(video)

    views = safe_int(video.get("views"))
    revenue = safe_float(manual.get("total_revenue"))
    rpm = safe_float(manual.get("average_rpm"))

    return {
        "title": video.get("title", ""),
        "video_id": video.get("video_id", ""),
        "player": video.get("player_name", "Unknown") or "Unknown",
        "content_type": video.get("content_type", "Solo Highlight") or "Solo Highlight",
        "era": get_video_era(video),
        "views": views,
        "synced_revenue": round(revenue, 2),
        "synced_rpm": round(rpm, 2),
        "synced_entries": safe_int(manual.get("entries")),
        "published": video.get("published", ""),
        "upload_year": safe_int(video.get("upload_year")),
        "thumbnail": video.get("thumbnail", "")
    }


def summarize_group(name, rows, group_key):
    videos = len(rows)
    total_views = sum(safe_int(row.get("views")) for row in rows)
    total_revenue = sum(safe_float(row.get("synced_revenue")) for row in rows)
    synced_revenue_videos = len([
        row for row in rows
        if safe_float(row.get("synced_revenue")) > 0 or safe_float(row.get("synced_rpm")) > 0
    ])
    rpm_values = [
        safe_float(row.get("synced_rpm"))
        for row in rows
        if safe_float(row.get("synced_rpm")) > 0
    ]

    average_rpm = round(sum(rpm_values) / len(rpm_values), 2) if rpm_values else 0
    average_revenue = safe_div(total_revenue, synced_revenue_videos)
    average_views = safe_div(total_views, videos)

    return {
        group_key: name,
        "videos": videos,
        "synced_revenue_videos": synced_revenue_videos,
        "revenue_coverage_percent": round((synced_revenue_videos / videos) * 100, 1) if videos else 0,
        "total_views": total_views,
        "average_views": average_views,
        "total_revenue": round(total_revenue, 2),
        "average_revenue": average_revenue,
        "average_rpm": average_rpm,
        "opportunity_score": opportunity_score(average_rpm, average_revenue, total_views, videos, synced_revenue_videos)
    }


def opportunity_score(average_rpm, average_revenue, total_views, videos, synced_revenue_videos):
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

    if total_views >= 1000000:
        score += 20
    elif total_views >= 500000:
        score += 16
    elif total_views >= 100000:
        score += 10

    if videos <= 3 and synced_revenue_videos > 0:
        score += 10

    return min(score, 100)


def build_era_analysis(enriched):
    groups = defaultdict(list)

    for video in enriched:
        groups[video.get("era", "Unknown")].append(video)

    rows = [summarize_group(name, items, "era") for name, items in groups.items()]

    rows.sort(
        key=lambda x: (x.get("average_rpm", 0), x.get("average_revenue", 0), x.get("total_views", 0)),
        reverse=True
    )

    insights = []

    if rows:
        best = rows[0]
        insights.append(
            f"Best era signal is {best['era']} with ${best['average_rpm']} average RPM and ${best['average_revenue']} average revenue."
        )

        underused = [row for row in rows if row.get("videos", 0) <= 3 and row.get("average_rpm", 0) > 0]
        if underused:
            insights.append(
                f"Underused era opportunity: {underused[0]['era']} has only {underused[0]['videos']} videos but a real RPM signal."
            )
    else:
        insights.append("No era data available yet.")

    return {
        "rankings": rows,
        "best_era": rows[0] if rows else None,
        "insights": insights
    }


def build_format_analysis(enriched):
    groups = defaultdict(list)

    for video in enriched:
        groups[video.get("content_type", "Solo Highlight") or "Solo Highlight"].append(video)

    rows = [summarize_group(name, items, "format") for name, items in groups.items()]

    rows.sort(
        key=lambda x: (x.get("average_rpm", 0), x.get("average_revenue", 0), x.get("total_views", 0)),
        reverse=True
    )

    insights = []

    if rows:
        best = rows[0]
        insights.append(
            f"Best format signal is {best['format']} with ${best['average_rpm']} average RPM and ${best['average_revenue']} average revenue."
        )

        weak = [row for row in rows if row.get("videos", 0) >= 5 and row.get("average_revenue", 0) < 25]
        if weak:
            insights.append(
                f"Possible weak format: {weak[0]['format']} has {weak[0]['videos']} videos but low average revenue."
            )
    else:
        insights.append("No format data available yet.")

    return {
        "rankings": rows,
        "best_format": rows[0] if rows else None,
        "insights": insights
    }


def top_10_done(player_name, videos):
    player = normalize(player_name)

    if not player:
        return False

    for video in videos:
        title = normalize(video.get("title", ""))
        player_name_on_video = normalize(video.get("player_name", ""))

        if "top 10" in title and (player in title or player == player_name_on_video):
            return True

    return False


def build_content_gap_detector(videos, player_rows, era_analysis, format_analysis):
    gaps = []

    for player in player_rows:
        total_videos = safe_int(player.get("total_videos"))
        avg_rpm = safe_float(player.get("average_rpm"))
        avg_rev = safe_float(player.get("average_revenue"))
        total_revenue = safe_float(player.get("total_revenue"))

        if total_videos <= 2 and (avg_rpm >= 2 or avg_rev >= 100 or total_revenue >= 250):
            gaps.append({
                "type": "Undercovered money player",
                "name": player.get("player", "Unknown"),
                "reason": "Strong manual money signal with low upload count.",
                "videos": total_videos,
                "average_rpm": round(avg_rpm, 2),
                "average_revenue": round(avg_rev, 2),
                "total_revenue": round(total_revenue, 2),
                "priority_score": min(100, 60 + int(avg_rpm * 8) + int(avg_rev / 20))
            })

    saved_videos = videos
    current_players = {normalize(v.get("player_name", "")) for v in saved_videos}

    for player in NBA_PLAYERS:
        name = player.get("name", "")
        key = normalize(name)

        if not key or key in current_players:
            continue

        priority = normalize(player.get("priority", ""))
        is_major_missing = (
            player.get("hall_of_fame")
            or priority in ["elite", "high"]
            or safe_int(player.get("mvp")) > 0
            or safe_int(player.get("all_star")) >= 5
        )

        if is_major_missing:
            gaps.append({
                "type": "Missing important player",
                "name": name,
                "reason": "Important player in database with no detected channel coverage.",
                "videos": 0,
                "average_rpm": 0,
                "average_revenue": 0,
                "total_revenue": 0,
                "priority_score": 70 + safe_int(player.get("mvp")) * 5 + safe_int(player.get("all_star"))
            })

    for player in NBA_PLAYERS:
        name = player.get("name", "")
        if top_10_done(name, saved_videos):
            continue

        priority = normalize(player.get("priority", ""))

        if player.get("hall_of_fame") or priority in ["elite", "high"]:
            gaps.append({
                "type": "Missing Top 10",
                "name": name,
                "reason": "Good player does not appear to have a Top 10 video yet.",
                "videos": 0,
                "average_rpm": 0,
                "average_revenue": 0,
                "total_revenue": 0,
                "priority_score": 65 + safe_int(player.get("mvp")) * 8
            })

    for era in era_analysis.get("rankings", []):
        if era.get("videos", 0) <= 3 and era.get("average_rpm", 0) >= 1:
            gaps.append({
                "type": "Underused money era",
                "name": era.get("era"),
                "reason": "Era has real RPM signal but low upload count.",
                "videos": era.get("videos"),
                "average_rpm": era.get("average_rpm"),
                "average_revenue": era.get("average_revenue"),
                "total_revenue": era.get("total_revenue"),
                "priority_score": era.get("opportunity_score", 0)
            })

    for fmt in format_analysis.get("rankings", []):
        if fmt.get("videos", 0) <= 3 and fmt.get("average_rpm", 0) >= 1:
            gaps.append({
                "type": "Underused money format",
                "name": fmt.get("format"),
                "reason": "Format has real RPM signal but low upload count.",
                "videos": fmt.get("videos"),
                "average_rpm": fmt.get("average_rpm"),
                "average_revenue": fmt.get("average_revenue"),
                "total_revenue": fmt.get("total_revenue"),
                "priority_score": fmt.get("opportunity_score", 0)
            })

    gaps.sort(key=lambda x: x.get("priority_score", 0), reverse=True)

    return {
        "gaps": gaps[:50],
        "top_gaps": gaps[:10],
        "total_gaps": len(gaps),
        "insights": [
            f"{len(gaps)} content gaps found." if gaps else "No major content gaps found yet."
        ]
    }


def build_player_saturation(player_rows):
    rows = []

    for player in player_rows:
        total_videos = safe_int(player.get("total_videos"))
        manual_videos = safe_int(player.get("synced_revenue_videos"))
        avg_rpm = safe_float(player.get("average_rpm"))
        avg_rev = safe_float(player.get("average_revenue"))
        total_views = safe_int(player.get("total_views"))
        total_revenue = safe_float(player.get("total_revenue"))

        status = "Balanced"
        reason = "Player coverage looks reasonable."

        if total_videos >= 20 and avg_rev < 25:
            status = "Overused"
            reason = "Many uploads but weak average synced revenue."
        elif total_videos >= 10 and avg_rpm > 0 and avg_rpm < 1:
            status = "Overused / Low RPM"
            reason = "Many uploads with weak RPM."
        elif total_videos <= 2 and (avg_rpm >= 2 or avg_rev >= 100):
            status = "Underused Opportunity"
            reason = "Strong money signal with low upload count."
        elif manual_videos < total_videos:
            status = "Needs More Revenue Data"
            reason = "Some uploads do not have synced revenue entered."

        rows.append({
            "player": player.get("player", "Unknown"),
            "status": status,
            "reason": reason,
            "total_videos": total_videos,
            "synced_revenue_videos": manual_videos,
            "revenue_coverage_percent": round((manual_videos / total_videos) * 100, 1) if total_videos else 0,
            "total_views": total_views,
            "total_revenue": round(total_revenue, 2),
            "average_revenue": round(avg_rev, 2),
            "average_rpm": round(avg_rpm, 2)
        })

    overused = [row for row in rows if "Overused" in row.get("status", "")]
    underused = [row for row in rows if row.get("status") == "Underused Opportunity"]
    needs_data = [row for row in rows if row.get("status") == "Needs More Revenue Data"]

    underused.sort(key=lambda x: (x.get("average_rpm", 0), x.get("average_revenue", 0)), reverse=True)
    overused.sort(key=lambda x: x.get("total_videos", 0), reverse=True)
    needs_data.sort(key=lambda x: x.get("total_videos", 0), reverse=True)

    return {
        "all_players": rows,
        "overused_players": overused[:25],
        "underused_players": underused[:25],
        "needs_revenue_data": needs_data[:25],
        "summary": {
            "total_players": len(rows),
            "overused_count": len(overused),
            "underused_count": len(underused),
            "needs_data_count": len(needs_data)
        }
    }


def build_ai_channel_brain_2(enriched, player_rows, era_analysis, format_analysis, content_gaps, saturation):
    channel_rpm = safe_float(get_best_channel_rpm())

    player_opportunities = saturation.get("underused_players", [])
    top_gap = content_gaps.get("top_gaps", [None])[0]
    best_era = era_analysis.get("best_era")
    best_format = format_analysis.get("best_format")

    best_next_upload = None

    if player_opportunities:
        player = player_opportunities[0]
        expected_views = safe_int(player.get("total_views") / max(player.get("total_videos", 1), 1)) or 50000
        expected_rpm = safe_float(player.get("average_rpm")) or channel_rpm
        expected_revenue = round((expected_views / 1000) * expected_rpm, 2) if expected_rpm > 0 else 0

        best_next_upload = {
            "player": player.get("player"),
            "format": best_format.get("format") if best_format else "Top 10",
            "era": best_era.get("era") if best_era else "Best available era",
            "expected_views": expected_views,
            "expected_rpm": round(expected_rpm, 2),
            "expected_revenue": expected_revenue,
            "confidence": "High" if player.get("synced_revenue_videos", 0) > 0 else "Medium",
            "reason": player.get("reason")
        }
    elif top_gap:
        best_next_upload = {
            "player": top_gap.get("name"),
            "format": best_format.get("format") if best_format else "Top 10",
            "era": best_era.get("era") if best_era else "Best available era",
            "expected_views": 50000,
            "expected_rpm": channel_rpm,
            "expected_revenue": round(50 * channel_rpm, 2) if channel_rpm > 0 else 0,
            "confidence": "Medium" if channel_rpm > 0 else "Needs more revenue data",
            "reason": top_gap.get("reason")
        }

    action_plan = []

    if best_next_upload:
        action_plan.append(
            f"Next upload idea: {best_next_upload['player']} in a {best_next_upload['format']} format."
        )

    if best_era:
        action_plan.append(
            f"Lean into {best_era['era']} content because it has the strongest current era signal."
        )

    if best_format:
        action_plan.append(
            f"Use more {best_format['format']} videos because it has the strongest current format signal."
        )

    if saturation.get("overused_players"):
        action_plan.append(
            f"Avoid overloading {saturation['overused_players'][0]['player']} until the revenue signal improves."
        )

    if not action_plan:
        action_plan.append("Enter more synced revenue data to unlock stronger Strategy Center recommendations.")

    return {
        "headline": "Strategy Center 2.0 is using revenue, RPM, era, format, content gaps, and saturation signals.",
        "best_next_upload": best_next_upload,
        "best_era": best_era,
        "best_format": best_format,
        "top_content_gap": top_gap,
        "overused_warning": saturation.get("overused_players", [None])[0],
        "underused_opportunity": saturation.get("underused_players", [None])[0],
        "action_plan": action_plan
    }


def build_strategy_intelligence():
    videos = get_saved_videos()
    enriched = [enrich_video(video) for video in videos]
    player_rows = get_best_player_revenue_summary(videos)

    era_analysis = build_era_analysis(enriched)
    format_analysis = build_format_analysis(enriched)
    content_gaps = build_content_gap_detector(videos, player_rows, era_analysis, format_analysis)
    saturation = build_player_saturation(player_rows)
    brain_2 = build_ai_channel_brain_2(enriched, player_rows, era_analysis, format_analysis, content_gaps, saturation)

    videos_with_synced_revenue = len([
        video for video in enriched
        if video.get("synced_revenue", 0) > 0 or video.get("synced_rpm", 0) > 0
    ])

    insights = []

    if era_analysis.get("best_era"):
        insights.append(
            f"Best era: {era_analysis['best_era']['era']} at ${era_analysis['best_era']['average_rpm']} RPM."
        )

    if format_analysis.get("best_format"):
        insights.append(
            f"Best format: {format_analysis['best_format']['format']} at ${format_analysis['best_format']['average_rpm']} RPM."
        )

    if saturation.get("underused_players"):
        insights.append(
            f"Top underused player: {saturation['underused_players'][0]['player']}."
        )

    if content_gaps.get("top_gaps"):
        insights.append(
            f"Top content gap: {content_gaps['top_gaps'][0]['name']} ({content_gaps['top_gaps'][0]['type']})."
        )

    if not insights:
        insights.append("Enter more synced revenue data to unlock stronger strategy insights.")

    return {
        "summary": {
            "total_videos": len(videos),
            "videos_with_synced_revenue": videos_with_synced_revenue,
            "manual_channel_rpm": round(safe_float(get_best_channel_rpm()), 2),
            "era_count": len(era_analysis.get("rankings", [])),
            "format_count": len(format_analysis.get("rankings", [])),
            "content_gap_count": content_gaps.get("total_gaps", 0),
            "overused_player_count": saturation.get("summary", {}).get("overused_count", 0),
            "underused_player_count": saturation.get("summary", {}).get("underused_count", 0)
        },
        "era_analysis": era_analysis,
        "format_analysis": format_analysis,
        "content_gap_detector": content_gaps,
        "player_saturation_detector": saturation,
        "ai_channel_brain_2": brain_2,
        "insights": insights
    }


@router.get("/strategy-intelligence")
def strategy_intelligence():
    return build_strategy_intelligence()


@router.get("/era-analysis")
def era_analysis():
    videos = [enrich_video(video) for video in get_saved_videos()]
    return build_era_analysis(videos)


@router.get("/format-analysis")
def format_analysis():
    videos = [enrich_video(video) for video in get_saved_videos()]
    return build_format_analysis(videos)


@router.get("/content-gap-detector")
def content_gap_detector():
    videos = get_saved_videos()
    enriched = [enrich_video(video) for video in videos]
    player_rows = get_best_player_revenue_summary(videos)
    era_analysis = build_era_analysis(enriched)
    format_analysis = build_format_analysis(enriched)
    return build_content_gap_detector(videos, player_rows, era_analysis, format_analysis)


@router.get("/player-saturation-detector")
def player_saturation_detector():
    videos = get_saved_videos()
    player_rows = get_best_player_revenue_summary(videos)
    return build_player_saturation(player_rows)


@router.get("/ai-channel-brain-2")
def ai_channel_brain_2():
    data = build_strategy_intelligence()
    return data.get("ai_channel_brain_2", {})
