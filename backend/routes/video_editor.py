from fastapi import APIRouter
from services.ffmpeg_service import get_ffmpeg_status

router = APIRouter()


@router.get("/video-editor/status")
def video_editor_status():
    return {
        "status": "ok",
        "module": "NBA Production Editor",
        "ffmpeg": get_ffmpeg_status(),
        "features": {
            "upload_long_source_or_clips": True,
            "rough_auto_clip_detection": True,
            "drag_rank_top10": True,
            "solo_highlight_exports": True,
            "bulk_solo_factory": True,
            "top10_countdown_rendering": True,
            "bottom_left_number_overlays": True,
            "clip_fades_0_1_seconds": True,
            "outro_png_exports": True,
            "preview_generation": True,
            "rendering": True
        }
    }


@router.get("/video-editor/templates")
def get_video_templates():
    return {
        "asset_folders": {
            "countdown": "backend/assets/countdown/10.png through 1.png",
            "branding": "backend/assets/branding/outro.png and optional intro.mp4",
            "legacy_templates_supported": "backend/uploads/content_studio/templates/outro.png and intro.mp4 still work"
        },
        "solo_highlight": {
            "intro": False,
            "outro": True,
            "number_overlay": False,
            "fade_in_seconds": 0.10,
            "fade_out_seconds": 0.10,
            "music": False
        },
        "top10": {
            "intro": "optional",
            "outro": True,
            "number_overlay": True,
            "number_overlay_position": "bottom-left",
            "fade_in_seconds": 0.10,
            "fade_out_seconds": 0.10,
            "music": "optional if music folder has files"
        }
    }


@router.get("/video-editor/project-types")
def project_types():
    return {
        "types": [
            {
                "id": "solo",
                "name": "Solo Highlight",
                "description": "One clip with 0.1 second fades and your outro PNG."
            },
            {
                "id": "top10",
                "name": "Top 10 Countdown",
                "description": "Rank 10 clips, apply bottom-left countdown PNG overlays, fade each clip, and attach outro."
            }
        ]
    }
