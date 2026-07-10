import os
import subprocess
import shutil
import random
from datetime import datetime


CONFIGURED_FFMPEG_PATH = (
    r"C:\Users\hpier\AppData\Local\Microsoft\WinGet\Packages"
    r"\BtbN.FFmpeg.GPL.8.1_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-n8.1.1-9-g58d4114d36-win64-gpl-8.1"
    r"\bin\ffmpeg.exe"
)

FFMPEG_PATH = (
    os.environ.get("FFMPEG_PATH")
    or (CONFIGURED_FFMPEG_PATH if os.path.exists(CONFIGURED_FFMPEG_PATH) else shutil.which("ffmpeg"))
    or CONFIGURED_FFMPEG_PATH
)
FFPROBE_PATH = (
    os.environ.get("FFPROBE_PATH")
    or (FFMPEG_PATH.replace("ffmpeg.exe", "ffprobe.exe") if str(FFMPEG_PATH).lower().endswith("ffmpeg.exe") else shutil.which("ffprobe"))
    or str(FFMPEG_PATH).replace("ffmpeg", "ffprobe")
)

VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
FADE_SECONDS = 0.10
OUTRO_SECONDS = 15


def ffmpeg_exists():
    return os.path.exists(FFMPEG_PATH)


def get_ffmpeg_status():
    if not ffmpeg_exists():
        return {
            "available": False,
            "path": FFMPEG_PATH,
            "message": "FFmpeg was not found at the saved path."
        }

    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-version"],
            capture_output=True,
            text=True,
            timeout=10
        )

        return {
            "available": result.returncode == 0,
            "path": FFMPEG_PATH,
            "message": "FFmpeg is ready" if result.returncode == 0 else "FFmpeg did not run correctly",
            "version_preview": result.stdout.splitlines()[0] if result.stdout else ""
        }

    except Exception as error:
        return {
            "available": False,
            "path": FFMPEG_PATH,
            "message": str(error)
        }


def run_command(command, timeout=600):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join([str(item) for item in command])
        }

    except Exception as error:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(error),
            "command": " ".join([str(item) for item in command])
        }


def safe_seconds(value, fallback=0):
    try:
        number = float(value or fallback)
        return max(0, number)
    except Exception:
        return fallback


def get_video_duration_seconds(video_path):
    if not ffmpeg_exists() or not os.path.exists(video_path):
        return 0

    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path
            ],
            capture_output=True,
            text=True,
            timeout=20
        )

        if result.returncode != 0:
            return 0

        return round(float(result.stdout.strip() or 0), 2)

    except Exception:
        return 0


