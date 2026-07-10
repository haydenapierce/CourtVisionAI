from datetime import datetime, timedelta
from collections import Counter, defaultdict
from fastapi import APIRouter
from pydantic import BaseModel

from database.db import get_saved_videos

try:
    from database.db import get_community_post_history as _db_get_community_post_history
except Exception:
    _db_get_community_post_history = None

try:
    from database.db import get_community_post_learning as _db_get_community_post_learning
except Exception:
    _db_get_community_post_learning = None

try:
    from database.db import save_community_post_result as _db_save_community_post_result
except Exception:
    _db_save_community_post_result = None

try:
    from database.db import update_community_post_result as _db_update_community_post_result
except Exception:
    _db_update_community_post_result = None

try:
    from database.db import seed_community_post_history_if_needed as _db_seed_community_post_history_if_needed
except Exception:
    _db_seed_community_post_history_if_needed = None

try:
    from data.player_database import NBA_PLAYERS
except Exception:
    NBA_PLAYERS = []

router = APIRouter(prefix="/community-automation", tags=["Community Automation"])

COMMUNITY_HISTORY_MEMORY = []

POST_TYPES = [
    "Next Upload Poll",
    "Player Debate",
    "Trivia / Guess Who",
    "Upload Teaser",
    "Community Question",
    "Throwback / History Post",
]

IDEA_LAB_PRIORITY_PLAYERS = [
    "Jason Kidd", "Clyde Drexler", "Chris Mullin", "Walter Davis", "John Stockton",
    "Maurice Cheeks", "Tiny Archibald", "David Thompson", "Dennis Johnson", "George Gervin",
    "Connie Hawkins", "Earl Monroe", "Bernard King", "Elvin Hayes", "Bob McAdoo", "Pete Maravich",
    "Gary Payton", "Shawn Kemp", "Pau Gasol", "Manu Ginobili", "Yao Ming", "Dikembe Mutombo",
    "Dwight Howard", "Tracy McGrady", "Carmelo Anthony", "Grant Hill", "Ray Allen", "Reggie Miller",
    "Steve Nash", "Chris Paul", "Julius Erving", "Vince Carter", "Dominique Wilkins", "Hakeem Olajuwon",
    "David Robinson", "Bill Russell", "Tim Duncan", "Kareem Abdul-Jabbar", "Wilt Chamberlain",
    "Magic Johnson", "Larry Bird", "Allen Iverson", "Kobe Bryant", "Michael Jordan", "LeBron James",
]


class CommunityPostResult(BaseModel):
    id: int = 0
    post_date: str = ""
    post_time: str = ""
    post_type: str = "Next Upload Poll"
    poll_subtype: str = ""
    topic: str = ""
    linked_video_id: str = ""
    linked_video_title: str = ""
    linked_player: str = ""
    linked_format: str = ""
    post_text: str = ""
    poll_option_1: str = ""
    poll_option_2: str = ""
    poll_option_3: str = ""
    poll_option_4: str = ""
    poll_option_5: str = ""
    option_a: str = ""
    option_b: str = ""
    option_c: str = ""
    option_d: str = ""
    option_e: str = ""
    option_a_percent: float = 0
    option_b_percent: float = 0
    option_c_percent: float = 0
    option_d_percent: float = 0
    option_e_percent: float = 0
    poll_winner: str = ""
    trivia_answer: str = ""
    likes: int = 0
    comments: int = 0
    votes: int = 0
    poll_uploaded_status: str = ""
    upload_date_after_poll: str = ""
    days_between_poll_and_upload: int = 0


def _safe_int(value):
    try:
        return int(float(value or 0))
    except Exception:
        return 0


def _safe_float(value):
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _money(value):
    try:
        return round(float(value or 0), 2)
    except Exception:
        return 0.0


def _normalize(value):
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


