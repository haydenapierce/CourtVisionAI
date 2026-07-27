import { forwardRef } from "react"

const PreviewMonitor = forwardRef(function PreviewMonitor({ src, muted, onTimeUpdate, onEnded }, ref) {
  return (
    <div className="editor-monitor-screen">
      {src ? (
        <video
          ref={ref}
          src={src}
          muted={muted}
          playsInline
          preload="metadata"
          onTimeUpdate={onTimeUpdate}
          onEnded={onEnded}
        />
      ) : (
        <div className="content-studio-empty">Select a clip to preview it.</div>
      )}
    </div>
  )
})

export default PreviewMonitor
