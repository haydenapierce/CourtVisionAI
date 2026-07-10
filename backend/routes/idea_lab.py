from fastapi import APIRouter, Query, UploadFile, File
from database.db import (
    create_connection,
    get_saved_videos,
    get_best_channel_rpm,
    get_best_player_revenue_summary,
    get_latest_video_sync_info,
    get_youtube_revenue_status
)
from data.player_database import NBA_PLAYERS
import io
import json
import os
from functools import lru_cache
from datetime import datetime, timedelta

router = APIRouter()

IDEA_LAB_CACHE = {
    "top_50_created_at": None,
    "top_50_payload": None
}

IDEA_LAB_CACHE_SECONDS = 600
IDEA_LAB_DISK_CACHE_FILE = os.path.join("database", "idea_lab_top_50_cache.json")


def _idea_lab_source_marker():
    try:
        video_info = get_latest_video_sync_info() or {}
    except Exception:
        video_info = {}

    try:
        revenue_status = get_youtube_revenue_status() or {}
    except Exception:
        revenue_status = {}

    latest_revenue = revenue_status.get("latest_sync") or {}

    if isinstance(latest_revenue, dict):
        revenue_marker = "|".join([
            str(latest_revenue.get("synced_at") or ""),
            str(latest_revenue.get("end_date") or ""),
            str(latest_revenue.get("video_rows") or ""),
        ])
    else:
        revenue_marker = str(latest_revenue or "")

    return "|".join([
        str(video_info.get("latest_video_sync") or ""),
        str(video_info.get("video_count") or ""),
        str(video_info.get("total_views") or ""),
        revenue_marker,
    ])


def _load_idea_lab_disk_cache():
    try:
        if not os.path.exists(IDEA_LAB_DISK_CACHE_FILE):
            return None

        with open(IDEA_LAB_DISK_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            cached = json.load(cache_file)

        if cached.get("source_marker") != _idea_lab_source_marker():
            return None

        payload = cached.get("payload")
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def _save_idea_lab_disk_cache(payload):
    try:
        os.makedirs(os.path.dirname(IDEA_LAB_DISK_CACHE_FILE), exist_ok=True)
        temporary_file = f"{IDEA_LAB_DISK_CACHE_FILE}.tmp"

        with open(temporary_file, "w", encoding="utf-8") as cache_file:
            json.dump({
                "source_marker": _idea_lab_source_marker(),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "payload": payload,
            }, cache_file, ensure_ascii=False)

        os.replace(temporary_file, IDEA_LAB_DISK_CACHE_FILE)
    except Exception:
        pass


@lru_cache(maxsize=50000)
def normalize(text):
    if not text:
        return ""

    return (
        str(text)
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
        .replace("  ", " ")
        .strip()
    )


PLAYER_LOOKUP_BY_NORMALIZED = {
    normalize(player.get("name", "")): player
    for player in NBA_PLAYERS
    if normalize(player.get("name", ""))
}

SORTED_NBA_PLAYERS = sorted(
    NBA_PLAYERS,
    key=lambda player: (
        int(player.get("youtube_score", 0) or 0) +
        int(player.get("popularity_score", 0) or 0) +
        (70 if str(player.get("priority", "")).lower() == "elite" else 0) +
        (45 if player.get("hall_of_fame") else 0)
    ),
    reverse=True
)


def deterministic_player_value(text, low=0.0, high=1.0):
    text = normalize(text)

    if not text:
        return round((low + high) / 2, 6)

    total = 0

    for index, char in enumerate(text):
        total += (index + 1) * ord(char)

    ratio = (total % 10000) / 10000
    return round(low + ((high - low) * ratio), 6)


def deterministic_player_factor(text, low=0.94, high=1.06):
    return deterministic_player_value(text, low, high)


def normalize_prediction_format(value):
    text = normalize(value)

    if "top 10" in text or "top ten" in text:
        return "Top 10"

    return "Solo Highlight"


def infer_video_format(video_or_title):
    if isinstance(video_or_title, dict):
        content_type = video_or_title.get("content_type", "")
        title = video_or_title.get("title", "")
        combined = f"{content_type} {title}"
    else:
        combined = str(video_or_title or "")

    return normalize_prediction_format(combined)


def get_format_revenue_lookup(videos=None, period_type="lifetime"):
    """
    Uses synced YouTube Analytics / Revenue Tracker rows to learn how Top 10 vs
    Solo Highlight performs on this channel. This is what makes the same player
    produce different projections for Top 10 and Solo Highlight.
    """
    if videos is None:
        videos = get_saved_videos()

    period_type = "28d" if period_type == "30d" else (period_type or "lifetime")

    video_lookup = {
        str(video.get("video_id") or ""): video
        for video in videos
        if str(video.get("video_id") or "")
    }

    totals = {
        "Top 10": {
            "format": "Top 10",
            "total_revenue": 0,
            "total_views": 0,
            "videos_with_revenue": 0,
            "total_videos": 0,
            "rpm_values": []
        },
        "Solo Highlight": {
            "format": "Solo Highlight",
            "total_revenue": 0,
            "total_views": 0,
            "videos_with_revenue": 0,
            "total_videos": 0,
            "rpm_values": []
        }
    }

    for video in videos:
        fmt = infer_video_format(video)
        totals[fmt]["total_videos"] += 1

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT video_id, title, views, estimated_revenue, rpm
    FROM youtube_revenue_period
    WHERE period_type=?
    AND video_id != '__CHANNEL__'
    """, (period_type,))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    # Primary source: synced YouTube Analytics period rows.
    for row in rows:
        video = video_lookup.get(str(row.get("video_id") or ""), {})
        fmt = infer_video_format(video if video else row.get("title", ""))
        revenue = float(row.get("estimated_revenue") or 0)
        views = int(row.get("views") or 0)
        rpm = float(row.get("rpm") or 0)

        if revenue > 0 or views > 0:
            totals[fmt]["total_revenue"] += revenue
            totals[fmt]["total_views"] += views
            totals[fmt]["videos_with_revenue"] += 1

        if rpm > 0:
            totals[fmt]["rpm_values"].append(rpm)

    # Fallback only to already-synced video columns, not hand-entered manual projections.
    if not any(item["videos_with_revenue"] for item in totals.values()):
        for video in videos:
            revenue = float(video.get("yt_estimated_revenue") or 0)
            views = int(video.get("views") or 0)
            rpm = float(video.get("yt_estimated_rpm") or 0)

            if revenue <= 0 and rpm <= 0:
                continue

            fmt = infer_video_format(video)
            totals[fmt]["total_revenue"] += revenue
            totals[fmt]["total_views"] += views
            totals[fmt]["videos_with_revenue"] += 1

            if rpm > 0:
                totals[fmt]["rpm_values"].append(rpm)

    output = {}

    for fmt, item in totals.items():
        average_rpm = (
            round(sum(item["rpm_values"]) / len(item["rpm_values"]), 3)
            if item["rpm_values"]
            else round((item["total_revenue"] / item["total_views"]) * 1000, 3)
            if item["total_views"] > 0
            else 0
        )

        output[fmt] = {
            **item,
            "total_revenue": round(item["total_revenue"], 2),
            "average_rpm": average_rpm,
            "average_views_per_video": int(item["total_views"] / item["videos_with_revenue"]) if item["videos_with_revenue"] else 0,
            "average_revenue_per_video": round(item["total_revenue"] / item["videos_with_revenue"], 2) if item["videos_with_revenue"] else 0,
            "source": "youtube_analytics_api_revenue_tracker"
        }

    return output


def get_player_format_revenue_lookup(videos=None, period_type="lifetime"):
    if videos is None:
        videos = get_saved_videos()

    period_type = "28d" if period_type == "30d" else (period_type or "lifetime")

    video_lookup = {
        str(video.get("video_id") or ""): video
        for video in videos
        if str(video.get("video_id") or "")
    }

    totals = {}

    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
    SELECT video_id, title, views, estimated_revenue, rpm
    FROM youtube_revenue_period
    WHERE period_type=?
    AND video_id != '__CHANNEL__'
    """, (period_type,))

    rows = [dict(row) for row in cursor.fetchall()]
    connection.close()

    for row in rows:
        video = video_lookup.get(str(row.get("video_id") or ""), {})
        player = normalize(video.get("player_name") or "Unknown")

        if not player or player == "unknown":
            continue

        fmt = infer_video_format(video if video else row.get("title", ""))
        key = (player, fmt)

        if key not in totals:
            totals[key] = {
                "player": video.get("player_name") or "Unknown",
                "format": fmt,
                "total_revenue": 0,
                "total_views": 0,
                "videos_with_revenue": 0,
                "rpm_values": []
            }

        revenue = float(row.get("estimated_revenue") or 0)
        views = int(row.get("views") or 0)
        rpm = float(row.get("rpm") or 0)

        if revenue > 0 or views > 0:
            totals[key]["total_revenue"] += revenue
            totals[key]["total_views"] += views
            totals[key]["videos_with_revenue"] += 1

        if rpm > 0:
            totals[key]["rpm_values"].append(rpm)

    output = {}

    for key, item in totals.items():
        avg_rpm = (
            round(sum(item["rpm_values"]) / len(item["rpm_values"]), 3)
            if item["rpm_values"]
            else round((item["total_revenue"] / item["total_views"]) * 1000, 3)
            if item["total_views"] > 0
            else 0
        )

        output[key] = {
            **item,
            "total_revenue": round(item["total_revenue"], 2),
            "average_rpm": avg_rpm,
            "average_views_per_video": int(item["total_views"] / item["videos_with_revenue"]) if item["videos_with_revenue"] else 0,
            "average_revenue_per_video": round(item["total_revenue"] / item["videos_with_revenue"], 2) if item["videos_with_revenue"] else 0,
            "source": "youtube_analytics_api_revenue_tracker"
        }

    return output


