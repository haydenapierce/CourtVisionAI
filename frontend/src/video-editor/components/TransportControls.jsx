export default function TransportControls({
  playing, muted, onPlayPause, onStop, onPreviousFrame, onNextFrame, onMute, onFullscreen
}) {
  return (
    <div className="transport-bar">
      <button type="button" onClick={onPreviousFrame} title="Previous frame">◀|</button>
      <button type="button" onClick={onPlayPause} title={playing ? "Pause" : "Play"}>
        {playing ? "❚❚" : "▶"}
      </button>
      <button type="button" onClick={onStop} title="Stop">■</button>
      <button type="button" onClick={onNextFrame} title="Next frame">|▶</button>
      <button type="button" onClick={onMute} title={muted ? "Unmute" : "Mute"}>
        {muted ? "🔇" : "🔊"}
      </button>
      <button type="button" onClick={onFullscreen} title="Fullscreen">⛶</button>
    </div>
  )
}
