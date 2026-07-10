import os
import time
from dotenv import dotenv_values
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

ENV_PATH = os.path.join(BASE_DIR, ".env")

env = dotenv_values(
    ENV_PATH,
    encoding="utf-8-sig"
)

API_KEY = env.get("YOUTUBE_API_KEY")
CHANNEL_HANDLE = env.get("CHANNEL_HANDLE", "nbatopten")

_YOUTUBE_SERVICE = None
_UPLOADS_PLAYLIST_CACHE = {}


def get_youtube_service():
    global _YOUTUBE_SERVICE

    if not API_KEY:
        raise Exception("Missing YOUTUBE_API_KEY in .env file")

    if _YOUTUBE_SERVICE is None:
        _YOUTUBE_SERVICE = build(
            "youtube",
            "v3",
            developerKey=API_KEY,
            cache_discovery=False
        )

    return _YOUTUBE_SERVICE


def _execute_with_retry(request, attempts=3):
    last_error = None

    for attempt in range(attempts):
        try:
            return request.execute()
        except Exception as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(0.6 * (attempt + 1))

    raise last_error


def get_channel_stats_by_handle(handle=CHANNEL_HANDLE):
    youtube = get_youtube_service()

    response = youtube.channels().list(
        part="statistics,snippet,contentDetails",
        forHandle=handle
    )
    response = _execute_with_retry(response)

    return response


def get_channel_uploads_playlist_id(handle=CHANNEL_HANDLE):
    if handle in _UPLOADS_PLAYLIST_CACHE:
        return _UPLOADS_PLAYLIST_CACHE[handle]

    response = get_channel_stats_by_handle(handle)
    items = response.get("items", [])

    if not items:
        return None

    channel = items[0]
    uploads_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    _UPLOADS_PLAYLIST_CACHE[handle] = uploads_id

    return uploads_id


def get_all_channel_videos(handle=CHANNEL_HANDLE):
    youtube = get_youtube_service()
    uploads_playlist_id = get_channel_uploads_playlist_id(handle)

    if not uploads_playlist_id:
        return []

    all_videos = []
    next_page_token = None

    while True:
        response = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token
        )
        response = _execute_with_retry(response)

        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            resource = snippet.get("resourceId", {})
            video_id = resource.get("videoId")

            if not video_id:
                continue

            thumbnails = snippet.get("thumbnails", {})
            thumbnail = ""

            if "maxres" in thumbnails:
                thumbnail = thumbnails["maxres"].get("url", "")
            elif "high" in thumbnails:
                thumbnail = thumbnails["high"].get("url", "")
            elif "medium" in thumbnails:
                thumbnail = thumbnails["medium"].get("url", "")

            all_videos.append({
                "title": snippet.get("title", "Unknown"),
                "video_id": video_id,
                "published": snippet.get("publishedAt", ""),
                "thumbnail": thumbnail
            })

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

    return all_videos


def get_video_stats(video_ids):
    youtube = get_youtube_service()

    if not video_ids:
        return {"items": []}

    all_items = []

    for i in range(0, len(video_ids), 50):
        batch = [
            v for v in video_ids[i:i + 50]
            if v
        ]

        if not batch:
            continue

        response = youtube.videos().list(
            part="statistics,snippet",
            id=",".join(batch)
        )
        response = _execute_with_retry(response)

        all_items.extend(response.get("items", []))

    return {
        "items": all_items
    }