def _canonical_post_type(value):
    text = _normalize(value)
    if "guess" in text or "trivia" in text or "quiz" in text:
        return "Trivia / Guess Who"
    if "teaser" in text or ("upload" in text and "poll" not in text) or "new video" in text or "video is up" in text:
        return "Upload Teaser"
    if "throwback" in text or "history" in text or "on this day" in text:
        return "Throwback / History Post"
    if "question" in text or "community" in text or "subscribers" in text or "donations" in text or "comment below" in text:
        return "Community Question"
    if "debate" in text or "finals" in text or "who will win" in text or "who’s winning" in text or "could" in text or "better" in text:
        return "Player Debate"
    return "Next Upload Poll"


def _season_from_date(date_text):
    try:
        month = int(str(date_text or "").split("-")[1])
    except Exception:
        return "Unknown"
    if month in (4, 5, 6):
        return "Playoffs / Finals"
    if month in (7, 8, 9):
        return "Offseason"
    return "Regular Season"


def _nba_year(date_text):
    try:
        year = int(str(date_text or "").split("-")[0])
        month = int(str(date_text or "").split("-")[1])
    except Exception:
        return ""
    return f"{year - 1}-{str(year)[-2:]}" if month <= 6 else f"{year}-{str(year + 1)[-2:]}"


def _engagement_score(row):
    # Votes matter most for polls. Comments are high-value. Likes are light signal.
    return round(_safe_int(row.get("votes")) * 0.35 + _safe_int(row.get("comments")) * 3 + _safe_int(row.get("likes")), 2)


def _option_count(row):
    return sum(1 for key in ["option_a", "option_b", "option_c", "option_d", "option_e"] if str(row.get(key) or "").strip())


def _normalize_history_row(row):
    item = dict(row or {})
    item["id"] = _safe_int(item.get("id"))
    item["post_type"] = _canonical_post_type(item.get("post_type") or item.get("type"))
    item["topic"] = item.get("topic") or item.get("poll_winner") or item.get("linked_player") or ""
    item["option_a"] = item.get("option_a") or item.get("poll_option_1") or ""
    item["option_b"] = item.get("option_b") or item.get("poll_option_2") or ""
    item["option_c"] = item.get("option_c") or item.get("poll_option_3") or ""
    item["option_d"] = item.get("option_d") or item.get("poll_option_4") or ""
    item["option_e"] = item.get("option_e") or item.get("poll_option_5") or ""
    for key in ["option_a_percent", "option_b_percent", "option_c_percent", "option_d_percent", "option_e_percent"]:
        item[key] = _safe_float(item.get(key))
    for key in ["likes", "comments", "votes", "poll_option_count", "days_between_poll_and_upload"]:
        item[key] = _safe_int(item.get(key))
    item["ai_engagement_score"] = _safe_float(item.get("ai_engagement_score")) or _engagement_score(item)
    item["season"] = item.get("season") or _season_from_date(item.get("post_date"))
    item["nba_year"] = item.get("nba_year") or _nba_year(item.get("post_date"))
    item["poll_option_count"] = item.get("poll_option_count") or _option_count(item)
    return item


def seed_community_history_if_needed():
    if _db_seed_community_post_history_if_needed:
        try:
            return _db_seed_community_post_history_if_needed()
        except Exception:
            return 0
    return 0


def get_community_post_history(limit=1000):
    rows = []
    if _db_get_community_post_history:
        try:
            rows = _db_get_community_post_history(limit) or []
        except Exception:
            rows = []
    if not rows:
        rows = COMMUNITY_HISTORY_MEMORY[-limit:]
    return [_normalize_history_row(row) for row in list(rows)[:limit]]


def _average(rows, key):
    rows = list(rows or [])
    if not rows:
        return 0
    return sum(_safe_float(row.get(key)) for row in rows) / max(1, len(rows))


def _bucket_stats(history, key_fn):
    bucket = defaultdict(lambda: {"score": 0.0, "count": 0, "votes": 0, "likes": 0, "comments": 0})
    for row in history:
        key = key_fn(row)
        if key in (None, ""):
            continue
        bucket[key]["score"] += _engagement_score(row)
        bucket[key]["count"] += 1
        bucket[key]["votes"] += _safe_int(row.get("votes"))
        bucket[key]["likes"] += _safe_int(row.get("likes"))
        bucket[key]["comments"] += _safe_int(row.get("comments"))
    return bucket


