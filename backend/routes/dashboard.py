from fastapi import APIRouter
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import unicodedata
from functools import lru_cache

from services.youtube_service import (
    get_channel_stats_by_handle,
    get_all_channel_videos,
    get_video_stats
)

from database.db import (
    save_video,
    save_videos_bulk,
    get_saved_videos,
    get_channel_totals,
    get_top_videos,
    get_best_revenue_for_video,
    get_best_player_revenue_summary,
    get_best_channel_rpm,
    get_best_revenue_summary,
    get_latest_video_sync_info
)

from data.player_database import NBA_PLAYERS

router = APIRouter()

MIN_TREND_VIEWS = 500

PLAYER_INDEX = []
PLAYER_META_BY_NORMALIZED = {}

def build_player_index():
    global PLAYER_INDEX, PLAYER_META_BY_NORMALIZED

    if PLAYER_INDEX:
        return

    rows = []

    for player in NBA_PLAYERS:
        name = player.get("name", "")
        normalized = normalize(name)

        if not normalized:
            continue

        rows.append((normalized, name, player))
        PLAYER_META_BY_NORMALIZED[normalized] = player

    # Longest names first prevents shorter partial names from winning too early.
    PLAYER_INDEX = sorted(rows, key=lambda item: len(item[0]), reverse=True)



def safe_div(a, b):
    try:
        return round(float(a) / float(b), 2) if float(b) else 0
    except Exception:
        return 0


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



def has_enough_views_for_trend(video):
    """
    Use this only for strategy/trend/leaderboard calculations.
    Do not use it for saved videos, channel totals, sync counts, or lifetime totals.
    """
    return safe_int(video.get("views")) >= MIN_TREND_VIEWS



@lru_cache(maxsize=20000)
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


build_player_index()


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


@lru_cache(maxsize=10000)
def detect_player(title):
    main_part = get_main_title_part(title)
    full_title = normalize(title)

    matches = []

    for normalized_player, player_name, _meta in PLAYER_INDEX:
        if normalized_player in main_part:
            index = main_part.find(normalized_player)
            matches.append((index, -len(normalized_player), player_name))

    if not matches:
        for normalized_player, player_name, _meta in PLAYER_INDEX:
            if normalized_player in full_title:
                index = full_title.find(normalized_player)
                matches.append((index, -len(normalized_player), player_name))

    if not matches:
        return "Unknown"

    matches.sort()
    return matches[0][2]


def detect_content_type(title):
    t = str(title or "").lower()

    if "top 10" in t or "top ten" in t:
        return "Top 10"

    # CourtVision now only uses two formats. Every non-Top 10 clip is a Solo Highlight.
    return "Solo Highlight"


def detect_content_subtype(title):
    t = str(title or "").lower()

    if "top 10" in t or "top ten" in t:
        if "dunk" in t or "dunks" in t:
            return "Top 10 Dunks"
        if "play" in t or "plays" in t:
            return "Top 10 Plays"
        if "block" in t or "blocks" in t:
            return "Top 10 Blocks"
        if "assist" in t or "assists" in t or "pass" in t or "passes" in t:
            return "Top 10 Assists"
        return "Top 10"

    return "Solo Highlight"


def calculate_ai_score(views, likes, comments):
    score = 0
    score += views * 0.00005
    score += likes * 0.002
    score += comments * 0.01
    return round(score, 2)


def get_video_age_days(published):
    try:
        published_date = datetime.fromisoformat(str(published).replace("Z", ""))
        return max(1, (datetime.now() - published_date).days)
    except Exception:
        return 9999


def attach_synced_money(video):
    """
    Safely attaches synced YouTube Analytics / Revenue Tracker money.

    This must never crash /dashboard/saved-videos. If a synced revenue row is
    missing, incomplete, or still lagging from YouTube Analytics, the video
    still returns normally with zero money fields.
    """
    try:
        money = get_best_revenue_for_video(video) or {}
    except Exception:
        money = {}

    revenue = float(
        money.get("total_revenue")
        or money.get("synced_revenue")
        or money.get("estimated_revenue")
        or money.get("amount")
        or video.get("synced_revenue")
        or video.get("estimated_revenue")
        or video.get("yt_estimated_revenue")
        or video.get("manual_revenue")
        or 0
    )

    rpm = float(
        money.get("average_rpm")
        or money.get("synced_rpm")
        or money.get("rpm")
        or money.get("estimated_rpm")
        or video.get("synced_rpm")
        or video.get("estimated_rpm")
        or video.get("yt_estimated_rpm")
        or video.get("manual_rpm")
        or 0
    )

    entries = int(
        money.get("entries")
        or money.get("periods_count")
        or 0
    )

    periods = money.get("periods") or {}

    updated = dict(video)
    updated["synced_revenue"] = round(revenue, 2)
    updated["synced_rpm"] = round(rpm, 2)
    updated["synced_revenue_entries"] = entries
    updated["synced_revenue_periods"] = periods
    updated["estimated_revenue"] = round(revenue, 2)
    updated["estimated_rpm"] = round(rpm, 2)
    updated["revenue_source"] = money.get("source", "youtube_analytics_api_or_zero")

    # Backward-compatible keys for any older frontend sections.
    updated["manual_revenue"] = round(revenue, 2)
    updated["manual_rpm"] = round(rpm, 2)
    updated["manual_revenue_entries"] = entries
    updated["manual_revenue_periods"] = periods

    return updated



def detect_top10_type_from_title(title):
    t = normalize(title)

    if "top 10" not in t and "top ten" not in t:
        return ""

    if "dunk" in t:
        return "Top 10 Dunks"
    if "assist" in t or "pass" in t or "passes" in t:
        return "Top 10 Assists"
    if "block" in t:
        return "Top 10 Blocks"
    if "clutch" in t or "game winner" in t or "buzzer" in t:
        return "Top 10 Clutch Shots"
    if "shot" in t or "shots" in t or "three" in t or "threes" in t or "3s" in t:
        return "Top 10 Clutch Shots"
    if "cross" in t or "handle" in t or "dribble" in t:
        return "Top 10 Crossovers"

    return "Top 10 Plays"


def player_role_tags(player_name, meta=None):
    meta = meta or {}
    text = normalize(
        " ".join([
            str(player_name or ""),
            str(meta.get("position", "")),
            str(meta.get("pos", "")),
            str(meta.get("role", "")),
            str(meta.get("tags", "")),
            str(meta.get("era", ""))
        ])
    )

    tags = set()

    big_terms = [" c ", "center", "f c", "c f", "pf", "power forward", "shaq", "hakeem", "mutombo", "duncan", "garnett", "david robinson", "bill russell", "wilt", "kareem", "ewing", "mourning", "ben wallace"]
    passer_terms = ["pg", "point guard", "magic", "john stockton", "steve nash", "jason kidd", "chris paul", "isiah thomas", "rajon rondo", "trae young", "luka", "lebron", "jokic", "kyrie"]
    dunk_terms = ["julius erving", "vince carter", "dominique", "jordan", "lebron", "shawn kemp", "blake griffin", "dwight", "ja morant", "anthony edwards", "zion", "wembanyama", "giannis"]
    clutch_terms = ["jordan", "kobe", "reggie miller", "larry bird", "ray allen", "damian lillard", "curry", "paul pierce", "kyrie", "magic", "lebron", "durant"]
    handles_terms = ["kyrie", "iverson", "curry", "jamal crawford", "isiah thomas", "tim hardaway", "chris paul", "jason williams"]

    padded = f" {text} "

    if any(term in padded for term in big_terms):
        tags.add("blocks")
        tags.add("dunks")

    if any(term in padded for term in passer_terms):
        tags.add("assists")

    if any(term in padded for term in dunk_terms):
        tags.add("dunks")

    if any(term in padded for term in clutch_terms):
        tags.add("clutch")

    if any(term in padded for term in handles_terms):
        tags.add("handles")

    # Guards/wings can generally have shots/clutch; bigs should not default to assists.
    if "g" in str(meta.get("pos", meta.get("position", ""))).lower() or "guard" in padded:
        tags.add("shots")
        tags.add("clutch")
        tags.add("handles")

    return tags


def next_top10_type_for_player(player_name, done_types, meta=None):
    """
    Always suggest Top 10 Plays first if it has not been done.
    If Top 10 Plays is already done, suggest a smart alternate type.
    """
    done = {str(x or "").strip() for x in done_types if x}
    tags = player_role_tags(player_name, meta)

    if "Top 10 Plays" not in done:
        return "Top 10 Plays"

    ordered = []

    if "dunks" in tags:
        ordered.append("Top 10 Dunks")
    if "assists" in tags:
        ordered.append("Top 10 Assists")
    if "blocks" in tags:
        ordered.append("Top 10 Blocks")
    if "clutch" in tags:
        ordered.append("Top 10 Clutch Shots")
    if "handles" in tags:
        ordered.append("Top 10 Crossovers")
    if "shots" in tags:
        ordered.append("Top 10 Clutch Shots")

    # Safe general fallback types
    ordered.extend([
        "Top 10 Dunks",
        "Top 10 Clutch Shots",
        "Top 10 Clutch Shots"
    ])

    # Keep blocks/assists restricted to fitting players only.
    for suggestion in ordered:
        if suggestion == "Top 10 Blocks" and "blocks" not in tags:
            continue
        if suggestion == "Top 10 Assists" and "assists" not in tags:
            continue
        if suggestion not in done:
            return suggestion

    return "Top 10 Plays"


CUSTOM_STRATEGY_IDEAS = [
    # Elite / direct user list
    {"player": "Mason Plumlee", "format": "Top 10 Plays", "tier": "fan_request", "title": "Mason Plumlee Top 10 Plays"},
    {"player": "Allen Iverson", "format": "Top 10 Crossovers", "tier": "elite", "title": "Allen Iverson Top 10 Crossovers of Career"},
    {"player": "Magic Johnson", "format": "Top 10 Assists", "tier": "elite", "title": "Magic Johnson Top 10 Assists of Career"},
    {"player": "Larry Bird", "format": "Top 10 Assists", "tier": "elite", "title": "Larry Bird Top 10 Assists of Career"},
    {"player": "Wilt Chamberlain", "format": "Top 10 Blocks", "tier": "elite", "title": "Wilt Chamberlain Top 10 Blocks of Career"},
    {"player": "Michael Jordan", "format": "Top 10 Clutch Plays", "tier": "elite", "title": "Michael Jordan Top 10 Clutch Plays of Career"},
    {"player": "Kobe Bryant", "format": "Top 10 Clutch Plays", "tier": "elite", "title": "Kobe Bryant Top 10 Clutch Plays of Career"},
    {"player": "Pete Maravich", "format": "Top 10 Assists", "tier": "elite", "title": "Pete Maravich Top 10 Assists of Career"},
    {"player": "Vince Carter", "format": "Top 10 Dunks", "tier": "elite", "title": "Vince Carter Top 10 Dunks of Career"},
    {"player": "Stephen Curry", "format": "Top 10 3-Pointers", "tier": "elite", "title": "Stephen Curry Top 10 3-Pointers of Career"},
    {"player": "LeBron James", "format": "Top 10 Dunks", "tier": "elite", "title": "LeBron James Top 10 Dunks of Career"},
    {"player": "Kareem Abdul-Jabbar", "format": "Top 10 Skyhooks", "tier": "elite", "title": "Kareem Abdul-Jabbar Top 10 Skyhooks of Career"},
    {"player": "Hakeem Olajuwon", "format": "Top 10 Blocks", "tier": "elite", "title": "Hakeem Olajuwon Top 10 Blocks of Career"},

    # S tier
    {"player": "Nikola Jokic", "format": "Top 10 Assists", "tier": "s", "title": "Nikola Jokic Top 10 Assists of Career"},
    {"player": "Steve Nash", "format": "Top 10 Assists", "tier": "s", "title": "Steve Nash Top 10 Assists of Career"},
    {"player": "Jason Williams", "format": "Top 10 Assists", "tier": "s", "title": "Jason Williams Top 10 Assists of Career"},
    {"player": "Shaquille O'Neal", "format": "Top 10 Dunks", "tier": "s", "title": "Shaquille O'Neal Top 10 Dunks of Career"},
    {"player": "Dominique Wilkins", "format": "Top 10 Dunks", "tier": "s", "title": "Dominique Wilkins Top 10 Dunks of Career"},
    {"player": "David Robinson", "format": "Top 10 Blocks", "tier": "s", "title": "David Robinson Top 10 Blocks of Career"},
    {"player": "Bill Russell", "format": "Top 10 Blocks", "tier": "s", "title": "Bill Russell Top 10 Blocks of Career"},
    {"player": "Tim Duncan", "format": "Top 10 Blocks", "tier": "s", "title": "Tim Duncan Top 10 Blocks of Career"},
    {"player": "Reggie Miller", "format": "Top 10 Clutch Plays", "tier": "s", "title": "Reggie Miller Top 10 Clutch Plays of Career"},
    {"player": "Ray Allen", "format": "Top 10 3-Pointers", "tier": "s", "title": "Ray Allen Top 10 3-Pointers of Career"},
    {"player": "Damian Lillard", "format": "Top 10 Clutch Plays", "tier": "s", "title": "Damian Lillard Top 10 Clutch Plays of Career"},
    {"player": "Chris Paul", "format": "Top 10 Assists", "tier": "s", "title": "Chris Paul Top 10 Assists of Career"},
    {"player": "Blake Griffin", "format": "Top 10 Dunks", "tier": "s", "title": "Blake Griffin Top 10 Dunks of Career"},
    {"player": "Derrick Rose", "format": "Top 10 Dunks", "tier": "s", "title": "Derrick Rose Top 10 Dunks of Career"},
    {"player": "Nate Robinson", "format": "Top 10 Dunks", "tier": "s", "title": "Nate Robinson Top 10 Dunks of Career"},
    {"player": "Ja Morant", "format": "Top 10 Dunks", "tier": "s", "title": "Ja Morant Top 10 Dunks of Career"},
    {"player": "Russell Westbrook", "format": "Top 10 Dunks", "tier": "s", "title": "Russell Westbrook Top 10 Dunks of Career"},
    {"player": "Kobe Bryant", "format": "Top 10 Fadeaways", "tier": "s", "title": "Kobe Bryant Top 10 Fadeaways of Career"},
    {"player": "Michael Jordan", "format": "Top 10 Fadeaways", "tier": "s", "title": "Michael Jordan Top 10 Fadeaways of Career"},
    {"player": "Kyrie Irving", "format": "Top 10 Crossovers", "tier": "s", "title": "Kyrie Irving Top 10 Crossovers of Career"},

    # A tier
    {"player": "George Gervin", "format": "Top 10 Plays", "tier": "a", "title": "George Gervin Top 10 Plays of Career"},
    {"player": "Connie Hawkins", "format": "Top 10 Plays", "tier": "a", "title": "Connie Hawkins Top 10 Plays of Career"},
    {"player": "David Thompson", "format": "Top 10 Dunks", "tier": "a", "title": "David Thompson Top 10 Dunks of Career"},
    {"player": "Earl Monroe", "format": "Top 10 Plays", "tier": "a", "title": "Earl Monroe Top 10 Plays of Career"},
    {"player": "Walt Frazier", "format": "Top 10 Plays", "tier": "a", "title": "Walt Frazier Top 10 Plays of Career"},
    {"player": "Bernard King", "format": "Top 10 Plays", "tier": "a", "title": "Bernard King Top 10 Plays of Career"},
    {"player": "Elvin Hayes", "format": "Top 10 Plays", "tier": "a", "title": "Elvin Hayes Top 10 Plays of Career"},
    {"player": "Bob McAdoo", "format": "Top 10 Plays", "tier": "a", "title": "Bob McAdoo Top 10 Plays of Career"},
    {"player": "Clyde Drexler", "format": "Top 10 Dunks", "tier": "a", "title": "Clyde Drexler Top 10 Dunks of Career"},
    {"player": "Shawn Kemp", "format": "Top 10 Dunks", "tier": "a", "title": "Shawn Kemp Top 10 Dunks of Career"},
    {"player": "Gary Payton", "format": "Top 10 Assists", "tier": "a", "title": "Gary Payton Top 10 Assists of Career"},
    {"player": "John Stockton", "format": "Top 10 Assists", "tier": "a", "title": "John Stockton Top 10 Assists of Career"},
    {"player": "Manu Ginobili", "format": "Top 10 Assists", "tier": "a", "title": "Manu Ginobili Top 10 Assists of Career"},
    {"player": "Pau Gasol", "format": "Top 10 Plays", "tier": "a", "title": "Pau Gasol Top 10 Plays of Career"},
    {"player": "Yao Ming", "format": "Top 10 Blocks", "tier": "a", "title": "Yao Ming Top 10 Blocks of Career"},
    {"player": "Dikembe Mutombo", "format": "Top 10 Blocks", "tier": "a", "title": "Dikembe Mutombo Top 10 Blocks of Career"},
    {"player": "Dwight Howard", "format": "Top 10 Dunks", "tier": "a", "title": "Dwight Howard Top 10 Dunks of Career"},
    {"player": "Tracy McGrady", "format": "Top 10 Dunks", "tier": "a", "title": "Tracy McGrady Top 10 Dunks of Career"},
    {"player": "Kevin Durant", "format": "Top 10 Crossovers", "tier": "a", "title": "Kevin Durant Top 10 Crossovers of Career"},
    {"player": "Carmelo Anthony", "format": "Top 10 Clutch Plays", "tier": "a", "title": "Carmelo Anthony Top 10 Clutch Plays of Career"},

    # Non-player/history topics
]


def custom_tier_defaults(tier):
    tier = normalize(tier)

    if tier == "elite":
        return {"views": 85000, "rpm": 3.85, "score": 98}
    if tier == "s":
        return {"views": 65000, "rpm": 3.35, "score": 90}
    if tier == "a":
        return {"views": 42000, "rpm": 2.75, "score": 78}
    if tier == "fan_request":
        return {"views": 18000, "rpm": 2.10, "score": 62}
    if tier == "topic_s":
        return {"views": 70000, "rpm": 3.25, "score": 88}
    if tier == "topic_a":
        return {"views": 52000, "rpm": 2.95, "score": 80}

    return {"views": 30000, "rpm": 2.50, "score": 70}



def format_multiplier(format_name):
    fmt = normalize(format_name)

    if "clutch" in fmt or "game winner" in fmt:
        return 1.10
    if "dunk" in fmt or "poster" in fmt:
        return 1.06
    if "fadeaway" in fmt or "skyhook" in fmt or "3 pointer" in fmt or "3 pointers" in fmt or "shot" in fmt:
        return 1.04
    if "handle" in fmt or "crossover" in fmt or "crossovers" in fmt:
        return 1.02
    if "assist" in fmt or "pass" in fmt:
        return 0.98
    if "block" in fmt:
        return 0.96

    return 1.00


def ensure_money_fields(item, channel_rpm=0, rank=0):
    """
    Every Strategy Center idea must show views, revenue, and RPM.

    Existing channel players keep real synced player/video revenue first.
    New/custom ideas use projected values weighted by actual channel RPM.
    A tiny cent-level rank adjustment prevents duplicate predicted revenue.
    """
    row = dict(item or {})

    views = safe_int(
        row.get("expected_views")
        or row.get("projected_views")
        or row.get("average_views")
        or row.get("views")
        or 0
    )

    rpm = safe_float(
        row.get("expected_rpm")
        or row.get("projected_rpm")
        or row.get("average_rpm")
        or row.get("synced_rpm")
        or row.get("estimated_rpm")
        or channel_rpm
        or 2.25
    )

    revenue = safe_float(
        row.get("expected_revenue")
        or row.get("projected_revenue")
        or row.get("best_format_total_revenue")
        or row.get("total_revenue")
        or row.get("average_revenue")
        or row.get("synced_revenue")
        or row.get("estimated_revenue")
        or 0
    )

    fmt = row.get("format") or row.get("content_type") or row.get("shuffle_format") or "Top 10 Plays"
    multiplier = format_multiplier(fmt)

    if views <= 0:
        base_score = safe_float(row.get("opportunity_score") or row.get("popularity_score") or 50)
        views = int(max(18000, base_score * 850))

    # If a player has real synced RPM, use it. If not, use channel/default RPM.
    rpm = max(0.01, rpm * multiplier)

    # If revenue is missing or tiny for a projected idea, calculate from views and RPM.
    calculated = (views / 1000) * rpm
    if revenue <= 0 or row.get("source") in ["Custom Idea Bank", "Idea Lab", "Player Database", "Custom/Idea Lab"]:
        revenue = max(revenue, calculated)

    # Unique cent-level adjustment so no two projected revenue values display exactly the same.
    revenue = round(revenue + ((rank + 1) * 0.01), 2)

    row["expected_views"] = views
    row["projected_views"] = views
    row["expected_revenue"] = revenue
    row["projected_revenue"] = revenue
    row["expected_rpm"] = round(rpm, 2)
    row["projected_rpm"] = round(rpm, 2)

    return row


def make_revenues_unique(items, channel_rpm=0):
    fixed = []
    used = set()

    for index, item in enumerate(items or []):
        row = ensure_money_fields(item, channel_rpm=channel_rpm, rank=index)
        revenue = safe_float(row.get("expected_revenue"))

        while round(revenue, 2) in used:
            revenue += 0.01

        revenue = round(revenue, 2)
        used.add(revenue)

        row["expected_revenue"] = revenue
        row["projected_revenue"] = revenue
        fixed.append(row)

    return fixed


def unique_by_player(items, limit=None):
    output = []
    seen = set()

    for item in items or []:
        name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name"))
        if not name or name in seen:
            continue

        seen.add(name)
        output.append(item)

        if limit and len(output) >= limit:
            break

    return output

