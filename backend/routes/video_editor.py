from fastapi import APIRouter
from services.ffmpeg_service import get_ffmpeg_status

router = APIRouter()


@router.get("/video-editor/status")
def video_editor_status():
    return {
        "status": "ok",
        "module": "Video Editor",
        "ffmpeg": get_ffmpeg_status(),
        "features": {
            "upload_clips": True,
            "solo_highlights": True,
            "top10_projects": True,
            "preview_generation": True,
            "thumbnail_generation": True,
            "rendering": True
        }
    }


@router.get("/video-editor/templates")
def get_video_templates():
    return {
        "solo_highlight": {
            "intro": False,
            "outro": True,
            "number_overlay": False,
            "music": False
        },
        "top10": {
            "intro": True,
            "outro": True,
            "number_overlay": True,
            "music": True
        }
    }


@router.get("/video-editor/project-types")
def project_types():
    return {
        "types": [
            {
                "id": "solo",
                "name": "Solo Highlight"
            },
            {
                "id": "top10",
                "name": "Top 10 Video"
            }
        ]
    }