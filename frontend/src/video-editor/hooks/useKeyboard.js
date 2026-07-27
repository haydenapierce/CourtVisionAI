import { useEffect } from "react"

export default function useKeyboard({
  onPlayPause, onUndo, onRedo, onDelete, onPreviousFrame, onNextFrame, enabled = true
}) {
  useEffect(() => {
    if (!enabled) return

    function onKeyDown(event) {
      if (event.target?.matches?.("input, textarea, select, [contenteditable='true']")) return

      if (event.code === "Space") {
        event.preventDefault()
        onPlayPause?.()
      } else if (event.key === "Delete") {
        onDelete?.()
      } else if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === "z") {
        event.preventDefault()
        onRedo?.()
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault()
        onUndo?.()
      } else if (event.key === "ArrowLeft") {
        onPreviousFrame?.()
      } else if (event.key === "ArrowRight") {
        onNextFrame?.()
      }
    }

    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [enabled, onPlayPause, onUndo, onRedo, onDelete, onPreviousFrame, onNextFrame])
}
