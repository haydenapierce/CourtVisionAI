from fastapi import APIRouter
from datetime import datetime
from collections import Counter
import re

from database.db import (
    get_saved_videos,
    get_best_revenue_for_video,
    get_best_channel_rpm
)

router = APIRouter()

END_SCREEN_CACHE = {"created_at": None, "payload": None}
END_SCREEN_CACHE_SECONDS = 90

STOP_WORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "vs", "at", "for",
    "with", "from", "top", "10", "ten", "nba", "career", "highlights", "plays",
    "play", "best", "greatest", "full", "game", "season", "all", "time"
}

RELATED_PLAYER_GROUPS = [
    {"julius erving", "michael jordan", "vince carter", "dominique wilkins", "kobe bryant", "lebron james", "ja morant", "anthony edwards", "shawn kemp"},
    {"kareem abdul-jabbar", "wilt chamberlain", "shaquille o'neal", "hakeem olajuwon", "david robinson", "bill russell", "tim duncan", "patrick ewing"},
    {"magic johnson", "larry bird", "julius erving", "kareem abdul-jabbar", "michael jordan", "isiah thomas"},
    {"allen iverson", "kyrie irving", "stephen curry", "jason williams", "pete maravich", "earl monroe", "steve nash"},
    {"nikola jokic", "luka doncic", "lebron james", "magic johnson", "larry bird", "jason kidd", "chris paul", "steve nash"},
    {"michael jordan", "kobe bryant", "lebron james", "kevin durant", "carmelo anthony", "tracy mcgrady", "grant hill"},
]

FORMAT_KEYWORDS = {
    "dunk": "Dunks",
    "dunks": "Dunks",
    "poster": "Dunks",
    "assist": "Assists",
    "assists": "Assists",
    "pass": "Assists",
    "passes": "Assists",
    "block": "Blocks",
    "blocks": "Blocks",
    "clutch": "Clutch",
    "winner": "Clutch",
    "buzzer": "Clutch",
    "shot": "Clutch",
    "shots": "Clutch",
    "crossover": "Crossovers",
    "crossovers": "Crossovers",
    "handle": "Crossovers",
    "handles": "Crossovers",
}


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
        .strip()
    )


def normalize_player(value):
    player = normalize(value)
    return re.sub(r"\s+", " ", player).strip()


def normalize_format(value, title=""):
    text = normalize(f"{value} {title}")
    if "top 10" in text or "top ten" in text:
        return "Top 10"
    return "Solo Highlight"


def topic_bucket(title):
    text = normalize(title)
    for keyword, bucket in FORMAT_KEYWORDS.items():
        if keyword in text.split() or keyword in text:
            return bucket
    return "Plays"


def title_keywords(title):
    words = re.findall(r"[a-zA-Z0-9]+", normalize(title))
    return {word for word in words if len(word) >= 3 and word not in STOP_WORDS}


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


def player_related_score(source_player, candidate_player):
    source = normalize_player(source_player)
    candidate = normalize_player(candidate_player)

    if not source or source == "unknown" or not candidate or candidate == "unknown":
        return 0

    if source == candidate:
        return 26

    for group in RELATED_PLAYER_GROUPS:
        normalized_group = {normalize_player(name) for name in group}
        if source in normalized_group and candidate in normalized_group:
            return 13

    return 0


def get_video_money(video):
    views = safe_int(video.get("views"))

    revenue = safe_float(video.get("yt_estimated_revenue") or video.get("estimated_revenue"))
    rpm = safe_float(video.get("yt_estimated_rpm") or video.get("estimated_rpm"))

    if rpm <= 0 and revenue > 0 and views > 0:
        rpm = (revenue / views) * 1000

    if revenue > 0 or rpm > 0:
        return {
            "revenue": round(revenue, 2),
            "rpm": round(rpm, 2),
            "source": "synced_video_row"
        }

    try:
        money = get_best_revenue_for_video(video) or {}
    except TypeError:
        money = get_best_revenue_for_video(video, "lifetime") or {}
    except Exception:
        money = {}

    revenue = safe_float(
        money.get("total_revenue")
        or money.get("estimated_revenue")
        or money.get("amount")
    )
    rpm = safe_float(
        money.get("average_rpm")
        or money.get("rpm")
        or money.get("estimated_rpm")
    )

    if rpm <= 0 and revenue > 0 and views > 0:
        rpm = (revenue / views) * 1000

    return {
        "revenue": round(revenue, 2),
        "rpm": round(rpm, 2),
        "source": money.get("source", "youtube_analytics_api_revenue_tracker")
    }