def get_revenue_tracker_player_money_lookup(videos=None):
    if videos is None:
        videos = get_saved_videos()

    summaries = get_best_player_revenue_summary(videos)
    lookup = {}

    for item in summaries:
        player_key = normalize(item.get("player", ""))

        if not player_key:
            continue

        lookup[player_key] = item

    return lookup


def get_revenue_baseline_rpm(revenue_lookup=None):
    """
    Uses Revenue Tracker / YouTube Analytics synced revenue and RPM data.
    If no player RPM exists, falls back to channel RPM.
    If no synced revenue data exists at all, returns 0 so revenue projections do not pretend accuracy.
    """
    rpm_values = []

    if revenue_lookup:
        for item in revenue_lookup.values():
            rpm = float(item.get("average_rpm") or 0)
            if rpm > 0:
                rpm_values.append(rpm)

    if rpm_values:
        return round(sum(rpm_values) / len(rpm_values), 2)

    channel_rpm = float(get_best_channel_rpm() or 0)

    if channel_rpm > 0:
        return round(channel_rpm, 2)

    return 0


def revenue_similarity_multiplier(player):
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))

    multiplier = 1.0

    if "1960" in era or "1970" in era or "1980" in era:
        multiplier += 0.12
    elif "1990" in era:
        multiplier += 0.06
    elif "2020" in era or "modern" in content_type:
        multiplier -= 0.10

    if "legend" in content_type or "nostalgia" in content_type:
        multiplier += 0.08

    return max(0.65, min(1.25, multiplier))


def top_10_done(player_name, videos):
    player = normalize(player_name)

    for video in videos:
        title = normalize(video.get("title", ""))

        if player in title and "top 10" in title:
            return True

    return False


def score_player(player):
    score = 0

    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))
    priority = normalize(player.get("priority", ""))

    score += int(player.get("youtube_score", 0) or 0)

    # Popularity score is the new player-level demand signal.
    # It helps Idea Lab favor players people are likely to search/click,
    # while still letting synced RPM/revenue decide the money upside.
    popularity = int(player.get("popularity_score", 0) or 0)
    score += popularity * 1.35

    if priority == "elite":
        score += 70
    elif priority == "high":
        score += 40
    elif priority == "medium":
        score += 15

    if player.get("hall_of_fame"):
        score += 45

    score += int(player.get("mvp", 0) or 0) * 18
    score += int(player.get("championships", 0) or 0) * 8
    score += int(player.get("all_star", 0) or 0) * 5

    if "1960" in era or "1970" in era or "1980" in era:
        score += 45
    if "1990" in era:
        score += 35
    if "2000" in era:
        score += 20
    if "2010" in era:
        score += 10
    if "2020" in era:
        score += 8

    if "legend" in content_type:
        score += 60
    if "nostalgia" in content_type:
        score += 55
    if "top 10" in content_type:
        score += 35
    if "dunk" in content_type:
        score += 25
    if "clutch" in content_type:
        score += 25
    if "shooting" in content_type:
        score += 20
    if "highlight" in content_type:
        score += 15

    high_profit_players = [
        "kareem abdul jabbar",
        "grant hill",
        "wilt chamberlain",
        "victor wembanyama",
        "caitlin clark",
        "pete maravich",
        "dennis rodman",
        "jerry west",
        "joel embiid",
        "tyrese haliburton",
        "mugsy bogues",
        "muggsy bogues",
        "gilbert arenas",
        "patrick ewing",
        "paul pierce",
        "jason kidd",
        "vince carter",
        "tracy mcgrady",
        "allen iverson",
        "steve nash",
        "dirk nowitzki",
        "tim duncan",
        "hakeem olajuwon",
        "dominique wilkins",
        "shawn kemp",
        "penny hardaway",
        "ray allen"
    ]

    mega_names = [
        "michael jordan",
        "lebron james",
        "kobe bryant",
        "stephen curry",
        "shaquille oneal",
        "magic johnson",
        "larry bird",
        "kevin durant",
        "carmelo anthony",
        "charles barkley",
        "bill russell",
        "julius erving",
        "giannis antetokounmpo",
        "luka doncic",
        "anthony edwards",
        "ja morant",
        "damian lillard",
        "chris paul",
        "jimmy butler",
        "derrick rose",
        "kyrie irving",
        "devin booker",
        "jayson tatum",
        "shai gilgeous alexander",
        "donovan mitchell",
        "zion williamson",
        "lamelo ball"
    ]

    low_profit_players = [
        "karl malone",
        "bradley beal",
        "darius garland",
        "derrick white",
        "draymond green"
    ]

    if name in high_profit_players:
        score += 120

    if name in mega_names:
        score += 70

    if name in low_profit_players:
        score -= 80

    # Small deterministic tie-breaker so players with similar profiles do not get identical ranks.
    score += deterministic_player_value(name, 0.01, 9.99)

    return round(score, 2)