def make_preview_thumbnail(video_path, output_path):
    if not ffmpeg_exists() or not os.path.exists(video_path):
        return False

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    try:
        result = subprocess.run(
            [
                FFMPEG_PATH,
                "-y",
                "-ss",
                "00:00:01",
                "-i",
                video_path,
                "-frames:v",
                "1",
                "-q:v",
                "2",
                output_path
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        return result.returncode == 0 and os.path.exists(output_path)

    except Exception:
        return False


def _candidate_paths(*parts):
    relative = os.path.join(*parts)
    return [
        relative,
        os.path.join("backend", relative),
        os.path.abspath(relative),
        os.path.abspath(os.path.join("backend", relative))
    ]


def first_existing_path(paths):
    for path in paths:
        if path and os.path.exists(path):
            return path
    return ""


def resolve_branding_asset(filename, templates_dir=""):
    candidates = []
    candidates.extend(_candidate_paths("assets", "branding", filename))
    if templates_dir:
        candidates.append(os.path.join(templates_dir, filename))
    candidates.append(os.path.join("uploads", "content_studio", "templates", filename))
    candidates.append(os.path.join("backend", "uploads", "content_studio", "templates", filename))
    return first_existing_path(candidates)


def resolve_countdown_asset(number):
    filename = f"{int(number)}.png"
    candidates = []
    candidates.extend(_candidate_paths("assets", "countdown", filename))
    return first_existing_path(candidates)


def get_video_scale_filter():
    return (
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
        "fps=30"
    )


def _effective_duration(input_path, trim_start=0, trim_end=0):
    trim_start = safe_seconds(trim_start, 0)
    trim_end = safe_seconds(trim_end, 0)

    if trim_end > trim_start:
        return round(trim_end - trim_start, 3)

    source_duration = get_video_duration_seconds(input_path)
    if source_duration > trim_start:
        return round(source_duration - trim_start, 3)

    return 0


def normalize_clip_segment(
    input_path,
    output_path,
    trim_start=0,
    trim_end=0,
    overlay_png_path=None,
    fade_seconds=FADE_SECONDS
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    trim_start = safe_seconds(trim_start, 0)
    trim_end = safe_seconds(trim_end, 0)
    duration = _effective_duration(input_path, trim_start, trim_end)

    command = [FFMPEG_PATH, "-y"]

    if trim_start > 0:
        command.extend(["-ss", str(trim_start)])

    command.extend(["-i", input_path])

    if overlay_png_path and os.path.exists(overlay_png_path):
        command.extend(["-i", overlay_png_path])

    if trim_end > trim_start:
        command.extend(["-t", str(round(trim_end - trim_start, 3))])

    fade = max(0, float(fade_seconds or 0))
    fade_filter = ""
    if fade > 0 and duration > fade:
        fade_out_start = max(0, duration - fade)
        fade_filter = f",fade=t=in:st=0:d={fade},fade=t=out:st={fade_out_start}:d={fade}"

    base_filter = f"{get_video_scale_filter()}{fade_filter}"

    if overlay_png_path and os.path.exists(overlay_png_path):
        # Small countdown PNG stays in bottom-left for the full clip.
        filter_complex = (
            f"[0:v]{base_filter},format=rgba[base];"
            "[1:v]scale=145:-1[ov];"
            "[base][ov]overlay=35:H-h-35:format=auto,format=yuv420p[v]"
        )
        command.extend([
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "0:a?"
        ])
    else:
        command.extend([
            "-vf",
            f"{base_filter},format=yuv420p",
            "-map",
            "0:v",
            "-map",
            "0:a?"
        ])

    command.extend([
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        output_path
    ])

    return run_command(command, timeout=900)


def make_outro_segment(outro_png_path, output_path, seconds=OUTRO_SECONDS):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    command = [
        FFMPEG_PATH,
        "-y",
        "-loop",
        "1",
        "-i",
        outro_png_path,
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        str(seconds),
        "-vf",
        f"{get_video_scale_filter()},format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path
    ]

    return run_command(command, timeout=300)


def concat_segments(segment_paths, concat_list_path, output_path):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(concat_list_path, "w", encoding="utf-8") as f:
        for path in segment_paths:
            normalized = os.path.abspath(path).replace("\\", "/")
            f.write(f"file '{normalized}'\n")

    command = [
        FFMPEG_PATH,
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        concat_list_path,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        output_path
    ]

    return run_command(command, timeout=900)


def get_music_files(music_dir):
    if not os.path.exists(music_dir):
        return []

    allowed = [".mp3", ".wav", ".m4a"]

    return [
        os.path.join(music_dir, name)
        for name in os.listdir(music_dir)
        if os.path.splitext(name)[1].lower() in allowed
    ]


def add_background_music(video_path, music_dir, output_path, volume=0.13):
    music_files = get_music_files(music_dir)

    if not music_files:
        return {
            "ok": True,
            "message": "No music files found. Kept video without background music.",
            "output_path": video_path,
            "music_used": None
        }

    selected_music = random.choice(music_files)

    command = [
        FFMPEG_PATH,
        "-y",
        "-i",
        video_path,
        "-stream_loop",
        "-1",
        "-i",
        selected_music,
        "-filter_complex",
        f"[1:a]volume={volume}[music];[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[a]",
        "-map",
        "0:v",
        "-map",
        "[a]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        output_path
    ]

    result = run_command(command, timeout=900)
    result["music_used"] = os.path.basename(selected_music)
    return result


def _safe_filename(value):
    clean = "".join(char for char in str(value or "clip") if char.isalnum() or char in (" ", "-", "_")).strip()
    return "_".join(clean.split())[:80] or "clip"


def _selected_top10_clips(project):
    clips = sorted(project.get("clips", []), key=lambda clip: int(clip.get("order") or 999))
    selected = [clip for clip in clips if clip.get("selected_for_top10", True)]
    return selected[:10]


def render_content_studio_project(project, templates_dir, rendered_dir):
    if not ffmpeg_exists():
        return {
            "ok": False,
            "message": "FFmpeg is not available.",
            "error": get_ffmpeg_status(),
            "output_path": None
        }

    project_id = project.get("project_id")
    project_type = project.get("project_type", "solo")
    project_render_dir = os.path.join(rendered_dir, project_id)
    temp_dir = os.path.join(project_render_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    intro_file = resolve_branding_asset("intro.mp4", templates_dir)
    outro_file = resolve_branding_asset("outro.png", templates_dir)
    music_dir = os.path.join(templates_dir, "music")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_output = os.path.join(project_render_dir, f"{project_id}_{timestamp}_base.mp4")
    final_output = os.path.join(project_render_dir, f"{project_id}_{timestamp}_final.mp4")
    concat_list = os.path.join(temp_dir, "concat_list.txt")

    if project_type == "top10":
        timeline_clips = _selected_top10_clips(project)
    else:
        timeline_clips = sorted(project.get("clips", []), key=lambda clip: int(clip.get("order") or 999))

    if not timeline_clips:
        return {
            "ok": False,
            "message": "No clips found in the project timeline.",
            "output_path": None
        }

    if project_type == "top10" and len(timeline_clips) < 10:
        return {
            "ok": False,
            "message": f"Top 10 rendering needs 10 selected clips. You currently have {len(timeline_clips)} selected.",
            "output_path": None
        }

    if not outro_file:
        return {
            "ok": False,
            "message": "Rendering needs outro.png. Put it in backend/assets/branding/outro.png or uploads/content_studio/templates/outro.png.",
            "output_path": None
        }

    segments = []
    logs = []

    # Intro is optional. If it exists, use it. If not, top 10 starts with #10 immediately.
    if project_type == "top10" and intro_file:
        intro_segment = os.path.join(temp_dir, "000_intro.mp4")
        intro_result = normalize_clip_segment(intro_file, intro_segment, 0, 0, fade_seconds=0)
        logs.append(intro_result)

        if intro_result.get("ok"):
            segments.append(intro_segment)

    for index, clip in enumerate(timeline_clips, start=1):
        input_path = clip.get("file_path", "").replace("/", os.sep)

        if not os.path.exists(input_path):
            logs.append({
                "ok": False,
                "message": f"Missing clip file: {input_path}",
                "clip": clip.get("title")
            })
            continue

        overlay_path = None
        if project_type == "top10":
            countdown_number = 11 - index
            overlay_path = resolve_countdown_asset(countdown_number)
            if not overlay_path:
                return {
                    "ok": False,
                    "message": f"Missing countdown overlay {countdown_number}.png in backend/assets/countdown/.",
                    "output_path": None
                }

        segment_path = os.path.join(temp_dir, f"{index:03d}_clip.mp4")
        result = normalize_clip_segment(
            input_path,
            segment_path,
            clip.get("trim_start", 0),
            clip.get("trim_end", 0),
            overlay_png_path=overlay_path,
            fade_seconds=FADE_SECONDS
        )
        logs.append(result)

        if not result.get("ok"):
            return {
                "ok": False,
                "message": f"Clip render failed: {clip.get('title')}",
                "error": result,
                "output_path": None
            }

        segments.append(segment_path)

    outro_segment = os.path.join(temp_dir, "999_outro.mp4")
    outro_result = make_outro_segment(outro_file, outro_segment, seconds=OUTRO_SECONDS)
    logs.append(outro_result)

    if not outro_result.get("ok"):
        return {
            "ok": False,
            "message": "Outro render failed.",
            "error": outro_result,
            "output_path": None
        }

    segments.append(outro_segment)

    concat_result = concat_segments(segments, concat_list, base_output)
    logs.append(concat_result)

    if not concat_result.get("ok"):
        return {
            "ok": False,
            "message": "Final concat failed.",
            "error": concat_result,
            "output_path": None
        }

    music_used = None
    output_path = base_output

    if project_type == "top10":
        music_result = add_background_music(base_output, music_dir, final_output)
        logs.append(music_result)
        music_used = music_result.get("music_used")

        if music_result.get("ok") and os.path.exists(final_output):
            output_path = final_output

    duration = get_video_duration_seconds(output_path)

    return {
        "ok": True,
        "message": "Project rendered successfully.",
        "output_path": output_path,
        "duration_seconds": duration,
        "music_used": music_used,
        "project_type": project_type,
        "logs": logs[-8:]
    }


def render_content_studio_solos(project, templates_dir, rendered_dir):
    if not ffmpeg_exists():
        return {
            "ok": False,
            "message": "FFmpeg is not available.",
            "error": get_ffmpeg_status(),
            "exports": []
        }

    project_id = project.get("project_id")
    project_render_dir = os.path.join(rendered_dir, project_id, "solos")
    temp_dir = os.path.join(project_render_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    outro_file = resolve_branding_asset("outro.png", templates_dir)

    if not outro_file:
        return {
            "ok": False,
            "message": "Solo exports need outro.png. Put it in backend/assets/branding/outro.png or uploads/content_studio/templates/outro.png.",
            "exports": []
        }

    clips = sorted(project.get("clips", []), key=lambda clip: int(clip.get("order") or 999))
    exports = []
    logs = []

    for index, clip in enumerate(clips, start=1):
        input_path = clip.get("file_path", "").replace("/", os.sep)

        if not os.path.exists(input_path):
            exports.append({
                "ok": False,
                "clip_id": clip.get("clip_id"),
                "title": clip.get("title"),
                "message": "Missing source file."
            })
            continue

        safe_title = _safe_filename(clip.get("title") or f"solo_{index}")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        solo_base = os.path.join(temp_dir, f"{index:03d}_{safe_title}_base.mp4")
        solo_outro = os.path.join(temp_dir, f"{index:03d}_{safe_title}_outro.mp4")
        solo_list = os.path.join(temp_dir, f"{index:03d}_{safe_title}_concat.txt")
        solo_output = os.path.join(project_render_dir, f"{index:03d}_{safe_title}_{timestamp}.mp4")

        clip_result = normalize_clip_segment(
            input_path,
            solo_base,
            clip.get("trim_start", 0),
            clip.get("trim_end", 0),
            fade_seconds=FADE_SECONDS
        )
        logs.append(clip_result)

        if not clip_result.get("ok"):
            exports.append({
                "ok": False,
                "clip_id": clip.get("clip_id"),
                "title": clip.get("title"),
                "message": "Clip render failed.",
                "error": clip_result
            })
            continue

        outro_result = make_outro_segment(outro_file, solo_outro, seconds=OUTRO_SECONDS)
        logs.append(outro_result)

        if not outro_result.get("ok"):
            exports.append({
                "ok": False,
                "clip_id": clip.get("clip_id"),
                "title": clip.get("title"),
                "message": "Outro render failed.",
                "error": outro_result
            })
            continue

        concat_result = concat_segments([solo_base, solo_outro], solo_list, solo_output)
        logs.append(concat_result)

        if not concat_result.get("ok"):
            exports.append({
                "ok": False,
                "clip_id": clip.get("clip_id"),
                "title": clip.get("title"),
                "message": "Final solo concat failed.",
                "error": concat_result
            })
            continue

        exports.append({
            "ok": True,
            "clip_id": clip.get("clip_id"),
            "title": clip.get("title"),
            "filename": os.path.basename(solo_output),
            "file_path": solo_output.replace("\\", "/"),
            "preview_url": f"/content-studio/rendered/{project_id}/solos/{os.path.basename(solo_output)}",
            "duration_seconds": get_video_duration_seconds(solo_output)
        })

    return {
        "ok": any(item.get("ok") for item in exports),
        "message": f"Exported {sum(1 for item in exports if item.get('ok'))} solo clips.",
        "exports": exports,
        "logs": logs[-8:]
    }