def enrich_video(video):
    money = get_video_money(video)
    title = video.get("title", "")
    player = video.get("player_name", "Unknown") or "Unknown"
    content_format = normalize_format(video.get("content_type", ""), title)
    views = safe_int(video.get("views"))
    age_days = video_age_days(video)

    return {
        "title": title,
        "video_id": video.get("video_id", ""),
        "thumbnail": video.get("thumbnail", ""),
        "player": player,
        "player_name": player,
        "content_type": content_format,
        "format": content_format,
        "topic_bucket": topic_bucket(title),
        "views": views,
        "revenue": money["revenue"],
        "rpm": money["rpm"],
        "revenue_source": money["source"],
        "published": video.get("published", ""),
        "upload_year": safe_int(video.get("upload_year")),
        "age_days": age_days,
        "views_per_day": safe_div(views, age_days),
        "keywords": sorted(title_keywords(title))
    }


def percentile_score(value, values):
    value = safe_float(value)
    clean = sorted([safe_float(v) for v in values if safe_float(v) > 0])
    if not clean or value <= 0:
        return 0
    below = len([v for v in clean if v <= value])
    return min(100, max(0, round((below / len(clean)) * 100)))


def score_recommendation(source, candidate, rpm_values, revenue_values, views_values, channel_rpm):
    score = 0
    reasons = []
    breakdown = {}

    player_score = player_related_score(source.get("player"), candidate.get("player"))
    score += player_score
    breakdown["player_match"] = min(100, round((player_score / 26) * 100)) if player_score else 0
    if player_score >= 26:
        reasons.append("Same player")
    elif player_score > 0:
        reasons.append("Related player audience")

    if source.get("format") == candidate.get("format"):
        score += 16
        breakdown["format_match"] = 100
        reasons.append("Same video format")
    else:
        breakdown["format_match"] = 35

    if source.get("topic_bucket") == candidate.get("topic_bucket") and source.get("topic_bucket") != "Plays":
        score += 12
        breakdown["topic_match"] = 100
        reasons.append(f"Same topic: {source.get('topic_bucket')}")
    else:
        shared_keywords = set(source.get("keywords", [])) & set(candidate.get("keywords", []))
        keyword_points = min(10, len(shared_keywords) * 2)
        score += keyword_points
        breakdown["topic_match"] = min(100, keyword_points * 10)
        if shared_keywords:
            reasons.append("Similar title keywords")

    rpm_percentile = percentile_score(candidate.get("rpm"), rpm_values)
    revenue_percentile = percentile_score(candidate.get("revenue"), revenue_values)
    views_percentile = percentile_score(candidate.get("views"), views_values)

    # Money-first scoring: revenue and RPM matter more than raw views because
    # the goal is to maximize long-term channel revenue, not just clicks.
    rpm_points = round((rpm_percentile / 100) * 24, 2)
    revenue_points = round((revenue_percentile / 100) * 25, 2)
    views_points = round((views_percentile / 100) * 5, 2)

    score += rpm_points + revenue_points + views_points
    breakdown["rpm_signal"] = rpm_percentile
    breakdown["revenue_signal"] = revenue_percentile
    breakdown["views_signal"] = views_percentile

    if candidate.get("rpm", 0) >= max(2, channel_rpm or 0):
        reasons.append("Strong RPM")
    if candidate.get("revenue", 0) > 0:
        reasons.append("Synced revenue signal")
    if candidate.get("views", 0) >= 100000:
        reasons.append("Proven high-view video")

    if candidate.get("age_days", 9999) >= 90:
        score += 5
        breakdown["evergreen_signal"] = 75
        reasons.append("Evergreen upload")
    else:
        breakdown["evergreen_signal"] = 45

    if source.get("format") == "Top 10" and candidate.get("format") == "Top 10":
        score += 5
        reasons.append("Strong Top 10 session path")

    if source.get("video_id") == candidate.get("video_id"):
        score = 0

    final_score = min(100, round(score, 1))
    confidence = "High" if final_score >= 78 else "Medium" if final_score >= 58 else "Low"

    source_views = safe_int(source.get("views"))
    candidate_rpm = safe_float(candidate.get("rpm")) or safe_float(channel_rpm)
    money_bonus = 1.0
    if safe_float(candidate.get("revenue")) >= 100:
        money_bonus += 0.18
    if safe_float(candidate.get("rpm")) >= max(2, channel_rpm or 0):
        money_bonus += 0.16

    estimated_click_rate = max(0.0025, min(0.04, (final_score / 3200) * money_bonus))
    estimated_extra_views = int(source_views * estimated_click_rate)
    estimated_extra_revenue = round((estimated_extra_views / 1000) * candidate_rpm, 2) if candidate_rpm > 0 else 0
    estimated_watch_minutes = int(estimated_extra_views * 2.4)

    if not reasons:
        reasons.append("Best available match from current synced library")

    return {
        "video_id": candidate.get("video_id"),
        "title": candidate.get("title"),
        "thumbnail": candidate.get("thumbnail"),
        "player": candidate.get("player"),
        "content_type": candidate.get("content_type"),
        "topic_bucket": candidate.get("topic_bucket"),
        "views": candidate.get("views"),
        "revenue": candidate.get("revenue"),
        "rpm": candidate.get("rpm"),
        "score": final_score,
        "confidence": confidence,
        "reasons": reasons[:7],
        "breakdown": breakdown,
        "estimated_extra_views": estimated_extra_views,
        "estimated_extra_revenue": estimated_extra_revenue,
        "estimated_watch_minutes": estimated_watch_minutes
    }


