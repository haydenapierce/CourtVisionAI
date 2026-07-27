const STORAGE_PREFIX = "courtvision_boot_task_ms_"

export const STARTUP_WORKER_COUNT = 4

const clamp = (value, min, max) => Math.min(max, Math.max(min, Number(value || 0)))

export function getStoredTaskEstimateMs(key, fallbackMs) {
  const fallback = Math.max(250, Number(fallbackMs || 4000))
  try {
    const saved = Number(window.localStorage.getItem(`${STORAGE_PREFIX}${key}`) || 0)
    if (Number.isFinite(saved) && saved >= 250) {
      // A single stalled launch must not poison ETA for every future launch.
      // Keep learned timings useful, but bound them to a realistic range for
      // this specific task.
      return clamp(saved, Math.max(250, fallback * 0.45), fallback * 3)
    }
  } catch {}
  return fallback
}

export function saveTaskEstimateMs(key, actualMs, fallbackMs) {
  try {
    const fallback = Math.max(250, Number(fallbackMs || 4000))
    const safeActual = clamp(actualMs, Math.max(250, fallback * 0.35), fallback * 3)
    const previous = getStoredTaskEstimateMs(key, fallback)
    const next = Math.round((previous * 0.65) + (safeActual * 0.35))
    window.localStorage.setItem(`${STORAGE_PREFIX}${key}`, String(next))
  } catch {}
}

function task(key, label, fallbackMs, lane = "tabs") {
  return {
    key,
    label,
    lane,
    status: "waiting",
    default_ms: fallbackMs,
    expected_ms: getStoredTaskEstimateMs(key, fallbackMs),
    running_progress: 0,
    active_label: "",
    started_at: null,
    completed_at: null
  }
}

export function createStartupTasks() {
  return [
    task("backendReady", "Backend and database ready", 900, "sequential"),
    task("cachedData", "Load saved channel totals", 900, "sequential"),
    task("dashboardSync", "Refresh YouTube videos and channel statistics", 20000, "sequential"),
    task("revenueSync", "Refresh YouTube Analytics revenue, views, and RPM", 26000, "sequential"),

    task("statsData", "Load dashboard totals", 900),
    task("savedVideosData", "Load Channel Library videos", 1600),
    task("rankingsData", "Load Channel Library player data", 1800),
    task("playersData", "Load Idea Lab", 4200),
    task("revenueSummaryData", "Load Revenue Center performance", 1400),
    task("youtubeRevenueStatusData", "Load Analytics sync status", 800),
    task("channelRevenueData", "Load channel revenue periods", 1000),
    task("videoRevenueData", "Load video revenue periods", 2200),
    task("revenueForecastData", "Load Revenue Center forecast", 4200),
    task("channelBrainData", "Load Decision Engine recommendation", 5000),
    task("strategyResponseData", "Verify Decision Engine data", 5000),
    task("deadRecoveryResponseData", "Load Dead Video Recovery", 5200),
    task("endScreenData", "Load End Screen Optimizer", 4200),
    task("studioTypesData", "Load Studio categories", 700),
    task("studioSummaryData", "Load Studio summary", 1100),
    task("studioBreakdownsData", "Load Studio Breakdowns", 2600),
    task("studioIntelligenceData", "Load Studio Intelligence", 4200),
    task("contentStudioStatusData", "Load CourtVision Editor status", 800),
    task("videoEditorStatusData", "Load Video Editor status", 800),
    task("contentStudioProjectsData", "Load CourtVision Editor projects", 1600),
    task("thumbnailBuilderProjectsData", "Load Thumbnail Builder projects", 1600),
    task("thumbnailBuilderSettingsData", "Load Thumbnail Builder settings", 900),
    task("communityData", "Load Community Automation", 2200),
    task("clipFinderConfigData", "Verify Clip Finder configuration", 900),
    task("clipFinderProjectsData", "Load Clip Finder project summaries", 1200),
    task("featureReadinessData", "Verify editor, render, upload, and project services", 900),

    task("finalVerification", "Verify every required tab is ready", 650, "sequential")
  ]
}

export function isFinishedTask(item) {
  return ["done", "warning"].includes(item?.status)
}

function runningFraction(item, now) {
  if (!item) return 0
  if (isFinishedTask(item)) return 1
  if (item.status !== "running") return 0

  const reported = clamp(item.running_progress, 0, 95) / 100
  const expected = Math.max(500, Number(item.expected_ms || 4000))
  const elapsed = Math.max(0, now - Number(item.started_at || now))

  // HTTP requests do not expose byte-level progress. Elapsed-time interpolation
  // keeps the visual bar moving but is capped so completion is never claimed
  // before the request and payload verification actually finish.
  const elapsedEstimate = Math.min(0.88, (elapsed / expected) * 0.72)
  return Math.min(0.95, Math.max(reported, elapsedEstimate))
}

