from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
import json
import mimetypes
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional


from routes.content_studio import PROJECTS_DIR, THUMBNAILS_DIR, ensure_content_studio_folders, load_project, save_project

router = APIRouter()

BASE_DIR = Path("uploads") / "content_studio" / "thumbnail_builder"
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".psd"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
TEMPLATE_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "thumbnail_templates"
FONT_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
DEFAULT_TEMPLATE_CACHE = BASE_DIR / "default_templates"


def _walk_psd_layers(container):
    for layer in container:
        yield layer
        try:
            if layer.is_group():
                yield from _walk_psd_layers(layer)
        except Exception:
            continue


def _psd_text_metadata(psd) -> list[dict]:
    layers = []
    for index, layer in enumerate(_walk_psd_layers(psd)):
        if str(getattr(layer, "kind", "")).lower() != "type":
            continue
        try:
            text = str(getattr(layer, "text", "") or "").strip()
        except Exception:
            text = ""
        bbox = getattr(layer, "bbox", None)
        left = int(getattr(bbox, "x1", 0) or 0)
        top = int(getattr(bbox, "y1", 0) or 0)
        width = max(1, int((getattr(bbox, "x2", left) or left) - left))
        height = max(1, int((getattr(bbox, "y2", top) or top) - top))
        font_size = max(18, min(180, int(height * 0.82)))
        font_family = "LEMON MILK"
        font_style = "italic"
        font_weight = 900
        try:
            engine = getattr(layer, "engine_dict", None) or {}
            style_run = engine.get("StyleRun", {}) if isinstance(engine, dict) else {}
            run_data = style_run.get("RunArray", []) if isinstance(style_run, dict) else []
            if run_data:
                sheet = (run_data[0].get("StyleSheet", {}) or {}).get("StyleSheetData", {}) or {}
                size_value = sheet.get("FontSize")
                if size_value:
                    font_size = max(18, min(180, int(float(size_value))))
        except Exception:
            pass
        layers.append({
            "key": f"line{len(layers) + 1}",
            "layer_name": str(getattr(layer, "name", "") or f"Line {len(layers) + 1}"),
            "label": f"Line {len(layers) + 1}",
            "text": text,
            "x": left,
            "y": top,
            "width": width,
            "height": height,
            "font_size": font_size,
            "font_family": font_family,
            "font_weight": font_weight,
            "font_style": font_style,
            "gradient_start": "#ffffff",
            "gradient_end": "#d7d7d7",
            "align": "left"
        })
        if len(layers) == 4:
            break
    return layers


def _ensure_dirs():
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    TEMPLATE_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    FONT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    DEFAULT_TEMPLATE_CACHE.mkdir(parents=True, exist_ok=True)


def _make_template_background_transparent(image):
    """Remove only the near-white background connected to the canvas edges.

    The supplied PSD templates contain an opaque white canvas. Keeping that
    canvas in the exported overlay hides the NBA source image in the browser.
    Flood-filling from the edges removes the background without deleting
    enclosed light artwork inside the template design.
    """
    from collections import deque

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    visited = bytearray(width * height)
    queue = deque()

    def is_background(x, y):
        red, green, blue, alpha = pixels[x, y]
        return alpha > 0 and red >= 242 and green >= 242 and blue >= 242

    def enqueue(x, y):
        index = y * width + x
        if visited[index] or not is_background(x, y):
            return
        visited[index] = 1
        queue.append((x, y))

    for x in range(width):
        enqueue(x, 0)
        enqueue(x, height - 1)
    for y in range(height):
        enqueue(0, y)
        enqueue(width - 1, y)

    while queue:
        x, y = queue.popleft()
        red, green, blue, _ = pixels[x, y]
        pixels[x, y] = (red, green, blue, 0)
        if x > 0:
            enqueue(x - 1, y)
        if x + 1 < width:
            enqueue(x + 1, y)
        if y > 0:
            enqueue(x, y - 1)
        if y + 1 < height:
            enqueue(x, y + 1)

    return rgba


def _project_template_key(project_type: str) -> str:
    return "top10" if str(project_type or "").lower() == "top10" else "solo-highlight"


