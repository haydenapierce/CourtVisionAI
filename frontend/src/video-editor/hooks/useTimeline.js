import { useMemo, useState } from "react"

export default function useTimeline(initialZoom = 12) {
  const [zoom, setZoom] = useState(initialZoom)
  const [playheadSeconds, setPlayheadSeconds] = useState(0)
  const pixelsPerSecond = useMemo(
    () => Math.max(4, Math.min(32, Number(zoom || 12))),
    [zoom]
  )
  return { zoom: pixelsPerSecond, setZoom, playheadSeconds, setPlayheadSeconds }
}
