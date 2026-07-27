import os
import subprocess
import shutil
import random
import queue
import threading
import re
import tempfile
import time
from datetime import datetime
from fractions import Fraction


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

CANCELLED_RENDER_PROJECTS = set()
ACTIVE_FFMPEG_PROCESSES = {}


def cancel_render(project_id):
    project_key = str(project_id)
    CANCELLED_RENDER_PROJECTS.add(project_key)
    process = ACTIVE_FFMPEG_PROCESSES.get(project_key)
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass


def clear_render_cancel(project_id):
    CANCELLED_RENDER_PROJECTS.discard(str(project_id))


def is_render_cancelled(project_id):
    return str(project_id) in CANCELLED_RENDER_PROJECTS


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



def video_has_audio(input_path):
    """Return True when the source contains at least one audio stream."""
    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                input_path
            ],
            capture_output=True,
            text=True,
            timeout=12
        )
        return result.returncode == 0 and bool((result.stdout or "").strip())
    except Exception:
        return False

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


def run_ffmpeg_with_progress(
    command,
    duration_seconds=0,
    progress_callback=None,
    timeout=7200,
    project_id=""
):
    """
    Run FFmpeg and report actual encoded-media progress using FFmpeg's
    machine-readable `-progress pipe:1` output.
    """
    duration_seconds = max(0.001, float(duration_seconds or 0))

    progress_command = list(command)
    # `-progress` is a global FFmpeg option. Insert it near the beginning so
    # commands may safely contain more than one output (the final MP4 plus the
    # live rendered-frame JPEG used by the editor).
    progress_command[1:1] = ["-progress", "pipe:1", "-nostats"]

    stderr_file = tempfile.TemporaryFile(mode="w+t", encoding="utf-8")

    try:
        process = subprocess.Popen(
            progress_command,
            stdout=subprocess.PIPE,
            stderr=stderr_file,
            text=True,
            universal_newlines=True,
            bufsize=1
        )

        project_key = str(project_id or "")
        if project_key:
            ACTIVE_FFMPEG_PROCESSES[project_key] = process

        last_fraction = 0.0
        last_callback_fraction = -1.0
        last_callback_at = 0.0

        def publish_progress(fraction, force=False):
            nonlocal last_callback_fraction, last_callback_at
            if not progress_callback:
                return
            now = time.monotonic()
            meaningful_step = fraction - last_callback_fraction >= 0.0025
            enough_time = now - last_callback_at >= 0.35
            if force or meaningful_step or enough_time:
                progress_callback(fraction)
                last_callback_fraction = fraction
                last_callback_at = now

        progress_lines = queue.Queue()

        def read_progress_lines():
            try:
                if process.stdout:
                    for output_line in iter(process.stdout.readline, ""):
                        progress_lines.put(output_line)
            finally:
                progress_lines.put(None)

        reader = threading.Thread(target=read_progress_lines, daemon=True)
        reader.start()

        reader_finished = False
        while True:
            try:
                line = progress_lines.get(timeout=0.5)
                if line is None:
                    reader_finished = True
                    line = ""
            except queue.Empty:
                line = ""
                # Keep the worker/UI heartbeat alive while FFmpeg is still
                # finalizing a frame, flushing the encoder, or moving atoms.
                # The percentage stays honest; ETA and elapsed time continue.
                if process.poll() is None:
                    publish_progress(last_fraction, force=True)

            if line:
                key, separator, value = line.strip().partition("=")

                if separator and key in {"out_time_ms", "out_time_us"}:
                    try:
                        encoded_seconds = float(value or 0) / 1_000_000
                        fraction = max(
                            last_fraction,
                            min(0.995, encoded_seconds / duration_seconds)
                        )
                        last_fraction = fraction
                        publish_progress(fraction)
                    except Exception:
                        pass

                elif separator and key == "out_time":
                    try:
                        hours, minutes, seconds = value.split(":")
                        encoded_seconds = (
                            float(hours) * 3600 +
                            float(minutes) * 60 +
                            float(seconds)
                        )
                        fraction = max(
                            last_fraction,
                            min(0.995, encoded_seconds / duration_seconds)
                        )
                        last_fraction = fraction
                        publish_progress(fraction)
                    except Exception:
                        pass

                elif separator and key == "progress" and value == "end":
                    last_fraction = 1.0
                    publish_progress(1.0, force=True)

            if process.poll() is not None and (reader_finished or progress_lines.empty()):
                break

        return_code = process.wait(timeout=timeout)
        stderr_file.seek(0)
        stderr_text = stderr_file.read()

        return {
            "ok": return_code == 0,
            "returncode": return_code,
            "stdout": "",
            "stderr": stderr_text,
            "command": " ".join([str(item) for item in progress_command])
        }

    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except Exception:
            pass

        stderr_file.seek(0)
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"FFmpeg timed out after {timeout} seconds.\n{stderr_file.read()}",
            "command": " ".join([str(item) for item in progress_command])
        }

    except Exception as error:
        return {
            "ok": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(error),
            "command": " ".join([str(item) for item in progress_command])
        }

    finally:
        if project_id:
            ACTIVE_FFMPEG_PROCESSES.pop(str(project_id), None)
        stderr_file.close()


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


