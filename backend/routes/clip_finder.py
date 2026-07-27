import json
import os
import re
import shutil
import subprocess
import sys
import uuid
import threading
import time
import html
import math
import random
import ctypes
from contextlib import contextmanager
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

import requests
from io import BytesIO
from PIL import Image, ImageFilter, ImageStat

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from services.youtube_service import get_youtube_service, _execute_with_retry
from services.ffmpeg_service import get_video_duration_seconds, get_video_fps
from routes.content_studio import (
    CLIPS_DIR,
    generate_metadata,
    get_template_status,
    save_project,
)

router = APIRouter(prefix="/clip-finder", tags=["Clip Finder"])

CLIP_FINDER_BUILD = "2026.07.27-durable-download-pipeline-v7.7"

_SEARCH_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="clip-finder-search")
_SEARCH_JOBS: dict[str, dict[str, Any]] = {}
_SEARCH_JOBS_LOCK = threading.Lock()

# Windows power-management flags used only while a Clip Finder search worker is
# active. SetThreadExecutionState is scoped to the calling worker thread, so
# the matching ES_CONTINUOUS release in the worker's finally block restores the
# user's normal Windows sleep settings as soon as that search ends.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_DISPLAY_REQUIRED = 0x00000002


def _set_windows_search_awake(active: bool) -> bool:
    """Prevent Windows system/display sleep for the current search thread."""
    if os.name != "nt":
        return False
    try:
        flags = (
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_DISPLAY_REQUIRED
            if active
            else _ES_CONTINUOUS
        )
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
        return bool(result)
    except Exception:
        # Search accuracy must never depend on power-management support.
        return False


@contextmanager
def _keep_computer_awake_during_search():
    """Keep the PC and display awake, then always restore normal behavior."""
    enabled = _set_windows_search_awake(True)
    try:
        yield enabled
    finally:
        if enabled:
            _set_windows_search_awake(False)

def _set_search_job(project_id: str, **updates):
    with _SEARCH_JOBS_LOCK:
        job = _SEARCH_JOBS.setdefault(project_id, {"status": "idle", "error": "", "started_at": None, "finished_at": None})
        job.update(updates)
        return dict(job)

def _get_search_job(project_id: str):
    with _SEARCH_JOBS_LOCK:
        return dict(_SEARCH_JOBS.get(project_id, {"status": "idle", "error": "", "started_at": None, "finished_at": None}))


@contextmanager
def _search_progress_heartbeat(project_id: str, *, interval_seconds: float = 8.0):
    """Keep frontend liveness detection updated during long blocking stages."""
    stop_event = threading.Event()

    def beat():
        serial = 0
        while not stop_event.wait(interval_seconds):
            job = _get_search_job(project_id)
            if job.get("status") != "running":
                return
            progress = dict(job.get("progress") or {})
            serial += 1
            progress["heartbeat_serial"] = int(progress.get("heartbeat_serial") or 0) + 1
            progress["heartbeat_at"] = now_iso()
            progress["elapsed_seconds"] = max(
                int(progress.get("elapsed_seconds") or 0),
                int(time.monotonic() - heartbeat_started),
            )
            _set_search_job(project_id, progress=progress)

    heartbeat_started = time.monotonic()
    thread = threading.Thread(target=beat, name=f"clip-finder-heartbeat-{project_id[:8]}", daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop_event.set()
        thread.join(timeout=1.0)

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data" / "clip_finder"
PROJECTS_DIR = DATA_DIR / "projects"
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)

# Permanent browser-download inbox. Configure the browser extension to save
# CourtVision source videos here. This is the project-root data folder requested
# by the user, not the normal Windows Downloads folder.
DOWNLOAD_INBOX_DIR = BASE_DIR.parent / "data" / "clip_finder" / "inbox"
DOWNLOAD_INBOX_DIR.mkdir(parents=True, exist_ok=True)
# v7 uses a fresh state filename so a stale OneDrive/Windows lock on the old
# pending_download.json can never block the next source download.
LEGACY_PENDING_DOWNLOAD_FILE = DATA_DIR / "pending_download.json"
PENDING_DOWNLOAD_FILE = DATA_DIR / "pending_download_v7.json"
_DOWNLOAD_VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
_DOWNLOAD_PARTIAL_EXTENSIONS = {".crdownload", ".part", ".tmp", ".download"}
_DOWNLOAD_WATCHER_LOCK = threading.Lock()
_DOWNLOAD_WATCHER_STARTED = False
_DOWNLOAD_PROCESS_LOCK = threading.Lock()
_DOWNLOAD_WATCHER_LAST_ERROR = ""
_DOWNLOAD_WATCHER_LAST_SCAN_AT = None
_DOWNLOAD_STABILITY: dict[str, dict[str, Any]] = {}
_PENDING_DOWNLOAD_STATE_LOCK = threading.RLock()
_PENDING_DOWNLOAD_CACHE: Optional[dict[str, Any]] = None
_RESET_ATTACHMENT_KEYS: set[tuple[str, str]] = set()
_RESET_ATTACHMENT_KEYS_LOCK = threading.RLock()