def _bucket_list(bucket, name_key):
    rows = []
    for key, stats in bucket.items():
        count = max(1, stats["count"])
        rows.append({
            name_key: key,
            "posts": stats["count"],
            "score": round(stats["score"] / count, 2),
            "average_votes": round(stats["votes"] / count, 1),
            "average_likes": round(stats["likes"] / count, 1),
            "average_comments": round(stats["comments"] / count, 1),
        })
    return sorted(rows, key=lambda item: item["score"], reverse=True)


def _learn_from_history(history):
    history = [_normalize_history_row(row) for row in history]
    if not history:
        return {
            "best_post_type": "Next Upload Poll",
            "best_type_score": 0,
            "best_time": "7:00 PM",
            "average_likes": 0,
            "average_comments": 0,
            "average_votes": 0,
            "top_topics": [],
            "insights": ["Community learning will improve after historical posts are imported."],
        }

    by_type = _bucket_stats(history, lambda row: row.get("post_type"))
    by_season = _bucket_stats(history, lambda row: row.get("season"))
    by_option_count = _bucket_stats(history, lambda row: row.get("poll_option_count") if row.get("poll_option_count") else "")
    by_winner = Counter()
    by_player = defaultdict(lambda: {"wins": 0, "votes": 0, "score": 0.0, "posts": 0})
    by_era = defaultdict(lambda: {"score": 0.0, "count": 0})

    for row in history:
        winner = str(row.get("poll_winner") or "").strip()
        if winner:
            by_winner[winner] += 1
            era = _era_for_player(winner)
            by_era[era]["score"] += _engagement_score(row)
            by_era[era]["count"] += 1
        for option_key in ["option_a", "option_b", "option_c", "option_d", "option_e"]:
            player = str(row.get(option_key) or "").strip()
            if not player:
                continue
            player_stats = by_player[player]
            player_stats["posts"] += 1
            player_stats["votes"] += _safe_int(row.get("votes"))
            player_stats["score"] += _engagement_score(row)
            if _normalize(player) == _normalize(winner):
                player_stats["wins"] += 1

    type_stats = _bucket_list(by_type, "post_type")
    season_stats = _bucket_list(by_season, "season")
    option_stats = _bucket_list(by_option_count, "option_count")

    best_type = type_stats[0] if type_stats else {"post_type": "Next Upload Poll", "score": 0}
    best_season = season_stats[0] if season_stats else {"season": "Unknown", "score": 0}
    best_option = option_stats[0] if option_stats else {"option_count": 4, "score": 0}

    player_trends = []
    for player, stats in by_player.items():
        posts = max(1, stats["posts"])
        win_rate = stats["wins"] / posts
        player_trends.append({
            "player": player,
            "polls": stats["posts"],
            "wins": stats["wins"],
            "win_rate": round(win_rate * 100, 1),
            "average_votes": round(stats["votes"] / posts, 1),
            "score": round(stats["score"] / posts, 2),
            "era": _era_for_player(player),
        })
    player_trends = sorted(player_trends, key=lambda item: (item["wins"], item["score"], item["average_votes"]), reverse=True)[:12]

    era_trends = []
    for era, stats in by_era.items():
        count = max(1, stats["count"])
        era_trends.append({"era": era, "score": round(stats["score"] / count, 2), "poll_wins": stats["count"]})
    era_trends = sorted(era_trends, key=lambda item: item["score"], reverse=True)

    total_likes = sum(_safe_int(row.get("likes")) for row in history)
    total_comments = sum(_safe_int(row.get("comments")) for row in history)
    total_votes = sum(_safe_int(row.get("votes")) for row in history)
    poll_rows = [row for row in history if _safe_int(row.get("votes")) > 0]

    insights = [
        f"3 posts per week is the safest cadence: enough signal without burning viewers out.",
        f"Best learned format: {best_type['post_type']}.",
        f"Best learned season: {best_season['season']}.",
        f"Best poll size: {best_option.get('option_count', 4)} options.",
    ]
    if player_trends:
        insights.append(f"Strongest poll/player signal: {player_trends[0]['player']}.")
    if era_trends:
        insights.append(f"Strongest era signal: {era_trends[0]['era']}.")

    return {
        "best_post_type": best_type["post_type"],
        "best_type_score": best_type["score"],
        "best_time": "7:00 PM",
        "average_likes": round(total_likes / max(1, len(history)), 1),
        "average_comments": round(total_comments / max(1, len(history)), 1),
        "average_votes": round(total_votes / max(1, len(poll_rows)), 1),
        "total_votes": total_votes,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "best_season": best_season["season"],
        "best_season_score": best_season["score"],
        "best_option_count": best_option.get("option_count", 4),
        "best_option_score": best_option.get("score", 0),
        "post_type_stats": type_stats,
        "season_stats": season_stats,
        "option_count_stats": option_stats,
        "player_trends": player_trends,
        "era_trends": era_trends,
        "top_topics": [{"topic": topic, "score": wins} for topic, wins in by_winner.most_common(10)],
        "top_poll_winners": [{"topic": topic, "wins": wins} for topic, wins in by_winner.most_common(10)],
        "insights": insights,
        "message": "Learning from all-time imported community post history plus new manual results.",
    }