def build_custom_strategy_ideas(candidates, player_meta):
    """
    User-curated idea bank + generated adjacent formats.
    Ranked with real channel signals when that player already has data.
    """
    candidate_by_player = {
        normalize(item.get("player")): item
        for item in candidates
        if item.get("player")
    }

    expanded = []

    for idea in CUSTOM_STRATEGY_IDEAS:
        if idea.get("format") == "Top 10 Plays" or idea.get("topic"):
            continue

        player = idea.get("player") or idea.get("topic") or idea.get("title")
        topic = idea.get("topic") or player
        title = idea.get("title") or f"{player} {idea.get('format', 'Top 10 Plays')}"
        fmt = idea.get("format") or "Top 10 Plays"
        tier = idea.get("tier") or "custom"
        defaults = custom_tier_defaults(tier)

        existing = candidate_by_player.get(normalize(player), {})
        real_avg_views = safe_int(existing.get("average_views"))
        real_expected_views = safe_int(existing.get("expected_views"))
        real_avg_revenue = safe_float(existing.get("average_revenue"))
        real_expected_revenue = safe_float(existing.get("expected_revenue"))
        real_rpm = safe_float(existing.get("average_rpm") or existing.get("expected_rpm"))

        # Use real synced player money first when this player already exists on the channel.
        # Otherwise use the tier defaults as a projected idea-lab estimate.
        expected_rpm = max(defaults["rpm"], real_rpm)
        expected_views = max(defaults["views"], int(real_avg_views * 1.12), real_expected_views)

        real_total_revenue = safe_float(existing.get("total_revenue"))
        real_blend = (real_avg_revenue * 0.65) + (real_expected_revenue * 0.35)

        expected_revenue = max(
            (expected_views / 1000) * expected_rpm,
            real_blend,
            real_total_revenue * 0.18,
            25
        )

        channel_bonus = 0
        if existing:
            channel_bonus += 10
        if safe_float(existing.get("total_revenue")) >= 100:
            channel_bonus += 8
        if safe_float(existing.get("average_rpm")) >= 2:
            channel_bonus += 6

        opportunity = min(100, defaults["score"] + channel_bonus)

        expanded.append({
            "player": player,
            "player_name": player,
            "topic": topic,
            "title": title,
            "format": fmt,
            "content_type": fmt,
            "era": existing.get("era") or player_meta.get(normalize(player), {}).get("era") or "Custom Idea Bank",
            "expected_views": int(expected_views),
            "projected_views": int(expected_views),
            "expected_revenue": round(expected_revenue, 2),
            "projected_revenue": round(expected_revenue, 2),
            "expected_rpm": round(expected_rpm, 2),
            "projected_rpm": round(expected_rpm, 2),
            "average_views": real_avg_views,
            "average_revenue": round(real_avg_revenue, 2),
            "average_rpm": round(real_rpm, 2),
            "total_revenue": round(safe_float(existing.get("total_revenue")), 2),
            "videos": safe_int(existing.get("videos")),
            "opportunity_score": round(opportunity, 1),
            "tier": tier.upper(),
            "source": "Custom Idea Bank",
            "reason": "Custom idea bank pick ranked with synced channel money trends."
        })

        # Add adjacent smart formats for high-value players so shuffle rarely repeats.
        if idea.get("player") and tier in ["elite", "s", "a"]:
            meta = player_meta.get(normalize(player), {})
            done_types = set(existing.get("done_top10_types") or [])
            tags = player_role_tags(player, meta)
            extra_formats = []

            if "dunks" in tags:
                extra_formats.append("Top 10 Dunks")
            if "assists" in tags:
                extra_formats.append("Top 10 Assists")
            if "blocks" in tags:
                extra_formats.append("Top 10 Blocks")
            if "clutch" in tags:
                extra_formats.append("Top 10 Clutch Plays")
            if "handles" in tags:
                extra_formats.append("Top 10 Crossovers")
            if "shots" in tags:
                extra_formats.append("Top 10 Clutch Shots")

            extra_formats.extend(["Top 10 Plays", "Top 10 Plays"])

            for extra_fmt in extra_formats:
                if normalize(extra_fmt) == normalize(fmt) or extra_fmt in done_types:
                    continue

                # Restrict weird formats to fitting player roles.
                if extra_fmt == "Top 10 Blocks" and "blocks" not in tags:
                    continue
                if extra_fmt == "Top 10 Assists" and "assists" not in tags:
                    continue
                if extra_fmt == "Top 10 Crossovers" and "handles" not in tags:
                    continue

                extra_views = int(expected_views * 0.82)
                extra_rpm = max(2.35, expected_rpm * 0.92)
                extra_revenue = (extra_views / 1000) * extra_rpm

                expanded.append({
                    "player": player,
                    "player_name": player,
                    "topic": player,
                    "title": f"{player} {extra_fmt} of Career",
                    "format": extra_fmt,
                    "content_type": extra_fmt,
                    "era": existing.get("era") or meta.get("era") or "Custom Idea Bank",
                    "expected_views": extra_views,
                    "projected_views": extra_views,
                    "expected_revenue": round(extra_revenue, 2),
                    "projected_revenue": round(extra_revenue, 2),
                    "expected_rpm": round(extra_rpm, 2),
                    "projected_rpm": round(extra_rpm, 2),
                    "average_views": real_avg_views,
                    "average_revenue": round(real_avg_revenue, 2),
                    "average_rpm": round(real_rpm, 2),
                    "total_revenue": round(safe_float(existing.get("total_revenue")), 2),
                    "videos": safe_int(existing.get("videos")),
                    "opportunity_score": round(max(55, opportunity - 8), 1),
                    "tier": f"{tier.upper()} ADJACENT",
                    "source": "Custom Idea Bank",
                    "reason": "Adjacent custom idea generated from player role and channel trends."
                })

    expanded.sort(
        key=lambda x: (
            safe_float(x.get("opportunity_score")),
            safe_float(x.get("expected_revenue")),
            safe_int(x.get("expected_views")),
            safe_float(x.get("expected_rpm"))
        ),
        reverse=True
    )

    return expanded


def build_channel_brain_recommendations(videos):
    """
    Final Strategy Center 2.4.

    Upload Next:
    - exactly the strongest synced revenue options first.

    Shuffle Ideas:
    - huge pool from uploaded players + missing Idea Lab/player-database players.
    - rarely repeats because the frontend shuffles through a much larger list.
    - tracks which Top 10 types are already done.
    - suggests Top 10 Plays first; if already done, suggests smart alternates
      like Top 10 Dunks, Clutch Shots, Blocks, Assists, Handles, etc.
    """
    if not videos:
        return {
            "version": "2.4-final",
            "headline": "No synced videos yet.",
            "today_focus": "Click Sync Channel first.",
            "best_upload_time": "6:00 PM",
            "best_next_upload": None,
            "upload_next": [],
            "shuffle_ideas": [],
            "avoid_next": [],
            "best_formats": [],
            "money_notes": [],
            "action_plan": [],
            "confidence_score": 0,
            "data_health": {
                "synced_videos": 0,
                "synced_revenue_videos": 0,
                "synced_revenue_coverage_percent": 0
            }
        }

    player_meta = {}
    for p in NBA_PLAYERS:
        name = p.get("name", "")
        if name:
            player_meta[normalize(name)] = p

    player_map = defaultdict(lambda: {
        "player": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": [],
        "synced_revenue_videos": 0,
        "top_10_videos": 0,
        "solo_highlight_videos": 0,
        "done_top10_types": set(),
        "subtypes": defaultdict(lambda: {
            "format": "",
            "videos": 0,
            "total_views": 0,
            "total_revenue": 0,
            "rpm_values": []
        })
    })

    format_totals = defaultdict(lambda: {
        "format": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": []
    })

    synced_revenue_videos = 0
    total_synced_revenue = 0
    covered_players = set()

    for video in videos:
        title = video.get("title", "") or ""
        player = video.get("player_name") or detect_player(title) or "Unknown"
        if player == "Unknown":
            continue

        covered_players.add(normalize(player))

        content_type = detect_content_type(title or video.get("content_type", ""))
        top10_type = detect_top10_type_from_title(title)
        content_subtype = top10_type or (detect_content_subtype(title or video.get("content_type", "")) if "detect_content_subtype" in globals() else content_type)
        views = safe_int(video.get("views"))

        try:
            money = get_best_revenue_for_video(video) or {}
        except Exception:
            money = {}

        revenue = safe_float(
            money.get("total_revenue")
            or money.get("synced_revenue")
            or money.get("estimated_revenue")
            or money.get("amount")
            or video.get("synced_revenue")
            or video.get("yt_estimated_revenue")
            or video.get("estimated_revenue")
            or video.get("manual_revenue")
        )

        rpm = safe_float(
            money.get("average_rpm")
            or money.get("synced_rpm")
            or money.get("rpm")
            or money.get("estimated_rpm")
            or video.get("synced_rpm")
            or video.get("yt_estimated_rpm")
            or video.get("estimated_rpm")
            or video.get("manual_rpm")
        )

        if rpm <= 0 and revenue > 0 and views > 0:
            rpm = (revenue / views) * 1000

        if revenue > 0 or rpm > 0:
            synced_revenue_videos += 1
            total_synced_revenue += revenue

        row = player_map[player]
        row["player"] = player
        row["videos"] += 1
        row["total_views"] += views
        row["total_revenue"] += revenue

        if top10_type:
            row["done_top10_types"].add(top10_type)

        if rpm > 0:
            row["rpm_values"].append(rpm)

        if revenue > 0 or rpm > 0:
            row["synced_revenue_videos"] += 1

        if content_type == "Top 10":
            row["top_10_videos"] += 1
        else:
            row["solo_highlight_videos"] += 1

        subtype_row = row["subtypes"][content_subtype]
        subtype_row["format"] = content_subtype
        subtype_row["videos"] += 1
        subtype_row["total_views"] += views
        subtype_row["total_revenue"] += revenue
        if rpm > 0:
            subtype_row["rpm_values"].append(rpm)

        format_totals[content_subtype]["format"] = content_subtype
        format_totals[content_subtype]["videos"] += 1
        format_totals[content_subtype]["total_views"] += views
        format_totals[content_subtype]["total_revenue"] += revenue
        if rpm > 0:
            format_totals[content_subtype]["rpm_values"].append(rpm)

    player_rows = []

    for player, row in player_map.items():
        videos_count = max(1, safe_int(row["videos"]))
        revenue_video_count = max(1, safe_int(row["synced_revenue_videos"]))
        avg_views = safe_div(row["total_views"], videos_count)
        avg_revenue = safe_div(row["total_revenue"], revenue_video_count)
        avg_rpm = round(sum(row["rpm_values"]) / len(row["rpm_values"]), 2) if row["rpm_values"] else 0
        meta = player_meta.get(normalize(player), {})

        subtype_options = []
        for subtype, item in row["subtypes"].items():
            subtype_videos = max(1, safe_int(item["videos"]))
            subtype_avg_views = safe_div(item["total_views"], subtype_videos)
            subtype_avg_revenue = safe_div(item["total_revenue"], subtype_videos)
            subtype_avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0

            subtype_options.append({
                "format": subtype,
                "videos": item["videos"],
                "average_views": subtype_avg_views,
                "average_revenue": subtype_avg_revenue,
                "average_rpm": subtype_avg_rpm,
                "total_views": item["total_views"],
                "total_revenue": round(item["total_revenue"], 2),
                "score": (item["total_revenue"] * 3) + (subtype_avg_revenue * 2) + (subtype_avg_rpm * 10) + (subtype_avg_views / 1000)
            })

        subtype_options.sort(key=lambda x: x["score"], reverse=True)
        best_subtype = subtype_options[0] if subtype_options else {
            "format": "Top 10 Plays",
            "average_views": avg_views,
            "average_revenue": avg_revenue,
            "average_rpm": avg_rpm,
            "total_revenue": row["total_revenue"]
        }

        next_type = next_top10_type_for_player(player, row["done_top10_types"], meta)

        player_rows.append({
            "player": player,
            "videos": row["videos"],
            "top_10_videos": row["top_10_videos"],
            "solo_highlight_videos": row["solo_highlight_videos"],
            "done_top10_types": sorted(list(row["done_top10_types"])),
            "next_top10_type": next_type,
            "total_views": row["total_views"],
            "total_revenue": round(row["total_revenue"], 2),
            "synced_revenue": round(row["total_revenue"], 2),
            "synced_revenue_videos": row["synced_revenue_videos"],
            "average_views": int(avg_views),
            "average_revenue": round(avg_revenue, 2),
            "average_rpm": round(avg_rpm, 2),
            "best_format": best_subtype["format"],
            "best_format_average_views": int(best_subtype.get("average_views", 0)),
            "best_format_average_revenue": round(best_subtype.get("average_revenue", 0), 2),
            "best_format_average_rpm": round(best_subtype.get("average_rpm", 0), 2),
            "best_format_total_revenue": round(best_subtype.get("total_revenue", 0), 2),
            "popularity_score": safe_float(meta.get("popularity_score") or meta.get("youtube_score") or 50),
            "format_breakdown": subtype_options
        })

    candidates = []

    for row in player_rows:
        player = row.get("player")
        meta = player_meta.get(normalize(player), {})

        # Upload Next should stay pure revenue order.
        upload_format = row.get("best_format") or "Top 10 Plays"
        shuffle_format = row.get("next_top10_type") or "Top 10 Plays"

        expected_views = safe_int(row.get("best_format_average_views")) or safe_int(row.get("average_views"))
        expected_revenue = max(
            safe_float(row.get("best_format_total_revenue")),
            safe_float(row.get("average_revenue")),
            safe_float(row.get("total_revenue")) * 0.18
        )
        expected_rpm = safe_float(row.get("best_format_average_rpm")) or safe_float(row.get("average_rpm"))
        total_revenue = safe_float(row.get("total_revenue"))
        avg_revenue = safe_float(row.get("average_revenue"))
        avg_rpm = safe_float(row.get("average_rpm"))
        total_views = safe_int(row.get("total_views"))

        is_weak_money_signal = (
            total_revenue < 10
            and expected_revenue < 10
            and avg_revenue < 10
        )

        candidates.append({
            "player": player,
            "player_name": player,
            "topic": player,
            "format": upload_format,
            "shuffle_format": shuffle_format,
            "content_type": upload_format,
            "era": meta.get("era") or "Unknown",
            "expected_views": expected_views,
            "projected_views": expected_views,
            "expected_revenue": round(expected_revenue, 2),
            "projected_revenue": round(expected_revenue, 2),
            "expected_rpm": round(expected_rpm, 2),
            "projected_rpm": round(expected_rpm, 2),
            "average_views": safe_int(row.get("average_views")),
            "average_revenue": round(avg_revenue, 2),
            "average_rpm": round(avg_rpm, 2),
            "total_revenue": round(total_revenue, 2),
            "videos": safe_int(row.get("videos")),
            "top_10_videos": safe_int(row.get("top_10_videos")),
            "done_top10_types": row.get("done_top10_types", []),
            "total_views": total_views,
            "synced_revenue_videos": row.get("synced_revenue_videos", 0),
            "is_weak_money_signal": is_weak_money_signal,
            "opportunity_score": round(
                min(100, (expected_revenue * 0.08) + (total_revenue * 0.04) + (expected_views / 10000) + (avg_rpm * 6)),
                1
            ),
            "reason": f"{upload_format} has the highest synced revenue signal for this player."
        })

    # Huge shuffle pool.
    shuffle_ideas = []

    # 1) Current channel players: use their NEXT smart Top 10 type, not necessarily their highest-revenue type.
    channel_rpm = safe_float(get_best_channel_rpm() or 0)

    for c in sorted(
        candidates,
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("expected_revenue")),
            safe_float(x.get("average_rpm")),
            safe_int(x.get("total_views"))
        ),
        reverse=True
    ):
        fmt = c.get("shuffle_format") or "Top 10 Plays"
        projected_views = max(safe_int(c.get("average_views")), safe_int(c.get("expected_views")), 25000)

        player_rpm = safe_float(c.get("average_rpm") or c.get("expected_rpm") or channel_rpm or 2.25)
        projected_rpm = max(0.01, player_rpm * format_multiplier(fmt))

        # Real synced player data first. Then calculate projected money from real RPM.
        projected_revenue = max(
            safe_float(c.get("total_revenue")) * 0.18,
            safe_float(c.get("average_revenue")),
            (projected_views / 1000) * projected_rpm,
            25
        )

        shuffle_ideas.append(ensure_money_fields({
            **c,
            "format": fmt,
            "content_type": fmt,
            "expected_views": projected_views,
            "projected_views": projected_views,
            "expected_revenue": projected_revenue,
            "projected_revenue": projected_revenue,
            "expected_rpm": projected_rpm,
            "projected_rpm": projected_rpm,
            "reason": f"Suggested next format: {fmt}."
        }, channel_rpm=channel_rpm, rank=len(shuffle_ideas)))

    # 2) Missing players from Idea Lab / database.
    missing_ideas = []
    for player in NBA_PLAYERS:
        name = player.get("name", "")
        key = normalize(name)
        if not name or key in covered_players:
            continue

        popularity = safe_float(
            player.get("popularity_score")
            or player.get("youtube_score")
            or player.get("priority_score")
            or 0
        )
        all_star = safe_int(player.get("all_star") or player.get("all_stars"))
        mvp = safe_int(player.get("mvp") or player.get("mvps"))
        hof = bool(player.get("hall_of_fame") or player.get("hof"))
        priority_text = normalize(player.get("priority", ""))

        idea_score = popularity + (all_star * 2) + (mvp * 8) + (15 if hof else 0)
        if priority_text in ["elite", "high"]:
            idea_score += 12

        if idea_score >= 25:
            fmt = next_top10_type_for_player(name, set(), player)
            expected_views = int(max(15000, idea_score * 850))
            expected_rpm = max(2.25, channel_rpm or 0, custom_tier_defaults(priority_text).get("rpm", 2.25))
            expected_revenue = (expected_views / 1000) * expected_rpm

            missing_ideas.append(ensure_money_fields({
                "player": name,
                "player_name": name,
                "topic": name,
                "format": fmt,
                "content_type": fmt,
                "era": player.get("era") or "Unknown",
                "expected_views": expected_views,
                "projected_views": expected_views,
                "expected_revenue": expected_revenue,
                "projected_revenue": expected_revenue,
                "expected_rpm": expected_rpm,
                "projected_rpm": expected_rpm,
                "average_views": 0,
                "average_revenue": 0,
                "average_rpm": 0,
                "total_revenue": 0,
                "videos": 0,
                "total_views": 0,
                "opportunity_score": round(min(100, idea_score), 1),
                "source": "Player Database",
                "reason": "High-rated missing player from Idea Lab/player database."
            }, channel_rpm=channel_rpm, rank=len(missing_ideas)))

    missing_ideas = sorted(
        missing_ideas,
        key=lambda x: (
            safe_float(x.get("expected_revenue")),
            safe_float(x.get("opportunity_score")),
            safe_int(x.get("expected_views"))
        ),
        reverse=True
    )[:250]

    custom_ideas = build_custom_strategy_ideas(candidates, player_meta)[:350]
    custom_ideas = make_revenues_unique(custom_ideas, channel_rpm=channel_rpm)

    # Merge unique by player + format so a player can appear again with a different Top 10 type.
    # Order matters: real channel winners first, then custom idea bank, then missing database players.
    seen = set()
    merged_shuffle = []
    for item in shuffle_ideas + custom_ideas + missing_ideas:
        item = ensure_money_fields(item, channel_rpm=channel_rpm, rank=len(merged_shuffle))
        key = f"{normalize(item.get('player') or item.get('player_name') or item.get('topic'))}|{normalize(item.get('format') or item.get('content_type'))}"
        if not key or key in seen:
            continue
        seen.add(key)
        merged_shuffle.append(item)

    shuffle_ideas = make_revenues_unique(merged_shuffle[:700], channel_rpm=channel_rpm)

    # Upload Next = 15 different names, money-safe.
    # It uses real synced channel revenue first, then fills from high-money projected/custom ideas.
    strong_real_uploads = []

    for c in candidates:
        total_revenue = safe_float(c.get("total_revenue"))
        expected_revenue = safe_float(c.get("expected_revenue"))
        avg_revenue = safe_float(c.get("average_revenue"))
        avg_rpm = safe_float(c.get("average_rpm") or c.get("expected_rpm"))

        # Hard filter: keep low-money players out of Upload Next.
        # They can still appear in Avoid Next or Shuffle if they are a custom high-upside idea.
        if c.get("is_weak_money_signal"):
            continue
        if total_revenue < 50 and expected_revenue < 75 and avg_revenue < 25:
            continue
        if avg_rpm > 0 and avg_rpm < 0.75 and total_revenue < 150:
            continue

        strong_real_uploads.append(ensure_money_fields(c, channel_rpm=channel_rpm, rank=len(strong_real_uploads)))

    strong_real_uploads = sorted(
        strong_real_uploads,
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("expected_revenue")),
            safe_float(x.get("average_rpm")),
            safe_int(x.get("total_views"))
        ),
        reverse=True
    )

    high_projected_fillers = sorted(
        [
            item for item in shuffle_ideas
            if safe_float(item.get("expected_revenue") or item.get("projected_revenue")) >= 80
            and safe_float(item.get("expected_rpm") or item.get("projected_rpm")) >= 1.5
        ],
        key=lambda x: (
            safe_float(x.get("expected_revenue") or x.get("projected_revenue")),
            safe_float(x.get("opportunity_score")),
            safe_int(x.get("expected_views") or x.get("projected_views"))
        ),
        reverse=True
    )

    upload_next = unique_by_player(strong_real_uploads + high_projected_fillers, limit=15)
    upload_next = make_revenues_unique(upload_next[:15], channel_rpm=channel_rpm)

    # Avoid Next stays low real synced money only.
    avoid_candidates = []
    for c in candidates:
        if c.get("is_weak_money_signal") or safe_float(c.get("total_revenue")) < 10 or safe_float(c.get("expected_revenue")) < 10:
            avoid_candidates.append({
                "player": c["player"],
                "reason": "Weak synced money signal compared with better options",
                "average_revenue": c.get("average_revenue", 0),
                "average_views": c.get("average_views", 0),
                "average_rpm": c.get("average_rpm", 0),
                "total_revenue": c.get("total_revenue", 0),
                "videos": c.get("videos", 0)
            })

    avoid_next = sorted(
        unique_by_player(avoid_candidates),
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("average_revenue")),
            safe_int(x.get("average_views"))
        )
    )[:30]

    format_rows = []
    for fmt, item in format_totals.items():
        videos_count = max(1, safe_int(item["videos"]))
        avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0
        format_rows.append({
            "type": fmt,
            "format": fmt,
            "videos": item["videos"],
            "total_views": item["total_views"],
            "total_revenue": round(item["total_revenue"], 2),
            "average_views": safe_div(item["total_views"], videos_count),
            "average_revenue": safe_div(item["total_revenue"], videos_count),
            "average_rpm": avg_rpm,
            "synced_revenue_videos": len(item["rpm_values"])
        })

    best_formats = sorted(
        format_rows,
        key=lambda x: (safe_float(x.get("average_revenue")), safe_float(x.get("average_rpm")), safe_int(x.get("total_views"))),
        reverse=True
    )

    best_next_upload = upload_next[0] if upload_next else (shuffle_ideas[0] if shuffle_ideas else None)
    coverage_percent = round((synced_revenue_videos / len(videos)) * 100, 1) if videos else 0

    if coverage_percent >= 80:
        confidence_score = 90
    elif coverage_percent >= 50:
        confidence_score = 75
    elif coverage_percent >= 25:
        confidence_score = 55
    elif coverage_percent > 0:
        confidence_score = 35
    else:
        confidence_score = 10

    if best_next_upload:
        headline = f"Best next upload: {best_next_upload['player']} in {best_next_upload['format']} format."
        today_focus = f"Plan a {best_next_upload['player']} {best_next_upload['format']} upload next."
        action_plan = [
            f"Plan a {best_next_upload['player']} {best_next_upload['format']} video next.",
            "Use Upload Next for highest synced revenue options.",
            "Use Shuffle Idea for a wide pool of smart alternate ideas from both channel history and Idea Lab.",
            "If Top 10 Plays is already done, use the suggested alternate type.",
            "Check 7-day revenue/RPM after upload and let the rankings update automatically."
        ]
    else:
        headline = "Sync more revenue data to generate a money-safe upload recommendation."
        today_focus = "Review Player Rankings and avoid weak-money players."
        action_plan = [
            "Sync channel videos.",
            "Run YouTube revenue sync.",
            "Review Player Rankings.",
            "Pick the strongest high-view and high-RPM player.",
            "Check results again after 7 days."
        ]

    return {
        "version": "2.4-final",
        "headline": headline,
        "today_focus": today_focus,
        "best_upload_time": "6:00 PM",
        "best_next_upload": best_next_upload,
        "confidence_score": confidence_score,
        "data_health": {
            "synced_videos": len(videos),
            "synced_revenue_videos": synced_revenue_videos,
            "synced_revenue_coverage_percent": coverage_percent,
            "total_synced_revenue": round(total_synced_revenue, 2),
            "manual_channel_rpm": round(float(get_best_channel_rpm() or 0), 2)
        },
        "upload_next": upload_next[:15],
        "shuffle_ideas": shuffle_ideas,
        "avoid_next": avoid_next,
        "best_formats": best_formats,
        "money_notes": [
            "Upload Next shows 15 different names and filters out low-money players.",
            "Shuffle Ideas includes current channel winners, the custom idea bank, Idea Lab/player database picks, and smart alternate Top 10 types.",
            "All Strategy Center ideas include expected RPM and unique expected revenue values.",
            "Top 10 Plays is suggested first; if already done, the system suggests Dunks, Clutch Shots, Blocks, Assists, Handles, or Shots based on player fit."
        ],
        "action_plan": action_plan
    }