def _clone_json_dict(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return a detached JSON-safe copy so polling cannot mutate shared state."""
    if payload is None:
        return None
    return json.loads(json.dumps(payload))


def _read_pending_download() -> Optional[dict[str, Any]]:
    """Return live pending state, recovering it from the saved project if needed."""
    global _PENDING_DOWNLOAD_CACHE
    with _PENDING_DOWNLOAD_STATE_LOCK:
        cached = _clone_json_dict(_PENDING_DOWNLOAD_CACHE)
    if cached is not None:
        return cached

    recovered = _recover_pending_download()
    if recovered is not None:
        with _PENDING_DOWNLOAD_STATE_LOCK:
            _PENDING_DOWNLOAD_CACHE = _clone_json_dict(recovered)
    return recovered


def _write_pending_download(payload: dict[str, Any], *, persist: bool = False) -> dict[str, Any]:
    """Update live state and optionally persist a meaningful transition."""
    global _PENDING_DOWNLOAD_CACHE
    detached = _clone_json_dict(payload) or {}
    with _PENDING_DOWNLOAD_STATE_LOCK:
        _PENDING_DOWNLOAD_CACHE = detached
    if persist:
        _persist_pending_download(detached)
    return _clone_json_dict(detached) or {}


def _clear_pending_download() -> None:
    """Clear transient state and best-effort remove obsolete lock-prone files."""
    global _PENDING_DOWNLOAD_CACHE
    with _PENDING_DOWNLOAD_STATE_LOCK:
        _PENDING_DOWNLOAD_CACHE = None

    # Old builds wrote these files inside OneDrive. They are no longer used.
    # Cleanup is best effort only and can never affect attachment success.
    stale_paths = [
        PENDING_DOWNLOAD_FILE,
        PENDING_DOWNLOAD_FILE.with_suffix(".tmp"),
        LEGACY_PENDING_DOWNLOAD_FILE,
        LEGACY_PENDING_DOWNLOAD_FILE.with_suffix(".tmp"),
    ]
    for path in stale_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    try:
        for pattern in (".pending_download*.tmp", "pending_download*.tmp"):
            for path in DATA_DIR.glob(pattern):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
    except OSError:
        pass

def _pending_from_result(project: dict[str, Any], result: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Rebuild an active download job from durable project fields.

    The browser-download workflow must survive backend restarts. The live cache
    makes polling fast, while these fields inside the project JSON are the
    durable source of truth.
    """
    pending_id = str(result.get("attachment_session_id") or "").strip()
    if not pending_id or result.get("local_file_path"):
        return None
    status = str(result.get("download_status") or "waiting")
    if status not in {"waiting", "detected", "attaching", "failed", "cancelled"}:
        status = "waiting"
    return {
        "pending_id": pending_id,
        "project_id": str(project.get("project_id") or ""),
        "result_id": str(result.get("result_id") or ""),
        "video_id": result.get("video_id"),
        "title": result.get("title"),
        "youtube_url": result.get("youtube_url"),
        "status": status,
        "message": result.get("download_message") or "Waiting for the MP4 download to finish…",
        "inbox_path": str(DOWNLOAD_INBOX_DIR),
        "baseline": result.get("download_baseline") if isinstance(result.get("download_baseline"), dict) else {},
        "started_at": result.get("download_started_at") or now_iso(),
        "started_epoch": float(result.get("download_started_epoch") or 0),
        "updated_at": result.get("download_updated_at") or now_iso(),
        "error": result.get("download_error") or "",
    }


def _recover_pending_download() -> Optional[dict[str, Any]]:
    """Recover the newest active download session from saved Clip Finder projects."""
    newest: tuple[float, dict[str, Any]] | None = None
    try:
        project_paths = list(PROJECTS_DIR.glob("*.json"))
    except OSError:
        return None

    for path in project_paths:
        try:
            project = normalize_project(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        for result in project.get("results", []):
            pending = _pending_from_result(project, result)
            if not pending or pending.get("status") in {"cancelled"}:
                continue
            started = float(pending.get("started_epoch") or 0)
            if newest is None or started > newest[0]:
                newest = (started, pending)
    return _clone_json_dict(newest[1]) if newest else None


def _persist_pending_download(payload: Optional[dict[str, Any]]) -> None:
    """Persist meaningful state changes on the exact source result.

    This avoids the old shared pending_download.json file entirely while still
    allowing the workflow to recover after a backend restart.
    """
    if not payload:
        return
    project_id = str(payload.get("project_id") or "")
    result_id = str(payload.get("result_id") or "")
    if not project_id or not result_id:
        return
    try:
        project = load_project(project_id)
    except Exception:
        return
    result = next((row for row in project.get("results", []) if str(row.get("result_id") or "") == result_id), None)
    if result is None:
        return

    result["attachment_session_id"] = str(payload.get("pending_id") or result.get("attachment_session_id") or "")
    result["download_status"] = str(payload.get("status") or "waiting")
    result["download_message"] = str(payload.get("message") or "")
    result["download_error"] = str(payload.get("error") or "")
    result["download_started_at"] = payload.get("started_at") or result.get("download_started_at") or now_iso()
    result["download_started_epoch"] = float(payload.get("started_epoch") or result.get("download_started_epoch") or 0)
    result["download_updated_at"] = payload.get("updated_at") or now_iso()
    if isinstance(payload.get("baseline"), dict):
        result["download_baseline"] = payload["baseline"]
    save_cf_project(project)


def _clear_result_download_state(result: dict[str, Any], *, clear_session: bool = True) -> None:
    for key in (
        "download_status",
        "download_message",
        "download_error",
        "download_started_at",
        "download_started_epoch",
        "download_updated_at",
        "download_baseline",
    ):
        result.pop(key, None)
    if clear_session:
        result.pop("attachment_session_id", None)

def _download_inbox_snapshot() -> dict[str, dict[str, float]]:
    snapshot: dict[str, dict[str, float]] = {}
    DOWNLOAD_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for path in DOWNLOAD_INBOX_DIR.iterdir():
            if not path.is_file():
                continue
            try:
                stat = path.stat()
                snapshot[path.name] = {
                    "size": float(stat.st_size),
                    "mtime": float(stat.st_mtime),
                }
            except OSError:
                continue
    except OSError:
        pass
    return snapshot


def _safe_source_filename(result: dict[str, Any], extension: str) -> str:
    title = re.sub(r"[^A-Za-z0-9._ -]+", "", str(result.get("title") or "")).strip()
    title = re.sub(r"\s+", " ", title)[:120].rstrip(" .")
    video_id = re.sub(r"[^A-Za-z0-9_-]+", "", str(result.get("video_id") or ""))[:32]
    base = title or video_id or "source-video"
    if video_id and video_id.lower() not in base.lower():
        base = f"{base} [{video_id}]"
    return f"{base}{extension.lower()}"


def _candidate_download_files(pending: dict[str, Any]) -> list[Path]:
    baseline = pending.get("baseline") if isinstance(pending.get("baseline"), dict) else {}
    started_epoch = float(pending.get("started_epoch") or 0)
    candidates: list[Path] = []
    DOWNLOAD_INBOX_DIR.mkdir(parents=True, exist_ok=True)

    try:
        paths = list(DOWNLOAD_INBOX_DIR.iterdir())
    except OSError:
        return []

    for path in paths:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix in _DOWNLOAD_PARTIAL_EXTENSIONS or suffix not in _DOWNLOAD_VIDEO_EXTENSIONS:
            continue

        try:
            stat = path.stat()
        except OSError:
            continue

        old = baseline.get(path.name)
        changed_since_begin = (
            old is None
            or int(float(old.get("size") or -1)) != int(stat.st_size)
            or abs(float(old.get("mtime") or -1) - float(stat.st_mtime)) > 0.001
        )
        new_enough = float(stat.st_mtime) >= max(0.0, started_epoch - 2.0)
        if changed_since_begin and new_enough and stat.st_size > 0:
            candidates.append(path)

    candidates.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0)
    return candidates


def _matching_partial_exists(source: Path) -> bool:
    try:
        source_name = source.name.lower()
        source_stem = source.stem.lower()
        for path in DOWNLOAD_INBOX_DIR.iterdir():
            if not path.is_file() or path == source:
                continue
            if path.suffix.lower() not in _DOWNLOAD_PARTIAL_EXTENSIONS:
                continue
            partial_name = path.name.lower()
            partial_stem = path.stem.lower()
            if (
                partial_name.startswith(source_name)
                or partial_name.startswith(source_stem)
                or source_name.startswith(partial_stem)
                or source_stem.startswith(partial_stem)
            ):
                return True
    except OSError:
        return True
    return False


def _file_is_stable(source: Path) -> bool:
    try:
        stat = source.stat()
        with source.open("rb") as handle:
            handle.read(1)
    except (OSError, PermissionError):
        return False

    if stat.st_size <= 0 or _matching_partial_exists(source):
        _DOWNLOAD_STABILITY.pop(str(source), None)
        return False

    key = str(source.resolve())
    previous = _DOWNLOAD_STABILITY.get(key)
    same = bool(
        previous
        and previous.get("size") == stat.st_size
        and previous.get("mtime_ns") == stat.st_mtime_ns
    )
    scans = int(previous.get("stable_scans") or 0) + 1 if same else 1
    _DOWNLOAD_STABILITY[key] = {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "stable_scans": scans,
    }
    return scans >= 3


def _move_download_to_managed_storage(source: Path, destination: Path) -> None:
    """Move a completed browser download into CourtVision storage reliably."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    last_error: Optional[Exception] = None
    for attempt in range(8):
        try:
            shutil.move(str(source), str(destination))
            if destination.exists() and destination.is_file() and destination.stat().st_size > 0:
                return
        except (PermissionError, OSError) as exc:
            last_error = exc
        time.sleep(0.25 * (attempt + 1))

    # Cross-device moves, OneDrive, antivirus, and browser file handles can make
    # rename/move unreliable. Copy-verify-delete is the durable fallback.
    try:
        shutil.copy2(str(source), str(destination))
        if not destination.exists() or destination.stat().st_size <= 0:
            raise OSError("The copied MP4 could not be verified.")
        try:
            source.unlink()
        except OSError:
            pass
        return
    except Exception as exc:
        last_error = exc

    raise RuntimeError(f"Could not move the completed MP4 into CourtVision storage: {last_error}")


def _attach_completed_inbox_file(pending: dict[str, Any], source: Path) -> dict[str, Any]:
    project_id = str(pending.get("project_id") or "")
    result_id = str(pending.get("result_id") or "")
    attachment_key = (project_id, result_id)
    with _RESET_ATTACHMENT_KEYS_LOCK:
        reset_requested = attachment_key in _RESET_ATTACHMENT_KEYS
    if reset_requested:
        # A delete/reset won the race while this browser download was finishing.
        # Remove the orphaned inbox file and never reconnect it to the source.
        try:
            if source.exists() and source.is_file():
                source.unlink()
        except OSError:
            pass
        _clear_pending_download()
        raise RuntimeError("Attachment was reset before the download finished.")
    project = load_project(project_id)
    result = next(
        (row for row in project.get("results", []) if row.get("result_id") == result_id),
        None,
    )
    if result is None:
        raise RuntimeError("The approved CourtVision source no longer exists.")
    if result.get("status") != "approved":
        raise RuntimeError("The source is no longer approved.")
    if str(result.get("attachment_session_id") or "") != str(pending.get("pending_id") or ""):
        # The source was reset or a newer download session replaced this one.
        # Never let an older watcher pass restore an attachment after deletion.
        try:
            if source.exists() and source.is_file():
                source.unlink()
        except OSError:
            pass
        _clear_pending_download()
        raise RuntimeError("This download session is no longer active.")

    destination_folder = DATA_DIR / "attached" / project_id
    destination_folder.mkdir(parents=True, exist_ok=True)
    destination = destination_folder / _safe_source_filename(result, source.suffix)
    if destination.exists():
        destination = destination_folder / (
            f"{destination.stem}-{uuid.uuid4().hex[:6]}{destination.suffix}"
        )

    _move_download_to_managed_storage(source, destination)
    attached_path = str(destination.resolve()).replace("\\", "/")
    result["local_file_path"] = attached_path
    result["attached_file_path"] = attached_path
    result["attached_filename"] = destination.name
    result["download_attached_at"] = now_iso()
    result["attachment_status"] = "complete"
    result.pop("attachment_reset_at", None)
    _clear_result_download_state(result, clear_session=True)
    save_cf_project(project)

    pending.update({
        "status": "attached",
        "message": "MP4 attached successfully. This source is complete and ready.",
        "attached_file_path": attached_path,
        "attached_filename": destination.name,
        "completed_at": now_iso(),
        "updated_at": now_iso(),
        "error": "",
    })
    _write_pending_download(pending)
    _DOWNLOAD_STABILITY.pop(str(source.resolve()), None)
    return project


def _process_download_inbox_once() -> Optional[dict[str, Any]]:
    global _DOWNLOAD_WATCHER_LAST_ERROR, _DOWNLOAD_WATCHER_LAST_SCAN_AT

    if not _DOWNLOAD_PROCESS_LOCK.acquire(blocking=False):
        return _read_pending_download()

    try:
        _DOWNLOAD_WATCHER_LAST_SCAN_AT = now_iso()
        pending = _read_pending_download()
        if not pending or pending.get("status") not in {"waiting", "detected", "attaching"}:
            return pending

        candidates = _candidate_download_files(pending)
        if not candidates:
            pending.update({
                "status": "waiting",
                "message": "Waiting for the completed MP4 in the CourtVision Inbox…",
                "updated_at": now_iso(),
            })
            _write_pending_download(pending)
            return pending

        source = candidates[-1]
        pending.update({
            "status": "detected",
            "message": f"MP4 detected: {source.name}. Waiting for the download to finish…",
            "detected_filename": source.name,
            "updated_at": now_iso(),
        })
        _write_pending_download(pending, persist=True)

        if not _file_is_stable(source):
            return pending

        pending.update({
            "status": "attaching",
            "message": "Download complete. Linking the MP4 to this YouTube source…",
            "updated_at": now_iso(),
        })
        _write_pending_download(pending, persist=True)

        _attach_completed_inbox_file(pending, source)
        _DOWNLOAD_WATCHER_LAST_ERROR = ""
        return _read_pending_download()

    except Exception as exc:
        _DOWNLOAD_WATCHER_LAST_ERROR = str(exc)
        pending = _read_pending_download()
        if pending:
            pending.update({
                "status": "failed",
                "message": "CourtVision detected the file but could not attach it.",
                "error": str(exc),
                "updated_at": now_iso(),
            })
            _write_pending_download(pending, persist=True)
        return pending
    finally:
        _DOWNLOAD_PROCESS_LOCK.release()


def _download_inbox_watcher_loop() -> None:
    global _DOWNLOAD_WATCHER_LAST_ERROR
    while True:
        try:
            _process_download_inbox_once()
        except Exception as exc:
            _DOWNLOAD_WATCHER_LAST_ERROR = str(exc)
        time.sleep(1.0)


def _ensure_download_watcher_started() -> None:
    global _DOWNLOAD_WATCHER_STARTED
    DOWNLOAD_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    with _DOWNLOAD_WATCHER_LOCK:
        if _DOWNLOAD_WATCHER_STARTED:
            return
        thread = threading.Thread(
            target=_download_inbox_watcher_loop,
            name="clip-download-inbox-watcher",
            daemon=True,
        )
        thread.start()
        _DOWNLOAD_WATCHER_STARTED = True




TOP10_CATEGORIES = [
    "Top 10 Plays", "Top 10 Dunks", "Top 10 Blocks", "Top 10 Game Winners",
    "Top 10 Clutch Shots", "Top 10 Assists", "Top 10 Crossovers",
    "Top 10 Layups", "Top 10 Posters", "Top 10 Steals", "Top 10 Buzzer Beaters",
    "Top 10 Alley-Oops", "Top 10 Handles", "Top 10 Defensive Plays",
]

CATEGORY_TERMS = {
    "Top 10 Plays": [
        "best plays", "greatest plays", "top plays", "career highlights", "best moments",
        "greatest moments", "iconic plays", "incredible plays", "unbelievable plays",
        "highlight reel", "highlights", "mixtape",
    ],
    "Top 10 Dunks": [
        "dunk", "dunks", "poster", "poster dunk", "posterizes", "slam", "slams",
        "facial", "hammer", "tomahawk", "windmill", "reverse dunk", "baseline dunk",
        "putback dunk", "tip dunk", "tip slam", "alley oop", "alley-oop", "lob dunk",
        "one handed dunk", "two handed dunk", "fast break dunk", "transition dunk",
        "monster dunk", "power dunk", "in game dunk", "nastiest dunks", "craziest dunks",
    ],
    "Top 10 Blocks": [
        "block", "blocks", "rejection", "rejections", "chase down block",
        "chasedown block", "swat", "swats", "rim protection", "defensive block",
    ],
    "Top 10 Game Winners": [
        "game winner", "game winners", "game winning shot", "game-winning shot",
        "go ahead shot", "go-ahead shot", "last second shot", "last-second shot",
        "walk off shot", "clutch winner", "wins the game",
    ],
    "Top 10 Clutch Shots": [
        "clutch shot", "clutch shots", "clutch plays", "late game", "late-game",
        "fourth quarter", "4th quarter", "overtime", "ot", "go ahead basket",
        "game tying shot", "game-tying shot", "dagger", "clutch bucket",
    ],
    "Top 10 Assists": [
        "assist", "assists", "pass", "passes", "passing highlights", "playmaking",
        "no look pass", "no-look pass", "behind the back pass", "alley oop assist",
        "lob assist", "dime", "dimes", "court vision",
    ],
    "Top 10 Crossovers": [
        "crossover", "crossovers", "ankle breaker", "ankle breakers", "breaks ankles",
        "hesitation", "stepback crossover", "killer crossover", "dribble move",
    ],
    "Top 10 Layups": [
        "layup", "layups", "acrobatic finish", "circus layup", "reverse layup",
        "finger roll", "scoop layup", "up and under", "english off glass", "tough finish",
    ],
    "Top 10 Posters": [
        "poster", "poster dunk", "posterizes", "dunk on", "dunks on", "dunk over",
        "dunks over", "facial", "puts on a poster", "slams on",
    ],
    "Top 10 Steals": [
        "steal", "steals", "pick pocket", "pickpocket", "interception",
        "strips", "stripped", "defensive highlights", "takeaway",
    ],
    "Top 10 Buzzer Beaters": [
        "buzzer beater", "buzzer beaters", "at the buzzer", "beats the buzzer",
        "last second", "last-second", "game winner", "walk off",
    ],
    "Top 10 Alley-Oops": [
        "alley oop", "alley-oop", "alley oops", "lob dunk", "lob dunks",
        "oop", "throws it down", "catches the lob", "finishes the lob",
    ],
    "Top 10 Handles": [
        "handles", "handle", "dribble moves", "ball handling", "ankle breaker",
        "ankle breakers", "crossovers", "hesitation", "combo moves", "iso moves",
    ],
    "Top 10 Defensive Plays": [
        "defensive plays", "defense highlights", "best defense", "blocks and steals",
        "block", "steal", "charge", "lockdown defense", "defensive stop",
    ],
}

# Lower-priority aliases broaden discovery without replacing the player's real name.
PLAYER_NICKNAMES = {
    "vince carter": ["Vinsanity", "Air Canada", "Half Man Half Amazing"],
    "michael jordan": ["Air Jordan", "His Airness", "MJ"],
    "lebron james": ["King James", "The King", "LBJ"],
    "kobe bryant": ["Black Mamba", "Mamba"],
    "shaquille oneal": ["Shaq", "The Big Aristotle", "Diesel"],
    "shaquille o neal": ["Shaq", "The Big Aristotle", "Diesel"],
    "allen iverson": ["The Answer", "AI"],
    "kevin durant": ["KD", "Slim Reaper"],
    "stephen curry": ["Steph Curry", "Chef Curry", "Chef Steph"],
    "giannis antetokounmpo": ["Greek Freak", "Giannis"],
    "nikola jokic": ["The Joker", "Joker"],
    "luka doncic": ["Luka Magic", "Wonder Boy"],
    "damian lillard": ["Dame", "Dame Time"],
    "paul pierce": ["The Truth"],
    "tracy mcgrady": ["T Mac", "T-Mac"],
    "dwyane wade": ["D Wade", "Flash"],
    "carmelo anthony": ["Melo"],
    "kyrie irving": ["Uncle Drew"],
    "russell westbrook": ["Russ", "Brodie"],
    "james harden": ["The Beard"],
    "chris paul": ["CP3", "Point God"],
    "anthony davis": ["AD", "The Brow"],
    "kawhi leonard": ["The Klaw", "Klaw"],
    "paul george": ["PG13", "Playoff P"],
    "joel embiid": ["The Process"],
    "ja morant": ["Ja"],
    "zion williamson": ["Zanos"],
    "derrick rose": ["D Rose", "D-Rose"],
    "kevin garnett": ["KG", "The Big Ticket"],
    "dirk nowitzki": ["The Tall Baller from the G"],
    "tim duncan": ["The Big Fundamental"],
    "magic johnson": ["Magic"],
    "larry bird": ["Larry Legend"],
    "hakeem olajuwon": ["The Dream", "Hakeem the Dream"],
    "charles barkley": ["Chuck", "Sir Charles"],
    "julius erving": ["Dr J", "Doctor J"],
    "dominique wilkins": ["Human Highlight Film"],
    "shawn kemp": ["Reign Man"],
    "gary payton": ["The Glove"],
    "jason williams": ["White Chocolate"],
    "penny hardaway": ["Penny"],
    "amare stoudemire": ["STAT"],
    "manu ginobili": ["Manu"],
    "tony parker": ["TP"],
    "rajone rondo": ["Playoff Rondo"],
    "ray allen": ["Jesus Shuttlesworth"],
    "demar derozan": ["Deebo"],
    "jimmy butler": ["Jimmy Buckets"],
    "donovan mitchell": ["Spida", "Spida Mitchell"],
    "trae young": ["Ice Trae"],
    "jayson tatum": ["JT"],
    "jaylen brown": ["JB"],
    "victor wembanyama": ["Wemby", "The Alien"],
}

NUMBERED_COMPILATION_WORDS = (
    "top 5", "top five", "top 10", "top ten", "10 best", "best 10",
    "top 15", "top 20", "top 25", "top 30", "top 40", "top 50",
    "top 75", "top 100", "50 best", "100 best",
)

COMPILATION_WORDS = (
    "best", "greatest", "all", "every", "career", "ultimate", "complete",
    "compilation", "collection", "mixtape", "highlight reel", "highlights",
    "moments", "plays of all time", "best of", "nastiest", "craziest",
    "most iconic", "most disrespectful", "rare highlights", "forgotten highlights",
)

TRUSTED_CHANNEL_TERMS = (
    "nba", "nba on espn", "espn", "sportscenter", "house of highlights",
    "bleacher report", "tnt", "nba tv", "nbatv", "abc", "cbs sports",
    "fox sports", "the score", "hoopmixtape", "ballislife", "maxamillion711",
    "hicko", "thenbafreak", "nba top 10", "pred21", "b z z",
)

# Players expected to have a deep YouTube highlight pool. Generic single-game
# packages are suppressed for these names unless the requested action appears
# in the title. Unknown players are classified adaptively after a search.
HIGHLIGHT_RICH_PLAYERS = {
    "kareem abdul jabbar", "ray allen", "carmelo anthony", "giannis antetokounmpo",
    "charles barkley", "larry bird", "kobe bryant", "jimmy butler", "vince carter",
    "stephen curry", "anthony davis", "demar derozan", "luka doncic", "tim duncan",
    "kevin durant", "julius erving", "kevin garnett", "paul george", "manu ginobili",
    "blake griffin", "james harden", "penny hardaway", "grant hill", "dwight howard",
    "allen iverson", "lebron james", "magic johnson", "nikola jokic", "shawn kemp",
    "kawhi leonard", "damian lillard", "karl malone", "moses malone", "ja morant",
    "tracy mcgrady", "reggie miller", "donovan mitchell", "steve nash",
    "dirk nowitzki", "shaquille oneal", "shaquille o neal", "hakeem olajuwon",
    "chris paul", "gary payton", "paul pierce", "scottie pippen", "derrick rose",
    "bill russell", "domantas sabonis", "david robinson", "jayson tatum",
    "isiah thomas", "klay thompson", "dwyane wade", "russell westbrook",
    "victor wembanyama", "jason williams", "dominique wilkins", "zion williamson",
    "trae young", "michael jordan", "john stockton", "patrick ewing",
}

SEASON_CAREER_TERMS = (
    "career highlights", "career highlight", "career mixtape", "career mix",
    "season highlights", "season highlight", "rookie season", "sophomore season",
    "playoff highlights", "playoffs highlights", "finals highlights",
    "regular season highlights", "prime highlights", "team highlights",
    "best season", "full season", "year highlights", "highlights 19", "highlights 20",
)

GENERIC_GAME_PACKAGE_TERMS = (
    "full game highlights", "full highlights", "game highlights", "all plays vs",
    "every play vs", "every point", "all possessions", "complete game",
    "highlights vs", "points vs", "pts vs", "full game",
)

EXCLUDED_CONTENT_TERMS = (
    "#shorts", "youtube shorts", "yt shorts", "slam dunk contest", "dunk contest",
    "all-star game", "all star game", "nba all-star", "nba all star", "rising stars",
    "skills challenge", "three-point contest", "3-point contest", "celebrity game",
    "summer league", "g league", "wnba", "ncaa", "college basketball",
    "high school", "prep basketball", "aau", "euroleague", "overseas league",
    "reaction", "reacts", "podcast", "interview", "documentary", "nba 2k", "nba2k",
    "2k26", "2k25", "2k24", "2k23", "video game", "nba live", "nba live 06",
    "nba live 07", "nba live 08", "nba live 09", "nba live 10", "nba live 14",
    "nba live 15", "nba live 16", "nba live 18", "nba live 19", "ea sports nba",
    "gameplay", "simulation",
)

NBA_CONTEXT_TERMS = (
    "nba", "playoffs", "playoff", "nba finals", "conference finals", "regular season",
    "espn", "tnt", "abc", "nbatv", "nba tv", "house of highlights",
    "lakers", "celtics", "knicks", "nets", "76ers", "sixers", "raptors", "bulls",
    "cavaliers", "cavs", "pistons", "pacers", "bucks", "heat", "magic", "hawks",
    "hornets", "wizards", "spurs", "mavericks", "mavs", "rockets", "grizzlies",
    "pelicans", "warriors", "clippers", "suns", "kings", "trail blazers", "blazers",
    "jazz", "nuggets", "timberwolves", "thunder",
)


def result_text(item: dict) -> str:
    tags = item.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    values = [item.get("title"), item.get("description"), item.get("channel_title"), *tags]
    return " ".join(str(value) for value in values if value).lower()


def is_short_result(item: dict) -> bool:
    """Return True when a result is short-form or 60 seconds or shorter."""
    text = result_text(item)
    url = str(item.get("youtube_url") or "").lower()
    duration = int(item.get("duration_seconds") or 0)
    return "/shorts/" in url or "#shorts" in text or "youtube shorts" in text or "yt shorts" in text or (0 < duration <= 60)


def _normalized_words(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _player_relevant(item: dict, player_name: str) -> bool:
    """Reject unrelated results while keeping cautious description-only matches."""
    player = _normalized_words(player_name)
    if not player:
        return True
    title = _normalized_words(item.get("title"))
    description = _normalized_words(item.get("description"))
    parts = player.split()
    surname = parts[-1] if parts else ""

    if player in title:
        return True
    # A distinctive surname in the title is usually sufficient for player highlight searches.
    if len(surname) >= 5 and re.search(rf"\b{re.escape(surname)}\b", title):
        return True

    if player in description:
        # Keep description-only matches only when the nearby text reads like an actual play/highlight reference.
        play_terms = (
            "highlight", "highlights", "dunk", "poster", "slam", "alley oop", "layup",
            "block", "steal", "assist", "crossover", "game winner", "buzzer", "clutch",
            "scores", "throws down", "finishes", "playoffs", "regular season",
        )
        positions = [match.start() for match in re.finditer(re.escape(player), description)]
        if len(positions) >= 2:
            return True
        for pos in positions:
            nearby = description[max(0, pos - 140):pos + len(player) + 180]
            if any(term in nearby for term in play_terms):
                return True
    return False


CATEGORY_CONFLICT_TERMS = {
    "Top 10 Dunks": ("assist", "assists", "passing", "passes", "playmaking", "blocks", "block compilation", "steals", "steal compilation", "crossovers", "ankle breakers", "three pointers", "3 pointers", "shooting highlights"),
    "Top 10 Posters": ("assist", "assists", "passing", "blocks", "steals", "crossovers", "three pointers", "shooting highlights"),
    "Top 10 Blocks": ("assist", "assists", "passing highlights", "dunk compilation", "dunks of", "crossovers", "three pointers", "shooting highlights"),
    "Top 10 Assists": ("dunk compilation", "top 10 dunks", "best dunks", "blocks", "block compilation", "steals", "steal compilation", "crossovers", "ankle breakers"),
    "Top 10 Crossovers": ("top 10 dunks", "dunk compilation", "blocks", "block compilation", "assists", "passing highlights", "rebound highlights"),
    "Top 10 Layups": ("three pointers", "shooting highlights", "blocks", "block compilation", "assists", "passing highlights"),
    "Top 10 Steals": ("top 10 dunks", "dunk compilation", "blocks", "block compilation", "assists", "passing highlights"),
    "Top 10 Game Winners": ("assist compilation", "passing highlights", "block compilation", "dunk compilation"),
    "Top 10 Buzzer Beaters": ("assist compilation", "passing highlights", "block compilation", "dunk compilation"),
}

def _title_explicitly_conflicts(item: dict, category: str) -> bool:
    title = _normalized_words(item.get("title"))
    if not title:
        return False
    requested_terms = tuple(_normalized_words(term) for term in CATEGORY_TERMS.get(category, []))
    if any(term and term in title for term in requested_terms):
        return False
    return any(term in title for term in CATEGORY_CONFLICT_TERMS.get(category, ()))

def _category_relevant(item: dict, category: str) -> bool:
    """Reject videos whose title explicitly advertises a different play type."""
    title = _normalized_words(item.get("title"))
    description = _normalized_words(item.get("description"))
    text = f"{title} {description}"

    # A title such as "Top 10 Assists" must never survive a dunk search merely
    # because its description also contains the player's dunks or highlights.
    if _title_explicitly_conflicts(item, category):
        return False

    positive = tuple(_normalized_words(term) for term in CATEGORY_TERMS.get(category, []))
    if any(term and term in text for term in positive):
        return True

    # Broad player compilations remain useful source packages for category clips,
    # but only after explicit wrong-category titles have been removed above.
    broad_source_terms = (
        "top 10 plays", "top ten plays", "top 20 plays", "top 50 plays",
        "top 100 plays", "best plays", "greatest plays", "career highlights",
        "ultimate highlights", "highlight reel", "mixtape", "best moments",
        "greatest moments", "career", "season highlights", "highlights",
    )
    return any(term in text for term in broad_source_terms)


def _looks_vertical_short_form(item: dict) -> bool:
    """Use reliable metadata only; ambiguous horizontal uploads are retained."""
    width = int(item.get("thumbnail_width") or 0)
    height = int(item.get("thumbnail_height") or 0)
    text = result_text(item)
    duration = int(item.get("duration_seconds") or 0)
    if width and height and height > width * 1.15:
        return True
    if any(term in text for term in (" tiktok ", " instagram reel", " reels", "vertical video", "portrait video")) and duration <= 180:
        return True
    return False


def _is_known_highlight_rich_player(player_name: str) -> bool:
    normalized = _normalized_words(player_name)
    return normalized in HIGHLIGHT_RICH_PLAYERS


def _title_has_requested_action(item: dict, category: str) -> bool:
    title = _normalized_words(item.get("title"))
    terms = [_normalized_words(term) for term in CATEGORY_TERMS.get(category, [])]
    return any(term and re.search(rf"\b{re.escape(term)}\b", title) for term in terms)


def _is_generic_single_game_package(item: dict, category: str) -> bool:
    title = _normalized_words(item.get("title"))
    duration = int(item.get("duration_seconds") or 0)
    game_wording = any(term in title for term in GENERIC_GAME_PACKAGE_TERMS)
    matchup_wording = bool(re.search(r"\bvs\b|\bversus\b|\bagainst\b", title))
    score_line = bool(re.search(r"\b\d{2,3}\s*(?:pts|points)\b", title))
    looks_like_game = game_wording or (matchup_wording and (duration >= 240 or score_line))
    return looks_like_game and not _title_has_requested_action(item, category)


_THUMBNAIL_CROP_CACHE: dict[str, bool] = {}
_THUMBNAIL_CROP_LOCK = threading.Lock()

def _region_stats(image: Image.Image, left: int, right: int) -> tuple[float, float]:
    region = image.crop((left, 0, right, image.height)).convert("L")
    brightness = float(ImageStat.Stat(region).mean[0])
    edges = region.filter(ImageFilter.FIND_EDGES)
    sharpness = float(ImageStat.Stat(edges).mean[0])
    return brightness, sharpness

def _thumbnail_has_embedded_portrait(item: dict) -> bool:
    """Detect portrait footage embedded inside a 16:9 frame with side panels/bars."""
    video_id = str(item.get("video_id") or "")
    url = str(item.get("thumbnail") or "")
    cache_key = video_id or url
    if not cache_key or not url:
        return False
    with _THUMBNAIL_CROP_LOCK:
        if cache_key in _THUMBNAIL_CROP_CACHE:
            return _THUMBNAIL_CROP_CACHE[cache_key]
    detected = False
    try:
        response = requests.get(url, timeout=6, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        image = Image.open(BytesIO(response.content)).convert("RGB").resize((320, 180))
        gray = image.convert("L")
        w, h = gray.size
        # Portrait-in-landscape edits generally create two strong vertical seams
        # around a narrow, sharper center panel while the sides are dark or blurred.
        column_diffs = []
        px = gray.load()
        for x in range(1, w):
            column_diffs.append(sum(abs(px[x, y] - px[x-1, y]) for y in range(h)) / h)
        left_candidates = range(int(w*.23), int(w*.43))
        right_candidates = range(int(w*.57), int(w*.77))
        left_x = max(left_candidates, key=lambda x: column_diffs[x-1])
        right_x = max(right_candidates, key=lambda x: column_diffs[x-1])
        left_seam = column_diffs[left_x-1]
        right_seam = column_diffs[right_x-1]
        center_width = right_x - left_x
        lb, ls = _region_stats(image, 0, left_x)
        cb, cs = _region_stats(image, left_x, right_x)
        rb, rs = _region_stats(image, right_x, w)
        side_brightness = (lb + rb) / 2
        side_sharpness = (ls + rs) / 2
        strong_two_seams = left_seam >= 20 and right_seam >= 20
        narrow_center = int(w*.24) <= center_width <= int(w*.48)
        blurred_sides = cs > 4 and side_sharpness < cs * .72
        dark_sides = cb > 20 and side_brightness < cb * .58
        detected = bool(strong_two_seams and narrow_center and (blurred_sides or dark_sides))
    except Exception:
        detected = False
    with _THUMBNAIL_CROP_LOCK:
        _THUMBNAIL_CROP_CACHE[cache_key] = detected
    return detected

def _mark_embedded_portrait_results(results: dict[str, dict]) -> None:
    candidates = [item for item in results.values() if not item.get("portrait_crop_checked")]
    if not candidates:
        return
    with ThreadPoolExecutor(max_workers=8, thread_name_prefix="clip-thumb-check") as pool:
        flags = list(pool.map(_thumbnail_has_embedded_portrait, candidates))
    for item, flag in zip(candidates, flags):
        item["portrait_crop_checked"] = True
        item["portrait_crop_detected"] = bool(flag)

def is_allowed_nba_game_result(item: dict, player_name: str = "", category: str = "", suppress_generic_games: bool = False) -> bool:
    """Keep relevant NBA game footage and reject unrelated, short-form, or game content."""
    text = result_text(item)
    compact = re.sub(r"[^a-z0-9]+", "", text)
    if is_short_result(item) or _looks_vertical_short_form(item) or item.get("portrait_crop_detected"):
        return False
    if any(term in text for term in EXCLUDED_CONTENT_TERMS):
        return False
    if re.search(r"nba\s*2k\s*\d{0,2}", text) or "nba2k" in compact:
        return False
    if re.search(r"nba\s*live(?:\s*\d{2,4})?", text) or "nbalive" in compact or "easportsnba" in compact:
        return False
    if not any(term in text for term in NBA_CONTEXT_TERMS):
        return False
    if player_name and not _player_relevant(item, player_name):
        return False
    if category and not _category_relevant(item, category):
        return False
    if suppress_generic_games and category and _is_generic_single_game_package(item, category):
        return False
    return True


def _normalize_instances(result: dict) -> list[dict]:
    """Return stable per-source clip instances so one long video can supply many plays."""
    raw = result.get("clip_instances")
    if not isinstance(raw, list) or not raw:
        raw = [{
            "instance_id": str(uuid.uuid4()),
            "label": "Clip 1",
            "notes": result.get("notes", ""),
            "rank_number": result.get("rank_number"),
        }]
    normalized = []
    for index, item in enumerate(raw[:30], start=1):
        if not isinstance(item, dict):
            item = {}
        rank = item.get("rank_number")
        normalized.append({
            "instance_id": str(item.get("instance_id") or uuid.uuid4()),
            "label": str(item.get("label") or f"Clip {index}")[:80],
            "notes": str(item.get("notes") or "")[:500],
            "rank_number": rank if isinstance(rank, int) and 1 <= rank <= 10 else None,
        })
    return normalized

def normalize_project(project: dict) -> dict:
    """Keep saved projects compatible with the simplified two-state review UI."""
    normalized = []
    for result in project.get("results", []):
        # Never destructively remove saved results merely because a player is
        # highlight-rich. Generic game suppression is a search/ranking concern,
        # not a project-loading rule. This preserves prior findings and reviews.
        if result.get("status") == "removed" or not is_allowed_nba_game_result(
            result, project.get("player_name", ""), project.get("category", ""), False
        ):
            continue
        if result.get("status") not in {"approved", "rejected"}:
            result["status"] = "unreviewed"
        result.pop("timestamp_ranges", None)
        result["clip_instances"] = _normalize_instances(result)
        result["rank_number"] = result["clip_instances"][0].get("rank_number") if len(result["clip_instances"]) == 1 else None
        normalized.append(result)
    project["results"] = normalized
    valid_ids = {r.get("result_id") for r in normalized if r.get("status") == "approved"}
    project["ranking"] = [rid for rid in project.get("ranking", []) if rid in valid_ids]
    return project


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def project_file(project_id: str) -> Path:
    return PROJECTS_DIR / f"{project_id}.json"


def load_project(project_id: str):
    path = project_file(project_id)
    if not path.exists():
        raise HTTPException(404, "Clip Finder project not found")
    return normalize_project(json.loads(path.read_text(encoding="utf-8")))


def save_cf_project(project: dict):
    normalize_project(project)
    project["updated_at"] = now_iso()
    destination = project_file(project["project_id"])
    _write_json_resilient(destination, project)
    return project


def parse_duration(value: str) -> int:
    match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not match:
        return 0
    h, m, s = [int(v or 0) for v in match.groups()]
    return h * 3600 + m * 60 + s


def _player_aliases(player: str) -> list[str]:
    normalized = _normalized_words(player)
    return PLAYER_NICKNAMES.get(normalized, [])


def _category_subjects(category: str) -> list[str]:
    terms = CATEGORY_TERMS.get(category) or [category.replace("Top 10", "").strip()]
    subjects = []
    for term in terms:
        cleaned = str(term or "").strip()
        if cleaned and cleaned not in subjects:
            subjects.append(cleaned)
    return subjects


def _search_time_hints(player: str, category: str) -> list[str]:
    text = f"{player} {category}"
    years = list(dict.fromkeys(re.findall(r"\b(?:19|20)\d{2}\b", text)))
    hints = []
    for year in years:
        hints.extend([year, f"{year} season", f"{year} playoffs"])
    season_match = re.search(r"\b((?:19|20)\d{2})[-/](\d{2,4})\b", text)
    if season_match:
        hints.append(season_match.group(0))
    return list(dict.fromkeys(hints))


def search_queries(player: str, category: str):
    """Build a compilation-first, category-specific YouTube search plan.

    Exact player-name searches always run first. Nicknames are intentionally
    lower priority and only broaden discovery after the real-name searches.
    """
    subjects = _category_subjects(category)
    primary = subjects[0]
    aliases = _player_aliases(player)
    time_hints = _search_time_hints(player, category)
    queries: list[str] = []

    def add(phrase: str):
        # Keep discovery queries natural. Relevance/exclusion rules are applied
        # after discovery, which avoids suppressing legitimate YouTube results.
        query = f'{phrase} NBA'.strip()
        if query not in queries:
            queries.append(query)

    # Tier 1: exact category compilations and every common numbered format.
    for subject in subjects[:8]:
        for numbered in (
            "top 10", "top ten", "10 best", "best 10", "top 20", "top 25",
            "top 30", "top 35", "top 40", "top 45", "top 50", "top 60",
            "top 75", "top 80", "top 100", "20 best", "25 best", "30 best",
            "50 best", "75 best", "100 best", "best twenty", "best fifty",
        ):
            add(f'"{player}" {numbered} {subject}')
        for descriptor in (
            "best", "greatest", "all", "every", "career", "ultimate", "complete",
            "nastiest", "craziest", "most iconic", "most disrespectful",
        ):
            add(f'"{player}" {descriptor} {subject}')
        for format_word in (
            "compilation", "collection", "mixtape", "highlight reel", "highlights",
            "career highlights", "season highlights", "best of all time",
        ):
            add(f'"{player}" {subject} {format_word}')

    # Tier 2: broad player compilations that may contain rare category clips.
    for phrase in (
        "top 10 plays", "top 20 plays", "top 50 plays", "top 100 plays",
        "best plays", "greatest plays", "career highlights", "ultimate highlights",
        "greatest moments", "best moments", "iconic moments", "highlight compilation",
        "career mixtape", "complete highlights", "rare highlights", "forgotten highlights",
        "season highlights", "playoff highlights",
    ):
        add(f'"{player}" {phrase}')

    # Tier 3: clearly titled solo plays. No defender-name guessing is performed.
    solo_patterns = {
        "Top 10 Dunks": (
            "poster dunk", "dunk on", "dunks on", "dunk over", "posterizes",
            "monster dunk", "hammer dunk", "tomahawk dunk", "windmill dunk",
            "reverse dunk", "baseline dunk", "putback dunk", "tip slam",
            "alley oop dunk", "lob dunk", "one handed dunk", "two handed dunk",
            "fast break dunk", "transition dunk", "in game dunk", "slam vs",
        ),
        "Top 10 Posters": (
            "poster dunk", "posterizes", "dunk on", "dunks on", "dunk over",
            "dunks over", "facial", "puts on a poster", "slams on",
        ),
        "Top 10 Blocks": (
            "chase down block", "chasedown block", "block vs", "blocks shot",
            "monster block", "rejection", "swat", "game saving block",
        ),
        "Top 10 Game Winners": (
            "game winner", "game winning shot", "last second shot", "go ahead shot",
            "wins the game", "walk off shot", "overtime game winner", "playoff game winner",
        ),
        "Top 10 Buzzer Beaters": (
            "buzzer beater", "at the buzzer", "beats the buzzer", "last second shot",
            "walk off shot", "playoff buzzer beater",
        ),
        "Top 10 Clutch Shots": (
            "clutch shot", "clutch three", "dagger", "late game shot", "fourth quarter",
            "overtime shot", "game tying shot", "go ahead basket", "clutch bucket",
        ),
        "Top 10 Assists": (
            "no look pass", "behind the back pass", "alley oop assist", "lob assist",
            "incredible assist", "great pass", "full court pass", "clutch assist",
        ),
        "Top 10 Crossovers": (
            "crossover", "ankle breaker", "breaks ankles", "killer crossover",
            "hesitation move", "stepback crossover", "crossover vs",
        ),
        "Top 10 Handles": (
            "handles", "dribble move", "ankle breaker", "breaks ankles",
            "hesitation", "iso move", "ball handling", "handle sequence",
        ),
        "Top 10 Layups": (
            "reverse layup", "acrobatic layup", "circus layup", "finger roll",
            "scoop layup", "up and under", "tough finish", "layup vs",
        ),
        "Top 10 Steals": (
            "steal vs", "pick pocket", "pickpocket", "strips", "interception",
            "game saving steal", "clutch steal", "takeaway",
        ),
        "Top 10 Alley-Oops": (
            "alley oop", "alley-oop", "lob dunk", "catches the lob",
            "finishes the lob", "oop vs",
        ),
        "Top 10 Defensive Plays": (
            "defensive play", "defensive stop", "game saving defense", "block vs",
            "steal vs", "takes charge", "lockdown defense",
        ),
        "Top 10 Plays": (
            "game winner", "buzzer beater", "poster dunk", "incredible play",
            "amazing play", "unbelievable play", "iconic moment", "clutch play",
            "best play vs", "highlight vs",
        ),
    }
    for phrase in solo_patterns.get(category, (primary,)):
        add(f'"{player}" {phrase}')
        add(f'"{player}" {phrase} vs')
        add(f'"{player}" {phrase} playoffs')

    # Tier 4: game, season, team-era, and date-oriented source packages.
    for subject in subjects[:5]:
        for phrase in (
            f"{subject} vs", f"{subject} game highlights", f"{subject} full highlights",
            f"{subject} playoff highlights", f"{subject} regular season",
        ):
            add(f'"{player}" {phrase}')
    for phrase in (
        "full game highlights", "all plays vs", "every play vs", "best plays vs",
        "playoff game highlights", "regular season highlights", "rookie season highlights",
        "prime highlights", "team highlights", "career game highlights",
    ):
        add(f'"{player}" {phrase}')

    for hint in time_hints:
        for subject in subjects[:4]:
            add(f'"{player}" {hint} {subject}')
            add(f'"{player}" {subject} {hint} highlights')

    # Tier 5: nicknames. These are intentionally last and never replace the name.
    for alias in aliases:
        for phrase in (
            f"top 10 {primary}", f"best {primary}", f"greatest {primary}",
            f"{primary} compilation", "career highlights", "greatest moments",
        ):
            add(f'"{alias}" "{player}" {phrase}')
            add(f'"{alias}" {phrase}')

    return queries


def prioritized_execution_queries(player: str, category: str, all_queries: list[str]) -> list[str]:
    """Put natural YouTube searches and trusted compilation channels first."""
    subject = _category_subjects(category)[0]
    simple = [
        f'{player} {category}',
        f'{player} top 10 {subject}',
        f'{player} best {subject}',
        f'{player} greatest {subject}',
        f'{player} {subject} compilation',
        f'{player} top 10 plays',
        f'{player} top 20 plays',
        f'{player} top 50 plays',
        f'{player} top 100 plays',
        f'{player} best plays',
        f'{player} greatest plays',
        f'{player} career highlights',
        f'{player} ultimate highlights',
        f'{player} highlight reel',
    ]
    channels = (
        "NBA", "House Of Hoops", "House of Highlights", "NBA Top 10",
        "MaxaMillion711", "Hicko", "TheNBAFreak", "Bleacher Report",
        "ESPN", "NBA TV", "Ballislife", "Hoopmixtape",
    )
    simple.extend(f'{player} {subject} {channel}' for channel in channels)
    simple.extend(f'{player} top plays {channel}' for channel in channels[:8])
    ordered: list[str] = []
    for query in [*simple, *all_queries]:
        clean = " ".join(str(query).split())
        if clean and clean not in ordered:
            ordered.append(clean)
    # Exhaustive mode deliberately keeps a focused set of natural searches,
    # then follows every continuation page for each one. The limit is configurable.
    limit = max(8, min(60, int(os.getenv("CLIP_FINDER_EXHAUSTIVE_QUERY_LIMIT", "10"))))
    return ordered[:limit]


def _source_type(item: dict, category: str) -> str:
    title = _normalized_words(item.get("title"))
    description = _normalized_words(item.get("description"))
    text = f"{title} {description}"
    duration = int(item.get("duration_seconds") or 0)
    category_terms = [_normalized_words(term) for term in CATEGORY_TERMS.get(category, [])]
    numbered = any(term in text for term in NUMBERED_COMPILATION_WORDS) or bool(
        re.search(r"\b(?:top|best|greatest)\s+(?:5|10|15|20|25|30|35|40|45|50|60|75|80|100)\b", text)
    )
    compilation = numbered or any(term in text for term in COMPILATION_WORDS)
    season_career = any(term in text for term in SEASON_CAREER_TERMS) or bool(
        re.search(r"\b(?:19|20)\d{2}(?:[ -](?:19|20)?\d{2})?\s+(?:season\s+)?highlights\b", text)
    )
    full_game = any(term in text for term in GENERIC_GAME_PACKAGE_TERMS) or duration >= 1200
    solo_markers = (
        " vs ", " game winner", "buzzer beater", "poster", "posterizes", "dunk on",
        "dunks on", "dunk over", "windmill", "reverse dunk", "tomahawk", "alley oop",
        "block on", "chase down", "steal", "layup", "assist", "crossover",
        "ankle breaker", "clutch shot", "at the buzzer",
    )
    category_match = any(term and term in text for term in category_terms)
    solo = not compilation and not season_career and not full_game and (
        any(marker in f" {title} " for marker in solo_markers)
        or (0 < duration <= 300 and any(term and term in title for term in category_terms))
    )
    if numbered:
        return "numbered_compilation"
    if compilation and category_match:
        return "category_compilation"
    if solo and category_match:
        return "category_solo"
    if solo:
        return "solo"
    if season_career:
        return "season_career_reel"
    if compilation:
        return "broad_compilation"
    if full_game:
        return "game_package"
    return "fallback"

def score_result(item: dict, player: str, category: str):
    title = str(item.get("title") or "").lower()
    description = str(item.get("description") or "").lower()
    channel = str(item.get("channel_title") or "").lower()
    text = f"{title} {description}"
    views = int(item.get("views") or 0)
    duration = int(item.get("duration_seconds") or 0)
    terms = [term.lower() for term in CATEGORY_TERMS.get(category, [])]
    source_type = _source_type(item, category)

    score = 0
    normalized_player = _normalized_words(player)
    normalized_title = _normalized_words(title)
    surname = normalized_player.split()[-1] if normalized_player else ""
    if normalized_player and normalized_player in normalized_title:
        score += 24
    elif surname and len(surname) >= 5 and re.search(rf"\b{re.escape(surname)}\b", normalized_title):
        score += 14

    if any(term in title for term in terms):
        score += 18
    elif any(term in text for term in terms):
        score += 8

    source_points = {
        "numbered_compilation": 44,
        "category_compilation": 38,
        "category_solo": 31,
        "solo": 25,
        "season_career_reel": 19,
        "broad_compilation": 14,
        "game_package": 5,
        "fallback": 1,
    }
    score += source_points[source_type]

    # Popularity strongly separates established source compilations from
    # low-view title copies once relevance is confirmed.
    if views > 0:
        score += min(24, max(0, int(math.log10(max(1, views)) * 4) - 4))
    if views >= 10_000_000:
        score += 8
    elif views >= 1_000_000:
        score += 6
    elif views >= 100_000:
        score += 4
    elif views < 100:
        score -= 8
    elif views < 1_000:
        score -= 4

    if any(term in channel for term in TRUSTED_CHANNEL_TERMS):
        score += 9
    if any(term in text for term in ("hd", "1080p", "4k", "remastered")):
        score += 3
    if any(term in text for term in ("playoffs", "nba finals", "conference finals", "game 7")):
        score += 4

    # Useful compilations are usually long enough to contain options, while
    # clearly titled solo clips are often short. Full games stay available but low.
    if source_type in {"numbered_compilation", "category_compilation", "broad_compilation", "season_career_reel"}:
        if 180 <= duration <= 3600:
            score += 6
        elif 60 <= duration < 180:
            score += 2
    elif source_type in {"category_solo", "solo"}:
        if 61 <= duration <= 300:
            score += 6
    elif duration >= 5400:
        score -= 6

    aliases = [alias.lower() for alias in _player_aliases(player)]
    if aliases and any(alias in title for alias in aliases):
        score += 2

    # Demote obvious category mismatches without deleting broad source packages.
    mismatch_terms = {
        "Top 10 Dunks": ("three pointer", "3 pointer", "jump shot", "free throw", "shooting highlights"),
        "Top 10 Blocks": ("three point highlights", "shooting highlights", "assist mix"),
        "Top 10 Assists": ("dunk contest", "block compilation"),
        "Top 10 Crossovers": ("block compilation", "rebound highlights"),
        "Top 10 Layups": ("three pointer", "jump shot", "block compilation"),
    }.get(category, ())
    if _title_explicitly_conflicts(item, category) or any(term in title for term in mismatch_terms):
        score -= 60

    item["source_priority"] = source_type
    return max(0, min(100, score))


class CreateProject(BaseModel):
    player_name: str = Field(min_length=1, max_length=100)
    category: str = "Top 10 Plays"


class ResultUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    local_file_path: Optional[str] = None
    rank_number: Optional[int] = None
    clip_count: Optional[int] = None
    clip_instances: Optional[List[dict[str, Any]]] = None


class RankingUpdate(BaseModel):
    ranked_result_ids: List[str]


class BeginDownloadRequest(BaseModel):
    result_id: str


class OpenAttachmentLocationRequest(BaseModel):
    project_id: str
    result_id: str


@router.get("/categories")
def categories():
    return {"categories": TOP10_CATEGORIES}


def _editor_project_uploaded(project_id: Optional[str]) -> bool:
    if not project_id:
        return False
    try:
        from routes.content_studio import load_project as load_editor_project
        editor_project = load_editor_project(project_id)
        return editor_project.get("status") == "uploaded" or bool(editor_project.get("youtube_upload"))
    except Exception:
        return False


def _reconcile_completed_archive(project: dict) -> dict:
    """Archive only after the final Top 10 and every generated solo project uploaded."""
    if project.get("trashed") or not project.get("editor_project_id"):
        return project
    solo_ids = project.get("solo_project_ids") or []
    if solo_ids and _editor_project_uploaded(project.get("editor_project_id")) and all(_editor_project_uploaded(pid) for pid in solo_ids):
        project["trashed"] = True
        project["trashed_at"] = now_iso()
        project["trash_reason"] = "All Top 10 and solo projects uploaded successfully"
        save_cf_project(project)
    return project


@router.get("/projects")
def list_projects(include_deleted: bool = False):
    projects = []
    for path in PROJECTS_DIR.glob("*.json"):
        try:
            p = normalize_project(json.loads(path.read_text(encoding="utf-8")))
            p = _reconcile_completed_archive(p)
            if bool(p.get("trashed")) != bool(include_deleted):
                continue
            projects.append({k: p.get(k) for k in ["project_id", "player_name", "category", "created_at", "updated_at", "trashed", "trashed_at", "trash_reason"]} | {
                "result_count": len(p.get("results", [])),
                "approved_count": sum(1 for r in p.get("results", []) if r.get("status") == "approved"),
                "unreviewed_count": sum(1 for r in p.get("results", []) if r.get("status") not in {"approved", "rejected"}),
            })
        except Exception:
            pass
    projects.sort(key=lambda p: p.get("trashed_at" if include_deleted else "updated_at", ""), reverse=True)
    return {"projects": projects}


@router.post("/projects/{project_id}/trash")
def trash_project(project_id: str):
    project = load_project(project_id)
    project["trashed"] = True
    project["trashed_at"] = now_iso()
    project["trash_reason"] = "Deleted by user"
    save_cf_project(project)
    return {"project": project}


@router.post("/projects/{project_id}/restore")
def restore_project(project_id: str):
    project = load_project(project_id)
    project["trashed"] = False
    project["trashed_at"] = None
    project["trash_reason"] = None
    save_cf_project(project)
    return {"project": project}


@router.delete("/projects/{project_id}")
def permanently_delete_project(project_id: str):
    path = project_file(project_id)
    if not path.exists():
        raise HTTPException(404, "Clip Finder project not found")
    path.unlink()
    return {"ok": True, "project_id": project_id}


@router.post("/projects")
def create_project(payload: CreateProject):
    if payload.category not in TOP10_CATEGORIES:
        raise HTTPException(400, "Unknown Top 10 category")
    project = {
        "project_id": str(uuid.uuid4()),
        "player_name": payload.player_name.strip(),
        "category": payload.category,
        "search_depth": "precision_exhaustive",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "results": [],
        "queries_run": [],
        "ranking": [],
        "editor_project_id": None,
        "trashed": False,
        "trashed_at": None,
        "trash_reason": None,
    }
    save_cf_project(project)
    return {"project": project}


@router.get("/projects/{project_id}")
def get_project(project_id: str):
    return {"project": load_project(project_id)}


def _extract_balanced_json(source: str, marker: str) -> Optional[dict]:
    """Extract the JSON object assigned after a marker in YouTube HTML."""
    marker_index = source.find(marker)
    if marker_index < 0:
        return None
    brace_index = source.find("{", marker_index + len(marker))
    if brace_index < 0:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(brace_index, len(source)):
        char = source[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(source[brace_index:index + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _text_value(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    if value.get("simpleText") is not None:
        return str(value.get("simpleText") or "")
    return "".join(str(run.get("text") or "") for run in value.get("runs", []) if isinstance(run, dict))


def _parse_compact_count(value: str) -> int:
    text = str(value or "").lower().replace("views", "").replace(",", "").strip()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*([kmb])?", text)
    if not match:
        return 0
    number = float(match.group(1))
    multiplier = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(match.group(2), 1)
    return int(number * multiplier)


def _parse_clock_duration(value: str) -> int:
    parts = [part for part in str(value or "").strip().split(":") if part.isdigit()]
    if not parts:
        return 0
    total = 0
    for part in parts:
        total = total * 60 + int(part)
    return total


def _renderer_to_result(renderer: dict[str, Any]) -> Optional[dict[str, Any]]:
    video_id = str(renderer.get("videoId") or "").strip()
    if not video_id:
        return None
    title = html.unescape(_text_value(renderer.get("title"))) or "Untitled"
    channel = html.unescape(_text_value(renderer.get("ownerText")) or _text_value(renderer.get("longBylineText")))
    snippets = renderer.get("detailedMetadataSnippets") or []
    description = ""
    if snippets and isinstance(snippets[0], dict):
        description = html.unescape(_text_value(snippets[0].get("snippetText", {})))
    thumbnails = renderer.get("thumbnail", {}).get("thumbnails", []) or []
    thumb = thumbnails[-1] if thumbnails else {}
    duration_text = _text_value(renderer.get("lengthText"))
    view_text = _text_value(renderer.get("viewCountText")) or _text_value(renderer.get("shortViewCountText"))
    published = _text_value(renderer.get("publishedTimeText"))
    return {
        "video_id": video_id,
        "title": title,
        "channel_title": channel,
        "description": description,
        "tags": [],
        "category_id": "",
        "published_at": published,
        "thumbnail": str(thumb.get("url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"),
        "thumbnail_width": int(thumb.get("width") or 0),
        "thumbnail_height": int(thumb.get("height") or 0),
        "views": _parse_compact_count(view_text),
        "duration_seconds": _parse_clock_duration(duration_text),
        "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
    }


def _extract_search_page(data: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return every video renderer and continuation token in a YouTube response."""
    rows: list[dict[str, Any]] = []
    tokens: list[str] = []
    seen_rows: set[str] = set()
    seen_tokens: set[str] = set()
    for node in _walk_json(data):
        renderer = node.get("videoRenderer") if isinstance(node, dict) else None
        if isinstance(renderer, dict):
            row = _renderer_to_result(renderer)
            if row and row["video_id"] not in seen_rows:
                seen_rows.add(row["video_id"])
                rows.append(row)
        if not isinstance(node, dict):
            continue
        continuation = node.get("continuationCommand")
        if isinstance(continuation, dict):
            token = str(continuation.get("token") or "").strip()
            if token and token not in seen_tokens:
                seen_tokens.add(token)
                tokens.append(token)
    return rows, tokens


def _extract_ytcfg(source: str) -> dict[str, Any]:
    """Read YouTube's public INNERTUBE configuration from the search HTML."""
    merged: dict[str, Any] = {}
    marker = "ytcfg.set("
    offset = 0
    while True:
        index = source.find(marker, offset)
        if index < 0:
            break
        data = _extract_balanced_json(source[index:], marker)
        if isinstance(data, dict):
            merged.update(data)
        offset = index + len(marker)
    return merged


def _sleep_with_progress(seconds: float, progress_callback, *, pages: int, found: int, pending: int, attempt: int, reason: str) -> None:
    """Wait without failing the job and keep the UI informed during throttling."""
    remaining = max(1, int(seconds))
    while remaining > 0:
        if progress_callback:
            progress_callback(
                pages,
                found,
                pending,
                False,
                {
                    "waiting": True,
                    "retry_in_seconds": remaining,
                    "retry_attempt": attempt,
                    "reason": reason,
                },
            )
        step = min(15, remaining)
        time.sleep(step)
        remaining -= step


class _YouTubeWebTemporarilyUnavailable(RuntimeError):
    pass


def _request_youtube_until_available(
    request_fn,
    *,
    progress_callback,
    pages: int,
    found: int,
    pending: int,
    label: str,
    max_attempts: int = 4,
):
    """Retry temporary failures, but never leave a search trapped forever.

    After a bounded paced retry window, the caller switches to the official
    YouTube Data API or preserves partial results and advances to the next query.
    """
    attempt = 0
    while attempt < max(1, max_attempts):
        try:
            response = request_fn()
            status = int(getattr(response, "status_code", 0) or 0)
            if status not in {403, 408, 425, 429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            reason = f"YouTube requested slower search pacing ({status})"
        except (requests.Timeout, requests.ConnectionError) as exc:
            reason = f"Temporary YouTube connection issue ({exc.__class__.__name__})"
        except requests.RequestException as exc:
            status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
            if status and status not in {403, 408, 425, 429, 500, 502, 503, 504}:
                raise
            reason = f"Temporary YouTube request issue ({status or exc.__class__.__name__})"

        attempt += 1
        if attempt >= max(1, max_attempts):
            raise _YouTubeWebTemporarilyUnavailable(f"{label}: {reason}")

        base = min(180.0, 15.0 * (2 ** min(attempt - 1, 4)))
        delay = base + random.uniform(0.0, max(2.0, base * 0.15))
        _sleep_with_progress(
            delay,
            progress_callback,
            pages=pages,
            found=found,
            pending=pending,
            attempt=attempt,
            reason=f"{label}: {reason}",
        )

    raise _YouTubeWebTemporarilyUnavailable(f"{label}: YouTube web search remained unavailable")


def _scrape_youtube_search(
    query: str,
    timeout: int = 35,
    progress_callback=None,
    max_pages_override: int | None = None,
    max_videos_override: int | None = None,
) -> list[dict[str, Any]]:
    """Exhaustively traverse YouTube web-search continuation pages.

    Temporary limits never terminate the search. CourtVision automatically
    spaces requests, preserves the exact continuation token, waits as long as
    necessary, and resumes from the same page when YouTube becomes available.
    """
    if max_pages_override is None:
        max_pages = max(1, min(5000, int(os.getenv("CLIP_FINDER_MAX_PAGES_PER_QUERY", "8"))))
    else:
        max_pages = max(1, min(5000, int(max_pages_override)))
    if max_videos_override is None:
        max_videos = max(50, min(250_000, int(os.getenv("CLIP_FINDER_MAX_VIDEOS_PER_QUERY", "1500"))))
    else:
        max_videos = max(50, min(250_000, int(max_videos_override)))
    page_delay = max(1.0, min(60.0, float(os.getenv("CLIP_FINDER_PAGE_DELAY_SECONDS", "0.8"))))

    session = requests.Session()
    session.cookies.set("CONSENT", "YES+cb", domain=".youtube.com")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    }

    response = _request_youtube_until_available(
        lambda: session.get(
            "https://www.youtube.com/results",
            params={"search_query": query, "hl": "en", "gl": "US"},
            headers=headers,
            timeout=timeout,
        ),
        progress_callback=progress_callback,
        pages=0,
        found=0,
        pending=1,
        label="Opening search",
        max_attempts=2,
    )

    data = _extract_balanced_json(response.text, "var ytInitialData =")
    if data is None:
        data = _extract_balanced_json(response.text, "ytInitialData =")
    if data is None:
        raise RuntimeError("YouTube returned an unexpected search page format.")

    config = _extract_ytcfg(response.text)
    api_key = str(config.get("INNERTUBE_API_KEY") or "").strip()
    client_version = str(config.get("INNERTUBE_CLIENT_VERSION") or "2.20240726.00.00").strip()
    visitor_data = str(config.get("VISITOR_DATA") or "").strip()
    context = config.get("INNERTUBE_CONTEXT")
    if not isinstance(context, dict):
        context = {
            "client": {
                "clientName": "WEB",
                "clientVersion": client_version,
                "hl": "en",
                "gl": "US",
            }
        }
    else:
        context = json.loads(json.dumps(context))
        client = context.setdefault("client", {})
        client.setdefault("clientName", "WEB")
        client.setdefault("clientVersion", client_version)
        client["hl"] = "en"
        client["gl"] = "US"
        if visitor_data:
            client.setdefault("visitorData", visitor_data)

    first_rows, first_tokens = _extract_search_page(data)
    discovered: dict[str, dict[str, Any]] = {}
    for row in first_rows:
        video_id = row.get("video_id")
        if not video_id or video_id in discovered:
            continue
        discovered[video_id] = row
        if progress_callback:
            progress_callback(1, len(discovered), len(first_tokens), False, {"candidate_added": True, "candidate": row})
    queue = deque(first_tokens)
    queued_tokens = set(first_tokens)
    processed_tokens: set[str] = set()
    pages = 1
    empty_pages = 0

    if progress_callback:
        progress_callback(pages, len(discovered), len(queue), False, None)

    if not api_key:
        return list(discovered.values())

    continuation_headers = {
        **headers,
        "Content-Type": "application/json",
        "Origin": "https://www.youtube.com",
        "Referer": response.url,
        "X-YouTube-Client-Name": "1",
        "X-YouTube-Client-Version": client_version,
    }
    if visitor_data:
        continuation_headers["X-Goog-Visitor-Id"] = visitor_data

    while queue and pages < max_pages and len(discovered) < max_videos:
        token = queue.popleft()
        if not token or token in processed_tokens:
            continue

        payload = {"context": context, "continuation": token}
        continuation_response = _request_youtube_until_available(
            lambda: session.post(
                "https://www.youtube.com/youtubei/v1/search",
                params={"key": api_key, "prettyPrint": "false"},
                headers=continuation_headers,
                json=payload,
                timeout=timeout,
            ),
            progress_callback=progress_callback,
            pages=pages,
            found=len(discovered),
            pending=len(queue) + 1,
            label=f"Continuing page {pages + 1}",
            max_attempts=2,
        )

        # Mark a token complete only after its exact request succeeds. A 429 or
        # connection interruption can therefore never silently discard a page.
        processed_tokens.add(token)
        try:
            continuation_data = continuation_response.json()
        except ValueError as exc:
            raise RuntimeError("YouTube returned an unreadable continuation response.") from exc

        rows, tokens = _extract_search_page(continuation_data)
        before = len(discovered)
        for row in rows:
            video_id = row.get("video_id")
            if not video_id or video_id in discovered:
                continue
            discovered[video_id] = row
            if progress_callback:
                progress_callback(pages + 1, len(discovered), len(queue), False, {"candidate_added": True, "candidate": row})
        added = len(discovered) - before
        pages += 1
        empty_pages = empty_pages + 1 if added == 0 else 0

        for next_token in tokens:
            if next_token not in processed_tokens and next_token not in queued_tokens:
                queued_tokens.add(next_token)
                queue.append(next_token)

        if progress_callback:
            progress_callback(pages, len(discovered), len(queue), False, None)

        if empty_pages >= 8:
            break
        if queue and page_delay:
            time.sleep(page_delay + random.uniform(0.0, min(3.0, page_delay * 0.35)))

    if progress_callback:
        progress_callback(pages, len(discovered), len(queue), True, None)
    return list(discovered.values())

def _enrich_scraped_results(discovered: dict[str, dict], video_ids: list[str]) -> None:
    """Best-effort batch enrichment. Failure never invalidates scraped results."""
    if not video_ids:
        return
    try:
        youtube = get_youtube_service()
    except Exception:
        return
    for offset in range(0, len(video_ids), 50):
        batch = video_ids[offset:offset + 50]
        try:
            details = _execute_with_retry(youtube.videos().list(
                part="snippet,statistics,contentDetails",
                id=",".join(batch),
            ))
        except Exception:
            continue
        for item in details.get("items", []):
            video_id = item.get("id")
            result = discovered.get(video_id)
            if not result:
                continue
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            thumbs = snippet.get("thumbnails", {})
            thumb = thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}
            result.update({
                "title": snippet.get("title") or result.get("title"),
                "channel_title": snippet.get("channelTitle") or result.get("channel_title"),
                "description": snippet.get("description") or result.get("description"),
                "tags": snippet.get("tags", result.get("tags", [])),
                "category_id": snippet.get("categoryId", result.get("category_id", "")),
                "published_at": snippet.get("publishedAt") or result.get("published_at"),
                "thumbnail": thumb.get("url") or result.get("thumbnail"),
                "thumbnail_width": int(thumb.get("width") or result.get("thumbnail_width") or 0),
                "thumbnail_height": int(thumb.get("height") or result.get("thumbnail_height") or 0),
                "views": int(stats.get("viewCount") or result.get("views") or 0),
                "duration_seconds": parse_duration(content.get("duration", "")) or result.get("duration_seconds", 0),
            })


