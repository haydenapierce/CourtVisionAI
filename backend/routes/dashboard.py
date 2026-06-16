from fastapi import APIRouter
from collections import defaultdict, Counter
from datetime import datetime
import unicodedata

from services.youtube_service import (
    get_channel_stats_by_handle,
    get_all_channel_videos,
    get_video_stats
)

from database.db import (
    save_video,
    get_saved_videos,
    get_channel_totals,
    get_top_videos
)

from data.player_database import NBA_PLAYERS

router = APIRouter()


REAL_PLAYER_RPM = {
    "kareem abdul jabbar": 1.30,
    "grant hill": 1.61,
    "wilt chamberlain": 2.05,
    "victor wembanyama": 1.75,
    "caitlin clark": 3.50,
    "pete maravich": 2.59,
    "dennis rodman": 2.57,
    "jerry west": 3.26,
    "chris andersen": 0.21,
    "joel embiid": 1.96,
    "tyrese haliburton": 2.13,
    "karl malone": 0.05,
    "tyrese maxey": 2.12,
    "derrick white": 1.40,
    "draymond green": 0.46,
    "brandon clarke": 1.63,
    "gilbert arenas": 1.50,
    "patrick ewing": 0.10,
    "bradley beal": 0.02,
    "darius garland": 0.49,
    "muggsy bogues": 0.10,
    "mugsy bogues": 0.10,
    "michael jordan": 2.75,
    "paul pierce": 2.80,
}


def safe_div(a, b):
    return round(a / b, 2) if b else 0


def normalize(text):
    text = str(text)

    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))

    return (
        text.lower()
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
        .replace("[", " ")
        .replace("]", " ")
        .replace("/", " ")
        .replace("\\", " ")
        .replace("  ", " ")
        .strip()
    )


def get_main_title_part(title):
    title_norm = normalize(title)

    separators = [
        " dunks on ",
        " dunk on ",
        " posterizes ",
        " poster on ",
        " blocks ",
        " blocks on ",
        " block on ",
        " rejects ",
        " crosses ",
        " crosses over ",
        " crossover on ",
        " vs ",
        " versus ",
        " over ",
        " on "
    ]

    main_part = title_norm

    for sep in separators:
        if sep in main_part:
            main_part = main_part.split(sep)[0]

    return main_part


def detect_player(title):
    main_part = get_main_title_part(title)
    full_title = normalize(title)

    matches = []

    for p in NBA_PLAYERS:
        player_name = p.get("name", "")
        normalized_player = normalize(player_name)

        if not normalized_player:
            continue

        if normalized_player in main_part:
            index = main_part.find(normalized_player)
            matches.append((index, len(normalized_player), player_name))

    if not matches:
        for p in NBA_PLAYERS:
            player_name = p.get("name", "")
            normalized_player = normalize(player_name)

            if not normalized_player:
                continue

            if normalized_player in full_title:
                index = full_title.find(normalized_player)
                matches.append((index, len(normalized_player), player_name))

    if not matches:
        return "Unknown"

    matches.sort(key=lambda x: (x[0], -x[1]))

    return matches[0][2]


def detect_content_type(title):
    t = title.lower()

    if "top 10" in t:
        return "Top 10"

    if "dunk" in t or "poster" in t:
        return "Dunk"

    if "clutch" in t or "buzzer" in t:
        return "Clutch"

    if "assist" in t:
        return "Assist"

    if "block" in t:
        return "Block"

    if "highlight" in t:
        return "Highlights"

    return "Other"


def estimate_rpm(player_name, content_type):
    name = normalize(player_name)

    if name in REAL_PLAYER_RPM:
        return REAL_PLAYER_RPM[name]

    rpm = 1.00

    if content_type == "Top 10":
        rpm += 0.45

    if content_type == "Clutch":
        rpm += 0.35

    if content_type == "Dunk":
        rpm += 0.15

    if content_type == "Highlights":
        rpm += 0.10

    if player_name != "Unknown":
        rpm += 0.20

    return round(max(rpm, 0.02), 2)


def estimate_revenue(views, rpm):
    return round((views / 1000) * rpm, 2)


def calculate_ai_score(views, likes, comments):
    score = 0
    score += views * 0.00005
    score += likes * 0.002
    score += comments * 0.01
    return round(score, 2)


@router.get("/dashboard/stats")
def dashboard_stats():
    data = get_channel_stats_by_handle("nbatopten")
    channel = data["items"][0]
    totals = get_channel_totals()

    return {
        "channel_name": channel["snippet"]["title"],
        "subscribers": int(channel["statistics"].get("subscriberCount", 0)),
        "total_views": int(channel["statistics"].get("viewCount", 0)),
        "video_count": int(channel["statistics"].get("videoCount", 0)),
        "database_videos": totals["total_videos"],
        "estimated_revenue": totals["estimated_revenue"]
    }