def _default_text_layers(project_type: str) -> list[dict]:
    """Return the permanent Solo Highlight text design; Top 10 has no text."""
    if _project_template_key(project_type) == "top10":
        return []
    sizes = [94, 94, 69, 47]
    gaps = [8, 8, 8]
    vertical_scale = 1.19
    y_positions = [0]
    for index, gap in enumerate(gaps):
        y_positions.append(y_positions[index] + int((sizes[index] * vertical_scale) + 0.9999) + gap)
    return [
        {"key": "line1", "label": "Line 1", "text": "PLAYER", "x": 0, "y": y_positions[0], "font_size": sizes[0], "min_font_size": 48, "max_width": 430, "gradient_start": "#ffffff", "gradient_end": "#eeeeee", "align": "center", "vertical_scale": vertical_scale},
        {"key": "line2", "label": "Line 2", "text": "NAME", "x": 0, "y": y_positions[1], "font_size": sizes[1], "min_font_size": 48, "max_width": 430, "gradient_start": "#ffffff", "gradient_end": "#eeeeee", "align": "center", "vertical_scale": vertical_scale},
        {"key": "line3", "label": "Line 3", "text": "HIGHLIGHT", "x": 0, "y": y_positions[2], "font_size": sizes[2], "min_font_size": 38, "max_width": 470, "gradient_start": "#ffe733", "gradient_end": "#f28a00", "align": "center", "vertical_scale": vertical_scale},
        {"key": "line4", "label": "Line 4", "text": "VS OPPONENT", "x": 0, "y": y_positions[3], "font_size": sizes[3], "min_font_size": 28, "max_width": 440, "gradient_start": "#ffffff", "gradient_end": "#eeeeee", "align": "center", "vertical_scale": vertical_scale},
    ]


def _render_default_template(project_type: str) -> Optional[dict]:
    """Render the selected template from its PSD source.

    Solo Highlight remains PSD-first so CourtVision can read the four text
    layers. The browser never receives the PSD directly; the backend creates a
    transparent PNG overlay with those type layers hidden, then the frontend
    renders editable replacement text from the extracted metadata.
    """
    _ensure_dirs()
    key = _project_template_key(project_type)

    psd_candidates = [
        TEMPLATE_ASSETS_DIR / f"{key}-template.psd",
        TEMPLATE_ASSETS_DIR / f"{key}.psd",
    ]
    png_candidates = (
        [TEMPLATE_ASSETS_DIR / "templatenowords.png"] if key == "solo-highlight" else []
    ) + [
        TEMPLATE_ASSETS_DIR / f"{key}-template.png",
        TEMPLATE_ASSETS_DIR / f"{key}.png",
    ]
    psd_source = next((item for item in psd_candidates if item.exists()), None)
    png_source = next((item for item in png_candidates if item.exists()), None)
    if not psd_source and not png_source:
        return None

    text_layers = []
    output = png_source
    source_mtime = png_source.stat().st_mtime if png_source else 0

    # The dedicated text-free PNG is the authoritative Solo Highlight overlay.
    # It is already transparent and must be returned without PSD compositing or
    # background removal. Other formats retain the existing PSD-first behavior.
    use_text_free_png = key == "solo-highlight" and png_source and png_source.name.lower() == "templatenowords.png"

    if psd_source and not use_text_free_png:
        source_mtime = psd_source.stat().st_mtime
        metadata_path = DEFAULT_TEMPLATE_CACHE / f"{key}-template-text.json"
        output = DEFAULT_TEMPLATE_CACHE / f"{key}-template-transparent-overlay-v2.png"
        try:
            from psd_tools import PSDImage

            refresh_metadata = not metadata_path.exists() or metadata_path.stat().st_mtime < source_mtime
            refresh_overlay = not output.exists() or output.stat().st_mtime < source_mtime
            psd = PSDImage.open(psd_source)

            if refresh_metadata:
                text_layers = _psd_text_metadata(psd)
                metadata_path.write_text(json.dumps(text_layers, indent=2), encoding="utf-8")
            else:
                text_layers = json.loads(metadata_path.read_text(encoding="utf-8"))

            if refresh_overlay:
                hidden_layers = []
                for layer in _walk_psd_layers(psd):
                    if str(getattr(layer, "kind", "")).lower() == "type":
                        hidden_layers.append((layer, bool(getattr(layer, "visible", True))))
                        layer.visible = False
                try:
                    overlay = psd.composite(force=True)
                    if overlay is None:
                        raise RuntimeError("PSD composite returned no image")
                    overlay = _make_template_background_transparent(overlay)
                    overlay.save(output, "PNG")
                finally:
                    for layer, was_visible in hidden_layers:
                        layer.visible = was_visible
        except Exception as error:
            return {
                "error": f"PSD template could not be rendered: {error}",
                "source_path": str(psd_source),
            }

    if not output or not output.exists():
        return None
    if len(text_layers) < 4:
        text_layers = _default_text_layers(project_type)

    return {
        "filename": output.name,
        "file_path": str(output.resolve()),
        "preview_url": f"/thumbnail-builder/default-template/{key}",
        "source_filename": output.name if use_text_free_png else (psd_source.name if psd_source else output.name),
        "is_default": True,
        "is_psd": bool(psd_source and not use_text_free_png),
        "text_free": bool(use_text_free_png or psd_source),
        "text_layers": text_layers[:4],
        "source_mtime": source_mtime,
    }