def optimize_video(source, candidates, rpm_values, revenue_values, views_values, channel_rpm):
    scored = [
        score_recommendation(source, candidate, rpm_values, revenue_values, views_values, channel_rpm)
        for candidate in candidates
        if candidate.get("video_id") and candidate.get("video_id") != source.get("video_id")
    ]

    scored = [item for item in scored if item.get("score", 0) > 0]
    scored.sort(
        key=lambda item: (
            item.get("score", 0),
            item.get("estimated_extra_revenue", 0),
            item.get("rpm", 0),
            item.get("revenue", 0),
            item.get("views", 0)
        ),
        reverse=True
    )

    recommendations = scored[:2]
    avg_score = safe_div(sum(item.get("score", 0) for item in recommendations), len(recommendations))
    estimated_extra_views = sum(safe_int(item.get("estimated_extra_views")) for item in recommendations)
    estimated_extra_revenue = round(sum(safe_float(item.get("estimated_extra_revenue")) for item in recommendations), 2)
    estimated_watch_minutes = sum(safe_int(item.get("estimated_watch_minutes")) for item in recommendations)

    status = "Ready" if len(recommendations) >= 2 else "Needs More Videos"

    summary_reason = ""
    if recommendations:
        first = recommendations[0]
        summary_reason = f"Best path starts with {first['title']} because it has a {first['score']}/100 match score and {', '.join(first['reasons'][:3]).lower()}."
    else:
        summary_reason = "Not enough eligible videos were found for this source video yet."

    return {
        "source_video": source,
        "recommendations": recommendations,
        "alternatives": scored[2:7],
        "end_screen_score": round(avg_score, 1),
        "estimated_extra_views": estimated_extra_views,
        "estimated_extra_revenue": estimated_extra_revenue,
        "estimated_watch_minutes": estimated_watch_minutes,
        "status": status,
        "summary_reason": summary_reason
    }


