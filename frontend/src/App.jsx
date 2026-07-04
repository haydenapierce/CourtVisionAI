import "./App.css"
import { useEffect, useRef, useState } from "react"
import logo from "./assets/nbatop10-logo.png"

const API = "http://127.0.0.1:8002"

function parseNumberInput(value) {
  if (value === null || value === undefined || value === "") return 0
  return Number(String(value).replace(/,/g, "")) || 0
}

function formatDateTime(value) {
  if (!value) return "—"

  const date = new Date(value)

  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit"
  })
}

function formatDateLong(value) {
  if (!value) return "—"

  const date = new Date(`${value}T00:00:00`)

  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric"
  })
}

function formatDateShort(value) {
  if (!value) return "—"

  const date = new Date(`${value}T00:00:00`)

  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric"
  })
}


function formatDateFull(value) {
  if (!value) return "—"

  const date = new Date(`${value}T00:00:00`)

  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric"
  })
}

function formatMoney(value) {
  const number = Number(value || 0)

  return `$${number.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`
}


function getForecastVideoRevenue(item) {
  return Number(
    item?.synced_revenue ??
    item?.revenue ??
    item?.estimated_revenue ??
    item?.manual_revenue ??
    0
  )
}

function getForecastVideoRpm(item) {
  return Number(
    item?.synced_rpm ??
    item?.rpm ??
    item?.estimated_rpm ??
    item?.manual_rpm ??
    0
  )
}


function formatDisplayText(value) {
  if (!value) return "—"

  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, char => char.toUpperCase())
}

function formatVideoTime(value) {
  const totalSeconds = Math.max(0, Math.floor(Number(value || 0)))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60

  return `${minutes}:${String(seconds).padStart(2, "0")}`
}

function periodOrder(period) {
  const order = {
    lifetime: 1,
    "365d": 2,
    "90d": 3,
    "28d": 4,
    "7d": 5
  }

  return order[period] || 99
}

function periodLabel(period) {
  const labels = {
    lifetime: "Lifetime",
    "365d": "Last 365 Days",
    "90d": "Last 90 Days",
    "28d": "Last 28 Days",
    "7d": "Last 7 Days"
  }

  return labels[period] || formatDisplayText(period)
}

function normalizeRevenuePeriod(period) {
  if (period === "30d") return "28d"
  return period || "lifetime"
}

function normalizeContentFormat(value) {
  const text = String(value || "").trim().toLowerCase()

  if (text.includes("top 10") || text.includes("top ten")) return "Top 10"

  return "Solo Highlight"
}


function cleanStrategyFormat(value) {
  let text = String(value || "Top 10 Plays").trim()

  text = text.replace(/Top 10\s+Top 10/gi, "Top 10")
  text = text.replace(/Dunks/gi, "Dunks")
  text = text.replace(/Poster Dunk/gi, "Dunk")
  text = text.replace(/Handles/gi, "Crossovers")
  text = text.replace(/Top 10 Shots/gi, "Top 10 Clutch Shots")
  text = text.replace(/Top 10 Clutch Plays/gi, "Top 10 Clutch Shots")
  text = text.replace(/Career Highlights/gi, "Plays")
  text = text.replace(/History Countdown/gi, "Top 10 Plays")

  const lower = text.toLowerCase()

  if (lower.includes("playoff")) return "Top 10 Playoff Moments"
  if (lower.includes("finals")) return "Top 10 Finals Plays"
  if (lower.includes("game winner")) return "Top 10 Game Winners"
  if (lower.includes("clutch")) return "Top 10 Clutch Shots"
  if (lower.includes("3") || lower.includes("three")) return "Top 10 3-Pointers"
  if (lower.includes("assist") || lower.includes("pass")) return "Top 10 Assists"
  if (lower.includes("block")) return "Top 10 Blocks"
  if (lower.includes("dunk") || lower.includes("poster")) return "Top 10 Dunks"
  if (lower.includes("play")) return "Top 10 Plays"

  return "Top 10 Plays"
}

function cleanStrategyName(value) {
  let text = String(value || "").trim()
  text = text.replace(/\s+/g, " ")
  text = text.replace(/\s+Top 10.*$/i, "")
  return text.trim()
}

function isBadStrategyIdea(item) {
  const format = String(item?.format || item?.content_type || "").toLowerCase()
  const source = String(item?.source || "").toLowerCase()
  const reason = String(item?.reason || "").toLowerCase()
  const topic = String(item?.topic || item?.player || item?.player_name || item?.name || "").toLowerCase()
  const realRevenue = Number(item?.total_revenue || item?.synced_revenue || item?.average_revenue || 0)

  const curatedNames = new Set([
    "mason plumlee", "allen iverson", "magic johnson", "larry bird", "wilt chamberlain",
    "michael jordan", "kobe bryant", "pete maravich", "vince carter", "stephen curry",
    "lebron james", "kareem abdul-jabbar", "hakeem olajuwon", "nikola jokic", "steve nash",
    "jason williams", "shaquille o'neal", "dominique wilkins", "david robinson",
    "bill russell", "tim duncan", "reggie miller", "ray allen", "damian lillard",
    "chris paul", "blake griffin", "derrick rose", "nate robinson", "ja morant",
    "russell westbrook", "kyrie irving", "george gervin", "connie hawkins",
    "david thompson", "earl monroe", "walt frazier", "bernard king", "elvin hayes",
    "bob mcadoo", "clyde drexler", "shawn kemp", "gary payton", "john stockton",
    "manu ginobili", "pau gasol", "yao ming", "dikembe mutombo", "dwight howard",
    "tracy mcgrady", "kevin durant", "carmelo anthony", "jerry west", "grant hill",
    "victor wembanyama", "charles barkley", "julius erving", "jason kidd"
  ])

  const isDatabaseOnly =
    source.includes("player database") ||
    source.includes("idea lab") ||
    reason.includes("idea lab top pick") ||
    reason.includes("player database") ||
    reason.includes("idea lab/player database")

  return (
    format.includes("history countdown") ||
    source.includes("history countdown") ||
    topic.includes("greatest fastbreak plays ever") ||
    topic.includes("smoothest plays") ||
    topic.includes("before jordan") ||
    (isDatabaseOnly && realRevenue <= 0 && !curatedNames.has(topic))
  )
}