def get_community_post_learning():
    if _db_get_community_post_learning:
        try:
            data = _db_get_community_post_learning()
            # Recompute here because route has newer model logic and is resilient to older DB functions.
            history = get_community_post_history(1000)
            return _learn_from_history(history) if history else data
        except Exception:
            pass
    return _learn_from_history(get_community_post_history(1000))


def _clean_result_payload(data):
    cleaned = dict(data or {})
    cleaned["post_date"] = cleaned.get("post_date") or ""
    cleaned["post_time"] = cleaned.get("post_time") or ""
    cleaned["post_type"] = _canonical_post_type(cleaned.get("post_type") or "Next Upload Poll")
    cleaned["option_a"] = cleaned.get("option_a") or cleaned.get("poll_option_1") or ""
    cleaned["option_b"] = cleaned.get("option_b") or cleaned.get("poll_option_2") or ""
    cleaned["option_c"] = cleaned.get("option_c") or cleaned.get("poll_option_3") or ""
    cleaned["option_d"] = cleaned.get("option_d") or cleaned.get("poll_option_4") or ""
    cleaned["option_e"] = cleaned.get("option_e") or cleaned.get("poll_option_5") or ""
    for key in ["option_a_percent", "option_b_percent", "option_c_percent", "option_d_percent", "option_e_percent"]:
        cleaned[key] = _safe_float(cleaned.get(key))
    cleaned["topic"] = cleaned.get("topic") or cleaned.get("poll_winner") or cleaned.get("trivia_answer") or cleaned.get("linked_player") or ""
    cleaned["poll_winner"] = cleaned.get("poll_winner") or ""
    cleaned["trivia_answer"] = cleaned.get("trivia_answer") or ""
    cleaned["linked_player"] = cleaned.get("linked_player") or cleaned.get("poll_winner") or ""
    cleaned["linked_format"] = cleaned.get("linked_format") or _infer_format(cleaned.get("post_text") or cleaned.get("linked_video_title") or "")
    cleaned["likes"] = _safe_int(cleaned.get("likes"))
    cleaned["comments"] = _safe_int(cleaned.get("comments"))
    cleaned["votes"] = _safe_int(cleaned.get("votes"))
    cleaned["poll_option_count"] = _option_count(cleaned)
    cleaned["season"] = _season_from_date(cleaned.get("post_date"))
    cleaned["nba_year"] = _nba_year(cleaned.get("post_date"))
    cleaned["ai_engagement_score"] = _engagement_score(cleaned)
    return cleaned


