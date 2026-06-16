import os
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


def get_youtube_service():

    if not API_KEY:
        raise Exception("Missing YOUTUBE_API_KEY in .env file")

    return build(
        "youtube",
        "v3",
        developerKey=API_KEY
    )


def get_channel_stats_by_handle(handle=CHANNEL_HANDLE):

    youtube = get_youtube_service()

    response = youtube.channels().list(
        part="statistics,snippet,contentDetails",
        forHandle=handle
    ).execute()

    return response


def get_channel_uploads_playlist_id(handle=CHANNEL_HANDLE):

    response = get_channel_stats_by_handle(handle)

    items = response.get("items", [])

    if not items:
        return None

    channel = items[0]

    return channel["contentDetails"]["relatedPlaylists"]["uploads"]


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
        ).execute()

        for item in response.get("items", []):

            snippet = item.get("snippet", {})

            resource = snippet.get("resourceId", {})

            video_id = resource.get("videoId")

            if not video_id:
                continue

            thumbnail = ""

            thumbnails = snippet.get("thumbnails", {})

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
        ).execute()

        all_items.extend(
            response.get("items", [])
        )

    return {
        "items": all_items
    }