@router.get("/dashboard/stats")
def dashboard_stats():
    data = get_channel_stats_by_handle("nbatopten")
    channel = data["items"][0]
    totals = get_channel_totals()

    try:
        revenue_summary = get_best_revenue_summary() or {}
    except Exception:
        revenue_summary = {}

    revenue_views = safe_int(
        (revenue_summary.get("channel_views_by_period") or {}).get("lifetime")
        or revenue_summary.get("total_channel_views")
        or revenue_summary.get("lifetime_channel_views")
        or 0
    )

    youtube_views = int(channel["statistics"].get("viewCount", 0))

    return {
        "channel_name": channel["snippet"]["title"],
        "subscribers": int(channel["statistics"].get("subscriberCount", 0)),
        "total_views": revenue_views or youtube_views,
        "youtube_total_views": youtube_views,
        "revenue_tracker_total_views": revenue_views,
        "video_count": int(channel["statistics"].get("videoCount", 0)),
        "database_videos": totals["total_videos"],
        "estimated_revenue": totals["estimated_revenue"],
        "synced_revenue": totals["estimated_revenue"],
        "manual_channel_rpm": get_best_channel_rpm()
    }


DASHBOARD_AUTO_SYNC_MAX_AGE_MINUTES = 20


def parse_datetime_safe(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(str(value).replace("Z", ""))
    except Exception:
        return None


def dashboard_video_data_is_fresh(max_age_minutes=DASHBOARD_AUTO_SYNC_MAX_AGE_MINUTES):
    try:
        info = get_latest_video_sync_info()
        video_count = int(info.get("video_count") or 0)
        latest_sync = parse_datetime_safe(info.get("latest_video_sync"))

        if video_count <= 0 or not latest_sync:
            return False

        return datetime.now() - latest_sync <= timedelta(minutes=max_age_minutes)
    except Exception:
        return False


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

    rows_to_save = []

    for video in videos:
        s = lookup.get(video["video_id"], {})
        title = video["title"]

        player_name = detect_player(title)
        content_type = detect_content_type(title)
        views = s.get("views", 0)

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
        except Exception:
            pass

        rows_to_save.append({
            "title": title,
            "video_id": video["video_id"],
            "published": published,
            "views": views,
            "likes": s.get("likes", 0),
            "comments": s.get("comments", 0),
            "thumbnail": s.get("thumbnail", ""),
            "estimated_revenue": 0,
            "estimated_rpm": 0,
            "content_type": content_type,
            "player_name": player_name,
            "title_length": len(title),
            "upload_year": upload_year,
            "ai_score": ai_score
        })

    synced = save_videos_bulk(rows_to_save)

    return {
        "message": "Channel synced successfully",
        "videos_synced": synced,
        "stats_batches": int((len(video_ids) + 49) / 50) if video_ids else 0,
        "stats_items_loaded": len(lookup)
    }

@router.get("/dashboard/saved-videos")
def saved_videos():
    """
    Returns synced videos without crashing if revenue is missing/lagging.

    Your video sync can succeed before YouTube Analytics revenue rows exist for
    every video. This route should still show all saved channel videos.
    """
    raw_videos = get_saved_videos()
    videos = []

    for video in raw_videos:
        try:
            videos.append(attach_synced_money(video))
        except Exception as error:
            fallback = dict(video)
            fallback["synced_revenue"] = 0
            fallback["synced_rpm"] = 0
            fallback["synced_revenue_entries"] = 0
            fallback["synced_revenue_periods"] = {}
            fallback["estimated_revenue"] = 0
            fallback["estimated_rpm"] = 0
            fallback["manual_revenue"] = 0
            fallback["manual_rpm"] = 0
            fallback["manual_revenue_entries"] = 0
            fallback["manual_revenue_periods"] = {}
            fallback["revenue_source"] = "safe_fallback_after_error"
            fallback["safe_error"] = str(error)
            videos.append(fallback)

    return {
        "total_saved": len(videos),
        "count": len(videos),
        "saved_videos": videos
    }


@router.get("/dashboard/player-rankings")
def player_rankings():
    """
    Final player rankings.

    Uses real synced channel videos plus synced YouTube Analytics / Revenue Tracker
    revenue and RPM. Returns compatibility keys so Dashboard, Player Rankings,
    Strategy Center, and older cards all read the same data safely.
    """
    videos = get_saved_videos()

    player_map = defaultdict(lambda: {
        "player": "Unknown",
        "videos": 0,
        "total_views": 0,
        "total_likes": 0,
        "total_comments": 0,
        "total_revenue": 0,
        "rpm_values": [],
        "synced_revenue_videos": 0,
        "top_10_videos": 0,
        "solo_highlight_videos": 0,
        "latest_upload": "",
        "top_video": None
    })

    for video in videos:
        if not has_enough_views_for_trend(video):
            continue

        player = video.get("player_name") or "Unknown"

        if not player or player == "Unknown":
            continue

        row = player_map[player]
        row["player"] = player
        row["videos"] += 1

        views = safe_int(video.get("views"))
        likes = safe_int(video.get("likes"))
        comments = safe_int(video.get("comments"))

        row["total_views"] += views
        row["total_likes"] += likes
        row["total_comments"] += comments

        content_type = detect_content_type(video.get("title", "") or video.get("content_type", ""))
        if content_type == "Top 10":
            row["top_10_videos"] += 1
        else:
            row["solo_highlight_videos"] += 1

        published = video.get("published") or ""
        if published > row["latest_upload"]:
            row["latest_upload"] = published

        if row["top_video"] is None or views > safe_int(row["top_video"].get("views")):
            row["top_video"] = {
                "title": video.get("title", ""),
                "video_id": video.get("video_id", ""),
                "views": views,
                "thumbnail": video.get("thumbnail", "")
            }

        try:
            money = get_best_revenue_for_video(video) or {}
        except Exception:
            money = {}

        revenue = safe_float(
            money.get("total_revenue")
            or money.get("estimated_revenue")
            or money.get("amount")
            or video.get("yt_estimated_revenue")
            or video.get("estimated_revenue")
        )

        rpm = safe_float(
            money.get("average_rpm")
            or money.get("rpm")
            or money.get("estimated_rpm")
            or video.get("yt_estimated_rpm")
            or video.get("estimated_rpm")
        )

        if revenue > 0 or rpm > 0:
            row["synced_revenue_videos"] += 1

        row["total_revenue"] += revenue

        if rpm > 0:
            row["rpm_values"].append(rpm)

    rankings = []

    for row in player_map.values():
        videos_count = safe_int(row.get("videos"))
        total_views = safe_int(row.get("total_views"))
        total_revenue = safe_float(row.get("total_revenue"))
        synced_revenue_videos = max(1, safe_int(row.get("synced_revenue_videos")))

        average_views = safe_div(total_views, videos_count)
        average_revenue = safe_div(total_revenue, synced_revenue_videos)
        average_rpm = round(sum(row["rpm_values"]) / len(row["rpm_values"]), 2) if row["rpm_values"] else 0

        money_score = 0
        money_score += min(45, average_revenue * 0.25)
        money_score += min(30, average_rpm * 6)
        money_score += min(25, average_views / 5000)

        rankings.append({
            **row,
            "average_views": int(average_views),
            "average_revenue": round(average_revenue, 2),
            "average_rpm": round(average_rpm, 2),
            "total_revenue": round(total_revenue, 2),
            "synced_revenue": round(total_revenue, 2),
            "money_score": round(money_score, 2),
            "opportunity_score": round(min(100, money_score), 2),

            # Compatibility keys for older frontend/backend code.
            "manual_revenue_videos": row["synced_revenue_videos"],
            "manual_videos": row["synced_revenue_videos"],
            "manual_revenue": round(total_revenue, 2),
            "manual_rpm": round(average_rpm, 2),
            "total_videos": videos_count
        })

    rankings = sorted(
        rankings,
        key=lambda x: (
            x.get("total_revenue", 0),
            x.get("average_rpm", 0),
            x.get("average_views", 0),
            x.get("total_views", 0)
        ),
        reverse=True
    )

    return {
        "player_rankings": rankings,
        "count": len(rankings)
    }


@router.get("/dashboard/content-analysis")
def content_analysis():
    videos = get_saved_videos()

    types = defaultdict(lambda: {
        "videos": 0,
        "views": 0,
        "revenue": 0,
        "rpm_values": [],
        "synced_revenue_videos": 0
    })

    for video in videos:
        if not has_enough_views_for_trend(video):
            continue

        content_type = detect_content_type(video.get("title", "") or video.get("content_type", ""))
        money = attach_synced_money(video)

        revenue = safe_float(money.get("synced_revenue"))
        rpm = safe_float(money.get("synced_rpm"))
        views = safe_int(video.get("views"))

        types[content_type]["videos"] += 1
        types[content_type]["views"] += views

        if revenue > 0:
            types[content_type]["revenue"] += revenue
            types[content_type]["synced_revenue_videos"] += 1

        if rpm > 0:
            types[content_type]["rpm_values"].append(rpm)

    output = []

    for content_type, data in types.items():
        rpm_values = data["rpm_values"]
        average_rpm = round(sum(rpm_values) / len(rpm_values), 2) if rpm_values else 0
        average_revenue = safe_div(data["revenue"], data["synced_revenue_videos"])

        output.append({
            "type": content_type,
            "format": content_type,
            "videos": data["videos"],
            "total_views": data["views"],
            "average_views": safe_div(data["views"], data["videos"]),
            "estimated_revenue": round(data["revenue"], 2),
            "synced_revenue": round(data["revenue"], 2),
            "total_revenue": round(data["revenue"], 2),
            "average_revenue": average_revenue,
            "average_rpm": average_rpm,
            "synced_revenue_videos": data["synced_revenue_videos"],
            "manual_revenue_videos": data["synced_revenue_videos"]
        })

    output.sort(
        key=lambda x: (x["average_revenue"], x["average_rpm"], x["total_views"]),
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

    trend_videos = [v for v in videos if has_enough_views_for_trend(v)]
    videos_with_money = [attach_synced_money(v) for v in trend_videos]
    totals = get_channel_totals()

    best_views = max(videos_with_money, key=lambda x: x.get("views", 0)) if videos_with_money else None

    if not videos_with_money:
        return {
            "error": "No videos with at least 500 views found for trend analysis"
        }

    synced_money_videos = [
        v for v in videos_with_money
        if v.get("synced_revenue", 0) > 0
    ]

    best_money = (
        max(synced_money_videos, key=lambda x: x.get("synced_revenue", 0))
        if synced_money_videos
        else None
    )

    top_money_videos = sorted(
        synced_money_videos,
        key=lambda x: x.get("synced_revenue", 0),
        reverse=True
    )[:10]

    low_money_high_views = [
        v for v in videos_with_money
        if v.get("views", 0) >= 10000
        and v.get("synced_revenue_entries", 0) > 0
        and v.get("synced_revenue", 0) < 25
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
            "estimated_revenue": totals["estimated_revenue"],
            "synced_revenue": totals["estimated_revenue"],
            "manual_channel_rpm": get_best_channel_rpm()
        },
        "money_strategy": {
            "main_takeaway": "Revenue now uses only synced Revenue Tracker entries.",
            "best_pattern": "Enter real video revenue to identify the true best money patterns.",
            "avoid_pattern": "Videos with high views but low synced revenue should be watched for revenue leaks.",
            "recommended_next_focus": [
                "Enter lifetime/365d/90d/30d/7d revenue for top videos",
                "Enter views and RPM for each revenue period",
                "Use synced revenue rankings before choosing new uploads",
                "Prioritize topics with proven manual RPM"
            ]
        },
        "best_video_by_views": (
            {
                "title": best_views["title"],
                "views": best_views["views"],
                "revenue": best_views["synced_revenue"],
                "player": best_views["player_name"]
            }
            if best_views
            else None
        ),
        "best_video_by_money": (
            {
                "title": best_money["title"],
                "views": best_money["views"],
                "revenue": best_money["synced_revenue"],
                "player": best_money["player_name"]
            }
            if best_money
            else None
        ),
        "top_money_videos": top_money_videos,
        "low_money_high_views": low_money_high_views,
        "best_players_by_money": player_data[:10],
        "best_content_types_by_money": content_data[:5],
        "title_analysis": {
            "common_words": top_words
        }
    }





# =========================================================
# FINAL Strategy Center override
# Money-safe final version:
# - Upload Next fills 15 names.
# - Existing channel players use real synced YouTube API revenue/RPM/views.
# - New/custom/Idea Lab fillers use conservative projections based on current channel RPM + real channel view trends.
# - No fake huge custom revenue numbers.
# - No "Top 10 Top 10".
# - No "Handles"; always "Crossovers".
# - No "Top 10 Shots"; use "Top 10 Clutch Shots".
# - No History Countdown ideas.
# =========================================================

def clean_strategy_format(value):
    text = str(value or "").strip()
    if not text:
        return "Top 10 Plays"

    text = text.replace("Top Ten", "Top 10")
    text = text.replace("top ten", "Top 10")
    text = text.replace("Handles", "Crossovers")
    text = text.replace("handles", "Crossovers")
    text = text.replace("Top 10 Shots", "Top 10 Clutch Shots")
    text = text.replace("Top 10 Career Highlights", "Top 10 Plays")
    text = text.replace("Career Highlights", "Top 10 Plays")
    text = text.replace("History Countdown", "Top 10 Plays")

    # Remove repeated Top 10 prefixes.
    while "Top 10 Top 10" in text:
        text = text.replace("Top 10 Top 10", "Top 10")

    # Normalize common variants.
    low = normalize(text)
    if "crossover" in low or "handle" in low or "dribble" in low:
        return "Top 10 Crossovers"
    if "clutch" in low or "game winner" in low or "buzzer" in low or "shot" in low:
        return "Top 10 Clutch Shots"
    if "3 pointer" in low or "3 pointers" in low or "three pointer" in low or "three pointers" in low:
        return "Top 10 3-Pointers"
    if "fadeaway" in low:
        return "Top 10 Fadeaways"
    if "skyhook" in low:
        return "Top 10 Skyhooks"
    if "dunk" in low:
        return "Top 10 Dunks"
    if "assist" in low or "pass" in low:
        return "Top 10 Assists"
    if "block" in low:
        return "Top 10 Blocks"
    if "play" in low:
        return "Top 10 Plays"

    if low.startswith("top 10"):
        return "Top 10 Plays"

    return text


def clean_strategy_title(player, fmt):
    player = str(player or "").strip()
    fmt = clean_strategy_format(fmt)

    # For player ideas, keep one clean title format.
    if not player:
        return fmt

    return f"{player} {fmt} of Career"


def clean_strategy_row(row):
    fixed = dict(row or {})
    player = fixed.get("player") or fixed.get("player_name") or fixed.get("topic") or fixed.get("name") or ""
    fmt = clean_strategy_format(fixed.get("format") or fixed.get("content_type") or fixed.get("shuffle_format") or "Top 10 Plays")

    fixed["player"] = player
    fixed["player_name"] = player
    fixed["topic"] = player
    fixed["format"] = fmt
    fixed["content_type"] = fmt
    fixed["shuffle_format"] = clean_strategy_format(fixed.get("shuffle_format") or fmt)
    fixed["title"] = clean_strategy_title(player, fmt)

    return fixed


def real_video_money(video):
    try:
        money = get_best_revenue_for_video(video) or {}
    except Exception:
        money = {}

    views = safe_int(video.get("views"))

    revenue = safe_float(
        money.get("total_revenue")
        or money.get("synced_revenue")
        or money.get("estimated_revenue")
        or money.get("amount")
        or video.get("synced_revenue")
        or video.get("yt_estimated_revenue")
        or video.get("estimated_revenue")
        or video.get("manual_revenue")
    )

    rpm = safe_float(
        money.get("average_rpm")
        or money.get("synced_rpm")
        or money.get("rpm")
        or money.get("estimated_rpm")
        or video.get("synced_rpm")
        or video.get("yt_estimated_rpm")
        or video.get("estimated_rpm")
        or video.get("manual_rpm")
    )

    if rpm <= 0 and revenue > 0 and views > 0:
        rpm = (revenue / views) * 1000

    return revenue, rpm, views


def actual_player_rows_from_videos(videos):
    player_map = defaultdict(lambda: {
        "player": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": [],
        "synced_revenue_videos": 0,
        "done_top10_types": set(),
        "format_totals": defaultdict(lambda: {
            "format": "",
            "videos": 0,
            "total_views": 0,
            "total_revenue": 0,
            "rpm_values": []
        })
    })

    for video in videos:
        if not has_enough_views_for_trend(video):
            continue

        title = video.get("title", "") or ""
        player = video.get("player_name") or detect_player(title) or "Unknown"
        if not player or player == "Unknown":
            continue

        revenue, rpm, views = real_video_money(video)
        top10_type = clean_strategy_format(detect_top10_type_from_title(title) or detect_content_subtype(title) or "Top 10 Plays")

        row = player_map[player]
        row["player"] = player
        row["videos"] += 1
        row["total_views"] += views
        row["total_revenue"] += revenue

        if top10_type:
            row["done_top10_types"].add(top10_type)

        if revenue > 0 or rpm > 0:
            row["synced_revenue_videos"] += 1

        if rpm > 0:
            row["rpm_values"].append(rpm)

        fmt_row = row["format_totals"][top10_type]
        fmt_row["format"] = top10_type
        fmt_row["videos"] += 1
        fmt_row["total_views"] += views
        fmt_row["total_revenue"] += revenue
        if rpm > 0:
            fmt_row["rpm_values"].append(rpm)

    rows = []
    for player, row in player_map.items():
        videos_count = max(1, safe_int(row["videos"]))
        revenue_count = max(1, safe_int(row["synced_revenue_videos"]))
        avg_views = safe_div(row["total_views"], videos_count)
        avg_revenue = safe_div(row["total_revenue"], revenue_count)
        avg_rpm = round(sum(row["rpm_values"]) / len(row["rpm_values"]), 2) if row["rpm_values"] else 0
        if avg_rpm <= 0 and row["total_revenue"] > 0 and row["total_views"] > 0:
            avg_rpm = round((row["total_revenue"] / row["total_views"]) * 1000, 2)

        format_options = []
        for _, fmt_row in row["format_totals"].items():
            fmt_videos = max(1, safe_int(fmt_row["videos"]))
            fmt_rpm = round(sum(fmt_row["rpm_values"]) / len(fmt_row["rpm_values"]), 2) if fmt_row["rpm_values"] else 0
            if fmt_rpm <= 0 and fmt_row["total_revenue"] > 0 and fmt_row["total_views"] > 0:
                fmt_rpm = round((fmt_row["total_revenue"] / fmt_row["total_views"]) * 1000, 2)

            format_options.append({
                "format": clean_strategy_format(fmt_row["format"]),
                "videos": fmt_row["videos"],
                "total_views": fmt_row["total_views"],
                "total_revenue": round(fmt_row["total_revenue"], 2),
                "average_views": safe_div(fmt_row["total_views"], fmt_videos),
                "average_revenue": safe_div(fmt_row["total_revenue"], fmt_videos),
                "average_rpm": fmt_rpm
            })

        format_options.sort(
            key=lambda x: (
                safe_float(x.get("total_revenue")),
                safe_float(x.get("average_revenue")),
                safe_float(x.get("average_rpm")),
                safe_int(x.get("total_views"))
            ),
            reverse=True
        )

        best_format = format_options[0] if format_options else {
            "format": "Top 10 Plays",
            "total_revenue": row["total_revenue"],
            "average_views": avg_views,
            "average_revenue": avg_revenue,
            "average_rpm": avg_rpm
        }

        meta = {}
        for p in NBA_PLAYERS:
            if normalize(p.get("name", "")) == normalize(player):
                meta = p
                break

        next_type = clean_strategy_format(next_top10_type_for_player(player, row["done_top10_types"], meta))

        rows.append({
            "player": player,
            "player_name": player,
            "topic": player,
            "videos": row["videos"],
            "total_views": row["total_views"],
            "total_revenue": round(row["total_revenue"], 2),
            "synced_revenue": round(row["total_revenue"], 2),
            "synced_revenue_videos": row["synced_revenue_videos"],
            "average_views": int(avg_views),
            "average_revenue": round(avg_revenue, 2),
            "average_rpm": round(avg_rpm, 2),
            "done_top10_types": sorted(list(row["done_top10_types"])),
            "next_top10_type": next_type,
            "best_format": clean_strategy_format(best_format.get("format")),
            "best_format_total_revenue": round(safe_float(best_format.get("total_revenue")), 2),
            "best_format_average_views": int(safe_float(best_format.get("average_views"))),
            "best_format_average_revenue": round(safe_float(best_format.get("average_revenue")), 2),
            "best_format_average_rpm": round(safe_float(best_format.get("average_rpm")), 2),
            "format_breakdown": format_options
        })

    return rows


def make_display_revenue_unique(rows, revenue_key="expected_revenue"):
    used = set()
    output = []

    for index, item in enumerate(rows or []):
        row = dict(item)
        revenue = round(safe_float(row.get(revenue_key)), 2)

        while revenue in used:
            revenue = round(revenue + 0.01, 2)

        used.add(revenue)
        row[revenue_key] = revenue
        row["projected_revenue"] = revenue
        output.append(row)

    return output


def conservative_projected_views(real_rows):
    values = [
        safe_int(r.get("average_views"))
        for r in real_rows
        if safe_int(r.get("average_views")) > 0
    ]
    if not values:
        return 25000

    values.sort()
    middle = values[len(values) // 2]
    return int(max(15000, min(65000, middle)))


def build_custom_fillers(real_rows, used_players, channel_rpm):
    """
    Fills Upload Next to 15 only when real synced-revenue players are fewer than 15.
    These are conservative projections, not fake huge revenue totals.
    """
    fillers = []
    base_views = conservative_projected_views(real_rows)
    rpm_values = [safe_float(r.get("average_rpm")) for r in real_rows if safe_float(r.get("average_rpm")) > 0]
    base_rpm = channel_rpm or (sum(rpm_values) / len(rpm_values) if rpm_values else 1.0)
    base_rpm = max(0.25, min(3.25, base_rpm))

    for idea in CUSTOM_STRATEGY_IDEAS:
        if idea.get("topic"):
            continue

        player = idea.get("player") or ""
        if not player:
            continue

        key = normalize(player)
        if key in used_players:
            continue

        fmt = clean_strategy_format(idea.get("format") or "Top 10 Plays")
        title = clean_strategy_title(player, fmt)

        # Conservative projected values based on current channel data, not inflated custom tier defaults.
        tier = normalize(idea.get("tier") or "")
        tier_views_multiplier = {
            "elite": 1.15,
            "s": 1.05,
            "a": 0.95,
            "fan request": 0.75,
            "fan_request": 0.75
        }.get(tier, 0.90)

        fmt_mult = format_multiplier(fmt)
        expected_views = int(base_views * tier_views_multiplier)
        expected_rpm = round(max(0.25, base_rpm * fmt_mult), 2)
        expected_revenue = round((expected_views / 1000) * expected_rpm, 2)

        fillers.append({
            "player": player,
            "player_name": player,
            "topic": player,
            "title": title,
            "format": fmt,
            "content_type": fmt,
            "expected_views": expected_views,
            "projected_views": expected_views,
            "expected_revenue": expected_revenue,
            "projected_revenue": expected_revenue,
            "expected_rpm": expected_rpm,
            "projected_rpm": expected_rpm,
            "average_views": 0,
            "average_revenue": 0,
            "average_rpm": 0,
            "total_revenue": 0,
            "videos": 0,
            "synced_revenue_videos": 0,
            "source": "Custom Idea Bank Projection",
            "reason": "Projected from current channel RPM and view trends because this player does not have synced revenue yet."
        })

    fillers.sort(
        key=lambda x: (
            safe_float(x.get("expected_revenue")),
            safe_int(x.get("expected_views")),
            safe_float(x.get("expected_rpm"))
        ),
        reverse=True
    )

    return fillers


def build_shuffle_pool(real_rows, upload_next, channel_rpm):
    pool = []
    seen = set()

    # Real channel players first, with next valid alternate format.
    for row in sorted(
        real_rows,
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("average_revenue")),
            safe_float(x.get("average_rpm")),
            safe_int(x.get("total_views"))
        ),
        reverse=True
    ):
        player = row.get("player")
        fmt = clean_strategy_format(row.get("next_top10_type") or row.get("best_format") or "Top 10 Plays")
        key = f"{normalize(player)}|{normalize(fmt)}"
        if key in seen:
            continue
        seen.add(key)

        expected_views = safe_int(row.get("average_views")) or conservative_projected_views(real_rows)
        expected_rpm = safe_float(row.get("average_rpm")) or channel_rpm or 1.0
        expected_revenue = round((expected_views / 1000) * expected_rpm, 2)

        pool.append({
            **row,
            "title": clean_strategy_title(player, fmt),
            "format": fmt,
            "content_type": fmt,
            "expected_views": expected_views,
            "projected_views": expected_views,
            "expected_revenue": expected_revenue,
            "projected_revenue": expected_revenue,
            "expected_rpm": round(expected_rpm, 2),
            "projected_rpm": round(expected_rpm, 2),
            "reason": f"Suggested next format: {fmt}."
        })

    used_players = {normalize(x.get("player")) for x in pool}
    custom_fillers = build_custom_fillers(real_rows, used_players, channel_rpm)

    for item in custom_fillers:
        key = f"{normalize(item.get('player'))}|{normalize(item.get('format'))}"
        if key in seen:
            continue
        seen.add(key)
        pool.append(item)

    # Add missing Idea Lab/database players conservatively.
    base_views = conservative_projected_views(real_rows)
    base_rpm = channel_rpm or 1.0
    for player in NBA_PLAYERS:
        name = player.get("name", "")
        if not name:
            continue

        fmt = clean_strategy_format(next_top10_type_for_player(name, set(), player))
        key = f"{normalize(name)}|{normalize(fmt)}"
        if key in seen:
            continue

        popularity = safe_float(
            player.get("popularity_score")
            or player.get("youtube_score")
            or player.get("priority_score")
            or 0
        )
        if popularity < 25:
            continue

        seen.add(key)
        expected_views = int(min(65000, max(15000, base_views * (0.75 + min(popularity, 100) / 250))))
        expected_rpm = round(max(0.25, base_rpm * format_multiplier(fmt)), 2)
        expected_revenue = round((expected_views / 1000) * expected_rpm, 2)

        pool.append({
            "player": name,
            "player_name": name,
            "topic": name,
            "title": clean_strategy_title(name, fmt),
            "format": fmt,
            "content_type": fmt,
            "expected_views": expected_views,
            "projected_views": expected_views,
            "expected_revenue": expected_revenue,
            "projected_revenue": expected_revenue,
            "expected_rpm": expected_rpm,
            "projected_rpm": expected_rpm,
            "average_views": 0,
            "average_revenue": 0,
            "average_rpm": 0,
            "total_revenue": 0,
            "videos": 0,
            "synced_revenue_videos": 0,
            "source": "Player Database Projection",
            "reason": "Projected from current channel RPM/view trends and player database priority."
        })

    pool.sort(
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("expected_revenue")),
            safe_int(x.get("expected_views")),
            safe_float(x.get("expected_rpm"))
        ),
        reverse=True
    )

    return make_display_revenue_unique(pool[:700])


