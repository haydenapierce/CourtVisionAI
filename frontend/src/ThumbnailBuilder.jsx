import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import "./ThumbnailBuilder.css"

const API = "http://127.0.0.1:8001"

const SOLO_TEXT_SIZES = [94, 94, 69, 47]
const SOLO_TEXT_GAPS = [8, 8, 8]

function clampNumber(value, minimum, maximum) {
  const number = Number(value)
  if (!Number.isFinite(number)) return minimum
  return Math.min(maximum, Math.max(minimum, number))
}
const SOLO_TEXT_DEFAULTS = (() => {
  const yPositions = [0]
  SOLO_TEXT_GAPS.forEach((gap, index) => {
    yPositions.push(yPositions[index] + Math.ceil(SOLO_TEXT_SIZES[index] * 1.19) + gap)
  })
  return [
    { key: "line1", label: "Line 1", text: "PLAYER", x: 0, y: yPositions[0], font_size: SOLO_TEXT_SIZES[0], min_font_size: 48, max_width: 430, gradient_start: "#ffffff", gradient_end: "#eeeeee", align: "center", vertical_scale: 1.19 },
    { key: "line2", label: "Line 2", text: "NAME", x: 0, y: yPositions[1], font_size: SOLO_TEXT_SIZES[1], min_font_size: 48, max_width: 430, gradient_start: "#ffffff", gradient_end: "#eeeeee", align: "center", vertical_scale: 1.19 },
    { key: "line3", label: "Line 3", text: "HIGHLIGHT", x: 0, y: yPositions[2], font_size: SOLO_TEXT_SIZES[2], min_font_size: 38, max_width: 470, gradient_start: "#ffe733", gradient_end: "#f28a00", align: "center", vertical_scale: 1.19 },
    { key: "line4", label: "Line 4", text: "VS OPPONENT", x: 0, y: yPositions[3], font_size: SOLO_TEXT_SIZES[3], min_font_size: 28, max_width: 440, gradient_start: "#ffffff", gradient_end: "#eeeeee", align: "center", vertical_scale: 1.19 }
  ]
})()

function projectTextDefaults(project) {
  const words = String(project?.project_name || "PLAYER NAME").trim().split(/\s+/).filter(Boolean)
  const first = (words.shift() || "PLAYER").toUpperCase()
  const second = (words.join(" ") || "NAME").toUpperCase()
  return SOLO_TEXT_DEFAULTS.map((layer, index) => ({
    ...layer,
    text: index === 0 ? first : index === 1 ? second : layer.text
  }))
}

function normalizeCanvasState(value, project) {
  const raw = value && typeof value === "object" ? value : {}
  const isTop10 = String(project?.project_type || "").toLowerCase() === "top10"
  const defaults = projectTextDefaults(project)
  const incoming = Array.isArray(raw.text_layers) ? raw.text_layers : []
  const textLayers = isTop10 ? [] : defaults.map((fallback, index) => {
    const current =
      incoming.find(item => item?.key === fallback.key) ||
      (fallback.key === "line4" ? incoming.find(item => item?.key === "accent") : null) ||
      incoming[index] ||
      {}

    // Saved workspaces may contain stale positions, invalid sizes, or partial
    // style objects from older Thumbnail Builder versions. Only preserve the
    // user's wording. The current template owns every visual property so the
    // four branded lines can never be moved off-canvas or made invisible.
    return {
      ...fallback,
      text: Object.prototype.hasOwnProperty.call(current, "text")
        ? String(current.text ?? "")
        : fallback.text
    }
  })
  return {
    ...raw,
    scale: Number(raw.scale || 1),
    x: Number(raw.x || 0),
    y: Number(raw.y || 0),
    text_group_x: 270,
    text_group_y: 54,
    text_group_rotation: -6,
    // Keep the complete four-line block inside the 1280 x 720 preview even
    // when an older workspace saved a large drag offset.
    text_offset_x: clampNumber(raw.text_offset_x || 0, -20, 720),
    text_offset_y: clampNumber(raw.text_offset_y || 0, -20, 245),
    text_layers: textLayers
  }
}

function extractApiError(response, payload, fallback) {
  const nested = payload?.detail && typeof payload.detail === "object" ? payload.detail : payload
  const technical = nested?.technical_detail || nested?.detail || payload?.detail || `${response.status} ${response.statusText}`
  const error = new Error(nested?.message || (typeof payload?.detail === "string" ? payload.detail : fallback))
  error.code = nested?.code || "request_failed"
  error.resolution = nested?.resolution || "Review the details, correct the issue, and try again."
  error.technicalDetail = typeof technical === "string" ? technical : JSON.stringify(technical, null, 2)
  return error
}

async function apiRequest(path, options = {}) {
  const response = await fetch(`${API}${path}`, options)
  const payload = await response.json().catch(() => null)
  if (!response.ok || payload?.ok === false) {
    throw extractApiError(response, payload, "Thumbnail Builder request failed.")
  }
  return payload
}

