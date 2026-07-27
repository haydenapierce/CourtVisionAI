export function clamp(value, minimum, maximum) {
  const number = Number(value || 0)
  return Math.min(maximum, Math.max(minimum, number))
}

export function buildRulerTicks(totalSeconds, pixelsPerSecond) {
  const safeTotal = Math.max(1, Number(totalSeconds || 0) + 15)
  const safeZoom = Math.max(4, Number(pixelsPerSecond || 12))

  let interval = 1
  if (safeZoom < 7) interval = 10
  else if (safeZoom < 11) interval = 5
  else if (safeZoom < 18) interval = 2

  const ticks = []
  for (let second = 0; second <= Math.ceil(safeTotal); second += interval) {
    ticks.push({
      second,
      left: second * safeZoom,
      major: second % (interval * 5) === 0
    })
  }

  return ticks
}

export function formatTimelineTime(seconds) {
  const safeSeconds = Math.max(0, Number(seconds || 0))
  const minutes = Math.floor(safeSeconds / 60)
  const remainder = Math.floor(safeSeconds % 60)
  return `${minutes}:${String(remainder).padStart(2, "0")}`
}


export function formatReadableDuration(seconds) {
  const safeSeconds = Math.max(0, Math.round(Number(seconds || 0)))
  const hours = Math.floor(safeSeconds / 3600)
  const minutes = Math.floor((safeSeconds % 3600) / 60)
  const remainder = safeSeconds % 60
  const parts = []
  if (hours) parts.push(`${hours} hour${hours === 1 ? "" : "s"}`)
  if (minutes) parts.push(`${minutes} minute${minutes === 1 ? "" : "s"}`)
  if (remainder || parts.length === 0) parts.push(`${remainder} second${remainder === 1 ? "" : "s"}`)
  return parts.join(" ")
}
