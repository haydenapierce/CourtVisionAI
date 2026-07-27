export default function TimelineTrack({ label, trackId, compact = false, children }) {
  return (
    <div className={`nle-track-row ${compact ? "compact" : ""}`}>
      <div className="nle-track-controls">
        <b>{label}</b>
        <small>{trackId}</small>
      </div>
      <div className="nle-track-lane">{children}</div>
    </div>
  )
}