function url(path) {
  return path ? `${API}${path}` : ""
}

function ProjectThumbnail({ project }) {
  const preview = project?.thumbnail?.preview_url
  return preview ? <img src={url(preview)} alt="" /> : <div className="tb-project-placeholder">THUMB</div>
}

export default function ThumbnailBuilder({
  showDialog,
  onProjectUpdated,
  initialProjects = null,
  onProjectsLoaded,
  preferredProjectId = "",
  launchContext = "standalone",
  onReturnToUploader
}) {
  const [projects, setProjects] = useState(() => Array.isArray(initialProjects) ? initialProjects : [])
  const [selectedId, setSelectedId] = useState("")
  const [project, setProject] = useState(null)
  const [workspace, setWorkspace] = useState(null)
  const [loading, setLoading] = useState(() => !Array.isArray(initialProjects) || initialProjects.length === 0)
  const [busy, setBusy] = useState("")
  const [canvas, setCanvas] = useState(() => normalizeCanvasState(null, null))
  const canvasRef = useRef(null)
  const drawRequestRef = useRef(0)
  const [editTarget, setEditTarget] = useState("background")
  const [manualEditOpen, setManualEditOpen] = useState(false)
  const [manualEditMode, setManualEditMode] = useState(null)
  const [draftCanvas, setDraftCanvas] = useState(null)
  const [editHistory, setEditHistory] = useState([])
  const [editHistoryIndex, setEditHistoryIndex] = useState(-1)
  const dragRef = useRef(null)
  const textAutosaveTimerRef = useRef(null)
  const textAutosaveSequenceRef = useRef(0)
  const selectedIdRef = useRef("")
  const [canvasSaveState, setCanvasSaveState] = useState("saved")
  const [textPositionUnlocked, setTextPositionUnlocked] = useState(false)

  const cloneCanvas = useCallback(value => JSON.parse(JSON.stringify(value)), [])

  function textDraftStorageKey(projectId) {
    return `courtvision-thumbnail-text:${projectId}`
  }

  function readSavedProjectText(projectId) {
    if (!projectId) return null
    try {
      const saved = JSON.parse(localStorage.getItem(textDraftStorageKey(projectId)) || "null")
      return Array.isArray(saved?.lines) && saved.lines.length === 4 ? saved.lines.map(value => String(value ?? "")) : null
    } catch {
      return null
    }
  }

  function applySavedProjectText(value, projectId, projectValue) {
    const normalized = normalizeCanvasState(value, projectValue)
    const savedLines = readSavedProjectText(projectId)
    if (!savedLines) return normalized
    return {
      ...normalized,
      text_layers: normalized.text_layers.map((layer, index) => ({ ...layer, text: savedLines[index] }))
    }
  }

  function rememberProjectText(projectId, nextCanvas) {
    if (!projectId) return
    try {
      const normalized = normalizeCanvasState(nextCanvas, project)
      localStorage.setItem(textDraftStorageKey(projectId), JSON.stringify({
        lines: normalized.text_layers.slice(0, 4).map(layer => String(layer.text ?? "")),
        saved_at: Date.now()
      }))
    } catch {
      // Browser storage is a safety net only; backend autosave still runs.
    }
  }

  function scheduleTextAutosave(nextCanvas) {
    const projectId = selectedId
    if (!projectId || !nextCanvas) return

    rememberProjectText(projectId, nextCanvas)
    const snapshot = cloneCanvas(normalizeCanvasState(nextCanvas, project))
    const sequence = ++textAutosaveSequenceRef.current

    if (textAutosaveTimerRef.current) clearTimeout(textAutosaveTimerRef.current)
    setCanvasSaveState("saving")
    textAutosaveTimerRef.current = setTimeout(async () => {
      try {
        const form = new FormData()
        form.append("canvas_json", JSON.stringify(snapshot))
        const data = await apiRequest(`/thumbnail-builder/project/${projectId}/canvas`, { method: "POST", body: form })
        if (sequence === textAutosaveSequenceRef.current && selectedIdRef.current === projectId) {
          setWorkspace(data.workspace)
          setCanvasSaveState("saved")
        }
      } catch (error) {
        if (sequence === textAutosaveSequenceRef.current && selectedIdRef.current === projectId) {
          setCanvasSaveState("error")
          notifyError(error, "Thumbnail Text Could Not Autosave")
        }
      }
    }, 450)
  }

  const previewCanvas = normalizeCanvasState(manualEditOpen && draftCanvas ? draftCanvas : canvas, project)

  const notifyError = useCallback((error, title = "Thumbnail Builder Error") => {
    showDialog(error?.message || "Thumbnail Builder could not finish that action.", {
      title,
      type: "error",
      code: error?.code || "thumbnail_builder_error",
      resolution: error?.resolution || "Review the information below and try again.",
      technicalDetail: error?.technicalDetail || String(error?.stack || error || "")
    })
  }, [showDialog])

  const loadProjects = useCallback(async (preferredId = "") => {
    try {
      const data = await apiRequest("/thumbnail-builder/projects")
      const list = data.projects || []
      setProjects(list)
      onProjectsLoaded?.(list)
      const requested = preferredId || preferredProjectId || selectedId
      const next = list.some(item => item.project_id === requested)
        ? requested
        : list[0]?.project_id || ""
      if (next) setSelectedId(next)
    } catch (error) {
      notifyError(error, "Projects Could Not Load")
    } finally {
      setLoading(false)
    }
  }, [notifyError, onProjectsLoaded, preferredProjectId, selectedId])


  useEffect(() => {
    const bootProjects = Array.isArray(initialProjects) ? initialProjects : []

    // Show any projects supplied by the application bootstrap immediately, but
    // always refresh from the Thumbnail Builder endpoint. App.jsx initializes
    // its bootstrap state with an empty array, which previously looked like a
    // completed load and prevented this component from ever requesting projects.
    if (bootProjects.length) {
      setProjects(bootProjects)
      const next = selectedId || bootProjects[0]?.project_id || ""
      if (next) setSelectedId(next)
    }
    loadProjects(preferredProjectId || selectedId || bootProjects[0]?.project_id || "")

  }, [])

  useEffect(() => {
    if (!preferredProjectId || preferredProjectId === selectedId) return
    if (projects.some(item => item.project_id === preferredProjectId)) {
      setSelectedId(preferredProjectId)
    }
  }, [preferredProjectId, projects, selectedId])

  useEffect(() => {
    selectedIdRef.current = selectedId
    if (textAutosaveTimerRef.current) {
      clearTimeout(textAutosaveTimerRef.current)
      textAutosaveTimerRef.current = null
    }
    return () => {
      if (textAutosaveTimerRef.current) clearTimeout(textAutosaveTimerRef.current)
    }
  }, [selectedId])

  useEffect(() => {
    setManualEditOpen(false)
    setManualEditMode(null)
    setDraftCanvas(null)
    setEditHistory([])
    setEditHistoryIndex(-1)
    if (!selectedId) {
      setProject(null)
      setWorkspace(null)
      return
    }
    setBusy("project")
    apiRequest(`/thumbnail-builder/project/${selectedId}`)
      .then(data => {
        setProject(data.project)
        setWorkspace(data.workspace)
        setCanvas(applySavedProjectText(data.workspace?.canvas, selectedId, data.project))
      })
      .catch(error => notifyError(error, "Project Could Not Open"))
      .finally(() => setBusy(""))
  }, [selectedId])


  const baseImageUrl = useMemo(() => {
    if (workspace?.source?.preview_url) return url(workspace.source.preview_url)
    return ""
  }, [workspace])

  const isTop10 = String(project?.project_type || "").toLowerCase() === "top10"
  const activeTemplate = workspace?.default_template || workspace?.template || null
  const templateKey = isTop10 ? "top10" : "solo-highlight"
  // The project format is authoritative. Request the locked default overlay
  // directly so an old workspace template can never replace or hide it.
  const templateVersion = activeTemplate?.source_mtime || activeTemplate?.filename || templateKey
  const templateUrl = project
    ? (templateKey === "solo-highlight"
      ? `/thumbnail_templates/templatenowords.png?v=${encodeURIComponent(templateVersion)}`
      : `${API}/thumbnail-builder/default-template/${templateKey}?v=${encodeURIComponent(templateVersion)}`)
    : ""

  const drawCanvas = useCallback(async () => {
    const element = canvasRef.current
    if (!element) return false

    const requestId = ++drawRequestRef.current
    const buffer = document.createElement("canvas")
    buffer.width = 1280
    buffer.height = 720
    const context = buffer.getContext("2d")
    context.clearRect(0, 0, 1280, 720)
    context.fillStyle = "#080808"
    context.fillRect(0, 0, 1280, 720)

    const loadImage = source => new Promise((resolve, reject) => {
      if (!source) return resolve(null)
      const image = new Image()
      image.crossOrigin = "anonymous"
      image.onload = () => resolve(image)
      image.onerror = reject
      image.src = source
    })

    try {
      // Canvas text must wait for the branded font; otherwise the first preview
      // can be permanently measured and drawn with a browser fallback font.
      await document.fonts?.load?.('italic 900 88px "Lemon Milk"').catch(() => null)

      // Load both layers together, then compose the complete frame offscreen.
      // Only the newest completed request may replace the visible canvas.
      const [image, template] = await Promise.all([
        loadImage(baseImageUrl).catch(() => null),
        loadImage(templateUrl).catch(() => null)
      ])

      if (image) {
        const fit = Math.max(1280 / image.width, 720 / image.height)
        const width = image.width * fit * Number(previewCanvas.scale || 1)
        const height = image.height * fit * Number(previewCanvas.scale || 1)
        const x = (1280 - width) / 2 + Number(previewCanvas.x || 0)
        const y = (720 - height) / 2 + Number(previewCanvas.y || 0)
        context.drawImage(image, x, y, width, height)
      }

      // The locked template is always composited after the source image.
      if (template) context.drawImage(template, 0, 0, 1280, 720)

      // Solo Highlight owns the permanent four-line editable text layout.
      // Top 10 thumbnails are image + locked logo template only.
      if (!isTop10) {
        // Always render exactly four normalized text layers after the template.
        // Each line is isolated so one malformed saved layer can never prevent
        // the remaining lines from appearing.
        const normalizedPreview = normalizeCanvasState(previewCanvas, project)
        const layers = normalizedPreview.text_layers.slice(0, 4)
        const groupX = clampNumber(
          Number(normalizedPreview.text_group_x || 270) + Number(normalizedPreview.text_offset_x || 0),
          250,
          990
        )
        const groupY = clampNumber(
          Number(normalizedPreview.text_group_y || 54) + Number(normalizedPreview.text_offset_y || 0),
          24,
          300
        )
        const groupRotation = Number(normalizedPreview.text_group_rotation || -6) * Math.PI / 180
        context.save()
        context.translate(groupX, groupY)
        context.rotate(groupRotation)
        layers.forEach((layer, layerIndex) => {
          context.save()
          try {
            const styleDefaults = SOLO_TEXT_DEFAULTS[layerIndex] || SOLO_TEXT_DEFAULTS[3]
            const text = String(layer?.text ?? styleDefaults.text).trim() || styleDefaults.text
            const family = '"Lemon Milk", Impact, "Arial Black", Arial, sans-serif'
            const weight = 900
            const style = "italic"
            const configuredSize = Number(styleDefaults.font_size)
            const minSize = Number(styleDefaults.min_font_size)
            const maxWidth = Number(styleDefaults.max_width)
            let size = configuredSize
            const setFont = () => { context.font = `${style} ${weight} ${size}px ${family}` }
            setFont()
            while (size > minSize && context.measureText(text).width > maxWidth) {
              size -= 1
              setFont()
            }

            context.translate(Number(styleDefaults.x), Number(styleDefaults.y))
            context.scale(1, Number(styleDefaults.vertical_scale || 1.19))
            context.textBaseline = "top"
            context.textAlign = styleDefaults.align
            context.lineJoin = "round"

            const extrusionDepth = Math.max(4, size * 0.08)
            context.lineWidth = Math.max(5, size * 0.075)

            // Give every one of the four text layers the same oversized,
            // Photoshop-style drop shadow. The first pass creates the broad
            // soft falloff; the second creates the strong visible offset edge.
            // Both passes stay behind the existing extrusion, outline, and fill.
            context.save()
            context.fillStyle = "rgba(0, 0, 0, 0.98)"
            context.shadowColor = "rgba(0, 0, 0, 0.90)"
            context.shadowBlur = Math.max(48, size * 0.65)
            context.shadowOffsetX = Math.max(20, size * 0.28)
            context.shadowOffsetY = Math.max(28, size * 0.38)
            context.fillText(text, 0, 0)
            context.restore()

            context.save()
            context.fillStyle = "rgba(0, 0, 0, 0.96)"
            context.shadowColor = "rgba(0, 0, 0, 0.96)"
            context.shadowBlur = Math.max(18, size * 0.24)
            context.shadowOffsetX = Math.max(24, size * 0.32)
            context.shadowOffsetY = Math.max(34, size * 0.44)
            context.fillText(text, 0, 0)
            context.restore()

            context.shadowColor = "transparent"
            context.shadowBlur = 0
            context.shadowOffsetX = 0
            context.shadowOffsetY = 0
            context.strokeStyle = "#111111"
            context.fillStyle = "#131313"
            for (let depth = extrusionDepth; depth >= 1; depth -= 1) {
              context.strokeText(text, depth, depth)
              context.fillText(text, depth, depth)
            }

            const gradient = context.createLinearGradient(0, 0, 0, size)
            gradient.addColorStop(0, styleDefaults.gradient_start)
            gradient.addColorStop(1, styleDefaults.gradient_end)
            context.fillStyle = gradient
            context.strokeText(text, 0, 0)
            context.fillText(text, 0, 0)
          } finally {
            context.restore()
          }
        })
        context.restore()
      }
      if (requestId !== drawRequestRef.current) return false
      const visibleContext = element.getContext("2d")
      visibleContext.clearRect(0, 0, 1280, 720)
      visibleContext.drawImage(buffer, 0, 0)
      return true
    } catch (error) {
      if (requestId === drawRequestRef.current) {
        const visibleContext = element.getContext("2d")
        visibleContext.clearRect(0, 0, 1280, 720)
        visibleContext.drawImage(buffer, 0, 0)
      }
      return false
    }
  }, [baseImageUrl, templateUrl, previewCanvas, isTop10])

  useEffect(() => {
    drawCanvas()
  }, [drawCanvas])

  function canvasPoint(event) {
    const rect = canvasRef.current?.getBoundingClientRect()
    if (!rect) return { x: 0, y: 0 }
    return {
      x: (event.clientX - rect.left) * (1280 / rect.width),
      y: (event.clientY - rect.top) * (720 / rect.height)
    }
  }

  function pushEditSnapshot(nextCanvas) {
    const snapshot = cloneCanvas(nextCanvas)
    setEditHistory(history => {
      const trimmed = history.slice(0, editHistoryIndex + 1)
      const next = [...trimmed, snapshot].slice(-80)
      setEditHistoryIndex(next.length - 1)
      return next
    })
  }

  function updateDraftCanvas(updater, commitHistory = true) {
    setDraftCanvas(previous => {
      const current = previous || cloneCanvas(canvas)
      const next = typeof updater === "function" ? updater(current) : updater
      if (commitHistory) queueMicrotask(() => pushEditSnapshot(next))
      return next
    })
  }

  function openManualEditor(mode) {
    const initial = cloneCanvas(normalizeCanvasState(canvas, project))
    setTextPositionUnlocked(mode === "text")
    setDraftCanvas(initial)
    setEditHistory([initial])
    setEditHistoryIndex(0)
    setEditTarget(mode === "text" ? "text-group" : "background")
    setManualEditMode(mode)
    setManualEditOpen(true)
  }

  function editTextLayer(layerIndex, text) {
    const sourceCanvas = manualEditOpen && draftCanvas ? draftCanvas : canvas
    const normalized = normalizeCanvasState(sourceCanvas, project)
    const nextCanvas = {
      ...normalized,
      text_layers: normalized.text_layers.map((item, index) =>
        index === layerIndex ? { ...item, text } : item
      )
    }

    // Update the preview immediately and persist the exact four lines for this
    // project. Visual text configuration is untouched.
    if (manualEditOpen && draftCanvas) {
      setDraftCanvas(nextCanvas)
    } else {
      setCanvas(nextCanvas)
    }
    setEditTarget(`line${layerIndex + 1}`)
    scheduleTextAutosave(nextCanvas)
  }

  async function saveTextEdits() {
    const current = manualEditOpen && draftCanvas ? draftCanvas : canvas
    if (!selectedId || !current) return

    // Blurring an input flushes the debounce so the latest keystroke is saved
    // immediately rather than waiting for the timer.
    if (textAutosaveTimerRef.current) {
      clearTimeout(textAutosaveTimerRef.current)
      textAutosaveTimerRef.current = null
    }
    scheduleTextAutosave(current)
  }

  function cancelManualEditor() {
    setDraftCanvas(null)
    setEditHistory([])
    setEditHistoryIndex(-1)
    setManualEditOpen(false)
    setManualEditMode(null)
    setTextPositionUnlocked(false)
    setEditTarget("background")
  }

  async function persistCanvas(nextCanvas) {
    if (!selectedId || !nextCanvas) return null
    setCanvasSaveState("saving")
    try {
      const form = new FormData()
      form.append("canvas_json", JSON.stringify(nextCanvas))
      const data = await apiRequest(`/thumbnail-builder/project/${selectedId}/canvas`, { method: "POST", body: form })
      setWorkspace(data.workspace)
      setCanvasSaveState("saved")
      return data.workspace
    } catch (error) {
      setCanvasSaveState("error")
      notifyError(error, "Thumbnail Edits Could Not Autosave")
      return null
    }
  }

  async function finishManualEditor() {
    if (!draftCanvas || busy === "canvas-save") return
    const nextCanvas = cloneCanvas(draftCanvas)
    setBusy("canvas-save")
    const savedWorkspace = await persistCanvas(nextCanvas)
    setBusy("")
    if (!savedWorkspace) return
    setCanvas(nextCanvas)
    setDraftCanvas(null)
    setEditHistory([])
    setEditHistoryIndex(-1)
    setManualEditOpen(false)
    setManualEditMode(null)
    setTextPositionUnlocked(false)
    setEditTarget("background")
  }

  const undoEdit = useCallback(() => {
    if (!manualEditOpen || editHistoryIndex <= 0) return
    const nextIndex = editHistoryIndex - 1
    setEditHistoryIndex(nextIndex)
    setDraftCanvas(cloneCanvas(editHistory[nextIndex]))
  }, [manualEditOpen, editHistoryIndex, editHistory, cloneCanvas])

  const redoEdit = useCallback(() => {
    if (!manualEditOpen || editHistoryIndex >= editHistory.length - 1) return
    const nextIndex = editHistoryIndex + 1
    setEditHistoryIndex(nextIndex)
    setDraftCanvas(cloneCanvas(editHistory[nextIndex]))
  }, [manualEditOpen, editHistoryIndex, editHistory, cloneCanvas])

  useEffect(() => {
    if (!manualEditOpen) return undefined
    const handleKeyDown = event => {
      if (!(event.ctrlKey || event.metaKey)) return
      const key = event.key.toLowerCase()
      if (key === "y" || (key === "z" && event.shiftKey)) {
        event.preventDefault()
        redoEdit()
        return
      }
      if (key === "z") {
        event.preventDefault()
        undoEdit()
      }
    }
    window.addEventListener("keydown", handleKeyDown)
    return () => window.removeEventListener("keydown", handleKeyDown)
  }, [manualEditOpen, undoEdit, redoEdit])

  function pointHitsTextGroup(point, workingCanvas) {
    const layers = Array.isArray(workingCanvas?.text_layers) ? workingCanvas.text_layers : []
    const offsetX = Number(workingCanvas?.text_group_x || 270) + Number(workingCanvas?.text_offset_x || 0)
    const offsetY = Number(workingCanvas?.text_group_y || 54) + Number(workingCanvas?.text_offset_y || 0)
    return layers.some((layer, index) => {
      const text = String(layer?.text || "").trim()
      if (!text) return false
      const styleDefaults = SOLO_TEXT_DEFAULTS[index] || SOLO_TEXT_DEFAULTS[3]
      const size = Number(styleDefaults.font_size)
      const width = Number(styleDefaults.max_width)
      const height = size * Number(styleDefaults.vertical_scale || 1.12)
      const x = Number(styleDefaults.x) + offsetX
      const y = Number(styleDefaults.y) + offsetY
      const align = styleDefaults.align || "center"
      const left = align === "center" ? x - width / 2 : align === "right" ? x - width : x
      return point.x >= left - 18 && point.x <= left + width + 18 && point.y >= y - 18 && point.y <= y + height + 18
    })
  }

  function beginCanvasDrag(event) {
    if (!manualEditOpen || !draftCanvas) return
    if (manualEditMode === "crop" && !baseImageUrl) return

    const point = canvasPoint(event)
    if (manualEditMode === "text") {
      dragRef.current = {
        kind: "text-group",
        startX: point.x,
        startY: point.y,
        originX: Number(draftCanvas.text_offset_x || 0),
        originY: Number(draftCanvas.text_offset_y || 0)
      }
      setEditTarget("text-group")
    } else {
      dragRef.current = {
        kind: "background",
        startX: point.x,
        startY: point.y,
        originX: Number(draftCanvas.x || 0),
        originY: Number(draftCanvas.y || 0)
      }
      setEditTarget("background")
    }
    event.currentTarget.setPointerCapture?.(event.pointerId)
  }

  function moveCanvasDrag(event) {
    const drag = dragRef.current
    if (!drag || !manualEditOpen) return
    const point = canvasPoint(event)
    const dx = point.x - drag.startX
    const dy = point.y - drag.startY
    updateDraftCanvas(previous => drag.kind === "background"
      ? { ...previous, x: Math.round(drag.originX + dx), y: Math.round(drag.originY + dy) }
      : {
          ...previous,
          text_offset_x: clampNumber(Math.round(drag.originX + dx), -20, 720),
          text_offset_y: clampNumber(Math.round(drag.originY + dy), -20, 245)
        }, false)
  }

  function endCanvasDrag(event) {
    if (dragRef.current && draftCanvas) pushEditSnapshot(draftCanvas)
    dragRef.current = null
    event.currentTarget.releasePointerCapture?.(event.pointerId)
  }

  useEffect(() => {
    const previewCanvasElement = canvasRef.current
    if (!previewCanvasElement) return undefined

    const handlePreviewWheel = event => {
      if (!manualEditOpen || manualEditMode !== "crop") return

      // While Edit Crop is active, the preview owns the wheel completely.
      // This prevents page scrolling and browser zoom while the cursor is over it.
      event.preventDefault()
      event.stopPropagation()

      if (!draftCanvas || !baseImageUrl) return

      setEditTarget("background")
      const direction = event.deltaY > 0 ? -0.05 : 0.05
      updateDraftCanvas(previous => ({
        ...previous,
        scale: Math.min(4, Math.max(0.35, Number(previous.scale || 1) + direction))
      }))
    }

    previewCanvasElement.addEventListener("wheel", handlePreviewWheel, { passive: false })
    return () => previewCanvasElement.removeEventListener("wheel", handlePreviewWheel)
  }, [manualEditOpen, manualEditMode, draftCanvas, baseImageUrl])

  async function uploadAsset(kind, file) {
    if (!selectedId || !file) return
    setBusy(kind)
    try {
      const form = new FormData()
      form.append("image", file)
      const data = await apiRequest(`/thumbnail-builder/project/${selectedId}/${kind}`, { method: "POST", body: form })
      setWorkspace(data.workspace)
      if (data.workspace?.canvas) setCanvas(normalizeCanvasState(data.workspace.canvas, project))
      if (kind === "source") {
        setManualEditOpen(false)
        setManualEditMode(null)
      } else {
        showDialog(data.message || "Template saved.", { title: "Template Added", type: "success" })
      }
    } catch (error) {
      notifyError(error, kind === "source" ? "Source Image Could Not Upload" : "Template Could Not Upload")
    } finally {
      setBusy("")
    }
  }

  async function normalizeClipboardImage(blob) {
    const bitmap = await createImageBitmap(blob)
    const buffer = document.createElement("canvas")
    buffer.width = bitmap.width
    buffer.height = bitmap.height
    const context = buffer.getContext("2d")
    context.drawImage(bitmap, 0, 0)
    bitmap.close?.()
    return await new Promise((resolve, reject) => {
      buffer.toBlob(result => result ? resolve(result) : reject(new Error("The clipboard image could not be converted to PNG.")), "image/png", 1)
    })
  }

  async function pasteImage() {
    if (!selectedId || !navigator.clipboard?.read) {
      notifyError(new Error("Clipboard image access is not available in this browser. Use Upload Image instead."), "Image Could Not Paste")
      return
    }
    setBusy("paste")
    try {
      const items = await navigator.clipboard.read()
      let imageBlob = null
      let mimeType = "image/png"
      for (const item of items) {
        const type = item.types.find(value => value.startsWith("image/"))
        if (type) {
          imageBlob = await item.getType(type)
          mimeType = type
          break
        }
      }
      if (!imageBlob) throw new Error("No copied image was found on the clipboard.")
      const normalizedBlob = await normalizeClipboardImage(imageBlob)
      const file = new File([normalizedBlob], "clipboard-image.png", { type: "image/png" })
      const form = new FormData()
      form.append("image", file)
      const data = await apiRequest(`/thumbnail-builder/project/${selectedId}/source`, { method: "POST", body: form })
      setWorkspace(data.workspace)
      if (data.workspace?.canvas) setCanvas(normalizeCanvasState(data.workspace.canvas, project))
      setManualEditOpen(false)
      setManualEditMode(null)
    } catch (error) {
      notifyError(error, "Image Could Not Paste")
    } finally {
      setBusy("")
    }
  }


  async function saveFinal() {
    if (!selectedId || !canvasRef.current) return
    setBusy("final")
    try {
      await drawCanvas()
      const blob = await new Promise(resolve => canvasRef.current.toBlob(resolve, "image/png", 1))
      if (!blob) throw new Error("The browser could not export the thumbnail canvas.")
      const form = new FormData()
      form.append("image", blob, "thumbnail.png")
      form.append("canvas_json", JSON.stringify(canvas))
      const data = await apiRequest(`/thumbnail-builder/project/${selectedId}/final`, { method: "POST", body: form })
      setWorkspace(data.workspace)
      setProject(data.project)
      onProjectUpdated?.(data.project)
      await loadProjects(selectedId)
      if (launchContext === "youtube" && onReturnToUploader) {
        onReturnToUploader(data.project)
      } else {
        showDialog("The final thumbnail was saved and automatically assigned to this video project.", { title: "Thumbnail Assigned", type: "success" })
      }
    } catch (error) {
      notifyError(error, "Final Thumbnail Could Not Save")
    } finally {
      setBusy("")
    }
  }

  async function downloadFinal() {
    await drawCanvas()
    const link = document.createElement("a")
    link.download = `${String(project?.project_name || "courtvision-thumbnail").replace(/[^a-z0-9]+/gi, "-")}.png`
    link.href = canvasRef.current.toDataURL("image/png")
    link.click()
  }


  if (loading) return <div className="card big"><h2>Thumbnail Builder</h2><p>Loading projects…</p></div>

  return (
    <div className="thumbnail-builder-page">
      <header className="tb-header">
        <div>
          <span>COURTVISION PRODUCTION</span>
          <h1>Thumbnail Builder</h1>
          <p>{isTop10 ? "Upload or paste an image, crop it beneath the locked Top 10 logo template, and assign the finished thumbnail." : "Upload or paste an image, crop it, edit the permanent four-line Solo Highlight text layout, and assign the finished thumbnail."}</p>
        </div>
        <div className="tb-header-actions">
          {launchContext === "youtube" && <button className="secondary" onClick={() => onReturnToUploader?.(project)}>Back to Upload</button>}
        </div>
      </header>

      {!projects.length ? (
        <section className="tb-empty">No saved editor projects were found.</section>
      ) : (
        <div className="tb-editor-shell">
          <aside className="tb-left-rail">
            <section className="tb-panel tb-project-panel">
              <div className="tb-section-title"><span>PROJECTS</span><h2>Video Projects</h2></div>
              <div className="tb-project-list">
                {projects.map(item => (
                  <button key={item.project_id} className={selectedId === item.project_id ? "tb-project active" : "tb-project"} onClick={() => setSelectedId(item.project_id)}>
                    <ProjectThumbnail project={item} />
                    <div><b>{item.project_name}</b><small>{item.project_type === "top10" ? "Top 10" : "Solo Highlight"}</small></div>
                  </button>
                ))}
              </div>
            </section>

            {project && !isTop10 && <>
              <section className="tb-panel tb-text-panel tb-text-left-rail">
                <div className="tb-section-title"><span>TEMPLATE TEXT</span><h2>Edit four lines</h2></div>
                <div className="tb-text-fields">
                  {(previewCanvas.text_layers || []).slice(0,4).map((layer,index) => (
                    <label key={layer.key || index}>
                      <span>Line {index + 1}</span>
                      <input
                        value={layer.text || ""}
                        onFocus={() => setEditTarget(`line${index + 1}`)}
                        onChange={event => editTextLayer(index, event.target.value)}
                        onBlur={saveTextEdits}
                      />
                    </label>
                  ))}
                </div>
              </section>

            </>}
          </aside>

          <main className="tb-main-workspace">
            {project && <>
              <section className="tb-panel tb-canvas-panel">
                <div className="tb-canvas-head"><div><span>THUMBNAIL CANVAS</span><h2>{project.project_name}</h2></div><div><b>{project.project_type === "top10" ? "Top 10" : "Solo Highlight"}</b><small>1280 × 720 · YouTube 16:9</small></div></div>
                <div className={manualEditOpen ? `tb-canvas-wrap editing ${manualEditMode || ""}` : "tb-canvas-wrap"}>
                  <canvas ref={canvasRef} width="1280" height="720" onPointerDown={beginCanvasDrag} onPointerMove={moveCanvasDrag} onPointerUp={endCanvasDrag} onPointerCancel={endCanvasDrag}/>
                  {!baseImageUrl && <div className="tb-upload-empty tb-upload-empty-floating"><h3>Add the original NBA image</h3><p>Upload a file or paste the image currently copied to your clipboard.</p><div><label>Upload Image<input type="file" accept=".png,.jpg,.jpeg,.webp,image/*" onClick={event => { event.currentTarget.value = "" }} onChange={event => uploadAsset("source", event.target.files?.[0])}/></label><button className="secondary" onClick={pasteImage}>Paste Image</button></div></div>}
                </div>
                <div className="tb-canvas-actions">
                  <div className="tb-action-buttons">
                    <label className="secondary">Upload Image<input type="file" accept=".png,.jpg,.jpeg,.webp,image/*" onClick={event => { event.currentTarget.value = "" }} onChange={event => uploadAsset("source", event.target.files?.[0])}/></label>
                    <button className="secondary" onClick={pasteImage} disabled={busy === "paste"}>{busy === "paste" ? "Pasting…" : "Paste Image"}</button>
                    <button
                      className={manualEditOpen && manualEditMode === "crop" ? "danger" : "secondary"}
                      onClick={manualEditOpen && manualEditMode === "crop" ? finishManualEditor : () => openManualEditor("crop")}
                      disabled={!baseImageUrl || busy === "canvas-save"}
                    >{busy === "canvas-save" && manualEditMode === "crop" ? "Saving…" : manualEditOpen && manualEditMode === "crop" ? "Done Cropping" : "Edit Crop"}</button>
{!isTop10 && <button
                      className={manualEditOpen && manualEditMode === "text" ? "danger" : "secondary"}
                      onClick={manualEditOpen && manualEditMode === "text" ? finishManualEditor : () => openManualEditor("text")}
                      disabled={busy === "canvas-save"}
                    >{busy === "canvas-save" && manualEditMode === "text" ? "Saving…" : manualEditOpen && manualEditMode === "text" ? "Done Editing Text" : "Edit Text"}</button>}
                  </div>
                </div>
              </section>

            </>}
          </main>

          {project && (
            <section className="tb-final-bar tb-final-full-width">
              <div className="tb-final-heading"><span>FINALIZE</span></div>
              <div className="tb-final-actions">
                <button className="secondary tb-download-button" onClick={downloadFinal} disabled={!baseImageUrl || manualEditOpen}>Download PNG</button>
                <button className="tb-assign-button" onClick={saveFinal} disabled={!baseImageUrl || !!busy || manualEditOpen}>
                  {busy === "final" ? "Saving…" : launchContext === "youtube" ? "Save & Return" : "Assign to Project"}
                </button>
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  )
}
