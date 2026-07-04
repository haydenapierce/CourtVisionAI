from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Optional
import os
import shutil
import uuid
import json
from datetime import datetime, timedelta
from services.ffmpeg_service import render_content_studio_project, get_video_duration_seconds

router = APIRouter()

BASE_UPLOAD_DIR = os.path.join("uploads", "content_studio")
CLIPS_DIR = os.path.join(BASE_UPLOAD_DIR, "clips")
PROJECTS_DIR = os.path.join(BASE_UPLOAD_DIR, "projects")
RENDERED_DIR = os.path.join(BASE_UPLOAD_DIR, "rendered")
THUMBNAILS_DIR = os.path.join(BASE_UPLOAD_DIR, "thumbnails")
TEMPLATES_DIR = os.path.join(BASE_UPLOAD_DIR, "templates")
MUSIC_DIR = os.path.join(TEMPLATES_DIR, "music")

INTRO_FILE = os.path.join(TEMPLATES_DIR, "intro.mp4")
OUTRO_FILE = os.path.join(TEMPLATES_DIR, "outro.png")

ALLOWED_VIDEO_EXTENSIONS = [".mp4"]
ALLOWED_MUSIC_EXTENSIONS = [".mp3", ".wav", ".m4a"]

CONTENT_STUDIO_STATUS_CACHE = {
    "created_at": None,
    "payload": None
}

CONTENT_STUDIO_STATUS_CACHE_SECONDS = 60


class ClipEdit(BaseModel):
    clip_id: str
    order: int = 1
    title: str = ""
    trim_start: float = 0
    trim_end: float = 0
    duration_seconds: float = 0
    selected_for_top10: bool = True


class MetadataEdit(BaseModel):
    title: str = ""
    description: str = ""
    tags: str = ""
    thumbnail_plan: str = ""


class ProjectEdit(BaseModel):
    project_name: str = ""
    clips: List[ClipEdit] = []
    top10_draft: Optional[MetadataEdit] = None
    solo_draft: Optional[MetadataEdit] = None


def ensure_content_studio_folders():
    for folder in [
        BASE_UPLOAD_DIR,
        CLIPS_DIR,
        PROJECTS_DIR,
        RENDERED_DIR,
        THUMBNAILS_DIR,
        TEMPLATES_DIR,
        MUSIC_DIR
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


def get_template_status():
    ensure_content_studio_folders()

    music_files = []

    if os.path.exists(MUSIC_DIR):
        music_files = [
            name for name in os.listdir(MUSIC_DIR)
            if os.path.splitext(name)[1].lower() in ALLOWED_MUSIC_EXTENSIONS
        ]

    return {
        "intro_exists": os.path.exists(INTRO_FILE),
        "intro_path": INTRO_FILE.replace("\\", "/"),
        "outro_exists": os.path.exists(OUTRO_FILE),
        "outro_path": OUTRO_FILE.replace("\\", "/"),
        "music_folder_exists": os.path.exists(MUSIC_DIR),
        "music_count": len(music_files),
        "music_files": music_files,
        "solo_template": {
            "intro": "off",
            "clip": "uploaded MP4",
            "outro": "outro.png held for 15 seconds"
        },
        "top10_template": {
            "intro": "intro.mp4",
            "clips": "10 selected clips in saved order",
            "outro": "outro.png held for 15 seconds",
            "music": "cycles through music folder"
        }
    }


def project_path(project_id):
    return os.path.join(PROJECTS_DIR, f"{project_id}.json")


def load_project(project_id):
    path = project_path(project_id)

    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_project(project):
    ensure_content_studio_folders()

    path = project_path(project["project_id"])

    project["updated_at"] = datetime.now().isoformat()

    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, indent=2)

    return project


def clone_clip_for_split(existing_clips, split_clip_id):
    if "_split_" not in split_clip_id:
        return None

    base_clip_id = split_clip_id.split("_split_")[0]

    for clip in existing_clips:
        if clip.get("clip_id") == base_clip_id:
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
            "music": MUSIC_DIR
        },
        "templates": get_template_status()
    }

    CONTENT_STUDIO_STATUS_CACHE["created_at"] = datetime.now()
    CONTENT_STUDIO_STATUS_CACHE["payload"] = payload

    return payload