def expected_rpm(player, video_length=3, title_type="Top 10", revenue_lookup=None, format_lookup=None, player_format_lookup=None):
    """
    Revenue Tracker RPM model:
    1. Use this player's synced RPM for this exact selected format if available.
    2. Use this player's synced overall RPM if available.
    3. Use this channel's synced RPM for the selected format if available.
    4. Use channel synced RPM as a final synced fallback.
    5. If no synced revenue data exists, return 0.
    """
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))
    selected_format = normalize_prediction_format(title_type)

    revenue_lookup = revenue_lookup or {}
    format_lookup = format_lookup or {}
    player_format_lookup = player_format_lookup or {}

    direct_format = player_format_lookup.get((name, selected_format))
    revenue_tracker_player = revenue_lookup.get(name)
    format_data = format_lookup.get(selected_format, {})

    if direct_format and float(direct_format.get("average_rpm") or 0) > 0:
        rpm = float(direct_format.get("average_rpm") or 0)
    elif revenue_tracker_player and float(revenue_tracker_player.get("average_rpm") or 0) > 0:
        rpm = float(revenue_tracker_player.get("average_rpm") or 0)
    elif float(format_data.get("average_rpm") or 0) > 0:
        rpm = float(format_data.get("average_rpm") or 0)
    else:
        baseline = get_revenue_baseline_rpm(revenue_lookup)

        if baseline <= 0:
            return 0

        rpm = baseline * revenue_similarity_multiplier(player)

        if "1960" in era or "1970" in era or "1980" in era:
            rpm += 0.05

        if "1990" in era:
            rpm += 0.03

        if "legend" in content_type or "nostalgia" in content_type:
            rpm += 0.04

        if "modern" in content_type:
            rpm -= 0.05

    # Format-specific adjustment learned from channel behavior. Top 10 usually holds
    # longer watch sessions. Solo Highlight is treated differently instead of sharing
    # the same number as Top 10.
    if selected_format == "Top 10":
        rpm *= 1.04
    else:
        rpm *= 0.88

    rpm *= deterministic_player_factor(f"{name}-{selected_format}", 0.965, 1.045)

    return round(max(rpm, 0), 3)

def copyright_risk(player, title_type="Top 10"):
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))
    selected_format = normalize_prediction_format(title_type)

    risk = 50

    if "1960" in era or "1970" in era or "1980" in era:
        risk -= 20
    if "1990" in era:
        risk -= 10
    if "2020" in era:
        risk += 20
    if "modern" in content_type:
        risk += 15
    if "clips" in content_type or "poster" in content_type:
        risk += 10

    if selected_format == "Solo Highlight":
        risk += 8
    else:
        risk -= 3

    safer_names = [
        "caitlin clark",
        "pete maravich",
        "jerry west",
        "wilt chamberlain",
        "kareem abdul jabbar",
        "grant hill",
        "dennis rodman"
    ]

    if name in safer_names:
        risk -= 20

    return max(0, min(100, risk))

def subscriber_gain_prediction(projected_views, player):
    name = normalize(player.get("name", ""))
    content_type = normalize(player.get("content_type", ""))

    rate = 0.002

    if "legend" in content_type or "nostalgia" in content_type:
        rate += 0.001

    if name in [
        "michael jordan",
        "kobe bryant",
        "lebron james",
        "caitlin clark",
        "victor wembanyama",
        "allen iverson",
        "stephen curry"
    ]:
        rate += 0.0015

    return int(projected_views * rate)




def content_gap_boost(player, already_done=False):
    """
    Rewards good players who do not already have a Top 10 on the channel.
    Penalizes repeated topics so Idea Lab is a true next-upload picker.
    """
    if already_done:
        return -65

    priority = normalize(player.get("priority", ""))
    content_type = normalize(player.get("content_type", ""))
    era = normalize(player.get("era", ""))

    boost = 30

    if priority == "elite":
        boost += 45
    elif priority == "high":
        boost += 30
    elif priority == "medium":
        boost += 12

    if "legend" in content_type or "nostalgia" in content_type:
        boost += 18

    if "1970" in era or "1980" in era or "1990" in era:
        boost += 12

    return boost


def footage_interest_score(player):
    """
    Estimates how good the player is for an NBA highlights channel, not just how famous they are.
    Dunkers, guards, wings, legends, and famous names get more upside.
    """
    name = normalize(player.get("name", ""))
    position = normalize(player.get("position", ""))
    content_type = normalize(player.get("content_type", ""))
    era = normalize(player.get("era", ""))

    score = 0

    if "g" in position:
        score += 12
    if "f" in position:
        score += 10
    if "c" in position:
        score += 5

    if "dunk" in content_type:
        score += 22
    if "guard" in content_type:
        score += 12
    if "legend" in content_type:
        score += 22
    if "nostalgia" in content_type:
        score += 18

    if "1980" in era or "1990" in era or "2000" in era:
        score += 14

    highlight_names = [
        "julius erving", "michael jordan", "vince carter", "dominique wilkins",
        "shawn kemp", "tracy mcgrady", "allen iverson", "kobe bryant",
        "derrick rose", "ja morant", "anthony edwards", "zion williamson",
        "penny hardaway", "grant hill", "clyde drexler", "dwight howard"
    ]

    if name in highlight_names:
        score += 35

    return score


def decision_score_for_player(player, already_done=False, revenue_lookup=None, selected_format="Top 10", format_lookup=None, player_format_lookup=None):
    revenue_lookup = revenue_lookup or {}
    format_lookup = format_lookup or {}
    player_format_lookup = player_format_lookup or {}
    selected_format = normalize_prediction_format(selected_format)
    name = normalize(player.get("name", ""))
    popularity = int(player.get("popularity_score", 0) or 0)

    base = score_player(player)
    rpm = expected_rpm(player, 3, selected_format, revenue_lookup, format_lookup, player_format_lookup)
    risk = copyright_risk(player, selected_format)
    gap = content_gap_boost(player, already_done if selected_format == "Top 10" else False)
    footage = footage_interest_score(player)

    revenue_tracker_player = revenue_lookup.get(name)
    direct_format = player_format_lookup.get((name, selected_format))
    format_data = format_lookup.get(selected_format, {})
    revenue_signal_boost = 0

    if revenue_tracker_player:
        revenue_signal_boost += min(65, float(revenue_tracker_player.get("total_revenue") or 0) * 0.18)
        revenue_signal_boost += min(35, float(revenue_tracker_player.get("average_rpm") or 0) * 10)

    if direct_format:
        revenue_signal_boost += min(45, float(direct_format.get("average_revenue_per_video") or 0) * 0.35)
        revenue_signal_boost += min(20, float(direct_format.get("average_rpm") or 0) * 7)

    if format_data:
        revenue_signal_boost += min(25, float(format_data.get("average_revenue_per_video") or 0) * 0.12)

    risk_penalty = max(0, risk - 55) * 1.1

    format_weight = 1.0 if selected_format == "Top 10" else 0.74

    score = (
        base * 0.58 * format_weight
        + footage * 1.15
        + gap
        + revenue_signal_boost
        + (rpm * 18)
        + (popularity * 0.42)
        - risk_penalty
    )

    score += deterministic_player_value(f"{name}-{selected_format}", 0.001, 0.999)

    return round(max(0, score), 3)