def _search_with_ytdlp(query: str, *, max_results: int = 150, progress_callback=None) -> list[dict[str, Any]]:
    """Independent search fallback that does not use the YouTube Data API.

    yt-dlp uses YouTube's public web clients and is therefore useful when the
    project's Data API key is rate-limited. It is optional at runtime, but is
    included in backend/requirements.txt by this fix.
    """
    try:
        import yt_dlp
    except Exception as exc:
        raise RuntimeError("yt-dlp search fallback is unavailable; install backend requirements") from exc

    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": max(25, int(max_results)),
        "socket_timeout": 30,
        "retries": 2,
        "fragment_retries": 1,
        "ignoreerrors": True,
        "noplaylist": False,
    }
    rows: list[dict[str, Any]] = []
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(f"ytsearch{max(25, int(max_results))}:{query}", download=False) or {}
    for entry in info.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        if not video_id:
            continue
        thumbnails = entry.get("thumbnails") or []
        thumb = thumbnails[-1] if thumbnails and isinstance(thumbnails[-1], dict) else {}
        row = {
            "video_id": video_id,
            "title": html.unescape(str(entry.get("title") or "Untitled")),
            "description": html.unescape(str(entry.get("description") or "")),
            "channel_title": html.unescape(str(entry.get("channel") or entry.get("uploader") or "")),
            "published_at": str(entry.get("timestamp") or entry.get("upload_date") or ""),
            "thumbnail": str(entry.get("thumbnail") or thumb.get("url") or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"),
            "thumbnail_width": int(thumb.get("width") or 0),
            "thumbnail_height": int(thumb.get("height") or 0),
            "views": int(entry.get("view_count") or 0),
            "duration_seconds": int(entry.get("duration") or 0),
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
            "discovery_source": "yt_dlp_search",
        }
        rows.append(row)
        if progress_callback:
            progress_callback(len(rows), row)
    return rows


def _run_search_sync(project_id: str):
    """Run a bounded, web-first Clip Finder search without Data API search.list."""
    project = load_project(project_id)
    existing = {r.get("video_id"): r for r in project.get("results", []) if r.get("video_id")}
    discovered = dict(existing)
    player = project["player_name"].strip()
    category = project["category"].strip()
    subject = category.lower().replace("top 10 ", "").strip()

    queries = list(dict.fromkeys([
        f"{player} {category}",
        f"{player} best {subject}",
        f"{player} greatest {subject}",
        f"{player} {subject} compilation",
        f"{player} career highlights",
        f"{player} {subject} NBA",
        f"{player} {subject} MaxaMillion711",
        f"{player} {subject} TheNBAFreak",
        f"{player} {subject} House of Highlights",
    ]))
    query_limit = max(3, min(len(queries), int(os.getenv("CLIP_FINDER_QUERY_LIMIT", "9"))))
    queries = queries[:query_limit]

    started = time.monotonic()
    completed_queries: list[str] = []
    warnings: list[str] = []
    sources: set[str] = set()
    last_candidate_time = started

    project["search_depth"] = "bounded_web_plus_optional_ytdlp"
    project["search_source"] = "youtube_web_primary_ytdlp_optional_api_metadata_only"

    def publish(message: str, completed: int, phase: str = "discovery", diagnostics: dict | None = None):
        elapsed = max(0.1, time.monotonic() - started)
        remaining_queries = max(0, len(queries) - completed)
        eta = int(remaining_queries * 18 + max(0, len(discovered)) * (0.04 if phase == "discovery" else 0.08))
        progress = {
            "completed": completed,
            "total": len(queries),
            "results": len(discovered),
            "candidate_update_serial": len(discovered),
            "estimated_seconds_remaining": max(2, eta),
            "message": message,
            "phase": phase,
            "elapsed_seconds": int(elapsed),
            "last_candidate_seconds_ago": int(max(0, time.monotonic() - last_candidate_time)),
            "sources_active": sorted(sources),
        }
        if diagnostics:
            progress["diagnostics"] = diagnostics
        _set_search_job(project_id, status="running", progress=progress)

    def merge_one(row: dict[str, Any], query: str) -> bool:
        nonlocal last_candidate_time
        video_id = str(row.get("video_id") or "").strip()
        if not video_id:
            return False
        previous = discovered.get(video_id, {})
        result = {
            **previous,
            **row,
            "result_id": previous.get("result_id") or str(uuid.uuid4()),
            "status": previous.get("status", "unreviewed") if previous.get("status") in {"approved", "rejected"} else "unreviewed",
            "notes": previous.get("notes", ""),
            "local_file_path": previous.get("local_file_path", ""),
            "clip_instances": previous.get("clip_instances", []),
            "query_matches": sorted(set(previous.get("query_matches", []) + [query])),
        }
        if not _player_relevant(result, player):
            return False
        result["suggestion_score"] = score_result(result, player, category)
        is_new = video_id not in discovered
        discovered[video_id] = result
        if is_new:
            last_candidate_time = time.monotonic()
        return is_new

    for index, query in enumerate(queries):
        before = len(discovered)
        publish(
            f'Searching YouTube {index + 1}/{len(queries)}: "{query}"',
            index,
            diagnostics={"query": query, "source": "youtube_web", "build": CLIP_FINDER_BUILD},
        )

        # Primary discovery: YouTube's public browser search and continuations.
        try:
            def web_progress(pages, _found, pending, done, extra):
                candidate = (extra or {}).get("candidate")
                if candidate:
                    merge_one(candidate, query)
                publish(
                    f'YouTube search {index + 1}/{len(queries)} · page {pages} · {len(discovered)} candidates',
                    index,
                    diagnostics={
                        "query": query, "source": "youtube_web", "page": pages,
                        "pending_pages": pending, "done": bool(done), "build": CLIP_FINDER_BUILD,
                    },
                )

            rows = _scrape_youtube_search(
                query,
                timeout=25,
                progress_callback=web_progress,
                max_pages_override=6 if index == 0 else 3,
                max_videos_override=700 if index == 0 else 300,
            )
            for row in rows:
                merge_one(row, query)
            if rows:
                sources.add("youtube_web")
                completed_queries.append(f"{query} [youtube_web]")
        except Exception as exc:
            warnings.append(f"{query} [youtube_web]: {exc}")

        # Optional independent supplement. It is strictly time-bounded so a
        # yt-dlp extraction can never freeze the entire Clip Finder job.
        try:
            import yt_dlp  # noqa: F401
            executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="clip-finder-ytdlp")
            try:
                future = executor.submit(
                    _search_with_ytdlp,
                    query,
                    max_results=160 if index == 0 else 80,
                    progress_callback=None,
                )
                rows = future.result(timeout=75)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
            for row in rows:
                merge_one(row, query)
            if rows:
                sources.add("yt_dlp")
                completed_queries.append(f"{query} [yt_dlp]")
        except ImportError:
            if index == 0:
                warnings.append("yt-dlp is not installed; browser discovery continued normally.")
        except Exception as exc:
            warnings.append(f"{query} [yt_dlp]: {exc}")

        publish(
            f'Finished {index + 1}/{len(queries)} · added {len(discovered) - before} · {len(discovered)} total',
            index + 1,
            diagnostics={"query": query, "source": "combined", "build": CLIP_FINDER_BUILD},
        )
        if len(discovered) >= 600 and index >= 3:
            break

    if not discovered:
        detail = " | ".join(warnings[-5:]) or "YouTube returned no discoverable videos."
        raise HTTPException(502, f"Clip Finder could not discover videos. {detail}")

    candidate_ids = list(discovered)
    publish(
        f"Verifying metadata for {len(candidate_ids)} videos",
        len(queries),
        phase="verification",
    )
    try:
        with _search_progress_heartbeat(project_id):
            _enrich_scraped_results(discovered, candidate_ids)
    except Exception as exc:
        warnings.append(f"Metadata enrichment: {exc}")

    publish(
        f"Inspecting video orientation for {len(discovered)} videos",
        len(queries),
        phase="orientation_check",
    )
    with _search_progress_heartbeat(project_id):
        _mark_embedded_portrait_results(discovered)

    publish(
        f"Filtering and ranking {len(discovered)} videos",
        len(queries),
        phase="filtering",
    )
    discovered = {
        video_id: result
        for video_id, result in discovered.items()
        if not result.get("portrait_crop_detected")
        and is_allowed_nba_game_result(result, player, category)
    }

    known_rich = _is_known_highlight_rich_player(player)
    highlight_rich = known_rich or len(discovered) >= 45
    if highlight_rich:
        stronger = {
            video_id: result
            for video_id, result in discovered.items()
            if not _is_generic_single_game_package(result, category)
            or result.get("status") in {"approved", "rejected"}
            or result.get("local_file_path")
        }
        if len(stronger) >= (20 if known_rich else 12):
            discovered = stronger

    for result in discovered.values():
        result["suggestion_score"] = score_result(result, player, category)

    project["highlight_rich_player"] = highlight_rich
    project["footage_profile"] = "highlight-rich" if highlight_rich else "footage-scarce"
    project["results"] = sorted(
        discovered.values(),
        key=lambda result: (result.get("suggestion_score", 0), int(result.get("views") or 0)),
        reverse=True,
    )
    project["queries_run"] = completed_queries
    project["query_pool_size"] = len(queries)
    project["query_execution_limit"] = len(queries)
    project["search_warnings"] = warnings[-25:]
    project["search_partial"] = not bool(sources)
    project["search_sources"] = sorted(sources)
    save_cf_project(project)

    return {
        "project": project,
        "new_count": max(0, len(discovered) - len(existing)),
        "total_count": len(discovered),
        "queries_run": len(completed_queries),
        "query_pool_size": len(queries),
        "search_warnings": warnings[-25:],
        "partial": not bool(sources),
        "search_sources": sorted(sources),
    }

