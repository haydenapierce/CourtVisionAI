import { useCallback, useRef, useState } from "react"

export default function usePlayback() {
  const videoRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)

  const playPause = useCallback(async () => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      await video.play()
      setPlaying(true)
    } else {
      video.pause()
      setPlaying(false)
    }
  }, [])

  const stop = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    video.pause()
    video.currentTime = 0
    setPlaying(false)
  }, [])

  const seek = useCallback((seconds) => {
    if (videoRef.current) videoRef.current.currentTime = Math.max(0, Number(seconds || 0))
  }, [])

  const stepFrame = useCallback((direction) => {
    const video = videoRef.current
    if (!video) return
    video.pause()
    setPlaying(false)
    video.currentTime = Math.max(0, video.currentTime + direction / 30)
  }, [])

  return { videoRef, playing, muted, setMuted, playPause, stop, seek, stepFrame }
}
