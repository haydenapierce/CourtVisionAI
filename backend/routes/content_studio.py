from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import uuid
import json
import re
import threading
import time
import sys
import ctypes
import math
from collections import deque
from datetime import datetime, timedelta
from services.ffmpeg_service import render_content_studio_project, render_content_studio_solos, get_video_duration_seconds, get_video_fps, cancel_render, clear_render_cancel, create_render_preview_seed
from services.metadata_generator import generate_solo_metadata, generate_top10_metadata, trim_tags
from services.youtube_upload_service import list_owned_playlists, upload_video, explain_youtube_error, sanitize_youtube_tags

router = APIRouter()

BASE_UPLOAD_DIR = os.path.join("uploads", "content_studio")
CLIPS_DIR = os.path.join(BASE_UPLOAD_DIR, "clips")
PROJECTS_DIR = os.path.join(BASE_UPLOAD_DIR, "projects")
RENDERED_DIR = os.path.join(BASE_UPLOAD_DIR, "rendered")
THUMBNAILS_DIR = os.path.join(BASE_UPLOAD_DIR, "thumbnails")
TRASH_DIR = os.path.join(BASE_UPLOAD_DIR, "trash")
TEMPLATES_DIR = os.path.join(BASE_UPLOAD_DIR, "templates")

ASSETS_DIR = os.path.join("assets")
BRANDING_DIR = os.path.join(ASSETS_DIR, "branding")
COUNTDOWN_DIR = os.path.join(ASSETS_DIR, "countdown")
MUSIC_DIR = os.path.join(ASSETS_DIR, "music")
LEGACY_MUSIC_DIR = os.path.join(TEMPLATES_DIR, "music")

LEGACY_INTRO_FILE = os.path.join(TEMPLATES_DIR, "intro.mp4")
LEGACY_OUTRO_FILE = os.path.join(TEMPLATES_DIR, "outro.png")
INTRO_FILE = os.path.join(BRANDING_DIR, "intro.mp4")
OUTRO_FILE = os.path.join(BRANDING_DIR, "outro.png")

ALLOWED_VIDEO_EXTENSIONS = [".mp4"]
ALLOWED_MUSIC_EXTENSIONS = [".mp3", ".wav", ".m4a"]

CONTENT_STUDIO_STATUS_CACHE = {
    "created_at": None,
    "payload": None
}

CONTENT_STUDIO_STATUS_CACHE_SECONDS = 60

RENDER_JOBS = {}
SOLO_EXPORT_JOBS = {}
JOB_LOCK = threading.Lock()
RENDER_HISTORY_LOCK = threading.Lock()
RENDER_HISTORY_FILE = os.path.join(BASE_UPLOAD_DIR, "render_history.json")
LIVE_RENDER_PREVIEW_FILENAME = "live_render_preview.jpg"


def _live_render_preview_path(project_id):
    return os.path.join(RENDERED_DIR, str(project_id), LIVE_RENDER_PREVIEW_FILENAME)


def _clear_live_render_preview(project_id):
    preview_path = _live_render_preview_path(project_id)
    try:
        if os.path.exists(preview_path):
            os.remove(preview_path)
    except OSError:
        pass
    return preview_path


def _project_source_duration(project):
    total = 0.0
    clips = project.get("clips") or []
    if project.get("project_type") == "top10":
        clips = [clip for clip in clips if clip.get("selected_for_top10", True)][:10]
    for clip in clips:
        start = max(0.0, float(clip.get("trim_start") or 0))
        end = max(0.0, float(clip.get("trim_end") or 0))
        duration = max(0.0, float(clip.get("duration_seconds") or 0))
        total += max(0.0, (end - start) if end > start else (duration - start))
    # The fixed outro is part of every final project render.
    return max(1.0, total + 15.0)


def _render_profile_key(project):
    settings = project.get("render_settings") or {}
    clips = project.get("clips") or []
    source_fps = float((clips[0] if clips else {}).get("source_fps") or 30)
    requested_fps = int(settings.get("output_fps") or 0)
    target_fps = int(round(source_fps)) if requested_fps <= 0 else requested_fps
    interpolation = "none" if target_fps <= source_fps + 0.5 else str(settings.get("interpolation_mode") or "auto")
    return f"{project.get('project_type','solo')}:{int(round(source_fps))}->{target_fps}:{interpolation}"


def _load_render_history():
    try:
        with RENDER_HISTORY_LOCK:
            if not os.path.exists(RENDER_HISTORY_FILE):
                return {}
            with open(RENDER_HISTORY_FILE, "r", encoding="utf-8") as source:
                data = json.load(source)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _baseline_render_estimate(project):
    """Return a useful first ETA before live progress exists.

    This intentionally favors a slightly conservative estimate so the timer
    counts down from a realistic total instead of starting at one second and
    climbing. Completed renders quickly replace this baseline through the
    per-profile history below.
    """
    settings = project.get("render_settings") or {}
    clips = project.get("clips") or []
    source_fps = float((clips[0] if clips else {}).get("source_fps") or 30)
    requested_fps = int(settings.get("output_fps") or 0)
    target_fps = int(round(source_fps)) if requested_fps <= 0 else requested_fps
    interpolation = target_fps > source_fps + 0.5 and str(settings.get("interpolation_mode") or "auto").lower() not in {"none", "off", "original"}

    total_duration = _project_source_duration(project)
    main_duration = max(1.0, total_duration - 15.0)
    project_type = str(project.get("project_type") or "solo").lower()

    if interpolation:
        fps_ratio = max(1.0, float(target_fps) / max(1.0, source_fps))
        # Motion-compensated interpolation is the expensive part. The factor is
        # deliberately conservative until this computer has matching history.
        seconds_per_source_second = 2.8 + (fps_ratio - 1.0) * 2.2
        if target_fps >= 120:
            seconds_per_source_second += 0.8
    else:
        seconds_per_source_second = 0.42 if project_type == "solo" else 0.58

    estimate = (main_duration * seconds_per_source_second) + (15.0 * 0.35) + 8.0
    if project_type == "top10":
        estimate += 10.0
    return max(8, int(round(estimate)))