def save_community_post_result(data):
    cleaned = _clean_result_payload(data)
    row_id = _safe_int(cleaned.get("id"))
    if row_id and _db_update_community_post_result:
        try:
            return _db_update_community_post_result(row_id, cleaned)
        except Exception:
            pass
    if _db_save_community_post_result:
        try:
            return _db_save_community_post_result(cleaned)
        except Exception:
            pass
    cleaned["id"] = row_id or len(COMMUNITY_HISTORY_MEMORY) + 1
    cleaned["logged_at"] = datetime.now().isoformat(timespec="seconds")
    COMMUNITY_HISTORY_MEMORY.append(cleaned)
    return cleaned["id"]


def _get_saved_videos():
    try:
        return get_saved_videos() or []
    except Exception:
        return []


def _player_from_video(video):
    player = str(video.get("player_name") or "").strip()
    if player and player.lower() != "unknown":
        return player
    title = str(video.get("title") or "")
    lowered = title.lower()
    for marker in [" top 10", " top ten", " poster", " dunk", " highlights", " plays", " career"]:
        pos = lowered.find(marker)
        if pos > 1:
            return title[:pos].strip()
    return title.split(" vs ")[0].strip()[:48] or "NBA Legends"


def _is_top10_video(video):
    title = _normalize(video.get("title"))
    content_type = _normalize(video.get("content_type"))
    return "top 10" in title or "top ten" in title or content_type == "top 10"


def _infer_format(text):
    lower = _normalize(text)
    if "dunk" in lower or "poster" in lower:
        return "Top 10 Dunks"
    if "block" in lower:
        return "Top 10 Blocks"
    if "assist" in lower or "pass" in lower:
        return "Top 10 Assists"
    if "game winner" in lower or "buzzer" in lower:
        return "Top 10 Game Winners"
    if "clutch" in lower:
        return "Top 10 Clutch Shots"
    if "crossover" in lower or "handles" in lower:
        return "Top 10 Crossovers"
    if "rookie" in lower:
        return "Top 10 Rookie Plays"
    return "Top 10 Plays"


def _video_variation(video):
    return _infer_format(video.get("title") or video.get("content_type") or "")


def _video_score(video):
    views = _safe_int(video.get("views"))
    likes = _safe_int(video.get("likes"))
    comments = _safe_int(video.get("comments"))
    revenue = _money(video.get("yt_estimated_revenue") or video.get("estimated_revenue"))
    rpm = _money(video.get("yt_estimated_rpm") or video.get("estimated_rpm"))
    return views * 0.0015 + likes * 0.18 + comments * 0.8 + revenue * 8 + rpm * 20


def _era_for_player(player):
    text = _normalize(player)
    modern = ["wembanyama", "jokic", "luka", "giannis", "ja", "anthony edwards", "haliburton", "brunson", "shai", "donovan", "jalen", "caitlin"]
    old_school = ["wilt", "russell", "west", "baylor", "maravich", "frazier", "monroe", "havlicek"]
    vintage = ["kareem", "erving", "gervin", "mcadoo", "hayes", "walton", "bird", "magic", "jordan", "dominique"]
    if any(name in text for name in modern):
        return "Modern / current"
    if any(name in text for name in old_school):
        return "Classic 1960s-70s"
    if any(name in text for name in vintage):
        return "Legends 1970s-90s"
    return "2000s / 2010s stars"


def _player_meta_names():
    names = []
    seen = set()
    for name in IDEA_LAB_PRIORITY_PLAYERS:
        key = _normalize(name)
        if key not in seen:
            seen.add(key)
            names.append(name)
    for player in NBA_PLAYERS or []:
        name = str(player.get("name") or "").strip()
        key = _normalize(name)
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names[:180]