def _search_worker(project_id: str):
    # The execution-state request remains active through long YouTube pacing
    # waits and metadata filtering. It is released in every completion, failure,
    # or cancellation path when this context exits.
    with _keep_computer_awake_during_search() as sleep_prevention_active:
        _set_search_job(project_id, sleep_prevention_active=sleep_prevention_active)
        try:
            _run_search_sync(project_id)
            _set_search_job(
                project_id,
                status="complete",
                error="",
                sleep_prevention_active=False,
                finished_at=now_iso(),
            )
        except Exception as exc:
            detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
            _set_search_job(
                project_id,
                status="failed",
                error=str(detail),
                sleep_prevention_active=False,
                finished_at=now_iso(),
            )


@router.post("/projects/{project_id}/search")
def start_search(project_id: str):
    # Validate before starting a background task so missing projects still return
    # a normal HTTP error immediately.
    project = load_project(project_id)
    current = _get_search_job(project_id)
    if current.get("status") in {"queued", "running"}:
        return {"accepted": True, "already_running": True, "job": current, "project": project, "clip_finder_build": CLIP_FINDER_BUILD}

    job = _set_search_job(
        project_id,
        status="queued",
        error="",
        started_at=now_iso(),
        finished_at=None,
    )

    def launch():
        _set_search_job(project_id, status="running")
        _search_worker(project_id)

    _SEARCH_EXECUTOR.submit(launch)
    return {"accepted": True, "already_running": False, "job": job, "project": project, "clip_finder_build": CLIP_FINDER_BUILD}