def build_exact_expected_views(decision_score, player, already_done=False, selected_format="Top 10", format_lookup=None, player_format_lookup=None):
    """
    Single exact-style estimate based on synced channel behavior. Top 10 and Solo
    Highlight intentionally use different baselines and multipliers.
    """
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    priority = normalize(player.get("priority", ""))
    popularity = int(player.get("popularity_score", 0) or 0)
    selected_format = normalize_prediction_format(selected_format)
    format_lookup = format_lookup or {}
    player_format_lookup = player_format_lookup or {}

    format_data = format_lookup.get(selected_format, {})
    direct_format = player_format_lookup.get((name, selected_format))

    channel_format_views = int(format_data.get("average_views_per_video") or 0)
    direct_player_views = int(direct_format.get("average_views_per_video") or 0) if direct_format else 0

    model_base = 2800 + (decision_score * 115)

    if direct_player_views > 0:
        base = (direct_player_views * 0.65) + (model_base * 0.35)
    elif channel_format_views > 0:
        base = (channel_format_views * 0.45) + (model_base * 0.55)
    else:
        base = model_base

    if priority == "elite":
        base *= 1.18
    elif priority == "high":
        base *= 1.08

    if popularity >= 90:
        base *= 1.22
    elif popularity >= 80:
        base *= 1.14
    elif popularity >= 70:
        base *= 1.08
    elif popularity <= 25:
        base *= 0.84

    if "1970" in era or "1980" in era or "1990" in era:
        base *= 1.08

    if selected_format == "Top 10":
        base *= 1.0
    else:
        base *= 0.58

    if already_done and selected_format == "Top 10":
        base *= 0.42

    base *= deterministic_player_factor(f"{name}-{selected_format}", 0.93, 1.07)

    minimum = 2500 if selected_format == "Top 10" else 900
    return int(max(minimum, round(base)))

def build_video_idea(player, title_type="Top 10"):
    name = player.get("name", "")
    selected_format = normalize_prediction_format(title_type)

    if selected_format == "Top 10":
        return f"{name} Top 10 Plays"

    return f"{name} Solo Highlight"

def recommendation_text(player, score, rpm, risk, has_revenue_tracker_player_data=False):
    name = player.get("name", "")

    if rpm <= 0:
        return f"{name} needs more synced Revenue Tracker data before CourtVision can make a synced-money projection."

    if has_revenue_tracker_player_data and risk <= 35 and rpm >= 2:
        return f"{name} has a strong synced money signal and lower risk based on your synced Revenue Tracker data."

    if has_revenue_tracker_player_data:
        return f"{name} has a direct synced revenue signal, so this prediction is more reliable than similar-player estimates."

    if score >= 250:
        return f"{name} has upside, but this is based on similar synced channel trends because direct synced player revenue is not available yet."

    if rpm >= 2:
        return f"{name} has solid similar-player RPM potential, but views may be modest unless title and thumbnail are strong."

    if risk >= 70:
        return f"{name} could be risky for monetization. Use caution with modern NBA footage."

    return f"{name} is a decent idea, but this projection should be treated as conservative until more synced revenue is available."


def build_view_range(score, player, already_done=False):
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))

    # More conservative than the old model.
    # Old: score * 350. New: score * 175.
    base = max(5000, score * 175)
    base = base * deterministic_player_factor(name, 0.92, 1.08)

    if name in [
        "michael jordan",
        "lebron james",
        "kobe bryant",
        "stephen curry",
        "shaquille oneal",
        "wilt chamberlain",
        "kareem abdul jabbar",
        "victor wembanyama",
        "caitlin clark",
        "julius erving"
    ]:
        low = int(base * 0.60)
        high = int(base * 1.30)
    elif "legend" in content_type or "nostalgia" in content_type or "1980" in era or "1990" in era:
        low = int(base * 0.35)
        high = int(base * 0.85)
    else:
        low = int(base * 0.25)
        high = int(base * 0.65)

    if already_done:
        low = int(low * 0.35)
        high = int(high * 0.45)

    low = max(3000, low)
    high = max(low + 3000, high)

    return low, high


def build_prediction(player, already_done=False, video_length=3, title_type="Top 10", revenue_lookup=None, format_lookup=None, player_format_lookup=None):
    revenue_lookup = revenue_lookup or {}
    format_lookup = format_lookup or {}
    player_format_lookup = player_format_lookup or {}
    selected_format = normalize_prediction_format(title_type)
    name_key = normalize(player.get("name", ""))
    direct_format = player_format_lookup.get((name_key, selected_format))
    format_data = format_lookup.get(selected_format, {})

    has_revenue_tracker_player_data = (
        name_key in revenue_lookup
        and float(revenue_lookup[name_key].get("average_rpm") or 0) > 0
    )

    has_exact_format_data = bool(
        direct_format
        and (
            float(direct_format.get("average_rpm") or 0) > 0
            or int(direct_format.get("average_views_per_video") or 0) > 0
        )
    )

    score = score_player(player)
    decision_score = decision_score_for_player(
        player,
        already_done,
        revenue_lookup,
        selected_format,
        format_lookup,
        player_format_lookup
    )
    rpm = expected_rpm(player, video_length, selected_format, revenue_lookup, format_lookup, player_format_lookup)
    risk = copyright_risk(player, selected_format)

    projected_views = build_exact_expected_views(
        decision_score,
        player,
        already_done,
        selected_format,
        format_lookup,
        player_format_lookup
    )

    if rpm > 0:
        projected_revenue = round((projected_views / 1000) * rpm, 2)
        projected_revenue += deterministic_player_value(f"{name_key}-{selected_format}", 0.01, 0.99)
        projected_revenue = round(projected_revenue, 2)
    else:
        projected_revenue = 0

    subscriber_gain = subscriber_gain_prediction(projected_views, player)
    revenue_baseline = get_revenue_baseline_rpm(revenue_lookup)

    if has_exact_format_data:
        revenue_confidence = "High - exact player + format synced data"
    elif has_revenue_tracker_player_data:
        revenue_confidence = "High - synced player revenue data"
    elif float(format_data.get("average_rpm") or 0) > 0:
        revenue_confidence = "Medium - synced format revenue data"
    elif revenue_baseline > 0:
        revenue_confidence = "Medium - synced channel revenue data"
    else:
        revenue_confidence = "No synced revenue data"

    return {
        **player,
        "top_10_done": already_done,
        "selected_format": selected_format,

        "recommended_score": score,
        "decision_score": decision_score,
        "popularity_score": int(player.get("popularity_score", 0) or 0),

        "expected_rpm": rpm,
        "copyright_risk": risk,

        "projected_views": projected_views,
        "projected_views_low": projected_views,
        "projected_views_high": projected_views,

        "projected_revenue": projected_revenue,
        "projected_revenue_low": projected_revenue,
        "projected_revenue_high": projected_revenue,

        "revenue_model": "youtube_analytics_revenue_tracker_format_model",
        "revenue_confidence": revenue_confidence,
        "has_revenue_tracker_player_revenue": has_revenue_tracker_player_data,
        "has_exact_player_format_revenue": has_exact_format_data,
        "format_average_rpm": round(float(format_data.get("average_rpm") or 0), 3),
        "format_average_views": int(format_data.get("average_views_per_video") or 0),
        "player_format_average_rpm": round(float((direct_format or {}).get("average_rpm") or 0), 3),
        "player_format_average_views": int((direct_format or {}).get("average_views_per_video") or 0),
        "data_source": "Revenue Tracker / YouTube Analytics API synced rows",

        "projected_subscribers": subscriber_gain,
        "projected_subscribers_low": subscriber_gain,
        "projected_subscribers_high": subscriber_gain,

        "video_idea": build_video_idea(player, selected_format),
        "recommendation": recommendation_text(player, decision_score, rpm, risk, has_revenue_tracker_player_data)
    }

