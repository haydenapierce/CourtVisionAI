import os
import re
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from services.youtube_oauth import get_authenticated_service


YOUTUBE_TAG_SAFE_LIMIT = 470
YOUTUBE_TAG_MAX_ITEM_LENGTH = 60


def _normalize_youtube_tag(value):
    tag = str(value or "").replace("\r", " ").replace("\n", " ").replace("\t", " ")
    tag = tag.replace(",", " ")
    tag = re.sub(r"\s+", " ", tag).strip(" ,")
    return tag


def youtube_tag_encoded_cost(tag, has_previous=False):
    value = str(tag or "")
    phrase_quotes = 2 if any(character.isspace() for character in value) else 0
    separator = 1 if has_previous else 0
    return len(value) + phrase_quotes + separator


def sanitize_youtube_tags(tags, max_cost=YOUTUBE_TAG_SAFE_LIMIT):
    """Return an API-safe, ranked-in-input-order YouTube tag payload.

    The UI stores tags as comma-separated text. This function is intentionally
    called again immediately before upload so manual edits cannot bypass the
    YouTube keyword limit or introduce malformed/duplicate tags.
    """
    raw_items = tags if isinstance(tags, (list, tuple)) else str(tags or "").split(",")
    accepted = []
    removed = []
    seen = set()
    encoded_cost = 0

    for raw_item in raw_items:
        tag = _normalize_youtube_tag(raw_item)
        key = tag.casefold()
        reason = ""

        if not tag:
            reason = "empty"
        elif not any(character.isalnum() for character in tag):
            reason = "punctuation_only"
        elif len(tag) > YOUTUBE_TAG_MAX_ITEM_LENGTH:
            reason = "too_long"
        elif key in seen:
            reason = "duplicate"
        else:
            cost = youtube_tag_encoded_cost(tag, has_previous=bool(accepted))
            if encoded_cost + cost > max_cost:
                reason = "over_youtube_limit"
            else:
                accepted.append(tag)
                seen.add(key)
                encoded_cost += cost

        if reason and tag:
            removed.append({"tag": tag, "reason": reason})

    return {
        "tags": accepted,
        "csv": ", ".join(accepted),
        "encoded_cost": encoded_cost,
        "limit": max_cost,
        "removed": removed,
        "valid": encoded_cost <= max_cost,
    }


def explain_youtube_error(error):
    text=str(error or "Unknown YouTube error")
    lower=text.lower()
    code="youtube_unknown"
    message="YouTube could not complete the request."
    resolution="Retry once. If it fails again, reconnect YouTube and review the backend terminal detail."
    if "invalidtags" in lower or "invalid video keywords" in lower or "invalid tags" in lower:
        code="youtube_invalid_tags"; message="YouTube rejected one or more video tags."; resolution="Review the Tags field, then regenerate or remove the rejected keyword. Reconnecting YouTube will not fix this metadata error."
    elif "quota" in lower or "dailylimitexceeded" in lower:
        code="youtube_quota_exceeded"; message="The YouTube API daily quota has been reached."; resolution="Wait for the Google API quota to reset, or increase the YouTube Data API quota in Google Cloud Console."
    elif "insufficient" in lower or "scope" in lower or "permission" in lower or "forbidden" in lower:
        code="youtube_permission_missing"; message="CourtVision does not currently have the required YouTube permission."; resolution="Delete backend/token_youtube_analytics.json, restart the backend, and sign in again while accepting every requested permission."
    elif "invalid_grant" in lower or "token" in lower or "unauthorized" in lower or "401" in lower:
        code="youtube_token_expired"; message="The saved YouTube authorization is expired or invalid."; resolution="Delete backend/token_youtube_analytics.json, restart CourtVision, then reconnect the correct YouTube channel."
    elif "uploadlimitexceeded" in lower:
        code="youtube_upload_limit"; message="The channel has reached its current YouTube upload limit."; resolution="Wait and retry later, or upload manually through YouTube Studio."
    elif "thumbnail" in lower:
        code="youtube_thumbnail_rejected"; message="YouTube rejected the custom thumbnail."; resolution="Use a JPG or PNG under 2 MB at 1280×720, then retry the upload or upload the thumbnail later in Studio."
    elif "publishat" in lower or "schedule" in lower:
        code="youtube_schedule_invalid"; message="The scheduled publishing time is invalid."; resolution="Choose Private visibility and select a future date and time, or clear the schedule field."
    elif "playlist" in lower:
        code="youtube_playlist_failed"; message="The video uploaded, but YouTube could not add it to one or more playlists."; resolution="Reconnect YouTube permissions or add the video to the playlist manually in YouTube Studio."
    elif "client_secret" in lower or "credentials" in lower:
        code="youtube_credentials_missing"; message="Google OAuth credentials are missing or invalid."; resolution="Place the correct OAuth Desktop client file at backend/client_secret.json and restart the backend."
    return {"code":code,"message":message,"resolution":resolution,"technical_detail":text}