def build_end_screen_optimizer():
    videos = [enrich_video(video) for video in get_saved_videos()]
    videos = [video for video in videos if video.get("video_id")]

    # User-facing list should follow the channel upload timeline:
    # most recent upload first, oldest upload last.
    videos.sort(
        key=lambda video: parse_date(video.get("published")) or datetime.min,
        reverse=True
    )

    channel_rpm = safe_float(get_best_channel_rpm())

    rpm_values = [video.get("rpm", 0) for video in videos]
    revenue_values = [video.get("revenue", 0) for video in videos]
    views_values = [video.get("views", 0) for video in videos]

    optimizations = [
        optimize_video(video, videos, rpm_values, revenue_values, views_values, channel_rpm)
        for video in videos
    ]

    # Keep the main channel plan in upload order so it is easy to work through
    # the channel from newest video to oldest video. The top opportunities list
    # below still ranks by upside.
    optimizations.sort(
        key=lambda item: parse_date(item.get("source_video", {}).get("published")) or datetime.min,
        reverse=True
    )

    ready = [item for item in optimizations if item.get("status") == "Ready"]
    avg_score = safe_div(sum(item.get("end_screen_score", 0) for item in ready), len(ready))
    total_extra_views = sum(safe_int(item.get("estimated_extra_views")) for item in ready)
    total_extra_revenue = round(sum(safe_float(item.get("estimated_extra_revenue")) for item in ready), 2)
    total_watch_minutes = sum(safe_int(item.get("estimated_watch_minutes")) for item in ready)

    player_counts = Counter(video.get("player", "Unknown") for video in videos if video.get("player"))
    format_counts = Counter(video.get("format", "Solo Highlight") for video in videos)

    top_opportunities = sorted(
        optimizations,
        key=lambda item: (
            item.get("estimated_extra_revenue", 0),
            item.get("estimated_extra_views", 0),
            item.get("end_screen_score", 0)
        ),
        reverse=True
    )[:10]

    insights = []
    if ready:
        top = ready[0]
        insights.append(f"{len(ready)} videos have two ready end-screen recommendations.")
        insights.append(f"Top opportunity: '{top['source_video']['title']}' could gain about {top['estimated_extra_views']:,} extra views from stronger end screens.")
    else:
        insights.append("Add or sync more videos to unlock stronger end-screen recommendations.")

    if player_counts:
        most_common_player = player_counts.most_common(1)[0][0]
        insights.append(f"Your strongest recommendation network is currently built around {most_common_player} content.")

    if format_counts:
        best_format = format_counts.most_common(1)[0][0]
        insights.append(f"Most available end-screen inventory is {best_format}, so matching format paths should be prioritized.")

    recommendations = []
    if top_opportunities:
        top = top_opportunities[0]
        recommendations.append(f"Update '{top['source_video']['title']}' first because it has the largest projected end-screen upside.")
    if total_extra_revenue > 0:
        recommendations.append(f"Across ready videos, estimated end-screen opportunity is about ${total_extra_revenue:.2f} in additional long-term revenue.")
    if not recommendations:
        recommendations.append("Keep syncing YouTube Analytics and add more uploads so CourtVision can build stronger end-screen paths.")

    return {
        "summary": {
            "total_videos_scanned": len(videos),
            "videos_ready": len(ready),
            "videos_needing_more_matches": len(optimizations) - len(ready),
            "overall_end_screen_score": round(avg_score, 1),
            "estimated_extra_views": total_extra_views,
            "estimated_extra_revenue": total_extra_revenue,
            "estimated_watch_minutes": total_watch_minutes,
            "channel_rpm": round(channel_rpm, 2),
            "data_source": "youtube_analytics_api_revenue_tracker"
        },
        "top_opportunities": top_opportunities,
        "all_optimizations": optimizations,
        "insights": insights,
        "recommendations": recommendations,
        "filters": {
            "players": sorted(player_counts.keys()),
            "formats": sorted(format_counts.keys())
        },
        "generated_at": datetime.now().isoformat(timespec="seconds")
    }


@router.get("/end-screen-optimizer")
def end_screen_optimizer():
    now = datetime.now()
    cached_at = END_SCREEN_CACHE.get("created_at")

    if cached_at and END_SCREEN_CACHE.get("payload"):
        age = (now - cached_at).total_seconds()
        if age <= END_SCREEN_CACHE_SECONDS:
            return END_SCREEN_CACHE["payload"]

    payload = build_end_screen_optimizer()
    END_SCREEN_CACHE["created_at"] = now
    END_SCREEN_CACHE["payload"] = payload
    return payload


@router.get("/end-screen-optimizer/{video_id}")
def end_screen_optimizer_for_video(video_id: str):
    data = build_end_screen_optimizer()
    match = None

    for item in data.get("all_optimizations", []):
        if item.get("source_video", {}).get("video_id") == video_id:
            match = item
            break

    return {
        "found": bool(match),
        "optimization": match,
        "summary": data.get("summary", {}),
        "insights": data.get("insights", []),
        "recommendations": data.get("recommendations", [])
    }
