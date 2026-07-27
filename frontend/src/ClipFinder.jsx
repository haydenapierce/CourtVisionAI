import { useEffect, useMemo, useRef, useState } from "react"
import "./ClipFinder.css"
import PlayerHeadshot from "./components/PlayerHeadshot.jsx"

const API = "http://127.0.0.1:8001"
const EXPECTED_CLIP_FINDER_BUILD = "2026.07.27-durable-download-pipeline-v7.7"
const FALLBACK_CATEGORIES = [
  "Top 10 Plays", "Top 10 Dunks", "Top 10 Blocks", "Top 10 Game Winners",
  "Top 10 Clutch Shots", "Top 10 Assists", "Top 10 Crossovers", "Top 10 Layups",
  "Top 10 Posters", "Top 10 Steals", "Top 10 Buzzer Beaters", "Top 10 Alley-Oops",
  "Top 10 Handles", "Top 10 Defensive Plays",
]


function etaLabel(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds || 0))
  if (!Number.isFinite(seconds) || seconds <= 0) return "Calculating ETA…"
  if (seconds < 60) return `About ${Math.max(5, Math.round(seconds / 5) * 5)} seconds remaining`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `About ${minutes} minute${minutes === 1 ? "" : "s"} remaining`
  const hours = Math.floor(minutes / 60)
  const remainder = minutes % 60
  return `About ${hours}h ${remainder}m remaining`
}
function secondsLabel(value) {
  const total = Math.max(0, Number(value) || 0)
  return `${Math.floor(total / 60)}:${String(Math.floor(total % 60)).padStart(2, "0")}`
}

function normalizedText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim()
}

function isStandardVideo(result, playerName = "", category = "") {
  const title = normalizedText(result?.title)
  const description = normalizedText(result?.description)
  const haystack = [title, description, normalizedText(result?.channel_title), ...(Array.isArray(result?.tags) ? result.tags.map(normalizedText) : [])].filter(Boolean).join(" ")
  const compact = haystack.replace(/[^a-z0-9]+/g, "")
  const url = String(result?.youtube_url || "").toLowerCase()
  const duration = Number(result?.duration_seconds || 0)
  const width = Number(result?.thumbnail_width || 0)
  const height = Number(result?.thumbnail_height || 0)
  const excluded = [
    "#shorts", "youtube shorts", "yt shorts", "slam dunk contest", "dunk contest", "all-star game",
    "all star game", "nba all-star", "nba all star", "rising stars", "skills challenge",
    "three-point contest", "3-point contest", "celebrity game", "summer league", "g league", "wnba",
    "ncaa", "college basketball", "high school", "prep basketball", "aau", "euroleague",
    "overseas league", "reaction", "reacts", "podcast", "interview", "documentary", "nba 2k",
    "nba2k", "2k26", "2k25", "2k24", "2k23", "video game", "mycareer", "myteam",
  ]
  if (duration <= 60 || url.includes("/shorts/") || compact.includes("nba2k") || excluded.some(term => haystack.includes(term))) return false
  if (width && height && height > width * 1.15) return false
  if (duration <= 180 && [" tiktok ", " instagram reel", " reels", "vertical video", "portrait video"].some(term => ` ${haystack} `.includes(term))) return false

  const player = normalizedText(playerName)
  if (player) {
    const surname = player.split(" ").at(-1) || ""
    const titleHasPlayer = title.includes(player) || (surname.length >= 5 && new RegExp(`\\b${surname.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`).test(title))
    const descMatches = description.split(player).length - 1
    const mentionIndex = description.indexOf(player)
    const nearbyDescription = mentionIndex >= 0 ? description.slice(Math.max(0, mentionIndex - 140), mentionIndex + player.length + 180) : ""
    const descriptionLooksRelevant = description.includes(player) && (descMatches >= 2 || ["highlight", "dunk", "poster", "slam", "alley oop", "layup", "block", "steal", "assist", "crossover", "game winner", "clutch", "playoffs"].some(term => nearbyDescription.includes(term)))
    if (!titleHasPlayer && !descriptionLooksRelevant) return false
  }

  if (category === "Top 10 Dunks") {
    const broad = ["top 10", "top ten", "highlights", "mixtape", "best of", "career", "season highlights", "game highlights"].some(term => haystack.includes(term))
    const dunk = ["dunk", "poster", "slam", "alley oop", "alley-oop", "windmill", "tomahawk", "putback"].some(term => haystack.includes(term))
    const clearlyWrong = ["three pointer", "3 pointer", "jump shot", "jumper", "midrange", "free throw"].some(term => title.includes(term))
    if (!broad && !dunk && clearlyWrong) return false
  }
  return true
}


function courtVisionError(error, context = "Clip Finder") {
  const raw = String(error?.message || error || "An unexpected error occurred.")
  const lower = raw.toLowerCase()
  if (error?.name === "TypeError" && (lower.includes("failed to fetch") || lower.includes("networkerror"))) {
    return { title: "Backend Unavailable", message: "CourtVision could not reach its local processing service on port 8001.", details: raw }
  }
  if (lower.includes("youtube.googleapis.com/youtube/v3/search") || lower.includes("youtube search is cooling down")) {
    return { title: "Old Clip Finder Backend Is Still Running", message: "CourtVision reached an older backend that still uses the quota-limited YouTube Data API search endpoint. Fully restart the backend with the included installer.", details: raw }
  }
  if (lower.includes("429") || lower.includes("temporarily limited") || lower.includes("rate limit")) {
    return { title: "Public YouTube Search Temporarily Limited", message: "The new search preserved all candidates and moved to its alternate public discovery source. If this error remains, review the detailed source and build information below.", details: raw }
  }
  if (lower.includes("unexpected search page format")) {
    return { title: "YouTube Search Format Changed", message: "YouTube returned a search page CourtVision could not read. No existing results were removed.", details: raw }
  }
  if (lower.includes("timed out") || lower.includes("timeout")) {
    return { title: "Search Timed Out", message: "The search took too long to finish. Any results already discovered were saved to this project.", details: raw }
  }
  if (lower.includes("no search results") || lower.includes("no matching")) {
    return { title: "No Matching Clips Found", message: "No standard NBA videos matched this player and category combination.", details: raw }
  }
  return { title: `${context} Error`, message: raw, details: raw }
}