def _variation_for_player(player_name, existing_variations):
    text = _normalize(player_name)
    done = {str(v) for v in existing_variations if v}
    if "Top 10 Plays" not in done:
        return "Top 10 Plays"
    dunkers = ["julius erving", "vince carter", "dominique", "michael jordan", "kobe", "lebron", "ja morant", "anthony edwards", "shawn kemp", "blake griffin", "dwight", "shaquille"]
    passers = ["magic", "stockton", "nash", "jason kidd", "chris paul", "jokic", "luka", "larry bird", "pete maravich", "jason williams"]
    blockers = ["wilt", "kareem", "hakeem", "david robinson", "bill russell", "tim duncan", "mutombo", "dwight", "shaq", "yao"]
    clutch = ["jordan", "kobe", "reggie", "bird", "ray allen", "lillard", "curry", "lebron", "durant", "carmelo"]
    handles = ["iverson", "kyrie", "curry", "jason williams", "pete maravich", "earl monroe"]
    ordered = []
    if any(name in text for name in dunkers):
        ordered.append("Top 10 Dunks")
    if any(name in text for name in passers):
        ordered.append("Top 10 Assists")
    if any(name in text for name in blockers):
        ordered.append("Top 10 Blocks")
    if any(name in text for name in clutch):
        ordered.extend(["Top 10 Game Winners", "Top 10 Clutch Shots"])
    if any(name in text for name in handles):
        ordered.append("Top 10 Crossovers")
    ordered.extend(["Top 10 Dunks", "Top 10 Game Winners", "Top 10 Clutch Shots", "Top 10 Assists", "Top 10 Blocks", "Solo Highlight"])
    for option in ordered:
        if option not in done:
            return option
    return "Solo Highlight"


def _build_player_candidates(limit=30):
    videos = _get_saved_videos()
    variations_by_player = defaultdict(set)
    top10_by_player = defaultdict(list)
    by_player = defaultdict(list)
    for video in videos:
        player = _player_from_video(video)
        key = _normalize(player)
        if not key or key == "unknown":
            continue
        by_player[key].append(video)
        variation = _video_variation(video)
        variations_by_player[key].add(variation)
        if _is_top10_video(video):
            top10_by_player[key].append(video)

    candidates = []
    for rank, name in enumerate(_player_meta_names(), start=1):
        key = _normalize(name)
        existing_rows = by_player.get(key, [])
        existing_variations = variations_by_player.get(key, set())
        format_name = _variation_for_player(name, existing_variations)
        best_existing = max(existing_rows, key=_video_score, default={})
        base_priority = max(25, 100 - rank * 1.1)
        if key in top10_by_player:
            base_priority += min(18, _safe_int(best_existing.get("views")) / 20000)
            reason = f"{name} already has a Top 10 signal, so the best next angle is {format_name}."
        else:
            base_priority += 10
            reason = f"{name} is an Idea Lab style candidate without a completed Top 10 in the synced library."
        candidates.append({
            "player": name,
            "format": format_name,
            "priority": round(base_priority, 2),
            "reason": reason,
            "era": _era_for_player(name),
            "existing_video": best_existing,
        })
    return candidates[:limit]


def _latest_unfulfilled_poll_winner(history, videos):
    for row in history:
        if _canonical_post_type(row.get("post_type")) != "Next Upload Poll":
            continue
        winner = str(row.get("poll_winner") or row.get("topic") or "").strip()
        if not winner:
            continue
        winner_key = _normalize(winner)
        for video in videos:
            title = _normalize(video.get("title"))
            player = _normalize(video.get("player_name"))
            if winner_key and (winner_key in title or winner_key == player):
                return ""
        return winner
    return ""


def _poll_options(candidates, start=0, count=5):
    if not candidates:
        return ["Jason Kidd", "Clyde Drexler", "John Stockton", "Shawn Kemp", "Reggie Miller"][:count]
    options = []
    index = start
    while len(options) < count and index < start + len(candidates) + count:
        candidate = candidates[index % len(candidates)]
        label = candidate.get("player") or "NBA Legend"
        if label not in options:
            options.append(label)
        index += 1
    return options