def build_channel_brain_recommendations(videos):
    if not videos:
        return {
            "version": "3.1-money-safe",
            "headline": "No synced videos yet.",
            "today_focus": "Click Sync Channel first.",
            "best_upload_time": "6:00 PM",
            "best_next_upload": None,
            "upload_next": [],
            "shuffle_ideas": [],
            "avoid_next": [],
            "best_formats": [],
            "money_notes": [],
            "action_plan": [],
            "confidence_score": 0,
            "data_health": {
                "synced_videos": 0,
                "synced_revenue_videos": 0,
                "synced_revenue_coverage_percent": 0
            }
        }

    channel_rpm = safe_float(get_best_channel_rpm() or 0)
    real_rows = actual_player_rows_from_videos(videos)

    synced_revenue_videos = sum(safe_int(r.get("synced_revenue_videos")) for r in real_rows)
    total_synced_revenue = sum(safe_float(r.get("total_revenue")) for r in real_rows)
    coverage_percent = round((synced_revenue_videos / len(videos)) * 100, 1) if videos else 0

    # Upload Next: real synced money players first.
    real_uploads = []
    for row in real_rows:
        if safe_float(row.get("total_revenue")) <= 0:
            continue

        fmt = clean_strategy_format(row.get("best_format") or "Top 10 Plays")
        expected_views = safe_int(row.get("best_format_average_views")) or safe_int(row.get("average_views"))
        expected_rpm = safe_float(row.get("best_format_average_rpm")) or safe_float(row.get("average_rpm"))
        expected_revenue = safe_float(row.get("total_revenue"))

        real_uploads.append(clean_strategy_row({
            **row,
            "title": clean_strategy_title(row.get("player"), fmt),
            "format": fmt,
            "content_type": fmt,
            "expected_views": expected_views,
            "projected_views": expected_views,
            "expected_revenue": expected_revenue,
            "projected_revenue": expected_revenue,
            "expected_rpm": round(expected_rpm, 2),
            "projected_rpm": round(expected_rpm, 2),
            "source": "Real YouTube API Revenue",
            "reason": f"Real synced channel revenue: ${expected_revenue:.2f}."
        }))

    real_uploads.sort(
        key=lambda x: (
            safe_float(x.get("expected_revenue")),
            safe_int(x.get("expected_views")),
            safe_float(x.get("expected_rpm"))
        ),
        reverse=True
    )

    seen_players = set()
    upload_next = []
    for item in real_uploads:
        key = normalize(item.get("player"))
        if not key or key in seen_players:
            continue
        seen_players.add(key)
        upload_next.append(item)
        if len(upload_next) >= 15:
            break

    # Fill to 15 conservatively if fewer than 15 real-money players exist.
    if len(upload_next) < 15:
        fillers = build_custom_fillers(real_rows, seen_players, channel_rpm)
        for item in fillers:
            key = normalize(item.get("player"))
            if not key or key in seen_players:
                continue
            seen_players.add(key)
            upload_next.append(clean_strategy_row(item))
            if len(upload_next) >= 15:
                break

    upload_next = make_display_revenue_unique(upload_next[:15])

    shuffle_ideas = build_shuffle_pool(real_rows, upload_next, channel_rpm)

    avoid_candidates = []
    for row in real_rows:
        total_revenue = safe_float(row.get("total_revenue"))
        avg_revenue = safe_float(row.get("average_revenue"))
        avg_rpm = safe_float(row.get("average_rpm"))

        if total_revenue <= 0 or (total_revenue < 10 and avg_revenue < 10) or (avg_rpm > 0 and avg_rpm < 0.75 and total_revenue < 50):
            avoid_candidates.append({
                "player": row.get("player"),
                "reason": "Weak synced money signal compared with better options",
                "average_revenue": round(avg_revenue, 2),
                "average_views": safe_int(row.get("average_views")),
                "average_rpm": round(avg_rpm, 2),
                "total_revenue": round(total_revenue, 2),
                "videos": safe_int(row.get("videos"))
            })

    avoid_next = sorted(
        unique_by_player(avoid_candidates),
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("average_revenue")),
            safe_float(x.get("average_rpm")),
            safe_int(x.get("average_views"))
        )
    )[:30]

    format_map = defaultdict(lambda: {
        "format": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": []
    })

    for row in real_rows:
        for item in row.get("format_breakdown", []):
            fmt = clean_strategy_format(item.get("format"))
            format_map[fmt]["format"] = fmt
            format_map[fmt]["videos"] += safe_int(item.get("videos"))
            format_map[fmt]["total_views"] += safe_int(item.get("total_views"))
            format_map[fmt]["total_revenue"] += safe_float(item.get("total_revenue"))
            if safe_float(item.get("average_rpm")) > 0:
                format_map[fmt]["rpm_values"].append(safe_float(item.get("average_rpm")))

    best_formats = []
    for fmt, item in format_map.items():
        videos_count = max(1, safe_int(item["videos"]))
        avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0

        best_formats.append({
            "type": fmt,
            "format": fmt,
            "videos": item["videos"],
            "total_views": item["total_views"],
            "total_revenue": round(item["total_revenue"], 2),
            "average_views": safe_div(item["total_views"], videos_count),
            "average_revenue": safe_div(item["total_revenue"], videos_count),
            "average_rpm": avg_rpm,
            "synced_revenue_videos": len(item["rpm_values"])
        })

    best_formats.sort(
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("average_revenue")),
            safe_float(x.get("average_rpm")),
            safe_int(x.get("total_views"))
        ),
        reverse=True
    )

    best_next_upload = upload_next[0] if upload_next else (shuffle_ideas[0] if shuffle_ideas else None)

    if coverage_percent >= 80:
        confidence_score = 90
    elif coverage_percent >= 50:
        confidence_score = 75
    elif coverage_percent >= 25:
        confidence_score = 55
    elif coverage_percent > 0:
        confidence_score = 35
    else:
        confidence_score = 10

    if best_next_upload:
        headline = f"Best next upload: {best_next_upload['player']} {best_next_upload['format']}."
        today_focus = f"Plan a {best_next_upload['player']} {best_next_upload['format']} upload next."
        action_plan = [
            f"Plan a {best_next_upload['player']} {best_next_upload['format']} video next.",
            "Use Upload Next for the highest real synced revenue players first.",
            "Use Shuffle Idea for alternate formats and conservative new-player projections.",
            "If Top 10 Plays is already done, use the suggested alternate type.",
            "Check 7-day revenue/RPM after upload and let rankings update automatically."
        ]
    else:
        headline = "Sync more revenue data to generate a money-safe upload recommendation."
        today_focus = "Review Player Rankings and avoid weak-money players."
        action_plan = [
            "Sync channel videos.",
            "Run YouTube revenue sync.",
            "Review Player Rankings.",
            "Pick the strongest high-view and high-RPM player.",
            "Check results again after 7 days."
        ]

    return {
        "version": "3.1-money-safe",
        "headline": headline,
        "today_focus": today_focus,
        "best_upload_time": "6:00 PM",
        "best_next_upload": best_next_upload,
        "confidence_score": confidence_score,
        "data_health": {
            "synced_videos": len(videos),
            "synced_revenue_videos": synced_revenue_videos,
            "synced_revenue_coverage_percent": coverage_percent,
            "total_synced_revenue": round(total_synced_revenue, 2),
            "manual_channel_rpm": round(channel_rpm, 2)
        },
        "upload_next": upload_next[:15],
        "shuffle_ideas": shuffle_ideas,
        "avoid_next": avoid_next,
        "best_formats": best_formats,
        "money_notes": [
            "Upload Next uses real synced YouTube API revenue first.",
            "If fewer than 15 real-money players exist, the remaining slots use conservative projections based on current channel RPM and view trends.",
            "Shuffle Ideas include real channel players, custom idea-bank players, and player database options.",
            "Completed Top 10 formats are skipped when possible."
        ],
        "action_plan": action_plan
    }


@router.get("/dashboard/channel-brain")
def channel_brain():
    videos = get_saved_videos()

    return {
        "channel_brain": build_channel_brain_recommendations(videos)
    }


@router.get("/dashboard/top-videos")
def dashboard_top_videos():
    videos = [attach_synced_money(v) for v in get_top_videos(20)]

    return {
        "top_videos": videos
    }


# =========================================================
# FINAL Strategy Center override 2.6
# Fixes:
# - Upload Next always returns 15 names.
# - First uses real synced YouTube API revenue/RPM/views from your saved channel videos.
# - Fillers use conservative unique projections from current channel averages, not fake huge revenue.
# - Projected views are unique instead of repeating 18,000.
# - Era is filled from player database where possible, then safe era map/fallback.
# - Adds photo_url / wiki_search_url fields for future UI cards.
# - Removes bad formats: Top 10 Top 10, Handles, Top 10 Shots, History Countdown.
# =========================================================

from urllib.parse import quote_plus


PLAYER_ERA_FALLBACKS = {
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
    "Connie Hawkins": "1960s/1970s",
    "David Thompson": "1970s/1980s",
    "Earl Monroe": "1970s",
    "Walt Frazier": "1970s",
    "Bernard King": "1980s",
    "Elvin Hayes": "1970s/1980s",
    "Bob McAdoo": "1970s/1980s",
    "Larry Bird": "1980s/1990s",
    "Magic Johnson": "1980s/1990s",
    "Michael Jordan": "1980s/1990s",
    "Hakeem Olajuwon": "1980s/1990s",
    "Dominique Wilkins": "1980s/1990s",
    "Clyde Drexler": "1980s/1990s",
    "Karl Malone": "1980s/1990s",
    "John Stockton": "1980s/1990s",
    "Shaquille O'Neal": "1990s/2000s",
    "David Robinson": "1990s",
    "Reggie Miller": "1990s/2000s",
    "Gary Payton": "1990s/2000s",
    "Shawn Kemp": "1990s",
    "Kobe Bryant": "2000s/2010s",
    "Allen Iverson": "2000s",
    "Vince Carter": "2000s/2010s",
    "Kevin Garnett": "2000s/2010s",
    "Tim Duncan": "2000s/2010s",
    "Dirk Nowitzki": "2000s/2010s",
    "Steve Nash": "2000s",
    "Jason Kidd": "2000s",
    "Tracy McGrady": "2000s",
    "Paul Pierce": "2000s",
    "Ray Allen": "2000s/2010s",
    "Manu Ginobili": "2000s/2010s",
    "Pau Gasol": "2000s/2010s",
    "Yao Ming": "2000s",
    "Dikembe Mutombo": "1990s/2000s",
    "Dwight Howard": "2000s/2010s",
    "LeBron James": "2000s/2010s/2020s",
    "Stephen Curry": "2010s/2020s",
    "Kevin Durant": "2010s/2020s",
    "Russell Westbrook": "2010s/2020s",
    "James Harden": "2010s/2020s",
    "Chris Paul": "2010s/2020s",
    "Carmelo Anthony": "2000s/2010s",
    "Derrick Rose": "2010s",
    "Blake Griffin": "2010s",
    "Damian Lillard": "2010s/2020s",
    "Kyrie Irving": "2010s/2020s",
    "Nikola Jokic": "2020s",
    "Giannis Antetokounmpo": "2010s/2020s",
    "Luka Doncic": "2020s",
    "Ja Morant": "2020s",
    "Victor Wembanyama": "2020s",
    "Anthony Edwards": "2020s",
    "Tyrese Haliburton": "2020s",
    "Tyrese Maxey": "2020s",
    "Derrick White": "2020s",
    "Chris Andersen": "2000s/2010s",
    "Mason Plumlee": "2010s/2020s",
    "Jason Williams": "2000s",
    "Nate Robinson": "2000s/2010s",
}


def clean_strategy_format(value):
    text = str(value or "").strip()

    if not text:
        return "Top 10 Plays"

    text = text.replace("Top 10 Top 10", "Top 10")
    text = text.replace("Career Highlights", "Plays")
    text = text.replace("History Countdown", "Top 10 Plays")
    text = text.replace("Handles", "Crossovers")
    text = text.replace("Top 10 Shots", "Top 10 Clutch Shots")
    text = text.replace("Top 10 Clutch Plays", "Top 10 Clutch Shots")

    while "Top 10 Top 10" in text:
        text = text.replace("Top 10 Top 10", "Top 10")

    allowed = [
        "Top 10 Plays",
        "Top 10 Dunks",
        "Top 10 Assists",
        "Top 10 Blocks",
        "Top 10 Clutch Shots",
        "Top 10 Crossovers",
        "Top 10 3-Pointers",
        "Top 10 Fadeaways",
        "Top 10 Skyhooks",
    ]

    low = normalize(text)
    for item in allowed:
        if normalize(item) in low:
            return item

    if "dunk" in low:
        return "Top 10 Dunks"
    if "assist" in low or "pass" in low:
        return "Top 10 Assists"
    if "block" in low:
        return "Top 10 Blocks"
    if "clutch" in low or "game winner" in low or "buzzer" in low:
        return "Top 10 Clutch Shots"
    if "crossover" in low or "cross" in low or "handle" in low:
        return "Top 10 Crossovers"
    if "3" in low or "three" in low:
        return "Top 10 3-Pointers"
    if "fadeaway" in low:
        return "Top 10 Fadeaways"
    if "skyhook" in low:
        return "Top 10 Skyhooks"

    return "Top 10 Plays"


def clean_strategy_title(player, fmt):
    player = str(player or "").strip()
    fmt = clean_strategy_format(fmt)

    if not player:
        return fmt

    # If topic already starts with Top 10, do not create "Top 10 Top 10".
    if normalize(player).startswith("top 10"):
        return player.replace("Handles", "Crossovers").replace("History Countdown", "").strip()

    return f"{player} {fmt} of Career"


def player_photo_url(player):
    name = str(player or "NBA Player").strip() or "NBA Player"
    return f"https://ui-avatars.com/api/?name={quote_plus(name)}&background=111111&color=ffffff&size=256&bold=true"


def player_wiki_search_url(player):
    name = str(player or "").strip()
    if not name:
        return ""
    return f"https://en.wikipedia.org/wiki/Special:Search?search={quote_plus(name)}"


def infer_player_era(player, meta=None):
    meta = meta or {}
    for key in ["era", "primary_era", "decade", "generation"]:
        value = str(meta.get(key, "") or "").strip()
        if value and value.lower() not in ["unknown", "none", "null", "custom idea bank"]:
            return value

    for start_key in ["start_year", "first_year", "from_year", "career_start", "draft_year", "rookie_year"]:
        year = safe_int(meta.get(start_key))
        if year:
            decade = int(year / 10) * 10
            return f"{decade}s"

    return PLAYER_ERA_FALLBACKS.get(str(player or "").strip(), "All-Time")


def unique_projected_views(base, rank=0, score=0, rpm=0, revenue=0):
    base = safe_int(base)
    if base <= 0:
        base = 18000

    # Small deterministic offsets make the numbers feel specific without faking huge jumps.
    offset = ((rank + 1) * 137) + int(safe_float(score) * 11) + int(safe_float(rpm) * 97) + int(safe_float(revenue) % 83)
    return max(1500, int(base + offset))


def strategy_money_row(item, rank=0, channel_rpm=0, conservative=False):
    row = dict(item or {})

    fmt = clean_strategy_format(row.get("format") or row.get("content_type") or row.get("shuffle_format") or "Top 10 Plays")
    player = row.get("player") or row.get("player_name") or row.get("topic") or row.get("name") or ""

    views = safe_int(
        row.get("expected_views")
        or row.get("projected_views")
        or row.get("average_views")
        or row.get("views")
        or 0
    )

    total_revenue = safe_float(row.get("total_revenue") or row.get("synced_revenue"))
    average_revenue = safe_float(row.get("average_revenue"))
    synced_revenue = safe_float(row.get("synced_revenue"))
    best_format_revenue = safe_float(row.get("best_format_total_revenue"))
    revenue = safe_float(row.get("expected_revenue") or row.get("projected_revenue"))

    rpm = safe_float(
        row.get("expected_rpm")
        or row.get("projected_rpm")
        or row.get("average_rpm")
        or row.get("synced_rpm")
        or row.get("best_format_average_rpm")
        or channel_rpm
        or 0
    )

    real_revenue = max(best_format_revenue, synced_revenue, total_revenue, average_revenue)

    if real_revenue > 0 and not conservative:
        revenue = real_revenue
    elif revenue <= 0:
        if rpm <= 0:
            rpm = safe_float(channel_rpm) or 1.75
        revenue = (max(views, 15000) / 1000) * rpm

    if rpm <= 0 and revenue > 0 and views > 0:
        rpm = (revenue / views) * 1000

    if rpm <= 0:
        rpm = safe_float(channel_rpm) or 1.75

    if views <= 0:
        # Real players use their average views when available; fillers use conservative but unique projection.
        views = 18000

    views = unique_projected_views(
        views,
        rank=rank,
        score=row.get("opportunity_score") or row.get("popularity_score") or 0,
        rpm=rpm,
        revenue=revenue
    )

    # Do not inflate conservative filler revenue past normal channel-level projections.
    if conservative:
        revenue = (views / 1000) * rpm

    revenue = round(max(0, revenue), 2)
    rpm = round(max(0.01, rpm), 2)

    meta = row.get("meta") or {}
    era = row.get("era") or infer_player_era(player, meta)

    row.update({
        "player": player,
        "player_name": player,
        "topic": row.get("topic") or player,
        "format": fmt,
        "content_type": fmt,
        "title": clean_strategy_title(player, fmt),
        "era": era,
        "expected_views": views,
        "projected_views": views,
        "expected_revenue": revenue,
        "projected_revenue": revenue,
        "expected_rpm": rpm,
        "projected_rpm": rpm,
        "photo_url": row.get("photo_url") or player_photo_url(player),
        "wiki_search_url": row.get("wiki_search_url") or player_wiki_search_url(player),
    })

    return row


def make_strategy_revenues_unique(items):
    used = set()
    output = []

    for idx, item in enumerate(items or []):
        row = dict(item)
        revenue = round(safe_float(row.get("expected_revenue") or row.get("projected_revenue")), 2)

        while revenue in used:
            revenue = round(revenue + 0.01, 2)

        used.add(revenue)
        row["expected_revenue"] = revenue
        row["projected_revenue"] = revenue
        output.append(row)

    return output