def _historical_render_estimate(project):
    baseline = _baseline_render_estimate(project)
    profile = (_load_render_history().get(_render_profile_key(project)) or {})
    samples = profile.get("seconds_per_source_second") or []
    clean = [float(value) for value in samples[-8:] if float(value or 0) > 0]
    if not clean:
        return baseline
    clean.sort()
    median = clean[len(clean) // 2]
    historical = max(1, int(round(median * _project_source_duration(project))))
    # Prefer this machine's real history, while retaining a little baseline
    # stability when only one or two samples exist.
    history_weight = min(0.9, 0.65 + len(clean) * 0.05)
    return max(1, int(round(historical * history_weight + baseline * (1.0 - history_weight))))


def _record_render_history(project, elapsed_seconds):
    source_duration = _project_source_duration(project)
    if elapsed_seconds <= 0 or source_duration <= 0:
        return
    rate = float(elapsed_seconds) / source_duration
    key = _render_profile_key(project)
    try:
        with RENDER_HISTORY_LOCK:
            data = {}
            if os.path.exists(RENDER_HISTORY_FILE):
                try:
                    with open(RENDER_HISTORY_FILE, "r", encoding="utf-8") as source:
                        loaded = json.load(source)
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            profile = data.get(key) or {}
            samples = [float(value) for value in (profile.get("seconds_per_source_second") or []) if float(value or 0) > 0]
            samples.append(rate)
            profile["seconds_per_source_second"] = samples[-12:]
            profile["last_total_seconds"] = int(round(elapsed_seconds))
            profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
            data[key] = profile
            os.makedirs(os.path.dirname(RENDER_HISTORY_FILE), exist_ok=True)
            temp_path = f"{RENDER_HISTORY_FILE}.tmp"
            with open(temp_path, "w", encoding="utf-8") as target:
                json.dump(data, target, indent=2)
            os.replace(temp_path, RENDER_HISTORY_FILE)
    except Exception:
        pass


# Keep Windows awake only while the background render worker is active.
# SetThreadExecutionState is thread-scoped, so acquire and release it from
# the same worker thread. Other platforms safely do nothing.
def _set_render_sleep_prevention(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    try:
        flags = ES_CONTINUOUS
        if enabled:
            flags |= ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return bool(result)
    except Exception:
        return False


def _clean_render_stage(stage: str) -> str:
    text = str(stage or "Rendering Final Video").strip()
    text = re.sub(r"\s*[—-]\s*\d{1,3}%\s*$", "", text).strip()
    lower = text.lower()
    if lower.startswith("interpolating clip"):
        return "Interpolating Clip"
    if lower.startswith("rendering clip") or lower.startswith("rendered clip"):
        return "Rendering Clip"
    if "outro" in lower:
        return "Rendering Outro"
    if "joining" in lower or "concat" in lower:
        return "Joining Video and Audio"
    if "final" in lower:
        return "Finalizing Video"
    if "prepar" in lower or "start" in lower:
        return "Preparing Render"
    return text


class ClipEdit(BaseModel):
    clip_id: str
    order: int = 1
    title: str = ""
    split_from_clip_id: Optional[str] = None
    file_path: str = ""
    preview_url: str = ""
    original_filename: str = ""
    trim_start: float = 0
    trim_end: float = 0
    duration_seconds: float = 0
    selected_for_top10: bool = True
    frame_x: float = 0
    frame_y: float = 0
    frame_scale: float = 1
    source_fps: float = 0
    muted: bool = False
    playback_rate: float = 1
    blurred_side_fill: bool = False
    blur_crop_left_pct: float = 0
    blur_crop_right_pct: float = 0
    blur_crop_offset_pct: float = 0


class MetadataEdit(BaseModel):
    title: str = ""
    description: str = ""
    tags: str = ""
    thumbnail_plan: str = ""


class RenderSettingsEdit(BaseModel):
    output_fps: int = 0
    interpolation_mode: str = "auto"


class MetadataSuggestionRequest(BaseModel):
    clip_happening: str = ""
    player_name: str = ""
    video_type: str = ""


class ProjectEdit(BaseModel):
    project_name: str = ""
    clips: List[ClipEdit] = []
    top10_draft: Optional[MetadataEdit] = None
    solo_draft: Optional[MetadataEdit] = None
    render_settings: Optional[RenderSettingsEdit] = None


def ensure_content_studio_folders():
    for folder in [
        BASE_UPLOAD_DIR,
        CLIPS_DIR,
        PROJECTS_DIR,
        RENDERED_DIR,
        THUMBNAILS_DIR,
        TRASH_DIR,
        TEMPLATES_DIR,
        MUSIC_DIR,
        LEGACY_MUSIC_DIR,
        ASSETS_DIR,
        BRANDING_DIR,
        COUNTDOWN_DIR
    ]:
        os.makedirs(folder, exist_ok=True)


def clean_title_from_filename(filename):
    name = os.path.splitext(filename or "")[0]
    name = name.replace("_", " ").replace("-", " ").replace(".", " ").strip()
    return " ".join(name.split()) or "Untitled NBA Highlight"


def generate_tags(title):
    base_tags = [
        title,
        "NBA",
        "NBA highlights",
        "basketball highlights",
        "NBA Top 10",
        "NBATop10",
        "best NBA plays",
        "basketball",
        "NBA history",
        "classic NBA",
        "NBA legends",
        "poster dunk",
        "slam dunk",
        "basketball video",
        "NBA dunks",
        "greatest NBA plays"
    ]

    tags = []
    current_length = 0

    for tag in base_tags:
        clean_tag = str(tag).strip()
        extra = len(clean_tag) + (2 if tags else 0)

        if clean_tag and current_length + extra <= 500:
            tags.append(clean_tag)
            current_length += extra

    return ", ".join(tags)


def generate_metadata(title, project_type):
    cleaned_title = clean_title_from_filename(title)

    if project_type == "top10":
        youtube_title = cleaned_title if "top 10" in cleaned_title.lower() else f"{cleaned_title} Top 10 Plays"
        description = (
            f"{youtube_title}\n\n"
            "NBA highlights, greatest plays, dunks, and moments. "
            "Subscribe to NBATop10 for more classic NBA Top 10 videos."
        )
        thumbnail_plan = (
            "Use the best action frame as the background, darken the crowd, brighten the player, "
            "add bold red/white Top 10 text, and keep the subject large for mobile viewers."
        )
    else:
        youtube_title = cleaned_title
        description = (
            f"{youtube_title}\n\n"
            "NBA highlight clip featuring one of the best basketball moments. "
            "Subscribe to NBATop10 for more NBA highlights, dunks, and classic basketball plays."
        )
        thumbnail_plan = (
            "Use the main action frame, zoom on the player, increase contrast, darken background, "
            "and add bold readable highlight text."
        )

    return {
        "title": youtube_title,
        "description": description,
        "tags": generate_tags(youtube_title),
        "thumbnail_plan": thumbnail_plan
    }


def _first_existing(paths):
    for path in paths:
        if path and os.path.exists(path):
            return path
    return ""


def get_intro_path():
    return _first_existing([INTRO_FILE, LEGACY_INTRO_FILE])


def get_outro_path():
    return _first_existing([OUTRO_FILE, LEGACY_OUTRO_FILE])


def get_countdown_status():
    items = {}

    for number in range(1, 11):
        path = os.path.join(COUNTDOWN_DIR, f"{number}.png")
        items[str(number)] = {
            "exists": os.path.exists(path),
            "path": path.replace("\\", "/")
        }

    return items


def get_template_status():
    ensure_content_studio_folders()

    music_files = []

    for music_folder in [MUSIC_DIR, LEGACY_MUSIC_DIR]:
        if not os.path.exists(music_folder):
            continue
        for name in os.listdir(music_folder):
            if os.path.splitext(name)[1].lower() in ALLOWED_MUSIC_EXTENSIONS and name not in music_files:
                music_files.append(name)

    countdown = get_countdown_status()
    missing_countdown = [number for number, info in countdown.items() if not info["exists"]]
    intro_path = get_intro_path()
    outro_path = get_outro_path()

    return {
        "intro_exists": bool(intro_path),
        "intro_path": intro_path.replace("\\", "/") if intro_path else "",
        "intro_optional": True,
        "outro_exists": bool(outro_path),
        "outro_path": outro_path.replace("\\", "/") if outro_path else "",
        "outro_required": True,
        "legacy_template_folder": TEMPLATES_DIR.replace("\\", "/"),
        "asset_branding_folder": BRANDING_DIR.replace("\\", "/"),
        "asset_countdown_folder": COUNTDOWN_DIR.replace("\\", "/"),
        "countdown_overlays_ready": len(missing_countdown) == 0,
        "missing_countdown_overlays": missing_countdown,
        "countdown_overlays": countdown,
        "music_folder_exists": os.path.exists(MUSIC_DIR),
        "music_count": len(music_files),
        "music_files": music_files,
        "solo_template": {
            "intro": "off",
            "clip": "uploaded MP4 or detected clip",
            "fade": "0.10 sec in + 0.10 sec out",
            "outro": "outro.png held for 15 seconds"
        },
        "top10_template": {
            "intro": "intro.mp4 if present, otherwise skipped",
            "clips": "10 ranked clips in saved drag order",
            "number_overlay": "10.png through 1.png bottom-left for full clip",
            "transition": "0.10 sec fade at clip start and end",
            "outro": "outro.png held for 15 seconds",
            "music": "cycles through music folder if music files exist"
        }
    }

def project_path(project_id):
    return os.path.join(PROJECTS_DIR, f"{project_id}.json")


def load_project(project_id):
    path = project_path(project_id)

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        project = json.load(f)

    changed = False
    for clip in project.get("clips", []):
        fps = float(clip.get("source_fps") or 0)
        file_path = str(clip.get("file_path") or "").replace("/", os.sep)
        if fps <= 0 and file_path and os.path.exists(file_path):
            detected = float(get_video_fps(file_path) or 0)
            if detected > 0:
                clip["source_fps"] = round(detected, 3)
                changed = True

    if changed:
        project["media_metadata_refreshed_at"] = datetime.now().isoformat(timespec="seconds")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(project, f, indent=2)

    return project


def save_project(project):
    ensure_content_studio_folders()

    path = project_path(project["project_id"])

    project["updated_at"] = datetime.now().isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    return project


def clone_clip_for_split(existing_clips, split_clip_id, split_from_clip_id=None):
    base_clip_id = str(split_from_clip_id or "").strip()
    if not base_clip_id and "_split_" in str(split_clip_id):
        base_clip_id = str(split_clip_id).split("_split_")[0]

    if not base_clip_id:
        return None

    for clip in existing_clips:
        if clip.get("clip_id") == base_clip_id or clip.get("split_from_clip_id") == base_clip_id:
            cloned = dict(clip)
            cloned["clip_id"] = split_clip_id
            cloned["split_from_clip_id"] = base_clip_id
            return cloned

    return None


@router.get("/content-studio/status")
def content_studio_status():
    cached_at = CONTENT_STUDIO_STATUS_CACHE.get("created_at")
    cached_payload = CONTENT_STUDIO_STATUS_CACHE.get("payload")

    if cached_at and cached_payload:
        try:
            if datetime.now() - cached_at <= timedelta(seconds=CONTENT_STUDIO_STATUS_CACHE_SECONDS):
                return cached_payload
        except Exception:
            pass

    ensure_content_studio_folders()

    payload = {
        "status": "ok",
        "message": "Content Studio folders ready",
        "folders": {
            "clips": CLIPS_DIR,
            "projects": PROJECTS_DIR,
            "rendered": RENDERED_DIR,
            "thumbnails": THUMBNAILS_DIR,
            "templates": TEMPLATES_DIR,
            "music": MUSIC_DIR,
            "legacy_music": LEGACY_MUSIC_DIR
        },
        "templates": get_template_status()
    }

    CONTENT_STUDIO_STATUS_CACHE["created_at"] = datetime.now()
    CONTENT_STUDIO_STATUS_CACHE["payload"] = payload

    return payload


@router.get("/content-studio/templates")
def content_studio_templates():
    return get_template_status()


@router.get("/content-studio/assets/outro")
def content_studio_outro_asset():
    outro_path = get_outro_path()

    if not outro_path or not os.path.exists(outro_path):
        raise HTTPException(
            status_code=404,
            detail="outro.png was not found in assets/branding."
        )

    return FileResponse(outro_path, media_type="image/png", filename="outro.png")


@router.post("/content-studio/upload")
async def upload_content_studio_clips(
    project_type: str = Form("solo"),
    project_name: str = Form("Untitled Project"),
    files: List[UploadFile] = File(...)
):
    ensure_content_studio_folders()

    project_id = str(uuid.uuid4())
    project_folder = os.path.join(CLIPS_DIR, project_id)
    os.makedirs(project_folder, exist_ok=True)

    saved_clips = []

    for index, file in enumerate(files):
        original_name = file.filename or f"clip_{index + 1}.mp4"
        extension = os.path.splitext(original_name)[1].lower()

        if extension not in ALLOWED_VIDEO_EXTENSIONS:
            continue

        safe_filename = f"{index + 1}_{uuid.uuid4().hex}{extension}"
        saved_path = os.path.join(project_folder, safe_filename)

        with open(saved_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        clip_title = clean_title_from_filename(original_name)
        duration_seconds = get_video_duration_seconds(saved_path)
        source_fps = get_video_fps(saved_path)

        saved_clips.append({
            "clip_id": str(uuid.uuid4()),
            "original_filename": original_name,
            "stored_filename": safe_filename,
            "title": clip_title,
            "file_path": saved_path.replace("\\", "/"),
            "preview_url": f"/content-studio/preview/{project_id}/{safe_filename}",
            "order": index + 1,
            "trim_start": 0,
            "trim_end": 0,
            "duration_seconds": duration_seconds,
            "source_fps": source_fps,
            "selected_for_top10": index < 10 if project_type == "top10" else True,
            "metadata": generate_metadata(clip_title, "solo")
        })

    top10_metadata = generate_metadata(project_name, "top10") if project_type == "top10" else None
    solo_metadata = generate_metadata(project_name or saved_clips[0]["title"], "solo") if project_type == "solo" and saved_clips else None

    project = {
        "project_id": project_id,
        "project_type": project_type,
        "project_name": project_name,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "clip_count": len(saved_clips),
        "clips": saved_clips,
        "top10_draft": top10_metadata,
        "solo_draft": solo_metadata,
        "status": "draft",
        "preview_confirmed": False,
        "render_status": "not_rendered",
        "rendered_video": None,
        "render_settings": {
            "output_fps": 0,
            "interpolation_mode": "auto",
            "intro_enabled": project_type == "top10",
            "intro_file": "intro.mp4 if available",
            "clip_fade_in_seconds": 0.10,
            "clip_fade_out_seconds": 0.10,
            "outro_enabled": True,
            "outro_file": "outro.png",
            "outro_hold_seconds": 15,
            "music_enabled": project_type == "top10",
            "music_mode": "cycle_folder",
            "music_folder": "music",
            "number_overlay_enabled": project_type == "top10",
            "number_overlay_position": "bottom-left",
            "number_overlay_files": "backend/assets/countdown/10.png through 1.png"
        },
        "templates": get_template_status()
    }

    save_project(project)

    return {
        "message": "Project uploaded",
        "project": project
    }


@router.get("/content-studio/projects")
def get_content_studio_projects():
    ensure_content_studio_folders()

    projects = []

    for filename in os.listdir(PROJECTS_DIR):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(PROJECTS_DIR, filename)

        try:
            with open(path, "r", encoding="utf-8") as f:
                project_data = json.load(f)
                if not project_data.get("trashed"):
                    projects.append(project_data)
        except Exception:
            continue

    projects = sorted(projects, key=lambda x: x.get("updated_at", x.get("created_at", "")), reverse=True)

    return {
        "projects": projects
    }


@router.get("/content-studio/project/{project_id}")
def get_content_studio_project(project_id: str):
    ensure_content_studio_folders()

    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    project["templates"] = get_template_status()

    return {
        "found": True,
        "project": project
    }


@router.put("/content-studio/project/{project_id}/edit")
def edit_content_studio_project(project_id: str, edit: ProjectEdit, request: Request):
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    edit_session = str(request.headers.get("X-CourtVision-Edit-Session") or "").strip()
    try:
        edit_revision = int(request.headers.get("X-CourtVision-Edit-Revision") or 0)
    except Exception:
        edit_revision = 0

    saved_session = str(project.get("_edit_session") or "")
    try:
        saved_revision = int(project.get("_edit_revision") or 0)
    except Exception:
        saved_revision = 0

    # Reject only stale writes from the same live editor session. A fresh app
    # session is allowed to begin again at revision 1.
    if edit_session and saved_session == edit_session and edit_revision and edit_revision <= saved_revision:
        return {
            "found": True,
            "stale_ignored": True,
            "project": project
        }

    if edit.project_name:
        project["project_name"] = edit.project_name

    existing_clips = project.get("clips", [])
    old_by_id = {clip.get("clip_id"): clip for clip in existing_clips}
    rebuilt_clips = []

    for index, update in enumerate(sorted(edit.clips, key=lambda x: int(x.order or 999)), start=1):
        if update.clip_id in old_by_id:
            base_clip = dict(old_by_id[update.clip_id])
        else:
            base_clip = clone_clip_for_split(
                existing_clips,
                update.clip_id,
                update.split_from_clip_id
            )

        # Persist copied/pasted timeline entries even if the legacy project
        # file did not yet contain their generated clip_id. The payload carries
        # the immutable source identity needed to rebuild the duplicate.
        if not base_clip and update.file_path:
            base_clip = {
                "clip_id": update.clip_id,
                "split_from_clip_id": update.split_from_clip_id,
                "file_path": update.file_path,
                "preview_url": update.preview_url,
                "original_filename": update.original_filename,
                "title": update.title or update.original_filename or "Clip",
                "duration_seconds": float(update.duration_seconds or 0),
                "source_fps": float(update.source_fps or 0)
            }

        if not base_clip:
            continue

        base_clip["clip_id"] = update.clip_id
        if update.split_from_clip_id:
            base_clip["split_from_clip_id"] = update.split_from_clip_id
        if update.file_path:
            base_clip["file_path"] = update.file_path
        if update.preview_url:
            base_clip["preview_url"] = update.preview_url
        if update.original_filename:
            base_clip["original_filename"] = update.original_filename
        base_clip["title"] = update.title or base_clip.get("title", "")
        base_clip["order"] = index
        duration_seconds = max(0, float(update.duration_seconds or base_clip.get("duration_seconds") or 0))
        trim_start = max(0, float(update.trim_start or 0))
        trim_end = max(0, float(update.trim_end or 0))

        if duration_seconds > 0:
            trim_start = min(trim_start, max(0, duration_seconds - 0.25))
            if trim_end <= trim_start:
                trim_end = duration_seconds
            trim_end = min(trim_end, duration_seconds)
            trim_end = max(trim_end, trim_start + 0.25)

        base_clip["trim_start"] = round(trim_start, 6)
        base_clip["trim_end"] = round(trim_end, 6)
        base_clip["duration_seconds"] = duration_seconds
        base_clip["selected_for_top10"] = bool(update.selected_for_top10)
        base_clip["frame_x"] = round(float(update.frame_x or 0), 2)
        base_clip["frame_y"] = round(float(update.frame_y or 0), 2)
        base_clip["frame_scale"] = round(max(0.5, min(3.0, float(update.frame_scale or 1))), 2)
        if float(update.source_fps or 0) > 0:
            base_clip["source_fps"] = round(float(update.source_fps), 3)
        base_clip["muted"] = bool(update.muted)
        base_clip["playback_rate"] = round(max(0.25, min(4.0, float(update.playback_rate or 1))), 3)
        base_clip["blurred_side_fill"] = bool(update.blurred_side_fill)
        base_clip["blur_crop_left_pct"] = round(max(0.0, min(42.0, float(update.blur_crop_left_pct or 0))), 2)
        base_clip["blur_crop_right_pct"] = round(max(0.0, min(42.0, float(update.blur_crop_right_pct or 0))), 2)
        base_clip["blur_crop_offset_pct"] = round(max(-30.0, min(30.0, float(update.blur_crop_offset_pct or 0))), 2)

        rebuilt_clips.append(base_clip)

    project["clips"] = rebuilt_clips
    project["clip_count"] = len(rebuilt_clips)

    if edit.top10_draft:
        project["top10_draft"] = edit.top10_draft.dict()

    if edit.solo_draft:
        project["solo_draft"] = edit.solo_draft.dict()

    if edit.render_settings:
        project["render_settings"] = {
            "output_fps": 0 if int(edit.render_settings.output_fps or 0) <= 0 else max(24, min(120, int(edit.render_settings.output_fps))),
            "interpolation_mode": str(edit.render_settings.interpolation_mode or "auto")
        }

    project["status"] = "edited"
    project["preview_confirmed"] = False
    if edit_session:
        project["_edit_session"] = edit_session
        project["_edit_revision"] = edit_revision
    project = save_project(project)

    return {
        "message": "Project edits saved",
        "project": project
    }


@router.put("/content-studio/project/{project_id}/approve")
def approve_content_studio_project(project_id: str):
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    project["status"] = "approved"
    project = save_project(project)

    return {
        "message": "Project approved. YouTube upload will still require a separate permission click.",
        "project": project
    }



@router.put("/content-studio/project/{project_id}/confirm-preview")
def confirm_content_studio_preview(project_id: str):
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    if not project.get("rendered_video"):
        return {
            "found": True,
            "confirmed": False,
            "message": "Render the final MP4 before confirming the preview.",
            "project": project
        }

    project["preview_confirmed"] = True
    project["status"] = "preview_confirmed"
    project = save_project(project)

    return {
        "found": True,
        "confirmed": True,
        "message": "Preview confirmed. YouTube draft and upload steps are now unlocked.",
        "project": project
    }



def _set_render_job(project_id, **updates):
    with JOB_LOCK:
        current = dict(RENDER_JOBS.get(project_id) or {})
        current.update(updates)
        current["project_id"] = project_id
        RENDER_JOBS[project_id] = current


def _render_project_worker(project_id):
    project = load_project(project_id)
    if not project:
        _set_render_job(project_id, status="failed", progress=0, stage="Project not found")
        return

    render_started = time.monotonic()
    sleep_lock_acquired = _set_render_sleep_prevention(True)
    progress_samples = deque(maxlen=120)
    historical_total = _historical_render_estimate(project)
    smoothed_eta = float(historical_total) if historical_total else None
    displayed_eta = int(round(smoothed_eta)) if smoothed_eta else None
    last_eta_publish_at = render_started
    last_project_save_at = 0.0
    last_saved_progress = -1
    last_saved_stage = ""
    live_preview_path = _clear_live_render_preview(project_id)
    os.makedirs(os.path.dirname(live_preview_path), exist_ok=True)
    live_preview_url = f"/content-studio/project/{project_id}/render-preview"

    def progress_callback(percent, stage):
        nonlocal smoothed_eta, displayed_eta, last_eta_publish_at
        nonlocal last_project_save_at, last_saved_progress, last_saved_stage

        safe_percent = int(max(0, min(100, percent)))
        clean_stage = _clean_render_stage(stage)
        now = time.monotonic()
        elapsed_seconds = max(0.0, now - render_started)
        progress_samples.append((now, float(safe_percent)))

        raw_candidates = []
        if historical_total and safe_percent < 100:
            raw_candidates.append(max(0.0, historical_total * (1.0 - safe_percent / 100.0)))

        if 2 <= safe_percent < 100 and elapsed_seconds >= 3:
            overall_total = elapsed_seconds / max(0.02, safe_percent / 100.0)
            raw_candidates.append(max(0.0, overall_total - elapsed_seconds))

            recent = [item for item in progress_samples if now - item[0] <= 25]
            if len(recent) >= 2:
                time_span = recent[-1][0] - recent[0][0]
                progress_span = recent[-1][1] - recent[0][1]
                if time_span >= 6 and progress_span >= 1:
                    percent_per_second = progress_span / time_span
                    raw_candidates.append(max(0.0, (100.0 - safe_percent) / percent_per_second))

        eta_seconds = None
        if safe_percent >= 100:
            eta_seconds = 0
            smoothed_eta = 0.0
            displayed_eta = 0
        elif raw_candidates:
            raw_candidates.sort()
            raw_eta = raw_candidates[len(raw_candidates) // 2]
            raw_eta = max(1.0, min(raw_eta, 6 * 3600.0))
            smoothed_eta = raw_eta if smoothed_eta is None else (smoothed_eta * 0.88 + raw_eta * 0.12)

            # Publish a calm ETA at most every two seconds. Limit changes so
            # transient interpolation speed spikes do not make it jump wildly.
            if displayed_eta is None:
                displayed_eta = int(round(smoothed_eta))
            elif now - last_eta_publish_at >= 1.0:
                publish_elapsed = max(1.0, now - last_eta_publish_at)
                model_target = int(round(smoothed_eta))
                countdown_target = max(1, int(round(displayed_eta - publish_elapsed)))

                # ETA must keep moving while FFmpeg is working inside a stage whose
                # integer progress percentage has not changed. Allow a controlled
                # increase only when fresh speed evidence says the render is slower.
                if model_target <= displayed_eta:
                    target = min(model_target, countdown_target)
                else:
                    max_rise = max(2, int(displayed_eta * 0.035))
                    target = min(displayed_eta + max_rise, model_target)

                max_drop = max(2, int(displayed_eta * 0.10), int(round(publish_elapsed)))
                target = max(displayed_eta - max_drop, target)
                displayed_eta = max(0, int(round(target)))
                last_eta_publish_at = now
            eta_seconds = displayed_eta

        _set_render_job(
            project_id,
            status="rendering" if safe_percent < 100 else "complete",
            progress=safe_percent,
            stage=clean_stage,
            elapsed_seconds=int(round(elapsed_seconds)),
            eta_seconds=eta_seconds,
            sleep_prevention_active=bool(sleep_lock_acquired),
            preview_url=live_preview_url,
            preview_available=os.path.exists(live_preview_path)
        )

        # Saving a JSON project file on every FFmpeg progress line can create
        # hundreds of writes, especially in OneDrive. Throttle disk writes while
        # keeping the in-memory job state fully live for the frontend poller.
        should_save = (
            safe_percent >= 100
            or now - last_project_save_at >= 1.25
            or (clean_stage != last_saved_stage and now - last_project_save_at >= 0.5)
        )
        if should_save and (safe_percent != last_saved_progress or clean_stage != last_saved_stage or safe_percent >= 100):
            latest = load_project(project_id) or project
            latest["render_status"] = "rendering" if safe_percent < 100 else "rendered"
            latest["render_progress"] = safe_percent
            latest["render_stage"] = clean_stage
            latest["render_eta_seconds"] = eta_seconds
            save_project(latest)
            last_project_save_at = now
            last_saved_progress = safe_percent
            last_saved_stage = clean_stage

    try:
        result = render_content_studio_project(
            project=project,
            templates_dir=TEMPLATES_DIR,
            rendered_dir=RENDERED_DIR,
            progress_callback=progress_callback,
            preview_path=live_preview_path
        )

        project = load_project(project_id) or project

        if not result.get("ok"):
            canceled = "canceled" in str(result.get("message", "")).lower() or "canceled" in str(result.get("error", "")).lower()
            project["render_status"] = "canceled" if canceled else "failed"
            project["render_progress"] = 0
            project["render_stage"] = "Render canceled by user" if canceled else result.get("message", "Render failed")
            project["render_error"] = result
            save_project(project)
            _set_render_job(project_id, status="failed", progress=0, stage=project["render_stage"], error=result)
            return

        output_path = result.get("output_path")
        output_filename = os.path.basename(output_path)
        elapsed_total = max(0.0, time.monotonic() - render_started)
        _record_render_history(project, elapsed_total)
        project["render_status"] = "rendered"
        project["render_progress"] = 100
        project["render_stage"] = "Render complete"
        project["render_eta_seconds"] = 0
        project["preview_confirmed"] = False
        project["render_error"] = None
        project["rendered_video"] = {
            "filename": output_filename,
            "file_path": output_path.replace("\\", "/"),
            "preview_url": f"/content-studio/rendered/{project_id}/{output_filename}",
            "duration_seconds": result.get("duration_seconds", 0),
            "music_used": result.get("music_used"),
            "output_fps": (result.get("output_fps") or result.get("original_fps") or project.get("render_settings", {}).get("output_fps") or (project.get("clips") or [{}])[0].get("source_fps") or 30),
            "interpolation_mode": result.get("interpolation_mode", "auto"),
            "render_time_seconds": round(elapsed_total, 1)
        }
        project = save_project(project)
        _set_render_job(project_id, status="complete", progress=100, stage="Render complete", eta_seconds=0, elapsed_seconds=int(round(elapsed_total)), project=project)
    except Exception as error:
        project = load_project(project_id) or project
        project["render_status"] = "failed"
        project["render_progress"] = 0
        project["render_stage"] = str(error)
        project["render_error"] = {"message": str(error)}
        save_project(project)
        _set_render_job(project_id, status="failed", progress=0, stage=str(error), error={"message": str(error)}, eta_seconds=None)
    finally:
        _set_render_sleep_prevention(False)
        with JOB_LOCK:
            current = dict(RENDER_JOBS.get(project_id) or {})
            current["sleep_prevention_active"] = False
            RENDER_JOBS[project_id] = current


@router.post("/content-studio/project/{project_id}/render")
def render_content_studio_project_route(project_id: str):
    ensure_content_studio_folders()
    project = load_project(project_id)

    if not project:
        return {"found": False, "ok": False, "message": "Project not found"}

    existing = RENDER_JOBS.get(project_id) or {}
    if existing.get("status") == "rendering":
        return {
            "found": True,
            "ok": True,
            "started": False,
            "message": "Render is already running.",
            "job": existing,
            "project": project
        }

    live_preview_path = _clear_live_render_preview(project_id)
    os.makedirs(os.path.dirname(live_preview_path), exist_ok=True)
    preview_seeded = create_render_preview_seed(project, live_preview_path)

    project["render_status"] = "rendering"
    project["render_progress"] = 1
    project["render_stage"] = "Preparing Render"
    project["render_eta_seconds"] = _historical_render_estimate(project)
    project["preview_confirmed"] = False
    project = save_project(project)

    _set_render_job(
        project_id,
        status="rendering",
        progress=1,
        stage="Preparing Render",
        started_at=datetime.now().isoformat(timespec="seconds"),
        elapsed_seconds=0,
        eta_seconds=project.get("render_eta_seconds"),
        sleep_prevention_active=False,
        preview_url=f"/content-studio/project/{project_id}/render-preview",
        preview_available=bool(preview_seeded)
    )

    thread = threading.Thread(
        target=_render_project_worker,
        args=(project_id,),
        daemon=True
    )
    thread.start()

    return {
        "found": True,
        "ok": True,
        "started": True,
        "message": "Render started.",
        "job": RENDER_JOBS.get(project_id),
        "project": project
    }


@router.get("/content-studio/project/{project_id}/render-status")
def get_content_studio_render_status(project_id: str):
    project = load_project(project_id)

    if not project:
        return {"found": False, "message": "Project not found"}

    job = RENDER_JOBS.get(project_id) or {
        "project_id": project_id,
        "status": project.get("render_status", "idle"),
        "progress": int(project.get("render_progress") or 0),
        "stage": project.get("render_stage") or ""
    }

    # Disk project state is authoritative after a backend restart, while the
    # in-memory job carries the most frequent progress updates during rendering.
    project_progress = int(project.get("render_progress") or 0)
    job_progress = int(job.get("progress") or 0)

    if project.get("render_status") == "rendered" or project_progress >= 100:
        job = {
            **job,
            "status": "complete",
            "progress": 100,
            "stage": project.get("render_stage") or "Render complete"
        }
    elif project.get("render_status") == "failed":
        job = {
            **job,
            "status": "failed",
            "progress": project_progress,
            "stage": project.get("render_stage") or "Render failed"
        }
    else:
        job = {
            **job,
            "progress": max(project_progress, job_progress)
        }

    job = {
        **job,
        "preview_url": f"/content-studio/project/{project_id}/render-preview",
        "preview_available": os.path.exists(_live_render_preview_path(project_id))
    }

    return {
        "found": True,
        "job": job,
        "project": project
    }


@router.get("/content-studio/project/{project_id}/render-preview")
def get_content_studio_live_render_preview(project_id: str):
    if not load_project(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    preview_path = _live_render_preview_path(project_id)
    if not os.path.exists(preview_path):
        raise HTTPException(status_code=404, detail="Live render frame is not ready yet")

    # Return an in-memory snapshot instead of streaming the path directly.
    # FFmpeg atomically replaces this JPEG many times per second. FileResponse
    # could open one generation while Windows/OneDrive replaced it, occasionally
    # sending a truncated JPEG and producing the browser's broken-image icon.
    frame_bytes = b""
    for attempt in range(3):
        try:
            with open(preview_path, "rb") as preview_file:
                candidate = preview_file.read()
            if len(candidate) >= 4 and candidate[:2] == b"\xff\xd8" and candidate[-2:] == b"\xff\xd9":
                frame_bytes = candidate
                break
        except (OSError, PermissionError):
            pass
        time.sleep(0.015 * (attempt + 1))

    if not frame_bytes:
        raise HTTPException(status_code=404, detail="Live render frame is being updated")

    return Response(
        content=frame_bytes,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
            "Content-Length": str(len(frame_bytes))
        }
    )


@router.post("/content-studio/project/{project_id}/render/cancel")
def cancel_content_studio_render(project_id: str):
    project = load_project(project_id)
    if not project:
        return {"found": False, "ok": False, "message": "Project not found"}

    cancel_render(project_id)
    project["render_status"] = "canceled"
    project["render_stage"] = "Render canceled by user"
    project["render_progress"] = int(project.get("render_progress") or 0)
    save_project(project)
    _set_render_job(
        project_id,
        status="canceled",
        progress=project["render_progress"],
        stage="Render canceled by user"
    )
    return {"found": True, "ok": True, "project": project}


@router.post("/content-studio/project/{project_id}/auto-detect-clips")
def auto_detect_content_studio_clips(project_id: str):
    """
    Starter detector for long source files.

    It creates 10 rough editable clip slots from a long source MP4 so the user can
    immediately trim, rename, and rank the plays. It intentionally does not delete
    the original source clip; it turns the source into reusable cloned clip objects.
    """
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    source_clips = project.get("clips", [])

    if not source_clips:
        return {
            "found": True,
            "ok": False,
            "message": "No source clips found.",
            "project": project
        }

    first_source = source_clips[0]
    source_duration = float(first_source.get("duration_seconds") or get_video_duration_seconds(first_source.get("file_path", "")) or 0)

    if source_duration <= 0:
        return {
            "found": True,
            "ok": False,
            "message": "Could not read the source video duration. Make sure FFmpeg is working.",
            "project": project
        }

    # Build 10 editable slots, roughly spaced through the full video.
    # The user can quickly drag trims to exact dunk start/end points after this.
    clip_length = max(8, min(24, source_duration / 14))
    gap = max(clip_length, source_duration / 10)

    detected = []

    for index in range(10):
        start = round(min(source_duration - 1, index * gap), 2)
        end = round(min(source_duration, start + clip_length), 2)

        cloned = dict(first_source)
        cloned["clip_id"] = f"{first_source.get('clip_id')}_detected_{index + 1}_{uuid.uuid4().hex[:6]}"
        cloned["title"] = f"{project.get('project_name') or 'Top 10'} Clip #{10 - index}"
        cloned["order"] = index + 1
        cloned["trim_start"] = start
        cloned["trim_end"] = end
        cloned["duration_seconds"] = source_duration
        cloned["selected_for_top10"] = True
        cloned["detected_from_clip_id"] = first_source.get("clip_id")
        cloned["detection_status"] = "rough_auto_detected_editable"
        detected.append(cloned)

    extras = [clip for clip in source_clips[1:] if clip.get("clip_id") != first_source.get("clip_id")]
    first_source["selected_for_top10"] = False
    first_source["title"] = first_source.get("title") or "Full Source Video"

    project["clips"] = detected + [first_source] + extras
    project["clip_count"] = len(project["clips"])
    project["status"] = "clips_detected"
    project["detection_summary"] = {
        "method": "rough_equal_spacing",
        "message": "10 editable rough clip slots created. Trim each one exactly, rename, and drag into final order.",
        "source_duration_seconds": source_duration
    }

    project = save_project(project)

    return {
        "found": True,
        "ok": True,
        "message": "Created 10 rough editable clip slots from the source video.",
        "project": project
    }


@router.post("/content-studio/project/{project_id}/render-solos")
def render_content_studio_solos_route(project_id: str):
    ensure_content_studio_folders()

    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    project["solo_export_status"] = "exporting"
    save_project(project)

    result = render_content_studio_solos(
        project=project,
        templates_dir=TEMPLATES_DIR,
        rendered_dir=RENDERED_DIR
    )

    if not result.get("ok"):
        project["solo_export_status"] = "failed"
        project["solo_exports"] = result.get("exports", [])
        project["solo_export_error"] = result
        save_project(project)

        return {
            "found": True,
            "ok": False,
            "message": result.get("message", "Solo export failed."),
            "result": result,
            "project": project
        }

    project["solo_export_status"] = "exported"
    project["solo_export_error"] = None
    project["solo_exports"] = result.get("exports", [])
    project = save_project(project)

    return {
        "found": True,
        "ok": True,
        "message": result.get("message", "Solo clips exported."),
        "solo_exports": project["solo_exports"],
        "project": project
    }


@router.get("/content-studio/rendered/{project_id}/solos/{filename}")
def preview_rendered_content_studio_solo_video(project_id: str, filename: str):
    file_path = os.path.join(RENDERED_DIR, project_id, "solos", filename)

    if not os.path.exists(file_path):
        return {
            "found": False,
            "message": "Rendered solo video not found"
        }

    return FileResponse(file_path, media_type="video/mp4", headers={"Cache-Control": "no-cache", "Accept-Ranges": "bytes", "Access-Control-Allow-Origin": "*"})


@router.get("/content-studio/rendered/{project_id}/{filename}")
def preview_rendered_content_studio_video(project_id: str, filename: str):
    file_path = os.path.join(RENDERED_DIR, project_id, filename)

    if not os.path.exists(file_path):
        return {
            "found": False,
            "message": "Rendered video not found"
        }

    return FileResponse(file_path, media_type="video/mp4", headers={"Cache-Control": "no-cache", "Accept-Ranges": "bytes", "Access-Control-Allow-Origin": "*"})


@router.get("/content-studio/preview/{project_id}/{filename}")
def preview_content_studio_clip(project_id: str, filename: str):
    file_path = os.path.join(CLIPS_DIR, project_id, filename)

    if not os.path.exists(file_path):
        return {
            "found": False,
            "message": "Clip not found"
        }

    return FileResponse(file_path, media_type="video/mp4", headers={"Cache-Control": "no-cache", "Accept-Ranges": "bytes", "Access-Control-Allow-Origin": "*"})



@router.post("/content-studio/project/{project_id}/metadata-suggestion")
def create_content_studio_metadata_suggestion(
    project_id: str,
    request: MetadataSuggestionRequest
):
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "ok": False,
            "message": "Project not found."
        }

    happening = " ".join(
        str(request.clip_happening or "").split()
    ).strip()
    player = " ".join(
        str(request.player_name or "").split()
    ).strip()
    project_type = str(
        project.get("project_type") or request.video_type or "solo"
    ).lower()

    subject_parts = [part for part in [player, happening] if part]
    subject = " ".join(subject_parts).strip()

    if not subject:
        subject = (
            project.get("project_name") or
            "NBA Highlight"
        )

    try:
        if project_type == "top10":
            clip_titles = [
                clip.get("title", "")
                for clip in project.get("clips", [])[:10]
            ]
            metadata = generate_top10_metadata(subject, clip_titles, player_name=player, happening=happening)
        else:
            metadata = generate_solo_metadata(subject, player_name=player, happening=happening)
    except Exception as error:
        # Guaranteed local fallback so metadata generation never depends on an
        # external AI/API being available.
        fallback = generate_metadata(subject, project_type)
        metadata = {
            "title": fallback.get("title", subject),
            "description": fallback.get("description", ""),
            "tags": fallback.get("tags", ""),
            "thumbnail_plan": fallback.get("thumbnail_plan", ""),
            "fallback_reason": str(error)
        }

    raw_tags = metadata.get("tags") or ""
    if isinstance(raw_tags, str):
        tag_items = [
            item.strip()
            for item in raw_tags.split(",")
            if item.strip()
        ]
    else:
        tag_items = list(raw_tags or [])

    generated_tag_text = trim_tags(tag_items)
    tag_validation = sanitize_youtube_tags(generated_tag_text)
    metadata["tags"] = tag_validation["csv"]

    project["metadata_context"] = {
        "clip_happening": happening,
        "player_name": player,
        "generated_at": datetime.now().isoformat(timespec="seconds")
    }

    draft_key = (
        "top10_draft"
        if project_type == "top10"
        else "solo_draft"
    )

    project[draft_key] = {
        "title": str(metadata.get("title") or subject)[:100],
        "description": str(metadata.get("description") or ""),
        "tags": str(metadata.get("tags") or ""),
        "thumbnail_plan": str(
            metadata.get("thumbnail_plan") or ""
        )
    }

    project = save_project(project)

    return {
        "found": True,
        "ok": True,
        "metadata": project[draft_key],
        "project": project
    }


@router.post("/api/content-studio/project/{project_id}/metadata-suggestion")
def create_content_studio_metadata_suggestion_api_alias(
    project_id: str,
    request: MetadataSuggestionRequest
):
    return create_content_studio_metadata_suggestion(project_id, request)


@router.post("/content-studio/metadata-suggestion/{project_id}")
def create_content_studio_metadata_suggestion_legacy_alias(
    project_id: str,
    request: MetadataSuggestionRequest
):
    return create_content_studio_metadata_suggestion(project_id, request)


@router.post("/content-studio/project/{project_id}/thumbnail")
async def upload_content_studio_thumbnail(
    project_id: str,
    thumbnail: UploadFile = File(...)
):
    ensure_content_studio_folders()
    project = load_project(project_id)
    if not project:
        return {"found": False, "message": "Project not found"}

    extension = os.path.splitext(thumbnail.filename or "")[1].lower()
    if extension not in [".jpg", ".jpeg", ".png"]:
        raise HTTPException(status_code=400, detail="Thumbnail must be JPG or PNG.")

    project_thumbnail_dir = os.path.join(THUMBNAILS_DIR, project_id)
    os.makedirs(project_thumbnail_dir, exist_ok=True)
    filename = f"thumbnail{extension}"
    file_path = os.path.join(project_thumbnail_dir, filename)

    with open(file_path, "wb") as target:
        shutil.copyfileobj(thumbnail.file, target)

    project["thumbnail"] = {
        "filename": filename,
        "file_path": file_path.replace("\\", "/"),
        "preview_url": f"/content-studio/thumbnail/{project_id}/{filename}"
    }
    project = save_project(project)

    return {"found": True, "ok": True, "thumbnail": project["thumbnail"], "project": project}


@router.get("/content-studio/thumbnail/{project_id}/{filename}")
def preview_content_studio_thumbnail(project_id: str, filename: str):
    file_path = os.path.join(THUMBNAILS_DIR, project_id, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Thumbnail not found.")
    media_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"
    return FileResponse(file_path, media_type=media_type, headers={"Cache-Control": "no-cache"})


@router.get("/content-studio/youtube/playlists")
def get_content_studio_youtube_playlists():
    try:
        playlists = list_owned_playlists()
        return {"ok": True, "playlists": playlists, "count": len(playlists), "message": "Playlists loaded." if playlists else "No owned playlists were found on the authorized channel."}
    except Exception as error:
        raw = str(error or "")
        try:
            parsed = json.loads(raw)
        except Exception:
            parsed = explain_youtube_error(error)
        return {"ok": False, "playlists": [], **parsed}


@router.post("/content-studio/youtube/reconnect")
def reconnect_content_studio_youtube():
    from services.youtube_oauth import TOKEN_FILE
    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)
        return {"ok": True, "message": "Saved YouTube authorization was cleared. The next YouTube action will open Google sign-in."}
    except Exception as error:
        return {"ok": False, "message": "CourtVision could not clear the saved YouTube authorization.", "resolution": "Close other CourtVision processes and delete backend/token_youtube_analytics.json manually.", "technical_detail": str(error)}


@router.post("/content-studio/project/{project_id}/youtube/upload")
def upload_content_studio_project_to_youtube(
    project_id: str,
    title: str = Form(...),
    description: str = Form(""),
    tags: str = Form(""),
    privacy_status: str = Form("private"),
    publish_at: str = Form(""),
    playlist_ids: str = Form("[]")
):
    project = load_project(project_id)
    if not project:
        return {"found": False, "ok": False, "message": "Project not found"}

    if not project.get("preview_confirmed"):
        return {
            "found": True,
            "ok": False,
            "message": "Confirm the final rendered preview before uploading."
        }

    rendered = project.get("rendered_video") or {}
    video_path = str(rendered.get("file_path") or "").replace("/", os.sep)
    if not video_path or not os.path.exists(video_path):
        return {"found": True, "ok": False, "message": "Rendered MP4 not found."}

    try:
        parsed_playlists = json.loads(playlist_ids or "[]")
        if not isinstance(parsed_playlists, list):
            parsed_playlists = []
    except Exception:
        parsed_playlists = []

    thumbnail_path = str((project.get("thumbnail") or {}).get("file_path") or "").replace("/", os.sep)
    tag_validation = sanitize_youtube_tags(tags)
    safe_tags = tag_validation["csv"]

    try:
        result = upload_video(
            video_path=video_path,
            title=title,
            description=description,
            tags=safe_tags,
            category_id="17",
            privacy_status=privacy_status,
            made_for_kids=False,
            publish_at=publish_at,
            thumbnail_path=thumbnail_path,
            playlist_ids=parsed_playlists
        )
    except Exception as error:
        raw = str(error or "")
        try:
            detail = json.loads(raw)
        except Exception:
            detail = explain_youtube_error(error)
        return {"found": True, "ok": False, **detail}

    project["youtube_upload"] = {
        **result,
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "title": title,
        "description": description,
        "tags": safe_tags,
        "tag_validation": tag_validation
    }
    project["status"] = "uploaded"
    project["trashed"] = True
    project["trashed_at"] = datetime.now().isoformat(timespec="seconds")
    project["trash_reason"] = "Uploaded to YouTube"
    project = save_project(project)

    return {"found": True, "ok": True, "result": result, "project": project}


@router.get("/content-studio/trash")
def get_content_studio_trash():
    ensure_content_studio_folders()
    projects = []
    for filename in os.listdir(PROJECTS_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(PROJECTS_DIR, filename), "r", encoding="utf-8") as source:
                project = json.load(source)
            if project.get("trashed"):
                projects.append(project)
        except Exception:
            continue

    projects.sort(
        key=lambda item: item.get("trashed_at", item.get("updated_at", "")),
        reverse=True
    )
    return {"projects": projects}


@router.post("/content-studio/project/{project_id}/trash")
def trash_content_studio_project(project_id: str):
    project = load_project(project_id)
    if not project:
        return {"found": False, "ok": False, "message": "Project not found"}

    project["trashed"] = True
    project["trashed_at"] = datetime.now().isoformat(timespec="seconds")
    project["status_before_trash"] = project.get("status", "draft")
    project["status"] = "trash"
    project = save_project(project)
    return {"found": True, "ok": True, "project": project}


@router.post("/content-studio/project/{project_id}/restore")
def restore_content_studio_project(project_id: str):
    project = load_project(project_id)
    if not project:
        return {"found": False, "ok": False, "message": "Project not found"}

    project["trashed"] = False
    project["restored_at"] = datetime.now().isoformat(timespec="seconds")
    project["status"] = project.get("status_before_trash") or "draft"
    project = save_project(project)
    return {"found": True, "ok": True, "project": project}


@router.delete("/content-studio/project/{project_id}/permanent")
def permanently_delete_content_studio_project(project_id: str):
    ensure_content_studio_folders()
    path = project_path(project_id)

    for folder in [
        os.path.join(CLIPS_DIR, project_id),
        os.path.join(RENDERED_DIR, project_id),
        os.path.join(THUMBNAILS_DIR, project_id),
    ]:
        if os.path.exists(folder):
            shutil.rmtree(folder, ignore_errors=True)

    if os.path.exists(path):
        os.remove(path)

    clear_render_cancel(project_id)
    RENDER_JOBS.pop(project_id, None)
    SOLO_EXPORT_JOBS.pop(project_id, None)

    return {"ok": True, "message": "Project permanently deleted", "project_id": project_id}


@router.delete("/content-studio/project/{project_id}")
def delete_content_studio_project(project_id: str):
    return trash_content_studio_project(project_id)