@router.get("/projects/{project_id}/search-status")
def search_status(project_id: str):
    project = load_project(project_id)
    job = _get_search_job(project_id)
    return {"job": job, "project": project, "clip_finder_build": CLIP_FINDER_BUILD}


@router.get("/runtime-info")
def clip_finder_runtime_info():
    return {
        "clip_finder_build": CLIP_FINDER_BUILD,
        "source_file": str(Path(__file__).resolve()),
        "discovery": ["youtube_web_continuations", "yt_dlp_optional"],
        "youtube_data_api_search_enabled": False,
        "source_mtime": Path(__file__).stat().st_mtime,
        "download_inbox_path": str(DOWNLOAD_INBOX_DIR),
        "download_inbox_automation": True,
        "download_inbox_exists": DOWNLOAD_INBOX_DIR.exists(),
    }


@router.get("/download-inbox")
def download_inbox_status():
    _ensure_download_watcher_started()
    pending = _process_download_inbox_once()
    files = []
    try:
        files = [
            {
                "name": path.name,
                "size_bytes": path.stat().st_size,
                "modified_at": path.stat().st_mtime,
            }
            for path in DOWNLOAD_INBOX_DIR.iterdir()
            if path.is_file()
        ]
    except OSError:
        files = []

    attached_project = None
    if pending and pending.get("status") == "attached" and pending.get("project_id"):
        try:
            attached_project = load_project(str(pending["project_id"]))
        except Exception:
            attached_project = None

    return {
        "inbox_path": str(DOWNLOAD_INBOX_DIR.resolve()),
        "pending": pending,
        "project": attached_project,
        "watcher_started": _DOWNLOAD_WATCHER_STARTED,
        "watcher_last_scan_at": _DOWNLOAD_WATCHER_LAST_SCAN_AT,
        "watcher_last_error": _DOWNLOAD_WATCHER_LAST_ERROR,
        "inbox_files": files,
        "clip_finder_build": CLIP_FINDER_BUILD,
    }