def _post_copy(post_type, candidate, options, locked_winner=""):
    player = candidate.get("player", "NBA Legend")
    format_name = candidate.get("format", "Top 10 Plays")
    if post_type == "Next Upload Poll":
        return f"Which player deserves a {format_name} video next?", options, f"Next Upload Poll: {format_name}"
    if post_type == "Player Debate":
        debate_options = options[:2] if len(options) >= 2 else [player, "Another legend"]
        return f"Who had the better highlight reel: {debate_options[0]} or {debate_options[1]}?", debate_options, "Player Debate"
    if post_type == "Trivia / Guess Who":
        return f"Guess who: this player is one of the next legends I’m considering for a Top 10 video.", [], "Trivia / Guess Who"
    if post_type == "Upload Teaser":
        if locked_winner:
            return f"The {locked_winner} video is the one viewers picked. I’m working on it now — stay tuned.", [], "Upload Teaser"
        return f"New {player} {format_name} idea is in the queue. Would you watch this one?", [], "Upload Teaser"
    if post_type == "Throwback / History Post":
        return f"Throwback debate: what is the most underrated play from {player}'s career?", [], "Throwback / History Post"
    return f"What NBA legend should get more love on this channel next?", [], "Community Question"


def _prediction_for_type(post_type, learning, history):
    same_type = [row for row in history if row.get("post_type") == post_type]
    poll_type = post_type in ("Next Upload Poll", "Player Debate")
    if same_type:
        votes = _average(same_type, "votes") if poll_type else 0
        likes = _average(same_type, "likes")
        comments = _average(same_type, "comments")
    else:
        votes = learning.get("average_votes", 0) if poll_type else 0
        likes = learning.get("average_likes", 1)
        comments = learning.get("average_comments", 0)
    return {
        "votes": max(0, int(round(votes))),
        "likes": max(1, int(round(likes))),
        "comments": max(0, int(round(comments))),
    }


def _build_post(day, slot, post_type, candidate, options, priority, learning_reason, learning, history, locked_winner=""):
    post_text, post_options, title = _post_copy(post_type, candidate, options, locked_winner)
    is_poll = post_type in ["Next Upload Poll", "Player Debate"]
    prediction = _prediction_for_type(post_type, learning, history)
    confidence_percent = min(96, max(55, int(60 + min(35, len(history) / 2) + min(12, priority / 12))))
    return {
        "date": day.strftime("%Y-%m-%d"),
        "day": day.strftime("%A"),
        "time": slot,
        "type": post_type,
        "title": title,
        "topic": candidate.get("player", "NBA Legend"),
        "post_text": post_text,
        "options": post_options if is_poll else [],
        "linked_video_id": candidate.get("existing_video", {}).get("video_id", "") if candidate.get("existing_video") else "",
        "linked_video_title": candidate.get("existing_video", {}).get("title", "") if candidate.get("existing_video") else "",
        "expected_likes": prediction["likes"],
        "expected_comments": prediction["comments"],
        "expected_votes": prediction["votes"] if is_poll else 0,
        "confidence": "High" if confidence_percent >= 80 else "Medium",
        "confidence_percent": confidence_percent,
        "priority_score": round(priority, 2),
        "reason": f"{candidate.get('reason', '')} {learning_reason}".strip(),
    }


def _next_schedule_days(today):
    # 3 posts/week: Tuesday, Thursday, Sunday. If today is one of them, include today.
    target_weekdays = [1, 3, 6]  # Tue, Thu, Sun
    days = []
    offset = 0
    while len(days) < 3 and offset < 14:
        candidate = today + timedelta(days=offset)
        if candidate.weekday() in target_weekdays:
            days.append(candidate)
        offset += 1
    return days


