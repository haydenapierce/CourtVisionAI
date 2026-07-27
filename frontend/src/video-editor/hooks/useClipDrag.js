import { useState } from "react"

export default function useClipDrag(onReorder) {
  const [draggedClipId, setDraggedClipId] = useState(null)

  function drop(targetClipId) {
    if (draggedClipId && targetClipId && draggedClipId !== targetClipId) {
      onReorder?.(draggedClipId, targetClipId)
    }
    setDraggedClipId(null)
  }

  return {
    draggedClipId,
    start: setDraggedClipId,
    drop,
    end: () => setDraggedClipId(null)
  }
}