@router.post("/download-inbox/open")
def open_download_inbox():
    DOWNLOAD_INBOX_DIR.mkdir(parents=True, exist_ok=True)
    folder = str(DOWNLOAD_INBOX_DIR.resolve())
    try:
        if os.name == "nt":
            try:
                os.startfile(folder)  # type: ignore[attr-defined]
            except Exception:
                subprocess.Popen(["explorer.exe", folder], close_fds=True)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder], close_fds=True)
        else:
            subprocess.Popen(["xdg-open", folder], close_fds=True)
    except Exception as exc:
        raise HTTPException(500, f"Could not open the CourtVision Inbox folder: {exc}")
    return {"ok": True, "inbox_path": folder}


@router.post("/projects/{project_id}/download-inbox/begin")
def begin_inbox_download(project_id: str, payload: BeginDownloadRequest):
    _ensure_download_watcher_started()
    project = load_project(project_id)
    result = next((row for row in project.get("results", []) if row.get("result_id") == payload.result_id), None)
    if result is None:
        raise HTTPException(404, "Result not found")
    if result.get("status") != "approved":
        raise HTTPException(400, "Approve this video before downloading its source MP4")

    # Beginning a new download explicitly re-enables attachment for this source.
    with _RESET_ATTACHMENT_KEYS_LOCK:
        _RESET_ATTACHMENT_KEYS.discard((project_id, str(payload.result_id)))

    current = _read_pending_download()
    if current and current.get("status") in {"waiting", "detected", "attaching"}:
        same_target = current.get("project_id") == project_id and current.get("result_id") == payload.result_id
        if not same_target:
            raise HTTPException(409, "Another source video is already waiting for a download. Finish or cancel it first.")
    elif current:
        # A completed/failed/cancelled job must never poison the next source.
        _clear_pending_download()

    pending_id = str(uuid.uuid4())
    started_at = now_iso()
    started_epoch = time.time()
    baseline = _download_inbox_snapshot()
    result["attachment_session_id"] = pending_id
    result["download_status"] = "waiting"
    result["download_message"] = "Waiting for the MP4 download to finish…"
    result["download_error"] = ""
    result["download_started_at"] = started_at
    result["download_started_epoch"] = started_epoch
    result["download_updated_at"] = started_at
    result["download_baseline"] = baseline
    result.pop("attachment_reset_at", None)
    save_cf_project(project)

    pending = {
        "pending_id": pending_id,
        "project_id": project_id,
        "result_id": payload.result_id,
        "video_id": result.get("video_id"),
        "title": result.get("title"),
        "youtube_url": result.get("youtube_url"),
        "status": "waiting",
        "message": "Waiting for the MP4 download to finish…",
        "inbox_path": str(DOWNLOAD_INBOX_DIR),
        "baseline": baseline,
        "started_at": started_at,
        "started_epoch": started_epoch,
        "updated_at": started_at,
        "error": "",
    }
    _write_pending_download(pending)
    return {"pending": pending, "inbox_path": str(DOWNLOAD_INBOX_DIR), "project": project}


