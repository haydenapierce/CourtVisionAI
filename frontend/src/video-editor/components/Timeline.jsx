import { useEffect, useMemo, useRef, useState } from "react"
import "../VideoEditor.css"
import { buildRulerTicks, clamp, formatReadableDuration, formatTimelineTime } from "../utils/timelineMath.js"

const OUTRO_SECONDS = 15

function TimelineFrame({ src, time }) {
  const videoRef = useRef(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video || video.readyState < 1) return
    const duration = Number(video.duration || 0)
    const target = Math.max(0, Math.min(duration > 0 ? Math.max(0, duration - 0.02) : Number(time || 0), Number(time || 0)))
    try { video.currentTime = target } catch (_) {}
  }, [time])

  return (
    <video
      ref={videoRef}
      src={src}
      muted
      playsInline
      preload="metadata"
      draggable={false}
      onLoadedMetadata={(event) => {
        const duration = Number(event.currentTarget.duration || 0)
        const target = Math.max(0, Math.min(duration > 0 ? Math.max(0, duration - 0.02) : Number(time || 0), Number(time || 0)))
        try { event.currentTarget.currentTime = target } catch (_) {}
      }}
      aria-hidden="true"
    />
  )
}

export default function Timeline({
  apiBase,
  clips,
  selectedClipId,
  draggedClipId,
  isTop10,
  playheadSeconds,
  playheadRef,
  zoom,
  canUndo,
  canRedo,
  totalSeconds,
  getClipWidth,
  getClipDuration,
  getClipSourceDuration,
  getClipTimelineStart,
  formatTime,
  onZoomChange,
  onUndo,
  onRedo,
  onResetTrim,
  onSelectClip,
  onSeekPointerDown,
  onSeekPointerMove,
  onSeekPointerUp,
  onSeekClick,
  onTrimStart,
  onDragStart,
  onDragEnd,
  onReorder,
  onSplit,
  onRemove,
  onToggleMute,
  onToggleSideFill,
  onResetSpeed
}) {
  const laneRef = useRef(null)
  const [controlHeld, setControlHeld] = useState(false)
  const [clipMenu, setClipMenu] = useState(null)

  useEffect(() => {
    const down = (event) => { if (event.key === "Control" || event.metaKey) setControlHeld(true) }
    const up = (event) => { if (event.key === "Control") setControlHeld(false) }
    const blur = () => setControlHeld(false)
    window.addEventListener("keydown", down)
    window.addEventListener("keyup", up)
    window.addEventListener("blur", blur)
    return () => {
      window.removeEventListener("keydown", down)
      window.removeEventListener("keyup", up)
      window.removeEventListener("blur", blur)
    }
  }, [])

  useEffect(() => {
    if (!clipMenu) return undefined
    const close = () => setClipMenu(null)
    const escape = (event) => { if (event.key === "Escape") close() }
    window.addEventListener("pointerdown", close)
    window.addEventListener("keydown", escape)
    return () => {
      window.removeEventListener("pointerdown", close)
      window.removeEventListener("keydown", escape)
    }
  }, [clipMenu])
  const safeClips = Array.isArray(clips) ? clips : []
  const safeZoom = clamp(zoom, 4, 32)
  const projectSeconds = Math.max(0.25, Number(totalSeconds || 0))
  const canvasWidth = Math.max(1100, (projectSeconds + OUTRO_SECONDS) * safeZoom + 120)

  const rulerTicks = useMemo(
    () => buildRulerTicks(projectSeconds, safeZoom),
    [projectSeconds, safeZoom]
  )

  function handleDrop(event, targetClipId) {
    event.preventDefault()
    event.stopPropagation()
    if (draggedClipId && targetClipId && draggedClipId !== targetClipId) {
      onReorder?.(draggedClipId, targetClipId)
    }
  }

  function stopPointer(event) {
    event.stopPropagation()
  }

  function seekPointerDown(event) {
    onSeekPointerDown?.(event, laneRef.current)
  }

  function seekPointerMove(event) {
    onSeekPointerMove?.(event, laneRef.current)
  }

  function seekPointerUp(event) {
    onSeekPointerUp?.(event, laneRef.current)
  }

  function seekClick(event) {
    onSeekClick?.(event, laneRef.current)
  }

  function handleTimelineWheel(event) {
    const frame = event.currentTarget.querySelector(".nle-scroll-frame")
    const horizontalIntent = Math.abs(event.deltaX) > Math.abs(event.deltaY)

    event.preventDefault()
    event.stopPropagation()

    if (horizontalIntent) {
      if (frame) frame.scrollLeft += event.deltaX
      return
    }

    const direction = event.deltaY < 0 ? 1 : -1
    onZoomChange?.(clamp(safeZoom + direction, 4, 32))
  }

  return (
    <section className="nle-timeline">
      <header className="nle-timeline-header">
        <div className="nle-title-group">
          <span className="nle-eyebrow">{isTop10 ? "TOP 10 TIMELINE" : "SOLO TIMELINE"}</span>
          <h3>{safeClips.length} clip{safeClips.length === 1 ? "" : "s"} • {formatReadableDuration(projectSeconds)}</h3>
        </div>

        <div className="nle-toolbar">
          <div className="nle-tool-group">
            <button type="button" onClick={onUndo} disabled={!canUndo} title="Undo trim (Ctrl+Z)">↶</button>
            <button type="button" onClick={onRedo} disabled={!canRedo} title="Redo trim (Ctrl+Shift+Z)">↷</button>
            <button type="button" onClick={onResetTrim} disabled={!selectedClipId} title="Reset selected trim">⟲</button>
          </div>

          <label className="nle-zoom">
            <span>−</span>
            <input
              type="range"
              min="4"
              max="32"
              step="1"
              value={safeZoom}
              onChange={(event) => onZoomChange?.(Number(event.target.value || 12))}
              aria-label="Timeline zoom"
            />
            <span>＋</span>
          </label>

          <div className="nle-time-readout" title="Current timeline position">
            {formatTimelineTime(playheadSeconds)}
          </div>
        </div>
      </header>

      <div className="nle-scroll-frame" onWheel={handleTimelineWheel}>
        <div className="nle-canvas" style={{ width: `${canvasWidth}px` }}>
          <div
            className="nle-ruler"
            onPointerDown={seekPointerDown}
            onPointerMove={seekPointerMove}
            onPointerUp={seekPointerUp}
            onPointerCancel={seekPointerUp}
            onClick={seekClick}
          >
            {rulerTicks.map((tick) => (
              <div
                key={tick.second}
                className={tick.major ? "nle-ruler-tick major" : "nle-ruler-tick"}
                style={{ left: `${tick.left}px` }}
              >
                <i />
                {tick.major && <span>{formatTimelineTime(tick.second)}</span>}
              </div>
            ))}
          </div>

          {isTop10 && (
            <div className="nle-track-row compact">
              <div className="nle-track-controls">
                <b>INTRO</b>
                <small>V3</small>
              </div>
              <div className="nle-track-lane">
                <div className="nle-static-asset intro">intro.mp4 (optional)</div>
              </div>
            </div>
          )}

          <div className="nle-track-row video">
            <div className="nle-track-controls">
              <b>VIDEO</b>
              <small>V1</small>
              <div className="nle-track-icons">
                <span title="Track visible">◉</span>
                <span title="Track unlocked">◇</span>
              </div>
            </div>

            <div
              ref={laneRef}
              className="nle-track-lane nle-video-lane"
              onPointerDown={seekPointerDown}
              onPointerMove={seekPointerMove}
              onPointerUp={seekPointerUp}
              onPointerCancel={seekPointerUp}
              onClick={seekClick}
            >
              <div
                ref={playheadRef}
                className="nle-playhead"
                style={{
                  left: `${Math.max(0, Math.min(projectSeconds * safeZoom, Number(playheadSeconds || 0) * safeZoom))}px`
                }}
              >
                <span />
                <button
                  type="button"
                  className="nle-playhead-hit-target"
                  aria-label="Drag playhead"
                  title="Drag playhead"
                  onPointerDown={(event) => {
                    event.stopPropagation()
                    seekPointerDown(event)
                  }}
                />
              </div>

              <div className="nle-clip-sequence">
                {safeClips.map((clip, index) => {
                  const active = clip.clip_id === selectedClipId
                  const slot = isTop10 && index < 10 ? `#${10 - index}` : ""
                  const width = Math.max(28, Number(getClipWidth?.(clip) || 28))
                  const trimStart = Number(clip.trim_start || 0)
                  const sourceDuration = Number(getClipSourceDuration?.(clip) || 0)
                  const trimEnd = Number(clip.trim_end || 0) > trimStart
                    ? Number(clip.trim_end)
                    : sourceDuration

                  return (
                    <article
                      key={clip.clip_id}
                      draggable
                      className={[
                        "nle-clip",
                        active ? "selected" : "",
                        draggedClipId === clip.clip_id ? "dragging" : ""
                      ].filter(Boolean).join(" ")}
                      style={{
                        width: `${width}px`,
                        minWidth: `${width}px`,
                        flexBasis: `${width}px`
                      }}
                      onDragStart={(event) => {
                        if (event.target.closest(".nle-trim-handle")) {
                          event.preventDefault()
                          return
                        }
                        event.dataTransfer.effectAllowed = "move"
                        event.dataTransfer.setData("text/plain", clip.clip_id)
                        onDragStart?.(clip.clip_id)
                      }}
                      onDragOver={(event) => {
                        event.preventDefault()
                        event.dataTransfer.dropEffect = "move"
                      }}
                      onDrop={(event) => handleDrop(event, clip.clip_id)}
                      onDragEnd={onDragEnd}
                      onPointerDown={(event) => {
                        // Keep native clip reordering available. Timeline seeking
                        // happens on click so a normal clip drag is not hijacked.
                        event.stopPropagation()
                      }}
                      onClick={(event) => {
                        event.stopPropagation()
                        onSelectClip?.(clip, { preservePlayhead: true })
                        seekClick(event)
                      }}
                      onDoubleClick={(event) => {
                        event.stopPropagation()
                        onSplit?.(clip.clip_id)
                      }}
                      onContextMenu={(event) => {
                        event.preventDefault()
                        event.stopPropagation()
                        onSelectClip?.(clip, { preservePlayhead: true })
                        setClipMenu({ clipId: clip.clip_id, x: event.clientX, y: event.clientY })
                      }}
                    >
                      <button
                        type="button"
                        className="nle-trim-handle left"
                        onPointerDown={(event) => onTrimStart?.(event, clip, "left")}
                        onClick={stopPointer}
                        title="Drag to trim clip start"
                        aria-label="Trim clip start"
                      />

                      <div className="nle-clip-preview nle-frame-strip" aria-hidden="true">
                        {(() => {
                          const frameCount = Math.max(1, Math.min(20, Math.ceil(width / 112)))
                          return Array.from({ length: frameCount }, (_, frameIndex) => {
                            const sampleTime = trimStart + ((frameIndex + 0.5) / frameCount) * Math.max(0.01, trimEnd - trimStart)
                            return (
                              <TimelineFrame
                                key={`${clip.clip_id}-${frameCount}-${frameIndex}`}
                                src={`${apiBase}${clip.preview_url}`}
                                time={sampleTime}
                              />
                            )
                          })
                        })()}
                      </div>

                      <div className="nle-clip-copy title-only">
                        <b>{slot && <strong>{slot}</strong>}{clip.title || `Clip ${index + 1}`}</b>
                      </div>

                      <div className="nle-clip-actions">
                        <button
                          type="button"
                          className={clip.muted ? "active" : ""}
                          onClick={(event) => {
                            event.stopPropagation()
                            onToggleMute?.(clip.clip_id, !clip.muted)
                          }}
                          title={clip.muted ? "Unmute this clip" : "Mute this clip"}
                          aria-label={clip.muted ? "Unmute this clip" : "Mute this clip"}
                        >
                          {clip.muted ? "🔇" : "🔊"}
                        </button>
                        <button type="button" onClick={(event) => { event.stopPropagation(); onSplit?.(clip.clip_id) }} title="Split clip">✂</button>
                        <button type="button" onClick={(event) => { event.stopPropagation(); onRemove?.(clip.clip_id) }} title="Remove clip">×</button>
                      </div>

                      <button
                        type="button"
                        className={`nle-trim-handle right${controlHeld ? " time-stretch-ready" : ""}`}
                        onPointerDown={(event) => onTrimStart?.(event, clip, "right")}
                        onClick={stopPointer}
                        title="Drag to trim clip end • Hold Ctrl while dragging to change speed"
                        aria-label="Trim clip end or hold Control to time-stretch"
                      />
                    </article>
                  )
                })}

                <div
                  className="nle-static-asset outro"
                  style={{
                    width: `${OUTRO_SECONDS * safeZoom}px`,
                    minWidth: `${OUTRO_SECONDS * safeZoom}px`
                  }}
                  title="Automatically attached to the final clip"
                >
                  <b>OUTRO</b>
                  <small>15 seconds</small>
                </div>
              </div>
            </div>
          </div>

          {isTop10 && (
            <>
              <div className="nle-track-row compact">
                <div className="nle-track-controls">
                  <b>NUMBERS</b>
                  <small>V2</small>
                </div>
                <div className="nle-track-lane nle-overlay-lane">
                  {safeClips.slice(0, 10).map((clip, index) => (
                    <div
                      className="nle-number-overlay"
                      key={`number-${clip.clip_id}`}
                      style={{ width: `${Math.max(28, Number(getClipWidth?.(clip) || 28))}px` }}
                    >
                      {10 - index}
                    </div>
                  ))}
                </div>
              </div>

              <div className="nle-track-row compact">
                <div className="nle-track-controls">
                  <b>MUSIC</b>
                  <small>A2</small>
                </div>
                <div className="nle-track-lane">
                  <div className="nle-audio-bed">optional background music</div>
                </div>
              </div>
            </>
          )}

          <div className="nle-track-row compact">
            <div className="nle-track-controls">
              <b>AUDIO</b>
              <small>A1</small>
            </div>
            <div className="nle-track-lane nle-waveform-lane">
              <div className="nle-audio-clip-sequence" aria-label="Clip audio waveform preview">
                {safeClips.map((clip, clipIndex) => {
                  const width = Math.max(28, Number(getClipWidth?.(clip) || 28))
                  const barCount = Math.max(8, Math.min(90, Math.floor(width / 5)))
                  return (
                    <div
                      key={`audio-${clip.clip_id}`}
                      className={`nle-audio-clip${clip.muted ? " muted" : ""}`}
                      style={{ width: `${width}px`, minWidth: `${width}px`, flexBasis: `${width}px` }}
                      title={`${clip.title || `Clip ${clipIndex + 1}`} audio${clip.muted ? " — muted" : ""}`}
                    >
                      <div className="nle-waveform">
                        {Array.from({ length: barCount }).map((_, index) => (
                          <i
                            key={index}
                            style={{ height: `${20 + (((index + clipIndex * 11) * 37) % 55)}%` }}
                          />
                        ))}
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {clipMenu && (
        <div
          className="nle-clip-context-menu"
          style={{ left: `${clipMenu.x}px`, top: `${clipMenu.y}px` }}
          onPointerDown={(event) => event.stopPropagation()}
          role="menu"
        >
          {(() => {
            const menuClip = safeClips.find((clip) => clip.clip_id === clipMenu.clipId)
            const menuClipSpeed = Number(menuClip?.playback_rate || 1)
            const isDefaultSpeed = Math.abs(menuClipSpeed - 1) < 0.0001
            return (
              <>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onToggleMute?.(clipMenu.clipId, !menuClip?.muted)
                    setClipMenu(null)
                  }}
                >
                  {menuClip?.muted ? "Unmute Clip Audio" : "Mute Clip Audio"}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  onClick={() => {
                    onToggleSideFill?.(clipMenu.clipId, !menuClip?.blurred_side_fill)
                    setClipMenu(null)
                  }}
                >
                  {menuClip?.blurred_side_fill ? "Remove Blurred Side Fill" : "Apply Blurred Side Fill"}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  disabled={isDefaultSpeed}
                  aria-disabled={isDefaultSpeed}
                  title={isDefaultSpeed ? "This clip is already at its default 1.00× speed." : "Reset this clip to 1.00× speed."}
                  onClick={() => {
                    if (isDefaultSpeed) return
                    onResetSpeed?.(clipMenu.clipId)
                    setClipMenu(null)
                  }}
                >
                  Reset to Default Speed
                </button>
              </>
            )
          })()}
        </div>
      )}

      <footer className="nle-footer">
        <span>{formatTimelineTime(playheadSeconds)}</span>
        <span>{safeZoom}px/sec</span>
        <span>Outro +{OUTRO_SECONDS}s</span>
        <small>Double-click split • Drag edges trim • Ctrl+drag right edge changes speed • Delete removes • Ctrl+C/V copies</small>
      </footer>
    </section>
  )
}