def build_channel_brain_recommendations(videos):
    if not videos:
        return {
            "version": "2.6-real-revenue",
            "headline": "No synced videos yet.",
            "today_focus": "Click Sync Channel first.",
            "best_upload_time": "6:00 PM",
            "best_next_upload": None,
            "upload_next": [],
            "shuffle_ideas": [],
            "avoid_next": [],
            "best_formats": [],
            "money_notes": [],
            "action_plan": ["Sync channel videos.", "Run YouTube revenue sync."],
            "confidence_score": 0,
            "data_health": {
                "synced_videos": 0,
                "synced_revenue_videos": 0,
                "synced_revenue_coverage_percent": 0
            }
        }

    channel_rpm = safe_float(get_best_channel_rpm() or 0)

    player_meta = {}
    for p in NBA_PLAYERS:
        name = p.get("name", "")
        if name:
            player_meta[normalize(name)] = p

    player_map = defaultdict(lambda: {
        "player": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": [],
        "synced_revenue_videos": 0,
        "top_10_videos": 0,
        "solo_highlight_videos": 0,
        "done_top10_types": set(),
        "subtypes": defaultdict(lambda: {
            "format": "",
            "videos": 0,
            "total_views": 0,
            "total_revenue": 0,
            "rpm_values": []
        })
    })

    format_totals = defaultdict(lambda: {
        "format": "",
        "videos": 0,
        "total_views": 0,
        "total_revenue": 0,
        "rpm_values": []
    })

    synced_revenue_videos = 0
    total_synced_revenue = 0
    covered_players = set()
    real_view_samples = []
    real_rpm_samples = []

    for video in videos:
        if not has_enough_views_for_trend(video):
            continue

        title = video.get("title", "") or ""
        player = video.get("player_name") or detect_player(title) or "Unknown"
        if player == "Unknown":
            continue

        covered_players.add(normalize(player))

        views = safe_int(video.get("views"))
        real_view_samples.append(views)

        try:
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

        if rpm <= 0 and revenue > 0 and views > 0:
            rpm = (revenue / views) * 1000

        if rpm > 0:
            real_rpm_samples.append(rpm)

        if revenue > 0 or rpm > 0:
            synced_revenue_videos += 1
            total_synced_revenue += revenue

        content_type = detect_content_type(title or video.get("content_type", ""))
        top10_type = clean_strategy_format(detect_top10_type_from_title(title))
        content_subtype = top10_type or clean_strategy_format(detect_content_subtype(title or video.get("content_type", "")))

        row = player_map[player]
        row["player"] = player
        row["videos"] += 1
        row["total_views"] += views
        row["total_revenue"] += revenue

        if top10_type:
            row["done_top10_types"].add(top10_type)

        if rpm > 0:
            row["rpm_values"].append(rpm)

        if revenue > 0 or rpm > 0:
            row["synced_revenue_videos"] += 1

        if content_type == "Top 10":
            row["top_10_videos"] += 1
        else:
            row["solo_highlight_videos"] += 1

        subtype_row = row["subtypes"][content_subtype]
        subtype_row["format"] = content_subtype
        subtype_row["videos"] += 1
        subtype_row["total_views"] += views
        subtype_row["total_revenue"] += revenue
        if rpm > 0:
            subtype_row["rpm_values"].append(rpm)

        format_totals[content_subtype]["format"] = content_subtype
        format_totals[content_subtype]["videos"] += 1
        format_totals[content_subtype]["total_views"] += views
        format_totals[content_subtype]["total_revenue"] += revenue
        if rpm > 0:
            format_totals[content_subtype]["rpm_values"].append(rpm)

    channel_avg_views = int(sum(real_view_samples) / len(real_view_samples)) if real_view_samples else 18000
    channel_avg_rpm = round(sum(real_rpm_samples) / len(real_rpm_samples), 2) if real_rpm_samples else (channel_rpm or 1.75)

    real_candidates = []
    avoid_candidates = []
    shuffle_ideas = []

    for player, row in player_map.items():
        videos_count = max(1, safe_int(row["videos"]))
        revenue_video_count = max(1, safe_int(row["synced_revenue_videos"]))
        avg_views = safe_div(row["total_views"], videos_count)
        avg_revenue = safe_div(row["total_revenue"], revenue_video_count)
        avg_rpm = round(sum(row["rpm_values"]) / len(row["rpm_values"]), 2) if row["rpm_values"] else 0
        meta = player_meta.get(normalize(player), {})

        subtype_options = []
        for subtype, item in row["subtypes"].items():
            subtype_videos = max(1, safe_int(item["videos"]))
            subtype_avg_views = safe_div(item["total_views"], subtype_videos)
            subtype_avg_revenue = safe_div(item["total_revenue"], subtype_videos)
            subtype_avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0
            subtype_options.append({
                "format": clean_strategy_format(subtype),
                "videos": item["videos"],
                "average_views": subtype_avg_views,
                "average_revenue": subtype_avg_revenue,
                "average_rpm": subtype_avg_rpm,
                "total_views": item["total_views"],
                "total_revenue": round(item["total_revenue"], 2),
                "score": (item["total_revenue"] * 3) + (subtype_avg_revenue * 2) + (subtype_avg_rpm * 10) + (subtype_avg_views / 1000)
            })

        subtype_options.sort(key=lambda x: x["score"], reverse=True)
        best = subtype_options[0] if subtype_options else {
            "format": "Top 10 Plays",
            "average_views": avg_views,
            "average_revenue": avg_revenue,
            "average_rpm": avg_rpm,
            "total_revenue": row["total_revenue"],
        }

        next_fmt = clean_strategy_format(next_top10_type_for_player(player, row["done_top10_types"], meta))
        upload_fmt = clean_strategy_format(best.get("format") or "Top 10 Plays")

        candidate = {
            "player": player,
            "player_name": player,
            "topic": player,
            "format": upload_fmt,
            "shuffle_format": next_fmt,
            "content_type": upload_fmt,
            "era": infer_player_era(player, meta),
            "expected_views": safe_int(best.get("average_views")) or int(avg_views),
            "projected_views": safe_int(best.get("average_views")) or int(avg_views),
            "expected_revenue": round(max(safe_float(best.get("total_revenue")), safe_float(best.get("average_revenue")), safe_float(row["total_revenue"])), 2),
            "projected_revenue": round(max(safe_float(best.get("total_revenue")), safe_float(best.get("average_revenue")), safe_float(row["total_revenue"])), 2),
            "expected_rpm": round(safe_float(best.get("average_rpm")) or avg_rpm or channel_avg_rpm, 2),
            "projected_rpm": round(safe_float(best.get("average_rpm")) or avg_rpm or channel_avg_rpm, 2),
            "average_views": int(avg_views),
            "average_revenue": round(avg_revenue, 2),
            "average_rpm": round(avg_rpm, 2),
            "total_revenue": round(row["total_revenue"], 2),
            "synced_revenue": round(row["total_revenue"], 2),
            "videos": row["videos"],
            "top_10_videos": row["top_10_videos"],
            "done_top10_types": sorted(list(row["done_top10_types"])),
            "total_views": row["total_views"],
            "synced_revenue_videos": row["synced_revenue_videos"],
            "photo_url": player_photo_url(player),
            "wiki_search_url": player_wiki_search_url(player),
            "reason": f"Real synced YouTube API revenue signal for this player."
        }

        if safe_float(candidate["total_revenue"]) > 0:
            real_candidates.append(candidate)

        if safe_float(candidate["total_revenue"]) < 10 and safe_float(candidate["expected_revenue"]) < 10:
            avoid_candidates.append({
                "player": player,
                "player_name": player,
                "reason": "Weak synced money signal compared with better options",
                "average_revenue": round(avg_revenue, 2),
                "average_views": int(avg_views),
                "average_rpm": round(avg_rpm, 2),
                "total_revenue": round(row["total_revenue"], 2),
                "videos": row["videos"],
                "era": infer_player_era(player, meta),
                "photo_url": player_photo_url(player),
                "wiki_search_url": player_wiki_search_url(player),
            })

        shuffle_ideas.append(strategy_money_row({
            **candidate,
            "format": next_fmt,
            "content_type": next_fmt,
            "expected_views": max(int(avg_views), safe_int(best.get("average_views")), int(channel_avg_views * 0.85)),
            "expected_revenue": max(avg_revenue, (max(int(avg_views), int(channel_avg_views * 0.85)) / 1000) * (avg_rpm or channel_avg_rpm)),
            "expected_rpm": avg_rpm or channel_avg_rpm,
            "reason": f"Suggested next format: {next_fmt}."
        }, rank=len(shuffle_ideas), channel_rpm=channel_avg_rpm, conservative=True))

    real_candidates = sorted(
        real_candidates,
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("expected_revenue")),
            safe_float(x.get("expected_rpm")),
            safe_int(x.get("total_views"))
        ),
        reverse=True
    )

    # Build conservative filler pool from your custom ideas and NBA player database.
    filler_pool = []

    for idea in CUSTOM_STRATEGY_IDEAS:
        player = idea.get("player") or idea.get("topic") or ""
        if not player:
            continue

        fmt = clean_strategy_format(idea.get("format") or "Top 10 Plays")
        meta = player_meta.get(normalize(player), {})
        tier = normalize(idea.get("tier", ""))
        defaults = custom_tier_defaults(tier)

        # Conservative projection: close to actual channel average, adjusted by tier and rank later.
        tier_factor = {
            "elite": 1.15,
            "s": 1.05,
            "a": 0.92,
            "fan request": 0.72,
            "fan_request": 0.72,
        }.get(tier, 0.85)

        base_views = int(max(8000, channel_avg_views * tier_factor))
        rpm = max(1.25, min(defaults.get("rpm", channel_avg_rpm), channel_avg_rpm * 1.35 if channel_avg_rpm else defaults.get("rpm", 2.0)))

        filler_pool.append(strategy_money_row({
            "player": player,
            "player_name": player,
            "topic": player,
            "format": fmt,
            "content_type": fmt,
            "era": infer_player_era(player, meta),
            "expected_views": base_views,
            "projected_views": base_views,
            "expected_rpm": rpm,
            "projected_rpm": rpm,
            "source": "Custom Idea Bank",
            "opportunity_score": defaults.get("score", 70),
            "reason": "Projected from your custom idea bank and current channel trends.",
            "photo_url": player_photo_url(player),
            "wiki_search_url": player_wiki_search_url(player),
        }, rank=len(filler_pool), channel_rpm=channel_avg_rpm, conservative=True))

    for player in NBA_PLAYERS:
        name = player.get("name", "")
        if not name or normalize(name) in covered_players:
            continue

        popularity = safe_float(player.get("popularity_score") or player.get("youtube_score") or player.get("priority_score") or 0)
        all_star = safe_int(player.get("all_star") or player.get("all_stars"))
        mvp = safe_int(player.get("mvp") or player.get("mvps"))
        hof = bool(player.get("hall_of_fame") or player.get("hof"))
        score = popularity + (all_star * 2) + (mvp * 8) + (15 if hof else 0)

        if score < 25:
            continue

        fmt = clean_strategy_format(next_top10_type_for_player(name, set(), player))
        base_views = int(max(7500, min(channel_avg_views * 1.05, score * 525)))
        rpm = max(1.15, channel_avg_rpm or channel_rpm or 1.75)

        filler_pool.append(strategy_money_row({
            "player": name,
            "player_name": name,
            "topic": name,
            "format": fmt,
            "content_type": fmt,
            "era": infer_player_era(name, player),
            "expected_views": base_views,
            "projected_views": base_views,
            "expected_rpm": rpm,
            "projected_rpm": rpm,
            "source": "Player Database",
            "opportunity_score": min(100, score),
            "reason": "Projected from Idea Lab/player database and current channel trends.",
            "photo_url": player_photo_url(name),
            "wiki_search_url": player_wiki_search_url(name),
        }, rank=len(filler_pool), channel_rpm=channel_avg_rpm, conservative=True))

    filler_pool = sorted(
        filler_pool,
        key=lambda x: (
            safe_float(x.get("expected_revenue")),
            safe_float(x.get("opportunity_score")),
            safe_int(x.get("expected_views"))
        ),
        reverse=True
    )

    # Upload Next: exactly 15 different names when possible.
    upload_next = []
    seen_players = set()

    for item in real_candidates + filler_pool:
        key = normalize(item.get("player") or item.get("player_name") or item.get("topic"))
        if not key or key in seen_players:
            continue

        seen_players.add(key)
        conservative = safe_float(item.get("total_revenue")) <= 0
        upload_next.append(strategy_money_row(item, rank=len(upload_next), channel_rpm=channel_avg_rpm, conservative=conservative))

        if len(upload_next) >= 15:
            break

    upload_next = make_strategy_revenues_unique(upload_next)

    # Shuffle has more options and can repeat players with different formats.
    shuffle_seen = set()
    merged_shuffle = []
    for item in shuffle_ideas + filler_pool:
        fmt = clean_strategy_format(item.get("format") or item.get("content_type"))
        key = f"{normalize(item.get('player') or item.get('player_name') or item.get('topic'))}|{normalize(fmt)}"
        if key in shuffle_seen:
            continue
        shuffle_seen.add(key)
        merged_shuffle.append(strategy_money_row({**item, "format": fmt, "content_type": fmt}, rank=len(merged_shuffle), channel_rpm=channel_avg_rpm, conservative=safe_float(item.get("total_revenue")) <= 0))

    shuffle_ideas = make_strategy_revenues_unique(merged_shuffle[:700])

    avoid_next = sorted(
        unique_by_player(avoid_candidates),
        key=lambda x: (
            safe_float(x.get("total_revenue")),
            safe_float(x.get("average_revenue")),
            safe_int(x.get("average_views"))
        )
    )[:30]

    format_rows = []
    for fmt, item in format_totals.items():
        fmt_clean = clean_strategy_format(fmt)
        videos_count = max(1, safe_int(item["videos"]))
        avg_rpm = round(sum(item["rpm_values"]) / len(item["rpm_values"]), 2) if item["rpm_values"] else 0
        format_rows.append({
            "type": fmt_clean,
            "format": fmt_clean,
            "videos": item["videos"],
            "total_views": item["total_views"],
            "total_revenue": round(item["total_revenue"], 2),
            "average_views": safe_div(item["total_views"], videos_count),
            "average_revenue": safe_div(item["total_revenue"], videos_count),
            "average_rpm": avg_rpm,
            "synced_revenue_videos": len(item["rpm_values"])
        })

    best_formats = sorted(
        format_rows,
        key=lambda x: (safe_float(x.get("average_revenue")), safe_float(x.get("average_rpm")), safe_int(x.get("total_views"))),
        reverse=True
    )

    best_next_upload = upload_next[0] if upload_next else None
    coverage_percent = round((synced_revenue_videos / len(videos)) * 100, 1) if videos else 0

    if coverage_percent >= 80:
        confidence_score = 90
    elif coverage_percent >= 50:
        confidence_score = 75
    elif coverage_percent >= 25:
        confidence_score = 55
    elif coverage_percent > 0:
        confidence_score = 35
    else:
        confidence_score = 10

    if best_next_upload:
        headline = f"Best next upload: {best_next_upload['player']} in {best_next_upload['format']} format."
        today_focus = f"Plan a {best_next_upload['player']} {best_next_upload['format']} upload next."
        action_plan = [
            f"Plan a {best_next_upload['player']} {best_next_upload['format']} video next.",
            "Use Upload Next for the best real revenue-backed choices.",
            "Use Shuffle Idea for more player/format ideas without repeating completed formats.",
            "Check 7-day revenue/RPM after upload and let the rankings update automatically."
        ]
    else:
        headline = "Sync more revenue data to generate a recommendation."
        today_focus = "Review Player Rankings and avoid weak-money players."
        action_plan = ["Sync channel videos.", "Run YouTube revenue sync.", "Review Player Rankings."]

    return {
        "version": "2.6-real-revenue-15-era-photo",
        "headline": headline,
        "today_focus": today_focus,
        "best_upload_time": "6:00 PM",
        "best_next_upload": best_next_upload,
        "confidence_score": confidence_score,
        "data_health": {
            "synced_videos": len(videos),
            "synced_revenue_videos": synced_revenue_videos,
            "synced_revenue_coverage_percent": coverage_percent,
            "total_synced_revenue": round(total_synced_revenue, 2),
            "manual_channel_rpm": round(channel_rpm, 2),
            "channel_average_views_used_for_projections": channel_avg_views,
            "channel_average_rpm_used_for_projections": channel_avg_rpm
        },
        "upload_next": upload_next[:15],
        "shuffle_ideas": shuffle_ideas,
        "avoid_next": avoid_next,
        "best_formats": best_formats,
        "money_notes": [
            "Upload Next fills 15 names when enough candidates exist.",
            "Existing players use real synced YouTube API revenue/RPM/views first.",
            "Projected fillers use conservative channel-average trends with unique view numbers.",
            "Era, photo_url, and wiki_search_url are included for future UI display."
        ],
        "action_plan": action_plan
    }


# =========================================================
# FINAL POSTPROCESS FIX — NO PLAYER PHOTOS
# Keeps current Strategy Center logic, then forces:
# - 15 Upload Next names
# - no repeated 15,000 / 18,000 projected view defaults
# - era restored
# - clean formats only
# - no photo fields/files needed
# =========================================================

_CV_PLAYER_ERA_FALLBACKS = {
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
    "Connie Hawkins": "1960s/1970s",
    "David Thompson": "1970s/1980s",
    "Earl Monroe": "1970s",
    "Walt Frazier": "1970s",
    "Bernard King": "1980s",
    "Elvin Hayes": "1970s/1980s",
    "Bob McAdoo": "1970s/1980s",
    "Larry Bird": "1980s/1990s",
    "Magic Johnson": "1980s/1990s",
    "Michael Jordan": "1980s/1990s",
    "Hakeem Olajuwon": "1980s/1990s",
    "Dominique Wilkins": "1980s/1990s",
    "Clyde Drexler": "1980s/1990s",
    "Karl Malone": "1980s/1990s",
    "John Stockton": "1980s/1990s",
    "Shaquille O'Neal": "1990s/2000s",
    "David Robinson": "1990s",
    "Reggie Miller": "1990s/2000s",
    "Gary Payton": "1990s/2000s",
    "Shawn Kemp": "1990s",
    "Kobe Bryant": "2000s/2010s",
    "Allen Iverson": "2000s",
    "Vince Carter": "2000s/2010s",
    "Kevin Garnett": "2000s/2010s",
    "Tim Duncan": "2000s/2010s",
    "Dirk Nowitzki": "2000s/2010s",
    "Steve Nash": "2000s",
    "Jason Kidd": "2000s",
    "Jason Williams": "2000s",
    "Tracy McGrady": "2000s",
    "Paul Pierce": "2000s",
    "Ray Allen": "2000s/2010s",
    "Manu Ginobili": "2000s/2010s",
    "Pau Gasol": "2000s/2010s",
    "Yao Ming": "2000s",
    "Dikembe Mutombo": "1990s/2000s",
    "Dwight Howard": "2000s/2010s",
    "LeBron James": "2000s/2010s/2020s",
    "Stephen Curry": "2010s/2020s",
    "Kevin Durant": "2010s/2020s",
    "Russell Westbrook": "2010s/2020s",
    "James Harden": "2010s/2020s",
    "Chris Paul": "2010s/2020s",
    "Carmelo Anthony": "2000s/2010s",
    "Derrick Rose": "2010s",
    "Blake Griffin": "2010s",
    "Damian Lillard": "2010s/2020s",
    "Kyrie Irving": "2010s/2020s",
    "Nikola Jokic": "2020s",
    "Giannis Antetokounmpo": "2010s/2020s",
    "Luka Doncic": "2020s",
    "Ja Morant": "2020s",
    "Victor Wembanyama": "2020s",
    "Anthony Edwards": "2020s",
    "Tyrese Haliburton": "2020s",
    "Tyrese Maxey": "2020s",
    "Derrick White": "2020s",
    "Chris Andersen": "2000s/2010s",
    "Mason Plumlee": "2010s/2020s",
    "Nate Robinson": "2000s/2010s",
}


def _cv_player_meta_lookup():
    lookup = {}
    for p in NBA_PLAYERS:
        name = p.get("name", "")
        if name:
            lookup[normalize(name)] = p
    return lookup


def _cv_clean_strategy_format(value):
    text = str(value or "Top 10 Plays").strip()
    text = text.replace("Top 10 Top 10", "Top 10")
    text = text.replace("Handles", "Crossovers")
    text = text.replace("Top 10 Shots", "Top 10 Clutch Shots")
    text = text.replace("Top 10 Clutch Plays", "Top 10 Clutch Shots")
    text = text.replace("Career Highlights", "Plays")
    text = text.replace("History Countdown", "Top 10 Plays")

    low = normalize(text)
    if "dunk" in low:
        return "Top 10 Dunks"
    if "assist" in low or "pass" in low:
        return "Top 10 Assists"
    if "block" in low:
        return "Top 10 Blocks"
    if "clutch" in low or "game winner" in low or "buzzer" in low:
        return "Top 10 Clutch Shots"
    if "cross" in low or "handle" in low or "dribble" in low:
        return "Top 10 Crossovers"
    if "3" in low or "three" in low:
        return "Top 10 3-Pointers"
    if "fadeaway" in low:
        return "Top 10 Fadeaways"
    if "skyhook" in low:
        return "Top 10 Skyhooks"
    return "Top 10 Plays"


def _cv_infer_era(player, meta=None, current=""):
    current = str(current or "").strip()
    if current and current.lower() not in ["unknown", "unknown era", "uncategorized", "custom idea bank", "none", "null", "—"]:
        return current

    meta = meta or {}
    for key in ["era", "primary_era", "decade", "generation"]:
        value = str(meta.get(key, "") or "").strip()
        if value and value.lower() not in ["unknown", "none", "null"]:
            return value

    for key in ["start_year", "first_year", "career_start", "draft_year", "rookie_year"]:
        year = safe_int(meta.get(key))
        if year:
            return f"{int(year / 10) * 10}s"

    return _CV_PLAYER_ERA_FALLBACKS.get(str(player or "").strip(), "All-Time")


def _cv_unique_views(base, name="", rank=0, score=0, rpm=0, revenue=0):
    base = safe_int(base)
    if base <= 0:
        base = 15000

    name_value = sum((i + 1) * ord(c) for i, c in enumerate(normalize(name)))
    offset = (name_value % 2700) + ((rank + 1) * 139) + int(safe_float(score) * 7) + int(safe_float(rpm) * 59) + int(safe_float(revenue) % 97)
    return max(1500, int(base + offset))


def _cv_make_unique_numbers(items):
    used_views = set()
    used_revenue = set()
    fixed = []

    for idx, raw in enumerate(items or []):
        item = dict(raw or {})
        player = item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "Unknown"
        revenue = round(safe_float(item.get("expected_revenue") or item.get("projected_revenue") or item.get("total_revenue") or item.get("average_revenue")), 2)
        views = safe_int(item.get("expected_views") or item.get("projected_views") or item.get("average_views") or item.get("views"))
        rpm = safe_float(item.get("expected_rpm") or item.get("projected_rpm") or item.get("average_rpm"))

        views = _cv_unique_views(views, player, idx, item.get("opportunity_score") or item.get("decision_score") or 0, rpm, revenue)
        while views in used_views:
            views += 137
        used_views.add(views)

        while revenue in used_revenue:
            revenue = round(revenue + 0.01, 2)
        used_revenue.add(revenue)

        item["expected_views"] = views
        item["projected_views"] = views
        item["expected_revenue"] = revenue
        item["projected_revenue"] = revenue
        fixed.append(item)

    return fixed