@router.get("/content-studio/templates")
def content_studio_templates():
    return get_template_status()


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
        "render_status": "not_rendered",
        "rendered_video": None,
        "render_settings": {
            "intro_enabled": project_type == "top10",
            "intro_file": "intro.mp4" if project_type == "top10" else None,
            "intro_to_clip_fade_seconds": 0,
            "outro_enabled": True,
            "outro_file": "outro.png",
            "outro_hold_seconds": 15,
            "music_enabled": project_type == "top10",
            "music_mode": "cycle_folder",
            "music_folder": "music",
            "number_overlay_enabled": project_type == "top10"
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
                projects.append(json.load(f))
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
def edit_content_studio_project(project_id: str, edit: ProjectEdit):
    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
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
            base_clip = clone_clip_for_split(existing_clips, update.clip_id)

        if not base_clip:
            continue

        base_clip["clip_id"] = update.clip_id
        base_clip["title"] = update.title or base_clip.get("title", "")
        base_clip["order"] = index
        base_clip["trim_start"] = max(0, float(update.trim_start or 0))
        base_clip["trim_end"] = max(0, float(update.trim_end or 0))
        base_clip["duration_seconds"] = max(0, float(update.duration_seconds or base_clip.get("duration_seconds") or 0))
        base_clip["selected_for_top10"] = bool(update.selected_for_top10)

        rebuilt_clips.append(base_clip)

    project["clips"] = rebuilt_clips
    project["clip_count"] = len(rebuilt_clips)

    if edit.top10_draft:
        project["top10_draft"] = edit.top10_draft.dict()

    if edit.solo_draft:
        project["solo_draft"] = edit.solo_draft.dict()

    project["status"] = "edited"
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




@router.post("/content-studio/project/{project_id}/render")
def render_content_studio_project_route(project_id: str):
    ensure_content_studio_folders()

    project = load_project(project_id)

    if not project:
        return {
            "found": False,
            "message": "Project not found"
        }

    project["render_status"] = "rendering"
    save_project(project)

    result = render_content_studio_project(
        project=project,
        templates_dir=TEMPLATES_DIR,
        rendered_dir=RENDERED_DIR
    )

    if not result.get("ok"):
        project["render_status"] = "failed"
        project["render_error"] = result
        save_project(project)

        return {
            "found": True,
            "ok": False,
            "message": result.get("message", "Render failed."),
            "result": result,
            "project": project
        }

    output_path = result.get("output_path")
    output_filename = os.path.basename(output_path)

    project["render_status"] = "rendered"
    project["render_error"] = None
    project["rendered_video"] = {
        "filename": output_filename,
        "file_path": output_path.replace("\\", "/"),
        "preview_url": f"/content-studio/rendered/{project_id}/{output_filename}",
        "duration_seconds": result.get("duration_seconds", 0),
        "music_used": result.get("music_used"),
        "rendered_at": datetime.now().isoformat()
    }

    project = save_project(project)

    return {
        "found": True,
        "ok": True,
        "message": "Project rendered successfully.",
        "rendered_video": project["rendered_video"],
        "project": project
    }


@router.get("/content-studio/rendered/{project_id}/{filename}")
def preview_rendered_content_studio_video(project_id: str, filename: str):
    file_path = os.path.join(RENDERED_DIR, project_id, filename)

    if not os.path.exists(file_path):
        return {
            "found": False,
            "message": "Rendered video not found"
        }

    return FileResponse(file_path, media_type="video/mp4")


@router.get("/content-studio/preview/{project_id}/{filename}")
def preview_content_studio_clip(project_id: str, filename: str):
    file_path = os.path.join(CLIPS_DIR, project_id, filename)

    if not os.path.exists(file_path):
        return {
            "found": False,
            "message": "Clip not found"
        }

    return FileResponse(file_path, media_type="video/mp4")


@router.delete("/content-studio/project/{project_id}")
def delete_content_studio_project(project_id: str):
    ensure_content_studio_folders()

    path = project_path(project_id)
    project_clip_folder = os.path.join(CLIPS_DIR, project_id)

    if os.path.exists(path):
        os.remove(path)

    if os.path.exists(project_clip_folder):
        shutil.rmtree(project_clip_folder)

    return {
        "message": "Project deleted",
        "project_id": project_id
    }