def _apply_default_template(project: dict, workspace: dict) -> dict:
    """Apply the permanent project-type-specific Thumbnail Builder layout."""
    project_type = str(project.get("project_type") or "").lower()
    is_top10 = project_type == "top10"

    # The project format is authoritative. Always refresh the matching locked
    # overlay so stale workspaces cannot substitute a different template.
    default_template = _render_default_template(project_type)
    if default_template:
        workspace["default_template"] = default_template

    canvas = workspace.setdefault("canvas", {"scale": 1, "x": 0, "y": 0, "text_layers": []})

    if is_top10:
        # Top 10 thumbnails are deliberately image-only beneath the permanent
        # logo/template overlay. Never revive stale Solo Highlight text layers.
        canvas["text_layers"] = []
        canvas.pop("text_offset_x", None)
        canvas.pop("text_offset_y", None)
        canvas["text_template_version"] = "top10-image-only-v1"
        return workspace

    layers = canvas.get("text_layers") if isinstance(canvas.get("text_layers"), list) else []
    defaults = _default_text_layers("solo")
    merged_layers = []
    for index, default_layer in enumerate(defaults):
        previous = layers[index] if index < len(layers) and isinstance(layers[index], dict) else {}
        merged = dict(default_layer)
        # Preserve only the project's editable wording. The exact current Solo
        # Highlight template controls every visual property and line position.
        if "text" in previous:
            merged["text"] = str(previous.get("text") or "")
        merged_layers.append(merged)

    canvas["text_layers"] = merged_layers
    canvas["text_group_x"] = 270
    canvas["text_group_y"] = 54
    canvas["text_group_rotation"] = -6.0
    canvas["text_offset_x"] = max(-20, min(720, float(canvas.get("text_offset_x") or 0)))
    canvas["text_offset_y"] = max(-20, min(245, float(canvas.get("text_offset_y") or 0)))
    canvas["text_template_version"] = "solo-permanent-four-line-v5"
    return workspace


def _safe_filename(name: str, fallback: str = "image.png") -> str:
    raw = os.path.basename(str(name or fallback))
    stem, ext = os.path.splitext(raw)
    ext = ext.lower() if ext.lower() in ALLOWED_IMAGE_EXTENSIONS else ".png"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._") or "image"
    return f"{stem[:80]}{ext}"


def _project_dir(project_id: str) -> Path:
    folder = BASE_DIR / project_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "sources").mkdir(exist_ok=True)
    (folder / "versions").mkdir(exist_ok=True)
    (folder / "templates").mkdir(exist_ok=True)
    (folder / "finals").mkdir(exist_ok=True)
    return folder


def _workspace_path(project_id: str) -> Path:
    return _project_dir(project_id) / "workspace.json"


def _load_workspace(project_id: str) -> dict:
    path = _workspace_path(project_id)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "project_id": project_id,
        "source": None,
        "template": None,
        "versions": [],
        "final": None,
        "canvas": {
            "scale": 1,
            "x": 0,
            "y": 0,
            "text_layers": [
                {"key": "line1", "label": "Top line", "text": "", "x": 70, "y": 430, "font_size": 66},
                {"key": "line2", "label": "Main line", "text": "", "x": 70, "y": 500, "font_size": 92},
                {"key": "line3", "label": "Bottom line", "text": "", "x": 70, "y": 600, "font_size": 58},
                {"key": "accent", "label": "Accent line", "text": "", "x": 70, "y": 665, "font_size": 38}
            ]
        },
        "updated_at": datetime.now().isoformat(timespec="seconds")
    }