function App() {
  const [tab, setTab] = useState("dashboard")

  const [stats, setStats] = useState({})
  const [savedVideos, setSavedVideos] = useState([])
  const [rankings, setRankings] = useState([])
  const [players, setPlayers] = useState([])
  const [ideaLabExpandedLists, setIdeaLabExpandedLists] = useState({})

  function isIdeaLabListExpanded(key) {
    return !!ideaLabExpandedLists[key]
  }

  function toggleIdeaLabList(key) {
    setIdeaLabExpandedLists(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  function ideaLabVisibleItems(items, key) {
    const safeItems = Array.isArray(items) ? items : []
    return isIdeaLabListExpanded(key) ? safeItems : safeItems.slice(0, 5)
  }

  const [channelBrain, setChannelBrain] = useState(null)
  const [strategyShuffleIndex, setStrategyShuffleIndex] = useState(0)

  const [revenueSummary, setRevenueSummary] = useState(null)
  const [revenueChecklist, setRevenueChecklist] = useState(null)
  const [channelRevenue, setChannelRevenue] = useState([])
  const [videoRevenue, setVideoRevenue] = useState([])
  const [youtubeRevenueStatus, setYoutubeRevenueStatus] = useState(null)
  const [youtubeRevenueSyncing, setYoutubeRevenueSyncing] = useState(false)
  const [revenuePeriod, setRevenuePeriod] = useState("lifetime")


  const [studioTypes, setStudioTypes] = useState([])
  const [studioBreakdowns, setStudioBreakdowns] = useState([])
  const [studioSummary, setStudioSummary] = useState(null)
  const [studioIntelligence, setStudioIntelligence] = useState(null)

  const [studioForm, setStudioForm] = useState({
    breakdown_type: "country",
    scope: "channel",
    video_id: "",
    title: "",
    period_type: "28d",
    item_name: "",
    views: "",
    watch_time_hours: "",
    average_view_duration: "",
    impressions: "",
    ctr: "",
    estimated_revenue: "",
    rpm: "",
    cpm: "",
    subscribers: "",
    percentage: "",
    extra_metric_name: "",
    extra_metric_value: "",
    start_date: "",
    end_date: "",
    notes: ""
  })

  const [channelForm, setChannelForm] = useState({
    period_type: "28d",
    amount: "",
    start_date: "",
    end_date: "",
    notes: ""
  })

  const [videoForm, setVideoForm] = useState({
    video_id: "",
    title: "",
    period_type: "lifetime",
    amount: "",
    views: "",
    rpm: "",
    start_date: "",
    end_date: "",
    notes: ""
  })





  const [playerSearch, setPlayerSearch] = useState("")
  const [playerFormat, setPlayerFormat] = useState("Top 10")
  const [playerResults, setPlayerResults] = useState([])
  const [prediction, setPrediction] = useState(null)

  const [thumbnailPreview, setThumbnailPreview] = useState(null)
  const [thumbnailAnalysis, setThumbnailAnalysis] = useState(null)

  const [loading, setLoading] = useState(false)
  const [initialBootLoading, setInitialBootLoading] = useState(true)
  const [initialBootStep, setInitialBootStep] = useState("Starting CourtVision AI...")
  const [initialBootError, setInitialBootError] = useState("")
  const [initialBootProgress, setInitialBootProgress] = useState(1)
  const [initialBootDisplayProgress, setInitialBootDisplayProgress] = useState(1)
  const [initialBootPhase, setInitialBootPhase] = useState("starting")
  const [initialBootCompletedUnits, setInitialBootCompletedUnits] = useState(0)
  const [initialBootTotalUnits, setInitialBootTotalUnits] = useState(1)
  const [initialBootRemainingSeconds, setInitialBootRemainingSeconds] = useState(null)
  const [initialBootSyncComplete, setInitialBootSyncComplete] = useState(false)
  const [initialBootRequiredItems, setInitialBootRequiredItems] = useState([])
  const [autoSyncingAll, setAutoSyncingAll] = useState(false)
  const [lastAutoSync, setLastAutoSync] = useState(null)
  const [showChannelRevenueEntries, setShowChannelRevenueEntries] = useState(false)
  const [showVideoRevenueEntries, setShowVideoRevenueEntries] = useState(false)
  const [openVideoRevenueRows, setOpenVideoRevenueRows] = useState({})
  const [revenueForecast, setRevenueForecast] = useState(null)
  const [strategyData, setStrategyData] = useState(null)
  const [deadRecoveryData, setDeadRecoveryData] = useState(null)
  const [deadRecoveryExpandedLists, setDeadRecoveryExpandedLists] = useState({})

  function isDeadRecoveryListExpanded(key) {
    return !!deadRecoveryExpandedLists[key]
  }

  function toggleDeadRecoveryList(key) {
    setDeadRecoveryExpandedLists(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  function deadRecoveryVisibleItems(items, key) {
    const safeItems = Array.isArray(items) ? items : []
    return isDeadRecoveryListExpanded(key) ? safeItems : safeItems.slice(0, 5)
  }

  const [aiStrategyExpandedLists, setAiStrategyExpandedLists] = useState({})

  function isAiStrategyListExpanded(key) {
    return !!aiStrategyExpandedLists[key]
  }

  function toggleAiStrategyList(key) {
    setAiStrategyExpandedLists(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  function aiStrategyVisibleItems(items, key) {
    const safeItems = Array.isArray(items) ? items : []
    const expanded = isAiStrategyListExpanded("strategyBoth")
    return expanded ? safeItems.slice(0, 15) : safeItems.slice(0, 5)
  }

  function aiStrategyAvoidVisibleItems(items) {
    const safeItems = Array.isArray(items) ? items : []
    const expanded = isAiStrategyListExpanded("strategyBoth")
    return expanded ? safeItems.slice(0, 15) : safeItems.slice(0, 5)
  }

  function aggregateAiStrategyFormats(items) {
    const totals = {}

    ;(Array.isArray(items) ? items : []).forEach(item => {
      const name = normalizeAiStrategyFormat(item?.type || item?.format)
      const value = Number(item?.average_revenue ?? item?.average_rpm ?? 0)
      const count = Number(item?.videos ?? item?.video_count ?? item?.count ?? 1) || 1

      if (!totals[name]) {
        totals[name] = {
          ...item,
          type: name,
          format: name,
          average_revenue: 0,
          average_rpm: 0,
          total_value: 0,
          count: 0
        }
      }

      totals[name].total_value += value * count
      totals[name].count += count
    })

    return Object.values(totals)
      .map(item => ({
        ...item,
        average_revenue: item.count ? item.total_value / item.count : 0,
        average_rpm: item.count ? item.total_value / item.count : 0
      }))
      .sort((a, b) => Number(b.average_revenue || b.average_rpm || 0) - Number(a.average_revenue || a.average_rpm || 0))
  }

  function normalizeAiStrategyFormat(value) {
    return normalizeContentFormat(value)
  }



  function getSmartVisibleFormatForStrategyIdea(item) {
    const directFormat = cleanStrategyFormat(item?.format || item?.content_type || item?.shuffle_format || "")

    if (directFormat && directFormat !== "Top 10 Plays") {
      return directFormat
    }

    const rawPlayerName = item?.player || item?.player_name || item?.topic || item?.name || ""
    const playerName = cleanStrategyName(rawPlayerName)
    const playerText = String(playerName || "").toLowerCase()

    if (!playerText) return "Top 10 Plays"

    const playerVideos = savedVideos.filter(video => {
      const title = String(video?.title || "").toLowerCase()
      const playerOnVideo = String(video?.player_name || "").toLowerCase()
      return playerOnVideo === playerText || title.includes(playerText)
    })

    const done = new Set()

    playerVideos.forEach(video => {
      const title = String(video?.title || "").toLowerCase()
      if (!title.includes("top 10") && !title.includes("top ten")) return

      if (title.includes("dunk")) done.add("Top 10 Dunks")
      else if (title.includes("assist") || title.includes("pass")) done.add("Top 10 Assists")
      else if (title.includes("block")) done.add("Top 10 Blocks")
      else if (title.includes("clutch") || title.includes("game winner") || title.includes("buzzer")) done.add("Top 10 Clutch Shots")
      else if (title.includes("cross") || title.includes("handle") || title.includes("dribble")) done.add("Top 10 Crossovers")
      else done.add("Top 10 Plays")
    })

    if (!done.has("Top 10 Plays")) return "Top 10 Plays"

    const isBig =
      playerText.includes("shaq") || playerText.includes("wilt") || playerText.includes("kareem") ||
      playerText.includes("hakeem") || playerText.includes("david robinson") || playerText.includes("bill russell") ||
      playerText.includes("mutombo") || playerText.includes("ewing") || playerText.includes("garnett") ||
      playerText.includes("dwight")

    const isPasser =
      playerText.includes("magic") || playerText.includes("john stockton") || playerText.includes("steve nash") ||
      playerText.includes("jason kidd") || playerText.includes("chris paul") || playerText.includes("jokic") ||
      playerText.includes("luka")

    const isDunker =
      playerText.includes("julius erving") || playerText.includes("vince carter") || playerText.includes("dominique") ||
      playerText.includes("jordan") || playerText.includes("lebron") || playerText.includes("kobe") ||
      playerText.includes("anthony edwards") || playerText.includes("ja morant") || playerText.includes("dwight")

    const isCrossover =
      playerText.includes("kyrie") || playerText.includes("iverson") || playerText.includes("curry") ||
      playerText.includes("durant") || playerText.includes("jason williams")

    const ordered = []

    if (isBig) ordered.push("Top 10 Blocks", "Top 10 Dunks")
    if (isPasser) ordered.push("Top 10 Assists")
    if (isDunker) ordered.push("Top 10 Dunks")
    ordered.push("Top 10 Clutch Shots")
    if (isCrossover) ordered.push("Top 10 Crossovers")
    ordered.push("Top 10 Plays")

    for (const option of ordered.map(cleanStrategyFormat)) {
      if (!done.has(option)) return option
    }

    return "Top 10 Plays"
  }

  function shuffleStrategyIdea() {
    const poolSize = strategyShufflePool.length

    if (poolSize <= 1) return

    setStrategyShuffleIndex(prev => {
      let next = Math.floor(Math.random() * poolSize)

      if (poolSize > 10) {
        let attempts = 0
        while (Math.abs(next - prev) <= 2 && attempts < 10) {
          next = Math.floor(Math.random() * poolSize)
          attempts += 1
        }
      }

      if (next === prev) {
        next = (next + 1) % poolSize
      }

      return next
    })
  }

  function normalizeAiStrategyEra(value) {
    const text = String(value || "").trim()

    const map = {
      "2020s / modern": "2020s",
      "2020s uploads": "2020s",
      "modern": "2020s",
      "unknown": "Uncategorized"
    }

    return map[text.toLowerCase()] || text
  }



  const [contentStudioProjects, setContentStudioProjects] = useState([])
  const [contentStudioStatus, setContentStudioStatus] = useState(null)
  const [videoEditorStatus, setVideoEditorStatus] = useState(null)
  const [contentStudioProjectType, setContentStudioProjectType] = useState("solo")
  const [contentStudioProjectName, setContentStudioProjectName] = useState("")
  const [contentStudioFiles, setContentStudioFiles] = useState([])
  const [contentStudioActiveProject, setContentStudioActiveProject] = useState(null)
  const [contentStudioUploading, setContentStudioUploading] = useState(false)
  const [contentStudioSelectedClipId, setContentStudioSelectedClipId] = useState(null)
  const [contentStudioDragClipId, setContentStudioDragClipId] = useState(null)
  const [contentStudioPlayheadSeconds, setContentStudioPlayheadSeconds] = useState(0)
  const contentStudioPreviewRef = useRef(null)
  const initialBootStartedRef = useRef(false)
  const initialBootSafeVisualStartedAtRef = useRef(null)
  const initialBootStartedAtRef = useRef(null)
  const initialBootVisualStartedAtRef = useRef(null)
  const initialBootEstimatedMsRef = useRef(180000)
  const initialBootLastRemainingRef = useRef(null)
  const initialBootRealSyncDoneRef = useRef(false)
  const initialBootVisualFinishStartedAtRef = useRef(null)
  const initialBootVisualFinishStartProgressRef = useRef(1)
  const initialBootTargetProgressRef = useRef(1)
  const initialBootTargetPercentRef = useRef(1)
  const initialBootDisplayPercentRef = useRef(1)
  const initialBootEtaStartedAtRef = useRef(null)

  function loadRevenueData() {
    fetch(`${API}/revenue/summary`)
      .then(r => r.json())
      .then(d => setRevenueSummary(d.summary || null))
      .catch(() => {})

    fetch(`${API}/revenue/checklist`)
      .then(r => r.json())
      .then(d => setRevenueChecklist(d.checklist || null))
      .catch(() => {})

    fetch(`${API}/revenue/channel`)
      .then(r => r.json())
      .then(d => setChannelRevenue(d.channel_revenue || []))
      .catch(() => {})

    fetch(`${API}/revenue/videos`)
      .then(r => r.json())
      .then(d => setVideoRevenue(d.video_revenue || []))
      .catch(() => {})

    fetch(`${API}/revenue/youtube/status`)
      .then(r => r.json())
      .then(d => setYoutubeRevenueStatus(d.status || null))
      .catch(() => {})
  }

  function loadRevenueForecastData() {
    fetch(`${API}/revenue-forecast`)
      .then(r => r.json())
      .then(d => setRevenueForecast(d || null))
      .catch(() => {})
  }

  function loadStrategyData() {
    fetch(`${API}/strategy-intelligence`)
      .then(r => r.json())
      .then(d => setStrategyData(d || null))
      .catch(() => {})
  }

  function loadDeadRecoveryData() {
    fetch(`${API}/dead-video-recovery`)
      .then(r => r.json())
      .then(d => setDeadRecoveryData(d || null))
      .catch(() => {})
  }

  function loadStudioData() {
    fetch(`${API}/studio-breakdowns/types`)
      .then(r => r.json())
      .then(d => setStudioTypes(d.types || []))
      .catch(() => {})

    fetch(`${API}/studio-breakdowns/summary`)
      .then(r => r.json())
      .then(d => setStudioSummary(d.summary || null))
      .catch(() => {})

    fetch(`${API}/studio-breakdowns`)
      .then(r => r.json())
      .then(d => setStudioBreakdowns(d.studio_breakdowns || []))
      .catch(() => {})

    fetch(`${API}/studio-intelligence`)
      .then(r => r.json())
      .then(d => setStudioIntelligence(d || null))
      .catch(() => {})
  }


  function loadContentStudioData() {
    fetch(`${API}/content-studio/status`)
      .then(r => r.json())
      .then(d => setContentStudioStatus(d || null))
      .catch(() => {})

    fetch(`${API}/video-editor/status`)
      .then(r => r.json())
      .then(d => setVideoEditorStatus(d || null))
      .catch(() => {})

    fetch(`${API}/content-studio/projects`)
      .then(r => r.json())
      .then(d => setContentStudioProjects(d.projects || []))
      .catch(() => {})
  }



  async function fetchJson(path, options = {}) {
    const response = await fetch(`${API}${path}`, options)

    if (!response.ok) {
      throw new Error(`${path} failed with status ${response.status}`)
    }

    return response.json()
  }

  function softTimeout(promise, milliseconds, fallback = null) {
    return Promise.race([
      promise,
      new Promise(resolve => {
        setTimeout(() => resolve(fallback), milliseconds)
      })
    ])
  }


  function isDashboardDataUsable(payload) {
    if (!payload) return false

    const statsPayload = payload.statsData || {}
    const savedVideoPayload = payload.savedVideosData || {}
    const rankingPayload = payload.rankingsData || {}
    const revenuePayload = payload.revenueSummaryData || {}

    const subscribers = Number(statsPayload.subscribers || 0)
    const totalViews = Number(statsPayload.total_views || 0)
    const savedVideoCount = Number((savedVideoPayload.saved_videos || []).length || 0)
    const rankingCount = Number((rankingPayload.player_rankings || []).length || 0)
    const revenueTotal = Number(
      revenuePayload?.summary?.channel_by_period?.lifetime ??
      revenuePayload?.summary?.total_channel_youtube_revenue ??
      0
    )

    return subscribers > 0 || totalViews > 0 || savedVideoCount > 0 || rankingCount > 0 || revenueTotal > 0
  }

  function formatBootRemainingTime(seconds) {
    if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
      return "Calculating..."
    }

    const safeSeconds = Math.max(0, Math.ceil(Number(seconds || 0)))
    const minutes = Math.floor(safeSeconds / 60)
    const remainingSeconds = safeSeconds % 60

    return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`
  }

  function getStoredBootEstimateMs() {
    try {
      const saved = Number(window.localStorage.getItem("courtvision_boot_estimate_ms") || 0)

      if (saved >= 8000 && saved <= 300000) {
        return saved
      }
    } catch {}

    // First-run estimate. This should feel quick, but still gives the
    // percentage enough time to move through the numbers instead of jumping.
    return 45000
  }

  function saveBootEstimateMs(actualMs) {
    try {
      const safeActual = Math.min(300000, Math.max(8000, Number(actualMs || 45000)))
      const previous = getStoredBootEstimateMs()

      // Weighted toward the newest successful startup so it learns quickly.
      const nextEstimate = Math.round((previous * 0.35) + (safeActual * 0.65))

      window.localStorage.setItem("courtvision_boot_estimate_ms", String(nextEstimate))
    } catch {}
  }

  function makeInitialBootItems() {
    return [
      { key: "dashboardSync", label: "Videos, views, subscribers, thumbnails, likes, and comments", status: "waiting", weight: 28 },
      { key: "revenueSync", label: "YouTube Analytics revenue, views, and RPM", status: "waiting", weight: 28 },
      { key: "statsData", label: "Dashboard stats", status: "waiting", weight: 7 },
      { key: "savedVideosData", label: "Saved videos", status: "waiting", weight: 8 },
      { key: "rankingsData", label: "Player rankings", status: "waiting", weight: 7 },
      { key: "revenueSummaryData", label: "Revenue summary", status: "waiting", weight: 7 },
      { key: "youtubeRevenueStatusData", label: "Revenue sync status", status: "waiting", weight: 5 },
      { key: "channelRevenueData", label: "Channel revenue rows", status: "waiting", weight: 4 },
      { key: "videoRevenueData", label: "Video revenue rows", status: "waiting", weight: 4 },
      { key: "playersData", label: "Idea Lab players", status: "waiting", weight: 2 }
    ]
  }

  function getBootItemWeight(items, key) {
    const item = (items || []).find(row => row.key === key)
    return Number(item?.weight || 0)
  }

  function updateBootItem(key, status) {
    setInitialBootRequiredItems(prev => {
      const next = (prev || []).map(item =>
        item.key === key ? { ...item, status } : item
      )

      const totalWeight = next.reduce((sum, item) => sum + Number(item.weight || 0), 0) || 100
      const doneWeight = next
        .filter(item => item.status === "done")
        .reduce((sum, item) => sum + Number(item.weight || 0), 0)

      const targetPercent = Math.min(99, Math.max(1, (doneWeight / totalWeight) * 100))
      initialBootTargetPercentRef.current = targetPercent

      setInitialBootCompletedUnits(Math.round(targetPercent))
      setInitialBootTotalUnits(100)

      return next
    })
  }

  function getBootItemsDonePercent(items) {
    const totalWeight = (items || []).reduce((sum, item) => sum + Number(item.weight || 0), 0) || 100
    const doneWeight = (items || [])
      .filter(item => item.status === "done")
      .reduce((sum, item) => sum + Number(item.weight || 0), 0)

    return Math.min(99, Math.max(1, (doneWeight / totalWeight) * 100))
  }

  function markBootUnitComplete(amount = 1) {
    setInitialBootCompletedUnits(prev => {
      const total = 100
      const next = Math.min(total, Math.max(Number(prev || 0), Number(prev || 0) + Number(amount || 1)))
      initialBootTargetProgressRef.current = Math.max(Number(initialBootTargetProgressRef.current || 1), next)
      return next
    })
  }

  async function loadDataPayloadWithBootTracking() {
    const requiredFetches = [
      { key: "statsData", path: "/dashboard/stats", fallback: {} },
      { key: "savedVideosData", path: "/dashboard/saved-videos", fallback: { saved_videos: [] } },
      { key: "rankingsData", path: "/dashboard/player-rankings", fallback: { player_rankings: [] } },
      { key: "revenueSummaryData", path: "/revenue/summary", fallback: { summary: null } },
      { key: "youtubeRevenueStatusData", path: "/revenue/youtube/status", fallback: { status: null } },
      { key: "channelRevenueData", path: "/revenue/channel", fallback: { channel_revenue: [] } },
      { key: "videoRevenueData", path: "/revenue/videos", fallback: { video_revenue: [] } },
      { key: "playersData", path: "/idea-lab/top-50", fallback: { top_50: [] } }
    ]

    const entries = await Promise.all(
      requiredFetches.map(async item => {
        updateBootItem(item.key, "running")

        try {
          const data = await fetchJson(item.path)
          updateBootItem(item.key, "done")
          return [item.key, data]
        } catch {
          updateBootItem(item.key, "done")
          return [item.key, item.fallback]
        }
      })
    )

    const payload = {
      ...Object.fromEntries(entries),
      channelBrainData: { channel_brain: null },
      revenueChecklistData: { checklist: null },
      revenueForecastData: null,
      strategyResponseData: null,
      deadRecoveryResponseData: null,
      studioTypesData: { types: [] },
      studioSummaryData: { summary: null },
      studioBreakdownsData: { studio_breakdowns: [] },
      studioIntelligenceData: null,
      contentStudioStatusData: null,
      videoEditorStatusData: null,
      contentStudioProjectsData: { projects: [] }
    }

    return payload
  }

  async function loadDataPayload() {
    try {
      return await fetchJson("/dashboard/startup-data")
    } catch {
      return await loadDataPayloadMultiFetch()
    }
  }

  async function loadDataPayloadMultiFetch() {
    const trackedFetch = async (path, fallback) => {
      try {
        return await fetchJson(path)
      } catch {
        return fallback
      }
    }

    const [
      statsData,
      savedVideosData,
      rankingsData,
      playersData,
      channelBrainData,
      revenueSummaryData,
      revenueChecklistData,
      channelRevenueData,
      videoRevenueData,
      youtubeRevenueStatusData,
      revenueForecastData,
      strategyResponseData,
      deadRecoveryResponseData,
      studioTypesData,
      studioSummaryData,
      studioBreakdownsData,
      studioIntelligenceData,
      contentStudioStatusData,
      videoEditorStatusData,
      contentStudioProjectsData
    ] = await Promise.all([
      trackedFetch("/dashboard/stats", {}),
      trackedFetch("/dashboard/saved-videos", { saved_videos: [] }),
      trackedFetch("/dashboard/player-rankings", { player_rankings: [] }),
      trackedFetch("/idea-lab/top-50", { top_50: [] }),
      trackedFetch("/dashboard/channel-brain", { channel_brain: null }),

      trackedFetch("/revenue/summary", { summary: null }),
      trackedFetch("/revenue/checklist", { checklist: null }),
      trackedFetch("/revenue/channel", { channel_revenue: [] }),
      trackedFetch("/revenue/videos", { video_revenue: [] }),
      trackedFetch("/revenue/youtube/status", { status: null }),

      trackedFetch("/revenue-forecast", null),
      trackedFetch("/strategy-intelligence", null),
      trackedFetch("/dead-video-recovery", null),

      trackedFetch("/studio-breakdowns/types", { types: [] }),
      trackedFetch("/studio-breakdowns/summary", { summary: null }),
      trackedFetch("/studio-breakdowns", { studio_breakdowns: [] }),
      trackedFetch("/studio-intelligence", null),

      trackedFetch("/content-studio/status", null),
      trackedFetch("/video-editor/status", null),
      trackedFetch("/content-studio/projects", { projects: [] })
    ])

    return {
      statsData,
      savedVideosData,
      rankingsData,
      playersData,
      channelBrainData,
      revenueSummaryData,
      revenueChecklistData,
      channelRevenueData,
      videoRevenueData,
      youtubeRevenueStatusData,
      revenueForecastData,
      strategyResponseData,
      deadRecoveryResponseData,
      studioTypesData,
      studioSummaryData,
      studioBreakdownsData,
      studioIntelligenceData,
      contentStudioStatusData,
      videoEditorStatusData,
      contentStudioProjectsData
    }
  }

  function applyLoadedData(payload) {
    setStats(payload.statsData || {})
    setSavedVideos(payload.savedVideosData?.saved_videos || [])
    setRankings(payload.rankingsData?.player_rankings || [])
    setPlayers(payload.playersData?.top_50 || [])

    setChannelBrain(payload.channelBrainData?.channel_brain || null)

    setRevenueSummary(payload.revenueSummaryData?.summary || null)
    setRevenueChecklist(payload.revenueChecklistData?.checklist || null)
    setChannelRevenue(payload.channelRevenueData?.channel_revenue || [])
    setVideoRevenue(payload.videoRevenueData?.video_revenue || [])
    setYoutubeRevenueStatus(payload.youtubeRevenueStatusData?.status || null)

    setRevenueForecast(payload.revenueForecastData || null)
    setStrategyData(payload.strategyResponseData || null)
    setDeadRecoveryData(payload.deadRecoveryResponseData || null)

    setStudioTypes(payload.studioTypesData?.types || [])
    setStudioSummary(payload.studioSummaryData?.summary || null)
    setStudioBreakdowns(payload.studioBreakdownsData?.studio_breakdowns || [])
    setStudioIntelligence(payload.studioIntelligenceData || null)

    setContentStudioStatus(payload.contentStudioStatusData || null)
    setVideoEditorStatus(payload.videoEditorStatusData || null)
    setContentStudioProjects(payload.contentStudioProjectsData?.projects || [])
  }

  async function waitForLoadedDashboardData() {
    let latestPayload = null

    for (let attempt = 0; attempt < 8; attempt += 1) {
      latestPayload = await loadDataPayload()

      if (isDashboardDataUsable(latestPayload)) {
        return latestPayload
      }

      await new Promise(resolve => setTimeout(resolve, 1000))
    }

    return latestPayload
  }

  async function loadData() {
    const payload = await loadDataPayload()
    applyLoadedData(payload)
    return payload
  }

  async function runFullAutoSync({ boot = false } = {}) {
    if (autoSyncingAll && !boot) return

    const bootTotalUnits = 100

    setAutoSyncingAll(true)

    try {
      if (boot) {
        const bootNow = Date.now()
        const bootItems = makeInitialBootItems()

        initialBootStartedAtRef.current = bootNow
        initialBootVisualStartedAtRef.current = bootNow
        initialBootEtaStartedAtRef.current = bootNow
        initialBootEstimatedMsRef.current = getStoredBootEstimateMs()
        initialBootLastRemainingRef.current = null
        initialBootRealSyncDoneRef.current = false
        initialBootVisualFinishStartedAtRef.current = null
        initialBootVisualFinishStartProgressRef.current = 1
        initialBootTargetProgressRef.current = 1
        initialBootTargetPercentRef.current = 1
        initialBootDisplayPercentRef.current = 1
        initialBootSafeVisualStartedAtRef.current = bootNow

        setInitialBootRequiredItems(bootItems)
        setInitialBootProgress(1)
        setInitialBootDisplayProgress(1)
        setInitialBootPhase("video")
        setInitialBootCompletedUnits(1)
        setInitialBootTotalUnits(bootTotalUnits)
        setInitialBootRemainingSeconds(null)
        setInitialBootSyncComplete(false)
        setInitialBootError("")
        setInitialBootStep("Syncing videos, views, subscribers, thumbnails, likes, and comments...")
      }

      if (boot) updateBootItem("dashboardSync", "running")

      const dashboardSyncResult = await fetchJson("/dashboard/auto-sync", { method: "POST" }).catch(error => ({
        ok: false,
        message: error?.message || "Dashboard/video sync failed."
      }))

      if (dashboardSyncResult?.ok === false) {
        throw new Error(dashboardSyncResult?.message || dashboardSyncResult?.error || "Dashboard/video sync failed.")
      }

      if (boot) {
        updateBootItem("dashboardSync", "done")
        setInitialBootPhase("revenue")
        setInitialBootStep("Syncing YouTube Analytics revenue, views, and RPM...")
        updateBootItem("revenueSync", "running")
      }

      const revenueSyncResult = await fetchJson("/revenue/youtube/auto-sync", { method: "POST" }).catch(error => ({
        ok: false,
        message: error?.message || "Revenue sync failed."
      }))

      if (revenueSyncResult?.ok === false || revenueSyncResult?.revenue_sync?.ok === false) {
        throw new Error(
          revenueSyncResult?.message ||
          revenueSyncResult?.revenue_sync?.message ||
          revenueSyncResult?.error ||
          "Revenue sync failed."
        )
      }

      if (boot) {
        updateBootItem("revenueSync", "done")
        setInitialBootPhase("data")
        setInitialBootStep("Loading fully synced dashboard and revenue data...")
      }

      const loadedPayload = boot ? await loadDataPayloadWithBootTracking() : await loadDataPayload()
      applyLoadedData(loadedPayload)

      if (boot && !isDashboardDataUsable(loadedPayload)) {
        throw new Error("CourtVision synced, but required dashboard data came back empty.")
      }

      setLastAutoSync(new Date())

      if (boot) {
        const actualBootMs = Date.now() - (initialBootStartedAtRef.current || Date.now())
        saveBootEstimateMs(actualBootMs)

        initialBootRealSyncDoneRef.current = true
        initialBootTargetProgressRef.current = 100
        initialBootTargetPercentRef.current = 100

        setInitialBootError("")
        setInitialBootCompletedUnits(100)
        setInitialBootTotalUnits(100)
        setInitialBootProgress(100)
        setInitialBootPhase("finishing")
        setInitialBootStep("Finalizing loaded CourtVision dashboard...")
        setInitialBootSyncComplete(true)
      }

      // Load heavier non-dashboard tabs after the required dashboard data is ready.
      setTimeout(() => {
        loadRevenueForecastData()
        loadStrategyData()
        loadDeadRecoveryData()
        loadStudioData()
        loadContentStudioData()
      }, 500)
    } catch (error) {
      console.error("CourtVision auto-sync failed:", error)

      if (boot) {
        setInitialBootError(error?.message || "Auto-sync failed. Restart the backend and try again.")
        setInitialBootPhase("error")
        setInitialBootStep("CourtVision Sync Needs Attention")
        setInitialBootRemainingSeconds(0)
        setInitialBootSyncComplete(false)

        // Do not show 100 unless the dashboard can open.
        const safePercent = Math.min(97, Number(initialBootDisplayPercentRef.current || initialBootDisplayProgress || 1))
        setInitialBootProgress(safePercent)
        setInitialBootDisplayProgress(safePercent)
        setInitialBootCompletedUnits(Math.round(safePercent))
        setInitialBootTotalUnits(100)
      }
    } finally {
      setAutoSyncingAll(false)
    }
  }

  useEffect(() => {
    if (!initialBootLoading) return

    const progressTimer = setInterval(() => {
      const now = Date.now()
      const startedAt = initialBootEtaStartedAtRef.current || initialBootStartedAtRef.current || now
      const elapsedSeconds = Math.max(1, (now - startedAt) / 1000)

      const target = Math.max(
        Number(initialBootTargetPercentRef.current || 1),
        initialBootSyncComplete || initialBootPhase === "finishing" || initialBootPhase === "complete" ? 100 : 1
      )

      setInitialBootDisplayProgress(prev => {
        const current = Number(prev || 1)

        if (initialBootError) {
          const next = Math.min(97, Math.max(current, Number(initialBootTargetPercentRef.current || current)))
          initialBootDisplayPercentRef.current = next
          return next
        }

        if (target <= current) {
          initialBootDisplayPercentRef.current = current
          return current
        }

        const gap = target - current
        const step = Math.max(0.05, Math.min(0.85, gap / 14))
        const next = Math.min(target, current + step)

        initialBootDisplayPercentRef.current = next
        return next
      })

      setInitialBootProgress(prev => {
        const current = Number(prev || 1)
        return Math.max(current, Math.min(100, target))
      })

      const displayPercent = Math.max(1, Number(initialBootDisplayPercentRef.current || initialBootDisplayProgress || 1))
      const rawCompleted = Math.min(100, Math.max(1, Math.round(displayPercent)))

      setInitialBootCompletedUnits(prev => Math.max(Number(prev || 1), rawCompleted))
      setInitialBootTotalUnits(100)

      if (initialBootError) {
        setInitialBootRemainingSeconds(0)
        return
      }

      if (displayPercent >= 99.9 && initialBootSyncComplete) {
        setInitialBootRemainingSeconds(0)
        return
      }

      const estimatedTotalSeconds = elapsedSeconds / Math.max(0.01, displayPercent / 100)
      const rawRemaining = Math.max(1, Math.ceil(estimatedTotalSeconds - elapsedSeconds))

      setInitialBootRemainingSeconds(prev => {
        if (prev === null || prev === undefined) return rawRemaining
        return Math.min(Number(prev), rawRemaining)
      })
    }, 90)

    return () => clearInterval(progressTimer)
  }, [
    initialBootLoading,
    initialBootError,
    initialBootSyncComplete,
    initialBootPhase,
    initialBootDisplayProgress
  ])


  useEffect(() => {
    if (
      !initialBootLoading ||
      initialBootError ||
      !initialBootSyncComplete ||
      initialBootDisplayProgress < 100
    ) return

    setInitialBootRemainingSeconds(0)
    setInitialBootPhase("complete")
    setInitialBootStep("CourtVision AI Ready.")

    const dashboardTimer = setTimeout(() => {
      setInitialBootLoading(false)
    }, 200)

    return () => clearTimeout(dashboardTimer)
  }, [
    initialBootLoading,
    initialBootError,
    initialBootSyncComplete,
    initialBootDisplayProgress
  ])


  useEffect(() => {
    if (!initialBootStartedRef.current) {
      initialBootStartedRef.current = true
      runFullAutoSync({ boot: true })
    }

    const liveDataTimer = setInterval(() => {
      loadData().catch(() => {})
    }, 60000)

    const fullSyncTimer = setInterval(() => {
      runFullAutoSync().catch(() => {})
    }, 900000)

    return () => {
      clearInterval(liveDataTimer)
      clearInterval(fullSyncTimer)
    }
  }, [])

  function autoSyncChannel() {
    runFullAutoSync().catch(() => {})
  }

  function syncChannel() {
    setLoading(true)

    runFullAutoSync()
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  function addChannelRevenue() {
    fetch(`${API}/revenue/channel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...channelForm,
        amount: parseNumberInput(channelForm.amount)
      })
    })
      .then(() => {
        setChannelForm({
          period_type: "28d",
          amount: "",
          start_date: "",
          end_date: "",
          notes: ""
        })
        loadRevenueData()
      })
      .catch(() => {})
  }

  function addVideoRevenue() {
    fetch(`${API}/revenue/videos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...videoForm,
        amount: parseNumberInput(videoForm.amount),
        views: parseNumberInput(videoForm.views),
        rpm: parseNumberInput(videoForm.rpm)
      })
    })
      .then(async (r) => {
        const data = await r.json()

        if (!r.ok) {
          alert("Video revenue save failed: " + JSON.stringify(data))
          return
        }

        setVideoForm({
          video_id: "",
          title: "",
          period_type: "lifetime",
          amount: "",
          views: "",
          rpm: "",
          start_date: "",
          end_date: "",
          notes: ""
        })
        loadRevenueData()
      })
      .catch((err) => {
        alert("Video revenue save failed: " + err.message)
      })
  }

  function addStudioBreakdown() {
    fetch(`${API}/studio-breakdowns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...studioForm,
        views: parseNumberInput(studioForm.views),
        watch_time_hours: parseNumberInput(studioForm.watch_time_hours),
        impressions: parseNumberInput(studioForm.impressions),
        ctr: parseNumberInput(studioForm.ctr),
        estimated_revenue: parseNumberInput(studioForm.estimated_revenue),
        rpm: parseNumberInput(studioForm.rpm),
        cpm: parseNumberInput(studioForm.cpm),
        subscribers: parseNumberInput(studioForm.subscribers),
        percentage: parseNumberInput(studioForm.percentage),
        extra_metric_value: parseNumberInput(studioForm.extra_metric_value)
      })
    })
      .then(() => {
        setStudioForm({
          breakdown_type: "country",
          scope: "channel",
          video_id: "",
          title: "",
          period_type: "28d",
          item_name: "",
          views: "",
          watch_time_hours: "",
          average_view_duration: "",
          impressions: "",
          ctr: "",
          estimated_revenue: "",
          rpm: "",
          cpm: "",
          subscribers: "",
          percentage: "",
          extra_metric_name: "",
          extra_metric_value: "",
          start_date: "",
          end_date: "",
          notes: ""
        })
        loadStudioData()
      })
      .catch(() => {})
  }

  function deleteStudioBreakdown(id) {
    fetch(`${API}/studio-breakdowns/${id}`, { method: "DELETE" })
      .then(() => loadStudioData())
      .catch(() => {})
  }

  function deleteChannelRevenue(id) {
    fetch(`${API}/revenue/channel/${id}`, { method: "DELETE" })
      .then(() => loadRevenueData())
      .catch(() => {})
  }

  function deleteVideoRevenue(id) {
    fetch(`${API}/revenue/videos/${id}`, { method: "DELETE" })
      .then(() => loadRevenueData())
      .catch(() => {})
  }





  function updatePlayerSearch(value) {
    setPlayerSearch(value)
    setPrediction(null)

    const query = value.trim()

    if (!query) {
      setPlayerResults([])
      return
    }

    fetch(`${API}/player-predictor/search?q=${encodeURIComponent(query)}`)
      .then(r => r.json())
      .then(d => {
        const sortedResults = (d.results || [])
          .map(player => typeof player === "string" ? { name: player } : player)
          .filter(player => player?.name)
          .sort((a, b) => String(a.name).localeCompare(String(b.name)))

        setPlayerResults(sortedResults)
      })
      .catch(() => setPlayerResults([]))
  }

  function selectPlayerResult(name) {
    setPlayerSearch(name)
    setPlayerResults([])
    setPrediction(null)
  }

  function runPlayerPrediction() {
    const name = playerSearch.trim()

    if (!name) return

    setPlayerResults([])

    fetch(
      `${API}/revenue-simulator?name=${encodeURIComponent(name)}&video_length=3&title_type=${encodeURIComponent(playerFormat)}`
    )
      .then(r => r.json())
      .then(d => {
        if (d.found && d.simulation) {
          setPrediction({
            ...d.simulation,
            name: d.simulation.name || name,
            selected_format: playerFormat
          })
          return
        }

        return fetch(`${API}/player-predictor/predict?name=${encodeURIComponent(name)}`)
          .then(r => r.json())
          .then(fallback => {
            if (fallback.found && fallback.prediction) {
              setPrediction({
                ...fallback.prediction,
                name: fallback.prediction.name || name,
                selected_format: playerFormat
              })
            }
          })
      })
      .catch(() => {})
  }


  function uploadContentStudioProject() {
    if (!contentStudioFiles.length) {
      alert("Choose at least one MP4 file first.")
      return
    }

    if (contentStudioProjectType === "solo" && contentStudioFiles.length !== 1) {
      alert("Solo Highlight projects need exactly 1 MP4 file.")
      return
    }

    if (contentStudioProjectType === "top10" && contentStudioFiles.length < 10) {
      alert("Top 10 projects need at least 10 MP4 files.")
      return
    }

    const formData = new FormData()
    formData.append("project_type", contentStudioProjectType)
    formData.append(
      "project_name",
      contentStudioProjectName.trim() ||
        (contentStudioProjectType === "top10" ? "Untitled Top 10 Project" : "Untitled Solo Highlight")
    )

    Array.from(contentStudioFiles).forEach(file => {
      formData.append("files", file)
    })

    setContentStudioUploading(true)

    fetch(`${API}/content-studio/upload`, {
      method: "POST",
      body: formData
    })
      .then(async r => {
        const data = await r.json()

        if (!r.ok) {
          alert("Content Studio upload failed: " + JSON.stringify(data))
          return
        }

        setContentStudioActiveProject(data.project || null)
        setContentStudioProjectName("")
        setContentStudioFiles([])
        loadContentStudioData()
        alert("Content Studio project created.")
      })
      .catch(err => {
        alert("Content Studio upload failed: " + err.message)
      })
      .finally(() => setContentStudioUploading(false))
  }

  function openContentStudioProject(projectId) {
    fetch(`${API}/content-studio/project/${projectId}`)
      .then(r => r.json())
      .then(d => {
        if (d.found) {
          const openedProject = d.project
          setContentStudioActiveProject(openedProject)
          setContentStudioSelectedClipId(openedProject.clips?.[0]?.clip_id || null)
          setContentStudioPlayheadSeconds(0)
        }
      })
      .catch(() => {})
  }

  function deleteContentStudioProject(projectId) {
    if (!confirm("Delete this Content Studio project from the app? This removes the imported project copy.")) {
      return
    }

    fetch(`${API}/content-studio/project/${projectId}`, {
      method: "DELETE"
    })
      .then(() => {
        if (contentStudioActiveProject?.project_id === projectId) {
          setContentStudioActiveProject(null)
        }

        loadContentStudioData()
      })
      .catch(() => {})
  }


  function getContentStudioDraft(project = contentStudioActiveProject) {
    if (!project) return null

    return project.project_type === "top10" ? project.top10_draft : project.solo_draft
  }

  function updateContentStudioProjectField(field, value) {
    if (!contentStudioActiveProject) return

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      [field]: value
    })
  }

  function updateContentStudioDraftField(field, value) {
    if (!contentStudioActiveProject) return

    const draftKey = contentStudioActiveProject.project_type === "top10" ? "top10_draft" : "solo_draft"

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      [draftKey]: {
        ...(contentStudioActiveProject[draftKey] || {}),
        [field]: value
      }
    })
  }

  function updateContentStudioClip(clipId, updates) {
    if (!contentStudioActiveProject) return

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      clips: (contentStudioActiveProject.clips || []).map(clip =>
        clip.clip_id === clipId ? { ...clip, ...updates } : clip
      )
    })
  }

  function reorderContentStudioClips(fromClipId, toClipId) {
    if (!contentStudioActiveProject || fromClipId === toClipId) return

    const clips = [...(contentStudioActiveProject.clips || [])]
    const fromIndex = clips.findIndex(clip => clip.clip_id === fromClipId)
    const toIndex = clips.findIndex(clip => clip.clip_id === toClipId)

    if (fromIndex < 0 || toIndex < 0) return

    const [movedClip] = clips.splice(fromIndex, 1)
    clips.splice(toIndex, 0, movedClip)

    const reordered = clips.map((clip, index) => ({
      ...clip,
      order: index + 1,
      selected_for_top10: contentStudioActiveProject.project_type === "top10" ? index < 10 : true
    }))

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      clips: reordered
    })
  }

  function moveContentStudioClip(clipId, direction) {
    if (!contentStudioActiveProject) return

    const clips = [...(contentStudioActiveProject.clips || [])]
    const index = clips.findIndex(clip => clip.clip_id === clipId)
    const targetIndex = index + direction

    if (index < 0 || targetIndex < 0 || targetIndex >= clips.length) return

    const [clip] = clips.splice(index, 1)
    clips.splice(targetIndex, 0, clip)

    const reordered = clips.map((item, i) => ({
      ...item,
      order: i + 1,
      selected_for_top10: contentStudioActiveProject.project_type === "top10" ? i < 10 : true
    }))

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      clips: reordered
    })
  }

  function splitContentStudioClip(clipId) {
    if (!contentStudioActiveProject) return

    const clips = [...(contentStudioActiveProject.clips || [])]
    const index = clips.findIndex(clip => clip.clip_id === clipId)

    if (index < 0) return

    const clip = clips[index]
    const trimStart = Number(clip.trim_start || 0)
    const trimEnd = Number(clip.trim_end || 0)
    const splitPoint = trimEnd > trimStart ? trimStart + ((trimEnd - trimStart) / 2) : trimStart + 3

    const firstHalf = {
      ...clip,
      title: `${clip.title} Part 1`,
      trim_start: trimStart,
      trim_end: Number(splitPoint.toFixed(2))
    }

    const secondHalf = {
      ...clip,
      clip_id: `${clip.clip_id}_split_${Date.now()}`,
      title: `${clip.title} Part 2`,
      trim_start: Number(splitPoint.toFixed(2)),
      trim_end: trimEnd,
      split_from_clip_id: clip.clip_id
    }

    clips.splice(index, 1, firstHalf, secondHalf)

    const reordered = clips.map((item, i) => ({
      ...item,
      order: i + 1,
      selected_for_top10: contentStudioActiveProject.project_type === "top10" ? i < 10 : true
    }))

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      clips: reordered,
      clip_count: reordered.length
    })

    setContentStudioSelectedClipId(secondHalf.clip_id)
  }

  function removeContentStudioClipFromTimeline(clipId) {
    if (!contentStudioActiveProject) return

    const clips = (contentStudioActiveProject.clips || [])
      .filter(clip => clip.clip_id !== clipId)
      .map((clip, index) => ({
        ...clip,
        order: index + 1,
        selected_for_top10: contentStudioActiveProject.project_type === "top10" ? index < 10 : true
      }))

    setContentStudioActiveProject({
      ...contentStudioActiveProject,
      clips,
      clip_count: clips.length
    })

    if (contentStudioSelectedClipId === clipId) {
      setContentStudioSelectedClipId(clips[0]?.clip_id || null)
    }
  }

  function saveContentStudioProjectEdits() {
    if (!contentStudioActiveProject) return

    const draft = getContentStudioDraft()

    fetch(`${API}/content-studio/project/${contentStudioActiveProject.project_id}/edit`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_name: contentStudioActiveProject.project_name,
        clips: (contentStudioActiveProject.clips || []).map((clip, index) => ({
          clip_id: clip.clip_id,
          order: index + 1,
          title: clip.title,
          trim_start: Number(clip.trim_start || 0),
          trim_end: Number(clip.trim_end || 0),
          duration_seconds: Number(clip.duration_seconds || 0),
          selected_for_top10: !!clip.selected_for_top10
        })),
        top10_draft: contentStudioActiveProject.project_type === "top10" ? draft : null,
        solo_draft: contentStudioActiveProject.project_type === "solo" ? draft : null
      })
    })
      .then(async r => {
        const data = await r.json()

        if (!r.ok || data.found === false) {
          alert("Project save failed: " + JSON.stringify(data))
          return
        }

        setContentStudioActiveProject(data.project)
        setContentStudioSelectedClipId(data.project?.clips?.[0]?.clip_id || contentStudioSelectedClipId)
        loadContentStudioData()
        alert("Project edits saved.")
      })
      .catch(err => alert("Project save failed: " + err.message))
  }

  function approveContentStudioProject() {
    if (!contentStudioActiveProject) return

    fetch(`${API}/content-studio/project/${contentStudioActiveProject.project_id}/approve`, {
      method: "PUT"
    })
      .then(async r => {
        const data = await r.json()

        if (!r.ok || data.found === false) {
          alert("Project approval failed: " + JSON.stringify(data))
          return
        }

        setContentStudioActiveProject(data.project)
        loadContentStudioData()
        alert("Project approved. Upload will still require your separate permission click.")
      })
      .catch(err => alert("Project approval failed: " + err.message))
  }


  function clampContentStudioNumber(value, min, max) {
    const number = Number(value || 0)

    if (Number.isNaN(number)) return min
    if (number < min) return min
    if (number > max) return max

    return Number(number.toFixed(2))
  }

  function getContentStudioClipDuration(clip) {
    const explicitDuration = Number(clip?.duration_seconds || clip?.duration || 0)

    if (explicitDuration > 0) return explicitDuration

    const trimEnd = Number(clip?.trim_end || 0)

    if (trimEnd > 0) return trimEnd

    return 120
  }

  function getContentStudioSortedClips(project = contentStudioActiveProject) {
    return [...(project?.clips || [])].sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
  }

  function getContentStudioEffectiveClipDuration(clip) {
    const fullDuration = getContentStudioClipDuration(clip)
    const start = Number(clip?.trim_start || 0)
    const rawEnd = Number(clip?.trim_end || 0)
    const end = rawEnd > start ? rawEnd : fullDuration

    return Math.max(0.25, end - start)
  }

  function getContentStudioTimelineTotalSeconds(project = contentStudioActiveProject) {
    const clips = getContentStudioSortedClips(project)
    const clipSeconds = clips.reduce((total, clip) => total + getContentStudioEffectiveClipDuration(clip), 0)

    return Number(Math.max(0.25, clipSeconds).toFixed(2))
  }

  function getContentStudioClipTimelineStart(clipId, project = contentStudioActiveProject) {
    const clips = getContentStudioSortedClips(project)
    let cursor = 0

    for (const clip of clips) {
      if (clip.clip_id === clipId) return cursor
      cursor += getContentStudioEffectiveClipDuration(clip)
    }

    return 0
  }

  function seekContentStudioTimeline(seconds) {
    if (!contentStudioActiveProject) return

    const clips = getContentStudioSortedClips()
    const totalSeconds = getContentStudioTimelineTotalSeconds()
    const nextTime = clampContentStudioNumber(seconds, 0, totalSeconds)
    let cursor = 0

    setContentStudioPlayheadSeconds(nextTime)

    if (contentStudioActiveProject.rendered_video?.preview_url) {
      window.setTimeout(() => {
        if (contentStudioPreviewRef.current) {
          contentStudioPreviewRef.current.currentTime = nextTime
        }
      }, 0)
      return
    }

    for (const clip of clips) {
      const clipLength = getContentStudioEffectiveClipDuration(clip)
      const clipStart = Number(clip.trim_start || 0)

      if (nextTime >= cursor && nextTime <= cursor + clipLength) {
        setContentStudioSelectedClipId(clip.clip_id)

        window.setTimeout(() => {
          if (contentStudioPreviewRef.current) {
            contentStudioPreviewRef.current.currentTime = clipStart + (nextTime - cursor)
          }
        }, 0)

        return
      }

      cursor += clipLength
    }
  }

  function handleContentStudioTimelineClick(event) {
    const lane = event.currentTarget
    const rect = lane.getBoundingClientRect()
    const x = event.clientX - rect.left
    const percent = x / Math.max(1, rect.width)
    const totalSeconds = getContentStudioTimelineTotalSeconds()

    seekContentStudioTimeline(percent * totalSeconds)
  }

  function handleContentStudioPreviewTimeUpdate(event, clip) {
    if (!clip) return

    const video = event.currentTarget
    const clipTimelineStart = getContentStudioClipTimelineStart(clip.clip_id)
    const clipTrimStart = Number(clip.trim_start || 0)
    const clipDuration = getContentStudioClipDuration(clip)
    const rawTrimEnd = Number(clip.trim_end || 0)
    const clipTrimEnd = rawTrimEnd > clipTrimStart ? rawTrimEnd : clipDuration
    const currentTime = Number(video.currentTime || 0)

    if (clipTrimEnd > clipTrimStart && currentTime >= clipTrimEnd) {
      video.pause()
      video.currentTime = clipTrimEnd
      setContentStudioPlayheadSeconds(Number((clipTimelineStart + (clipTrimEnd - clipTrimStart)).toFixed(2)))
      return
    }

    const relativeTime = clampContentStudioNumber(currentTime - clipTrimStart, 0, clipTrimEnd - clipTrimStart)

    setContentStudioPlayheadSeconds(Number((clipTimelineStart + relativeTime).toFixed(2)))
  }

  function startContentStudioTrimDrag(event, clip, side) {
    if (!clip || !contentStudioActiveProject) return

    event.preventDefault()
    event.stopPropagation()

    const startX = event.clientX
    const clipElement = event.currentTarget.closest(".timeline-clip")
    const clipWidth = Math.max(160, clipElement?.getBoundingClientRect()?.width || 240)
    const duration = getContentStudioClipDuration(clip)

    const originalStart = Number(clip.trim_start || 0)
    const originalEnd = Number(clip.trim_end || duration || 0) || duration

    function onMouseMove(moveEvent) {
      const deltaX = moveEvent.clientX - startX
      const deltaSeconds = (deltaX / clipWidth) * duration

      if (side === "left") {
        const maxStart = Math.max(0, originalEnd - 0.25)
        const nextStart = clampContentStudioNumber(originalStart + deltaSeconds, 0, maxStart)

        updateContentStudioClip(clip.clip_id, {
          trim_start: nextStart
        })
      }

      if (side === "right") {
        const minEnd = Math.max(0.25, originalStart + 0.25)
        const nextEnd = clampContentStudioNumber(originalEnd + deltaSeconds, minEnd, duration)

        updateContentStudioClip(clip.clip_id, {
          trim_end: nextEnd
        })
      }
    }

    function onMouseUp() {
      window.removeEventListener("mousemove", onMouseMove)
      window.removeEventListener("mouseup", onMouseUp)
    }

    window.addEventListener("mousemove", onMouseMove)
    window.addEventListener("mouseup", onMouseUp)
  }

  function renderContentStudioProject() {
    if (!contentStudioActiveProject) return

    const proceed = confirm(
      "Render this project now? This will save your current timeline edits first, then create the final MP4 with the correct template."
    )

    if (!proceed) return

    const draft = getContentStudioDraft()

    fetch(`${API}/content-studio/project/${contentStudioActiveProject.project_id}/edit`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_name: contentStudioActiveProject.project_name,
        clips: (contentStudioActiveProject.clips || []).map((clip, index) => ({
          clip_id: clip.clip_id,
          order: index + 1,
          title: clip.title,
          trim_start: Number(clip.trim_start || 0),
          trim_end: Number(clip.trim_end || 0),
          duration_seconds: Number(clip.duration_seconds || 0),
          selected_for_top10: !!clip.selected_for_top10
        })),
        top10_draft: contentStudioActiveProject.project_type === "top10" ? draft : null,
        solo_draft: contentStudioActiveProject.project_type === "solo" ? draft : null
      })
    })
      .then(async saveResponse => {
        const savedData = await saveResponse.json()

        if (!saveResponse.ok || savedData.found === false) {
          alert("Project save before render failed: " + JSON.stringify(savedData))
          return null
        }

        setContentStudioActiveProject({
          ...savedData.project,
          render_status: "rendering"
        })

        return fetch(`${API}/content-studio/project/${contentStudioActiveProject.project_id}/render`, {
          method: "POST"
        })
      })
      .then(async renderResponse => {
        if (!renderResponse) return

        const renderData = await renderResponse.json()

        if (!renderResponse.ok || renderData.ok === false) {
          setContentStudioActiveProject(renderData.project || contentStudioActiveProject)
          alert("Render failed: " + JSON.stringify(renderData.message || renderData.result || renderData))
          return
        }

        setContentStudioActiveProject(renderData.project)
        setContentStudioSelectedClipId(renderData.project?.clips?.[0]?.clip_id || contentStudioSelectedClipId)
        loadContentStudioData()
        alert("Render finished. Your final MP4 is ready to preview.")
      })
      .catch(err => alert("Render failed: " + err.message))
  }


  function syncYouTubeRevenue(syncType = "daily") {
    const isFull = syncType === "full"

    if (isFull) {
      const proceed = confirm(
        "Run a full YouTube revenue sync? This can take a while, but it should pull all-time YouTube Studio estimated revenue/RPM history into CourtVision."
      )

      if (!proceed) return
    }

    setYoutubeRevenueSyncing(true)

    const url = isFull
      ? `${API}/revenue/youtube/sync?sync_type=full&start_date=2022-10-09`
      : `${API}/revenue/youtube/sync?sync_type=daily`

    fetch(url, {
      method: "POST"
    })
      .then(async r => {
        const data = await r.json()

        if (!r.ok || data.ok === false) {
          alert("YouTube revenue sync failed: " + JSON.stringify(data.message || data))
          return
        }

        setYoutubeRevenueStatus(data.status || null)
        loadRevenueData()
        loadData()

        alert(
          `YouTube revenue sync complete. Channel rows: ${data.channel_rows_saved}. Video rows: ${data.video_rows_saved}.`
        )
      })
      .catch(err => {
        alert("YouTube revenue sync failed: " + err.message)
      })
      .finally(() => setYoutubeRevenueSyncing(false))
  }

  function analyzeThumbnail(file) {
    if (!file) return

    setThumbnailPreview(URL.createObjectURL(file))
    setThumbnailAnalysis(null)

    const formData = new FormData()
    formData.append("file", file)

    fetch(`${API}/thumbnail-analyzer/analyze`, {
      method: "POST",
      body: formData
    })
      .then(r => r.json())
      .then(d => setThumbnailAnalysis(d.analysis))
      .catch(() => {})
  }

  function riskColor(risk) {
    if (risk <= 35) return "#4ade80"
    if (risk <= 60) return "#facc15"
    return "#f87171"
  }

  function scoreColor(score) {
    if (score >= 80) return "#4ade80"
    if (score >= 60) return "#facc15"
    return "#f87171"
  }

  function viewsRange(item) {
    if (!item) return "—"

    const projected = Number(item.projected_views || 0)
    const low = Number(item.projected_views_low || 0)
    const high = Number(item.projected_views_high || 0)

    if (projected > 0) {
      return projected.toLocaleString()
    }

    if (low > 0 && high > 0) {
      if (low === high) return low.toLocaleString()
      return `${low.toLocaleString()}–${high.toLocaleString()}`
    }

    return "—"
  }

  function revenueRange(item) {
    if (!item) return "—"

    const projected = Number(item.projected_revenue || 0)
    const low = Number(item.projected_revenue_low || 0)
    const high = Number(item.projected_revenue_high || 0)

    if (projected > 0) {
      return formatMoney(projected)
    }

    if (low > 0 && high > 0) {
      if (low === high) return formatMoney(low)
      return `${formatMoney(low)}–${formatMoney(high)}`
    }

    return "—"
  }

  function subscriberRange(item) {
    if (!item) return "—"

    if (item.projected_subscribers_low && item.projected_subscribers_high) {
      return `${item.projected_subscribers_low.toLocaleString()}–${item.projected_subscribers_high.toLocaleString()}`
    }

    return item.projected_subscribers?.toLocaleString() || "—"
  }

  const nextIdea = players[0]
  const topIdeas = players.slice(0, 4)
  const topPlayers = rankings.slice(0, 5)

  const lifetimeChannelRevenue = Number(
    revenueSummary?.channel_by_period?.lifetime ??
    revenueSummary?.total_channel_youtube_revenue ??
    revenueSummary?.total_channel_manual_revenue ??
    stats.estimated_revenue ??
    0
  )

  const totalEstimatedRevenue = lifetimeChannelRevenue

  const dashboardTotalViews = Number(
    revenueSummary?.channel_views_by_period?.lifetime ??
    revenueSummary?.total_channel_views ??
    revenueSummary?.lifetime_channel_views ??
    stats.total_views ??
    0
  )

  const syncedVideoPercent = stats.video_count
    ? Math.min(100, Math.round((savedVideos.length / Number(stats.video_count || 1)) * 100))
    : 0

  const bestMoneyPlayer = rankings[0]
  const bestPlayerRevenueValue = Number(
    bestMoneyPlayer?.total_revenue ??
    bestMoneyPlayer?.synced_revenue ??
    bestMoneyPlayer?.manual_revenue ??
    bestMoneyPlayer?.average_revenue ??
    bestMoneyPlayer?.expected_revenue ??
    bestMoneyPlayer?.projected_revenue ??
    0
  )
  const forecastChannelRpmValue = Number(
    revenueForecast?.summary?.manual_channel_rpm ??
    stats?.manual_channel_rpm ??
    stats?.synced_rpm ??
    stats?.estimated_rpm ??
    0
  )

  const strategyUploadNextClean = (channelBrain?.upload_next || [])
    .filter(item => item && !isBadStrategyIdea(item))
    .slice(0, 15)

  const strategyIdeaLabShuffleIdeas = (players || []).map((item, index) => {
    const playerName = item?.player || item?.name || item?.player_name || item?.topic || "Unknown"
    const playerText = String(playerName || "").toLowerCase()

    const playerVideos = savedVideos.filter(video => {
      const title = String(video?.title || "").toLowerCase()
      const playerOnVideo = String(video?.player_name || "").toLowerCase()
      return playerOnVideo === playerText || title.includes(playerText)
    })

    const doneTop10Types = new Set()

    playerVideos.forEach(video => {
      const title = String(video?.title || "").toLowerCase()
      if (!title.includes("top 10") && !title.includes("top ten")) return

      if (title.includes("dunk")) doneTop10Types.add("Top 10 Dunks")
      else if (title.includes("assist") || title.includes("pass")) doneTop10Types.add("Top 10 Assists")
      else if (title.includes("block")) doneTop10Types.add("Top 10 Blocks")
      else if (title.includes("clutch") || title.includes("buzzer") || title.includes("game winner")) doneTop10Types.add("Top 10 Clutch Shots")
      else if (title.includes("cross") || title.includes("handle")) doneTop10Types.add("Top 10 Crossovers")
      else doneTop10Types.add("Top 10 Plays")
    })

    let format = "Top 10 Plays"

    if (doneTop10Types.has("Top 10 Plays")) {
      const lower = playerText

      if (
        lower.includes("shaq") || lower.includes("wilt") || lower.includes("kareem") ||
        lower.includes("hakeem") || lower.includes("david robinson") || lower.includes("bill russell") ||
        lower.includes("mutombo") || lower.includes("ewing") || lower.includes("garnett")
      ) {
        format = doneTop10Types.has("Top 10 Dunks") ? "Top 10 Blocks" : "Top 10 Dunks"
      } else if (
        lower.includes("magic") || lower.includes("john stockton") || lower.includes("steve nash") ||
        lower.includes("jason kidd") || lower.includes("chris paul") || lower.includes("kyrie") ||
        lower.includes("trae") || lower.includes("luka") || lower.includes("jokic")
      ) {
        format = doneTop10Types.has("Top 10 Assists") ? "Top 10 Clutch Shots" : "Top 10 Assists"
      } else if (
        lower.includes("julius erving") || lower.includes("vince carter") || lower.includes("dominique") ||
        lower.includes("jordan") || lower.includes("lebron") || lower.includes("kobe") ||
        lower.includes("anthony edwards") || lower.includes("ja morant")
      ) {
        format = doneTop10Types.has("Top 10 Dunks") ? "Top 10 Clutch Shots" : "Top 10 Dunks"
      } else {
        format = doneTop10Types.has("Top 10 Clutch Shots") ? "Top 10 Dunks" : "Top 10 Clutch Shots"
      }
    }

    const opportunityScore = Number(
      item?.opportunity_score ??
      item?.score ??
      item?.popularity_score ??
      item?.youtube_score ??
      50
    )

    const projectedViews = Number(
      item?.projected_views ??
      item?.expected_views ??
      item?.average_views ??
      item?.views_prediction ??
      0
    )

    const projectedRevenue = Number(
      item?.projected_revenue ??
      item?.expected_revenue ??
      item?.average_revenue ??
      item?.revenue_prediction ??
      0
    )

    return {
      ...item,
      player: playerName,
      player_name: playerName,
      topic: playerName,
      format,
      content_type: format,
      expected_views: projectedViews > 0 ? projectedViews : Math.round(Math.max(25000, opportunityScore * 900)),
      projected_views: projectedViews > 0 ? projectedViews : Math.round(Math.max(25000, opportunityScore * 900)),
      expected_revenue: projectedRevenue > 0 ? projectedRevenue : Math.round(Math.max(25, opportunityScore * 1.8) * 100) / 100,
      projected_revenue: projectedRevenue > 0 ? projectedRevenue : Math.round(Math.max(25, opportunityScore * 1.8) * 100) / 100,
      expected_rpm: Number(item?.expected_rpm ?? item?.projected_rpm ?? item?.average_rpm ?? 2.25),
      projected_rpm: Number(item?.expected_rpm ?? item?.projected_rpm ?? item?.average_rpm ?? 2.25),
      total_revenue: Number(item?.total_revenue ?? item?.synced_revenue ?? 0),
      videos: Number(item?.videos ?? item?.total_videos ?? playerVideos.length),
      opportunity_score: opportunityScore,
      reason: playerVideos.length
        ? `Idea Lab pick. Suggested next format: ${format}.`
        : "Idea Lab top pick. Suggested first format: Top 10 Plays.",
      source: "Idea Lab"
    }
  })

  const strategyShufflePoolRaw = [
    ...(channelBrain?.shuffle_ideas || []),
    ...(channelBrain?.upload_next || [])
  ].filter(item => item && !isBadStrategyIdea(item) && (item.player || item.player_name || item.topic || item.name))

  const strategyShufflePool = strategyShufflePoolRaw.filter((item, index, arr) => {
    const name = cleanStrategyName(item?.player || item?.player_name || item?.topic || item?.name)
    const format = cleanStrategyFormat(item?.format || item?.content_type || "Top 10 Plays")
    if (!name) return false

    const key = `${String(name).toLowerCase()}|${String(format).toLowerCase()}`
    return arr.findIndex(other => {
      const otherName = cleanStrategyName(other?.player || other?.player_name || other?.topic || other?.name)
      const otherFormat = cleanStrategyFormat(other?.format || other?.content_type || "Top 10 Plays")
      return `${String(otherName).toLowerCase()}|${String(otherFormat).toLowerCase()}` === key
    }) === index
  })







  const selectedChannelRevenueEntry = (channelRevenue || []).find(entry =>
    normalizeRevenuePeriod(entry.period_type) === revenuePeriod
  )

  const selectedVideoRevenueEntries = (videoRevenue || []).filter(entry =>
    normalizeRevenuePeriod(entry.period_type) === revenuePeriod
  )

  const selectedChannelRevenue = Number(
    selectedChannelRevenueEntry?.amount ??
    revenueSummary?.channel_by_period?.[revenuePeriod] ??
    0
  )

  const selectedChannelViews = Number(
    revenueSummary?.channel_views_by_period?.[revenuePeriod] ??
    selectedChannelRevenueEntry?.views ??
    0
  )

  const selectedChannelRpm = Number(
    revenueSummary?.channel_rpm_by_period?.[revenuePeriod] ??
    (selectedChannelViews > 0 ? (selectedChannelRevenue / selectedChannelViews) * 1000 : 0)
  )

  const selectedVideoRevenue = Number(
    revenueSummary?.video_by_period?.[revenuePeriod] ??
    selectedVideoRevenueEntries.reduce((sum, entry) => sum + Number(entry.amount || 0), 0)
  )

  const selectedVideoViews = Number(
    revenueSummary?.video_views_by_period?.[revenuePeriod] ??
    selectedVideoRevenueEntries.reduce((sum, entry) => sum + Number(entry.views || 0), 0)
  )

  const selectedVideoRpm = Number(
    revenueSummary?.video_rpm_by_period?.[revenuePeriod] ??
    (selectedVideoViews > 0 ? (selectedVideoRevenue / selectedVideoViews) * 1000 : 0)
  )

  const selectedChannelRawRevenue = Number(
    revenueSummary?.channel_raw_by_period?.[revenuePeriod] ??
    selectedChannelRevenue
  )

  const privateHiddenAdjustment = Number(
    revenueSummary?.private_hidden_lifetime_adjustment || 
    youtubeRevenueStatus?.private_hidden_lifetime_adjustment ||
    0
  )

  const topEarningVideos = selectedVideoRevenueEntries
    .filter(entry => Number(entry.amount || 0) > 0)
    .sort((a, b) => Number(b.amount || 0) - Number(a.amount || 0))

  const initialBootProgressText =
    initialBootDisplayProgress >= 100
      ? "100"
      : Number(Math.min(99.9, initialBootDisplayProgress || 0)).toFixed(1)

  const initialBootProgressBarWidth = `${Math.min(100, Math.max(0, Number(initialBootDisplayProgress || 0)))}%`

  const allRevenuePeriods = ["lifetime", "365d", "90d", "28d", "7d"]

  function findPlayerTop10Video(playerName) {
    const player = String(playerName || "").toLowerCase()

    if (!player) return null

    return (
      savedVideos.find(v =>
        String(v.player_name || "").toLowerCase() === player &&
        String(v.content_type || "").toLowerCase() === "top 10" &&
        v.thumbnail
      ) ||
      savedVideos.find(v =>
        String(v.title || "").toLowerCase().includes(player) &&
        String(v.title || "").toLowerCase().includes("top 10") &&
        v.thumbnail
      ) ||
      savedVideos.find(v =>
        String(v.player_name || "").toLowerCase() === player &&
        v.thumbnail
      )
    )
  }

  function normalizeRevenueTitle(value) {
    return String(value || "").trim().toLowerCase()
  }

  function getRevenueVideoKey(video) {
    const videoId = String(video?.video_id || "").trim()

    if (videoId) return `id:${videoId}`

    return `title:${normalizeRevenueTitle(video?.title || "")}`
  }

  function getRevenueEntryKey(entry) {
    const videoId = String(entry?.video_id || "").trim()

    if (videoId) return `id:${videoId}`

    return `title:${normalizeRevenueTitle(entry?.title || "")}`
  }

  function getRevenueEntriesForVideo(video) {
    const videoKey = getRevenueVideoKey(video)
    const titleKey = `title:${normalizeRevenueTitle(video?.title || "")}`

    return videoRevenue
      .filter(entry => {
        const entryKey = getRevenueEntryKey(entry)

        return entryKey === videoKey || entryKey === titleKey
      })
      .sort((a, b) => periodOrder(a.period_type) - periodOrder(b.period_type))
  }

  function getMissingRevenueCount(video) {
    const requiredPeriods = ["lifetime", "365d", "90d", "28d", "7d"]
    const entries = getRevenueEntriesForVideo(video)
    const enteredPeriods = new Set(entries.map(entry => String(entry.period_type || "").replace("30d", "28d")))

    return requiredPeriods.filter(period => !enteredPeriods.has(period)).length
  }

  function toggleVideoRevenueRow(video) {
    const key = getRevenueVideoKey(video)

    setOpenVideoRevenueRows(prev => ({
      ...prev,
      [key]: !prev[key]
    }))
  }

  if (initialBootLoading) {
    return (
      <div className="app">
        <div
          style={{
            minHeight: "100vh",
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            background: "radial-gradient(circle at top, rgba(255,255,255,0.08), rgba(0,0,0,0.95))"
          }}
        >
          <div
            style={{
              width: "min(520px, 92vw)",
              minHeight: "318px",
              boxSizing: "border-box",
              border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: "22px",
              padding: "28px",
              background: "rgba(10,10,14,0.92)",
              boxShadow: "0 24px 70px rgba(0,0,0,0.45)",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center"
            }}
          >
            <img src={logo} className="logo" style={{ width: "90px", marginBottom: "14px" }} />

            <h2 style={{ margin: "8px 0 10px" }}>Loading CourtVision AI</h2>

            <p style={{
              color: "rgba(255,255,255,0.72)",
              lineHeight: 1.5,
              minHeight: "48px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              margin: "0 auto"
            }}>
              {initialBootStep}
            </p>

            <div style={{
              marginTop: "8px",
              color: "rgba(255,255,255,0.9)",
              fontSize: "18px",
              fontWeight: 800,
              letterSpacing: "0.08em"
            }}>
              {initialBootProgressText}%
            </div>

            <div
              style={{
                height: "10px",
                borderRadius: "999px",
                overflow: "hidden",
                background: "rgba(255,255,255,0.12)",
                marginTop: "20px"
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: initialBootProgressBarWidth,
                  borderRadius: "999px",
                  background: "rgba(255,255,255,0.85)",
                  transition: "width 0.25s ease"
                }}
              />
            </div>

            <div style={{
              marginTop: "12px",
              display: "flex",
              justifyContent: "center",
              gap: "14px",
              flexWrap: "wrap",
              color: "rgba(255,255,255,0.62)",
              fontSize: "12px",
              lineHeight: 1.35
            }}>
              <span>
                Estimated Time Remaining: <b style={{ color: "rgba(255,255,255,0.82)" }}>{formatBootRemainingTime(initialBootRemainingSeconds)}</b>
              </span>
              <span>
                Loaded: <b style={{ color: "rgba(255,255,255,0.82)" }}>{Math.min(Math.max(1, Math.round(initialBootDisplayProgress)), 100)}/100</b>
              </span>
            </div>

            <small style={{ display: "block", marginTop: "16px", color: "rgba(255,255,255,0.5)" }}>
              {initialBootPhase === "video" ? "Syncing channel videos and public stats..." :
                initialBootPhase === "revenue" ? "Syncing YouTube Analytics revenue and RPM..." :
                initialBootPhase === "data" ? "Loading fully synced data for all tabs..." :
                "Syncing all data before opening dashboard..."}
            </small>
          </div>
        </div>
      </div>
    )
  }


  return (
    <div className="app">
      <div className="sidebar">
        <img src={logo} className="logo" />

        <div style={{
          margin: "8px 0 14px",
          padding: "8px 10px",
          borderRadius: "12px",
          background: autoSyncingAll ? "rgba(255,255,255,0.12)" : "rgba(255,255,255,0.06)",
          color: "rgba(255,255,255,0.72)",
          fontSize: "12px",
          lineHeight: 1.35
        }}>
          {autoSyncingAll ? "Auto-Syncing..." : "Auto-Sync On"}
          {lastAutoSync && (
            <div style={{ color: "rgba(255,255,255,0.45)" }}>
              Last Sync: {lastAutoSync.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
            </div>
          )}
        </div>

        <button className={tab === "dashboard" ? "active-tab" : ""} onClick={() => setTab("dashboard")}>Dashboard</button>
        <button className={tab === "videos" ? "active-tab" : ""} onClick={() => setTab("videos")}>Videos</button>
        <button className={tab === "rankings" ? "active-tab" : ""} onClick={() => setTab("rankings")}>Player Rankings</button>
        <button className={tab === "channelBrain" ? "active-tab" : ""} onClick={() => setTab("channelBrain")}>Strategy Center</button>
        <button className={tab === "revenue" ? "active-tab" : ""} onClick={() => setTab("revenue")}>Revenue Tracker</button>
        <button className={tab === "revenueForecast" ? "active-tab" : ""} onClick={() => setTab("revenueForecast")}>Revenue Forecast</button>
        <button className={tab === "deadRecovery" ? "active-tab" : ""} onClick={() => setTab("deadRecovery")}>Dead Video Recovery</button>
        <button className={tab === "ideas" ? "active-tab" : ""} onClick={() => setTab("ideas")}>Idea Lab</button>
        <button className={tab === "predictor" ? "active-tab" : ""} onClick={() => setTab("predictor")}>Player Predictor</button>
        <button className={tab === "thumbnail" ? "active-tab" : ""} onClick={() => setTab("thumbnail")}>Thumbnail Analyzer</button>
        <button className={tab === "contentStudio" ? "active-tab" : ""} onClick={() => setTab("contentStudio")}>Content Studio</button>
      </div>

      <div className="main">
        {tab === "dashboard" && (
          <>
            <div className="hero">
              <div>
                <h1 className="title">NBATop10 Analytics</h1>
                <p className="subtitle">AI-powered YouTube growth engine</p>
              </div>

              <div className="live-status">LIVE</div>
            </div>

            <div className="grid">
              <div className="card stat-card">
                <h2>{stats.subscribers?.toLocaleString() || "—"}</h2>
                <p>Subscribers</p>
              </div>

              <div className="card stat-card">
                <h2>{dashboardTotalViews > 0 ? dashboardTotalViews.toLocaleString() : "—"}</h2>
                <p>Total Views</p>
              </div>

              <div className="card stat-card">
                <h2>{formatMoney(lifetimeChannelRevenue)}</h2>
                <p>Total Revenue</p>
              </div>

              <div className="card stat-card">
                <h2>{syncedVideoPercent}%</h2>
                <p>Videos Synced</p>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Next Best Upload</h2>

                {nextIdea ? (
                  <>
                    <h3>{nextIdea.name}</h3>
                    <p>{nextIdea.video_idea}</p>

                    <div className="quick-stat">
                      <span>Projected Views</span>
                      <b>{viewsRange(nextIdea)}</b>
                    </div>

                    <div className="quick-stat">
                      <span>Projected Revenue</span>
                      <b>{revenueRange(nextIdea)}</b>
                    </div>

                    <div className="quick-stat">
                      <span>Copyright Risk</span>
                      <b style={{ color: riskColor(nextIdea.copyright_risk) }}>
                        {nextIdea.copyright_risk}%
                      </b>
                    </div>
                  </>
                ) : (
                  <p>Sync channel to generate ideas.</p>
                )}
              </div>

              <div className="card dashboard-card">
                <h2>Revenue Snapshot</h2>

                <div className="quick-stat">
                  <span>Revenue</span>
                  <b>{formatMoney(lifetimeChannelRevenue)}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Money Player</span>
                  <b>{bestMoneyPlayer?.player || "—"}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Player Revenue</span>
                  <b>{bestPlayerRevenueValue > 0 ? formatMoney(bestPlayerRevenueValue) : "$0.00"}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Money Pattern</span>
                  <b>Legends / Nostalgia</b>
                </div>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Top Idea Lab Picks</h2>

                {topIdeas.map((p, i) => (
                  <div className="mini-row" key={i}>
                    <span>#{i + 1} {p.name}</span>
                    <span>{revenueRange(p)}</span>
                  </div>
                ))}

                {topIdeas.length === 0 && (
                  <p>No Idea Lab picks loaded yet.</p>
                )}
              </div>

              <div className="card dashboard-card">
                <h2>Copyright Safety</h2>

                <div className="quick-stat">
                  <span>Safest Strategy</span>
                  <b>Older legends</b>
                </div>

                <div className="quick-stat">
                  <span>Riskier Strategy</span>
                  <b>Modern clips</b>
                </div>

                <div className="quick-stat">
                  <span>Current Channel Risk</span>
                  <b style={{ color: "#facc15" }}>Moderate</b>
                </div>

                <div className="quick-stat">
                  <span>Best Format</span>
                  <b>Top 10</b>
                </div>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Top Performing Players</h2>

                {topPlayers.map((p, i) => (
                  <div className="mini-row" key={i}>
                    <span>#{i + 1} {p.player}</span>
                    <span>{p.total_views?.toLocaleString()} views</span>
                  </div>
                ))}
              </div>

              <div className="card dashboard-card">
                <h2>Thumbnail Score Shortcut</h2>

                {thumbnailAnalysis ? (
                  <>
                    <div className="quick-stat">
                      <span>Last CTR Score</span>
                      <b style={{ color: scoreColor(thumbnailAnalysis.ctr_score) }}>
                        {thumbnailAnalysis.ctr_score}/100
                      </b>
                    </div>

                    <div className="quick-stat">
                      <span>Verdict</span>
                      <b>{thumbnailAnalysis.verdict}</b>
                    </div>
                  </>
                ) : (
                  <>
                    <p>No thumbnail analyzed yet.</p>
                    <button className="sync" onClick={() => setTab("thumbnail")}>
                      Analyze Thumbnail
                    </button>

                    {savedVideos.find(video => video.thumbnail)?.thumbnail && (
                      <img
                        src={savedVideos.find(video => video.thumbnail)?.thumbnail}
                        alt="Top video thumbnail"
                        style={{
                          width: "100%",
                          maxWidth: "360px",
                          aspectRatio: "16 / 9",
                          objectFit: "cover",
                          borderRadius: "16px",
                          border: "1px solid #303030",
                          marginTop: "22px",
                          boxShadow: "0 0 22px rgba(0, 0, 0, 0.45)"
                        }}
                      />
                    )}
                  </>
                )}
              </div>
            </div>
          </>
        )}

        {tab === "videos" && (
          <div className="card big">
            <h2>Saved Channel Videos</h2>

            {savedVideos.map((v, i) => (
              <div className="video-row" key={i}>
                <div className="video-info">
                  <b>#{i + 1} {v.title}</b>
                  <span>Views: {(v.views || 0).toLocaleString()}</span>
                  <span>Likes: {(v.likes || 0).toLocaleString()}</span>
                  <span>Comments: {(v.comments || 0).toLocaleString()}</span>
                  <span>Revenue: {formatMoney(v.manual_revenue || v.estimated_revenue || 0)}</span>
                  <span>RPM: {formatMoney(v.manual_rpm || v.estimated_rpm || 0)}</span>
                </div>

                {v.thumbnail ? (
                  <img
                    src={v.thumbnail}
                    alt={v.title}
                    className="video-thumbnail"
                  />
                ) : (
                  <div className="video-thumbnail placeholder">No Thumbnail</div>
                )}
              </div>
            ))}
          </div>
        )}

        {tab === "rankings" && (
          <div className="card big">
            <h2>Player Rankings</h2>

            {rankings.map((p, i) => {
              const playerVideo = findPlayerTop10Video(p.player)

              return (
                <div className="video-row" key={i}>
                  <div className="video-info">
                    <b>#{i + 1} {p.player}</b>
                    <span>Total Views: {(p.total_views || 0).toLocaleString()}</span>
                    <span>Average Views: {(p.average_views || 0).toLocaleString()}</span>
                    <span>Revenue: {formatMoney(p.estimated_revenue || p.manual_revenue || 0)}</span>
                    <span>Videos: {p.videos}</span>
                  </div>

                  {playerVideo?.thumbnail ? (
                    <img
                      src={playerVideo.thumbnail}
                      alt={p.player}
                      className="video-thumbnail"
                    />
                  ) : (
                    <div className="video-thumbnail placeholder">No Top 10 Thumbnail</div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {tab === "channelBrain" && (
          <div className="card big ai-strategy-page">
            <div className="ai-strategy-header">
              <span className="editor-kicker">Strategy Center</span>
              <h2>Strategy Center</h2>
              <p>
                Final upload strategy using synced revenue, RPM, views, player history, format signals, and content-gap value.
              </p>
            </div>

            {!channelBrain ? (
              <div className="ai-brain-loading">Loading Strategy Center...</div>
            ) : (
              <>
                {(() => {
                  const uniquePool = strategyShufflePool

                  const best = uniquePool.length
                    ? uniquePool[strategyShuffleIndex % uniquePool.length]
                    : channelBrain?.best_next_upload

                  const playerName = cleanStrategyName(best?.player || best?.player_name || best?.topic || best?.name || "—")
                  const ideaTitle = best?.title || best?.video_idea || ""
                  const formatName = cleanStrategyFormat(getSmartVisibleFormatForStrategyIdea(best))
                  const eraName = normalizeAiStrategyEra(best?.era || "—")
                  const expectedViews = Number(best?.expected_views || best?.projected_views || best?.average_views || 0)
                  const expectedRevenue = Number(best?.expected_revenue || best?.projected_revenue || best?.average_revenue || 0)
                  const expectedRpm = Number(best?.expected_rpm || best?.projected_rpm || best?.average_rpm || (expectedViews > 0 && expectedRevenue > 0 ? (expectedRevenue / expectedViews) * 1000 : 0) || 0)
                  const reason = best?.reason || channelBrain?.headline || "Best available recommendation based on synced channel performance."

                  return (
                    <div className="ai-strategy-best-next final-ai-brain-card">
                      <div className="ai-panel-heading">
                        <span>Best Next Upload</span>
                        <small>money-focused pick</small>
                      </div>

                      <div className="ai-brain-focus-top final-ai-brain-top">
                        <div>
                          <span className="editor-kicker">Recommended Next Move</span>
                          <h3>{playerName !== "—" ? `Plan a ${cleanStrategyName(playerName)} ${cleanStrategyFormat(formatName)} upload next.` : "Sync strategy data to generate your next upload."}</h3>
                        </div>

                        <div className="ai-brain-time-pill">
                          <span>Best Upload Time</span>
                          <b>{channelBrain?.best_upload_time || "6:00 PM"}</b>
                        </div>

                        <button
                          className="strategy-shuffle-button"
                          type="button"
                          onClick={shuffleStrategyIdea}
                        >
                          Shuffle Idea
                        </button>
                      </div>

                      <p className="final-ai-reason">{reason}</p>

                      <div className="ai-strategy-best-grid">
                        <div>
                          <span>Player / Topic</span>
                          <b>{playerName}</b>
                        </div>

                        <div>
                          <span>Format</span>
                          <b>{cleanStrategyFormat(formatName)}</b>
                        </div>

                        <div>
                          <span>Era</span>
                          <b>{eraName}</b>
                        </div>

                        <div>
                          <span>Expected Views</span>
                          <b>{expectedViews > 0 ? expectedViews.toLocaleString() : "—"}</b>
                        </div>

                        <div>
                          <span>Expected Revenue</span>
                          <b>{expectedRevenue > 0 ? formatMoney(expectedRevenue) : "—"}</b>
                        </div>

                        <div>
                          <span>Expected RPM</span>
                          <b>{expectedRpm > 0 ? formatMoney(expectedRpm) : "—"}</b>
                        </div>
                      </div>
                    </div>
                  )
                })()}

                <div className="ai-brain-two-col">
                  <div className="ai-brain-panel">
                    <div className="ai-panel-heading">
                      <span>Upload Next</span>
                      <small>highest money opportunity</small>
                    </div>

                    <div className="ai-brain-list">
                      {strategyUploadNextClean.length > 0 ? (
                        aiStrategyVisibleItems(strategyUploadNextClean, "uploadNext").map((p, i) => (
                          <div className="ai-brain-row" key={i}>
                            <div>
                              <b>#{i + 1} {cleanStrategyName(p.player || p.player_name || p.topic || p.name)}</b>
                              <small>{p.reason || "Strong revenue/RPM signal"}</small>
                            </div>
                            <strong>{formatMoney(p.total_revenue || p.synced_revenue || p.expected_revenue || p.projected_revenue || p.average_revenue || 0)}</strong>
                          </div>
                        ))
                      ) : (
                        <p>No upload-next suggestions yet.</p>
                      )}
                    </div>
                  </div>

                  <div className="ai-brain-panel">
                    <div className="ai-panel-heading">
                      <span>Avoid Next</span>
                      <small>weak money signal</small>
                    </div>

                    <div className="ai-brain-list">
                      {channelBrain?.avoid_next?.length > 0 ? (
                        aiStrategyAvoidVisibleItems(channelBrain.avoid_next).map((p, i) => (
                          <div className="ai-brain-row" key={i}>
                            <div>
                              <b>#{i + 1} {cleanStrategyName(p.player || p.player_name || p.topic || p.name)}</b>
                              <small>{p.reason || "Weak revenue/RPM signal"}</small>
                            </div>
                            <strong>{formatMoney(p.average_revenue || p.total_revenue || 0)}</strong>
                          </div>
                        ))
                      ) : (
                        <p>No avoid warnings yet.</p>
                      )}
                    </div>
                  </div>
                </div>


                {(strategyUploadNextClean.length > 5 || (channelBrain?.avoid_next || []).length > 5) && (
                  <button
                    className="show-more-button strategy-shared-show-more"
                    onClick={() => toggleAiStrategyList("strategyBoth")}
                  >
                    {isAiStrategyListExpanded("strategyBoth") ? "Show Less" : "Show More (15)"}
                  </button>
                )}

                <div className="ai-brain-panel final-action-panel">
                  <div className="ai-panel-heading">
                    <span>Action Plan</span>
                    <small>next step</small>
                  </div>

                  <div className="final-action-grid">
                    {channelBrain?.action_plan?.length > 0 ? (
                      channelBrain.action_plan.slice(0, 5).map((item, i) => (
                        <div className="final-action-card" key={i}>
                          <span>{i + 1}</span>
                          <p>{item}</p>
                        </div>
                      ))
                    ) : (
                      <p>No action plan yet.</p>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {tab === "revenue" && (
          <div className="card big revenue-clean-tracker revenue-tracker-perfect">
            <div className="revenue-hero-card">
              <div className="revenue-hero-copy">
                <span className="editor-kicker">YouTube Analytics API</span>
                <h2>Revenue Tracker</h2>
                <p>
                  Auto-synced YouTube Studio estimated revenue and RPM. Rolling periods use the last completed day so the totals stay close to Studio.
                </p>
              </div>

              <div className="revenue-sync-mini-panel">
                <div className="revenue-sync-mini-grid">
                  <div>
                    <span>Last Sync</span>
                    <b>{youtubeRevenueStatus?.latest_sync?.synced_at ? formatDateTime(youtubeRevenueStatus.latest_sync.synced_at) : "Not synced yet"}</b>
                  </div>

                  <div>
                    <span>Data Range</span>
                    <b>
                      {formatDateFull(youtubeRevenueStatus?.first_analytics_date)}
                      {" → "}
                      {formatDateFull(youtubeRevenueStatus?.last_analytics_date)}
                    </b>
                  </div>

                  <div>
                    <span>Synced Rows</span>
                    <b>{(youtubeRevenueStatus?.total_daily_rows || 0).toLocaleString()}</b>
                  </div>
                </div>
              </div>
            </div>

            <div className="revenue-period-tabs">
              {allRevenuePeriods.map(period => (
                <button
                  key={period}
                  className={revenuePeriod === period ? "active-period" : ""}
                  onClick={() => setRevenuePeriod(period)}
                >
                  {periodLabel(period)}
                </button>
              ))}
            </div>

            <div className="grid revenue-main-metrics">
              <div className="card stat-card metric-card primary-revenue-card">
                <h2 className="metric-value">{formatMoney(selectedChannelRevenue)}</h2>
                <p>{periodLabel(revenuePeriod)} Revenue</p>
              </div>

              <div className="card stat-card metric-card">
                <h2 className="metric-value">{selectedChannelViews.toLocaleString()}</h2>
                <p>{periodLabel(revenuePeriod)} Views</p>
              </div>

              <div className="card stat-card metric-card">
                <h2 className="metric-value">{formatMoney(selectedChannelRpm)}</h2>
                <p>{periodLabel(revenuePeriod)} RPM</p>
              </div>

              <div className="card stat-card metric-card">
                <h2 className="metric-value">{topEarningVideos.length.toLocaleString()}</h2>
                <p>Videos With Revenue</p>
              </div>
            </div>

            <div className="card big revenue-period-summary-card">
              <div className="auto-revenue-header compact">
                <div>
                  <h2>Revenue By Period</h2>
                  <p>Click a period to update the totals and top earning videos below.</p>
                </div>
              </div>

              <div className="revenue-period-list clean-period-list">
                {allRevenuePeriods.map(period => (
                  <button
                    type="button"
                    className={`revenue-period-item revenue-period-button ${revenuePeriod === period ? "active-revenue-period" : ""}`}
                    key={period}
                    onClick={() => setRevenuePeriod(period)}
                  >
                    <span className="revenue-period-label">{periodLabel(period)}</span>
                    <span className="revenue-period-value">{formatMoney(revenueSummary?.channel_by_period?.[period] || 0)}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="card big top-earning-videos-card">
              <div className="auto-revenue-header compact">
                <div>
                  <h2>Top Earning Videos</h2>
                  <p>Most to least revenue for {periodLabel(revenuePeriod)}.</p>
                </div>

                <div className="top-earning-count">
                  {topEarningVideos.length.toLocaleString()} videos
                </div>
              </div>

              {topEarningVideos.length > 0 ? (
                <div className="top-earning-list">
                  {topEarningVideos.map((entry, index) => {
                    const matchedVideo = savedVideos.find(video => video.video_id === entry.video_id)

                    return (
                      <div className="top-earning-row" key={`${entry.video_id}-${entry.period_type}-${index}`}>
                        <div className="top-earning-rank">#{index + 1}</div>

                        {matchedVideo?.thumbnail ? (
                          <img
                            className="top-earning-thumb"
                            src={matchedVideo.thumbnail}
                            alt={entry.title || matchedVideo.title || "Video thumbnail"}
                          />
                        ) : (
                          <div className="top-earning-thumb placeholder">No Thumbnail</div>
                        )}

                        <div className="top-earning-info">
                          <b>{entry.title || matchedVideo?.title || "Untitled Video"}</b>
                          <span>Views: {Number(entry.views || 0).toLocaleString()} • RPM: {formatMoney(entry.rpm || 0)}</span>
                        </div>

                        <div className="top-earning-money">
                          {formatMoney(entry.amount || 0)}
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                <p>No synced video revenue found for {periodLabel(revenuePeriod)} yet. Run Sync Revenue or Full Backfill.</p>
              )}
            </div>
          </div>
        )}

        {tab === "revenueForecast" && (
          <div className="card big revenue-forecast-page">
            <div className="forecast-header">
              <span className="editor-kicker">Revenue Forecast</span>
              <h2>Revenue Forecast</h2>
              <p>
                Forecasts use your synced revenue/RPM data to estimate short-term and long-term earning pace.
              </p>
            </div>

            {!revenueForecast ? (
              <div className="forecast-loading">Loading revenue forecast...</div>
            ) : (
              <>
                <div className="forecast-metric-grid">
                  <div className="forecast-metric-card primary">
                    <span>Latest 7 Days</span>
                    <b>{formatMoney(revenueForecast.summary?.latest_7d_revenue || 0)}</b>
                    <small>recent earning pace</small>
                  </div>

                  <div className="forecast-metric-card">
                    <span>Latest 28 Days</span>
                    <b>{formatMoney(revenueForecast.summary?.latest_28d_revenue || 0)}</b>
                    <small>monthly trend base</small>
                  </div>

                  <div className="forecast-metric-card">
                    <span>Projected Monthly</span>
                    <b>{formatMoney(revenueForecast.forecast?.projected_monthly || 0)}</b>
                    <small>current run rate</small>
                  </div>

                  <div className="forecast-metric-card">
                    <span>Projected Yearly</span>
                    <b>{formatMoney(revenueForecast.forecast?.projected_yearly || 0)}</b>
                    <small>12-month pace</small>
                  </div>
                </div>

                <div className="forecast-panel forecast-video-panel">
                  <div className="forecast-panel-heading">
                    <span>Top Video Revenue Forecasts</span>
                    <small>best upside from more views</small>
                  </div>

                  {revenueForecast.top_video_forecasts?.length > 0 ? (
                    <div className="forecast-video-list">
                      {revenueForecast.top_video_forecasts.slice(0, 10).map((v, i) => {
                        const match = savedVideos.find(saved =>
                          saved.video_id === v.video_id ||
                          saved.title === v.title ||
                          String(saved.title || "").toLowerCase() === String(v.title || "").toLowerCase()
                        )

                        return (
                          <div className="forecast-video-row" key={i}>
                            {match?.thumbnail ? (
                              <img
                                src={match.thumbnail}
                                alt={v.title}
                                className="forecast-video-thumb"
                              />
                            ) : (
                              <div className="forecast-video-thumb placeholder">
                                No Thumbnail
                              </div>
                            )}

                            <div className="forecast-video-main">
                              <b>#{i + 1} {v.title}</b>
                              <div className="forecast-video-meta">
                                <span>{v.player || "Unknown"}</span>
                                <span>{normalizeContentFormat(v.content_type)}</span>
                                <span>{v.views?.toLocaleString()} views</span>
                              </div>
                            </div>

                            <div className="forecast-video-money">
                              <div>
                                <span>Revenue</span>
                                <b>{formatMoney(v.manual_revenue || 0)}</b>
                              </div>

                              <div>
                                <span>RPM</span>
                                <b>{formatMoney(v.manual_rpm || 0)}</b>
                              </div>

                              <div>
                                <span>Next 10k</span>
                                <b>{formatMoney(v.estimated_next_10k_views_revenue || 0)}</b>
                              </div>

                              <div>
                                <span>Next 100k</span>
                                <b>{formatMoney(v.estimated_next_100k_views_revenue || 0)}</b>
                              </div>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  ) : (
                    <p>No video forecast data yet. Sync revenue and video RPM first.</p>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {tab === "deadRecovery" && (
          <div className="card big dead-recovery-page">
            <div className="dead-recovery-header">
              <span className="editor-kicker">Dead Video Recovery</span>
              <h2>Dead Video Recovery</h2>
              <p>
                Finds older or underperforming videos that are worth saving with better titles, thumbnails, playlists, community posts, remakes, or fresh uploads.
              </p>
            </div>

            {!deadRecoveryData ? (
              <div className="dead-recovery-loading">Loading dead video recovery...</div>
            ) : (
              <>
                <div className="dead-recovery-metric-grid">
                  <div className="dead-recovery-metric-card">
                    <span>Videos Scanned</span>
                    <b>{deadRecoveryData.summary?.total_videos_scanned || 0}</b>
                    <small>total channel videos checked</small>
                  </div>

                  <div className="dead-recovery-metric-card">
                    <span>Recovery Candidates</span>
                    <b>{deadRecoveryData.summary?.total_recovery_candidates || 0}</b>
                    <small>worth improving or refreshing</small>
                  </div>

                  <div className="dead-recovery-metric-card">
                    <span>High RPM / Low Reach</span>
                    <b>{deadRecoveryData.summary?.high_rpm_low_reach || 0}</b>
                    <small>good money signal, low exposure</small>
                  </div>

                  <div className="dead-recovery-metric-card">
                    <span>Revenue Leaks</span>
                    <b>{deadRecoveryData.summary?.revenue_leaks || 0}</b>
                    <small>views without strong RPM</small>
                  </div>
                </div>

                <div className="dead-recovery-panel">
                  <div className="dead-recovery-panel-heading">
                    <span>Recovery Insights</span>
                    <small>what the scan found</small>
                  </div>

                  <div className="dead-recovery-note-list">
                    {deadRecoveryData.insights?.length > 0 ? (
                      deadRecoveryData.insights.slice(0, 5).map((insight, i) => (
                        <p key={i}>• {insight}</p>
                      ))
                    ) : (
                      <p>No recovery insights yet.</p>
                    )}
                  </div>
                </div>

                <div className="dead-recovery-two-col dead-recovery-equal-row">
                  <div className="dead-recovery-panel">
                    <div className="dead-recovery-panel-heading">
                      <span>Top Recovery Candidates</span>
                      <small>highest overall priority</small>
                    </div>

                    <div className="dead-recovery-rank-list">
                      {deadRecoveryData.top_candidates?.length > 0 ? (
                        deadRecoveryVisibleItems(deadRecoveryData.top_candidates, "topCandidates").map((v, i) => (
                          <div className="dead-recovery-rank-row" key={i}>
                            <div>
                              <b>#{i + 1} {v.title}</b>
                              <small>{v.recovery_category || "Recovery Candidate"} • {(v.views || 0).toLocaleString()} views</small>
                            </div>
                            <strong>{v.recovery_score || 0}</strong>
                          </div>
                        ))
                      ) : (
                        <p>No recovery candidates yet.</p>
                      )}
                    </div>

                    {deadRecoveryData.top_candidates?.length > 5 && (
                      <button className="dead-recovery-show-more" onClick={() => toggleDeadRecoveryList("topCandidates")}>
                        {isDeadRecoveryListExpanded("topCandidates") ? "Show Less" : "Show More"}
                      </button>
                    )}
                  </div>

                  <div className="dead-recovery-panel">
                    <div className="dead-recovery-panel-heading">
                      <span>High RPM / Low Reach</span>
                      <small>fix title or thumbnail first</small>
                    </div>

                    <div className="dead-recovery-rank-list">
                      {deadRecoveryData.high_rpm_low_reach?.length > 0 ? (
                        deadRecoveryVisibleItems(deadRecoveryData.high_rpm_low_reach, "highRpmLowReach").map((v, i) => (
                          <div className="dead-recovery-rank-row" key={i}>
                            <div>
                              <b>#{i + 1} {v.title}</b>
                              <small>{v.player || "Unknown"} • {(v.views || 0).toLocaleString()} views</small>
                            </div>
                            <strong>{formatMoney(v.manual_rpm || 0)} RPM</strong>
                          </div>
                        ))
                      ) : (
                        <p>No high-RPM low-reach videos yet.</p>
                      )}
                    </div>

                    {deadRecoveryData.high_rpm_low_reach?.length > 5 && (
                      <button className="dead-recovery-show-more" onClick={() => toggleDeadRecoveryList("highRpmLowReach")}>
                        {isDeadRecoveryListExpanded("highRpmLowReach") ? "Show Less" : "Show More"}
                      </button>
                    )}
                  </div>
                </div>

                <div className="dead-recovery-two-col dead-recovery-equal-row">
                  <div className="dead-recovery-panel">
                    <div className="dead-recovery-panel-heading">
                      <span>Remake / Reupload Candidates</span>
                      <small>fresh version may work better</small>
                    </div>

                    <div className="dead-recovery-rank-list">
                      {[...(deadRecoveryData.remake_candidates || []), ...(deadRecoveryData.reupload_candidates || [])].length > 0 ? (
                        deadRecoveryVisibleItems([...(deadRecoveryData.remake_candidates || []), ...(deadRecoveryData.reupload_candidates || [])], "remakeReupload").map((v, i) => (
                          <div className="dead-recovery-rank-row" key={i}>
                            <div>
                              <b>#{i + 1} {v.title}</b>
                              <small>{v.recovery_category || "Remake Candidate"} • {v.age_days || 0} days old</small>
                            </div>
                            <strong>{formatMoney(v.manual_revenue || 0)}</strong>
                          </div>
                        ))
                      ) : (
                        <p>No remake or reupload candidates yet.</p>
                      )}
                    </div>

                    {[...(deadRecoveryData.remake_candidates || []), ...(deadRecoveryData.reupload_candidates || [])].length > 5 && (
                      <button className="dead-recovery-show-more" onClick={() => toggleDeadRecoveryList("remakeReupload")}>
                        {isDeadRecoveryListExpanded("remakeReupload") ? "Show Less" : "Show More"}
                      </button>
                    )}
                  </div>

                  <div className="dead-recovery-panel">
                    <div className="dead-recovery-panel-heading">
                      <span>Revenue Leaks</span>
                      <small>views with weak monetization</small>
                    </div>

                    <div className="dead-recovery-rank-list">
                      {deadRecoveryData.revenue_leaks?.length > 0 ? (
                        deadRecoveryVisibleItems(deadRecoveryData.revenue_leaks, "revenueLeaks").map((v, i) => (
                          <div className="dead-recovery-rank-row" key={i}>
                            <div>
                              <b>#{i + 1} {v.title}</b>
                              <small>{(v.views || 0).toLocaleString()} views • {formatMoney(v.manual_rpm || 0)} RPM</small>
                            </div>
                            <strong>{formatMoney(v.manual_revenue || 0)}</strong>
                          </div>
                        ))
                      ) : (
                        <p>No major revenue leaks yet.</p>
                      )}
                    </div>

                    {deadRecoveryData.revenue_leaks?.length > 5 && (
                      <button className="dead-recovery-show-more" onClick={() => toggleDeadRecoveryList("revenueLeaks")}>
                        {isDeadRecoveryListExpanded("revenueLeaks") ? "Show Less" : "Show More"}
                      </button>
                    )}
                  </div>
                </div>

                <div className="dead-recovery-panel">
                  <div className="dead-recovery-panel-heading">
                    <span>Recommended Fixes</span>
                    <small>next step</small>
                  </div>

                  <div className="dead-recovery-action-list">
                    {deadRecoveryData.recommendations?.length > 0 ? (
                      deadRecoveryData.recommendations.slice(0, 6).map((step, i) => (
                        <div className="dead-recovery-action-step" key={i}>
                          <span>{i + 1}</span>
                          <p>{step}</p>
                        </div>
                      ))
                    ) : (
                      <p>No recovery recommendations yet.</p>
                    )}
                  </div>
                </div>

                <div className="dead-recovery-panel dead-recovery-video-panel">
                  <div className="dead-recovery-panel-heading">
                    <span>Full Recovery List</span>
                    <small>ranked by recovery score</small>
                  </div>

                  {deadRecoveryData.top_candidates?.length > 0 ? (
                    <>
                      <div className="dead-recovery-video-list">
                        {deadRecoveryVisibleItems(deadRecoveryData.top_candidates, "fullRecoveryList").map((v, i) => (
                          <div className="dead-recovery-video-row" key={i}>
                            {v.thumbnail ? (
                              <img src={v.thumbnail} alt={v.title} className="dead-recovery-thumb" />
                            ) : (
                              <div className="dead-recovery-thumb placeholder">No Thumbnail</div>
                            )}

                            <div className="dead-recovery-video-main">
                              <b>#{i + 1} {v.title}</b>
                              <div className="dead-recovery-video-meta">
                                <span>{v.player || "Unknown"}</span>
                                <span>{normalizeContentFormat(v.content_type)}</span>
                                <span>{v.recovery_category || "Recovery"}</span>
                                <span>{(v.views || 0).toLocaleString()} views</span>
                              </div>
                            </div>

                            <div className="dead-recovery-video-money">
                              <div>
                                <span>Score</span>
                                <b>{v.recovery_score || 0}</b>
                              </div>

                              <div>
                                <span>Revenue</span>
                                <b>{formatMoney(v.manual_revenue || 0)}</b>
                              </div>

                              <div>
                                <span>RPM</span>
                                <b>{formatMoney(v.manual_rpm || 0)}</b>
                              </div>

                              <div>
                                <span>100k Est.</span>
                                <b>{formatMoney(v.estimated_revenue_if_100k_views || 0)}</b>
                              </div>
                            </div>
                          </div>
                        ))}
                      </div>

                      {deadRecoveryData.top_candidates?.length > 5 && (
                        <button className="dead-recovery-show-more" onClick={() => toggleDeadRecoveryList("fullRecoveryList")}>
                          {isDeadRecoveryListExpanded("fullRecoveryList") ? "Show Less" : "Show More"}
                        </button>
                      )}
                    </>
                  ) : (
                    <p>No full recovery list yet.</p>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {tab === "ideas" && (
          <div className="card big idea-lab-page">
            <div className="idea-lab-header">
              <span className="editor-kicker">Idea Lab</span>
              <h2>NBA Idea Lab</h2>
              <p>
                Ranks the best next players from your full NBA player database using channel history, real revenue/RPM signals, player profile, era, saturation risk, and content-gap value.
              </p>
            </div>

            <div className="idea-lab-metric-grid">
              <div className="idea-lab-metric-card">
                <span>Players Ranked</span>
                <b>{players.length}</b>
                <small>top database picks returned</small>
              </div>

              <div className="idea-lab-metric-card">
                <span>Best Pick</span>
                <b>{players[0]?.name || "—"}</b>
                <small>highest decision score</small>
              </div>

              <div className="idea-lab-metric-card">
                <span>Expected Revenue</span>
                <b>{formatMoney(players[0]?.projected_revenue || 0)}</b>
                <small>single exact-style estimate</small>
              </div>

              <div className="idea-lab-metric-card">
                <span>Confidence</span>
                <b>{players[0]?.revenue_confidence || "—"}</b>
                <small>based on available data</small>
              </div>
            </div>

            <div className="idea-lab-panel">
              <div className="idea-lab-panel-heading">
                <span>Best Next Uploads</span>
                <small>top 5 shown, expand for more</small>
              </div>

              {players.length > 0 ? (
                <>
                  <div className="idea-lab-list">
                    {ideaLabVisibleItems(players, "bestIdeas").map((p, i) => (
                      <div className="idea-lab-row" key={i}>
                        <div className="idea-lab-rank">#{i + 1}</div>

                        <div className="idea-lab-main">
                          <b>{p.name}</b>
                          <small>{p.video_idea}</small>

                          <div className="idea-lab-tags">
                            <span>{p.era || "Unknown Era"}</span>
                            <span>{p.position || "Unknown Position"}</span>
                            <span>{p.priority || "Unranked"}</span>
                            <span>{p.top_10_done ? "Top 10 Already Done" : "Content Gap"}</span>
                          </div>

                          <p>{p.recommendation}</p>
                        </div>

                        <div className="idea-lab-money">
                          <div>
                            <span>Expected Revenue</span>
                            <b>{formatMoney(p.projected_revenue || 0)}</b>
                          </div>

                          <div>
                            <span>Expected Views</span>
                            <b>{(p.projected_views || 0).toLocaleString()}</b>
                          </div>

                          <div>
                            <span>Expected RPM</span>
                            <b>{formatMoney(p.expected_rpm || 0)}</b>
                          </div>

                          <div>
                            <span>Decision Score</span>
                            <b>{Number(p.decision_score || p.recommended_score || 0).toFixed(2)}</b>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {players.length > 5 && (
                    <button className="idea-lab-show-more" onClick={() => toggleIdeaLabList("bestIdeas")}>
                      {isIdeaLabListExpanded("bestIdeas") ? "Show Less" : "Show More"}
                    </button>
                  )}
                </>
              ) : (
                <p>No idea lab players loaded yet.</p>
              )}
            </div>

            <div className="idea-lab-two-col">
              <div className="idea-lab-panel">
                <div className="idea-lab-panel-heading">
                  <span>Best Undone Top 10s</span>
                  <small>highest content-gap value</small>
                </div>

                <div className="idea-lab-mini-list">
                  {ideaLabVisibleItems(players.filter(p => !p.top_10_done), "undone").map((p, i) => (
                    <div className="idea-lab-mini-row" key={i}>
                      <div>
                        <b>#{i + 1} {p.name}</b>
                        <small>{p.era || "Unknown"} • {p.priority || "Unranked"}</small>
                      </div>
                      <strong>{formatMoney(p.projected_revenue || 0)}</strong>
                    </div>
                  ))}
                </div>

                {players.filter(p => !p.top_10_done).length > 5 && (
                  <button className="idea-lab-show-more" onClick={() => toggleIdeaLabList("undone")}>
                    {isIdeaLabListExpanded("undone") ? "Show Less" : "Show More"}
                  </button>
                )}
              </div>

              <div className="idea-lab-panel">
                <div className="idea-lab-panel-heading">
                  <span>Safest Money Picks</span>
                  <small>lower risk + stronger return</small>
                </div>

                <div className="idea-lab-mini-list">
                  {ideaLabVisibleItems([...players].filter(p => Number(p.copyright_risk || 0) <= 55).sort((a, b) => Number(b.projected_revenue || 0) - Number(a.projected_revenue || 0)), "safeMoney").map((p, i) => (
                    <div className="idea-lab-mini-row" key={i}>
                      <div>
                        <b>#{i + 1} {p.name}</b>
                        <small>Risk: {p.copyright_risk}% • {p.revenue_confidence}</small>
                      </div>
                      <strong>{formatMoney(p.projected_revenue || 0)}</strong>
                    </div>
                  ))}
                </div>

                {players.filter(p => Number(p.copyright_risk || 0) <= 55).length > 5 && (
                  <button className="idea-lab-show-more" onClick={() => toggleIdeaLabList("safeMoney")}>
                    {isIdeaLabListExpanded("safeMoney") ? "Show Less" : "Show More"}
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {tab === "predictor" && (
          <div className="player-predictor-page">
            <div className="card big predictor-hero-card">
              <div className="predictor-header">
                <span className="editor-kicker">Player Predictor</span>
                <h2>Player Predictor</h2>
                <p>
                  Enter the player, choose the format, and generate one focused upload prediction using synced Revenue Tracker / YouTube Analytics data.
                </p>
              </div>

              <div className="predictor-sim-grid">
                <div style={{ position: "relative" }}>
                  <input
                    value={playerSearch}
                    onChange={(e) => updatePlayerSearch(e.target.value)}
                    onFocus={() => {
                      if (playerSearch.trim()) updatePlayerSearch(playerSearch)
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") runPlayerPrediction()
                      if (e.key === "Escape") setPlayerResults([])
                    }}
                    placeholder="Player name..."
                    className="predictor-search-input"
                    autoComplete="off"
                  />

                  {playerResults.length > 0 && (
                    <div
                      className="predictor-autocomplete-list"
                      style={{
                        position: "absolute",
                        top: "calc(100% + 8px)",
                        left: 0,
                        right: 0,
                        zIndex: 50,
                        maxHeight: "280px",
                        overflowY: "auto",
                        background: "#090909",
                        border: "1px solid #303030",
                        borderRadius: "14px",
                        boxShadow: "0 18px 40px rgba(0, 0, 0, 0.55)",
                        padding: "8px"
                      }}
                    >
                      {playerResults.map((player, index) => (
                        <button
                          key={`${player.name}-${index}`}
                          type="button"
                          onClick={() => selectPlayerResult(player.name)}
                          style={{
                            width: "100%",
                            display: "block",
                            textAlign: "left",
                            padding: "12px 14px",
                            border: "0",
                            borderRadius: "10px",
                            background: "transparent",
                            color: "#fff",
                            fontWeight: 700,
                            cursor: "pointer"
                          }}
                        >
                          {player.name}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <select
                  value={playerFormat}
                  onChange={(e) => {
                    setPlayerFormat(e.target.value)
                    setPrediction(null)
                  }}
                  className="predictor-search-input"
                >
                  <option>Top 10</option>
                  <option>Solo Highlight</option>
                </select>

                <button className="predictor-run-button" onClick={runPlayerPrediction}>
                  Predict Upload
                </button>
              </div>
            </div>

            {prediction && (
              <div className="card big predictor-result-card">
                <div className="predictor-result-top">
                  <div>
                    <span className="editor-kicker">Prediction Result</span>
                    <h2>{prediction.name}</h2>
                    <p>{prediction.video_idea || `${prediction.name} ${prediction.selected_format}`}</p>
                  </div>

                  <div className="predictor-risk-pill" style={{ borderColor: riskColor(prediction.copyright_risk || 0) }}>
                    <span>Copyright Risk</span>
                    <b style={{ color: riskColor(prediction.copyright_risk || 0) }}>{prediction.copyright_risk || 0}%</b>
                  </div>
                </div>

                <div className="predictor-tag-row">
                  <span>{prediction.selected_format || playerFormat}</span>
                  <span>{prediction.era || "Unknown Era"}</span>
                  <span>{prediction.position || "Unknown Position"}</span>
                  <span>{prediction.revenue_confidence || "Synced revenue model"}</span>
                </div>

                <div className="predictor-metric-grid">
                  <div className="predictor-metric-card">
                    <span>Projected Views</span>
                    <b>{Number(prediction.projected_views || 0).toLocaleString()}</b>
                    <small>single estimate</small>
                  </div>

                  <div className="predictor-metric-card">
                    <span>Projected Revenue</span>
                    <b>{formatMoney(prediction.projected_revenue || 0)}</b>
                    <small>Revenue Tracker model</small>
                  </div>

                  <div className="predictor-metric-card">
                    <span>Expected RPM</span>
                    <b>{formatMoney(prediction.expected_rpm || 0)}</b>
                    <small>synced RPM signal</small>
                  </div>

                  <div className="predictor-metric-card">
                    <span>Subscribers</span>
                    <b>{Number(prediction.projected_subscribers || 0).toLocaleString()}</b>
                    <small>expected gain</small>
                  </div>
                </div>

                {prediction.recommendation && (
                  <div className="predictor-panel">
                    <div className="predictor-panel-heading">
                      <span>Recommendation</span>
                      <small>what CourtVision sees</small>
                    </div>

                    <p>{prediction.recommendation}</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}


        {tab === "contentStudio" && (
          <div className="content-studio editor-mode">
            <div className="editor-topbar">
              <div>
                <h2>Content Studio Editor</h2>
                <p>
                  Open a project, preview clips, trim by dragging the clip ends, save the draft, then approve before rendering or uploading.
                </p>
              </div>

              <div className="editor-topbar-actions">
                {contentStudioActiveProject && (
                  <>
                    <button className="editor-btn editor-btn-primary" onClick={saveContentStudioProjectEdits}>
                      Save Project
                    </button>

                    <button className="editor-btn" onClick={approveContentStudioProject}>
                      Approve
                    </button>

                    <button
                      className="editor-btn"
                      onClick={renderContentStudioProject}
                      disabled={contentStudioActiveProject?.render_status === "rendering"}
                    >
                      {contentStudioActiveProject?.render_status === "rendering" ? "Rendering..." : "Render"}
                    </button>

                    <button
                      className="editor-btn"
                      onClick={() => {
                        if (!contentStudioActiveProject?.rendered_video?.preview_url) {
                          alert("Render the final MP4 first. Upload will always require your permission click.")
                          return
                        }

                        alert("YouTube upload is the next step. Final rendered video is ready, but upload is still permission-only placeholder.")
                      }}
                    >
                      Upload
                    </button>
                  </>
                )}
              </div>
            </div>

            <div className="editor-status-strip">
              <div className="editor-status-pill">
                <span>Projects</span>
                <b>{contentStudioProjects.length}</b>
              </div>

              <div className="editor-status-pill">
                <span>FFmpeg</span>
                <b>{videoEditorStatus?.ffmpeg?.available ? "Ready" : "Check"}</b>
              </div>

              <div className="editor-status-pill">
                <span>Mode</span>
                <b>{contentStudioProjectType === "top10" ? "Top 10" : "Solo"}</b>
              </div>

              <div className="editor-status-pill">
                <span>Template</span>
                <b>
                  {contentStudioProjectType === "top10"
                    ? "Intro + 10 Clips + Outro + Music"
                    : "Clip + Outro"}
                </b>
              </div>
            </div>

            <div className="editor-create-card">
              <div className="editor-panel-title">
                <span>New Project</span>
                <small>Import MP4 files from your computer</small>
              </div>

              <div className="editor-create-grid">
                <label className="editor-field">
                  <span>Project Type</span>
                  <select
                    value={contentStudioProjectType}
                    onChange={(e) => {
                      setContentStudioProjectType(e.target.value)
                      setContentStudioFiles([])
                    }}
                  >
                    <option value="solo">Solo Highlight</option>
                    <option value="top10">Top 10 Video</option>
                  </select>
                </label>

                <label className="editor-field">
                  <span>Project Name</span>
                  <input
                    value={contentStudioProjectName}
                    onChange={(e) => setContentStudioProjectName(e.target.value)}
                    placeholder={
                      contentStudioProjectType === "top10"
                        ? "Example: Julius Erving Top 10 Dunks"
                        : "Example: Dr J Poster Dunk"
                    }
                  />
                </label>

                <label className="editor-field editor-field-wide">
                  <span>MP4 Clips</span>
                  <input
                    type="file"
                    accept="video/mp4"
                    multiple={contentStudioProjectType === "top10"}
                    onChange={(e) => setContentStudioFiles(Array.from(e.target.files || []))}
                  />
                  <small>
                    {contentStudioProjectType === "solo"
                      ? "Solo Highlight: choose exactly 1 clip. No intro. Outro image holds for 15 seconds."
                      : "Top 10: choose 10+ clips. Top 10 uses intro, clips, outro image, and cycling background music."}
                  </small>
                </label>

                <div className="editor-file-list">
                  <span>Selected Files</span>
                  {contentStudioFiles.length > 0 ? (
                    contentStudioFiles.slice(0, 8).map((file, i) => (
                      <small key={`${file.name}-${i}`}>
                        #{i + 1} {file.name} — {Math.round((file.size || 0) / 1024 / 1024)} MB
                      </small>
                    ))
                  ) : (
                    <small>No files selected</small>
                  )}

                  {contentStudioFiles.length > 8 && (
                    <small>+ {contentStudioFiles.length - 8} more</small>
                  )}
                </div>

                <button
                  className="editor-btn editor-btn-primary editor-field-wide"
                  onClick={uploadContentStudioProject}
                  disabled={contentStudioUploading}
                >
                  {contentStudioUploading ? "Uploading..." : "Create Project"}
                </button>
              </div>
            </div>

            {contentStudioActiveProject && (() => {
              const draft = getContentStudioDraft()
              const sortedClips = [...(contentStudioActiveProject.clips || [])].sort((a, b) => Number(a.order || 0) - Number(b.order || 0))
              const selectedClip = sortedClips.find(clip => clip.clip_id === contentStudioSelectedClipId) || sortedClips[0]
              const isTop10 = contentStudioActiveProject.project_type === "top10"
              const selectedIndex = selectedClip ? sortedClips.findIndex(clip => clip.clip_id === selectedClip.clip_id) : -1

              return (
                <div className="video-editor-shell">
                  <div className="editor-project-bar">
                    <div>
                      <span className="editor-kicker">Open Project</span>
                      <h2>{contentStudioActiveProject.project_name || "Untitled Project"}</h2>
                      <p>
                        {isTop10
                          ? "Top 10 template: Intro → #10 to #1 → 15 second outro → background music."
                          : "Solo template: Highlight clip → 15 second outro. No intro."}
                      </p>
                    </div>

                    <div className="editor-project-meta">
                      <span>{isTop10 ? "Top 10 Video" : "Solo Highlight"}</span>
                      <span>{sortedClips.length} timeline clips</span>
                      <span>Status: {contentStudioActiveProject.status || "draft"}</span>
                    </div>
                  </div>

                  {contentStudioActiveProject.rendered_video?.preview_url && (
                    <div className="editor-create-card" style={{ marginBottom: "18px" }}>
                      <div className="editor-panel-title">
                        <span>Rendered Final Video</span>
                        <small>Preview the finished MP4 before YouTube upload</small>
                      </div>

                      <video
                        src={`${API}${contentStudioActiveProject.rendered_video.preview_url}`}
                        controls
                        style={{
                          width: "100%",
                          maxHeight: "420px",
                          borderRadius: "16px",
                          border: "1px solid #303030",
                          background: "#000"
                        }}
                      />

                      <div className="quick-stat">
                        <span>Duration</span>
                        <b>{contentStudioActiveProject.rendered_video.duration_seconds || "—"} seconds</b>
                      </div>

                      <div className="quick-stat">
                        <span>Music Used</span>
                        <b>{contentStudioActiveProject.rendered_video.music_used || "None"}</b>
                      </div>
                    </div>
                  )}

                  {contentStudioActiveProject.render_status === "failed" && (
                    <div className="editor-create-card" style={{ marginBottom: "18px", borderColor: "rgba(255, 0, 0, 0.5)" }}>
                      <div className="editor-panel-title">
                        <span>Render Failed</span>
                        <small>Check the backend terminal for full FFmpeg details</small>
                      </div>
                      <p>{contentStudioActiveProject.render_error?.message || "Render failed."}</p>
                    </div>
                  )}

                  <div className="editor-workspace">
                    <aside className="editor-media-bin">
                      <div className="editor-panel-title">
                        <span>Media Bin</span>
                        <small>Source clips</small>
                      </div>

                      <div className="media-bin-list">
                        {sortedClips.map((clip, index) => (
                          <button
                            key={clip.clip_id}
                            className={clip.clip_id === selectedClip?.clip_id ? "media-bin-item selected" : "media-bin-item"}
                            onClick={() => setContentStudioSelectedClipId(clip.clip_id)}
                          >
                            <video src={`${API}${clip.preview_url}`} muted />
                            <div>
                              <b>{clip.title || `Clip ${index + 1}`}</b>
                              <small>
                                {isTop10 && index < 10 ? `Top 10 slot #${10 - index}` : isTop10 ? "Extra / solo draft" : "Solo clip"}
                              </small>
                            </div>
                          </button>
                        ))}
                      </div>

                      <div className="editor-template-box">
                        <b>Template Assets</b>
                        {isTop10 ? (
                          <>
                            <small>Intro: intro.mp4</small>
                            <small>Outro: outro.png / 15 sec</small>
                            <small>Music: cycles music folder</small>
                          </>
                        ) : (
                          <>
                            <small>Intro: off</small>
                            <small>Outro: outro.png / 15 sec</small>
                            <small>Music: off</small>
                          </>
                        )}
                      </div>
                    </aside>

                    <section className="editor-preview-monitor">
                      <div className="editor-panel-title">
                        <span>Preview Monitor</span>
                        <small>{selectedClip ? selectedClip.title : "No clip selected"}</small>
                      </div>

                      <div className="preview-screen">
                        {contentStudioActiveProject.rendered_video?.preview_url ? (
                          <video
                            ref={contentStudioPreviewRef}
                            src={`${API}${contentStudioActiveProject.rendered_video.preview_url}`}
                            controls
                            key={`rendered-${contentStudioActiveProject.rendered_video.filename || contentStudioActiveProject.updated_at || contentStudioActiveProject.project_id}`}
                            onTimeUpdate={(event) => {
                              const total = getContentStudioTimelineTotalSeconds()
                              const current = Number(event.currentTarget.currentTime || 0)
                              setContentStudioPlayheadSeconds(Number(Math.min(current, total).toFixed(2)))
                            }}
                          />
                        ) : selectedClip ? (
                          <video
                            ref={contentStudioPreviewRef}
                            src={`${API}${selectedClip.preview_url}`}
                            controls
                            key={selectedClip.clip_id}
                            onLoadedMetadata={(event) => {
                              const duration = Number(event.currentTarget.duration || 0)

                              if (duration > 0 && Number(selectedClip.duration_seconds || 0) !== Number(duration.toFixed(2))) {
                                updateContentStudioClip(selectedClip.clip_id, {
                                  duration_seconds: Number(duration.toFixed(2))
                                })
                              }

                              event.currentTarget.currentTime = Number(selectedClip.trim_start || 0)
                            }}
                            onTimeUpdate={(event) => handleContentStudioPreviewTimeUpdate(event, selectedClip)}
                          />
                        ) : (
                          <div className="preview-empty">Select a clip from the timeline</div>
                        )}
                      </div>

                  <div className="timeline-editor preview-timeline-editor">
                    <div className="timeline-header">
                      <div>
                        <span className="editor-kicker">Timeline</span>
                        <h3>{isTop10 ? "Top 10 Edit Timeline" : "Solo Highlight Timeline"}</h3>
                      </div>

                      <div className="timeline-help">
                        Click/drag to scrub • Drag either clip edge to trim
                      </div>
                    </div>

                    {isTop10 && (
                      <div className="timeline-row">
                        <div className="track-label">Intro</div>
                        <div className="track-lane">
                          <div className="timeline-asset intro">intro.mp4</div>
                        </div>
                      </div>
                    )}

                    <div className="timeline-row">
                      <div className="track-label">Video</div>
                      <div
                        className="track-lane video-track"
                        onMouseDown={handleContentStudioTimelineClick}
                      >
                        <div
                          className="timeline-playhead"
                          style={{
                            left: `${Math.min(100, Math.max(0, (contentStudioPlayheadSeconds / Math.max(1, getContentStudioTimelineTotalSeconds())) * 100))}%`
                          }}
                        />
                        {sortedClips.map((clip, index) => {
                          const active = clip.clip_id === selectedClip?.clip_id
                          const top10Slot = isTop10 && index < 10 ? `#${10 - index}` : null

                          return (
                            <div
                              key={clip.clip_id}
                              draggable
                              onDragStart={() => setContentStudioDragClipId(clip.clip_id)}
                              onDragOver={(e) => e.preventDefault()}
                              onDrop={() => reorderContentStudioClips(contentStudioDragClipId, clip.clip_id)}
                              onClick={(event) => {
                                event.stopPropagation()
                                setContentStudioSelectedClipId(clip.clip_id)
                                seekContentStudioTimeline(getContentStudioClipTimelineStart(clip.clip_id))
                              }}
                              className={active ? "timeline-clip selected" : "timeline-clip"}
                              style={{
                                flexBasis: `${Math.max(210, Math.min(520, getContentStudioEffectiveClipDuration(clip) * 5))}px`
                              }}
                            >
                              <div
                                className="trim-handle left"
                                title="Drag to trim the start"
                                onMouseDown={(event) => startContentStudioTrimDrag(event, clip, "left")}
                              />
                              <div className="clip-thumb">
                                <video src={`${API}${clip.preview_url}`} muted />
                              </div>

                              <div className="clip-text">
                                <b>{top10Slot ? `${top10Slot} ` : ""}{clip.title}</b>
                                <small>
                                  {formatVideoTime(clip.trim_start || 0)} → {formatVideoTime(Number(clip.trim_end || 0) > Number(clip.trim_start || 0) ? clip.trim_end : getContentStudioClipDuration(clip))}
                                </small>
                              </div>

                              <div
                                className="trim-handle right"
                                title="Drag to trim the end"
                                onMouseDown={(event) => startContentStudioTrimDrag(event, clip, "right")}
                              />
                            </div>
                          )
                        })}
                      </div>
                    </div>

                    {isTop10 && (
                      <>
                        <div className="timeline-row">
                          <div className="track-label">Numbers</div>
                          <div className="track-lane overlay-track">
                            {sortedClips.slice(0, 10).map((clip, index) => (
                              <div className="timeline-overlay" key={`overlay-${clip.clip_id}`}>
                                #{10 - index}
                              </div>
                            ))}
                          </div>
                        </div>

                        <div className="timeline-row">
                          <div className="track-label">Music</div>
                          <div className="track-lane">
                            <div className="timeline-music">music folder cycles through 5 mp3 files</div>
                          </div>
                        </div>
                      </>
                    )}

                  </div>

                      {contentStudioActiveProject.rendered_video?.preview_url && (
                        <div className="rendered-preview-note">
                          Showing final rendered MP4 with the outro attached. Change trims, save, and render again to update this preview.
                        </div>
                      )}

                    <div className="editor-properties editor-properties-under-preview">
                      <div className="editor-panel-title">
                        <span>Properties</span>
                        <small>Selected clip + YouTube draft</small>
                      </div>

                      {selectedClip ? (
                        <>
                          <label className="editor-field">
                            <span>Clip Name</span>
                            <input
                              value={selectedClip.title || ""}
                              onChange={(e) => updateContentStudioClip(selectedClip.clip_id, { title: e.target.value })}
                            />
                          </label>

                          <div className="editor-two-col">
                            <label className="editor-field">
                              <span>Trim Start</span>
                              <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={selectedClip.trim_start || 0}
                                onChange={(e) => updateContentStudioClip(selectedClip.clip_id, { trim_start: e.target.value })}
                              />
                            </label>

                            <label className="editor-field">
                              <span>Trim End</span>
                              <input
                                type="number"
                                min="0"
                                step="0.1"
                                value={selectedClip.trim_end || ""}
                                onChange={(e) => updateContentStudioClip(selectedClip.clip_id, { trim_end: e.target.value })}
                                placeholder="End"
                              />
                            </label>
                          </div>

                          {isTop10 && (
                            <label className="editor-field">
                              <span>Top 10 Usage</span>
                              <select
                                value={selectedClip.selected_for_top10 ? "yes" : "no"}
                                onChange={(e) => updateContentStudioClip(selectedClip.clip_id, { selected_for_top10: e.target.value === "yes" })}
                              >
                                <option value="yes">Included</option>
                                <option value="no">Extra only</option>
                              </select>
                            </label>
                          )}

                          <div className="editor-property-note">
                            <b>Timeline Position</b>
                            <span>{selectedIndex >= 0 ? selectedIndex + 1 : "—"} of {sortedClips.length}</span>
                          </div>
                        </>
                      ) : (
                        <p>No clip selected.</p>
                      )}

                      <div className="editor-divider" />

                      <label className="editor-field">
                        <span>Project Name</span>
                        <input
                          value={contentStudioActiveProject.project_name || ""}
                          onChange={(e) => updateContentStudioProjectField("project_name", e.target.value)}
                        />
                      </label>

                      <label className="editor-field">
                        <span>YouTube Title</span>
                        <input
                          value={draft?.title || ""}
                          onChange={(e) => updateContentStudioDraftField("title", e.target.value)}
                        />
                      </label>

                      <label className="editor-field">
                        <span>Description</span>
                        <textarea
                          value={draft?.description || ""}
                          onChange={(e) => updateContentStudioDraftField("description", e.target.value)}
                          rows="5"
                        />
                      </label>

                      <label className="editor-field">
                        <span>Tags</span>
                        <textarea
                          value={draft?.tags || ""}
                          onChange={(e) => updateContentStudioDraftField("tags", e.target.value)}
                          rows="3"
                        />
                      </label>

                      <label className="editor-field">
                        <span>Thumbnail Plan</span>
                        <textarea
                          value={draft?.thumbnail_plan || ""}
                          onChange={(e) => updateContentStudioDraftField("thumbnail_plan", e.target.value)}
                          rows="3"
                        />
                      </label>
                    </div>
                    </section>


                  </div>


                </div>
              )
            })()}

            <div className="saved-projects-panel">
              <div className="editor-panel-title">
                <span>Saved Projects</span>
                <small>Open a project to edit it</small>
              </div>

              {contentStudioProjects.length > 0 ? (
                <div className="saved-projects-grid">
                  {contentStudioProjects.map((project, i) => (
                    <div className="saved-project-card" key={project.project_id || i}>
                      <div>
                        <b>{project.project_name}</b>
                        <small>{project.project_type === "top10" ? "Top 10 Video" : "Solo Highlight"}</small>
                        <small>{project.clip_count} clips • {project.status}</small>
                        <small>Created: {formatDateTime(project.created_at)}</small>
                      </div>

                      {project.clips?.[0]?.preview_url ? (
                        <video src={`${API}${project.clips[0].preview_url}`} muted />
                      ) : (
                        <div className="preview-empty">No Preview</div>
                      )}

                      <div className="saved-project-actions">
                        <button className="editor-btn editor-btn-primary" onClick={() => openContentStudioProject(project.project_id)}>
                          Open Editor
                        </button>

                        <button className="editor-btn danger" onClick={() => deleteContentStudioProject(project.project_id)}>
                          Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <p>No Content Studio projects yet.</p>
              )}
            </div>
          </div>
        )}


        {tab === "thumbnail" && (
          <div className="card big">
            <h2>Thumbnail Analyzer</h2>

            <p className="tool-intro">
              Upload a thumbnail to score brightness, contrast, color separation,
              aspect ratio, and estimated CTR potential.
            </p>

            <input
              type="file"
              accept="image/*"
              onChange={(e) => analyzeThumbnail(e.target.files[0])}
              className="search-box"
            />

            {thumbnailPreview && (
              <img
                src={thumbnailPreview}
                alt="Thumbnail preview"
                style={{
                  width: "100%",
                  maxWidth: "640px",
                  borderRadius: "18px",
                  marginTop: "20px",
                  border: "1px solid #333"
                }}
              />
            )}

            {thumbnailAnalysis && (
              <div className="prediction-card">
                <h2>
                  CTR Score:
                  <span style={{ color: scoreColor(thumbnailAnalysis.ctr_score) }}>
                    {" "}{thumbnailAnalysis.ctr_score}/100
                  </span>
                </h2>

                <div className="quick-stat">
                  <span>Size</span>
                  <b>{thumbnailAnalysis.width} x {thumbnailAnalysis.height}</b>
                </div>

                <div className="quick-stat">
                  <span>Aspect Ratio</span>
                  <b>{thumbnailAnalysis.aspect_ratio}</b>
                </div>

                <div className="quick-stat">
                  <span>Brightness</span>
                  <b>{thumbnailAnalysis.brightness}</b>
                </div>

                <div className="quick-stat">
                  <span>Contrast</span>
                  <b>{thumbnailAnalysis.contrast}</b>
                </div>

                <div className="quick-stat">
                  <span>Color Separation</span>
                  <b>{thumbnailAnalysis.color_separation}</b>
                </div>

                <div className="quick-stat">
                  <span>Verdict</span>
                  <b>{thumbnailAnalysis.verdict}</b>
                </div>

                <h3>Recommendations</h3>

                {thumbnailAnalysis.recommendations?.map((r, i) => (
                  <p key={i}>• {r}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default App