function estimateParallelRemainingMs(items, workerCount, now) {
  const durations = items
    .filter(item => item.lane === "tabs" && !isFinishedTask(item) && item.status !== "error")
    .map(item => {
      const expected = Math.max(500, Number(item.expected_ms || 4000))
      return expected * (1 - runningFraction(item, now))
    })
    .sort((a, b) => b - a)

  if (!durations.length) return 0

  const lanes = Array.from({ length: Math.max(1, workerCount) }, () => 0)
  durations.forEach(duration => {
    let target = 0
    for (let index = 1; index < lanes.length; index += 1) {
      if (lanes[index] < lanes[target]) target = index
    }
    lanes[target] += duration
  })

  return Math.max(...lanes)
}

function progressWeight(item) {
  const expected = Math.max(250, Number(item?.expected_ms || item?.default_ms || 4000))
  // Duration still matters, but logarithmic weighting prevents one long API
  // request from owning half of the progress bar. This keeps the percentage
  // aligned with Loaded X / Total while preserving extra weight for real work.
  return clamp(1 + (Math.log2(expected / 500) * 0.42), 0.8, 3.4)
}

export function computeStartupSnapshot(items, { syncComplete = false, workerCount = STARTUP_WORKER_COUNT } = {}) {
  const now = Date.now()
  const safeItems = Array.isArray(items) ? items : []
  const totalWeight = safeItems.reduce(
    (sum, item) => sum + progressWeight(item),
    0
  ) || 1

  const completedWeight = safeItems.reduce((sum, item) => {
    return sum + (progressWeight(item) * runningFraction(item, now))
  }, 0)

  const weightedPercent = (completedWeight / totalWeight) * 100
  const rawPercent = syncComplete ? 100 : clamp(weightedPercent, 0.5, 99.4)
  const completedCount = safeItems.filter(isFinishedTask).length
  const waitingCount = safeItems.filter(item => item.status === "waiting").length
  const runningCount = safeItems.filter(item => item.status === "running").length
  const warningCount = safeItems.filter(item => item.status === "warning").length
  const errorCount = safeItems.filter(item => item.status === "error").length
  const runningItems = safeItems.filter(item => item.status === "running")
  const firstWaiting = safeItems.find(item => item.status === "waiting")
  const activeItem = runningItems[0] || firstWaiting || null

  const sequentialRemaining = safeItems
    .filter(item => item.lane === "sequential" && !isFinishedTask(item) && item.status !== "error")
    .reduce((sum, item) => {
      const expected = Math.max(500, Number(item.expected_ms || 4000))
      return sum + (expected * (1 - runningFraction(item, now)))
    }, 0)

  const parallelRemaining = estimateParallelRemainingMs(safeItems, workerCount, now)
  const remainingMs = syncComplete ? 0 : sequentialRemaining + parallelRemaining

  return {
    rawPercent,
    completedCount,
    totalCount: safeItems.length,
    activeItem,
    waitingCount,
    runningCount,
    warningCount,
    errorCount,
    remainingSeconds: syncComplete ? 0 : Math.max(1, Math.ceil(remainingMs / 1000))
  }
}

export async function runTrackedTaskPool(specs, options) {
  const {
    fetchJson,
    updateTask,
    concurrency = STARTUP_WORKER_COUNT
  } = options

  const trackedFetch = async spec => {
    const {
      key,
      label,
      path,
      fallback,
      timeoutMs = 45000,
      maxAttempts = 1,
      validate
    } = spec

    updateTask(key, "running", { label, progress: 0 })
    let lastError = null

    for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
      try {
        if (attempt > 1) {
          updateTask(key, "running", {
            label: `${label.replace(/\.\.\.$/, "")} (retry ${attempt}/${maxAttempts})...`,
            progress: 0
          })
        }

        const value = await fetchJson(path, { timeoutMs })
        if (value === undefined || value === null) {
          throw new Error(`No data returned from ${path}`)
        }
        if (typeof validate === "function") {
          const validationMessage = validate(value)
          if (validationMessage) {
            throw new Error(`${path} returned invalid startup data: ${validationMessage}`)
          }
        }

        updateTask(key, "done")
        return { key, value, status: "done" }
      } catch (error) {
        lastError = error
        console.error(`Startup request failed (${attempt}/${maxAttempts}): ${path}`, error)
        if (attempt < maxAttempts) {
          await new Promise(resolve => setTimeout(resolve, 400 * attempt))
        }
      }
    }

    if (fallback !== undefined) {
      updateTask(key, "warning", {
        label: `${label.replace(/\.\.\.$/, "")} (loaded fallback)`
      })
      return { key, value: fallback, status: "warning" }
    }

    const exactMessage = String(lastError?.message || `Startup request failed: ${path}`)
    updateTask(key, "error", {
      label: `${label.replace(/\.\.\.$/, "")} — ${exactMessage}`
    })

    return {
      key,
      error: lastError || new Error(`Startup request failed: ${path}`),
      status: "error"
    }
  }

  const results = new Array(specs.length)
  let nextIndex = 0

  const worker = async () => {
    while (true) {
      const index = nextIndex
      nextIndex += 1
      if (index >= specs.length) return
      results[index] = await trackedFetch(specs[index])
    }
  }

  await Promise.all(Array.from(
    { length: Math.min(Math.max(1, concurrency), specs.length) },
    () => worker()
  ))

  const failed = results.find(result => result?.status === "error")
  if (failed) throw failed.error

  return results.reduce((payload, result) => {
    if (result) payload[result.key] = result.value
    return payload
  }, {})
}
