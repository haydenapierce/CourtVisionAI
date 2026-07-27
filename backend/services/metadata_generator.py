import re
from collections import Counter
from functools import lru_cache
import math
import time

MAX_TAG_LENGTH = 470  # Conservative YouTube API-safe encoded tag budget
MAX_TITLE_LENGTH = 100

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "best", "by", "for", "from",
    "in", "into", "is", "it", "of", "on", "or", "the", "this", "to", "video",
    "with", "vs", "versus", "his", "her", "their", "that", "over"
}

ACTION_KEYWORDS = {
    "dunk": ["dunk", "slam dunk", "poster", "poster dunk", "jams", "throws it down", "slams"],
    "layup": ["layup", "finger roll", "scoop shot", "up and under", "euro step"],
    "block": ["block", "rejection", "swat", "chasedown", "chase-down"],
    "pass": ["pass", "assist", "no-look", "behind-the-back", "alley-oop", "outlet"],
    "shot": ["game winner", "buzzer beater", "clutch shot", "three-pointer", "jumper", "fadeaway", "step-back"],
    "handle": ["crossover", "ankle breaker", "dribble", "handles", "spin move"],
    "steal": ["steal", "strip", "interception", "pickpocket"],
    "rebound": ["rebound", "putback"],
}

# Ordered from most specific to most general. A phrase is used only when the
# user's clip description supports it; CourtVision never invents a move.
SIGNATURE_ACTION_PATTERNS = [
    # Dunks
    {"key": "jump_over_poster", "action": "dunk", "label": "Jump-Over Poster Dunk", "patterns": [
        r"\b(?:jump(?:s|ed|ing)?|leap(?:s|ed|ing)?|vault(?:s|ed|ing)?|clear(?:s|ed|ing)?)\s+(?:completely\s+|right\s+)?over\b.*\b(?:dunk|slam|poster)",
        r"\b(?:dunk|slam|poster)\b.*\b(?:jump(?:s|ed|ing)?|leap(?:s|ed|ing)?|vault(?:s|ed|ing)?|clear(?:s|ed|ing)?)\s+over\b",
    ], "tag_phrases": ["jump over dunk", "jump-over poster dunk", "dunk over defender"]},
    {"key": "windmill_dunk", "action": "dunk", "label": "Windmill Dunk", "patterns": [r"\bwindmill(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["windmill dunk"]},
    {"key": "reverse_dunk", "action": "dunk", "label": "Reverse Dunk", "patterns": [r"\breverse(?:\s+(?:slam|dunk))\b"], "tag_phrases": ["reverse dunk"]},
    {"key": "tomahawk_dunk", "action": "dunk", "label": "Tomahawk Dunk", "patterns": [r"\btomahawk(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["tomahawk dunk"]},
    {"key": "cradle_dunk", "action": "dunk", "label": "Cradle Dunk", "patterns": [r"\bcradle(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["cradle dunk"]},
    {"key": "double_clutch_dunk", "action": "dunk", "label": "Double-Clutch Dunk", "patterns": [r"\bdouble[ -]?clutch(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["double clutch dunk"]},
    {"key": "360_dunk", "action": "dunk", "label": "360 Dunk", "patterns": [r"\b360(?:[- ]degree)?(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["360 dunk"]},
    {"key": "between_legs_dunk", "action": "dunk", "label": "Between-the-Legs Dunk", "patterns": [r"\bbetween[- ]the[- ]legs(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["between the legs dunk"]},
    {"key": "self_alley_oop_dunk", "action": "dunk", "label": "Self Alley-Oop Dunk", "patterns": [r"\bself[- ]alley[- ]oop(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["self alley oop dunk"]},
    {"key": "alley_oop_dunk", "action": "dunk", "label": "Alley-Oop Dunk", "patterns": [r"\balley[- ]oop(?:\s+(?:slam|dunk|finish))?\b"], "tag_phrases": ["alley oop dunk"]},
    {"key": "putback_dunk", "action": "dunk", "label": "Putback Dunk", "patterns": [r"\bput[- ]?back(?:\s+(?:slam|dunk))?\b"], "tag_phrases": ["putback dunk"]},
    {"key": "one_hand_dunk", "action": "dunk", "label": "One-Handed Dunk", "patterns": [r"\bone[- ]hand(?:ed)?(?:\s+(?:slam|dunk))\b"], "tag_phrases": ["one handed dunk"]},
    {"key": "two_hand_dunk", "action": "dunk", "label": "Two-Handed Dunk", "patterns": [r"\btwo[- ]hand(?:ed)?(?:\s+(?:slam|dunk))\b"], "tag_phrases": ["two handed dunk"]},
    {"key": "baseline_dunk", "action": "dunk", "label": "Baseline Dunk", "patterns": [r"\bbaseline(?:\s+(?:slam|dunk))\b"], "tag_phrases": ["baseline dunk"]},
    {"key": "fast_break_dunk", "action": "dunk", "label": "Fast-Break Dunk", "patterns": [r"\bfast[- ]break(?:\s+(?:slam|dunk))\b"], "tag_phrases": ["fast break dunk"]},
    {"key": "coast_to_coast_dunk", "action": "dunk", "label": "Coast-to-Coast Dunk", "patterns": [r"\bcoast[- ]to[- ]coast(?:\s+(?:slam|dunk|finish))?\b"], "tag_phrases": ["coast to coast dunk"]},

    # Passes
    {"key": "behind_back_pass", "action": "pass", "label": "Behind-the-Back Pass", "patterns": [r"\bbehind[- ]the[- ]back(?:\s+pass)?\b"], "tag_phrases": ["behind the back pass"]},
    {"key": "overhead_pass", "action": "pass", "label": "Overhead Pass", "patterns": [r"\bover[- ]?head(?:\s+pass)?\b"], "tag_phrases": ["overhead pass"]},
    {"key": "no_look_pass", "action": "pass", "label": "No-Look Pass", "patterns": [r"\bno[- ]look(?:\s+pass)?\b"], "tag_phrases": ["no look pass"]},
    {"key": "full_court_pass", "action": "pass", "label": "Full-Court Pass", "patterns": [r"\bfull[- ]court(?:\s+pass)?\b"], "tag_phrases": ["full court pass"]},
    {"key": "baseball_pass", "action": "pass", "label": "Baseball Pass", "patterns": [r"\bbaseball(?:\s+pass)?\b"], "tag_phrases": ["baseball pass"]},
    {"key": "wraparound_pass", "action": "pass", "label": "Wraparound Pass", "patterns": [r"\bwrap[- ]?around(?:\s+pass)?\b"], "tag_phrases": ["wraparound pass"]},
    {"key": "bounce_pass", "action": "pass", "label": "Bounce Pass", "patterns": [r"\bbounce(?:\s+pass)?\b"], "tag_phrases": ["bounce pass"]},
    {"key": "touch_pass", "action": "pass", "label": "Touch Pass", "patterns": [r"\btouch(?:\s+pass)?\b"], "tag_phrases": ["touch pass"]},
    {"key": "outlet_pass", "action": "pass", "label": "Outlet Pass", "patterns": [r"\boutlet(?:\s+pass)?\b"], "tag_phrases": ["outlet pass"]},
    {"key": "cross_court_pass", "action": "pass", "label": "Cross-Court Pass", "patterns": [r"\bcross[- ]court(?:\s+(?:pass|laser))?\b"], "tag_phrases": ["cross court pass"]},

    # Layups and finishes
    {"key": "reverse_layup", "action": "layup", "label": "Reverse Layup", "patterns": [r"\breverse(?:\s+layup)\b"], "tag_phrases": ["reverse layup"]},
    {"key": "circus_layup", "action": "layup", "label": "Circus Layup", "patterns": [r"\bcircus(?:\s+(?:layup|shot|finish))?\b"], "tag_phrases": ["circus layup"]},
    {"key": "double_clutch_layup", "action": "layup", "label": "Double-Clutch Layup", "patterns": [r"\bdouble[ -]?clutch(?:\s+layup)\b"], "tag_phrases": ["double clutch layup"]},
    {"key": "scoop_layup", "action": "layup", "label": "Scoop Layup", "patterns": [r"\bscoop(?:\s+(?:layup|shot))?\b"], "tag_phrases": ["scoop layup"]},
    {"key": "finger_roll", "action": "layup", "label": "Finger Roll", "patterns": [r"\bfinger[- ]roll\b"], "tag_phrases": ["finger roll"]},
    {"key": "euro_step", "action": "layup", "label": "Euro-Step Layup", "patterns": [r"\beuro[- ]?step(?:\s+layup)?\b"], "tag_phrases": ["euro step layup"]},
    {"key": "up_and_under", "action": "layup", "label": "Up-and-Under Layup", "patterns": [r"\bup[- ]and[- ]under(?:\s+layup)?\b"], "tag_phrases": ["up and under layup"]},
    {"key": "spin_layup", "action": "layup", "label": "Spinning Layup", "patterns": [r"\bspin(?:ning)?(?:\s+layup|\s+finish)\b"], "tag_phrases": ["spinning layup"]},

    # Shots
    {"key": "buzzer_beater", "action": "shot", "label": "Buzzer-Beater", "patterns": [r"\bbuzzer[- ]beater\b", r"\bat the buzzer\b"], "tag_phrases": ["buzzer beater"]},
    {"key": "game_winner", "action": "shot", "label": "Game-Winner", "patterns": [r"\bgame[- ]winner\b", r"\bgame[- ]winning(?:\s+shot)?\b"], "tag_phrases": ["game winner"]},
    {"key": "step_back_three", "action": "shot", "label": "Step-Back Three", "patterns": [r"\bstep[- ]back(?:\s+(?:three|3|three-pointer|3-pointer))\b"], "tag_phrases": ["step back three"]},
    {"key": "fadeaway", "action": "shot", "label": "Fadeaway Jumper", "patterns": [r"\bfade[- ]?away(?:\s+jumper|\s+shot)?\b"], "tag_phrases": ["fadeaway jumper"]},
    {"key": "turnaround", "action": "shot", "label": "Turnaround Jumper", "patterns": [r"\bturn[- ]?around(?:\s+jumper|\s+shot)?\b"], "tag_phrases": ["turnaround jumper"]},
    {"key": "bank_shot", "action": "shot", "label": "Bank Shot", "patterns": [r"\bbank(?:ed)?(?:\s+shot|\s+jumper)?\b"], "tag_phrases": ["bank shot"]},
    {"key": "deep_three", "action": "shot", "label": "Deep Three-Pointer", "patterns": [r"\bdeep(?:\s+(?:three|3|three-pointer|3-pointer))\b"], "tag_phrases": ["deep three pointer"]},
    {"key": "pull_up", "action": "shot", "label": "Pull-Up Jumper", "patterns": [r"\bpull[- ]up(?:\s+jumper|\s+shot|\s+three)?\b"], "tag_phrases": ["pull up jumper"]},

    # Defense / handles
    {"key": "chasedown_block", "action": "block", "label": "Chase-Down Block", "patterns": [r"\bchase[- ]?down(?:\s+(?:block|rejection))?\b"], "tag_phrases": ["chase down block"]},
    {"key": "game_saving_block", "action": "block", "label": "Game-Saving Block", "patterns": [r"\bgame[- ]saving(?:\s+block)?\b"], "tag_phrases": ["game saving block"]},
    {"key": "ankle_breaker", "action": "handle", "label": "Ankle-Breaking Crossover", "patterns": [r"\bankle[- ]break(?:er|ing)?\b"], "tag_phrases": ["ankle breaker crossover"]},
    {"key": "spin_move", "action": "handle", "label": "Spin Move", "patterns": [r"\bspin(?:ning)?\s+move\b"], "tag_phrases": ["spin move"]},
    {"key": "behind_back_dribble", "action": "handle", "label": "Behind-the-Back Crossover", "patterns": [r"\bbehind[- ]the[- ]back(?:\s+(?:dribble|crossover|move))\b"], "tag_phrases": ["behind the back crossover"]},
]


EVENT_ALIASES = {
    "sydney olympics": "Sydney Olympics",
    "2000 olympics": "2000 Olympics",
    "olympic games": "Olympics",
    "nba finals": "NBA Finals",
    "all-star game": "NBA All-Star Game",
    "all star game": "NBA All-Star Game",
    "slam dunk contest": "NBA Slam Dunk Contest",
}


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def clean_title_from_filename(filename):
    if not filename:
        return "Untitled NBA Highlight"
    name = filename.rsplit(".", 1)[0]
    name = name.replace("_", " ").replace("-", " ").replace(".", " ")
    return _clean(name) or "Untitled NBA Highlight"


def _smart_title_case(value):
    special = {
        "nba": "NBA", "usa": "USA", "olympics": "Olympics", "ncaa": "NCAA",
        "wnba": "WNBA", "mvp": "MVP", "vs": "vs.", "ii": "II", "iii": "III",
        "iv": "IV", "jr": "Jr.", "sr": "Sr."
    }
    output = []
    for word in _clean(value).split():
        plain = re.sub(r"[^A-Za-z0-9]", "", word).lower()
        if plain in special:
            replacement = special[plain]
            punctuation = word[len(re.sub(r"[^A-Za-z0-9]", "", word)):] if word else ""
            output.append(replacement + punctuation)
        elif re.match(r"^\d{4}$", word):
            output.append(word)
        elif word.startswith("7'") or word.startswith('7"'):
            output.append(word)
        else:
            output.append(word[:1].upper() + word[1:])
    return " ".join(output)


TITLE_MINOR_WORDS = {
    "a", "an", "and", "as", "at", "but", "by", "for", "from", "in",
    "into", "nor", "of", "on", "or", "per", "the", "to", "via", "vs",
    "with", "yet"
}

TITLE_SPECIAL_WORDS = {
    "nba": "NBA", "wnba": "WNBA", "ncaa": "NCAA", "usa": "USA",
    "mvp": "MVP", "olympics": "Olympics", "all-star": "All-Star",
    "allstar": "All-Star", "vs": "vs.", "jr": "Jr.", "sr": "Sr.",
    "ii": "II", "iii": "III", "iv": "IV"
}


def _capitalize_title_word(word):
    """Capitalize one meaningful title word while preserving punctuation and heights."""
    if not word:
        return word

    # Preserve explicitly supplied measurements such as 7'2" and ordinary years/numbers.
    if re.fullmatch(r'\d+(?:[\'′]\d{1,2}[\"″]?)?', word):
        return word.replace("′", "'").replace("″", '"')

    leading = re.match(r"^[^A-Za-zÀ-ÖØ-öø-ÿ0-9]*", word).group(0)
    trailing = re.search(r'[^A-Za-zÀ-ÖØ-öø-ÿ0-9.\'’"-]*$', word).group(0)
    core_end = len(word) - len(trailing) if trailing else len(word)
    core = word[len(leading):core_end]
    if not core:
        return word

    lower_core = core.casefold().rstrip(".")
    if lower_core in TITLE_SPECIAL_WORDS:
        return leading + TITLE_SPECIAL_WORDS[lower_core] + trailing

    # Capitalize each side of meaningful hyphenated terms: Game-Winner, No-Look.
    if "-" in core:
        parts = core.split("-")
        formatted = "-".join(
            part[:1].upper() + part[1:] if part else part
            for part in parts
        )
        return leading + formatted + trailing

    return leading + core[:1].upper() + core[1:] + trailing


def _title_case_solo(value):
    """Apply readable YouTube title case without capitalizing short filler words."""
    words = _clean(value).split()
    if not words:
        return ""

    output = []
    last_index = len(words) - 1
    for index, word in enumerate(words):
        plain = re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ0-9-]", "", word).casefold().rstrip(".")
        if index not in {0, last_index} and plain in TITLE_MINOR_WORDS:
            # Keep standard title filler words lowercase while preserving punctuation.
            output.append(word.lower())
        else:
            output.append(_capitalize_title_word(word))
    return " ".join(output)


def _strip_duplicate_player(happening, player):
    text = _clean(happening)
    player = _clean(player)
    if not text or not player:
        return text
    pattern = re.compile(rf"^\s*{re.escape(player)}(?:\s+{re.escape(player)})?\s*", re.IGNORECASE)
    return pattern.sub("", text, count=1).strip(" ,-–—")


def _sentence(value):
    text = _clean(value)
    if not text:
        return ""
    text = text[0].upper() + text[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _extract_year(text):
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text or "")
    return match.group(1) if match else ""


def _extract_height(text):
    match = re.search(r"\b([5-8])\s*['′]\s*(\d{1,2})?\s*(?:[\"″])?", text or "")
    if not match:
        return ""
    feet = match.group(1)
    inches = match.group(2) or "0"
    return f"{feet}'{inches}\""


def _extract_event(text):
    cleaned = _clean(text)
    lowered = cleaned.casefold()
    year = _extract_year(cleaned)
    for phrase, display in EVENT_ALIASES.items():
        if phrase in lowered:
            if year and year not in display:
                return f"{year} {display.replace('2000 ', '')}"
            return display
    event_patterns = [
        (r"\bnba playoffs\b", "NBA Playoffs"),
        (r"\bplayoffs\b", "Playoffs"),
        (r"\bnba finals\b", "NBA Finals"),
        (r"\bconference finals\b", "Conference Finals"),
        (r"\ball[- ]star game\b", "NBA All-Star Game"),
        (r"\bslam dunk contest\b", "NBA Slam Dunk Contest"),
        (r"\bolympic(?: games|s)?\b", "Olympics"),
        (r"\bpreseason\b", "Preseason"),
        (r"\bregular season\b", "Regular Season"),
    ]
    for pattern, display in event_patterns:
        if re.search(pattern, lowered):
            return f"{year} {display}" if year else display
    return ""

def _detect_signature_action(text):
    """Return the most specific action explicitly supported by the input."""
    cleaned = _clean(text)
    for item in SIGNATURE_ACTION_PATTERNS:
        if any(re.search(pattern, cleaned, flags=re.I) for pattern in item["patterns"]):
            return item
    return None


def _detect_action(text):
    signature = _detect_signature_action(text)
    if signature:
        return signature["action"]
    lowered = _clean(text).lower()
    for action, phrases in ACTION_KEYWORDS.items():
        if any(phrase in lowered for phrase in phrases):
            return action
    return "highlight"


def _extract_opponent(text, player=""):
    cleaned = _strip_duplicate_player(text, player)
    # Accept natural lowercase input, then stop before event/time/context phrases.
    match = re.search(
        r'\b(?:over|on|against|vs\.?|versus)\s+(?:the\s+)?(?:\d\s*[\'′]\s*\d{0,2}\s*["″]?\s*)?(.+?)(?=\s+(?:for|at|in|during|with|to|after|before)\b|[,.!?]|$)',
        cleaned,
        flags=re.I,
    )
    if not match:
        return ""
    candidate = _clean(match.group(1)).strip(" ,-–—")
    if not candidate or candidate.casefold() in {"the", "a", "rim", "basket"}:
        return ""
    words = candidate.split()
    if len(words) > 5:
        candidate = " ".join(words[:5])
    return _smart_title_case(candidate)

def _play_type_phrase(text):
    signature = _detect_signature_action(text)
    if signature:
        return signature["label"]

    lowered = _clean(text).casefold()
    checks = [
        (("poster dunk", "slam dunk poster", "posterizes", "posterized", "poster"), "Poster Dunk"),
        (("slam dunk", "throws it down", "jams", "dunk"), "Slam Dunk"),
        (("block", "rejection", "swat"), "Block"),
        (("assist", "pass"), "Pass"),
        (("three pointer", "three-pointer", "3 pointer", "3-pointer"), "Three-Pointer"),
        (("jump shot", "jumper"), "Jump Shot"),
        (("layup",), "Layup"),
        (("crossover",), "Crossover"),
        (("steal", "strip", "interception"), "Steal"),
        (("rebound",), "Rebound"),
    ]
    for phrases, label in checks:
        if any(phrase in lowered for phrase in phrases):
            return label
    return "Highlight Play"


def _meaningful_tokens(text):
    return [
        token.lower()
        for token in re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9']+", _clean(text))
        if len(token) > 2 and token.lower() not in STOPWORDS
    ]


def _is_top10_video(video):
    content_type = str(video.get("content_type") or "").casefold()
    title = str(video.get("title") or "").casefold()
    return "top 10" in content_type or "top10" in content_type or "top 10" in title


_CHANNEL_PROFILE_CACHE = {"created_at": 0.0, "profiles": {}}
_CHANNEL_PROFILE_CACHE_SECONDS = 300


def _percentile(values, fraction):
    values = sorted(float(value or 0) for value in values if float(value or 0) > 0)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int(round((len(values) - 1) * fraction))))
    return values[index]


def _load_channel_performance_profile(project_type):
    """Learn metadata patterns from the channel's real synced performance data.

    The profile favors high-view, high-revenue, and high-RPM videos without
    allowing one outlier or a tiny high-RPM video to dominate. Generation still
    works if the database is unavailable.
    """
    normalized_type = "top10" if str(project_type).casefold() == "top10" else "solo"
    now = time.monotonic()
    cached = _CHANNEL_PROFILE_CACHE["profiles"].get(normalized_type)
    if cached and now - _CHANNEL_PROFILE_CACHE["created_at"] <= _CHANNEL_PROFILE_CACHE_SECONDS:
        return cached

    try:
        from database.db import get_saved_videos, get_top_youtube_video_revenue
        videos = list(get_saved_videos() or [])
        revenue_rows = list(get_top_youtube_video_revenue("lifetime", 250) or [])
    except Exception:
        videos, revenue_rows = [], []

    revenue_by_id = {
        str(row.get("video_id") or "").strip(): row
        for row in revenue_rows
        if str(row.get("video_id") or "").strip()
    }
    revenue_by_title = {
        normalize_title_key(row.get("title")): row
        for row in revenue_rows
        if normalize_title_key(row.get("title"))
    }

    records = []
    for video in videos:
        if (normalized_type == "top10") != _is_top10_video(video):
            continue
        title = _clean(video.get("title"))
        if not title:
            continue
        video_id = str(video.get("video_id") or "").strip()
        revenue_row = revenue_by_id.get(video_id) or revenue_by_title.get(normalize_title_key(title), {})
        views = max(float(video.get("views") or 0), float(revenue_row.get("views") or 0))
        revenue = max(
            float(video.get("estimated_revenue") or video.get("revenue") or 0),
            float(revenue_row.get("estimated_revenue") or revenue_row.get("amount") or 0),
        )
        rpm = max(
            float(video.get("estimated_rpm") or video.get("rpm") or 0),
            float(revenue_row.get("rpm") or 0),
        )
        likes = float(video.get("likes") or 0)
        comments = float(video.get("comments") or 0)
        records.append({
            "title": title,
            "views": views,
            "revenue": revenue,
            "rpm": rpm,
            "engagement": (likes + comments * 2) / max(1.0, views),
        })

    if not records:
        profile = {
            "tokens": Counter(), "phrases": Counter(), "titles": [],
            "ideal_length": 62, "separator_scores": {}, "sample_size": 0,
        }
        _CHANNEL_PROFILE_CACHE["created_at"] = now
        _CHANNEL_PROFILE_CACHE["profiles"][normalized_type] = profile
        return profile

    view_p90 = max(1.0, _percentile([r["views"] for r in records], .90))
    revenue_p90 = max(1.0, _percentile([r["revenue"] for r in records], .90))
    rpm_p90 = max(1.0, _percentile([r["rpm"] for r in records], .90))

    for record in records:
        view_score = min(1.25, math.log1p(record["views"]) / math.log1p(view_p90))
        revenue_score = min(1.25, math.log1p(record["revenue"] * 20) / math.log1p(revenue_p90 * 20))
        rpm_score = min(1.0, record["rpm"] / rpm_p90) if record["rpm"] > 0 else 0
        engagement_score = min(1.0, record["engagement"] / .06)
        # Views and revenue lead. RPM helps, but cannot let a low-view outlier win.
        record["performance_score"] = (
            view_score * .46 + revenue_score * .34 + rpm_score * .14 + engagement_score * .06
        )

    records.sort(key=lambda item: item["performance_score"], reverse=True)
    strongest = records[:min(40, len(records))]
    token_counter = Counter()
    phrase_counter = Counter()
    separator_scores = Counter()
    weighted_lengths = []

    for rank, record in enumerate(strongest):
        weight = record["performance_score"] * max(.35, 1 - rank / max(1, len(strongest) * 1.3))
        tokens = _meaningful_tokens(record["title"])
        for token in tokens:
            token_counter[token] += weight
        for left, right in zip(tokens, tokens[1:]):
            phrase_counter[f"{left} {right}"] += weight
        for separator in (" | ", ": ", " - ", " vs. ", " at the "):
            if separator in record["title"]:
                separator_scores[separator] += weight
        weighted_lengths.append((len(record["title"]), weight))

    total_length_weight = sum(weight for _, weight in weighted_lengths) or 1
    ideal_length = round(sum(length * weight for length, weight in weighted_lengths) / total_length_weight)
    ideal_length = max(45, min(82, ideal_length))

    profile = {
        "tokens": token_counter,
        "phrases": phrase_counter,
        "titles": [record["title"] for record in strongest],
        "ideal_length": ideal_length,
        "separator_scores": dict(separator_scores),
        "sample_size": len(records),
    }
    _CHANNEL_PROFILE_CACHE["created_at"] = now
    _CHANNEL_PROFILE_CACHE["profiles"][normalized_type] = profile
    return profile


def normalize_title_key(value):
    return re.sub(r"[^a-z0-9]+", " ", _clean(value).casefold()).strip()


def _load_channel_title_trends(project_type):
    profile = _load_channel_performance_profile(project_type)
    return profile["tokens"], profile["titles"]

def _score_title_candidate(title, player, happening, trend_tokens, profile=None):
    title = _clean(title)
    if not title or len(title) > MAX_TITLE_LENGTH:
        return -10_000
    profile = profile or {"tokens": trend_tokens, "phrases": Counter(), "ideal_length": 62, "separator_scores": {}}
    score = 0.0
    lowered = title.casefold()
    player_lower = _clean(player).casefold()
    if player_lower and player_lower in lowered:
        score += 24
    action = _detect_action(happening)
    play_type = _play_type_phrase(happening)
    if play_type.casefold() in lowered:
        score += 24
    signature = _detect_signature_action(happening)
    if signature and signature.get("key") == "jump_over_poster":
        if "jumps over" in lowered:
            score += 45
        elif "leaps over" in lowered:
            score += 38
        elif "jump-over" in lowered:
            score += 20
        else:
            score -= 12
    elif signature and signature.get("label", "").casefold() in lowered:
        score += 12
    elif action == "dunk" and any(term in lowered for term in ("dunk", "jumps over", "poster")):
        score += 14
    elif action == "block" and "block" in lowered:
        score += 14
    elif action == "pass" and any(term in lowered for term in ("pass", "assist", "no-look")):
        score += 14
    elif action == "shot" and any(term in lowered for term in ("winner", "buzzer", "clutch", "shot")):
        score += 14

    year = _extract_year(happening)
    event = _extract_event(happening)
    opponent = _extract_opponent(happening, player)
    if year and year in title:
        score += 6
    if event and any(token.casefold() in lowered for token in _meaningful_tokens(event)):
        score += 8
    if opponent and opponent.casefold() in lowered:
        score += 8

    title_tokens = _meaningful_tokens(title)
    token_counter = profile.get("tokens", trend_tokens)
    phrase_counter = profile.get("phrases", Counter())
    score += sum(min(4.5, float(token_counter[token]) / 5) for token in title_tokens)
    score += sum(min(4, float(phrase_counter[f"{a} {b}"]) / 4) for a, b in zip(title_tokens, title_tokens[1:]))

    ideal = int(profile.get("ideal_length") or 62)
    score -= abs(len(title) - ideal) * .10
    for separator, separator_score in profile.get("separator_scores", {}).items():
        if separator in title:
            score += min(3, float(separator_score) / 5)

    if title.casefold().startswith(f"{player_lower} {player_lower}"):
        score -= 100
    if "highlight highlight" in lowered or "dunk dunk" in lowered:
        score -= 30
    # Avoid generic hype when exact searchable context is available.
    if any(word in lowered for word in ("incredible", "unforgettable", "amazing")) and (opponent or event):
        score -= 3
    return score

def _fit_title(value):
    title = _clean(value).strip(" -–—:|")
    if len(title) <= MAX_TITLE_LENGTH:
        return title
    shortened = title[:MAX_TITLE_LENGTH].rsplit(" ", 1)[0].rstrip(" -–—:|")
    return shortened or title[:MAX_TITLE_LENGTH]


def _youtube_tag_cost(tag, has_previous=False):
    """Conservative version of YouTube's encoded keyword budget.

    YouTube accepts a list of keyword strings, but phrases containing spaces are
    effectively quoted when the total 500-character keyword limit is evaluated.
    CourtVision uses a 470-character ceiling so punctuation and API encoding can
    never push an apparently valid tag set over YouTube's limit.
    """
    value = str(tag or "")
    phrase_quotes = 2 if any(character.isspace() for character in value) else 0
    separator = 1 if has_previous else 0
    return len(value) + phrase_quotes + separator


def trim_tags(tags):
    final = []
    seen = set()
    total = 0

    for raw_tag in tags:
        # Commas delimit tags in CourtVision's editor, so remove embedded commas.
        # Keep useful basketball punctuation such as apostrophes and double quotes
        # in measurements like 7'2".
        tag = _clean(raw_tag).replace(",", " ").strip(" ,")
        tag = " ".join(tag.split())
        key = tag.casefold()

        if (
            not tag
            or key in seen
            or len(tag) > 60
            or not any(character.isalnum() for character in tag)
        ):
            continue

        extra = _youtube_tag_cost(tag, has_previous=bool(final))
        if total + extra > MAX_TAG_LENGTH:
            continue

        final.append(tag)
        seen.add(key)
        total += extra

    return ", ".join(final)


def _solo_tags(player, happening, title):
    action = _detect_action(happening)
    play_type = _play_type_phrase(happening)
    opponent = _extract_opponent(happening, player)
    event = _extract_event(happening)
    year = _extract_year(happening)
    height = _extract_height(happening)
    profile = _load_channel_performance_profile("solo")
    signature = _detect_signature_action(happening)

    tags = [
        player,
        f"{player} highlights" if player else "",
        f"{player} {play_type}" if player else "",
        f"{player} NBA highlights" if player else "",
        play_type,
    ]
    if signature:
        tags += list(signature.get("tag_phrases") or [])
        tags += [f"{player} {phrase}" for phrase in signature.get("tag_phrases", []) if player]

    if action == "dunk":
        tags += [f"{player} dunk", f"{player} poster dunk", "poster dunk", "slam dunk", "NBA dunks"]
    elif action == "block":
        tags += [f"{player} block", "NBA blocks", "best NBA blocks"]
    elif action == "pass":
        tags += [f"{player} pass", f"{player} assists", "NBA assists", "best NBA passes"]
    elif action == "shot":
        tags += [f"{player} clutch", f"{player} game winner", "NBA clutch moments", "NBA game winners"]

    tags += [
        opponent,
        f"{player} over {opponent}" if player and opponent else "",
        f"{player} vs {opponent}" if player and opponent else "",
        f"{play_type} over {opponent}" if opponent else "",
        event,
        f"{player} {event}" if player and event else "",
        f"{event} basketball" if event else "",
        f"{year} basketball" if year else "",
        f"{height} {play_type}" if height else "",
        "NBA highlights", "basketball highlights", "NBA history",
        "classic NBA", "NBA legends", "iconic NBA moments", "NBATop10",
    ]

    # Add only a few proven channel terms, never whole old titles.
    input_tokens = set(_meaningful_tokens(f"{player} {happening} {title}"))
    proven_terms = [
        token for token, _ in profile["tokens"].most_common(25)
        if token not in input_tokens and token not in STOPWORDS and len(token) >= 4
    ][:4]
    tags.extend(proven_terms)
    return trim_tags(tags)

def _top10_tags(subject, player, happening):
    base = player or subject
    tags = [
        base, f"{base} top 10 plays", f"Top 10 {base} plays", f"{base} highlights",
        f"{base} best plays", f"{base} career highlights", "NBA Top 10",
        "top 10 NBA plays", "best NBA plays", "NBA highlights", "basketball highlights",
        "NBA legends", "NBA history", "classic NBA", "NBATop10", "basketball"
    ]
    if happening:
        tags.extend([happening, f"{base} {happening}"])
    return trim_tags(tags)


def _build_solo_title(player, happening):
    """Generate and score multiple unique Solo Highlight title candidates."""
    player = _smart_title_case(player) if player else "NBA"
    detail = _strip_duplicate_player(happening, player)
    action = _detect_action(detail)
    play_type = _play_type_phrase(detail)
    opponent = _extract_opponent(detail, player)
    event = _extract_event(detail)
    year = _extract_year(detail)
    height = _extract_height(detail)  # explicit input only
    profile = _load_channel_performance_profile("solo")
    trend_tokens = profile["tokens"]

    opponent_display = _clean(f"{height} {opponent}") if height and opponent else opponent
    context = event or year
    candidates = []
    signature = _detect_signature_action(detail)
    signature_key = signature.get("key") if signature else ""

    if signature_key == "jump_over_poster" and opponent_display:
        candidates += [
            f"{player} Jumps Over {opponent_display} for the Poster Dunk" + (f" | {context}" if context else ""),
            f"{player}'s Jump-Over Poster Dunk on {opponent_display}" + (f" | {context}" if context else ""),
            f"{player} Leaps Over {opponent_display} for a Slam Dunk" + (f" at the {context}" if context else ""),
        ]
    elif signature:
        if opponent_display:
            candidates += [
                f"{player} {play_type} Over {opponent_display}" + (f" | {context}" if context else ""),
                f"{player}'s {play_type} vs. {opponent_display}" + (f" | {context}" if context else ""),
            ]
        else:
            candidates += [
                f"{player} {play_type}" + (f" | {context}" if context else ""),
                f"{player}'s {play_type}" + (f" at the {context}" if context else ""),
            ]

    if action == "dunk":
        if opponent_display:
            candidates += [
                f"{player} {play_type} Over {opponent_display}" + (f" | {context}" if context else ""),
                f"{player} Jumps Over {opponent_display}" + (f" at the {context}" if context else ""),
                f"{player}'s {play_type} Over {opponent_display}" + (f" | {context}" if context else ""),
            ]
        else:
            candidates += [
                f"{player} {play_type}" + (f" at the {context}" if context else ""),
                f"{player}'s {play_type}" + (f" | {context}" if context else ""),
            ]
    elif action == "block":
        candidates += [
            f"{player} {play_type}" + (f" on {opponent}" if opponent else "") + (f" | {context}" if context else ""),
            f"{player}'s {play_type}" + (f" vs. {opponent}" if opponent else "") + (f" at the {context}" if context else ""),
        ]
    elif action == "pass":
        candidates += [
            f"{player} {play_type}" + (f" vs. {opponent}" if opponent else "") + (f" | {context}" if context else ""),
            f"{player}'s {play_type}" + (f" at the {context}" if context else ""),
        ]
    elif action == "shot":
        candidates += [
            f"{player} {play_type}" + (f" vs. {opponent}" if opponent else "") + (f" | {context}" if context else ""),
            f"{player}'s {play_type}" + (f" at the {context}" if context else ""),
        ]
    else:
        candidates += [
            f"{player} {play_type}" + (f" vs. {opponent}" if opponent else "") + (f" | {context}" if context else ""),
            f"{player}'s {play_type}" + (f" at the {context}" if context else ""),
        ]

    concise_detail = _sentence(detail).rstrip(".")
    if concise_detail:
        candidates.append(f"{player}: {concise_detail}")
    candidates.append(f"{player} {play_type}")

    fitted = []
    seen = set()
    for candidate in candidates:
        candidate = candidate.replace("the 2000 Olympics", "2000 Olympics")
        formatted = _fit_title(_title_case_solo(candidate))
        key = formatted.casefold()
        if formatted and key not in seen:
            fitted.append(formatted)
            seen.add(key)
    return max(
        fitted,
        key=lambda candidate: _score_title_candidate(candidate, player, detail, trend_tokens, profile),
    )

def _solo_context_suffix(event="", year=""):
    if event:
        return f" at the {event}"
    if year:
        return f" in {year}"
    return ""


def _solo_action_description(player, play_type, opponent="", event="", year="", height="", signature=None):
    """Build specific Solo Highlight copy using only details supported by the user's input."""
    signature_key = (signature or {}).get("key", "")
    opponent_display = _clean(f"{height} {opponent}") if height and opponent else opponent
    context = _solo_context_suffix(event, year)
    target = f" {opponent_display}" if opponent_display else ""

    if signature_key == "jump_over_poster":
        if opponent_display:
            first = f'{player} jumps over {opponent_display} and throws down the slam{context}.'
            second = (
                f'The jump over {opponent} is the defining detail: {player} gets above the defender '
                'before finishing at the rim, making this far more specific than a standard poster dunk.'
            )
        else:
            first = f'{player} clears the defender and finishes a jump-over poster dunk{context}.'
            second = 'The leap over the defender is the defining detail, followed immediately by the finish at the rim.'
        return first, second

    signature_templates = {
        "windmill_dunk": (
            f'{player} unleashes a windmill dunk{target}{context}.',
            'The full arm swing and finish are the defining parts of the play, not just the fact that it ends in a dunk.'
        ),
        "reverse_dunk": (
            f'{player} finishes with a reverse dunk{target}{context}.',
            'The play is built around the reverse finish, with the ball protected on the opposite side of the rim.'
        ),
        "tomahawk_dunk": (
            f'{player} powers down a tomahawk dunk{target}{context}.',
            'The high one-arm load and forceful downward finish give this dunk its specific shape and identity.'
        ),
        "cradle_dunk": (
            f'{player} completes a cradle dunk{target}{context}.',
            'The ball control through the gather and cradle motion is what separates this finish from a routine slam.'
        ),
        "double_clutch_dunk": (
            f'{player} converts a double-clutch dunk{target}{context}.',
            'The midair adjustment before the finish is the key detail, forcing the play to change after takeoff.'
        ),
        "360_dunk": (
            f'{player} completes a 360 dunk{target}{context}.',
            'The full rotation is the defining element of the play and stays central to the finish at the rim.'
        ),
        "between_legs_dunk": (
            f'{player} throws down a between-the-legs dunk{target}{context}.',
            'The ball transfer beneath the legs is the signature movement that defines the entire finish.'
        ),
        "self_alley_oop_dunk": (
            f'{player} creates and finishes a self alley-oop dunk{target}{context}.',
            'The self-pass and immediate finish make this a two-part play rather than a standard dunk attempt.'
        ),
        "alley_oop_dunk": (
            f'{player} finishes an alley-oop dunk{target}{context}.',
            'The timing between the pass, catch, and finish is the central sequence of the play.'
        ),
        "putback_dunk": (
            f'{player} attacks the miss and finishes a putback dunk{target}{context}.',
            'The instant reaction off the rebound is what creates the play before the finish at the rim.'
        ),
        "behind_back_pass": (
            f'{player} delivers a behind-the-back pass{target}{context}.',
            'The pass changes direction behind the body, creating the angle that makes this assist different from a routine feed.'
        ),
        "overhead_pass": (
            f'{player} fires an overhead pass{target}{context}.',
            'The release over the defense and the direct passing lane are the defining details of the play.'
        ),
        "no_look_pass": (
            f'{player} delivers a no-look pass{target}{context}.',
            'The play is defined by the misdirection: the eyes sell one option while the ball goes somewhere else.'
        ),
        "full_court_pass": (
            f'{player} launches a full-court pass{target}{context}.',
            'The distance, accuracy, and immediate transition opportunity are the specific features that make the pass stand out.'
        ),
        "baseball_pass": (
            f'{player} throws a baseball pass{target}{context}.',
            'The long one-handed delivery creates a fast break before the defense can recover.'
        ),
        "wraparound_pass": (
            f'{player} threads a wraparound pass{target}{context}.',
            'The ball travels around the defender rather than through a normal passing window.'
        ),
        "cross_court_pass": (
            f'{player} sends a cross-court pass{target}{context}.',
            'The play depends on moving the ball across the floor into a passing lane that is not directly in front of the passer.'
        ),
        "reverse_layup": (
            f'{player} finishes a reverse layup{target}{context}.',
            'Using the opposite side of the rim is the key detail, with the basket helping shield the ball from the defense.'
        ),
        "circus_layup": (
            f'{player} converts a circus layup{target}{context}.',
            'The unusual body angle and improvised release make this finish different from a standard drive to the rim.'
        ),
        "double_clutch_layup": (
            f'{player} completes a double-clutch layup{target}{context}.',
            'The midair change before release is the defining movement, allowing the finish to adjust around the defense.'
        ),
        "finger_roll": (
            f'{player} finishes with a finger roll{target}{context}.',
            'The soft upward release off the fingertips is the defining feature of the finish.'
        ),
        "euro_step": (
            f'{player} uses a Euro-step to finish{target}{context}.',
            'The two-step change of direction creates the opening before the ball reaches the rim.'
        ),
        "up_and_under": (
            f'{player} scores with an up-and-under finish{target}{context}.',
            'The initial fake moves the defender before the second motion creates the actual scoring angle.'
        ),
        "buzzer_beater": (
            f'{player} hits a buzzer-beater{target}{context}.',
            'The shot and the expiring clock are inseparable parts of the moment, with no possession left afterward.'
        ),
        "game_winner": (
            f'{player} hits the game-winner{target}{context}.',
            'The score, clock, and final result give the shot its meaning beyond the make itself.'
        ),
        "step_back_three": (
            f'{player} creates space for a step-back three{target}{context}.',
            'The backward separation move is the defining action before the three-point release.'
        ),
        "fadeaway": (
            f'{player} knocks down a fadeaway jumper{target}{context}.',
            'The backward body movement creates the shooting window while increasing the difficulty of the release.'
        ),
        "chasedown_block": (
            f'{player} erases the shot with a chase-down block{target}{context}.',
            'The recovery from behind is the defining part of the play, ending with the block at the rim.'
        ),
        "game_saving_block": (
            f'{player} makes a game-saving block{target}{context}.',
            'The defensive stop matters because of the immediate game situation, not only the block itself.'
        ),
        "ankle_breaker": (
            f'{player} drops the defender with an ankle-breaking crossover{target}{context}.',
            'The sudden change of direction creates the separation and defines the play before the next move.'
        ),
    }

    if signature_key in signature_templates:
        return signature_templates[signature_key]

    action = _detect_action(play_type)
    if action == "dunk":
        first = f'{player} finishes a {play_type.lower()}{target}{context}.'
        second = 'The takeoff, contact, and finish at the rim are the specific parts of the play shown in this highlight.'
    elif action == "pass":
        first = f'{player} delivers a {play_type.lower()}{target}{context}.'
        second = 'The passing angle and placement create the opportunity and define the sequence.'
    elif action == "layup":
        first = f'{player} converts a {play_type.lower()}{target}{context}.'
        second = 'The footwork and release around the rim are the defining details of the finish.'
    elif action == "block":
        first = f'{player} records a {play_type.lower()}{target}{context}.'
        second = 'The recovery, timing, and point of contact at the rim define the defensive play.'
    elif action == "shot":
        first = f'{player} makes the {play_type.lower()}{target}{context}.'
        second = 'The shot type and game situation are the specific details that give the play its identity.'
    else:
        first = f'{player} completes the {play_type.lower()}{target}{context}.'
        second = 'This video focuses on the exact movement and result described in the play.'
    return first, second


def generate_solo_metadata(subject, player_name="", happening=""):
    player = _clean(player_name)
    happening = _clean(happening)
    if not player:
        subject_tokens = _clean(subject).split()
        player = " ".join(subject_tokens[:2]) if subject_tokens else "NBA"

    player_display = _smart_title_case(player)
    clean_happening = _strip_duplicate_player(happening, player)
    title = _build_solo_title(player, clean_happening)
    event = _extract_event(clean_happening)
    opponent = _extract_opponent(clean_happening, player)
    play_type = _play_type_phrase(clean_happening)
    height = _extract_height(clean_happening)
    year = _extract_year(clean_happening)
    signature = _detect_signature_action(clean_happening)

    first_sentence, second_sentence = _solo_action_description(
        player=player_display,
        play_type=play_type,
        opponent=opponent,
        event=event,
        year=year,
        height=height,
        signature=signature,
    )

    player_hashtag = re.sub(r'[^A-Za-z0-9]', '', player_display)
    description = (
        f"{first_sentence}\n\n"
        f"{second_sentence}\n\n"
        "Subscribe to NBATop10 for more NBA Top 10 videos, classic NBA highlights, "
        "legendary dunks, game-winners, blocks, passes, and basketball history.\n\n"
        f"#NBA #{player_hashtag} #Basketball"
    )

    return {
        "title": title,
        "description": description,
        "tags": _solo_tags(player_display, clean_happening, title),
        "thumbnail_plan": "Use the strongest action frame, keep the player and ball large and sharp, darken the crowd, preserve the original jersey details, and use little or no text so the image reads instantly on mobile.",
    }

def generate_top10_metadata(subject, clip_titles=None, player_name="", happening=""):
    subject = _clean(subject) or _clean(player_name) or "NBA"
    player = _clean(player_name) or subject
    title_subject = _smart_title_case(player)
    trend_tokens, _ = _load_channel_title_trends("top10")
    candidates = [
        f"{title_subject} Top 10 Plays of All Time",
        f"Top 10 {title_subject} Plays of All Time",
        f"{title_subject}'s 10 Greatest Plays",
    ]
    title = max(
        (_fit_title(candidate) for candidate in candidates),
        key=lambda candidate: _score_title_candidate(candidate, player, happening or "top 10 plays", trend_tokens)
    )

    clips = [clean_title_from_filename(item) for item in (clip_titles or []) if _clean(item)][:10]
    lines = [
        f"{title}\n",
        f"A countdown of {_smart_title_case(player)}'s greatest plays, built from the most memorable highlights, dunks, passes, clutch moments, and career-defining sequences."
    ]
    if happening:
        lines.append(_sentence(happening))
    lines.extend([
        "\nWatch the full ranking, then comment with the play you would put at No. 1.",
        "\nSubscribe to NBATop10 for NBA countdowns, classic highlights, legendary players, and basketball history."
    ])
    if clips:
        lines.append("\nCountdown:")
        for index, clip in enumerate(clips, 1):
            lines.append(f"#{11 - index}: {clip}")
    lines.append(f"\n#NBA #{re.sub(r'[^A-Za-z0-9]', '', player)} #NBATop10")

    return {
        "title": title,
        "description": "\n".join(lines),
        "tags": _top10_tags(subject, player, happening),
        "thumbnail_plan": "Use the strongest action shot, keep the player large, darken the crowd, brighten the player and ball, and use concise red-and-white Top 10 text that stays readable on mobile."
    }