_cv_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv_previous_build_channel_brain_recommendations(videos)
    meta_lookup = _cv_player_meta_lookup()
    channel_rpm = safe_float((data.get("data_health") or {}).get("channel_average_rpm_used_for_projections") or get_best_channel_rpm() or 1.75)

    def fix_item(raw, rank=0, conservative=False):
        item = dict(raw or {})
        player = item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "Unknown"
        meta = meta_lookup.get(normalize(player), {})

        fmt = _cv_clean_strategy_format(item.get("format") or item.get("content_type") or item.get("shuffle_format") or "Top 10 Plays")
        views = safe_int(item.get("expected_views") or item.get("projected_views") or item.get("average_views") or item.get("views") or 15000)
        rpm = safe_float(item.get("expected_rpm") or item.get("projected_rpm") or item.get("average_rpm") or channel_rpm or 1.75)
        revenue = safe_float(item.get("expected_revenue") or item.get("projected_revenue") or item.get("total_revenue") or item.get("average_revenue"))

        if revenue <= 0:
            revenue = (views / 1000) * rpm

        if conservative and revenue < 10:
            revenue = max(10.01, revenue)

        item.update({
            "player": player,
            "player_name": player,
            "topic": player,
            "format": fmt,
            "content_type": fmt,
            "title": f"{player} {fmt} of Career",
            "era": _cv_infer_era(player, meta, item.get("era")),
            "expected_views": _cv_unique_views(views, player, rank, item.get("opportunity_score") or 0, rpm, revenue),
            "projected_views": _cv_unique_views(views, player, rank, item.get("opportunity_score") or 0, rpm, revenue),
            "expected_revenue": round(revenue, 2),
            "projected_revenue": round(revenue, 2),
            "expected_rpm": round(max(0.01, rpm), 2),
            "projected_rpm": round(max(0.01, rpm), 2),
        })

        # Remove any older photo fields if they exist.
        item.pop("photo_url", None)
        item.pop("wiki_url", None)
        item.pop("wiki_search_url", None)
        return item

    upload_next = [fix_item(x, i, conservative=safe_float(x.get("total_revenue")) <= 0) for i, x in enumerate(data.get("upload_next") or [])]
    shuffle_ideas = [fix_item(x, i, conservative=safe_float(x.get("total_revenue")) <= 0) for i, x in enumerate(data.get("shuffle_ideas") or [])]

    seen_players = {normalize(x.get("player") or x.get("player_name") or x.get("topic")) for x in upload_next}
    for item in shuffle_ideas:
        key = normalize(item.get("player") or item.get("player_name") or item.get("topic"))
        if not key or key in seen_players:
            continue
        seen_players.add(key)
        upload_next.append(fix_item(item, len(upload_next), conservative=safe_float(item.get("total_revenue")) <= 0))
        if len(upload_next) >= 15:
            break

    if len(upload_next) < 15:
        for p in NBA_PLAYERS:
            name = p.get("name", "")
            key = normalize(name)
            if not name or key in seen_players:
                continue

            score = safe_float(p.get("popularity_score") or p.get("youtube_score") or p.get("priority_score") or 35)
            views = _cv_unique_views(max(12000, int(score * 575)), name, len(upload_next), score, channel_rpm, 0)
            filler = fix_item({
                "player": name,
                "format": _cv_clean_strategy_format(next_top10_type_for_player(name, set(), p)),
                "era": _cv_infer_era(name, p),
                "expected_views": views,
                "projected_views": views,
                "expected_rpm": channel_rpm,
                "projected_rpm": channel_rpm,
                "expected_revenue": round((views / 1000) * channel_rpm, 2),
                "projected_revenue": round((views / 1000) * channel_rpm, 2),
                "reason": "Projected from Idea Lab/player database and current channel trends.",
                "source": "Player Database"
            }, len(upload_next), conservative=True)

            seen_players.add(key)
            upload_next.append(filler)
            if len(upload_next) >= 15:
                break

    data["upload_next"] = _cv_make_unique_numbers(upload_next[:15])
    data["shuffle_ideas"] = _cv_make_unique_numbers(shuffle_ideas[:700])
    data["avoid_next"] = [fix_item(x, i) for i, x in enumerate(data.get("avoid_next") or [])]
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else data.get("best_next_upload")

    if data.get("best_next_upload"):
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."

    data["version"] = "2.7-final-15-era-unique-views-no-photos"
    return data


# =========================================================
# FINAL REALISTIC PROJECTION FILTER 2.8
# Fixes examples like random database players showing 400k+ views.
# - Caps projected database-only ideas to realistic ranges.
# - Prefers real channel winners + custom curated NBA ideas.
# - Reduces obscure/random old player frequency in Shuffle.
# - Keeps Upload Next at 15.
# =========================================================

_CV_CURATED_PRIORITY_NAMES = {
    "mason plumlee",
    "allen iverson",
    "magic johnson",
    "larry bird",
    "wilt chamberlain",
    "michael jordan",
    "kobe bryant",
    "pete maravich",
    "vince carter",
    "stephen curry",
    "lebron james",
    "kareem abdul jabbar",
    "hakeem olajuwon",
    "nikola jokic",
    "steve nash",
    "jason williams",
    "shaquille oneal",
    "shaquille o neal",
    "dominique wilkins",
    "david robinson",
    "bill russell",
    "tim duncan",
    "reggie miller",
    "ray allen",
    "damian lillard",
    "chris paul",
    "blake griffin",
    "derrick rose",
    "nate robinson",
    "ja morant",
    "russell westbrook",
    "kyrie irving",
    "george gervin",
    "connie hawkins",
    "david thompson",
    "earl monroe",
    "walt frazier",
    "bernard king",
    "elvin hayes",
    "bob mcadoo",
    "clyde drexler",
    "shawn kemp",
    "gary payton",
    "john stockton",
    "manu ginobili",
    "pau gasol",
    "yao ming",
    "dikembe mutombo",
    "dwight howard",
    "tracy mcgrady",
    "kevin durant",
    "carmelo anthony",
    "jerry west",
    "grant hill",
    "victor wembanyama",
    "charles barkley",
    "julius erving",
}

_CV_RANDOM_DATABASE_BLOCKLIST = {
    "tom abernethy",
    "scott wedman",
    "tim thomas",
    "terry teagle",
    "skylar mays",
}


def _cv_is_random_database_player(item):
    source = normalize(item.get("source") or "")
    reason = normalize(item.get("reason") or "")
    name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")

    if name in _CV_CURATED_PRIORITY_NAMES:
        return False

    if name in _CV_RANDOM_DATABASE_BLOCKLIST:
        return True

    if "player database" in source or "idea lab/player database" in reason:
        total_revenue = safe_float(item.get("total_revenue") or item.get("synced_revenue"))
        videos = safe_int(item.get("videos"))
        score = safe_float(item.get("opportunity_score") or item.get("decision_score") or item.get("recommended_score"))
        # Keep only strong database names. Most random database-only players should not dominate shuffle.
        if total_revenue <= 0 and videos <= 0 and score < 82:
            return True

    return False


def _cv_realistic_projection_cap(item, rank=0, channel_avg_views=25000, channel_rpm=1.35):
    row = dict(item or {})
    name = row.get("player") or row.get("player_name") or row.get("topic") or row.get("name") or "Unknown"
    name_key = normalize(name)
    source = normalize(row.get("source") or "")
    reason = normalize(row.get("reason") or "")
    has_real_revenue = safe_float(row.get("total_revenue") or row.get("synced_revenue")) > 0

    views = safe_int(row.get("expected_views") or row.get("projected_views") or row.get("average_views"))
    rpm = safe_float(row.get("expected_rpm") or row.get("projected_rpm") or row.get("average_rpm") or channel_rpm or 1.35)

    # Real channel players can stay higher because they are proven by your own stats.
    if has_real_revenue:
        cap = max(30000, min(125000, int(channel_avg_views * 2.75)))
        floor = 5000
    elif name_key in _CV_CURATED_PRIORITY_NAMES:
        # Curated ideas can be good, but not 400k unless your channel stats really justify it.
        cap = max(22000, min(85000, int(channel_avg_views * 1.65)))
        floor = 6500
    elif "custom idea" in source:
        cap = max(18000, min(65000, int(channel_avg_views * 1.25)))
        floor = 5500
    else:
        # Plain database filler should be conservative.
        cap = max(12000, min(42000, int(channel_avg_views * 0.85)))
        floor = 3500

    # Compress huge outliers instead of allowing 400k+.
    if views > cap:
        name_value = sum((i + 1) * ord(c) for i, c in enumerate(name_key))
        views = int(cap - (name_value % 2400) - (rank * 47))
        views = max(floor, views)

    if views <= 0:
        views = floor + ((rank + 1) * 211)

    # Make each view number unique/specific.
    views = _cv_unique_views(views, name, rank, row.get("opportunity_score") or row.get("decision_score") or 0, rpm, row.get("expected_revenue") or 0)

    # Re-cap after uniqueness offset.
    if views > cap:
        views = cap - ((rank * 137) % 1900)
        views = max(floor, views)

    revenue = safe_float(row.get("expected_revenue") or row.get("projected_revenue"))
    if not has_real_revenue:
        # For projected-only ideas, revenue should follow views * RPM, not old inflated defaults.
        rpm = min(max(rpm, 0.75), 3.25)
        revenue = round((views / 1000) * rpm, 2)

    row["expected_views"] = int(views)
    row["projected_views"] = int(views)
    row["expected_rpm"] = round(rpm, 2)
    row["projected_rpm"] = round(rpm, 2)
    row["expected_revenue"] = round(revenue, 2)
    row["projected_revenue"] = round(revenue, 2)

    if _cv_is_random_database_player(row):
        row["avoid_shuffle"] = True

    return row