@router.get("")
def get_community_automation():
    seeded_count = seed_community_history_if_needed()
    history = get_community_post_history(1000)
    learning = get_community_post_learning()
    candidates = _build_player_candidates(30)
    videos = _get_saved_videos()
    locked_winner = _latest_unfulfilled_poll_winner(history, videos)
    today = datetime.now()
    learned_time = learning.get("best_time") or "7:00 PM"
    total_votes = sum(_safe_int(row.get("votes")) for row in history)
    momentum = min(100, round((len(history) * 1.0) + (learning.get("best_type_score") or 0) / 2, 1))

    if locked_winner:
        post_types = ["Upload Teaser", "Community Question", "Player Debate"]
        learning_reason = f"The most recent next-upload poll winner is {locked_winner}, so the scheduler will not make another next-upload poll until that video is posted or logged."
    else:
        post_types = ["Next Upload Poll", "Player Debate", "Throwback / History Post"]
        learning_reason = "3 posts per week is the recommended cadence. It rotates formats and uses all-time poll history to avoid repeating the same post type too often."

    schedule = []
    schedule_days = _next_schedule_days(today)
    for index, day in enumerate(schedule_days):
        candidate = candidates[index % len(candidates)] if candidates else {"player": "NBA Legends", "format": "Top 10 Plays", "priority": 55, "reason": "Fallback recommendation.", "era": "Mixed"}
        opt_count = int(learning.get("best_option_count") or 4)
        opt_count = min(5, max(2, opt_count))
        options = _poll_options(candidates, index, opt_count)
        post_type = post_types[index % len(post_types)]
        priority = min(98, candidate.get("priority", 55) + (learning.get("best_type_score") or 0) / 14)
        schedule.append(_build_post(day, learned_time if index == 0 else ["12:15 PM", "6:45 PM", "7:30 PM"][index % 3], post_type, candidate, options, priority, learning_reason, learning, history, locked_winner))

    top_recommendation = schedule[0] if schedule else None
    return {
        "summary": {
            "next_recommended_post": top_recommendation,
            "best_time_today": top_recommendation.get("time") if top_recommendation else learned_time,
            "community_momentum": momentum,
            "engagement_score": momentum,
            "logged_posts": len(history),
            "total_posts": len(history),
            "total_votes": total_votes,
            "total_likes": sum(_safe_int(row.get("likes")) for row in history),
            "total_comments": sum(_safe_int(row.get("comments")) for row in history),
            "best_learned_post_type": learning.get("best_post_type") or "Next Upload Poll",
            "best_type": learning.get("best_post_type") or "Next Upload Poll",
            "best_time": learning.get("best_time") or learned_time,
            "best_topic": top_recommendation.get("topic") if top_recommendation else "Next Top 10 Poll",
            "best_season": learning.get("best_season"),
            "best_option_count": learning.get("best_option_count"),
            "locked_poll_winner": locked_winner,
            "available_post_types": POST_TYPES,
            "seeded_imports_added": seeded_count,
            "recommended_weekly_cadence": "3 posts per week",
            "strategy_note": "Uses all-time community post history, manual updates, synced videos, and Idea Lab candidates.",
        },
        "next_post": top_recommendation,
        "schedule": schedule,
        "poll_bank": [],
        "history": history,
        "learning": learning,
        "source_videos": [candidate.get("existing_video", {}) for candidate in candidates[:8]],
        "idea_lab_candidates": candidates[:12],
        "available_post_types": POST_TYPES,
    }


@router.get("/history")
def community_history():
    seed_community_history_if_needed()
    history = get_community_post_history(1000)
    return {"history": history, "learning": _learn_from_history(history)}


@router.post("/log")
def log_community_result(result: CommunityPostResult):
    data = result.dict()
    for idx, key in enumerate(["a", "b", "c", "d", "e"], start=1):
        option_key = f"option_{key}"
        poll_key = f"poll_option_{idx}"
        if not data.get(poll_key) and data.get(option_key):
            data[poll_key] = data.get(option_key, "")
    new_id = save_community_post_result(data)
    return {"status": "ok", "id": new_id, "message": "Community post result saved/updated. Future recommendations will use all-time history, votes, percentages, likes, comments, winners, post types, eras, seasons, and Idea Lab candidates."}


@router.post("/results")
def save_community_result_alias(result: CommunityPostResult):
    return log_community_result(result)
