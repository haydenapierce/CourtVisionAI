from fastapi import APIRouter
from services.youtube_oauth import get_authenticated_service

router = APIRouter()

@router.get("/dashboard/stats")
def stats():

    youtube, _ = get_authenticated_service()

    res = youtube.channels().list(
        part="statistics",
        mine=True
    ).execute()

    s = res["items"][0]["statistics"]

    return {
        "subscribers": int(s.get("subscriberCount", 0)),
        "total_views": int(s.get("viewCount", 0)),
        "video_count": int(s.get("videoCount", 0))
    }