def list_owned_playlists():
    try:
        youtube,_=get_authenticated_service()
        playlists=[]; page_token=None
        while True:
            response=youtube.playlists().list(part="snippet,status",mine=True,maxResults=50,pageToken=page_token).execute()
            for item in response.get("items",[]):
                playlists.append({"id":item.get("id"),"title":item.get("snippet",{}).get("title","Untitled Playlist"),"privacy":item.get("status",{}).get("privacyStatus","")})
            page_token=response.get("nextPageToken")
            if not page_token: break
        return playlists
    except Exception as error:
        detail=explain_youtube_error(error)
        raise RuntimeError(json_error(detail)) from error


def json_error(detail):
    import json
    return json.dumps(detail, ensure_ascii=False)


def upload_video(video_path,title,description,tags,category_id="17",privacy_status="private",made_for_kids=False,publish_at="",thumbnail_path="",playlist_ids=None):
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Rendered video not found: {video_path}")
    try:
        youtube,_=get_authenticated_service()
        # CourtVision uploads general-audience sports content. It is safe for children,
        # but it is not specifically directed to children, so YouTube's correct default
        # is "Not made for kids". Sports is always category 17.
        status={"privacyStatus":privacy_status,"selfDeclaredMadeForKids":False}
        if publish_at and privacy_status=="private": status["publishAt"]=publish_at
        tag_validation = sanitize_youtube_tags(tags)
        clean_tags = tag_validation["tags"]
        body={"snippet":{"title":str(title or "Untitled NBA Highlight")[:100],"description":str(description or ""),"tags":clean_tags,"categoryId":"17"},"status":status}
        media=MediaFileUpload(video_path,mimetype="video/mp4",chunksize=8*1024*1024,resumable=True)
        request=youtube.videos().insert(part="snippet,status",body=body,media_body=media)
        response=None
        while response is None:
            _,response=request.next_chunk()
        video_id=response.get("id")
        warnings=[]
        if video_id and thumbnail_path and os.path.exists(thumbnail_path):
            try:
                youtube.thumbnails().set(videoId=video_id,media_body=MediaFileUpload(thumbnail_path,resumable=False)).execute()
            except Exception as error:
                warnings.append(explain_youtube_error(error))
        added=[]
        for playlist_id in playlist_ids or []:
            if not playlist_id or not video_id: continue
            try:
                youtube.playlistItems().insert(part="snippet",body={"snippet":{"playlistId":playlist_id,"resourceId":{"kind":"youtube#video","videoId":video_id}}}).execute()
                added.append(playlist_id)
            except Exception as error:
                warnings.append(explain_youtube_error(error))
        return {"ok":True,"video_id":video_id,"youtube_url":f"https://www.youtube.com/watch?v={video_id}" if video_id else "","playlists_added":added,"privacy_status":privacy_status,"warnings":warnings,"uploaded_tags":clean_tags,"tag_validation":tag_validation}
    except Exception as error:
        if isinstance(error, RuntimeError):
            raise
        detail=explain_youtube_error(error)
        raise RuntimeError(json_error(detail)) from error