def _save_workspace(project_id: str, workspace: dict) -> dict:
    workspace["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _workspace_path(project_id).write_text(json.dumps(workspace, indent=2), encoding="utf-8")
    return workspace


def _preview_url(project_id: str, category: str, filename: str) -> str:
    return f"/thumbnail-builder/file/{project_id}/{category}/{filename}"


def _error(code: str, message: str, resolution: str, technical: str = "", status: int = 400):
    raise HTTPException(status_code=status, detail={
        "ok": False,
        "code": code,
        "message": message,
        "resolution": resolution,
        "technical_detail": technical
    })


def _write_upload(upload: UploadFile, destination: Path):
    extension = Path(upload.filename or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        _error(
            "thumbnail_invalid_format",
            "CourtVision could not use that image format.",
            "Choose a PNG, JPG, JPEG, or WEBP image and try again.",
            f"Unsupported extension: {extension or '(none)'}"
        )
    with destination.open("wb") as target:
        shutil.copyfileobj(upload.file, target)
    if destination.stat().st_size > MAX_IMAGE_BYTES:
        destination.unlink(missing_ok=True)
        _error(
            "thumbnail_file_too_large",
            "The source image is too large for Thumbnail Builder.",
            "Use an image smaller than 50 MB, then try again.",
            f"File size: {destination.stat().st_size if destination.exists() else 'over limit'} bytes"
        )


@router.get("/thumbnail-builder/settings")
def thumbnail_builder_settings():
    """Return the saved Thumbnail Builder configuration required at startup.

    This route intentionally returns only masked key metadata; it never exposes
    the stored API key to the browser. Missing or malformed settings safely fall
    back to the program defaults instead of failing CourtVision startup.
    """
    settings_file = Path("backend") / ".courtvision_thumbnail_settings.json"
    data = {"model": "gpt-image-2", "quality": "high", "api_key": ""}

    if settings_file.exists():
        try:
            saved = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(saved)
        except (OSError, ValueError, TypeError):
            # A damaged optional settings file should not block the application.
            pass

    env_key = str(os.getenv("OPENAI_API_KEY") or "").strip()
    key = env_key or str(data.get("api_key") or "").strip()
    model = str(data.get("model") or "gpt-image-2")
    quality = str(data.get("quality") or "high")

    return {
        "ok": True,
        "settings": {
            "model": model,
            "quality": quality,
            "has_api_key": bool(key),
            "masked_api_key": f"••••{key[-4:]}" if len(key) >= 4 else ("Saved" if key else ""),
        },
    }


@router.get("/thumbnail-builder/projects")
def thumbnail_builder_projects():
    """Return the same active editor projects shown by Content Studio.

    Workspace/template initialization is intentionally isolated from project
    discovery. A missing or malformed Thumbnail Builder workspace must never
    make a valid saved editor project disappear from this list.
    """
    ensure_content_studio_folders()
    _ensure_dirs()

    projects = []
    for filename in os.listdir(PROJECTS_DIR):
        if not filename.lower().endswith(".json"):
            continue

        path = os.path.join(PROJECTS_DIR, filename)
        try:
            with open(path, "r", encoding="utf-8") as source:
                project = json.load(source)
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(project, dict) or project.get("trashed"):
            continue

        # Older projects can be missing project_id even though the filename is
        # authoritative. Using the stem keeps them selectable without altering
        # the saved editor project on disk.
        project_id = str(project.get("project_id") or Path(filename).stem).strip()
        if not project_id:
            continue

        workspace_error = None
        try:
            workspace = _load_workspace(project_id)
            workspace = _apply_default_template(project, workspace)
        except Exception as error:
            # The project must still be visible. The workspace will be created
            # normally when the user selects/uploads an image for this project.
            workspace = {
                "project_id": project_id,
                "source": None,
                "template": None,
                "versions": [],
                "final": None,
            }
            workspace_error = str(error)

        item = {
            "project_id": project_id,
            "project_name": project.get("project_name") or "Untitled Project",
            "project_type": project.get("project_type") or "solo-highlight",
            "updated_at": project.get("updated_at") or project.get("created_at") or "",
            "created_at": project.get("created_at") or "",
            "thumbnail": project.get("thumbnail"),
            "clips": project.get("clips") or [],
            "workspace": workspace,
        }
        if workspace_error:
            item["workspace_warning"] = workspace_error
        projects.append(item)

    projects.sort(key=lambda item: item.get("updated_at", ""), reverse=True)
    return {"ok": True, "projects": projects}


@router.get("/thumbnail-builder/project/{project_id}")
def get_thumbnail_workspace(project_id: str):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Return to Saved Projects and choose an existing project.", project_id, 404)
    return {"ok": True, "project": project, "workspace": _apply_default_template(project, _load_workspace(project_id))}


@router.post("/thumbnail-builder/project/{project_id}/source")
async def upload_thumbnail_source(project_id: str, image: UploadFile = File(...)):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Choose an existing saved project and try again.", project_id, 404)
    folder = _project_dir(project_id)
    filename = f"source-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_safe_filename(image.filename)}"
    destination = folder / "sources" / filename
    _write_upload(image, destination)
    workspace = _load_workspace(project_id)
    workspace["source"] = {
        "filename": filename,
        "file_path": str(destination),
        "preview_url": _preview_url(project_id, "sources", filename),
        "created_at": datetime.now().isoformat(timespec="seconds")
    }
    workspace["versions"] = []
    workspace["selected_version_id"] = ""
    _save_workspace(project_id, workspace)
    return {"ok": True, "message": "Source image added.", "workspace": _apply_default_template(project, workspace)}


@router.delete("/thumbnail-builder/project/{project_id}/source")
def remove_thumbnail_source(project_id: str):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Choose an existing saved project and try again.", project_id, 404)
    workspace = _load_workspace(project_id)
    for item in [workspace.get("source"), *(workspace.get("versions") or [])]:
        if not isinstance(item, dict):
            continue
        path = Path(item.get("file_path", ""))
        try:
            if path.exists() and _project_dir(project_id) in path.resolve().parents:
                path.unlink(missing_ok=True)
        except Exception:
            pass
    workspace["source"] = None
    workspace["versions"] = []
    workspace["selected_version_id"] = ""
    workspace = _apply_default_template(project, workspace)
    _save_workspace(project_id, workspace)
    return {"ok": True, "message": "Source photo removed.", "workspace": workspace}


@router.post("/thumbnail-builder/project/{project_id}/template")
async def upload_thumbnail_template(project_id: str, image: UploadFile = File(...)):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Choose an existing saved project and try again.", project_id, 404)
    folder = _project_dir(project_id)
    filename = f"template-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{_safe_filename(image.filename)}"
    destination = folder / "templates" / filename
    _write_upload(image, destination)
    preview_destination = destination
    if destination.suffix.lower() == ".psd":
        try:
            from psd_tools import PSDImage
            preview_destination = destination.with_suffix(".png")
            PSDImage.open(destination).composite().save(preview_destination)
        except Exception as error:
            destination.unlink(missing_ok=True)
            _error("thumbnail_psd_render_failed", "CourtVision could not open that PSD template.", "Confirm the PSD is not damaged, install the updated requirements, and try again.", str(error), 400)
    workspace = _load_workspace(project_id)
    workspace["template"] = {
        "filename": preview_destination.name,
        "source_filename": destination.name,
        "file_path": str(preview_destination),
        "preview_url": _preview_url(project_id, "templates", preview_destination.name),
        "created_at": datetime.now().isoformat(timespec="seconds")
    }
    _save_workspace(project_id, workspace)
    return {"ok": True, "message": "Template added.", "workspace": workspace}


@router.post("/thumbnail-builder/project/{project_id}/canvas")
async def save_thumbnail_canvas(project_id: str, canvas_json: str = Form(...)):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Choose an existing saved project and try again.", project_id, 404)
    try:
        canvas = json.loads(canvas_json)
    except Exception as error:
        _error("invalid_canvas", "The thumbnail crop and text settings could not be read.", "Reopen Crop & Text and try saving again.", str(error), 400)
    if not isinstance(canvas, dict):
        _error("invalid_canvas", "The thumbnail crop and text settings are invalid.", "Reopen Crop & Text and try saving again.", repr(canvas), 400)
    workspace = _load_workspace(project_id)
    workspace["canvas"] = canvas
    _save_workspace(project_id, workspace)
    return {"ok": True, "message": "Thumbnail edits autosaved.", "workspace": workspace}


@router.post("/thumbnail-builder/project/{project_id}/final")
async def save_final_thumbnail(
    project_id: str,
    image: UploadFile = File(...),
    canvas_json: str = Form("")
):
    project = load_project(project_id)
    if not project:
        _error("project_not_found", "That CourtVision project could not be found.", "Choose an existing saved project and try again.", project_id, 404)
    project_thumbnail_dir = Path(THUMBNAILS_DIR) / project_id
    project_thumbnail_dir.mkdir(parents=True, exist_ok=True)
    filename = "thumbnail.png"
    destination = project_thumbnail_dir / filename
    with destination.open("wb") as target:
        shutil.copyfileobj(image.file, target)
    project["thumbnail"] = {
        "filename": filename,
        "file_path": str(destination),
        "preview_url": f"/content-studio/thumbnail/{project_id}/{filename}",
        "updated_at": datetime.now().isoformat(timespec="seconds")
    }
    project = save_project(project)
    workspace = _load_workspace(project_id)
    final_folder = _project_dir(project_id) / "finals"
    archive_name = f"final-{datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
    shutil.copy2(destination, final_folder / archive_name)
    workspace["final"] = {
        "filename": archive_name,
        "file_path": str(final_folder / archive_name),
        "preview_url": _preview_url(project_id, "finals", archive_name),
        "created_at": datetime.now().isoformat(timespec="seconds")
    }
    if canvas_json:
        try:
            workspace["canvas"] = json.loads(canvas_json)
        except Exception:
            pass
    _save_workspace(project_id, workspace)
    return {"ok": True, "message": "Final thumbnail saved and assigned to the project.", "project": project, "workspace": workspace}



@router.get("/thumbnail-builder/font/lemon-milk")
def thumbnail_builder_lemon_milk_font():
    candidates = [
        FONT_ASSETS_DIR / "LEMONMILK-BoldItalic.otf",
        FONT_ASSETS_DIR / "LemonMilk-BoldItalic.otf",
        FONT_ASSETS_DIR / "LEMON_MILK_Bold_Italic.otf",
    ]
    font_path = next((path for path in candidates if path.exists()), None)
    if not font_path:
        _error("thumbnail_font_missing", "The Lemon Milk Bold Italic font is not installed.", "Place LEMONMILK-BoldItalic.otf in backend/assets/fonts and restart the backend.", str(FONT_ASSETS_DIR), 404)
    return FileResponse(font_path, media_type="font/otf", headers={"Cache-Control": "public, max-age=3600"})


@router.get("/thumbnail-builder/template-no-words")
def thumbnail_builder_template_no_words():
    """Serve the permanent Solo Highlight overlay directly from templatenowords.png."""
    _ensure_dirs()
    path = TEMPLATE_ASSETS_DIR / "templatenowords.png"
    if not path.exists():
        _error(
            "thumbnail_template_no_words_missing",
            "The Solo Highlight overlay is not available.",
            "Place templatenowords.png in backend/assets/thumbnail_templates and restart the backend.",
            str(path),
            404,
        )
    return FileResponse(
        path,
        media_type="image/png",
        headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"},
    )


@router.get("/thumbnail-builder/default-template/{template_key}")
def thumbnail_builder_default_template(template_key: str):
    project_type = "top10" if template_key == "top10" else "solo"
    template = _render_default_template(project_type)
    if not template or template.get("error"):
        _error("thumbnail_default_template_missing", "The default thumbnail template is not available.", "Place the template in backend/assets/thumbnail_templates and restart the backend.", str(template or template_key), 404)
    path = Path(template["file_path"])
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "no-store"})

@router.get("/thumbnail-builder/file/{project_id}/{category}/{filename}")
def thumbnail_builder_file(project_id: str, category: str, filename: str):
    if category not in {"sources", "versions", "templates", "finals"}:
        _error("thumbnail_path_invalid", "That thumbnail file location is not valid.", "Return to Thumbnail Builder and choose the image again.", category, 400)
    safe_name = os.path.basename(filename)
    path = _project_dir(project_id) / category / safe_name
    if not path.exists():
        _error("thumbnail_file_missing", "That thumbnail image file could not be found.", "Choose another saved version or upload the image again.", str(path), 404)
    return FileResponse(path)