def get_video_fps(video_path):
    """Return the source average frame rate, or 0 when FFprobe cannot read it."""
    if not os.path.exists(video_path):
        return 0

    try:
        result = subprocess.run(
            [
                FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=avg_frame_rate",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path
            ],
            capture_output=True,
            text=True,
            timeout=20
        )

        value = str(result.stdout or "").strip()
        if result.returncode != 0 or not value or value == "0/0":
            return 0

        return round(float(Fraction(value)), 3)
    except Exception:
        return 0


def get_video_scale_filter(target_fps=60, interpolation_mode="auto", source_fps=0):
    source_fps = float(source_fps or 0)
    interpolation_mode = str(interpolation_mode or "auto").lower()

    filters = [
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=decrease",
        f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:(ow-iw)/2:(oh-ih)/2"
    ]

    # 0 means preserve the project's detected original frame rate.
    if not target_fps or float(target_fps) <= 0:
        return ",".join(filters)

    target_fps = max(24, min(120, int(round(float(target_fps)))))
    should_interpolate = (
        interpolation_mode in {"auto", "motion", "minterpolate"}
        and source_fps > 0
        and source_fps + 0.5 < target_fps
    )

    if should_interpolate:
        filters.append(
            f"minterpolate=fps={target_fps}:mi_mode=mci:"
            "mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        )
    else:
        filters.append(f"fps={target_fps}")

    return ",".join(filters)


def _effective_duration(input_path, trim_start=0, trim_end=0):
    trim_start = safe_seconds(trim_start, 0)
    trim_end = safe_seconds(trim_end, 0)

    if trim_end > trim_start:
        return trim_end - trim_start

    source_duration = get_video_duration_seconds(input_path)
    if source_duration > trim_start:
        return source_duration - trim_start

    return 0




def get_video_dimensions(input_path):
    try:
        probe = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", input_path],
            capture_output=True, text=True, timeout=12
        )
        value = (probe.stdout or "").strip().splitlines()[0]
        width, height = value.lower().split("x", 1)
        return int(float(width)), int(float(height))
    except Exception:
        return 0, 0

def detect_active_video_crop(input_path):
    """Detect stable left/right pillarbox bars independently and crop safely inside them."""
    try:
        source_w, source_h = 0, 0
        duration = 0.0
        probe = subprocess.run(
            [FFPROBE_PATH, "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", input_path],
            capture_output=True, text=True, timeout=12
        )
        values = [line.strip() for line in (probe.stdout or "").splitlines() if line.strip()]
        if len(values) >= 2:
            source_w, source_h = int(float(values[0])), int(float(values[1]))
        if len(values) >= 3:
            duration = max(0.0, float(values[2]))
        if not source_w or not source_h:
            return None

        sample_times = [0.5]
        if duration > 4:
            sample_times = sorted(set(max(0.25, min(duration - 0.75, duration * ratio)) for ratio in (0.08, 0.3, 0.55, 0.8)))

        candidates = []
        pattern = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")
        for sample_time in sample_times:
            command = [
                FFMPEG_PATH, "-hide_banner", "-ss", f"{sample_time:.3f}", "-i", input_path,
                "-t", "1.8", "-vf", "cropdetect=48:2:0", "-an", "-f", "null", "-"
            ]
            result = subprocess.run(command, capture_output=True, text=True, timeout=18)
            for item in pattern.findall((result.stderr or "") + (result.stdout or "")):
                w, h, x, y = map(int, item)
                left = x
                right = source_w - (x + w)
                top = y
                bottom = source_h - (y + h)
                removed_x = left + right
                removed_y = top + bottom
                if (
                    removed_x >= source_w * 0.055
                    and removed_x <= source_w * 0.48
                    and removed_y <= source_h * 0.08
                    and left >= 0 and right >= 0
                ):
                    candidates.append((left, right, top, bottom))

        if not candidates:
            return None

        def percentile(values, fraction):
            ordered = sorted(int(v) for v in values)
            index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
            return ordered[index]

        # Evaluate each side separately because archival encodes are often asymmetric.
        left = percentile([item[0] for item in candidates], 0.72)
        right = percentile([item[1] for item in candidates], 0.72)
        # Blurred Side Fill only removes encoded left/right pillarbox bars.
        # Preserve the full vertical picture so the sharp foreground always
        # reaches the top and bottom of the 16:9 output.
        top = 0
        bottom = 0

        # Move a few pixels inside the detected picture boundary so compression noise
        # or a one-pixel matte cannot survive in the finished composition.
        safety_x = max(8, int(round(source_w * 0.009)))
        if left >= source_w * 0.025:
            left += safety_x
        if right >= source_w * 0.025:
            right += safety_x

        crop_x = max(0, min(source_w - 2, left))
        crop_y = max(0, min(source_h - 2, top))
        crop_w = source_w - crop_x - max(0, right)
        crop_h = source_h - crop_y - max(0, bottom)

        # H.264/yuv420 requires even dimensions and offsets.
        crop_x -= crop_x % 2
        crop_y -= crop_y % 2
        crop_w -= crop_w % 2
        crop_h -= crop_h % 2
        if crop_w < source_w * 0.5 or crop_h < source_h * 0.82:
            return None
        return (crop_w, crop_h, crop_x, crop_y)
    except Exception:
        return None