_cv_pre_realistic_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv_pre_realistic_build_channel_brain_recommendations(videos)

    data_health = data.get("data_health") or {}
    channel_avg_views = safe_int(data_health.get("channel_average_views_used_for_projections")) or 25000
    channel_rpm = safe_float(data_health.get("channel_average_rpm_used_for_projections") or data_health.get("manual_channel_rpm") or get_best_channel_rpm() or 1.35)

    # Clean/cap shuffle and reduce random database-only players.
    raw_shuffle = data.get("shuffle_ideas") or []
    cleaned_shuffle = []

    for index, item in enumerate(raw_shuffle):
        fixed = _cv_realistic_projection_cap(item, index, channel_avg_views, channel_rpm)
        if fixed.get("avoid_shuffle"):
            continue
        cleaned_shuffle.append(fixed)

    # Sort shuffle with real/channel/custom priority first, then database.
    def shuffle_sort_key(item):
        name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or "")
        source = normalize(item.get("source") or "")
        real = 1 if safe_float(item.get("total_revenue") or item.get("synced_revenue")) > 0 else 0
        curated = 1 if name in _CV_CURATED_PRIORITY_NAMES else 0
        database_penalty = -1 if "player database" in source else 0
        return (
            real,
            curated,
            database_penalty,
            safe_float(item.get("expected_revenue") or item.get("projected_revenue")),
            safe_int(item.get("expected_views") or item.get("projected_views"))
        )

    cleaned_shuffle = sorted(cleaned_shuffle, key=shuffle_sort_key, reverse=True)

    # Upload Next: keep real winners, then curated, then strongest remaining only.
    raw_upload = data.get("upload_next") or []
    combined = raw_upload + cleaned_shuffle

    upload = []
    seen = set()

    for index, item in enumerate(combined):
        fixed = _cv_realistic_projection_cap(item, index, channel_avg_views, channel_rpm)
        if fixed.get("avoid_shuffle"):
            continue

        name = normalize(fixed.get("player") or fixed.get("player_name") or fixed.get("topic") or "")
        if not name or name in seen:
            continue

        # Do not let pure random database projections appear before better names.
        source = normalize(fixed.get("source") or "")
        real = safe_float(fixed.get("total_revenue") or fixed.get("synced_revenue")) > 0
        curated = name in _CV_CURATED_PRIORITY_NAMES
        if not real and not curated and "player database" in source and len(upload) < 12:
            continue

        seen.add(name)
        upload.append(fixed)

        if len(upload) >= 15:
            break

    # If still below 15, fill with best remaining non-random candidates.
    if len(upload) < 15:
        for index, item in enumerate(cleaned_shuffle):
            fixed = _cv_realistic_projection_cap(item, index + len(upload), channel_avg_views, channel_rpm)
            name = normalize(fixed.get("player") or fixed.get("player_name") or fixed.get("topic") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            upload.append(fixed)
            if len(upload) >= 15:
                break

    # Final uniqueness pass.
    data["shuffle_ideas"] = _cv_make_unique_numbers(cleaned_shuffle[:700])
    data["upload_next"] = _cv_make_unique_numbers(upload[:15])
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else data.get("best_next_upload")

    if data.get("best_next_upload"):
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."

    data["version"] = "2.8-realistic-projections-less-random"
    data.setdefault("money_notes", [])
    data["money_notes"] = [
        "Projected-only ideas are capped to realistic channel ranges.",
        "Random database-only players are reduced in Shuffle Idea.",
        "Real synced channel revenue players and curated idea-bank names are prioritized.",
        "Projected views stay unique without inflating into unrealistic 400k+ estimates."
    ]

    return data


# =========================================================
# FINAL STRICT CHANNEL-REALISTIC STRATEGY FIX 2.9
# This removes random Player Database names from Best Next Upload / Shuffle.
# Strategy Center now uses:
# 1) real synced channel players
# 2) your curated custom idea bank names only
# 3) no random database-only players like Zendon Hamilton / Will Barton / Tyler Hall
# Projections are capped to realistic ranges from your own channel data.
# =========================================================

_CV_STRICT_CURATED_NAMES = {
    "mason plumlee",
    "allen iverson",
    "magic johnson",
    "larry bird",
    "wilt chamberlain",
    "michael jordan",
    "kobe bryant",
    "pete maravich",
    "vince carter",
    "stephen curry",
    "lebron james",
    "kareem abdul jabbar",
    "hakeem olajuwon",
    "nikola jokic",
    "steve nash",
    "jason williams",
    "shaquille oneal",
    "shaquille o neal",
    "dominique wilkins",
    "david robinson",
    "bill russell",
    "tim duncan",
    "reggie miller",
    "ray allen",
    "damian lillard",
    "chris paul",
    "blake griffin",
    "derrick rose",
    "nate robinson",
    "ja morant",
    "russell westbrook",
    "kyrie irving",
    "george gervin",
    "connie hawkins",
    "david thompson",
    "earl monroe",
    "walt frazier",
    "bernard king",
    "elvin hayes",
    "bob mcadoo",
    "clyde drexler",
    "shawn kemp",
    "gary payton",
    "john stockton",
    "manu ginobili",
    "pau gasol",
    "yao ming",
    "dikembe mutombo",
    "dwight howard",
    "tracy mcgrady",
    "kevin durant",
    "carmelo anthony",
    "jerry west",
    "grant hill",
    "victor wembanyama",
    "charles barkley",
    "julius erving",
    "jason kidd",
    "patrick ewing",
    "paul pierce",
    "dennis rodman",
    "muggsy bogues",
    "mugsy bogues",
    "gilbert arenas",
}

_CV_STRICT_ALLOWED_SOURCES = {
    "custom idea bank",
    "youtube analytics api revenue tracker",
    "youtube analytics api or zero",
    "revenue tracker",
    "synced channel",
    "real synced",
}


def _cv_strict_has_real_channel_money(item):
    return (
        safe_float(item.get("total_revenue")) > 0
        or safe_float(item.get("synced_revenue")) > 0
        or safe_float(item.get("average_revenue")) > 0
        or safe_float(item.get("best_format_total_revenue")) > 0
    )


def _cv_strict_is_curated(item):
    name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")
    return name in _CV_STRICT_CURATED_NAMES


def _cv_strict_keep_item(item):
    if not item:
        return False

    source = normalize(item.get("source") or "")
    reason = normalize(item.get("reason") or "")
    name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")

    if not name or name == "unknown":
        return False

    # Always keep real channel winners.
    if _cv_strict_has_real_channel_money(item):
        return True

    # Keep your hand-picked idea-bank names.
    if _cv_strict_is_curated(item):
        return True

    # Block pure Player Database / Idea Lab filler from Strategy Center shuffle.
    if "player database" in source or "player database" in reason or "idea lab/player database" in reason:
        return False

    # Block anything that is not from a trusted source unless curated.
    if source and source not in _CV_STRICT_ALLOWED_SOURCES and not _cv_strict_is_curated(item):
        return False

    return False


def _cv_strict_cap_projection(item, rank=0, channel_avg_views=25000, channel_rpm=1.35):
    row = dict(item or {})
    name = row.get("player") or row.get("player_name") or row.get("topic") or row.get("name") or "Unknown"
    is_real = _cv_strict_has_real_channel_money(row)
    is_curated = _cv_strict_is_curated(row)

    rpm = safe_float(row.get("expected_rpm") or row.get("projected_rpm") or row.get("average_rpm") or channel_rpm or 1.35)
    rpm = max(0.75, min(rpm, 3.75))

    views = safe_int(row.get("expected_views") or row.get("projected_views") or row.get("average_views") or row.get("views"))
    revenue = safe_float(row.get("expected_revenue") or row.get("projected_revenue") or row.get("total_revenue") or row.get("average_revenue"))

    if is_real:
        # For real channel winners, use actual average/best views but avoid fake 300k+ projections.
        cap = max(25000, min(140000, int(channel_avg_views * 2.35)))
        floor = 5000
        if views <= 0:
            views = safe_int(row.get("average_views") or channel_avg_views)
        if revenue <= 0:
            revenue = safe_float(row.get("total_revenue") or row.get("average_revenue") or ((views / 1000) * rpm))
    elif is_curated:
        # Hand-picked idea bank: realistic high-upside, not random 400k.
        cap = max(18000, min(75000, int(channel_avg_views * 1.35)))
        floor = 4500
        if views <= 0 or views > cap:
            views = int(min(cap, max(floor, channel_avg_views * 0.85)))
        revenue = (views / 1000) * rpm
    else:
        cap = 0
        floor = 0
        views = 0
        revenue = 0

    if cap and views > cap:
        views = cap - ((rank * 173) % 2400)

    if views < floor:
        views = floor + ((rank * 149) % 1800)

    # unique but still capped
    views = _cv_unique_views(views, name, rank, row.get("opportunity_score") or 0, rpm, revenue)
    if cap and views > cap:
        views = cap - ((rank * 131) % 2100)
    if floor and views < floor:
        views = floor + ((rank * 97) % 1200)

    if not is_real:
        revenue = (views / 1000) * rpm

    row["expected_views"] = int(views)
    row["projected_views"] = int(views)
    row["expected_rpm"] = round(rpm, 2)
    row["projected_rpm"] = round(rpm, 2)
    row["expected_revenue"] = round(revenue, 2)
    row["projected_revenue"] = round(revenue, 2)
    row["format"] = _cv_clean_strategy_format(row.get("format") or row.get("content_type") or "Top 10 Plays")
    row["content_type"] = row["format"]
    row["reason"] = (
        "Real synced YouTube API revenue signal for this player."
        if is_real
        else "Curated idea bank pick projected from your current channel trends."
    )

    return row


_cv_strict_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv_strict_previous_build_channel_brain_recommendations(videos)
    data_health = data.get("data_health") or {}

    channel_avg_views = safe_int(data_health.get("channel_average_views_used_for_projections")) or 25000
    channel_rpm = safe_float(data_health.get("channel_average_rpm_used_for_projections") or data_health.get("manual_channel_rpm") or get_best_channel_rpm() or 1.35)

    # Strictly keep only real channel players + curated idea-bank players.
    candidates = []
    for item in (data.get("upload_next") or []) + (data.get("shuffle_ideas") or []):
        if not _cv_strict_keep_item(item):
            continue
        candidates.append(item)

    # Sort real synced winners before curated projections.
    def strict_sort(item):
        real = 1 if _cv_strict_has_real_channel_money(item) else 0
        curated = 1 if _cv_strict_is_curated(item) else 0
        return (
            real,
            safe_float(item.get("total_revenue") or item.get("synced_revenue") or item.get("average_revenue")),
            curated,
            safe_float(item.get("expected_revenue") or item.get("projected_revenue")),
            safe_int(item.get("expected_views") or item.get("projected_views"))
        )

    candidates = sorted(candidates, key=strict_sort, reverse=True)

    # Build Upload Next: 15 unique names from real + curated only.
    upload = []
    seen_names = set()

    for index, item in enumerate(candidates):
        name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")
        if not name or name in seen_names:
            continue

        fixed = _cv_strict_cap_projection(item, len(upload), channel_avg_views, channel_rpm)
        if safe_int(fixed.get("expected_views")) <= 0:
            continue

        seen_names.add(name)
        upload.append(fixed)

        if len(upload) >= 15:
            break

    # Build shuffle: allow same player with different formats, but no random database.
    shuffle = []
    seen_keys = set()

    for index, item in enumerate(candidates):
        fixed = _cv_strict_cap_projection(item, len(shuffle), channel_avg_views, channel_rpm)
        name = normalize(fixed.get("player") or fixed.get("player_name") or fixed.get("topic") or "")
        fmt = normalize(fixed.get("format") or fixed.get("content_type") or "")
        key = f"{name}|{fmt}"

        if not name or key in seen_keys:
            continue

        seen_keys.add(key)
        shuffle.append(fixed)

        if len(shuffle) >= 500:
            break

    data["upload_next"] = _cv_make_unique_numbers(upload[:15])
    data["shuffle_ideas"] = _cv_make_unique_numbers(shuffle)
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else None

    if data["best_next_upload"]:
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."
    else:
        data["today_focus"] = "Sync more revenue data or add more curated ideas."
        data["headline"] = "No safe strategy recommendation yet."

    data["version"] = "2.9-strict-real-channel-and-curated-only"
    data["money_notes"] = [
        "Strategy Center blocks random database-only players.",
        "Upload Next uses real synced channel winners first, then curated idea-bank names only.",
        "Projected-only suggestions are capped to realistic channel ranges.",
        "No 300k-500k projections unless the player is actually backed by your synced channel data."
    ]

    return data


# =========================================================
# FINAL FRONTEND-SAFE STRICT FILTER 3.0
# Blocks plain Idea Lab top picks from Strategy Center too.
# Strategy Center is now only real synced channel winners + hand-curated idea bank.
# =========================================================

_cv3_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv3_previous_build_channel_brain_recommendations(videos)

    def keep(row):
        if not row:
            return False

        name = normalize(row.get("player") or row.get("player_name") or row.get("topic") or row.get("name") or "")
        source = normalize(row.get("source") or "")
        reason = normalize(row.get("reason") or "")
        real = _cv_strict_has_real_channel_money(row)
        curated = name in _CV_STRICT_CURATED_NAMES

        if real or curated:
            return True

        # Plain Idea Lab / Player Database should not appear in Strategy Center.
        if "idea lab" in source or "idea lab" in reason or "player database" in source or "player database" in reason:
            return False

        return False

    upload = [x for x in (data.get("upload_next") or []) if keep(x)]
    shuffle = [x for x in (data.get("shuffle_ideas") or []) if keep(x)]

    # Refill upload to 15 from shuffle, but still strict only.
    seen = {normalize(x.get("player") or x.get("player_name") or x.get("topic") or "") for x in upload}
    for item in shuffle:
        name = normalize(item.get("player") or item.get("player_name") or item.get("topic") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        upload.append(item)
        if len(upload) >= 15:
            break

    data["upload_next"] = _cv_make_unique_numbers(upload[:15])
    data["shuffle_ideas"] = _cv_make_unique_numbers(shuffle[:500])
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else None

    if data["best_next_upload"]:
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."
    else:
        data["today_focus"] = "Sync more real revenue data or add more curated ideas."
        data["headline"] = "No safe strategy recommendation yet."

    data["version"] = "3.0-final-real-channel-curated-only-no-idea-lab-fillers"
    data["money_notes"] = [
        "Strategy Center no longer uses plain Idea Lab top picks.",
        "Shuffle Idea only uses real synced channel winners and your curated idea-bank names.",
        "Random players like Doug Collins, Billy Donovan, Charlie Scott, and similar database-only names are blocked.",
        "Projections are capped to realistic channel ranges."
    ]

    return data


# =========================================================
# FINAL HUGE APPROVED SHUFFLE POOL 4.0
# Large Strategy Center pool with hundreds of realistic suggestions.
# Uses real synced channel data first, then approved high-upside NBA names only.
# Allowed formats only:
# Dunks, Poster Dunks, Blocks, Assists, Clutch Shots, Game Winners,
# 3-Pointers, Playoff Moments, Finals Plays.
# =========================================================

_CV_ALLOWED_STRATEGY_FORMATS = [
    "Top 10 Dunks",
    "Top 10 Poster Dunks",
    "Top 10 Blocks",
    "Top 10 Assists",
    "Top 10 Clutch Shots",
    "Top 10 Game Winners",
    "Top 10 3-Pointers",
    "Top 10 Playoff Moments",
    "Top 10 Finals Plays",
]

_CV_APPROVED_BIG_SHUFFLE_PLAYERS = ['Michael Jordan', 'Julius Erving', 'Kareem Abdul-Jabbar', 'Wilt Chamberlain', 'Larry Bird', 'Magic Johnson', 'Kobe Bryant', 'LeBron James', 'Stephen Curry', "Shaquille O'Neal", 'Hakeem Olajuwon', 'Charles Barkley', 'David Robinson', 'Grant Hill', 'Nikola Jokic', 'Reggie Miller', 'Kevin Durant', 'Vince Carter', 'Tracy McGrady', 'Allen Iverson', 'Luka Doncic', 'Giannis Antetokounmpo', 'Ja Morant', 'Derrick Rose', 'Damian Lillard', 'Russell Westbrook', 'Kyrie Irving', 'Anthony Edwards', 'Victor Wembanyama', 'Elgin Baylor', 'Jerry West', 'Oscar Robertson', 'Pete Maravich', 'George Gervin', 'Connie Hawkins', 'Earl Monroe', 'Walt Frazier', 'Bernard King', 'Bob McAdoo', 'Elvin Hayes', 'David Thompson', 'Bill Russell', 'Clyde Drexler', 'Dominique Wilkins', 'Patrick Ewing', 'Karl Malone', 'John Stockton', 'Chris Mullin', 'Kevin McHale', 'Robert Parish', 'Moses Malone', 'Alex English', 'Adrian Dantley', 'Detlef Schrempf', 'Mark Aguirre', 'Isiah Thomas', 'Penny Hardaway', 'Jason Kidd', 'Steve Nash', 'Chris Paul', 'Gary Payton', 'Shawn Kemp', 'Dikembe Mutombo', 'Yao Ming', 'Dwight Howard', 'Kevin Garnett', 'Paul Pierce', 'Ray Allen', 'Carmelo Anthony', "Amar'e Stoudemire", 'Joe Johnson', 'Deron Williams', 'Manu Ginobili', 'Tony Parker', 'Pau Gasol', 'Rasheed Wallace', 'Ben Wallace', 'Baron Davis', 'Gilbert Arenas', 'Michael Redd', 'Richard Hamilton', 'Dwyane Wade', 'Dirk Nowitzki', 'Chris Webber', 'Alonzo Mourning', 'Mark Price', 'Kevin Johnson', 'Tim Hardaway', 'Mitch Richmond', 'Glen Rice', 'Antoine Walker', 'Stephon Marbury', 'Steve Francis', 'Jayson Tatum', 'Jaylen Brown', 'Devin Booker', 'Donovan Mitchell', 'Trae Young', 'Zion Williamson', 'LaMelo Ball', 'Paolo Banchero', 'Chet Holmgren', 'Jamal Murray', 'Shai Gilgeous-Alexander', 'Tyrese Haliburton', "De'Aaron Fox", 'Jalen Brunson', 'Evan Mobley', 'Cade Cunningham', 'Franz Wagner', 'Scottie Barnes', 'Alperen Sengun', 'Amen Thompson', 'Tyrese Maxey', 'Jaren Jackson Jr.', 'Bam Adebayo', 'Brandon Ingram', 'Zach LaVine', 'Jalen Green', 'Jaime Jaquez Jr.', 'Cam Thomas', 'Ausar Thompson', 'Scoot Henderson', 'Jalen Williams', 'Mikal Bridges', 'Desmond Bane', 'Tyler Herro', 'Darius Garland', 'Anfernee Simons', 'Jason Williams', 'Jamal Crawford', 'Lou Williams', 'Nate Robinson', 'Muggsy Bogues', 'Earl Boykins', 'Ricky Rubio', 'Rajon Rondo', 'Andre Iguodala', 'Shawn Marion', 'Gerald Green', 'J.R. Smith', 'Nick Young', 'Lance Stephenson', 'Corey Brewer', 'Michael Beasley', 'Zach Randolph', 'Al Jefferson', 'Monta Ellis', 'Larry Johnson', 'Antonio McDyess', 'Larry Hughes', 'Jason Richardson', 'Quentin Richardson', 'Stephen Jackson', 'Ron Artest', 'Latrell Sprewell', 'Robert Horry', 'Derek Fisher', 'Mike Bibby', 'Nick Van Exel', 'Jalen Rose', 'Antawn Jamison', 'Josh Smith', 'Josh Howard', 'Kenyon Martin', 'Stromile Swift', 'Darius Miles', 'Rudy Gay', 'Andre Miller', 'Juwan Howard', 'Larry Nance', 'Larry Nance Jr.', 'Aaron Gordon', 'DeMar DeRozan', 'Mark Eaton', 'Manute Bol', 'Shawn Bradley', 'Klay Thompson', 'Peja Stojakovic', 'Kyle Korver', 'Steve Kerr', 'JJ Redick', 'Buddy Hield', 'Duncan Robinson', 'Mike Miller', 'Danny Green', 'Jason Terry', 'Chauncey Billups', 'Sam Cassell', 'Brandon Roy', 'Michael Finley', 'Jerry Stackhouse', 'Glenn Robinson', 'Rashard Lewis', 'Hedo Turkoglu', 'Andrei Kirilenko', 'Anderson Varejao', 'Tyson Chandler', 'Marcus Camby', "Jermaine O'Neal", 'Carlos Boozer', 'David Lee', 'Lamar Odom', 'Andrew Bynum', 'Andrew Wiggins', 'Khris Middleton', 'Jrue Holiday', 'Brook Lopez', 'Marc Gasol', 'Mike Conley', 'Goran Dragic', 'Kemba Walker', 'Isaiah Thomas', 'John Wall', 'Bradley Beal', 'CJ McCollum', 'Pascal Siakam', 'Fred VanVleet', 'Kyle Lowry', 'DeMarcus Cousins', 'Blake Griffin', 'DeAndre Jordan', 'Serge Ibaka', 'Luol Deng', 'Joakim Noah', 'Zydrunas Ilgauskas', 'Derrick Coleman', 'Shareef Abdur-Rahim', 'Vlade Divac', 'Arvydas Sabonis', 'Toni Kukoc', 'Drazen Petrovic', 'Dino Radja', 'Sarunas Marciulionis', 'Dale Ellis', 'Dell Curry', 'Byron Scott', 'James Worthy', 'AC Green', 'Horace Grant', 'Dennis Rodman', 'Scottie Pippen', 'Joe Dumars', 'Bill Laimbeer', 'Mark Jackson', 'Kenny Anderson', 'Terrell Brandon', 'Kendall Gill', 'Damon Stoudamire', 'Rod Strickland', 'Rik Smits', 'Mookie Blaylock', 'Steve Smith', 'Allan Houston', 'Keith Van Horn', 'Sam Perkins', 'Cedric Ceballos', 'Tom Chambers', 'Xavier McDaniel', 'Fat Lever', 'Kiki Vandeweghe', 'Walter Davis', 'World B. Free', 'Marques Johnson', 'Sidney Moncrief', 'Jack Sikma', 'Artis Gilmore', 'Bob Lanier', 'Nate Thurmond', 'Wes Unseld', 'Dave Cowens', 'Bob Cousy', 'Sam Jones', 'Hal Greer', 'Dave Bing', 'Tiny Archibald', 'Rick Barry', 'Billy Cunningham', 'Dave DeBusschere', 'Willis Reed', 'Jo Jo White', 'Gail Goodrich', 'Spencer Haywood', 'Maurice Cheeks', 'Bobby Jones', 'Dennis Johnson', 'Sidney Wicks', 'Ralph Sampson', 'Rolando Blackman', 'Jeff Hornacek', 'Dan Majerle', 'Mahmoud Abdul-Rauf', 'Reggie Lewis', 'Len Bias']

_CV_APPROVED_BIG_SHUFFLE_SET = {normalize(name) for name in _CV_APPROVED_BIG_SHUFFLE_PLAYERS}

_CV_FORMAT_SPECIALISTS = {
    "dunks": {
        "julius erving","michael jordan","kobe bryant","lebron james","vince carter","dominique wilkins","shawn kemp","blake griffin","ja morant","derrick rose","russell westbrook","anthony edwards","zach lavine","gerald green","jason richardson","clyde drexler","tracy mcgrady","dwight howard","shaquille oneal","shaquille o neal","david thompson","aaron gordon","larry nance","larry nance jr","demar derozan","giannis antetokounmpo","zion williamson","kenyon martin","stromile swift","darius miles","rudy gay"
    },
    "poster": {
        "julius erving","michael jordan","kobe bryant","lebron james","vince carter","dominique wilkins","shawn kemp","blake griffin","ja morant","anthony edwards","shaquille oneal","shaquille o neal","charles barkley","dwight howard","giannis antetokounmpo","zach lavine","gerald green"
    },
    "blocks": {
        "wilt chamberlain","bill russell","hakeem olajuwon","david robinson","dikembe mutombo","dwight howard","tim duncan","ben wallace","alonzo mourning","mark eaton","manute bol","shawn bradley","yao ming","victor wembanyama","evan mobley","chet holmgren","shaquille oneal","shaquille o neal","kareem abdul jabbar","patrick ewing","kevin garnett","serge ibaka","marcus camby","tyson chandler","jermaine oneal"
    },
    "assists": {
        "magic johnson","john stockton","steve nash","jason kidd","chris paul","pete maravich","jason williams","gary payton","rajon rondo","ricky rubio","luka doncic","nikola jokic","tyrese haliburton","trae young","penny hardaway","isiah thomas","lebron james","larry bird","bob cousy","tiny archibald","mark jackson","andre miller","mike conley","tony parker","manu ginobili"
    },
    "three": {
        "stephen curry","ray allen","reggie miller","damian lillard","klay thompson","peja stojakovic","kyle korver","steve kerr","jj redick","buddy hield","devin booker","kevin durant","james harden","larry bird","kyrie irving","michael redd","duncan robinson","mike miller","danny green","jason terry","cj mccollum","donovan mitchell","trae young"
    },
    "clutch": {
        "michael jordan","kobe bryant","larry bird","damian lillard","stephen curry","lebron james","kevin durant","dirk nowitzki","reggie miller","ray allen","paul pierce","carmelo anthony","devin booker","jayson tatum","shai gilgeous alexander","dwyane wade","magic johnson","kyrie irving","chauncey billups","jerry west","luka doncic","nikola jokic"
    },
    "playoff": {
        "michael jordan","kobe bryant","lebron james","magic johnson","larry bird","tim duncan","hakeem olajuwon","kareem abdul jabbar","shaquille oneal","shaquille o neal","stephen curry","kevin durant","nikola jokic","reggie miller","dwyane wade","dirk nowitzki","kawhi leonard","paul pierce","jason kidd","ray allen","vince carter","allen iverson","julius erving","jerry west","bill russell"
    },
    "finals": {
        "michael jordan","kobe bryant","lebron james","magic johnson","larry bird","tim duncan","hakeem olajuwon","kareem abdul jabbar","shaquille oneal","shaquille o neal","stephen curry","kevin durant","nikola jokic","dwyane wade","dirk nowitzki","jerry west","bill russell","julius erving","ray allen","kawhi leonard","giannis antetokounmpo"
    },
}


def _cv4_norm_player_name(value):
    return normalize(value).replace("'", "").replace("’", "").strip()


def _cv4_allowed_formats_for_player(player_name, done_types=None):
    done = {str(x or "").strip() for x in (done_types or set()) if x}
    key = _cv4_norm_player_name(player_name)
    formats = []

    def add(fmt):
        if fmt not in formats and fmt not in done:
            formats.append(fmt)

    if key in _CV_FORMAT_SPECIALISTS["dunks"]:
        add("Top 10 Dunks")
    if key in _CV_FORMAT_SPECIALISTS["poster"]:
        add("Top 10 Poster Dunks")
    if key in _CV_FORMAT_SPECIALISTS["blocks"]:
        add("Top 10 Blocks")
    if key in _CV_FORMAT_SPECIALISTS["assists"]:
        add("Top 10 Assists")
    if key in _CV_FORMAT_SPECIALISTS["clutch"]:
        add("Top 10 Clutch Shots")
        add("Top 10 Game Winners")
    if key in _CV_FORMAT_SPECIALISTS["three"]:
        add("Top 10 3-Pointers")
    if key in _CV_FORMAT_SPECIALISTS["playoff"]:
        add("Top 10 Playoff Moments")
    if key in _CV_FORMAT_SPECIALISTS["finals"]:
        add("Top 10 Finals Plays")

    # sensible generic fallbacks for approved names only
    if not formats:
        add("Top 10 Clutch Shots")
        add("Top 10 Dunks")
        add("Top 10 Playoff Moments")

    return formats[:6]


def _cv4_tier_for_player(player_name, has_real=False):
    key = _cv4_norm_player_name(player_name)
    if has_real:
        return "real"
    if key in {
        "michael jordan","julius erving","kareem abdul jabbar","wilt chamberlain","larry bird","magic johnson","kobe bryant","lebron james","stephen curry","shaquille oneal","shaquille o neal","hakeem olajuwon","charles barkley","david robinson","grant hill","nikola jokic","reggie miller","kevin durant","vince carter","tracy mcgrady","allen iverson","luka doncic","giannis antetokounmpo","ja morant","derrick rose","damian lillard","russell westbrook","kyrie irving","anthony edwards","victor wembanyama"
    }:
        return "s"
    if key in {
        "elgin baylor","jerry west","oscar robertson","pete maravich","george gervin","connie hawkins","earl monroe","walt frazier","bernard king","bob mcadoo","elvin hayes","david thompson","bill russell","clyde drexler","dominique wilkins","patrick ewing","karl malone","john stockton","chris mullin","kevin mchale","robert parish","moses malone","alex english","adrian dantley","detlef schrempf","penny hardaway","jason kidd","steve nash","chris paul","gary payton","shawn kemp","dikembe mutombo","yao ming","dwight howard","kevin garnett","paul pierce","ray allen","carmelo anthony","manu ginobili","tony parker","pau gasol","dwyane wade","dirk nowitzki","chris webber","alonzo mourning","isiah thomas"
    }:
        return "a"
    if key in {
        "jayson tatum","jaylen brown","devin booker","donovan mitchell","trae young","zion williamson","lamelo ball","paolo banchero","chet holmgren","jamal murray","shai gilgeous alexander","tyrese haliburton","deaaron fox","jalen brunson","evan mobley","cade cunningham","franz wagner","scottie barnes","alperen sengun","amen thompson","tyrese maxey","jalen green","jalen williams"
    }:
        return "modern"
    return "role"


def _cv4_multiplier_for_format(fmt):
    f = normalize(fmt)
    if "poster" in f:
        return 1.08
    if "clutch" in f or "game winner" in f:
        return 1.07
    if "finals" in f:
        return 1.06
    if "playoff" in f:
        return 1.05
    if "dunk" in f:
        return 1.04
    if "3 pointer" in f:
        return 1.03
    if "assist" in f:
        return 0.97
    if "block" in f:
        return 0.95
    return 1.0


def _cv4_specific_int(base, player, fmt, rank, low, high):
    seed = sum((i + 1) * ord(c) for i, c in enumerate(normalize(f"{player} {fmt}")))
    value = int(base + (seed % 3800) + rank * 113)
    if value > high:
        value = high - (seed % 2200) - (rank % 17) * 29
    if value < low:
        value = low + (seed % 1500) + (rank % 13) * 37
    return max(low, min(high, value))


def _cv4_real_money(item):
    return safe_float(item.get("total_revenue") or item.get("synced_revenue") or item.get("average_revenue") or item.get("best_format_total_revenue"))


def _cv4_make_idea(player, fmt, rank, channel_avg_views, channel_rpm, real_item=None, done_types=None):
    real_item = real_item or {}
    has_real = _cv4_real_money(real_item) > 0
    tier = _cv4_tier_for_player(player, has_real)

    if has_real:
        base_views = safe_int(real_item.get("average_views") or real_item.get("expected_views") or real_item.get("projected_views") or channel_avg_views)
        rpm = safe_float(real_item.get("expected_rpm") or real_item.get("projected_rpm") or real_item.get("average_rpm") or channel_rpm or 1.35)
        low, high = 6000, max(30000, min(140000, int(channel_avg_views * 2.35)))
    elif tier == "s":
        base_views = int(channel_avg_views * 1.18)
        rpm = max(channel_rpm, 1.65)
        low, high = 9000, max(25000, min(85000, int(channel_avg_views * 1.65)))
    elif tier == "a":
        base_views = int(channel_avg_views * 0.95)
        rpm = max(channel_rpm * 0.98, 1.35)
        low, high = 7000, max(21000, min(68000, int(channel_avg_views * 1.35)))
    elif tier == "modern":
        base_views = int(channel_avg_views * 0.80)
        rpm = max(channel_rpm * 0.92, 1.20)
        low, high = 5500, max(18000, min(55000, int(channel_avg_views * 1.10)))
    else:
        base_views = int(channel_avg_views * 0.62)
        rpm = max(channel_rpm * 0.88, 1.05)
        low, high = 3500, max(14000, min(39000, int(channel_avg_views * 0.82)))

    rpm = min(max(rpm * _cv4_multiplier_for_format(fmt), 0.75), 3.75)
    views = _cv4_specific_int(base_views, player, fmt, rank, low, high)

    if has_real and fmt == real_item.get("format"):
        revenue = _cv4_real_money(real_item)
    else:
        revenue = round((views / 1000) * rpm, 2)

    return {
        "player": player,
        "player_name": player,
        "topic": player,
        "title": f"{player} {fmt} of Career",
        "format": fmt,
        "content_type": fmt,
        "era": real_item.get("era") or _cv_infer_era(player, {}, ""),
        "expected_views": int(views),
        "projected_views": int(views),
        "expected_revenue": round(revenue, 2),
        "projected_revenue": round(revenue, 2),
        "expected_rpm": round(rpm, 2),
        "projected_rpm": round(rpm, 2),
        "total_revenue": round(_cv4_real_money(real_item), 2),
        "average_views": safe_int(real_item.get("average_views")),
        "average_revenue": safe_float(real_item.get("average_revenue")),
        "average_rpm": safe_float(real_item.get("average_rpm")),
        "source": "Real Channel Data" if has_real else "Approved Expansion Pool",
        "reason": "Real synced YouTube API revenue signal for this player." if has_real else "Approved high-upside player projected from your channel revenue/view trends.",
        "tier": tier,
    }


_cv4_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv4_previous_build_channel_brain_recommendations(videos)
    data_health = data.get("data_health") or {}
    channel_avg_views = safe_int(data_health.get("channel_average_views_used_for_projections")) or 25000
    channel_rpm = safe_float(data_health.get("channel_average_rpm_used_for_projections") or data_health.get("manual_channel_rpm") or get_best_channel_rpm() or 1.35)

    # Find completed formats by player.
    done_by_player = defaultdict(set)
    for video in videos or []:
        player = video.get("player_name") or detect_player(video.get("title", ""))
        fmt = detect_top10_type_from_title(video.get("title", ""))
        if player and fmt:
            done_by_player[normalize(player)].add(fmt)

    # Real channel items from previous pipeline.
    real_by_player = {}
    for item in (data.get("upload_next") or []) + (data.get("shuffle_ideas") or []):
        player = item.get("player") or item.get("player_name") or item.get("topic") or item.get("name")
        if not player:
            continue
        if _cv4_real_money(item) > 0:
            key = normalize(player)
            if key not in real_by_player or _cv4_real_money(item) > _cv4_real_money(real_by_player[key]):
                real_by_player[key] = item

    ideas = []
    rank = 0

    # Real winners first, with smart alternate formats.
    for key, item in sorted(real_by_player.items(), key=lambda pair: _cv4_real_money(pair[1]), reverse=True):
        player = item.get("player") or item.get("player_name") or item.get("topic")
        if not player:
            continue
        formats = _cv4_allowed_formats_for_player(player, done_by_player.get(normalize(player), set()))
        for fmt in formats:
            ideas.append(_cv4_make_idea(player, fmt, rank, channel_avg_views, channel_rpm, item, done_by_player.get(normalize(player), set())))
            rank += 1

    # Approved big expansion pool.
    for player in _CV_APPROVED_BIG_SHUFFLE_PLAYERS:
        key = normalize(player)
        formats = _cv4_allowed_formats_for_player(player, done_by_player.get(key, set()))
        for fmt in formats:
            ideas.append(_cv4_make_idea(player, fmt, rank, channel_avg_views, channel_rpm, real_by_player.get(key), done_by_player.get(key, set())))
            rank += 1

    # De-dupe player + format; keep highest revenue.
    by_key = {}
    for idea in ideas:
        key = f"{normalize(idea.get('player'))}|{normalize(idea.get('format'))}"
        if key not in by_key or safe_float(idea.get("expected_revenue")) > safe_float(by_key[key].get("expected_revenue")):
            by_key[key] = idea

    ideas = list(by_key.values())

    # Unique view/revenue display values.
    used_views = set()
    used_revenue = set()
    final_ideas = []
    for i, idea in enumerate(sorted(ideas, key=lambda x: (
        1 if _cv4_real_money(x) > 0 else 0,
        safe_float(x.get("expected_revenue")),
        safe_int(x.get("expected_views"))
    ), reverse=True)):
        row = dict(idea)
        views = safe_int(row.get("expected_views"))
        while views in used_views:
            views += 137
        used_views.add(views)
        row["expected_views"] = views
        row["projected_views"] = views

        revenue = round(safe_float(row.get("expected_revenue")), 2)
        while revenue in used_revenue:
            revenue = round(revenue + 0.01, 2)
        used_revenue.add(revenue)
        row["expected_revenue"] = revenue
        row["projected_revenue"] = revenue
        final_ideas.append(row)

    upload_seen = set()
    upload_next = []
    for idea in final_ideas:
        key = normalize(idea.get("player"))
        if key in upload_seen:
            continue
        upload_seen.add(key)
        upload_next.append(idea)
        if len(upload_next) >= 15:
            break

    data["upload_next"] = upload_next
    data["shuffle_ideas"] = final_ideas[:1000]
    data["best_next_upload"] = upload_next[0] if upload_next else None

    if data["best_next_upload"]:
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."
    else:
        data["today_focus"] = "Sync more revenue data."
        data["headline"] = "No safe strategy recommendation yet."

    data["version"] = "4.0-huge-approved-shuffle-pool"
    data["money_notes"] = [
        "Shuffle has a large approved pool, not random database filler.",
        "Only approved formats are used: dunks, poster dunks, blocks, assists, clutch shots, game winners, 3-pointers, playoff moments, finals plays.",
        "Real channel revenue players are weighted first.",
        "Approved stars, legends, modern names, and role-player favorites fill the rest with capped realistic projections."
    ]

    return data


# =========================================================
# FINAL FORMAT ORDER RULE 4.1
# Rule:
# - If the player has never had a Top 10 on the channel, suggest ONLY Top 10 Plays.
# - If the player has Top 10 videos but not Top 10 Plays, suggest ONLY Top 10 Plays.
# - Only after Top 10 Plays exists do we suggest Dunks, Blocks, Assists,
#   Clutch Shots, Game Winners, Poster Dunks, 3-Pointers, Playoff Moments, Finals Plays.
# =========================================================

_CV_ALLOWED_STRATEGY_FORMATS = [
    "Top 10 Plays",
    "Top 10 Dunks",
    "Top 10 Poster Dunks",
    "Top 10 Blocks",
    "Top 10 Assists",
    "Top 10 Clutch Shots",
    "Top 10 Game Winners",
    "Top 10 3-Pointers",
    "Top 10 Playoff Moments",
    "Top 10 Finals Plays",
]


def _cv4_allowed_formats_for_player(player_name, done_types=None):
    done = {str(x or "").strip() for x in (done_types or set()) if x}
    key = _cv4_norm_player_name(player_name)

    # Brand-new player OR player without Top 10 Plays:
    # only suggest the main "Top 10 Plays" first.
    if "Top 10 Plays" not in done:
        return ["Top 10 Plays"]

    formats = []

    def add(fmt):
        if fmt not in formats and fmt not in done:
            formats.append(fmt)

    # Once Top 10 Plays exists, then allow smart alternate formats.
    if key in _CV_FORMAT_SPECIALISTS["dunks"]:
        add("Top 10 Dunks")
    if key in _CV_FORMAT_SPECIALISTS["poster"]:
        add("Top 10 Poster Dunks")
    if key in _CV_FORMAT_SPECIALISTS["blocks"]:
        add("Top 10 Blocks")
    if key in _CV_FORMAT_SPECIALISTS["assists"]:
        add("Top 10 Assists")
    if key in _CV_FORMAT_SPECIALISTS["clutch"]:
        add("Top 10 Clutch Shots")
        add("Top 10 Game Winners")
    if key in _CV_FORMAT_SPECIALISTS["three"]:
        add("Top 10 3-Pointers")
    if key in _CV_FORMAT_SPECIALISTS["playoff"]:
        add("Top 10 Playoff Moments")
    if key in _CV_FORMAT_SPECIALISTS["finals"]:
        add("Top 10 Finals Plays")

    # If Top 10 Plays exists but no specialist format is clear, use safe money formats.
    if not formats:
        add("Top 10 Clutch Shots")
        add("Top 10 Playoff Moments")
        add("Top 10 Dunks")

    return formats[:6]


# =========================================================
# FINAL FORMAT LOCK 4.2
# User rule:
# - If player does NOT already have Top 10 Plays on this channel:
#   ONLY suggest Top 10 Plays.
# - If player already has Top 10 Plays:
#   then unlock other allowed Top 10 formats.
# - Top 10 Poster Dunks is deleted completely and becomes Top 10 Dunks.
# =========================================================

_CV_FINAL_ALLOWED_ALT_FORMATS = [
    "Top 10 Dunks",
    "Top 10 Blocks",
    "Top 10 Assists",
    "Top 10 Clutch Shots",
    "Top 10 Game Winners",
    "Top 10 3-Pointers",
    "Top 10 Playoff Moments",
    "Top 10 Finals Plays",
]


def _cv_final_clean_format(value):
    text = str(value or "Top 10 Plays").strip()
    text = text.replace("Top 10 Top 10", "Top 10")
    text = text.replace("Poster Dunks", "Dunks")
    text = text.replace("Poster Dunk", "Dunk")
    text = text.replace("Handles", "Crossovers")
    text = text.replace("Top 10 Shots", "Top 10 Clutch Shots")
    text = text.replace("Top 10 Clutch Plays", "Top 10 Clutch Shots")
    text = text.replace("Career Highlights", "Plays")
    text = text.replace("History Countdown", "Top 10 Plays")

    low = normalize(text)

    if "playoff" in low:
        return "Top 10 Playoff Moments"
    if "finals" in low:
        return "Top 10 Finals Plays"
    if "game winner" in low or "game winners" in low:
        return "Top 10 Game Winners"
    if "clutch" in low:
        return "Top 10 Clutch Shots"
    if "3 pointer" in low or "3 pointers" in low or "three pointer" in low or "three pointers" in low:
        return "Top 10 3-Pointers"
    if "assist" in low or "pass" in low:
        return "Top 10 Assists"
    if "block" in low:
        return "Top 10 Blocks"
    if "dunk" in low or "poster" in low:
        return "Top 10 Dunks"
    if "play" in low:
        return "Top 10 Plays"

    return "Top 10 Plays"


def _cv_final_format_order_for_player(player_name):
    key = _cv4_norm_player_name(player_name) if "_cv4_norm_player_name" in globals() else normalize(player_name)
    ordered = []

    def add(fmt):
        fmt = _cv_final_clean_format(fmt)
        if fmt != "Top 10 Poster Dunks" and fmt not in ordered:
            ordered.append(fmt)

    # Strongest YouTube formats first, but only after Top 10 Plays already exists.
    if "_CV_FORMAT_SPECIALISTS" in globals():
        if key in _CV_FORMAT_SPECIALISTS.get("dunks", set()) or key in _CV_FORMAT_SPECIALISTS.get("poster", set()):
            add("Top 10 Dunks")
        if key in _CV_FORMAT_SPECIALISTS.get("clutch", set()):
            add("Top 10 Clutch Shots")
            add("Top 10 Game Winners")
        if key in _CV_FORMAT_SPECIALISTS.get("assists", set()):
            add("Top 10 Assists")
        if key in _CV_FORMAT_SPECIALISTS.get("blocks", set()):
            add("Top 10 Blocks")
        if key in _CV_FORMAT_SPECIALISTS.get("three", set()):
            add("Top 10 3-Pointers")
        if key in _CV_FORMAT_SPECIALISTS.get("playoff", set()):
            add("Top 10 Playoff Moments")
        if key in _CV_FORMAT_SPECIALISTS.get("finals", set()):
            add("Top 10 Finals Plays")

    # General fallback for players who already have Top 10 Plays.
    add("Top 10 Dunks")
    add("Top 10 Clutch Shots")
    add("Top 10 Game Winners")
    add("Top 10 Playoff Moments")
    add("Top 10 Finals Plays")

    return ordered


def _cv_final_done_types_by_player(videos):
    done = defaultdict(set)

    for video in videos or []:
        title = video.get("title", "")
        player = video.get("player_name") or detect_player(title)

        if not player or player == "Unknown":
            continue

        top10_type = detect_top10_type_from_title(title)

        if top10_type:
            done[normalize(player)].add(_cv_final_clean_format(top10_type))

    return done


def _cv_final_choose_format(player_name, current_format, done_types):
    done = {str(x or "").strip() for x in (done_types or set()) if x}

    # This is the main rule:
    # no Top 10 Plays done yet = only Top 10 Plays.
    if "Top 10 Plays" not in done:
        return "Top 10 Plays"

    current = _cv_final_clean_format(current_format)

    # Poster Dunks is banned.
    if current == "Top 10 Poster Dunks":
        current = "Top 10 Dunks"

    # If current is a valid alt and not already done, keep it.
    if current in _CV_FINAL_ALLOWED_ALT_FORMATS and current not in done:
        return current

    # Otherwise pick the best smart alt not already done.
    for fmt in _cv_final_format_order_for_player(player_name):
        fmt = _cv_final_clean_format(fmt)
        if fmt in _CV_FINAL_ALLOWED_ALT_FORMATS and fmt not in done:
            return fmt

    # If every alt is done, cycle back to the safest format.
    return "Top 10 Clutch Shots"


def _cv_final_fix_item_format(item, videos, index=0):
    row = dict(item or {})
    player = row.get("player") or row.get("player_name") or row.get("topic") or row.get("name") or "Unknown"
    done_map = _cv_final_done_types_by_player(videos)
    done_types = done_map.get(normalize(player), set())

    fmt = _cv_final_choose_format(player, row.get("format") or row.get("content_type") or "Top 10 Plays", done_types)

    row["player"] = player
    row["player_name"] = player
    row["topic"] = player
    row["format"] = fmt
    row["content_type"] = fmt
    row["title"] = f"{player} {fmt} of Career"

    # Recalculate projected-only revenue if format changed; keep real synced totals intact.
    real_money = safe_float(row.get("total_revenue") or row.get("synced_revenue") or row.get("average_revenue"))
    views = safe_int(row.get("expected_views") or row.get("projected_views") or row.get("average_views") or 0)
    rpm = safe_float(row.get("expected_rpm") or row.get("projected_rpm") or row.get("average_rpm") or get_best_channel_rpm() or 1.35)

    if views <= 0:
        views = 8000 + (index * 137)

    # Tiny multiplier for format differences, still realistic.
    mult = 1.0
    low = normalize(fmt)
    if "game winner" in low or "clutch" in low:
        mult = 1.06
    elif "finals" in low or "playoff" in low:
        mult = 1.04
    elif "dunk" in low:
        mult = 1.03
    elif "3 pointer" in low:
        mult = 1.02
    elif "assist" in low or "block" in low:
        mult = 0.96

    rpm = round(max(0.75, min(3.75, rpm * mult)), 2)

    if real_money <= 0:
        revenue = round((views / 1000) * rpm, 2)
        row["expected_revenue"] = revenue
        row["projected_revenue"] = revenue

    row["expected_rpm"] = rpm
    row["projected_rpm"] = rpm
    row["expected_views"] = views
    row["projected_views"] = views

    return row


_cv_final_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv_final_previous_build_channel_brain_recommendations(videos)

    fixed_shuffle = []
    seen_shuffle = set()

    for index, item in enumerate(data.get("shuffle_ideas") or []):
        row = _cv_final_fix_item_format(item, videos, index)
        key = f"{normalize(row.get('player'))}|{normalize(row.get('format'))}"

        if key in seen_shuffle:
            continue

        seen_shuffle.add(key)
        fixed_shuffle.append(row)

    fixed_upload = []
    seen_upload_players = set()

    # Upload Next should still show 15 different players.
    for index, item in enumerate((data.get("upload_next") or []) + fixed_shuffle):
        row = _cv_final_fix_item_format(item, videos, index)
        player_key = normalize(row.get("player"))

        if not player_key or player_key in seen_upload_players:
            continue

        seen_upload_players.add(player_key)
        fixed_upload.append(row)

        if len(fixed_upload) >= 15:
            break

    data["shuffle_ideas"] = _cv_make_unique_numbers(fixed_shuffle[:1000]) if "_cv_make_unique_numbers" in globals() else fixed_shuffle[:1000]
    data["upload_next"] = _cv_make_unique_numbers(fixed_upload[:15]) if "_cv_make_unique_numbers" in globals() else fixed_upload[:15]
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else None

    if data["best_next_upload"]:
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} in {best.get('format')} format."

    data["version"] = "4.2-top10-plays-first-no-poster-dunks"
    data["money_notes"] = [
        "If a player has no Top 10 Plays on the channel, Strategy Center only suggests Top 10 Plays.",
        "Specialty formats unlock only after Top 10 Plays exists for that player.",
        "Top 10 Poster Dunks was removed and converted to Top 10 Dunks.",
        "Allowed formats are Top 10 Plays, Dunks, Blocks, Assists, Clutch Shots, Game Winners, 3-Pointers, Playoff Moments, and Finals Plays."
    ]

    return data


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


_cv5_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def build_channel_brain_recommendations(videos):
    data = _cv5_previous_build_channel_brain_recommendations(videos)

    def fix_row(row):
        if not row:
            return row

        fixed = dict(row)
        player = fixed.get("player") or fixed.get("player_name") or fixed.get("topic") or fixed.get("name")

        if player:
            fixed["era"] = _cv_career_years_for_player(player)
            fixed["career_years"] = fixed["era"]

        return fixed

    data["upload_next"] = [fix_row(x) for x in data.get("upload_next", [])]
    data["shuffle_ideas"] = [fix_row(x) for x in data.get("shuffle_ideas", [])]
    data["avoid_next"] = [fix_row(x) for x in data.get("avoid_next", [])]
    data["best_next_upload"] = fix_row(data.get("best_next_upload")) if data.get("best_next_upload") else None

    data["version"] = "5.0-career-years-not-all-time"
    data.setdefault("money_notes", [])
    data["money_notes"] = [
        *data["money_notes"],
        "Era field now shows player career years instead of vague All-Time labels."
    ]

    return data


# =========================================================
# FINAL UPLOAD NEXT SORT FIX 5.1
# Upload Next ranking:
# - sort strictly by real synced total revenue / displayed revenue high to low
# - strongest money players at #1
# - weak $0.01 / low-revenue players pushed down or removed when better options exist
# =========================================================

_cv51_previous_build_channel_brain_recommendations = build_channel_brain_recommendations


def _cv51_upload_money_value(row):
    if not row:
        return 0

    # This matches what the frontend displays first.
    return safe_float(
        row.get("total_revenue")
        or row.get("synced_revenue")
        or row.get("expected_revenue")
        or row.get("projected_revenue")
        or row.get("average_revenue")
        or 0
    )


def build_channel_brain_recommendations(videos):
    data = _cv51_previous_build_channel_brain_recommendations(videos)

    upload = list(data.get("upload_next") or [])

    # If upload list is short or has weak low-money players, pull stronger unique players from shuffle too.
    combined = upload + list(data.get("shuffle_ideas") or [])

    best_by_player = {}

    for item in combined:
        player = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")

        if not player:
            continue

        money = _cv51_upload_money_value(item)

        # Ignore near-zero players unless we have no better choices later.
        if money <= 0.01:
            continue

        if player not in best_by_player or money > _cv51_upload_money_value(best_by_player[player]):
            best_by_player[player] = item

    ranked = sorted(
        best_by_player.values(),
        key=lambda row: (
            _cv51_upload_money_value(row),
            safe_int(row.get("expected_views") or row.get("projected_views") or row.get("average_views") or 0),
            safe_float(row.get("expected_rpm") or row.get("projected_rpm") or row.get("average_rpm") or 0)
        ),
        reverse=True
    )

    # If fewer than 15 after removing near-zero, backfill with the best remaining unique players.
    if len(ranked) < 15:
        seen = {normalize(x.get("player") or x.get("player_name") or x.get("topic") or x.get("name") or "") for x in ranked}

        fallback = sorted(
            combined,
            key=lambda row: (
                _cv51_upload_money_value(row),
                safe_int(row.get("expected_views") or row.get("projected_views") or row.get("average_views") or 0),
                safe_float(row.get("expected_rpm") or row.get("projected_rpm") or row.get("average_rpm") or 0)
            ),
            reverse=True
        )

        for item in fallback:
            player = normalize(item.get("player") or item.get("player_name") or item.get("topic") or item.get("name") or "")

            if not player or player in seen:
                continue

            seen.add(player)
            ranked.append(item)

            if len(ranked) >= 15:
                break

    data["upload_next"] = ranked[:15]
    data["best_next_upload"] = data["upload_next"][0] if data["upload_next"] else None

    if data["best_next_upload"]:
        best = data["best_next_upload"]
        data["today_focus"] = f"Plan a {best.get('player')} {best.get('format')} upload next."
        data["headline"] = f"Best next upload: {best.get('player')} ranked by highest synced revenue."

    data["version"] = "5.1-upload-next-highest-revenue-sort"
    data.setdefault("money_notes", [])
    data["money_notes"] = [
        *data["money_notes"],
        "Upload Next is sorted by highest synced/displayed revenue from top to bottom."
    ]

    return data


# =========================================================
# AUTO SYNC ORCHESTRATOR SUPPORT
# Prevents duplicate dashboard syncs from stacking while frontend auto-refreshes.
# =========================================================

_AUTO_SYNC_STATE = {
    "dashboard_sync_running": False,
    "last_dashboard_sync": "",
    "last_dashboard_sync_result": None
}


def run_dashboard_sync_safely(force=False):
    if _AUTO_SYNC_STATE["dashboard_sync_running"]:
        return {
            "ok": True,
            "already_running": True,
            "message": "Dashboard sync already running",
            "last_result": _AUTO_SYNC_STATE.get("last_dashboard_sync_result")
        }

    if not force and dashboard_video_data_is_fresh():
        info = get_latest_video_sync_info()
        result = {
            "ok": True,
            "skipped": True,
            "fresh": True,
            "message": "Dashboard/video data is already fresh. Loaded saved synced data.",
            "video_count": info.get("video_count", 0),
            "latest_video_sync": info.get("latest_video_sync", ""),
            "total_views": info.get("total_views", 0)
        }

        _AUTO_SYNC_STATE["last_dashboard_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_SYNC_STATE["last_dashboard_sync_result"] = result

        return {
            "ok": True,
            "already_running": False,
            "skipped": True,
            "message": "Dashboard/video data already fresh",
            "dashboard_sync": result,
            "last_dashboard_sync": _AUTO_SYNC_STATE["last_dashboard_sync"]
        }

    _AUTO_SYNC_STATE["dashboard_sync_running"] = True

    try:
        result = sync_channel()
        _AUTO_SYNC_STATE["last_dashboard_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_SYNC_STATE["last_dashboard_sync_result"] = result

        return {
            "ok": True,
            "already_running": False,
            "message": "Dashboard/video sync complete",
            "dashboard_sync": result,
            "last_dashboard_sync": _AUTO_SYNC_STATE["last_dashboard_sync"]
        }

    except Exception as error:
        _AUTO_SYNC_STATE["last_dashboard_sync"] = datetime.now().isoformat(timespec="seconds")
        _AUTO_SYNC_STATE["last_dashboard_sync_result"] = {
            "ok": False,
            "error": str(error)
        }

        return {
            "ok": False,
            "already_running": False,
            "message": "Dashboard/video sync failed",
            "error": str(error),
            "last_dashboard_sync": _AUTO_SYNC_STATE["last_dashboard_sync"]
        }

    finally:
        _AUTO_SYNC_STATE["dashboard_sync_running"] = False




STARTUP_DATA_CACHE = {
    "created_at": None,
    "payload": None
}

STARTUP_DATA_CACHE_SECONDS = 45


def clear_startup_data_cache():
    STARTUP_DATA_CACHE["created_at"] = None
    STARTUP_DATA_CACHE["payload"] = None


@router.get("/dashboard/startup-data")
def dashboard_startup_data():
    cached_at = STARTUP_DATA_CACHE.get("created_at")
    cached_payload = STARTUP_DATA_CACHE.get("payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=STARTUP_DATA_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    def safe_call(fn, fallback):
        try:
            result = fn()
            return result if result is not None else fallback
        except Exception:
            return fallback

    def safe_import_call(module_name, function_name, fallback):
        try:
            module = __import__(module_name, fromlist=[function_name])
            return safe_call(getattr(module, function_name), fallback)
        except Exception:
            return fallback

    from routes.idea_lab import top_50
    from routes.revenue import (
        revenue_summary,
        revenue_checklist,
        get_channel_revenue,
        get_video_revenue,
        youtube_revenue_status
    )

    payload = {
        "statsData": safe_call(dashboard_stats, {}),
        "savedVideosData": safe_call(saved_videos, {"saved_videos": []}),
        "rankingsData": safe_call(player_rankings, {"player_rankings": []}),
        "playersData": safe_call(top_50, {"top_50": []}),
        "channelBrainData": safe_call(channel_brain, {"channel_brain": None}),

        "revenueSummaryData": safe_call(revenue_summary, {"summary": None}),
        "revenueChecklistData": safe_call(revenue_checklist, {"checklist": None}),
        "channelRevenueData": safe_call(get_channel_revenue, {"channel_revenue": []}),
        "videoRevenueData": safe_call(get_video_revenue, {"video_revenue": []}),
        "youtubeRevenueStatusData": safe_call(youtube_revenue_status, {"status": None}),

        "revenueForecastData": safe_import_call("routes.revenue_forecast", "revenue_forecast", None),
        "strategyResponseData": safe_import_call("routes.content_strategy", "strategy_intelligence", None),
        "deadRecoveryResponseData": safe_import_call("routes.dead_video_recovery", "dead_video_recovery", None),

        "studioTypesData": safe_import_call("routes.studio_breakdowns", "studio_breakdown_types", {"types": []}),
        "studioSummaryData": safe_import_call("routes.studio_breakdowns", "studio_breakdowns_summary", {"summary": None}),
        "studioBreakdownsData": safe_import_call("routes.studio_breakdowns", "get_studio_breakdowns", {"studio_breakdowns": []}),
        "studioIntelligenceData": safe_import_call("routes.studio_intelligence", "studio_intelligence", None),

        "contentStudioStatusData": safe_import_call("routes.content_studio", "content_studio_status", None),
        "videoEditorStatusData": safe_import_call("routes.video_editor", "video_editor_status", None),
        "contentStudioProjectsData": safe_import_call("routes.content_studio", "get_content_studio_projects", {"projects": []})
    }

    STARTUP_DATA_CACHE["created_at"] = datetime.now()
    STARTUP_DATA_CACHE["payload"] = payload

    return payload


@router.post("/dashboard/auto-sync")
def dashboard_auto_sync(force: bool = False):
    """
    Frontend-safe auto sync route.

    Use this instead of making the user press Sync Channel.
    It refreshes video views, likes, comments, thumbnails, player names, and saved videos.
    """
    result = run_dashboard_sync_safely(force=force)
    clear_startup_data_cache()
    return result


@router.get("/dashboard/sync-status")
def dashboard_sync_status():
    return {
        "dashboard_sync_running": _AUTO_SYNC_STATE["dashboard_sync_running"],
        "last_dashboard_sync": _AUTO_SYNC_STATE["last_dashboard_sync"],
        "last_dashboard_sync_result": _AUTO_SYNC_STATE["last_dashboard_sync_result"]
    }