function normalizedInstances(result) {
  if (Array.isArray(result?.clip_instances) && result.clip_instances.length) return result.clip_instances
  return [{ instance_id: `${result?.result_id || "clip"}-1`, label: "Clip 1", notes: result?.notes || "", rank_number: result?.rank_number ?? null }]
}

export default function ClipFinder({ onOpenEditor }) {
  const [categories, setCategories] = useState([])
  const [projects, setProjects] = useState([])
  const [projectsLoading, setProjectsLoading] = useState(true)
  const [deletedProjects, setDeletedProjects] = useState([])
  const [showDeleted, setShowDeleted] = useState(false)
  const [project, setProject] = useState(null)
  const [player, setPlayer] = useState("")
  const [playerResults, setPlayerResults] = useState([])
  const [activePlayerResult, setActivePlayerResult] = useState(-1)
  const [category, setCategory] = useState("")
  const [categoryMenuOpen, setCategoryMenuOpen] = useState(false)
  const [filter, setFilter] = useState("unreviewed")
  const [busy, setBusy] = useState(false)
  const [searchProgress, setSearchProgress] = useState(null)
  const [displayedCandidates, setDisplayedCandidates] = useState(0)
  const [error, setError] = useState(null)
  const [validationError, setValidationError] = useState("")
  const [rankError, setRankError] = useState("")
  const [changeSelectionId, setChangeSelectionId] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [confirmBusy, setConfirmBusy] = useState(false)
  const [downloadInbox, setDownloadInbox] = useState({ inbox_path:"", pending:null })
  const lastAttachedPendingIdRef = useRef("")
  const resetAttachmentKeysRef = useRef(new Set())
  const downloadPollSequenceRef = useRef(0)
  const currentProjectRef = useRef(null)
  const playerFieldRef = useRef(null)
  const categoryFieldRef = useRef(null)
  const batchInputRef = useRef(null)

  useEffect(() => {
    currentProjectRef.current = project
  }, [project])

  async function jsonFetch(path, options = {}, timeoutMs = 30000) {
    const controller = new AbortController()
    const inheritedSignal = options.signal
    const onAbort = () => controller.abort()
    if (inheritedSignal) inheritedSignal.addEventListener("abort", onAbort, { once:true })
    const timeout = window.setTimeout(() => controller.abort(), timeoutMs)
    try {
      const response = await fetch(`${API}${path}`, { ...options, signal: controller.signal })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || data.message || `Request failed (${response.status})`)
      return data
    } catch (error) {
      if (error?.name === "AbortError") throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)} seconds`)
      throw error
    } finally {
      window.clearTimeout(timeout)
      if (inheritedSignal) inheritedSignal.removeEventListener("abort", onAbort)
    }
  }

  async function hydrateSummaries(rows) {
    return Promise.all((rows || []).map(async summary => {
      try {
        const detail = await jsonFetch(`/clip-finder/projects/${summary.project_id}`)
        const valid = (detail.project?.results || []).filter(result => isStandardVideo(result, detail.project?.player_name, detail.project?.category))
        return { ...summary, display_result_count: valid.length, display_approved_count: valid.filter(r => r.status === "approved").length }
      } catch {
        return { ...summary, display_result_count: Number(summary.result_count || 0), display_approved_count: Number(summary.approved_count || 0) }
      }
    }))
  }

  async function loadProjects() {
    setProjectsLoading(true)
    try {
      const [active, deleted] = await Promise.all([
        jsonFetch("/clip-finder/projects"),
        jsonFetch("/clip-finder/projects?include_deleted=true"),
      ])
      setProjects(await hydrateSummaries(active.projects))
      setDeletedProjects(await hydrateSummaries(deleted.projects))
    } finally {
      setProjectsLoading(false)
    }
  }

  useEffect(() => {
    const target = Number(searchProgress?.results || 0)
    if (!searchProgress) { setDisplayedCandidates(0); return }
    const timer = window.setInterval(() => {
      setDisplayedCandidates(current => {
        if (current >= target) return target
        return current + 1
      })
    }, 120)
    return () => window.clearInterval(timer)
  }, [searchProgress?.results, !!searchProgress])

  useEffect(() => {
    jsonFetch("/clip-finder/categories").then(d => setCategories(d.categories?.length ? d.categories : FALLBACK_CATEGORIES)).catch(() => setCategories(FALLBACK_CATEGORIES))
    loadProjects().catch(() => setProjectsLoading(false))
  }, [])

  useEffect(() => {
    let stopped = false
    async function pollDownloadInbox() {
      const sequence = ++downloadPollSequenceRef.current
      try {
        const data = await jsonFetch("/clip-finder/download-inbox", {}, 10000)
        if (stopped || sequence !== downloadPollSequenceRef.current) return
        setDownloadInbox(data)
        const pending = data.pending
        if (pending?.status === "attached") {
          const attachmentKey = `${pending.project_id || ""}:${pending.result_id || ""}`
          // Ignore a stale in-flight poll response after that attachment was reset.
          // The backend clears the pending job during delete, and a later poll removes
          // this guard once the stale attached response is gone.
          if (!resetAttachmentKeysRef.current.has(attachmentKey)) {
            const activeProject = currentProjectRef.current
            if (data.project && activeProject?.project_id === pending.project_id) {
              setProject(data.project)
            } else if (activeProject?.project_id === pending.project_id) {
              const refreshed = await jsonFetch(`/clip-finder/projects/${pending.project_id}`)
              if (!stopped) setProject(refreshed.project)
            }
            if (pending.pending_id !== lastAttachedPendingIdRef.current) {
              lastAttachedPendingIdRef.current = pending.pending_id
            }
          }
        }
      } catch {
        // Main backend availability UI handles connection failures.
      }
    }
    pollDownloadInbox()
    const timer = window.setInterval(pollDownloadInbox, 1000)
    return () => { stopped = true; window.clearInterval(timer) }
  }, [project?.project_id])

  useEffect(() => {
    function closeMenus(event) {
      if (!playerFieldRef.current?.contains(event.target)) { setPlayerResults([]); setActivePlayerResult(-1) }
      if (!categoryFieldRef.current?.contains(event.target)) setCategoryMenuOpen(false)
      if (!event.target.closest?.(".clip-change-selection")) setChangeSelectionId(null)
    }
    document.addEventListener("mousedown", closeMenus)
    return () => document.removeEventListener("mousedown", closeMenus)
  }, [])

  useEffect(() => {
    if (player.trim() && category) setValidationError("")
  }, [player, category])

  function updatePlayerSearch(value) {
    setPlayer(value); setError(null); setActivePlayerResult(-1)
    const query = value.trim()
    if (!query) return setPlayerResults([])
    fetch(`${API}/player-predictor/search?q=${encodeURIComponent(query)}`)
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setPlayerResults((data.results || []).map(x => typeof x === "string" ? { name: x } : x).filter(x => x?.name).sort((a,b) => String(a.name).localeCompare(String(b.name))).slice(0,50)))
      .catch(() => setPlayerResults([]))
  }

  function selectPlayer(name) { setPlayer(name); setPlayerResults([]); setActivePlayerResult(-1); setValidationError("") }
  function handlePlayerKeyDown(event) {
    if (event.key === "Escape") { setPlayerResults([]); setActivePlayerResult(-1); return }
    if (!playerResults.length) return
    if (event.key === "ArrowDown") { event.preventDefault(); setActivePlayerResult(i => Math.min(i + 1, playerResults.length - 1)) }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActivePlayerResult(i => Math.max(i - 1, 0)) }
    else if (event.key === "Enter" && activePlayerResult >= 0) { event.preventDefault(); selectPlayer(playerResults[activePlayerResult].name) }
  }

  async function createProject() {
    const missing = []
    if (!player.trim()) missing.push("player")
    if (!category) missing.push("video type")
    if (missing.length) {
      const phrase = missing.length === 1 ? missing[0] : `${missing.slice(0,-1).join(", ")} and ${missing.at(-1)}`
      setError(null); setValidationError(`Select a ${phrase} before searching.`); return
    }
    setBusy(true); setError(null); setValidationError(""); setPlayerResults([])
    try {
      const data = await jsonFetch("/clip-finder/projects", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ player_name:player.trim(), category }) })
      setProject(data.project)
      await searchProject(data.project.project_id)
      await loadProjects()
    } catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }

  async function openProject(id) {
    setBusy(true); setError(null)
    try { const data = await jsonFetch(`/clip-finder/projects/${id}`); setProject(data.project); setFilter("unreviewed") }
    catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }
  async function searchProject(id = project?.project_id) {
    if (!id) return
    setBusy(true); setError(null); setSearchProgress({ message:"Preparing exhaustive YouTube search…", completed:0, total:0, results:0 })
    try {
      const started = await jsonFetch(`/clip-finder/projects/${id}/search`, { method:"POST" })
      if (started.clip_finder_build !== EXPECTED_CLIP_FINDER_BUILD) {
        throw new Error(`Clip Finder backend build mismatch. Frontend expects ${EXPECTED_CLIP_FINDER_BUILD}, but port 8001 returned ${started.clip_finder_build || "an older unversioned backend"}. The replacement frontend is loaded, but the backend process is still running old code. Stop both Python/Uvicorn processes, then start the backend again from CourtVisionAI\\backend.`)
      }
      // Keep the existing project in memory, but do not reveal partial or stale
      // result lists while the exhaustive search is still running.
      if (started.job?.progress) setSearchProgress(started.job.progress)

      let lastProgressSignature = ""
      let lastProgressAt = Date.now()
      while (true) {
        await new Promise(resolve => setTimeout(resolve, 750))
        const status = await jsonFetch(`/clip-finder/projects/${id}/search-status`)
        if (status.clip_finder_build !== EXPECTED_CLIP_FINDER_BUILD) {
          throw new Error(`Clip Finder backend changed during search. Expected ${EXPECTED_CLIP_FINDER_BUILD}, received ${status.clip_finder_build || "an older unversioned backend"}.`)
        }
        const state = status.job?.status
        if (status.job?.progress) {
          setSearchProgress(status.job.progress)
          const signature = JSON.stringify({
            results: status.job.progress.results,
            completed: status.job.progress.completed,
            phase: status.job.progress.phase,
            message: status.job.progress.message,
            heartbeat: status.job.progress.heartbeat_serial,
          })
          if (signature !== lastProgressSignature) {
            lastProgressSignature = signature
            lastProgressAt = Date.now()
          }
        }
        if (state === "running" && Date.now() - lastProgressAt > 240000) {
          throw new Error("Clip Finder received no backend heartbeat for 4 minutes. Check the backend terminal for the exact stalled stage, then retry.")
        }
        if (state === "complete") {
          if (status.project) setProject(status.project)
          return
        }
        if (state === "failed") {
          // Never silently restart a failed job. The old behavior created an
          // endless 60-second loop at zero candidates when quota/configuration
          // was unavailable. Surface the real backend error immediately.
          throw new Error(String(status.job?.error || "YouTube search failed."))
        }
      }
    } catch (e) {
      setError(courtVisionError(e, "Clip Finder Search"))
    } finally {
      setSearchProgress(null)
      setBusy(false)
    }
  }
  async function updateResult(resultId, patch) {
    if (!project) return
    setError(null)
    try {
      const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/results/${resultId}`, { method:"PATCH", headers:{"Content-Type":"application/json"}, body:JSON.stringify(patch) })
      setProject(data.project); setRankError("")
    } catch (e) { setError(courtVisionError(e)) }
  }
  async function attachFile(resultId, file) {
    if (!file) return
    const body = new FormData(); body.append("file", file)
    setBusy(true); setError(null)
    try { const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/results/${resultId}/attach`, { method:"POST", body }); setProject(data.project) }
    catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }
  function deleteAttachedVideo(result) {
    if (!project || !result) return
    setConfirmDialog({
      title: "Delete Local MP4?",
      message: "Delete this MP4 and reset the source?",
      confirmLabel: "Delete MP4",
      danger: true,
      actionType: "deleteAttachment",
      projectId: project.project_id,
      resultId: result.result_id,
    })
  }

  async function attachBatch(files) {
    const selected = Array.from(files || []); if (!selected.length) return
    const body = new FormData(); selected.forEach(file => body.append("files", file))
    setBusy(true); setError(null)
    try {
      const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/attach-batch`, { method:"POST", body }); setProject(data.project)
      if (data.unmatched?.length) setError({ title:"Some Files Were Not Matched", message:`${data.unmatched.length} file(s) could not be matched automatically. Attach those individually.`, details:"" })
    } catch (e) { setError(courtVisionError(e)) } finally { setBusy(false); if (batchInputRef.current) batchInputRef.current.value = "" }
  }

  async function beginAutoDownload(result) {
    if (!project || !result?.youtube_url) return
    const attachmentKey = `${project.project_id}:${result.result_id}`
    resetAttachmentKeysRef.current.delete(attachmentKey)
    downloadPollSequenceRef.current += 1

    const optimisticPending = {
      pending_id: `starting-${Date.now()}`,
      project_id: project.project_id,
      result_id: result.result_id,
      video_id: result.video_id,
      title: result.title,
      youtube_url: result.youtube_url,
      status: "waiting",
      message: "Waiting for the MP4 download to finish…",
    }
    setDownloadInbox(current => ({ ...current, pending: optimisticPending }))

    // Open YouTube directly from the user's click so browser popup protection
    // never blocks it. CourtVision then registers the durable download session.
    window.open(result.youtube_url, "_blank", "noopener,noreferrer")

    setError(null)
    try {
      const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/download-inbox/begin`, {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({ result_id:result.result_id }),
      })
      setDownloadInbox({ inbox_path:data.inbox_path, pending:data.pending })
      if (data.project) setProject(data.project)
    } catch (e) {
      setDownloadInbox(current => ({ ...current, pending:null }))
      setError(courtVisionError(e, "Download Automation"))
    }
  }

  async function cancelAutoDownload() {
    try {
      const data = await jsonFetch("/clip-finder/download-inbox/cancel", { method:"POST" })
      setDownloadInbox(current => ({ ...current, pending:data.pending }))
    } catch (e) { setError(courtVisionError(e, "Download Automation")) }
  }

  async function openDownloadInbox() {
    try {
      const data = await jsonFetch("/clip-finder/download-inbox/open", { method:"POST" })
      setDownloadInbox(current => ({ ...current, inbox_path:data.inbox_path }))
    } catch (e) { setError(courtVisionError(e, "Download Automation")) }
  }

  async function openAttachedLocation(result) {
    if (!project || !result) return
    setError(null)
    try {
      await jsonFetch(`/clip-finder/projects/${project.project_id}/results/${result.result_id}/attachment/open-location`, {
        method:"POST",
      })
    } catch (e) {
      setError(courtVisionError(e, "Open File Location"))
    }
  }

  async function clearDownloadStatus() {
    try {
      await jsonFetch("/clip-finder/download-inbox/clear", { method:"POST" })
      setDownloadInbox(current => ({ ...current, pending:null }))
    } catch (e) { setError(courtVisionError(e, "Download Automation")) }
  }

  function requestTrash(id) {
    setConfirmDialog({
      title: "Move Project to Recently Deleted?",
      message: "The project will leave Current Projects and can be restored later.",
      confirmLabel: "Move to Recently Deleted",
      danger: false,
      actionType: "trash",
      projectId: id,
    })
  }
  async function restoreProject(id) {
    setBusy(true); setError(null)
    try {
      await jsonFetch(`/clip-finder/projects/${id}/restore`, { method:"POST" })
      await loadProjects()
      setShowDeleted(false)
    } catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }
  function requestPermanentDelete(id) {
    setConfirmDialog({
      title: "Delete Project Forever?",
      message: "This permanently removes the Clip Finder project. This action cannot be undone.",
      confirmLabel: "Delete Forever",
      danger: true,
      actionType: "delete",
      projectId: id,
    })
  }
  async function runConfirmedAction() {
    const dialog = confirmDialog
    if (!dialog || confirmBusy) return
    const id = dialog.projectId
    setConfirmBusy(true)
    setError(null)
    try {
      if (dialog.actionType === "trash") {
        // The route only changes a few JSON fields, so it should return quickly.
        // A hard timeout guarantees this modal can never remain on Working forever.
        await jsonFetch(`/clip-finder/projects/${id}/trash`, { method:"POST" }, 15000)
        const moved = projects.find(item => item.project_id === id)
        setProjects(items => items.filter(item => item.project_id !== id))
        if (moved) setDeletedProjects(items => [{ ...moved, trashed:true, trashed_at:new Date().toISOString() }, ...items.filter(item => item.project_id !== id)])
        if (project?.project_id === id) setProject(null)
      } else if (dialog.actionType === "delete") {
        await jsonFetch(`/clip-finder/projects/${id}`, { method:"DELETE" }, 15000)
        setDeletedProjects(items => items.filter(item => item.project_id !== id))
        setProjects(items => items.filter(item => item.project_id !== id))
        if (project?.project_id === id) setProject(null)
      } else if (dialog.actionType === "deleteAttachment") {
        const attachmentKey = `${id}:${dialog.resultId}`
        resetAttachmentKeysRef.current.add(attachmentKey)
        // Invalidate every older inbox response before changing local state.
        downloadPollSequenceRef.current += 1

        // Reset the card immediately so the interface never remains visually
        // attached while the delete request or a stale inbox poll is finishing.
        setProject(current => {
          if (!current || current.project_id !== id) return current
          return {
            ...current,
            results: (current.results || []).map(result => {
              if (result.result_id !== dialog.resultId) return result
              const reset = { ...result }
              delete reset.local_file_path
              delete reset.download_attached_at
              delete reset.attachment_status
              delete reset.attached_original_filename
              delete reset.attached_file_path
              delete reset.attached_filename
              delete reset.local_video_path
              delete reset.media_path
              delete reset.attachment_session_id
              reset.attachment_reset_at = new Date().toISOString()
              return reset
            }),
          }
        })
        setDownloadInbox(current => ({ ...current, pending:null }))

        const data = await jsonFetch(`/clip-finder/projects/${id}/results/${dialog.resultId}/attachment`, { method:"DELETE" }, 30000)
        if (data?.project) {
          // Force the exact source into its normal pre-download state even if an
          // old backend field survives in a cached response.
          setProject({
            ...data.project,
            results: (data.project.results || []).map(result => {
              if (result.result_id !== dialog.resultId) return result
              const reset = { ...result }
              for (const key of ["local_file_path","download_attached_at","attachment_status","attached_original_filename","attached_file_path","attached_filename","local_video_path","media_path","attachment_session_id"]) delete reset[key]
              reset.attachment_reset_at = reset.attachment_reset_at || new Date().toISOString()
              return reset
            }),
          })
        }
      }
      // Close immediately after the mutation succeeds. The potentially slower
      // full-list hydration happens in the background and cannot trap the dialog.
      setConfirmDialog(null)
      loadProjects().catch(() => {})
    } catch (e) {
      // Always release the modal on timeout or backend error. A user can retry,
      // and a background refresh reconciles cases where the server completed
      // the action but the response was interrupted.
      setConfirmDialog(null)
      setError(courtVisionError(e, dialog.actionType === "deleteAttachment" ? "Delete MP4" : dialog.actionType === "delete" ? "Delete Project" : "Move Project"))
      loadProjects().catch(() => {})
    } finally {
      setConfirmBusy(false)
    }
  }

  const standardResults = useMemo(() => (project?.results || []).filter(result => isStandardVideo(result, project?.player_name, project?.category)), [project])
  const counts = useMemo(() => ({
    all: standardResults.length,
    unreviewed: standardResults.filter(r => !["approved","rejected"].includes(r.status)).length,
    approved: standardResults.filter(r => r.status === "approved").length,
    rejected: standardResults.filter(r => r.status === "rejected").length,
    ready: standardResults.filter(r => r.status === "approved" && r.local_file_path).length,
  }), [standardResults])
  const reviewComplete = counts.all > 0 && counts.unreviewed === 0
  const visible = useMemo(() => filter === "all" ? standardResults : filter === "unreviewed" ? standardResults.filter(r => !["approved","rejected"].includes(r.status)) : standardResults.filter(r => r.status === filter), [standardResults, filter])
  const approved = useMemo(() => standardResults.filter(r => r.status === "approved"), [standardResults])
  const attachedApproved = useMemo(() => approved.filter(r => r.local_file_path), [approved])
  const allApprovedAttached = approved.length > 0 && attachedApproved.length === approved.length
  const allInstances = useMemo(() => approved.flatMap(result => normalizedInstances(result).map(instance => ({ result, instance }))), [approved])
  const ranked = allInstances.filter(({result,instance}) => result.local_file_path && Number(instance.rank_number) >= 1 && Number(instance.rank_number) <= 10)
  const rankNumbers = ranked.map(({instance}) => Number(instance.rank_number))
  const validTop10 = reviewComplete && ranked.length === 10 && new Set(rankNumbers).size === 10 && [1,2,3,4,5,6,7,8,9,10].every(n => rankNumbers.includes(n))
  const pendingDownload = downloadInbox?.pending || null
  const activeDownload = ["waiting","detected","attaching"].includes(pendingDownload?.status)
  const pendingForCurrentProject = pendingDownload?.project_id === project?.project_id

  async function updateInstances(result, instances) { await updateResult(result.result_id, { clip_instances: instances }) }
  function setClipCount(result, value) {
    const count = Math.max(1, Math.min(30, Number(value) || 1))
    updateResult(result.result_id, { clip_count: count })
  }
  function setInstanceField(result, instanceId, field, value) {
    const instances = normalizedInstances(result).map(instance => instance.instance_id === instanceId ? { ...instance, [field]: value } : instance)
    if (field === "rank_number" && value !== null) {
      const duplicate = allInstances.find(({instance}) => instance.instance_id !== instanceId && Number(instance.rank_number) === Number(value))
      if (duplicate) { setRankError(`Rank #${value} is already assigned to another clip.`); return }
    }
    updateInstances(result, instances)
  }

  async function openCandidateEditor() {
    if (!allApprovedAttached) {
      setError({ title:"Attach Every Approved MP4 First", message:`${Math.max(0, counts.approved - counts.ready)} approved source file${Math.max(0, counts.approved - counts.ready) === 1 ? " is" : "s are"} still missing. CourtVision will unlock the editor after every approved source is attached.`, details:"" })
      return
    }
    setBusy(true); setError(null)
    try { const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/build-candidate-editor-project`, { method:"POST" }); onOpenEditor?.(data.editor_project.project_id) }
    catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }
  async function buildTimeline() {
    if (!validTop10) { setRankError("Assign each rank from 1 through 10 once. The same source video can supply multiple ranked clip instances."); return }
    setBusy(true); setError(null); setRankError("")
    try { const data = await jsonFetch(`/clip-finder/projects/${project.project_id}/build-editor-project`, { method:"POST" }); onOpenEditor?.(data.editor_project.project_id) }
    catch (e) { setError(courtVisionError(e)) } finally { setBusy(false) }
  }

  return <div className="clip-finder-page">
    <div className="clip-finder-header"><span className="editor-kicker">Research Workspace</span><h1>Clip Finder</h1><p>Find, review, rank, and send NBA plays directly into a Top 10 timeline.</p></div>
    {error && <div className="clip-error" role="alert"><strong>{error.title || "Clip Finder Error"}</strong><span>{error.message || String(error)}</span>{error.details && error.details !== error.message && <details><summary>Show details</summary><code>{error.details}</code></details>}<button type="button" aria-label="Dismiss error" onClick={()=>setError(null)}>×</button></div>}
    {validationError && <div className="clip-validation-error">{validationError}</div>}

    {!project && <>
      <div className="clip-search-card">
        <label className={!player.trim() && validationError ? "clip-field-missing" : ""}>Player Name
          <div className="clip-player-autocomplete" ref={playerFieldRef}>
            <input value={player} onChange={e => updatePlayerSearch(e.target.value)} onFocus={() => player.trim() && updatePlayerSearch(player)} onKeyDown={handlePlayerKeyDown} placeholder="Select Player" autoComplete="off" />
            {playerResults.length > 0 && <div className="clip-player-results">{playerResults.map((item,index) => <button type="button" key={`${item.name}-${index}`} className={index===activePlayerResult?"active":""} onMouseDown={e=>e.preventDefault()} onClick={()=>selectPlayer(item.name)}>{item.name}</button>)}</div>}
          </div>
        </label>
        <label className={!category && validationError ? "clip-field-missing" : ""}>Top 10 Video
          <div className="clip-category-select" ref={categoryFieldRef}>
            <button type="button" className={`clip-category-trigger${!category?" placeholder":""}`} onClick={()=>setCategoryMenuOpen(o=>!o)}><span>{category || "Select Video Type"}</span><span className="clip-category-chevron">⌄</span></button>
            {categoryMenuOpen && <div className="clip-category-menu">{(categories.length?categories:FALLBACK_CATEGORIES).map(x=><button type="button" className={category===x?"selected":""} key={x} onClick={()=>{setCategory(x);setCategoryMenuOpen(false)}}>{x}</button>)}</div>}
          </div>
        </label>
        <button className="clip-primary clip-create-button" onClick={createProject} disabled={busy}>{busy?"Searching…":"Create Project & Search"}</button>
      </div>

      <div className="clip-projects">
        <div className="clip-project-list-heading"><h2>{showDeleted ? "Recently Deleted" : "Saved Clip Finder Projects"}</h2><button onClick={()=>setShowDeleted(v=>!v)}>{showDeleted ? "Back to Projects" : `Recently Deleted${deletedProjects.length ? ` (${deletedProjects.length})` : ""}`}</button></div>
        {(showDeleted ? deletedProjects : projects).map(p => <div className="clip-project-row" key={p.project_id} role="button" tabIndex={0} onClick={()=>!showDeleted&&openProject(p.project_id)} onKeyDown={e=>e.key==="Enter"&&!showDeleted&&openProject(p.project_id)}>
          <PlayerHeadshot playerName={p.player_name} className="clip-project-headshot" />
          <div className="clip-project-info"><strong>{p.player_name} — {p.category}</strong><span>{p.display_result_count ?? p.result_count ?? 0} found · {p.display_approved_count ?? p.approved_count ?? 0} approved</span></div>
          <div className="clip-project-actions">{showDeleted ? <><button onClick={e=>{e.stopPropagation();restoreProject(p.project_id)}}>Restore</button><button className="danger" onClick={e=>{e.stopPropagation();requestPermanentDelete(p.project_id)}}>Delete Forever</button></> : <><button onClick={e=>{e.stopPropagation();openProject(p.project_id)}}>Open Project</button><button className="danger" onClick={e=>{e.stopPropagation();requestTrash(p.project_id)}}>Delete</button></>}</div>
        </div>)}
        {projectsLoading ? <div className="clip-empty clip-loading-projects"><span className="clip-loading-spinner" aria-hidden="true" />Loading projects…</div> : !(showDeleted ? deletedProjects : projects).length && <div className="clip-empty">{showDeleted ? "Recently Deleted is empty." : "No saved projects yet."}</div>}
      </div>
    </>}

    {project && <>
      <div className="clip-project-toolbar"><div><button onClick={()=>{setProject(null);loadProjects().catch(()=>{})}}>← Projects</button><strong>{project.player_name} — {project.category}</strong></div><button onClick={()=>searchProject()} disabled={busy}>{busy?"Working…":"Search Again"}</button></div>
      <div className="clip-count-grid">{[["Found",counts.all],["Remaining",counts.unreviewed],["Approved",counts.approved],["Rejected",counts.rejected]].map(([k,v])=><div key={k}><strong>{v}</strong><span>{k}</span></div>)}</div>

      <section className="clip-ranking-panel">
        <div className="clip-ranking-heading"><div><h2>Top 10 Order</h2><p>One source video can supply several plays. Set how many clips you expect, add notes, then rank the final ten.</p></div><div className="clip-ranking-summary">{allInstances.length} clip slots · {counts.ready} files attached</div></div>
        {!reviewComplete && <div className="clip-workflow-notice"><strong>Finish reviewing before building your Top 10.</strong><span>Approve or reject all {counts.unreviewed} remaining video{counts.unreviewed===1?"":"s"} to unlock importing and ranking.</span></div>}
        {reviewComplete && <>
          <div className={`clip-download-automation ${pendingDownload?.status || "idle"}`}>
            <div>
              <strong>{activeDownload ? `Waiting for: ${pendingDownload?.title || "source video"}` : pendingDownload?.status === "attached" ? "Source video attached automatically" : pendingDownload?.status === "failed" ? "Automatic attachment needs attention" : "Automatic download inbox ready"}</strong>
              <span>{activeDownload ? (pendingDownload?.message || "Download the MP4 into the CourtVision Inbox folder.") : pendingDownload?.status === "attached" ? `${pendingDownload?.title || "Video"} is attached and ready.` : pendingDownload?.status === "failed" ? `${pendingDownload?.message || "Attachment failed"} ${pendingDownload?.error || ""}` : `Set your browser downloader to save MP4 files into ${downloadInbox?.inbox_path || "CourtVisionAI\\data\\clip_finder\\inbox"}. CourtVision handles one download at a time.`}</span>
            </div>
            <div className="clip-download-automation-actions">
              <button type="button" onClick={openDownloadInbox}>Open Inbox Folder</button>
              {activeDownload && <button type="button" className="danger" onClick={cancelAutoDownload}>Cancel Waiting Download</button>}
              {!activeDownload && pendingDownload && <button type="button" onClick={clearDownloadStatus}>Dismiss</button>}
            </div>
          </div>
          <div className="clip-import-stage"><div><strong>Import approved source videos</strong><span>Attach each source once—even when it contains several plays. CourtVision will duplicate that source into separate timeline clip slots for trimming.</span></div><label className="clip-batch-button">{busy?"Importing…":"Import Multiple Videos"}<input ref={batchInputRef} type="file" accept="video/*" multiple disabled={busy} onChange={e=>attachBatch(e.target.files)}/></label></div>
          <div className="clip-import-progress"><span>{counts.ready}/{counts.approved} approved source files attached</span><span>{Math.max(0,counts.approved-counts.ready)} still missing</span></div>
          {approved.length>0 && <div className="clip-editor-gate"><button className="clip-secondary-wide" onClick={openCandidateEditor} disabled={busy || !allApprovedAttached}>{allApprovedAttached ? `Open All ${allInstances.length} Clip Slot${allInstances.length===1?"":"s"} in CourtVision Editor` : `Attach All Approved MP4s to Unlock Editor (${counts.ready}/${counts.approved})`}</button>{!allApprovedAttached && <span>Every approved source must have its local MP4 attached before any clip slots can enter the editor.</span>}</div>}
          <div className="clip-ranking-list">{approved.map(result => {
            const isPendingSource = pendingDownload?.result_id===result.result_id&&activeDownload
            const attachmentKey = `${project?.project_id || ""}:${result.result_id}`
            const isAttached = Boolean(result.local_file_path) && !resetAttachmentKeysRef.current.has(attachmentKey)
            const sourceStatus = isAttached ? "attached" : isPendingSource ? "waiting" : "ready"
            return <div className={`clip-source-ranking ${sourceStatus}`} key={result.result_id}>
              <div className="clip-source-card-top">
                <div className="clip-source-thumbnail-wrap">
                  <img className="clip-source-thumbnail" src={result.thumbnail} alt=""/>
                  <span className={`clip-source-status-badge ${sourceStatus}`}>
                    {sourceStatus==="attached"?"Attached":sourceStatus==="waiting"?"Waiting":"Ready"}
                  </span>
                </div>
                <div className="clip-source-main">
                  <div className="clip-source-title-row">
                    <div className="clip-source-info">
                      <strong title={result.title}>{result.title}</strong>
                      <span>{isAttached?"MP4 attached successfully. This YouTube source is complete and synced to its local video.":isPendingSource?(pendingDownload.message||"Waiting for the MP4 download to finish…"):"Open this YouTube video, then save its MP4 into the CourtVision Inbox."}</span>
                    </div>
                    <label className="clip-source-count">
                      <span>Clip slots</span>
                      <input type="number" min="1" max="30" value={normalizedInstances(result).length} onChange={e=>setClipCount(result,e.target.value)}/>
                    </label>
                  </div>
                  <div className="clip-source-actions">
                    {isAttached
                      ? <><span className="clip-attached clip-source-action-status">MP4 Attached ✓</span><button type="button" className="clip-source-youtube attached" onClick={()=>openAttachedLocation(result)}>Open File Location</button><button type="button" className="clip-delete-attached" onClick={()=>deleteAttachedVideo(result)} disabled={busy}>Delete MP4</button></>
                      : <button type="button" className="clip-source-youtube" onClick={()=>beginAutoDownload(result)} disabled={!result.youtube_url||(activeDownload&&pendingDownload?.result_id!==result.result_id)}>{isPendingSource?"Waiting for Download…":"Download MP4"}</button>}
                  </div>
                </div>
              </div>
              <div className="clip-instance-list">{normalizedInstances(result).map((instance,index)=><div className="clip-instance-row" key={instance.instance_id}>
                <span className="clip-instance-number">{index+1}</span>
                <div className="clip-instance-field">
                  <span className="clip-instance-field-label">Clip name</span>
                  <input value={instance.label||""} onChange={e=>setInstanceField(result,instance.instance_id,"label",e.target.value)} placeholder={`Clip ${index+1}`}/>
                </div>
                <div className="clip-instance-field notes">
                  <span className="clip-instance-field-label">Timestamp or notes</span>
                  <input value={instance.notes||""} onChange={e=>setInstanceField(result,instance.instance_id,"notes",e.target.value)} placeholder="Time, play description, opponent, or note"/>
                </div>
                <label className="clip-instance-rank"><span>Rank</span><input type="number" min="1" max="10" disabled={!isAttached} value={instance.rank_number??""} onChange={e=>setInstanceField(result,instance.instance_id,"rank_number",e.target.value===""?null:Number(e.target.value))} placeholder="1–10"/></label>
              </div>)}</div>
            </div>
          })}</div>
          {rankError&&<div className="clip-rank-error">{rankError}</div>}
          <button className="clip-primary build" onClick={buildTimeline} disabled={busy||!validTop10}>Lock In Top 10 & Build Final Timeline</button>
          {!validTop10&&<small>Assign ranks 1–10 exactly once. The same source video may fill several ranked clip slots; each slot becomes independently trimmable in the existing editor.</small>}
        </>}
      </section>

      <section className="clip-results-panel">
        <div className="clip-results-header"><div><h2>Video Results</h2><p>Standard NBA regular-season and playoff videos only. Shorts, contests, NBA 2K, college, and high-school footage are excluded.</p></div>{!searchProgress&&<div className="clip-filters">{["unreviewed","approved","rejected","all"].map(x=><button className={filter===x?"active":""} onClick={()=>setFilter(x)} key={x}>{x[0].toUpperCase()+x.slice(1)}</button>)}</div>}</div>
        {searchProgress ? <div className="clip-exhaustive-search">
          <div className="clip-search-spinner" aria-hidden="true" />
          <h3>Searching all available YouTube results</h3>
          <p>{searchProgress.message || "Following every available search page…"}</p>
          <div className="clip-search-stats">
            <span>{Number(displayedCandidates||0).toLocaleString()} candidates found</span>
            {searchProgress.total>0&&<span>{Math.min(Number(searchProgress.completed||0)+1,Number(searchProgress.total))} of {searchProgress.total} searches</span>}
            {searchProgress.pages>0&&<span>Page {searchProgress.pages}</span>}
            <span>{etaLabel(searchProgress.estimated_seconds_remaining)}</span>
          </div>
          <small>Candidates count upward one at a time while CourtVision searches relevance, highest-view results, trusted sources, and supplemental YouTube pages. Results remain hidden until metadata verification, filtering, and ranking finish.</small>
        </div> : <div className="clip-result-list">{visible.map(r=><article className="clip-result" key={r.result_id}>
          <div className="clip-result-thumbnail-wrap"><img src={r.thumbnail} alt=""/><span className="clip-duration">{secondsLabel(r.duration_seconds)}</span></div>
          <div className="clip-result-main">
            <div className="clip-result-top">
              <span className="clip-rank-score">Suggested {r.suggestion_score}/100</span>
              <span className="clip-view-count">{Number(r.views||0).toLocaleString()} views</span>
            </div>
            <h3 title={r.title}>{r.title}</h3>
            <div className="clip-result-meta">
              <span className="clip-channel" title={r.channel_title||"Unknown Channel"}>{r.channel_title||"Unknown Channel"}</span>
              <span className="clip-published-date">{r.published_at?.slice(0,10)||"Unknown Date"}</span>
            </div>
            <div className="clip-actions"><button className="youtube" onClick={()=>window.open(r.youtube_url,"_blank","noopener,noreferrer")}>Open on YouTube</button>
              {!["approved","rejected"].includes(r.status) ? <><button className="approve" onClick={()=>updateResult(r.result_id,{status:"approved"})}>Approve</button><button className="reject" onClick={()=>updateResult(r.result_id,{status:"rejected"})}>Reject</button></> : <div className="clip-change-selection"><button onClick={e=>{e.stopPropagation();setChangeSelectionId(changeSelectionId===r.result_id?null:r.result_id)}}>Change Selection</button>{changeSelectionId===r.result_id&&<div className="clip-change-menu"><button onClick={()=>{updateResult(r.result_id,{status:"approved"});setChangeSelectionId(null)}}>Approve</button><button onClick={()=>{updateResult(r.result_id,{status:"rejected"});setChangeSelectionId(null)}}>Reject</button><button onClick={()=>{updateResult(r.result_id,{status:"unreviewed"});setChangeSelectionId(null)}}>Return to Unreviewed</button></div>}</div>}
              {r.status==="approved"&&!r.local_file_path&&<button className="clip-auto-download-button" onClick={()=>beginAutoDownload(r)} disabled={activeDownload&&pendingDownload?.result_id!==r.result_id}>{pendingDownload?.result_id===r.result_id&&activeDownload?"Waiting for Download…":"Download MP4"}</button>}
              {r.status==="approved"&&r.local_file_path&&<span className="clip-attached">MP4 Attached · {normalizedInstances(r).length} clip slot{normalizedInstances(r).length===1?"":"s"}</span>}
            </div>
          </div>
        </article>)}{!visible.length&&<div className="clip-empty">No standard videos in this filter.</div>}</div>}
      </section>
    </>}
    {confirmDialog && <div className="clip-modal-backdrop" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget&&!confirmBusy)setConfirmDialog(null)}}>
      <div className="clip-modal" role="dialog" aria-modal="true" aria-labelledby="clip-confirm-title">
        <h2 id="clip-confirm-title">{confirmDialog.title}</h2>
        <p>{confirmDialog.message}</p>
        <div className="clip-modal-actions">
          <button type="button" onClick={()=>setConfirmDialog(null)} disabled={confirmBusy}>Cancel</button>
          <button type="button" className={confirmDialog.danger?"danger":"primary"} onClick={runConfirmedAction} disabled={confirmBusy}>{confirmBusy?"Working…":confirmDialog.confirmLabel}</button>
        </div>
      </div>
    </div>}
  </div>
}