def build_players():
    saved_videos = get_saved_videos()
    revenue_lookup = get_revenue_tracker_player_money_lookup(saved_videos)
    format_lookup = get_format_revenue_lookup(saved_videos)
    player_format_lookup = get_player_format_revenue_lookup(saved_videos)
    players = []

    for p in NBA_PLAYERS:
        done = top_10_done(p.get("name", ""), saved_videos)
        players.append(build_prediction(
            p,
            done,
            title_type="Top 10",
            revenue_lookup=revenue_lookup,
            format_lookup=format_lookup,
            player_format_lookup=player_format_lookup
        ))

    players.sort(
        key=lambda x: (
            x.get("decision_score", 0),
            x.get("projected_revenue", 0),
            x.get("expected_rpm", 0),
            x.get("recommended_score", 0)
        ),
        reverse=True
    )

    return players


def score_thumbnail(image):
    from PIL import ImageStat

    image = image.convert("RGB")
    width, height = image.size

    small = image.resize((160, 90))
    gray = small.convert("L")

    stat = ImageStat.Stat(gray)
    brightness = stat.mean[0]
    contrast = stat.stddev[0]

    color_stat = ImageStat.Stat(small)
    r, g, b = color_stat.mean
    color_spread = max(r, g, b) - min(r, g, b)

    aspect_ratio = round(width / height, 2) if height else 0

    brightness_score = 100 - abs(brightness - 135) * 0.8
    contrast_score = min(100, contrast * 2.2)
    color_score = min(100, color_spread * 2.5)

    aspect_score = 100 if 1.70 <= aspect_ratio <= 1.85 else 65

    ctr_score = (
        brightness_score * 0.25
        + contrast_score * 0.35
        + color_score * 0.20
        + aspect_score * 0.20
    )

    ctr_score = int(max(0, min(100, ctr_score)))

    recommendations = []

    if brightness < 95:
        recommendations.append("Thumbnail is too dark. Brighten the player/face.")
    elif brightness > 185:
        recommendations.append("Thumbnail may be too bright. Add more contrast.")

    if contrast < 35:
        recommendations.append("Contrast is low. Darken background and make subject pop.")
    else:
        recommendations.append("Contrast looks solid for YouTube.")

    if color_spread < 18:
        recommendations.append("Colors look flat. Increase saturation or add stronger color separation.")
    else:
        recommendations.append("Color separation is good.")

    if aspect_score < 100:
        recommendations.append("Image is not close to 16:9. Use 1280x720 or 1920x1080.")

    if ctr_score >= 80:
        verdict = "Strong thumbnail. Good click potential."
    elif ctr_score >= 60:
        verdict = "Decent thumbnail, but it could be more clickable."
    else:
        verdict = "Weak thumbnail. Needs stronger contrast, brightness, or layout."

    return {
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "brightness": round(brightness, 2),
        "contrast": round(contrast, 2),
        "color_separation": round(color_spread, 2),
        "ctr_score": ctr_score,
        "brightness_score": int(max(0, min(100, brightness_score))),
        "contrast_score": int(max(0, min(100, contrast_score))),
        "color_score": int(max(0, min(100, color_score))),
        "aspect_score": aspect_score,
        "verdict": verdict,
        "recommendations": recommendations
    }


def build_top_50_uncached():
    players = build_players()

    not_done = [
        p for p in players
        if p.get("top_10_done") is False
    ]

    return {
        "top_50": not_done[:50],
        "summary": {
            "players_scored": len(players),
            "not_done_count": len(not_done),
            "model": "youtube_analytics_revenue_tracker_exact_estimate"
        }
    }


