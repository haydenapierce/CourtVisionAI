from fastapi import APIRouter, Query, UploadFile, File
from database.db import get_saved_videos
from data.player_database import NBA_PLAYERS
from PIL import Image, ImageStat
import io

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
        score += 160

    if name in mega_names:
        score += 85

    if name in low_profit_players:
        score -= 80

    return score


def expected_rpm(player, video_length=3, title_type="Top 10"):
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))

    if name in REAL_PLAYER_RPM:
        rpm = REAL_PLAYER_RPM[name]
    else:
        rpm = 1.00

        if "1960" in era or "1970" in era or "1980" in era:
            rpm += 0.65

        if "1990" in era:
            rpm += 0.35

        if "legend" in content_type or "nostalgia" in content_type:
            rpm += 0.35

        if "modern" in content_type:
            rpm -= 0.20

    if int(video_length) >= 5:
        rpm += 0.20

    if int(video_length) >= 8:
        rpm += 0.20

    if normalize(title_type) == "career":
        rpm += 0.15

    if normalize(title_type) == "clutch":
        rpm += 0.10

    if normalize(title_type) == "poster":
        rpm -= 0.15

    return round(max(rpm, 0.02), 2)


def copyright_risk(player, title_type="Top 10"):
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))

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
        risk += 20

    if normalize(title_type) == "poster":
        risk += 15
    if normalize(title_type) == "clutch":
        risk += 10
    if normalize(title_type) == "career":
        risk -= 5

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


def recommendation_text(player, score, rpm, risk):
    name = player.get("name", "")

    if risk <= 35 and rpm >= 2:
        return f"{name} is a strong money-safe idea, but still use the conservative range before expecting a breakout."

    if score >= 250:
        return f"{name} has good upside, but the projection is shown as a range because views can vary a lot."

    if rpm >= 2:
        return f"{name} has solid RPM potential, but views may be more modest unless the thumbnail/title are strong."

    if risk >= 70:
        return f"{name} could be risky for monetization. Use caution with modern NBA footage."

    return f"{name} is a decent idea, but treat this as a moderate upside video."


def build_view_range(score, player, already_done=False):
    name = normalize(player.get("name", ""))
    era = normalize(player.get("era", ""))
    content_type = normalize(player.get("content_type", ""))

    base = max(10000, score * 350)

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
        low = int(base * 0.85)
        high = int(base * 2.0)
    elif "legend" in content_type or "nostalgia" in content_type or "1980" in era or "1990" in era:
        low = int(base * 0.55)
        high = int(base * 1.25)
    else:
        low = int(base * 0.35)
        high = int(base * 0.95)

    if already_done:
        low = int(low * 0.35)
        high = int(high * 0.45)

    low = max(5000, low)
    high = max(low + 5000, high)

    return low, high


def build_prediction(player, already_done=False, video_length=3, title_type="Top 10"):
    score = score_player(player)
    rpm = expected_rpm(player, video_length, title_type)
    risk = copyright_risk(player, title_type)

    view_low, view_high = build_view_range(score, player, already_done)
    projected_views = int((view_low + view_high) / 2)

    revenue_low = round((view_low / 1000) * rpm, 2)
    revenue_high = round((view_high / 1000) * rpm, 2)
    projected_revenue = round((revenue_low + revenue_high) / 2, 2)

    subscriber_low = subscriber_gain_prediction(view_low, player)
    subscriber_high = subscriber_gain_prediction(view_high, player)
    projected_subscribers = int((subscriber_low + subscriber_high) / 2)

    return {
        **player,
        "top_10_done": already_done,
        "recommended_score": score,
        "expected_rpm": rpm,
        "copyright_risk": risk,

        "projected_views": projected_views,
        "projected_views_low": view_low,
        "projected_views_high": view_high,

        "projected_revenue": projected_revenue,
        "projected_revenue_low": revenue_low,
        "projected_revenue_high": revenue_high,

        "projected_subscribers": projected_subscribers,
        "projected_subscribers_low": subscriber_low,
        "projected_subscribers_high": subscriber_high,

        "video_idea": f"{player.get('name', '')} {title_type} Plays",
        "recommendation": recommendation_text(player, score, rpm, risk)
    }


def build_players():
    saved_videos = get_saved_videos()
    players = []

    for p in NBA_PLAYERS:
        done = top_10_done(p.get("name", ""), saved_videos)
        players.append(build_prediction(p, done))

    players.sort(
        key=lambda x: (
            x.get("projected_revenue_high", 0),
            x.get("recommended_score", 0)
        ),
        reverse=True
    )

    return players


def score_thumbnail(image):
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


@router.get("/idea-lab/top-50")
def top_50():
    players = build_players()

    not_done = [
        p for p in players
        if p.get("top_10_done") is False
    ]

    return {
        "top_50": not_done[:50]
    }


@router.get("/missing-legends")
def missing_legends():
    players = build_players()

    missing = []

    for p in players:
        if p.get("top_10_done"):
            continue

        is_good_missing = (
            p.get("hall_of_fame")
            or normalize(p.get("priority", "")) in ["elite", "high"]
            or p.get("recommended_score", 0) >= 180
            or p.get("projected_revenue_high", 0) >= 100
        )

        if is_good_missing:
            missing.append(p)

    missing.sort(
        key=lambda x: (
            x.get("projected_revenue_high", 0),
            x.get("recommended_score", 0),
            -x.get("copyright_risk", 100)
        ),
        reverse=True
    )

    return {
        "total_missing": len(missing),
        "missing_legends": missing[:75]
    }


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

    for p in NBA_PLAYERS:
        if normalize(p.get("name", "")) == query:
            done = top_10_done(p.get("name", ""), saved_videos)
            prediction = build_prediction(p, done)

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

    for p in NBA_PLAYERS:
        if normalize(p.get("name", "")) == query:
            done = top_10_done(p.get("name", ""), saved_videos)

            prediction = build_prediction(
                p,
                done,
                video_length,
                title_type
            )

            return {
                "found": True,
                "simulation": prediction
            }

    return {
        "found": False,
        "message": "Player not found"
    }


@router.post("/thumbnail-analyzer/analyze")
async def analyze_thumbnail(file: UploadFile = File(...)):
    contents = await file.read()

    image = Image.open(io.BytesIO(contents))
    result = score_thumbnail(image)

    return {
        "filename": file.filename,
        "analysis": result
    }