@router.post("/download-inbox/cancel")
def cancel_inbox_download():
    pending = _read_pending_download()
    if pending:
        project_id = str(pending.get("project_id") or "")
        result_id = str(pending.get("result_id") or "")
        if project_id and result_id:
            try:
                project = load_project(project_id)
                result = next((row for row in project.get("results", []) if str(row.get("result_id") or "") == result_id), None)
                if result is not None and not result.get("local_file_path"):
                    _clear_result_download_state(result, clear_session=True)
                    save_cf_project(project)
            except Exception:
                pass
        pending.update({"status": "cancelled", "message": "Pending download cancelled.", "updated_at": now_iso()})
    _clear_pending_download()
    return {"pending": None}


@router.post("/download-inbox/clear")
def clear_finished_inbox_download():
    pending = _read_pending_download()
    if pending and pending.get("status") in {"waiting", "detected", "attaching"}:
        raise HTTPException(409, "A download is still active")
    _clear_pending_download()
    return {"ok": True}


@router.patch("/projects/{project_id}/results/{result_id}")
def update_result(project_id: str, result_id: str, payload: ResultUpdate):
    project = load_project(project_id)
    result = next((r for r in project.get("results", []) if r.get("result_id") == result_id), None)
    if not result:
        raise HTTPException(404, "Result not found")
    if payload.status is not None:
        if payload.status not in {"unreviewed", "approved", "rejected"}:
            raise HTTPException(400, "Invalid review status")
        result["status"] = payload.status
    if payload.notes is not None:
        result["notes"] = payload.notes
    if payload.local_file_path is not None:
        path = os.path.abspath(os.path.expanduser(payload.local_file_path)) if payload.local_file_path else ""
        if path and not os.path.isfile(path):
            raise HTTPException(400, "Local video file was not found")
        result["local_file_path"] = path.replace("\\", "/")
        if path:
            result["attached_file_path"] = path.replace("\\", "/")
            result["attached_filename"] = Path(path).name
            result["attachment_status"] = "complete"
            result.pop("attachment_reset_at", None)
            _clear_result_download_state(result, clear_session=True)
        else:
            for key in ("attached_file_path", "attached_filename", "attachment_status"):
                result.pop(key, None)
            _clear_result_download_state(result, clear_session=True)
    if payload.clip_count is not None:
        if payload.clip_count < 1 or payload.clip_count > 30:
            raise HTTPException(400, "Clips from one video must be between 1 and 30")
        current = _normalize_instances(result)
        while len(current) < payload.clip_count:
            current.append({"instance_id": str(uuid.uuid4()), "label": f"Clip {len(current) + 1}", "notes": "", "rank_number": None})
        result["clip_instances"] = current[:payload.clip_count]
    if payload.clip_instances is not None:
        if not 1 <= len(payload.clip_instances) <= 30:
            raise HTTPException(400, "A video must contain between 1 and 30 clip instances")
        result["clip_instances"] = _normalize_instances({"clip_instances": payload.clip_instances})
    if payload.rank_number is not None:
        if payload.rank_number < 1 or payload.rank_number > 10:
            raise HTTPException(400, "Rank must be between 1 and 10")
        if result.get("status") != "approved" or not result.get("local_file_path"):
            raise HTTPException(400, "Approve and attach an MP4 before assigning a rank")
        instances = _normalize_instances(result)
        instances[0]["rank_number"] = payload.rank_number
        result["clip_instances"] = instances
        result["rank_number"] = payload.rank_number
    elif "rank_number" in getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set())):
        instances = _normalize_instances(result)
        instances[0]["rank_number"] = None
        result["clip_instances"] = instances
        result["rank_number"] = None
    if result.get("status") != "approved":
        instances = _normalize_instances(result)
        for instance in instances:
            instance["rank_number"] = None
        result["clip_instances"] = instances
        result["rank_number"] = None

    used = {}
    for row in project.get("results", []):
        for instance in _normalize_instances(row):
            rank = instance.get("rank_number")
            if rank is None:
                continue
            if rank in used and used[rank] != instance.get("instance_id"):
                raise HTTPException(400, f"Rank #{rank} is already assigned")
            used[rank] = instance.get("instance_id")
    save_cf_project(project)
    return {"project": project, "result": result}


@router.delete("/projects/{project_id}/results/{result_id}/attachment")
def delete_result_attachment(project_id: str, result_id: str):
    """Delete one managed source video and permanently reset its attachment state."""
    attachment_key = (project_id, result_id)

    # Serialize against the watcher. Once this lock is held, no in-flight scan can
    # save the same MP4 back after the reset response reaches the frontend.
    with _DOWNLOAD_PROCESS_LOCK:
        with _RESET_ATTACHMENT_KEYS_LOCK:
            _RESET_ATTACHMENT_KEYS.add(attachment_key)

        pending = _read_pending_download()
        if (
            pending
            and str(pending.get("project_id") or "") == project_id
            and str(pending.get("result_id") or "") == result_id
        ):
            _clear_pending_download()

        project = load_project(project_id)
        result = next(
            (row for row in project.get("results", []) if row.get("result_id") == result_id),
            None,
        )
        if result is None:
            raise HTTPException(404, "Result not found")

        raw_path = str(result.get("local_file_path") or "").strip()
        deleted_file = False
        if raw_path:
            candidate = Path(raw_path).expanduser()
            try:
                candidate_resolved = candidate.resolve(strict=False)
                attached_root = (DATA_DIR / "attached").resolve(strict=False)
                candidate_resolved.relative_to(attached_root)
            except (ValueError, OSError):
                # A stale or manually edited path must not prevent the source from
                # returning to its normal Download MP4 state. Do not delete it.
                candidate_resolved = None

            if candidate_resolved is not None:
                try:
                    if candidate_resolved.exists() and candidate_resolved.is_file():
                        candidate_resolved.unlink()
                        deleted_file = True
                except PermissionError as exc:
                    raise HTTPException(409, f"The video is currently in use and could not be deleted: {exc}")
                except OSError as exc:
                    raise HTTPException(500, f"Could not delete the attached video: {exc}")

        # Clear every known attachment field. Planning data remains untouched.
        for key in (
            "local_file_path",
            "download_attached_at",
            "attachment_status",
            "attached_original_filename",
            "attached_file_path",
            "attached_filename",
            "local_video_path",
            "media_path",
            "attachment_session_id",
        ):
            result.pop(key, None)
        _clear_result_download_state(result, clear_session=True)
        result["attachment_reset_at"] = now_iso()

        result["clip_instances"] = _normalize_instances(result)
        save_cf_project(project)

        # Reload from disk and verify the durable source of truth is reset.
        saved_project = load_project(project_id)
        saved_result = next(
            (row for row in saved_project.get("results", []) if row.get("result_id") == result_id),
            None,
        )
        if saved_result is None:
            raise HTTPException(500, "The source disappeared while saving the reset")
        for key in (
            "local_file_path",
            "attachment_status",
            "attached_file_path",
            "local_video_path",
            "media_path",
            "attachment_session_id",
        ):
            saved_result.pop(key, None)
        _clear_result_download_state(saved_result, clear_session=True)
        saved_result["attachment_reset_at"] = saved_result.get("attachment_reset_at") or now_iso()
        save_cf_project(saved_project)

    return {
        "project": saved_project,
        "result": saved_result,
        "deleted_file": deleted_file,
        "reset": True,
        "message": "Local MP4 removed. This source is ready to download again.",
    }


@router.post("/projects/{project_id}/results/{result_id}/attachment/open-location")
def open_result_attachment_location(project_id: str, result_id: str):
    """Open the permanent managed folder containing the attached source video."""
    return _open_result_attachment_location(project_id, result_id)


@router.post("/open-attached-location")
def open_attached_location(request: OpenAttachmentLocationRequest):
    """Stable non-dynamic endpoint used by the Clip Finder interface."""
    return _open_result_attachment_location(request.project_id, request.result_id)


