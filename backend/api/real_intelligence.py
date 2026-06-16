from fastapi import APIRouter
from services.youtube_oauth import get_authenticated_service

router = APIRouter()


# =========================
# REAL VIDEOS
# =========================
@router.get("/real/videos")
def real_videos():

    youtube, _ = get_authenticated_service()

    res = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=30
    ).execute()

    videos = []

    for v in res.get("items", []):
        videos.append({
            "title": v["snippet"]["title"],
            "video_id": v["id"]["videoId"],
            "thumbnail": v["snippet"]["thumbnails"]["high"]["url"],
            "published": v["snippet"]["publishedAt"]
        })

    return {"videos": videos}


# =========================
# REAL ANALYSIS ENGINE
# =========================
@router.get("/real/analyze")
def analyze():

    youtube, _ = get_authenticated_service()

    res = youtube.channels().list(
        part="statistics",
        mine=True
    ).execute()

    s = res["items"][0]["statistics"]

    views = int(s.get("viewCount", 0))
    subs = int(s.get("subscriberCount", 0))
    videos = int(s.get("videoCount", 1))

    avg = views / videos

    score = (subs * 0.02) + (avg * 0.0001)

    return {
        "score": round(score, 2),
        "avg_views": int(avg),
        "level": "Elite" if score > 80 else "Growing"
    }


# =========================
# CONTENT GAP DETECTOR
# =========================
@router.get("/real/gaps")
def gaps():

    youtube, _ = get_authenticated_service()

    res = youtube.search().list(
        part="snippet",
        forMine=True,
        type="video",
        maxResults=50
    ).execute()

    titles = " ".join([v["snippet"]["title"].lower() for v in res.get("items", [])])

    nba_targets = [
        "jokic", "giannis", "luka",
        "kawhi", "tatum", "durant",
        "westbrook", "shaq"
    ]

    missing = [p for p in nba_targets if p not in titles]

    return {
        "missing_players": missing,
        "opportunity_score": len(missing) * 10
    }


# =========================
# NEXT VIDEO AI ENGINE
# =========================
@router.get("/real/next")
def next_video():

    youtube, _ = get_authenticated_service()

    res = youtube.channels().list(
        part="statistics",
        mine=True
    ).execute()

    s = res["items"][0]["statistics"]

    views = int(s.get("viewCount", 0))
    subs = int(s.get("subscriberCount", 0))

    avg = views / 50

    if avg > 15000:
        rec = "Top 10 LeBron Clutch Moments"
    elif avg > 8000:
        rec = "Top 10 Curry 3PT Runs"
    else:
        rec = "Top 10 Underrated NBA Legends"

    return {
        "recommendation": rec,
        "reason": "Based on real channel performance data"
    }