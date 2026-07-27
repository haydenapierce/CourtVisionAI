const STORAGE_KEY = "courtvision_startup_diagnostics"
const MAX_RUNS = 12

export function saveStartupDiagnostics(items, totalMs) {
  try {
    const previous = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "[]")
    const run = {
      completed_at: new Date().toISOString(),
      total_ms: Math.max(0, Number(totalMs || 0)),
      tasks: (items || []).map(item => ({
        key: item.key,
        label: item.label,
        status: item.status,
        duration_ms: item.started_at && item.completed_at
          ? Math.max(0, Number(item.completed_at) - Number(item.started_at))
          : null
      }))
    }
    const next = [run, ...(Array.isArray(previous) ? previous : [])].slice(0, MAX_RUNS)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  } catch {}
}

export function clearStartupDiagnostics() {
  try {
    window.localStorage.removeItem(STORAGE_KEY)
  } catch {}
}