@router.get("/idea-lab/top-50")
def top_50():
    cached_at = IDEA_LAB_CACHE.get("top_50_created_at")
    cached_payload = IDEA_LAB_CACHE.get("top_50_payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=IDEA_LAB_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    disk_payload = _load_idea_lab_disk_cache()

    if disk_payload:
        IDEA_LAB_CACHE["top_50_created_at"] = datetime.now()
        IDEA_LAB_CACHE["top_50_payload"] = disk_payload
        return disk_payload

    payload = build_top_50_uncached()
    IDEA_LAB_CACHE["top_50_created_at"] = datetime.now()
    IDEA_LAB_CACHE["top_50_payload"] = payload
    _save_idea_lab_disk_cache(payload)
    return payload


@router.get("/player-predictor/search")
def player_predictor_search(q: str = Query("")):
    query = normalize(q)

    if not query:
        return {
            "query": q,
            "results": []
        }

    matches = []

    for p in NBA_PLAYERS:
        name = p.get("name", "")
        normalized_name = normalize(name)

        if normalized_name.startswith(query) or query in normalized_name:
            matches.append({
                "name": name,
                "era": p.get("era", ""),
                "position": p.get("position", ""),
                "priority": p.get("priority", "")
            })

    matches = sorted(matches, key=lambda x: x["name"])[:15]

    return {
        "query": q,
        "results": matches
    }


@router.get("/player-predictor/predict")
def player_predictor_predict(name: str = Query("")):
    query = normalize(name)
    saved_videos = get_saved_videos()
    revenue_lookup = get_revenue_tracker_player_money_lookup(saved_videos)
    format_lookup = get_format_revenue_lookup(saved_videos)
    player_format_lookup = get_player_format_revenue_lookup(saved_videos)

    for p in NBA_PLAYERS:
        if normalize(p.get("name", "")) == query:
            done = top_10_done(p.get("name", ""), saved_videos)
            format_lookup = get_format_revenue_lookup(saved_videos)
            player_format_lookup = get_player_format_revenue_lookup(saved_videos)
            prediction = build_prediction(
                p,
                done,
                title_type="Top 10",
                revenue_lookup=revenue_lookup,
                format_lookup=format_lookup,
                player_format_lookup=player_format_lookup
            )

            return {
                "found": True,
                "prediction": prediction
            }

    return {
        "found": False,
        "message": "Player not found"
    }


@router.get("/revenue-simulator")
def revenue_simulator(
    name: str,
    video_length: int = 3,
    title_type: str = "Top 10"
):
    query = normalize(name)
    saved_videos = get_saved_videos()
    revenue_lookup = get_revenue_tracker_player_money_lookup(saved_videos)
    format_lookup = get_format_revenue_lookup(saved_videos)
    player_format_lookup = get_player_format_revenue_lookup(saved_videos)

    for p in NBA_PLAYERS:
        if normalize(p.get("name", "")) == query:
            done = top_10_done(p.get("name", ""), saved_videos)

            prediction = build_prediction(
                p,
                done,
                video_length,
                title_type,
                revenue_lookup=revenue_lookup,
                format_lookup=format_lookup,
                player_format_lookup=player_format_lookup
            )

            return {
                "found": True,
                "simulation": prediction
            }

    return {
        "found": False,
        "message": "Player not found"
    }


@router.get("/player-predictor/format-baselines")
def player_predictor_format_baselines():
    saved_videos = get_saved_videos()
    return {
        "source": "Revenue Tracker / YouTube Analytics API synced rows",
        "formats": get_format_revenue_lookup(saved_videos),
        "model_note": "Player Predictor uses exact player+format rows when available, then synced player rows, then synced format rows, then synced channel RPM."
    }


@router.post("/thumbnail-analyzer/analyze")
async def analyze_thumbnail(file: UploadFile = File(...)):
    from PIL import Image

    contents = await file.read()

    image = Image.open(io.BytesIO(contents))
    result = score_thumbnail(image)

    return {
        "filename": file.filename,
        "analysis": result
    }


# =========================================================
# FINAL Idea Lab fix — NO PLAYER PHOTOS
# Adds era fallback and unique projected views.
# No player_photos.py needed.
# =========================================================

_IDEA_ERA_FALLBACKS = {
    "George Mikan": "1940s/1950s",
    "Bill Russell": "1950s/1960s",
    "Wilt Chamberlain": "1960s/1970s",
    "Jerry West": "1960s/1970s",
    "Elgin Baylor": "1960s/1970s",
    "Oscar Robertson": "1960s/1970s",
    "Kareem Abdul-Jabbar": "1970s/1980s",
    "Julius Erving": "1970s/1980s",
    "Pete Maravich": "1970s",
    "George Gervin": "1970s/1980s",
    "Larry Bird": "1980s/1990s",
    "Magic Johnson": "1980s/1990s",
    "Michael Jordan": "1980s/1990s",
    "Hakeem Olajuwon": "1980s/1990s",
    "Dominique Wilkins": "1980s/1990s",
    "Kobe Bryant": "2000s/2010s",
    "Allen Iverson": "2000s",
    "Vince Carter": "2000s/2010s",
    "Tim Duncan": "2000s/2010s",
    "Steve Nash": "2000s",
    "Jason Kidd": "2000s",
    "Jason Williams": "2000s",
    "Tracy McGrady": "2000s",
    "Ray Allen": "2000s/2010s",
    "Dwight Howard": "2000s/2010s",
    "LeBron James": "2000s/2010s/2020s",
    "Stephen Curry": "2010s/2020s",
    "Kevin Durant": "2010s/2020s",
    "Russell Westbrook": "2010s/2020s",
    "Chris Paul": "2010s/2020s",
    "Derrick Rose": "2010s",
    "Blake Griffin": "2010s",
    "Damian Lillard": "2010s/2020s",
    "Kyrie Irving": "2010s/2020s",
    "Nikola Jokic": "2020s",
    "Giannis Antetokounmpo": "2010s/2020s",
    "Luka Doncic": "2020s",
    "Ja Morant": "2020s",
    "Anthony Edwards": "2020s",
}


def _idea_safe_int(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _idea_safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0


def _idea_infer_era(player):
    name = str(player.get("name", "") or "").strip()
    for key in ["era", "primary_era", "decade", "generation"]:
        value = str(player.get(key, "") or "").strip()
        if value and value.lower() not in ["unknown", "none", "null"]:
            return value

    for key in ["start_year", "first_year", "career_start", "draft_year", "rookie_year"]:
        year = _idea_safe_int(player.get(key))
        if year:
            return f"{int(year / 10) * 10}s"

    return _IDEA_ERA_FALLBACKS.get(name, "All-Time")


def _idea_unique_views(base, name, selected_format="", rank=0, score=0, rpm=0, revenue=0):
    base = _idea_safe_int(base)
    if base <= 0:
        base = 15000

    name_key = normalize(f"{name}-{selected_format}")
    name_value = sum((i + 1) * ord(c) for i, c in enumerate(name_key))
    offset = (name_value % 2900) + ((rank + 1) * 131) + int(_idea_safe_float(score) * 5) + int(_idea_safe_float(rpm) * 73) + int(_idea_safe_float(revenue) % 89)
    return max(1500, int(base + offset))


def _idea_enrich_player_row(row, rank=0):
    output = dict(row or {})
    name = output.get("name") or output.get("player") or "Unknown"
    selected_format = output.get("selected_format") or "Top 10"

    era = output.get("era")
    if not era or str(era).lower() in ["unknown", "unknown era", "none", "null"]:
        source = next((p for p in NBA_PLAYERS if normalize(p.get("name", "")) == normalize(name)), {"name": name})
        era = _idea_infer_era(source)

    views = _idea_unique_views(
        output.get("projected_views") or output.get("expected_views"),
        name,
        selected_format,
        rank,
        output.get("decision_score") or output.get("recommended_score") or 0,
        output.get("expected_rpm") or 0,
        output.get("projected_revenue") or 0
    )

    rpm = _idea_safe_float(output.get("expected_rpm"))
    revenue = _idea_safe_float(output.get("projected_revenue"))
    if rpm > 0:
        revenue = round((views / 1000) * rpm, 2)

    output["era"] = era
    output["projected_views"] = views
    output["projected_views_low"] = views
    output["projected_views_high"] = views
    output["projected_revenue"] = revenue
    output["projected_revenue_low"] = revenue
    output["projected_revenue_high"] = revenue

    output.pop("photo_url", None)
    output.pop("wiki_url", None)
    output.pop("wiki_search_url", None)
    return output


_idea_original_build_prediction = build_prediction
_idea_original_build_players = build_players


def build_prediction(player, already_done=False, video_length=3, title_type="Top 10", revenue_lookup=None, format_lookup=None, player_format_lookup=None):
    base = _idea_original_build_prediction(
        player,
        already_done=already_done,
        video_length=video_length,
        title_type=title_type,
        revenue_lookup=revenue_lookup,
        format_lookup=format_lookup,
        player_format_lookup=player_format_lookup
    )
    return _idea_enrich_player_row(base, rank=0)


def build_players():
    players = _idea_original_build_players()
    enriched = [_idea_enrich_player_row(player, rank=index) for index, player in enumerate(players)]

    used_views = set()
    used_revenue = set()
    final = []

    for index, player in enumerate(enriched):
        row = dict(player)

        views = _idea_safe_int(row.get("projected_views"))
        while views in used_views:
            views += 137
        used_views.add(views)
        row["projected_views"] = views
        row["projected_views_low"] = views
        row["projected_views_high"] = views

        revenue = round(_idea_safe_float(row.get("projected_revenue")), 2)
        while revenue in used_revenue:
            revenue = round(revenue + 0.01, 2)
        used_revenue.add(revenue)
        row["projected_revenue"] = revenue
        row["projected_revenue_low"] = revenue
        row["projected_revenue_high"] = revenue

        final.append(row)

    final.sort(
        key=lambda x: (
            x.get("decision_score", 0),
            x.get("projected_revenue", 0),
            x.get("expected_rpm", 0),
            x.get("recommended_score", 0)
        ),
        reverse=True
    )
    return final


# =========================================================
# FINAL CAREER YEARS FIX 5.0
# Replaces vague "All-Time" era labels with actual career year ranges.
# Uses player_database fields first, then a large career-year fallback map.
# =========================================================

_CV_CAREER_YEARS_FALLBACK = {'Michael Jordan': '1984-2003', 'Julius Erving': '1971-1987', 'Kareem Abdul-Jabbar': '1969-1989', 'Wilt Chamberlain': '1959-1973', 'Larry Bird': '1979-1992', 'Magic Johnson': '1979-1996', 'Kobe Bryant': '1996-2016', 'LeBron James': '2003-present', 'Stephen Curry': '2009-present', "Shaquille O'Neal": '1992-2011', 'Hakeem Olajuwon': '1984-2002', 'Charles Barkley': '1984-2000', 'David Robinson': '1989-2003', 'Grant Hill': '1994-2013', 'Nikola Jokic': '2015-present', 'Reggie Miller': '1987-2005', 'Kevin Durant': '2007-present', 'Vince Carter': '1998-2020', 'Tracy McGrady': '1997-2013', 'Allen Iverson': '1996-2010', 'Luka Doncic': '2018-present', 'Giannis Antetokounmpo': '2013-present', 'Ja Morant': '2019-present', 'Derrick Rose': '2008-2024', 'Damian Lillard': '2012-present', 'Russell Westbrook': '2008-present', 'Kyrie Irving': '2011-present', 'Anthony Edwards': '2020-present', 'Victor Wembanyama': '2023-present', 'Elgin Baylor': '1958-1971', 'Jerry West': '1960-1974', 'Oscar Robertson': '1960-1974', 'Pete Maravich': '1970-1980', 'George Gervin': '1972-1986', 'Connie Hawkins': '1961-1976', 'Earl Monroe': '1967-1980', 'Walt Frazier': '1967-1980', 'Bernard King': '1977-1993', 'Bob McAdoo': '1972-1986', 'Elvin Hayes': '1968-1984', 'David Thompson': '1975-1984', 'Bill Russell': '1956-1969', 'Clyde Drexler': '1983-1998', 'Dominique Wilkins': '1982-1999', 'Patrick Ewing': '1985-2002', 'Karl Malone': '1985-2004', 'John Stockton': '1984-2003', 'Chris Mullin': '1985-2001', 'Kevin McHale': '1980-1993', 'Robert Parish': '1976-1997', 'Moses Malone': '1974-1995', 'Alex English': '1976-1991', 'Adrian Dantley': '1976-1991', 'Detlef Schrempf': '1985-2001', 'Mark Aguirre': '1981-1994', 'Isiah Thomas': '1981-1994', 'Penny Hardaway': '1993-2008', 'Jason Kidd': '1994-2013', 'Steve Nash': '1996-2014', 'Chris Paul': '2005-present', 'Gary Payton': '1990-2007', 'Shawn Kemp': '1989-2003', 'Dikembe Mutombo': '1991-2009', 'Yao Ming': '2002-2011', 'Dwight Howard': '2004-2022', 'Kevin Garnett': '1995-2016', 'Paul Pierce': '1998-2017', 'Ray Allen': '1996-2014', 'Carmelo Anthony': '2003-2022', "Amar'e Stoudemire": '2002-2016', 'Joe Johnson': '2001-2022', 'Deron Williams': '2005-2017', 'Manu Ginobili': '2002-2018', 'Tony Parker': '2001-2019', 'Pau Gasol': '2001-2019', 'Rasheed Wallace': '1995-2013', 'Ben Wallace': '1996-2012', 'Baron Davis': '1999-2012', 'Gilbert Arenas': '2001-2012', 'Michael Redd': '2000-2012', 'Richard Hamilton': '1999-2013', 'Dwyane Wade': '2003-2019', 'Dirk Nowitzki': '1998-2019', 'Chris Webber': '1993-2008', 'Alonzo Mourning': '1992-2008', 'Mark Price': '1986-1998', 'Kevin Johnson': '1987-2000', 'Tim Hardaway': '1989-2003', 'Mitch Richmond': '1988-2002', 'Glen Rice': '1989-2004', 'Antoine Walker': '1996-2008', 'Stephon Marbury': '1996-2009', 'Steve Francis': '1999-2008', 'Jayson Tatum': '2017-present', 'Jaylen Brown': '2016-present', 'Devin Booker': '2015-present', 'Donovan Mitchell': '2017-present', 'Trae Young': '2018-present', 'Zion Williamson': '2019-present', 'LaMelo Ball': '2020-present', 'Paolo Banchero': '2022-present', 'Chet Holmgren': '2022-present', 'Jamal Murray': '2016-present', 'Shai Gilgeous-Alexander': '2018-present', 'Tyrese Haliburton': '2020-present', "De'Aaron Fox": '2017-present', 'Jalen Brunson': '2018-present', 'Evan Mobley': '2021-present', 'Cade Cunningham': '2021-present', 'Franz Wagner': '2021-present', 'Scottie Barnes': '2021-present', 'Alperen Sengun': '2021-present', 'Amen Thompson': '2023-present', 'Tyrese Maxey': '2020-present', 'Jaren Jackson Jr.': '2018-present', 'Bam Adebayo': '2017-present', 'Brandon Ingram': '2016-present', 'Zach LaVine': '2014-present', 'Jalen Green': '2021-present', 'Jaime Jaquez Jr.': '2023-present', 'Cam Thomas': '2021-present', 'Ausar Thompson': '2023-present', 'Scoot Henderson': '2023-present', 'Jalen Williams': '2022-present', 'Mikal Bridges': '2018-present', 'Desmond Bane': '2020-present', 'Tyler Herro': '2019-present', 'Darius Garland': '2019-present', 'Anfernee Simons': '2018-present', 'Jason Williams': '1998-2011', 'Jamal Crawford': '2000-2020', 'Lou Williams': '2005-2022', 'Nate Robinson': '2005-2018', 'Muggsy Bogues': '1987-2001', 'Mugsy Bogues': '1987-2001', 'Earl Boykins': '1998-2012', 'Ricky Rubio': '2011-2023', 'Rajon Rondo': '2006-2022', 'Andre Iguodala': '2004-2023', 'Shawn Marion': '1999-2015', 'Gerald Green': '2005-2019', 'J.R. Smith': '2004-2020', 'JR Smith': '2004-2020', 'Nick Young': '2007-2018', 'Lance Stephenson': '2010-2022', 'Corey Brewer': '2007-2020', 'Michael Beasley': '2008-2019', 'Zach Randolph': '2001-2019', 'Al Jefferson': '2004-2018', 'Monta Ellis': '2005-2017', 'Larry Johnson': '1991-2001', 'Antonio McDyess': '1995-2011', 'Larry Hughes': '1998-2012', 'Jason Richardson': '2001-2015', 'Quentin Richardson': '2000-2013', 'Stephen Jackson': '2000-2014', 'Ron Artest': '1999-2017', 'Metta World Peace': '1999-2017', 'Latrell Sprewell': '1992-2005', 'Robert Horry': '1992-2008', 'Derek Fisher': '1996-2014', 'Mike Bibby': '1998-2012', 'Nick Van Exel': '1993-2006', 'Jalen Rose': '1994-2007', 'Antawn Jamison': '1998-2014', 'Josh Smith': '2004-2017', 'Josh Howard': '2003-2012', 'Kenyon Martin': '2000-2015', 'Stromile Swift': '2000-2009', 'Darius Miles': '2000-2009', 'Rudy Gay': '2006-2023', 'Andre Miller': '1999-2016', 'Juwan Howard': '1994-2013', 'Larry Nance': '1981-1994', 'Larry Nance Jr.': '2015-present', 'Aaron Gordon': '2014-present', 'DeMar DeRozan': '2009-present', 'Mark Eaton': '1982-1993', 'Manute Bol': '1985-1995', 'Shawn Bradley': '1993-2005', 'Klay Thompson': '2011-present', 'Peja Stojakovic': '1998-2011', 'Kyle Korver': '2003-2020', 'Steve Kerr': '1988-2003', 'JJ Redick': '2006-2021', 'Buddy Hield': '2016-present', 'Duncan Robinson': '2018-present', 'Mike Miller': '2000-2017', 'Danny Green': '2009-2023', 'Jason Terry': '1999-2018', 'Chauncey Billups': '1997-2014', 'Sam Cassell': '1993-2009', 'Brandon Roy': '2006-2013', 'Michael Finley': '1995-2010', 'Jerry Stackhouse': '1995-2013', 'Glenn Robinson': '1994-2005', 'Rashard Lewis': '1998-2014', 'Hedo Turkoglu': '2000-2015', 'Andrei Kirilenko': '2001-2015', 'Anderson Varejao': '2004-2021', 'Tyson Chandler': '2001-2020', 'Marcus Camby': '1996-2013', "Jermaine O'Neal": '1996-2014', 'Carlos Boozer': '2002-2017', 'David Lee': '2005-2017', 'Lamar Odom': '1999-2013', 'Andrew Bynum': '2005-2014', 'Andrew Wiggins': '2014-present', 'Khris Middleton': '2012-present', 'Jrue Holiday': '2009-present', 'Brook Lopez': '2008-present', 'Marc Gasol': '2008-2021', 'Mike Conley': '2007-present', 'Goran Dragic': '2008-2023', 'Kemba Walker': '2011-2023', 'Isaiah Thomas': '2011-present', 'John Wall': '2010-2023', 'Bradley Beal': '2012-present', 'CJ McCollum': '2013-present', 'Pascal Siakam': '2016-present', 'Fred VanVleet': '2016-present', 'Kyle Lowry': '2006-present', 'DeMarcus Cousins': '2010-2022', 'DeAndre Jordan': '2008-present', 'Serge Ibaka': '2009-2023', 'Luol Deng': '2004-2019', 'Joakim Noah': '2007-2020', 'Zydrunas Ilgauskas': '1996-2011', 'Derrick Coleman': '1990-2005', 'Shareef Abdur-Rahim': '1996-2008', 'Vlade Divac': '1989-2005', 'Arvydas Sabonis': '1981-2005', 'Toni Kukoc': '1990-2006', 'Drazen Petrovic': '1984-1993', 'Dino Radja': '1985-2003', 'Sarunas Marciulionis': '1981-1997', 'Dale Ellis': '1983-2000', 'Dell Curry': '1986-2002', 'Byron Scott': '1983-1997', 'James Worthy': '1982-1994', 'A.C. Green': '1985-2001', 'AC Green': '1985-2001', 'Horace Grant': '1987-2004', 'Dennis Rodman': '1986-2000', 'Scottie Pippen': '1987-2004', 'Joe Dumars': '1985-1999', 'Bill Laimbeer': '1979-1994', 'Mark Jackson': '1987-2004', 'Kenny Anderson': '1991-2006', 'Terrell Brandon': '1991-2002', 'Kendall Gill': '1990-2005', 'Damon Stoudamire': '1995-2008', 'Rod Strickland': '1988-2005', 'Rik Smits': '1988-2000', 'Mookie Blaylock': '1989-2002', 'Steve Smith': '1991-2005', 'Allan Houston': '1993-2005', 'Keith Van Horn': '1997-2006', 'Sam Perkins': '1984-2001', 'Cedric Ceballos': '1990-2001', 'Tom Chambers': '1981-1998', 'Xavier McDaniel': '1985-1998', 'Fat Lever': '1982-1994', 'Kiki Vandeweghe': '1980-1993', 'Walter Davis': '1977-1992', 'World B. Free': '1975-1988', 'Marques Johnson': '1977-1990', 'Sidney Moncrief': '1979-1991', 'Jack Sikma': '1977-1991', 'Artis Gilmore': '1971-1989', 'Bob Lanier': '1970-1984', 'Nate Thurmond': '1963-1977', 'Wes Unseld': '1968-1981', 'Dave Cowens': '1970-1983', 'Bob Cousy': '1950-1970', 'Sam Jones': '1957-1969', 'Hal Greer': '1958-1973', 'Dave Bing': '1966-1978', 'Tiny Archibald': '1970-1984', 'Rick Barry': '1965-1980', 'Billy Cunningham': '1965-1976', 'Dave DeBusschere': '1962-1974', 'Willis Reed': '1964-1974', 'Jo Jo White': '1969-1981', 'Gail Goodrich': '1965-1979', 'Spencer Haywood': '1969-1983', 'Maurice Cheeks': '1978-1993', 'Bobby Jones': '1974-1986', 'Dennis Johnson': '1976-1990', 'Sidney Wicks': '1971-1981', 'Ralph Sampson': '1983-1995', 'Rolando Blackman': '1981-1997', 'Jeff Hornacek': '1986-2000', 'Dan Majerle': '1988-2002', 'Mahmoud Abdul-Rauf': '1990-2001', 'Reggie Lewis': '1987-1993', 'Len Bias': '1986'}

_CV_CAREER_YEARS_LOOKUP = {normalize(name): years for name, years in _CV_CAREER_YEARS_FALLBACK.items()}


def _cv_extract_career_years_from_meta(meta):
    meta = meta or {}

    direct_keys = [
        "career_years", "years_active", "active_years", "years",
        "career", "nba_years", "playing_years"
    ]

    for key in direct_keys:
        value = str(meta.get(key, "") or "").strip()
        if value and value.lower() not in ["unknown", "none", "null", "all-time", "all time"]:
            return value.replace("–", "-").replace("—", "-")

    start_keys = ["start_year", "from_year", "first_year", "career_start", "rookie_year", "draft_year", "debut_year"]
    end_keys = ["end_year", "to_year", "last_year", "career_end", "retired_year", "final_year"]

    start = 0
    end = 0

    for key in start_keys:
        try:
            start = int(float(meta.get(key) or 0))
        except Exception:
            start = 0
        if start:
            break

    for key in end_keys:
        value = meta.get(key)
        if str(value).lower() in ["present", "current", "active", "now"]:
            return f"{start}-present" if start else "Active"
        try:
            end = int(float(value or 0))
        except Exception:
            end = 0
        if end:
            break

    if start and end:
        return f"{start}-{end}"
    if start and not end:
        # If player marked active anywhere, show present.
        active_text = normalize(" ".join(str(meta.get(k, "")) for k in ["status", "active", "current"]))
        if "active" in active_text or "true" in active_text or "current" in active_text:
            return f"{start}-present"
        return f"{start}-present"

    return ""


def _cv_career_years_for_player(player_name):
    name_key = normalize(player_name)

    # Prefer data.player_database if it has years.
    try:
        for player in NBA_PLAYERS:
            if normalize(player.get("name", "")) == name_key:
                years = _cv_extract_career_years_from_meta(player)
                if years:
                    return years
                break
    except Exception:
        pass

    # Then fallback map.
    if name_key in _CV_CAREER_YEARS_LOOKUP:
        return _CV_CAREER_YEARS_LOOKUP[name_key]

    return "Career years unavailable"



_idea5_previous_build_players = build_players
_idea5_previous_build_prediction = build_prediction


def _idea5_fix_player_row(row):
    fixed = dict(row or {})
    player = fixed.get("name") or fixed.get("player") or fixed.get("player_name") or fixed.get("topic")

    if player:
        fixed["era"] = _cv_career_years_for_player(player)
        fixed["career_years"] = fixed["era"]

    return fixed


def build_players():
    return [_idea5_fix_player_row(row) for row in _idea5_previous_build_players()]


def build_prediction(player, already_done=False, video_length=3, title_type="Top 10", revenue_lookup=None, format_lookup=None, player_format_lookup=None):
    row = _idea5_previous_build_prediction(
        player,
        already_done=already_done,
        video_length=video_length,
        title_type=title_type,
        revenue_lookup=revenue_lookup,
        format_lookup=format_lookup,
        player_format_lookup=player_format_lookup
    )
    return _idea5_fix_player_row(row)

