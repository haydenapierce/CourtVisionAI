from fastapi import APIRouter
from services.youtube_oauth import get_authenticated_service

router = APIRouter()

@router.get("/youtube/stats")
def youtube_stats():

    youtube, _ = get_authenticated_service()

    res = youtube.channels().list(
        part="statistics",
        mine=True
    ).execute()

    s = res["items"][0]["statistics"]

    return {
        "views": int(s.get("viewCount", 0)),
        "subscribers": int(s.get("subscriberCount", 0)),
        "videos": int(s.get("videoCount", 0))
    }