@router.get("/dashboard/sync")
def sync_channel():
    videos = get_all_channel_videos("nbatopten")
    video_ids = [v["video_id"] for v in videos]
    stats = get_video_stats(video_ids)

    lookup = {}

    for v in stats.get("items", []):
        snippet = v.get("snippet", {})
        statistics = v.get("statistics", {})

        lookup[v["id"]] = {
            "views": int(statistics.get("viewCount", 0)),
            "likes": int(statistics.get("likeCount", 0)),
            "comments": int(statistics.get("commentCount", 0)),
            "thumbnail": (
                snippet
                .get("thumbnails", {})
                .get("high", {})
                .get("url", "")
            )
        }

    synced = 0

    for video in videos:
        s = lookup.get(video["video_id"], {})
        title = video["title"]

        player_name = detect_player(title)
        content_type = detect_content_type(title)
        views = s.get("views", 0)

        rpm = estimate_rpm(player_name, content_type)
        revenue = estimate_revenue(views, rpm)

        ai_score = calculate_ai_score(
            views,
            s.get("likes", 0),
            s.get("comments", 0)
        )

        published = video["published"]
        upload_year = 0

        try:
            upload_year = datetime.fromisoformat(
                published.replace("Z", "")
            ).year
        except:
            pass

        save_video(
            title=title,
            video_id=video["video_id"],
            published=published,
            views=views,
            likes=s.get("likes", 0),
            comments=s.get("comments", 0),
            thumbnail=s.get("thumbnail", ""),
            estimated_revenue=revenue,
            estimated_rpm=rpm,
            content_type=content_type,
            player_name=player_name,
            title_length=len(title),
            upload_year=upload_year,
            ai_score=ai_score
        )

        synced += 1

    return {
        "message": "Channel synced successfully",
        "videos_synced": synced
    }


@router.get("/dashboard/saved-videos")
def saved_videos():
    videos = get_saved_videos()

    return {
        "total_saved": len(videos),
        "saved_videos": videos
    }


@router.get("/dashboard/player-rankings")
def player_rankings():
    videos = get_saved_videos()

    players = defaultdict(lambda: {
        "videos": 0,
        "views": 0,
        "revenue": 0,
        "ai_score": 0
    })

    for v in videos:
        p = v.get("player_name", "Unknown")

        if not p or p == "Unknown":
            continue

        players[p]["videos"] += 1
        players[p]["views"] += v.get("views", 0)
        players[p]["revenue"] += v.get("estimated_revenue", 0)
        players[p]["ai_score"] += v.get("ai_score", 0)

    results = []

    for name, d in players.items():
        if d["views"] < 500:
            continue

        results.append({
            "player": name,
            "videos": d["videos"],
            "total_views": d["views"],
            "average_views": safe_div(d["views"], d["videos"]),
            "estimated_revenue": round(d["revenue"], 2),
            "average_revenue": safe_div(d["revenue"], d["videos"]),
            "ai_score": round(d["ai_score"], 2)
        })

    results.sort(
        key=lambda x: x["estimated_revenue"],
        reverse=True
    )

    return {
        "player_rankings": results
    }


@router.get("/dashboard/content-analysis")
def content_analysis():
    videos = get_saved_videos()

    types = defaultdict(lambda: {
        "videos": 0,
        "views": 0,
        "revenue": 0
    })

    for v in videos:
        t = v.get("content_type", "Other")

        types[t]["videos"] += 1
        types[t]["views"] += v.get("views", 0)
        types[t]["revenue"] += v.get("estimated_revenue", 0)

    output = []

    for k, d in types.items():
        output.append({
            "type": k,
            "videos": d["videos"],
            "total_views": d["views"],
            "average_views": safe_div(d["views"], d["videos"]),
            "estimated_revenue": round(d["revenue"], 2),
            "average_revenue": safe_div(d["revenue"], d["videos"])
        })

    output.sort(
        key=lambda x: x["estimated_revenue"],
        reverse=True
    )

    return {
        "content_analysis": output
    }


@router.get("/dashboard/ai-report")
def ai_report():
    videos = get_saved_videos()

    if not videos:
        return {
            "error": "No videos found"
        }

    totals = get_channel_totals()

    best_views = max(
        videos,
        key=lambda x: x.get("views", 0)
    )

    best_money = max(
        videos,
        key=lambda x: x.get("estimated_revenue", 0)
    )

    top_money_videos = sorted(
        videos,
        key=lambda x: x.get("estimated_revenue", 0),
        reverse=True
    )[:10]

    low_money_high_views = [
        v for v in videos
        if v.get("views", 0) >= 10000 and v.get("estimated_revenue", 0) < 25
    ][:10]

    words = []

    for v in videos:
        words += v.get("title", "").split()

    top_words = Counter(words).most_common(20)

    player_data = player_rankings()["player_rankings"]
    content_data = content_analysis()["content_analysis"]

    return {
        "channel_analysis": {
            "total_videos": totals["total_videos"],
            "total_views": totals["total_views"],
            "average_views": totals["average_views"],
            "estimated_revenue": totals["estimated_revenue"]
        },
        "money_strategy": {
            "main_takeaway": "Revenue is highly uneven. Prioritize proven high-RPM players and avoid low-RPM claimed/modern clips.",
            "best_pattern": "Career Top 10 videos with legends, older footage, and players with proven RPM.",
            "avoid_pattern": "Videos that get views but extremely low RPM, such as Karl Malone, Bradley Beal, or some short modern clips.",
            "recommended_next_focus": [
                "Kareem-style legends",
                "Grant Hill / Pete Maravich / Jerry West style nostalgia",
                "Caitlin Clark high-RPM topics",
                "Longer 3+ minute career Top 10 videos",
                "Avoid low-RPM player topics unless view upside is huge"
            ]
        },
        "best_video_by_views": {
            "title": best_views["title"],
            "views": best_views["views"],
            "revenue": best_views["estimated_revenue"],
            "player": best_views["player_name"]
        },
        "best_video_by_money": {
            "title": best_money["title"],
            "views": best_money["views"],
            "revenue": best_money["estimated_revenue"],
            "player": best_money["player_name"]
        },
        "top_money_videos": top_money_videos,
        "low_money_high_views": low_money_high_views,
        "best_players_by_money": player_data[:10],
        "best_content_types_by_money": content_data[:5],
        "title_analysis": {
            "common_words": top_words
        }
    }


@router.get("/dashboard/top-videos")
def dashboard_top_videos():
    return {
        "top_videos": get_top_videos(20)
    }