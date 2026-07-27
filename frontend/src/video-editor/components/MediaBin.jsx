import { formatReadableDuration } from "../utils/timelineMath.js"
export default function MediaBin({ clips = [], selectedClipId, apiBase, onSelect }) {
  return (
    <aside className="editor-media-bin">
      <div className="editor-panel-title">
        <span>Media</span>
        <small>{clips.length} clips</small>
      </div>
      <div className="media-bin-list">
        {clips.map((clip, index) => (
          <button
            type="button"
            key={clip.clip_id}
            className={`media-bin-item ${clip.clip_id === selectedClipId ? "selected" : ""}`}
            onClick={() => onSelect?.(clip)}
          >
            <video src={`${apiBase}${clip.preview_url}`} muted preload="metadata" />
            <span>
              <b>{clip.title || `Clip ${index + 1}`}</b>
              <small>{formatReadableDuration(clip.duration_seconds || 0)}</small>
            </span>
          </button>
        ))}
      </div>
    </aside>
  )
}