def _find_managed_attachment(project_id: str, result: dict[str, Any]) -> Optional[Path]:
    """Resolve the saved attachment and recover from an older stale absolute path."""
    attached_root = (DATA_DIR / "attached").resolve(strict=False)
    project_folder = (attached_root / project_id).resolve(strict=False)

    raw_candidates = [
        result.get("local_file_path"),
        result.get("attached_file_path"),
        result.get("local_video_path"),
        result.get("media_path"),
    ]
    for raw_path in raw_candidates:
        if not str(raw_path or "").strip():
            continue
        candidate = Path(str(raw_path)).expanduser().resolve(strict=False)
        try:
            candidate.relative_to(attached_root)
        except (ValueError, OSError):
            continue
        if candidate.exists() and candidate.is_file():
            return candidate

    if not project_folder.exists() or not project_folder.is_dir():
        return None

    media_extensions = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    files = [path for path in project_folder.iterdir() if path.is_file() and path.suffix.lower() in media_extensions]
    if not files:
        return None

    saved_names = {
        Path(str(value)).name.lower()
        for value in (
            result.get("local_file_path"),
            result.get("attached_file_path"),
            result.get("attached_filename"),
            result.get("attached_original_filename"),
        )
        if str(value or "").strip()
    }
    for candidate in files:
        if candidate.name.lower() in saved_names:
            return candidate.resolve(strict=False)

    video_id = str(result.get("video_id") or "").strip().lower()
    if video_id:
        matching = [candidate for candidate in files if video_id in candidate.name.lower()]
        if matching:
            return max(matching, key=lambda path: path.stat().st_mtime).resolve(strict=False)

    return None


def _open_result_attachment_location(project_id: str, result_id: str):
    project = load_project(project_id)
    result = next(
        (row for row in project.get("results", []) if row.get("result_id") == result_id),
        None,
    )
    if result is None:
        raise HTTPException(404, "Source not found")

    project_folder = (DATA_DIR / "attached" / project_id).resolve(strict=False)
    project_folder.mkdir(parents=True, exist_ok=True)
    candidate = _find_managed_attachment(project_id, result)

    # Always open the permanent sorted folder. Older records may point to files
    # the user manually removed; opening the folder is still useful and must not
    # produce a misleading route-level Not Found error.
    try:
        if os.name == "nt":
            os.startfile(str(project_folder))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(project_folder)], close_fds=True)
        else:
            subprocess.Popen(["xdg-open", str(project_folder)], close_fds=True)
    except Exception as exc:
        raise HTTPException(500, f"Could not open the sorted MP4 folder: {exc}")

    if candidate is not None and str(result.get("local_file_path") or "") != str(candidate):
        result["local_file_path"] = str(candidate).replace("\\", "/")
        result["attached_file_path"] = str(candidate).replace("\\", "/")
        result["attached_filename"] = candidate.name
        result["attachment_status"] = "complete"
        save_cf_project(project)

    return {
        "ok": True,
        "file_exists": candidate is not None,
        "file_path": str(candidate) if candidate is not None else "",
        "folder_path": str(project_folder),
    }


@router.post("/projects/{project_id}/results/{result_id}/attach")
async def attach_file(project_id: str, result_id: str, file: UploadFile = File(...)):
    project = load_project(project_id)
    result = next((r for r in project.get("results", []) if r.get("result_id") == result_id), None)
    if not result:
        raise HTTPException(404, "Result not found")
    folder = DATA_DIR / "attached" / project_id
    folder.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "clip.mp4").suffix.lower()
    if ext not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
        raise HTTPException(400, "Unsupported video type")
    destination = folder / f"{result['video_id']}_{uuid.uuid4().hex[:8]}{ext}"
    with destination.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    attached_path = str(destination).replace("\\", "/")
    result["local_file_path"] = attached_path
    result["attached_file_path"] = attached_path
    result["attached_filename"] = destination.name
    result["attachment_status"] = "complete"
    result.pop("attachment_reset_at", None)
    _clear_result_download_state(result, clear_session=True)
    save_cf_project(project)
    return {"project": project, "result": result}


def _normalize_match_text(value: str) -> str:
    value = os.path.splitext(os.path.basename(value or ""))[0].lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return " ".join(value.split())


def _best_file_match(filename: str, candidates: list[dict]) -> Optional[dict]:
    normalized = _normalize_match_text(filename)
    if not normalized:
        return None
    for candidate in candidates:
        video_id = str(candidate.get("video_id") or "").lower()
        if video_id and video_id in filename.lower():
            return candidate
    scored = []
    for candidate in candidates:
        title = _normalize_match_text(candidate.get("title") or "")
        ratio = SequenceMatcher(None, normalized, title).ratio()
        overlap = len(set(normalized.split()) & set(title.split()))
        scored.append((ratio + min(0.35, overlap * 0.05), candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] >= 0.35 else None


@router.post("/projects/{project_id}/attach-batch")
async def attach_batch(project_id: str, files: List[UploadFile] = File(...)):
    project = load_project(project_id)
    candidates = [
        result for result in project.get("results", [])
        if result.get("status") == "approved" and not result.get("local_file_path")
    ]
    if not candidates:
        raise HTTPException(400, "There are no approved results waiting for files")

    folder = DATA_DIR / "attached" / project_id
    folder.mkdir(parents=True, exist_ok=True)
    matched = []
    unmatched = []

    for upload in files:
        filename = upload.filename or "clip.mp4"
        ext = Path(filename).suffix.lower()
        if ext not in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
            unmatched.append(filename)
            continue
        result = _best_file_match(filename, candidates)
        if result is None:
            unmatched.append(filename)
            continue
        destination = folder / f"{result['video_id']}_{uuid.uuid4().hex[:8]}{ext}"
        with destination.open("wb") as out:
            shutil.copyfileobj(upload.file, out)
        attached_path = str(destination).replace("\\", "/")
        result["local_file_path"] = attached_path
        result["attached_file_path"] = attached_path
        result["attached_filename"] = destination.name
        result["attachment_status"] = "complete"
        result.pop("attachment_reset_at", None)
        _clear_result_download_state(result, clear_session=True)
        result["attached_original_filename"] = filename
        matched.append({"filename": filename, "result_id": result["result_id"]})
        candidates = [item for item in candidates if item.get("result_id") != result.get("result_id")]

    save_cf_project(project)
    return {"project": project, "matched": matched, "unmatched": unmatched}


def _make_editor_clip(editor_id: str, result: dict, index: int, copy_source: bool = True, instance: Optional[dict] = None) -> dict:
    source = str(result.get("local_file_path") or "").replace("/", os.sep)
    if not source or not os.path.isfile(source):
        raise HTTPException(400, f"Missing local file for {result.get('title')}")
    ext = os.path.splitext(source)[1].lower() or ".mp4"
    if copy_source:
        editor_folder = os.path.join(CLIPS_DIR, editor_id)
        os.makedirs(editor_folder, exist_ok=True)
        stored = f"{index}_{uuid.uuid4().hex}{ext}"
        dest = os.path.join(editor_folder, stored)
        shutil.copy2(source, dest)
    else:
        stored = os.path.basename(source)
        dest = source
    instance = instance or _normalize_instances(result)[0]
    return {
        "clip_id": str(uuid.uuid4()),
        "original_filename": os.path.basename(source),
        "stored_filename": stored,
        "title": f"{result.get('title', f'Clip {index}')} — {instance.get('label', f'Clip {index}')}",
        "file_path": dest.replace("\\", "/"),
        "preview_url": f"/content-studio/preview/{editor_id}/{stored}" if copy_source else "",
        "order": index,
        "trim_start": 0.0,
        "trim_end": 0.0,
        "duration_seconds": get_video_duration_seconds(dest),
        "source_fps": get_video_fps(dest),
        "selected_for_top10": bool(instance.get("rank_number")),
        "metadata": generate_metadata(result.get("title", ""), "solo"),
        "source_url": result.get("youtube_url", ""),
        "clip_finder_result_id": result.get("result_id"),
        "clip_finder_rank": instance.get("rank_number"),
        "clip_finder_instance_id": instance.get("instance_id"),
        "clip_finder_instance_label": instance.get("label"),
        "clip_finder_notes": instance.get("notes", ""),
    }


def _base_render_settings(project_type: str) -> dict:
    return {
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
        "number_overlay_files": "backend/assets/countdown/10.png through 1.png",
    }


@router.post("/projects/{project_id}/build-candidate-editor-project")
def build_candidate_editor_project(project_id: str):
    project = load_project(project_id)
    unreviewed = [r for r in project.get("results", []) if r.get("status") not in {"approved", "rejected"}]
    if unreviewed:
        raise HTTPException(400, f"Review all videos first. {len(unreviewed)} remain")
    approved_results = [
        result for result in project.get("results", [])
        if result.get("status") == "approved"
    ]
    if not approved_results:
        raise HTTPException(400, "Approve at least one source video before opening the editor")

    missing = []
    for result in approved_results:
        local_path = str(result.get("local_file_path") or "").strip()
        if not local_path or not Path(local_path.replace("/", os.sep)).is_file():
            missing.append(result)
    if missing:
        raise HTTPException(
            400,
            f"Attach every approved source MP4 before opening the editor. {len(missing)} of {len(approved_results)} approved source files are missing.",
        )

    approved = approved_results

    editor_id = str(uuid.uuid4())
    clips = []
    index = 1
    for result in approved:
        for instance in _normalize_instances(result):
            clips.append(_make_editor_clip(editor_id, result, index, instance=instance))
            index += 1
    name = f"{project['player_name']} {project['category']} — Candidate Review"
    editor_project = {
        "project_id": editor_id,
        "project_type": "top10_candidates",
        "project_name": name,
        "project_group": f"{project['player_name']} — {project['category']}",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "clip_count": len(clips),
        "clips": clips,
        "top10_draft": generate_metadata(name, "top10"),
        "solo_draft": None,
        "status": "draft",
        "preview_confirmed": False,
        "render_status": "not_rendered",
        "rendered_video": None,
        "render_settings": _base_render_settings("top10"),
        "templates": get_template_status(),
        "clip_finder_project_id": project_id,
        "clip_finder_stage": "candidate_review",
    }
    save_project(editor_project)
    project["candidate_editor_project_id"] = editor_id
    save_cf_project(project)
    return {"project": project, "editor_project": editor_project}


@router.put("/projects/{project_id}/ranking")
def save_ranking(project_id: str, payload: RankingUpdate):
    project = load_project(project_id)
    approved_ids = {r["result_id"] for r in project.get("results", []) if r.get("status") == "approved"}
    project["ranking"] = [rid for rid in payload.ranked_result_ids if rid in approved_ids]
    save_cf_project(project)
    return {"project": project}


@router.post("/projects/{project_id}/build-editor-project")
def build_editor_project(project_id: str):
    project = load_project(project_id)
    valid_results = [r for r in project.get("results", []) if is_allowed_nba_game_result(r)]
    unreviewed = [r for r in valid_results if r.get("status") not in {"approved", "rejected"}]
    if unreviewed:
        raise HTTPException(400, f"Review all videos before building. {len(unreviewed)} remain")

    ranked = []
    for result in valid_results:
        if result.get("status") != "approved" or not result.get("local_file_path"):
            continue
        for instance in _normalize_instances(result):
            rank = instance.get("rank_number")
            if isinstance(rank, int) and 1 <= rank <= 10:
                ranked.append((result, instance))
    rank_numbers = [instance["rank_number"] for _, instance in ranked]
    if len(ranked) != 10 or set(rank_numbers) != set(range(1, 11)):
        raise HTTPException(400, "Assign every rank from 1 through 10 exactly once and attach each ranked source MP4")

    # Timeline order is #10 through #1. A source video may appear more than once.
    ranked.sort(key=lambda pair: pair[1]["rank_number"], reverse=True)
    editor_id = str(uuid.uuid4())
    clips = [_make_editor_clip(editor_id, result, index, instance=instance) for index, (result, instance) in enumerate(ranked, start=1)]
    name = f"{project['player_name']} {project['category']}"
    project_group = f"{project['player_name']} — {project['category']}"
    editor_project = {
        "project_id": editor_id,
        "project_type": "top10",
        "project_name": name,
        "project_group": project_group,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "clip_count": 10,
        "clips": clips,
        "top10_draft": generate_metadata(name, "top10"),
        "solo_draft": None,
        "status": "draft",
        "preview_confirmed": False,
        "render_status": "not_rendered",
        "rendered_video": None,
        "render_settings": _base_render_settings("top10"),
        "templates": get_template_status(),
        "clip_finder_project_id": project_id,
        "clip_finder_stage": "final_top10",
        "locked_rank_order": [instance["rank_number"] for _, instance in ranked],
    }
    save_project(editor_project)

    solo_project_ids = []
    for result, instance in ranked:
        solo_id = str(uuid.uuid4())
        solo_clip = _make_editor_clip(solo_id, result, 1, instance=instance)
        solo_name = f"{project['player_name']} — #{instance['rank_number']} — {instance.get('label', 'Solo Clip')}"
        solo_project = {
            "project_id": solo_id,
            "project_type": "solo",
            "project_name": solo_name,
            "project_group": project_group,
            "project_subgroup": "Solo Clips",
            "parent_top10_project_id": editor_id,
            "created_at": now_iso(),
            "updated_at": now_iso(),
            "clip_count": 1,
            "clips": [solo_clip],
            "top10_draft": None,
            "solo_draft": generate_metadata(result.get("title", ""), "solo"),
            "status": "draft",
            "preview_confirmed": False,
            "render_status": "not_rendered",
            "rendered_video": None,
            "render_settings": _base_render_settings("solo"),
            "templates": get_template_status(),
            "clip_finder_project_id": project_id,
            "clip_finder_result_id": result.get("result_id"),
            "clip_finder_rank": instance.get("rank_number"),
            "clip_finder_instance_id": instance.get("instance_id"),
            "clip_finder_notes": instance.get("notes", ""),
            "source_url": result.get("youtube_url", ""),
        }
        save_project(solo_project)
        solo_project_ids.append(solo_id)

    project["editor_project_id"] = editor_id
    project["solo_project_ids"] = solo_project_ids
    project["ranking_locked_at"] = now_iso()
    project["ranking"] = [instance["instance_id"] for _, instance in ranked]
    save_cf_project(project)
    return {
        "project": project,
        "editor_project": editor_project,
        "solo_project_ids": solo_project_ids,
        "message": "Final Top 10 and 10 reviewable solo projects created. Nothing was rendered or uploaded.",
    }