def normalize_clip_segment(
    input_path,
    output_path,
    trim_start=0,
    trim_end=0,
    overlay_png_path=None,
    fade_seconds=FADE_SECONDS,
    fade_in_seconds=None,
    fade_out_seconds=None,
    target_fps=60,
    interpolation_mode="auto",
    progress_callback=None,
    project_id="",
    frame_scale=1.0,
    frame_x=0.0,
    frame_y=0.0,
    preview_path=None,
    playback_rate=1.0,
    muted=False,
    blurred_side_fill=False,
    blur_crop_left_pct=0.0,
    blur_crop_right_pct=0.0,
    blur_crop_offset_pct=0.0
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    trim_start = safe_seconds(trim_start, 0)
    trim_end = safe_seconds(trim_end, 0)
    source_duration = _effective_duration(input_path, trim_start, trim_end)
    playback_rate = max(0.25, min(4.0, float(playback_rate or 1.0)))
    duration = max(0.05, source_duration / playback_rate)

    command = [FFMPEG_PATH, "-y", "-i", input_path]

    has_overlay = bool(overlay_png_path and os.path.exists(overlay_png_path))
    if has_overlay:
        command.extend(["-i", overlay_png_path])

    # Trim inside the filter graph rather than with output-level -ss/-t.
    # This keeps the editor's exact source in/out points independent of
    # keyframes, playback-rate changes, audio duration, and output FPS.

    if fade_in_seconds is None:
        fade_in_seconds = fade_seconds
    if fade_out_seconds is None:
        fade_out_seconds = fade_seconds

    fade_in = max(0.0, float(fade_in_seconds or 0))
    fade_out = max(0.0, float(fade_out_seconds or 0))
    source_fps = get_video_fps(input_path)

    video_filters = [
        f"trim=start={trim_start:.6f}:end={trim_start + source_duration:.6f}",
        "setpts=PTS-STARTPTS"
    ]
    if abs(playback_rate - 1.0) > 0.001:
        video_filters.append(f"setpts=PTS/{playback_rate:.6f}")
    video_filters.append(get_video_scale_filter(target_fps, interpolation_mode, source_fps))
    frame_scale = max(0.5, min(3.0, float(frame_scale or 1.0)))
    frame_x = max(-100.0, min(100.0, float(frame_x or 0.0)))
    frame_y = max(-100.0, min(100.0, float(frame_y or 0.0)))
    if abs(frame_scale - 1.0) > 0.001 or abs(frame_x) > 0.001 or abs(frame_y) > 0.001:
        scaled_w = max(VIDEO_WIDTH, int(round(VIDEO_WIDTH * frame_scale)))
        scaled_h = max(VIDEO_HEIGHT, int(round(VIDEO_HEIGHT * frame_scale)))
        max_x = max(0, scaled_w - VIDEO_WIDTH)
        max_y = max(0, scaled_h - VIDEO_HEIGHT)
        crop_x = max(0, min(max_x, int(round((max_x / 2) - (frame_x / 100.0) * (max_x / 2)))))
        crop_y = max(0, min(max_y, int(round((max_y / 2) - (frame_y / 100.0) * (max_y / 2)))))
        video_filters.extend([
            f"scale={scaled_w}:{scaled_h}",
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:{crop_x}:{crop_y}"
        ])
    if fade_in > 0 and duration > fade_in:
        video_filters.append(f"fade=t=in:st=0:d={fade_in}")
    if fade_out > 0 and duration > fade_out:
        video_filters.append(f"fade=t=out:st={max(0, duration-fade_out)}:d={fade_out}")

    base_filter = ",".join(video_filters)

    has_audio_stream = video_has_audio(input_path)
    audio_filters = []
    if has_audio_stream:
        audio_filters.extend([
            f"atrim=start={trim_start:.6f}:end={trim_start + source_duration:.6f}",
            "asetpts=PTS-STARTPTS"
        ])
    if muted and has_audio_stream:
        audio_filters.append("volume=0")
    elif has_audio_stream and abs(playback_rate - 1.0) > 0.001:
        remaining_rate = playback_rate
        while remaining_rate > 2.0 + 1e-6:
            audio_filters.append("atempo=2.0")
            remaining_rate /= 2.0
        while remaining_rate < 0.5 - 1e-6:
            audio_filters.append("atempo=0.5")
            remaining_rate /= 0.5
        audio_filters.append(f"atempo={remaining_rate:.6f}")
    if has_audio_stream and fade_in > 0 and duration > fade_in:
        audio_filters.append(f"afade=t=in:st=0:d={fade_in}")
    if has_audio_stream and fade_out > 0 and duration > fade_out:
        audio_filters.append(f"afade=t=out:st={max(0, duration-fade_out)}:d={fade_out}")

    preview_enabled = bool(preview_path)
    if preview_enabled:
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)

    # The preview branch is split after scaling, Pan/Crop, fades, overlays, and
    # motion interpolation. Therefore every JPEG written here is a genuine
    # output frame from the same filter graph used by the final MP4, including
    # newly generated interpolation frames. The small resolution keeps the
    # additional encode cost controlled.
    preview_cutoff = max(0.05, duration - max(0.35, fade_out))
    preview_filter = (
        f"select='lt(t,{preview_cutoff:.3f})',"
        # The preview is a monitor, not a second full-rate deliverable. Encoding
        # every 30/60 FPS frame to MJPEG made the main render compete with a
        # second video encode and was the main reason progress appeared to stall.
        # Four genuine post-effects frames per second stays visually live while
        # keeping the final MP4 encode prioritized.
        "fps=4,"
        "scale=480:270:force_original_aspect_ratio=decrease,"
        "pad=480:270:(ow-iw)/2:(oh-ih)/2"
    )

    if blurred_side_fill:
        crop_values = None
        try:
            left_pct = max(0.0, min(42.0, float(blur_crop_left_pct or 0.0)))
            right_pct = max(0.0, min(42.0, float(blur_crop_right_pct or 0.0)))
            if left_pct + right_pct > 0.01:
                source_w, source_h = get_video_dimensions(input_path)
                if source_w > 0 and source_h > 0:
                    crop_x = int(round(source_w * left_pct / 100.0))
                    crop_right = int(round(source_w * right_pct / 100.0))
                    crop_w = max(2, source_w - crop_x - crop_right)
                    crop_x -= crop_x % 2
                    crop_w -= crop_w % 2
                    crop_values = (crop_w, source_h - (source_h % 2), crop_x, 0)
        except Exception:
            crop_values = None
        if not crop_values:
            crop_values = detect_active_video_crop(input_path)
        crop_filter = ""
        if crop_values:
            crop_w, crop_h, crop_x, crop_y = crop_values
            crop_filter = f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"

        timing_parts = [
            f"trim=start={trim_start:.6f}:end={trim_start + source_duration:.6f}",
            "setpts=PTS-STARTPTS"
        ]
        if abs(playback_rate - 1.0) > 0.001:
            timing_parts.append(f"setpts=PTS/{playback_rate:.6f}")
        timing_filter = ",".join(timing_parts) + ","
        fps_filter = ""
        if target_fps and float(target_fps) > 0:
            target_rate = max(24, min(120, int(round(float(target_fps)))))
            should_interpolate = (
                str(interpolation_mode or "auto").lower() in {"auto", "motion", "minterpolate"}
                and source_fps > 0
                and source_fps + 0.5 < target_rate
            )
            if should_interpolate:
                fps_filter = (
                    f",minterpolate=fps={target_rate}:mi_mode=mci:"
                    "mc_mode=aobmc:me_mode=bidir:vsbmc=1"
                )
            else:
                fps_filter = f",fps={target_rate}"

        blur_crop_offset_pct = max(-30.0, min(30.0, float(blur_crop_offset_pct or 0.0)))
        foreground_x = f"(W-w)/2+(W*{blur_crop_offset_pct:.6f}/100)"

        final_adjustments = []
        if abs(frame_scale - 1.0) > 0.001 or abs(frame_x) > 0.001 or abs(frame_y) > 0.001:
            scaled_w = max(VIDEO_WIDTH, int(round(VIDEO_WIDTH * frame_scale)))
            scaled_h = max(VIDEO_HEIGHT, int(round(VIDEO_HEIGHT * frame_scale)))
            max_x = max(0, scaled_w - VIDEO_WIDTH)
            max_y = max(0, scaled_h - VIDEO_HEIGHT)
            crop_x = max(0, min(max_x, int(round((max_x / 2) - (frame_x / 100.0) * (max_x / 2)))))
            crop_y = max(0, min(max_y, int(round((max_y / 2) - (frame_y / 100.0) * (max_y / 2)))))
            final_adjustments.extend([f"scale={scaled_w}:{scaled_h}", f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT}:{crop_x}:{crop_y}"])
        if fade_in > 0 and duration > fade_in:
            final_adjustments.append(f"fade=t=in:st=0:d={fade_in}")
        if fade_out > 0 and duration > fade_out:
            final_adjustments.append(f"fade=t=out:st={max(0, duration-fade_out)}:d={fade_out}")
        final_suffix = ("," + ",".join(final_adjustments)) if final_adjustments else ""

        filter_parts = [
            # Remove encoded pillarbox pixels before creating either layer.
            # The sharp foreground is fitted without distortion; its duplicate
            # is enlarged with cover behavior and blurred behind it.
            f"[0:v]{timing_filter}{crop_filter}split=2[side_fg_src][side_bg_src]",
            f"[side_bg_src]scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},gblur=sigma=18:steps=2,eq=brightness=-0.015:saturation=0.99[side_bg]",
            f"[side_fg_src]scale=-2:{VIDEO_HEIGHT}[side_fg]",
            f"[side_bg][side_fg]overlay={foreground_x}:(H-h)/2:format=auto{fps_filter}{final_suffix},format=yuv420p[side_base]"
        ]

        output_label = "[side_base]"
        if has_overlay:
            filter_parts.extend([
                "[1:v]scale=145:-1[ov]",
                "[side_base][ov]overlay=35:H-h-35:format=auto,format=yuv420p[side_overlay]"
            ])
            output_label = "[side_overlay]"

        if preview_enabled:
            filter_parts.extend([
                f"{output_label}split=2[v][preview_source]",
                f"[preview_source]{preview_filter}[preview]"
            ])
            output_label = "[v]"

        command.extend(["-filter_complex", ";".join(filter_parts), "-map", output_label])
        # Keep audio mapping optional. Referencing [0:a] inside filter_complex
        # makes the entire render fail when an archival clip has no audio
        # stream, which is common for downloaded highlight footage. Applying
        # audio filters with -af preserves mute/speed/fades when audio exists
        # while 0:a? safely allows silent clips to render.
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend(["-map", "0:a?"])

        filter_threads = max(1, min(16, (os.cpu_count() or 4) - 1))
        command.extend([
            "-filter_threads", str(filter_threads),
            "-filter_complex_threads", str(filter_threads),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "0",
            "-c:a", "aac", "-ar", "44100", "-ac", "2", "-movflags", "+faststart",
            output_path
        ])
        if preview_enabled:
            command.extend([
                "-map", "[preview]", "-an", "-c:v", "mjpeg", "-q:v", "10",
                "-f", "image2", "-update", "1", "-atomic_writing", "1", preview_path
            ])

        def wrapped_progress(fraction):
            if project_id and is_render_cancelled(project_id):
                raise RuntimeError("Render canceled by user.")
            if progress_callback:
                progress_callback(fraction)

        return run_ffmpeg_with_progress(
            command,
            duration_seconds=duration,
            progress_callback=wrapped_progress,
            timeout=7200,
            project_id=project_id
        )

    if has_overlay:
        if preview_enabled:
            filter_parts = [
                f"[0:v]{base_filter},format=rgba[base]",
                "[1:v]scale=145:-1[ov]",
                "[base][ov]overlay=35:H-h-35:format=auto,format=yuv420p,split=2[v][preview_source]",
                f"[preview_source]{preview_filter}[preview]"
            ]
        else:
            filter_parts = [
                f"[0:v]{base_filter},format=rgba[base]",
                "[1:v]scale=145:-1[ov]",
                "[base][ov]overlay=35:H-h-35:format=auto,format=yuv420p[v]"
            ]
        if audio_filters:
            filter_parts.append(f"[0:a]{','.join(audio_filters)}[a]")
        command.extend(["-filter_complex", ";".join(filter_parts), "-map", "[v]"])
        command.extend(["-map", "[a]" if audio_filters else "0:a?"])
    elif preview_enabled:
        filter_parts = [
            f"[0:v]{base_filter},format=yuv420p,split=2[v][preview_source]",
            f"[preview_source]{preview_filter}[preview]"
        ]
        command.extend(["-filter_complex", ";".join(filter_parts), "-map", "[v]"])
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend(["-map", "0:a?"])
    else:
        command.extend(["-vf", f"{base_filter},format=yuv420p", "-map", "0:v"])
        if audio_filters:
            command.extend(["-af", ",".join(audio_filters)])
        command.extend(["-map", "0:a?"])

    filter_threads = max(1, min(16, (os.cpu_count() or 4) - 1))
    command.extend([
        "-filter_threads", str(filter_threads),
        "-filter_complex_threads", str(filter_threads),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-threads", "0",
        "-c:a", "aac",
        "-ar", "44100",
        "-ac", "2",
        "-movflags", "+faststart",
        output_path
    ])

    if preview_enabled:
        command.extend([
            "-map", "[preview]",
            "-an",
            "-c:v", "mjpeg",
            "-q:v", "10",
            "-f", "image2",
            "-update", "1",
            "-atomic_writing", "1",
            preview_path
        ])

    def wrapped_progress(fraction):
        if project_id and is_render_cancelled(project_id):
            raise RuntimeError("Render canceled by user.")
        if progress_callback:
            progress_callback(fraction)

    return run_ffmpeg_with_progress(
        command,
        duration_seconds=duration,
        progress_callback=wrapped_progress,
        timeout=7200,
        project_id=project_id
    )


def create_render_preview_seed(project, preview_path):
    """Create a fast first-frame preview before the background render starts."""
    try:
        clips = sorted(project.get("clips") or [], key=lambda clip: int(clip.get("order") or 999))
        if project.get("project_type") == "top10":
            clips = [clip for clip in clips if clip.get("selected_for_top10", True)]
        if not clips:
            return False

        clip = clips[0]
        input_path = str(clip.get("file_path") or "").replace("/", os.sep)
        if not input_path or not os.path.exists(input_path):
            return False

        trim_start = max(0.0, float(clip.get("trim_start") or 0))
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        temp_preview = f"{preview_path}.seed.tmp.jpg"
        command = [
            FFMPEG_PATH, "-y",
            "-ss", str(trim_start),
            "-i", input_path,
            "-frames:v", "1",
            "-vf",
            "scale=480:270:force_original_aspect_ratio=decrease,"
            "pad=480:270:(ow-iw)/2:(oh-ih)/2",
            "-q:v", "4",
            temp_preview
        ]
        result = run_command(command, timeout=30)
        if result.get("ok") and os.path.exists(temp_preview) and os.path.getsize(temp_preview) > 0:
            os.replace(temp_preview, preview_path)
            return True
        try:
            if os.path.exists(temp_preview):
                os.remove(temp_preview)
        except OSError:
            pass
    except Exception:
        pass
    return False

def make_outro_segment(
    outro_png_path,
    output_path,
    seconds=OUTRO_SECONDS,
    target_fps=60,
    fade_in_seconds=0.3,
    fade_out_seconds=2.0,
    progress_callback=None,
    project_id="",
    preview_path=None
):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    vf = [get_video_scale_filter(target_fps, "none", target_fps or 60)]
    if fade_in_seconds > 0:
        vf.append(f"fade=t=in:st=0:d={fade_in_seconds}")
    if fade_out_seconds > 0:
        vf.append(f"fade=t=out:st={max(0, seconds-fade_out_seconds)}:d={fade_out_seconds}")
    vf.append("format=yuv420p")

    af = []
    if fade_in_seconds > 0:
        af.append(f"afade=t=in:st=0:d={fade_in_seconds}")
    if fade_out_seconds > 0:
        af.append(f"afade=t=out:st={max(0, seconds-fade_out_seconds)}:d={fade_out_seconds}")

    preview_enabled = bool(preview_path)
    if preview_enabled:
        os.makedirs(os.path.dirname(preview_path), exist_ok=True)
        preview_filter = (
            "scale=480:270:force_original_aspect_ratio=decrease,"
            "pad=480:270:(ow-iw)/2:(oh-ih)/2"
        )
        filter_complex = (
            f"[0:v]{','.join(vf)},split=2[v][preview_source];"
            f"[preview_source]{preview_filter}[preview]"
        )
        command = [
            FFMPEG_PATH, "-y",
            "-loop", "1", "-i", outro_png_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(seconds),
            "-filter_complex", filter_complex,
            "-map", "[v]",
            "-map", "1:a"
        ]
    else:
        command = [
            FFMPEG_PATH, "-y",
            "-loop", "1", "-i", outro_png_path,
            "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t", str(seconds),
            "-vf", ",".join(vf),
        ]
    if af:
        command.extend(["-af", ",".join(af)])
    filter_threads = max(1, min(16, (os.cpu_count() or 4) - 1))
    command.extend([
        "-filter_threads", str(filter_threads),
        "-filter_complex_threads", str(filter_threads),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-threads", "0",
        "-c:a", "aac",
        "-shortest",
        "-movflags", "+faststart",
        output_path
    ])
    if preview_enabled:
        command.extend([
            "-map", "[preview]",
            "-t", str(seconds),
            "-an",
            "-c:v", "mjpeg",
            "-q:v", "10",
            "-f", "image2",
            "-update", "1",
            "-atomic_writing", "1",
            preview_path
        ])

    def wrapped_progress(fraction):
        if project_id and is_render_cancelled(project_id):
            raise RuntimeError("Render canceled by user.")
        if progress_callback:
            progress_callback(fraction)

    return run_ffmpeg_with_progress(
        command,
        duration_seconds=seconds,
        progress_callback=wrapped_progress,
        timeout=1800,
        project_id=project_id
    )

def concat_segments(segment_paths, concat_list_path, output_path, progress_callback=None, project_id=""):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(concat_list_path, "w", encoding="utf-8") as f:
        for path in segment_paths:
            normalized = os.path.abspath(path).replace("\\", "/")
            f.write(f"file '{normalized}'\n")

    total_duration = sum(max(0.0, get_video_duration_seconds(path)) for path in segment_paths)
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

    return run_ffmpeg_with_progress(
        command,
        duration_seconds=max(0.1, total_duration),
        progress_callback=progress_callback,
        timeout=900,
        project_id=project_id
    )


def get_music_files(music_dir):
    if not os.path.exists(music_dir):
        return []

    allowed = [".mp3", ".wav", ".m4a"]

    return [
        os.path.join(music_dir, name)
        for name in os.listdir(music_dir)
        if os.path.splitext(name)[1].lower() in allowed
    ]


def add_background_music(video_path, music_dir, output_path, volume=0.13, progress_callback=None, project_id=""):
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

    result = run_ffmpeg_with_progress(
        command,
        duration_seconds=max(0.1, get_video_duration_seconds(video_path)),
        progress_callback=progress_callback,
        timeout=900,
        project_id=project_id
    )
    result["music_used"] = os.path.basename(selected_music)
    return result


def _safe_filename(value):
    clean = "".join(char for char in str(value or "clip") if char.isalnum() or char in (" ", "-", "_")).strip()
    return "_".join(clean.split())[:80] or "clip"


def _selected_top10_clips(project):
    clips = sorted(project.get("clips", []), key=lambda clip: int(clip.get("order") or 999))
    selected = [clip for clip in clips if clip.get("selected_for_top10", True)]
    return selected[:10]


def render_content_studio_project(project, templates_dir, rendered_dir, progress_callback=None, preview_path=None):
    if not ffmpeg_exists():
        return {
            "ok": False,
            "message": "FFmpeg is not available.",
            "error": get_ffmpeg_status(),
            "output_path": None
        }

    project_id = project.get("project_id")
    project_type = project.get("project_type", "solo")
    render_settings = project.get("render_settings") or {}
    requested_fps = int(render_settings.get("output_fps") or 0)
    first_source_path = str((project.get("clips") or [{}])[0].get("file_path") or "").replace("/", os.sep)
    detected_original_fps = get_video_fps(first_source_path) or 30
    target_fps = detected_original_fps if requested_fps <= 0 else max(24, min(120, requested_fps))
    interpolation_mode = str(render_settings.get("interpolation_mode") or "auto")
    # Interpolation only makes sense when increasing above the actual source rate.
    # Original-rate renders and equal/lower target rates use standard frame conversion.
    if float(target_fps) <= float(detected_original_fps) + 0.5:
        interpolation_mode = "none"

    def report(percent, stage):
        if progress_callback:
            try:
                progress_callback(int(max(0, min(100, percent))), str(stage))
            except Exception:
                pass

    clear_render_cancel(project_id)
    report(2, "Preparing project")
    project_render_dir = os.path.join(rendered_dir, project_id)
    os.makedirs(project_render_dir, exist_ok=True)

    intro_file = resolve_branding_asset("intro.mp4", templates_dir)
    outro_file = resolve_branding_asset("outro.png", templates_dir)
    music_dir = os.path.join(templates_dir, "music")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Keep high-write intermediate media out of the OneDrive-backed project
    # folder. Only the completed MP4 is copied into CourtVision storage.
    temp_dir = os.path.join(tempfile.gettempdir(), "CourtVision", "render-temp", str(project_id), timestamp)
    shutil.rmtree(temp_dir, ignore_errors=True)
    os.makedirs(temp_dir, exist_ok=True)
    base_output = os.path.join(temp_dir, f"{project_id}_{timestamp}_base.mp4")
    final_output = os.path.join(temp_dir, f"{project_id}_{timestamp}_final.mp4")
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
    total_work_units = max(1, len(timeline_clips) + 3)
    completed_work_units = 0

    # Intro is optional. If it exists, use it. If not, top 10 starts with #10 immediately.
    if project_type == "top10" and intro_file:
        intro_segment = os.path.join(temp_dir, "000_intro.mp4")
        intro_duration = max(0.1, get_video_duration_seconds(intro_file))
        intro_result = normalize_clip_segment(
            intro_file,
            intro_segment,
            0,
            0,
            fade_seconds=0,
            fade_in_seconds=0,
            fade_out_seconds=0.3,
            target_fps=target_fps,
            interpolation_mode=interpolation_mode,
            progress_callback=lambda fraction: report(
                4 + (fraction * 8),
                "Rendering intro"
            ),
            project_id=project_id,
            preview_path=preview_path,
            playback_rate=clip.get("playback_rate", 1.0),
            muted=bool(clip.get("muted", False))
        )
        logs.append(intro_result)

        if intro_result.get("ok"):
            segments.append(intro_segment)
            completed_work_units += 1
            report(5 + (completed_work_units / total_work_units) * 75, "Rendered intro")

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
        clip_progress_start = 8 + ((index - 1) / max(1, len(timeline_clips))) * 68
        clip_progress_span = 68 / max(1, len(timeline_clips))
        interpolation_label = (
            "Interpolating Clip"
            if interpolation_mode != "none"
            else "Rendering Clip"
        )

        if project_type == "top10":
            clip_fade_in = 0.3 if index == 1 else 0.1
            clip_fade_out = 0.3 if index == len(timeline_clips) else 0.1
        else:
            # Solo projects may contain multiple clips. Keep intermediate clips
            # perfectly back-to-back and fade only the final clip into the outro.
            clip_fade_in = 0.0
            clip_fade_out = 0.3 if index == len(timeline_clips) else 0.0

        result = normalize_clip_segment(
            input_path,
            segment_path,
            clip.get("trim_start", 0),
            clip.get("trim_end", 0),
            overlay_png_path=overlay_path,
            fade_seconds=0,
            fade_in_seconds=clip_fade_in,
            fade_out_seconds=clip_fade_out,
            target_fps=target_fps,
            interpolation_mode=interpolation_mode,
            progress_callback=lambda fraction, start=clip_progress_start, span=clip_progress_span, label=interpolation_label: report(
                start + (fraction * span),
                label
            ),
project_id=project_id,
            frame_scale=clip.get("frame_scale", 1.0),
            frame_x=clip.get("frame_x", 0.0),
            frame_y=clip.get("frame_y", 0.0),
            preview_path=preview_path,
            playback_rate=clip.get("playback_rate", 1.0),
            muted=bool(clip.get("muted", False)),
            blurred_side_fill=bool(clip.get("blurred_side_fill", False)),
            blur_crop_left_pct=clip.get("blur_crop_left_pct", 0.0),
            blur_crop_right_pct=clip.get("blur_crop_right_pct", 0.0),
            blur_crop_offset_pct=clip.get("blur_crop_offset_pct", 0.0)
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
        completed_work_units += 1
        report(
            5 + (completed_work_units / total_work_units) * 75,
            f"Rendered clip {index} of {len(timeline_clips)}"
        )

    outro_segment = os.path.join(temp_dir, "999_outro.mp4")
    outro_result = make_outro_segment(
        outro_file,
        outro_segment,
        seconds=OUTRO_SECONDS,
        target_fps=target_fps,
        # The final real clip owns the 0.3-second transition. Start the
        # static outro immediately after that clip ends so it can never appear
        # early or add a second overlapping fade.
        fade_in_seconds=0.0,
        fade_out_seconds=2.0,
        progress_callback=lambda fraction: report(
            77 + (fraction * 8),
            "Rendering static outro"
        ),
        project_id=project_id,
        # The outro is part of the final edited timeline, so publish its
        # actual rendered frames to the same live preview stream.
        preview_path=preview_path
    )
    logs.append(outro_result)

    if not outro_result.get("ok"):
        return {
            "ok": False,
            "message": "Outro render failed.",
            "error": outro_result,
            "output_path": None
        }

    segments.append(outro_segment)
    completed_work_units += 1
    report(85, "Static outro ready")

    report(86, "Joining video and audio")
    concat_result = concat_segments(
        segments,
        concat_list,
        base_output,
        progress_callback=lambda fraction: report(86 + (fraction * 6), "Joining video and audio"),
        project_id=project_id
    )
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

    report(93, "Finalizing MP4")

    if project_type == "top10":
        music_result = add_background_music(
            base_output,
            music_dir,
            final_output,
            progress_callback=lambda fraction: report(93 + (fraction * 6), "Mixing final audio"),
            project_id=project_id
        )
        logs.append(music_result)
        music_used = music_result.get("music_used")

        if music_result.get("ok") and os.path.exists(final_output):
            output_path = final_output

    report(99, "Saving final video")
    duration = get_video_duration_seconds(output_path)
    stored_output = os.path.join(project_render_dir, f"{project_id}_{timestamp}_final.mp4")
    shutil.copy2(output_path, stored_output)
    output_path = stored_output
    shutil.rmtree(temp_dir, ignore_errors=True)
    report(100, "Render complete")

    return {
        "ok": True,
        "message": "Project rendered successfully.",
        "output_path": output_path,
        "duration_seconds": duration,
        "music_used": music_used,
        "project_type": project_type,
        "output_fps": round(float(target_fps), 3),
        "original_fps": round(float(detected_original_fps), 3),
        "interpolation_mode": "original" if requested_fps <= 0 else interpolation_mode,
        "logs": logs[-8:]
    }


def render_content_studio_solos(project, templates_dir, rendered_dir, progress_callback=None):
    if not ffmpeg_exists():
        return {
            "ok": False,
            "message": "FFmpeg is not available.",
            "error": get_ffmpeg_status(),
            "exports": []
        }

    project_id = project.get("project_id")
    render_settings = project.get("render_settings") or {}
    requested_fps = int(render_settings.get("output_fps") or 0)
    first_source_path = str((project.get("clips") or [{}])[0].get("file_path") or "").replace("/", os.sep)
    detected_original_fps = get_video_fps(first_source_path) or 30
    target_fps = detected_original_fps if requested_fps <= 0 else max(24, min(120, requested_fps))
    interpolation_mode = str(render_settings.get("interpolation_mode") or "auto")
    if float(target_fps) <= float(detected_original_fps) + 0.5:
        interpolation_mode = "none"

    def report(percent, stage):
        if progress_callback:
            try:
                progress_callback(int(max(0, min(100, percent))), str(stage))
            except Exception:
                pass

    report(2, "Preparing solo exports")
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
