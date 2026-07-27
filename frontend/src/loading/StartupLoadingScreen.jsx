import logo from "../assets/nbatop10-logo.png"

function formatRemainingTime(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) {
    return "Calculating..."
  }

  const safeSeconds = Math.max(0, Math.ceil(Number(seconds || 0)))
  const minutes = Math.floor(safeSeconds / 60)
  const remainingSeconds = safeSeconds % 60
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`
}

export default function StartupLoadingScreen({
  step,
  progress,
  remainingSeconds,
  items,
  error,
  showTechnicalDetails,
  onToggleTechnicalDetails,
  onRetry,
  phase
}) {
  const safeProgress = Math.min(100, Math.max(0, Number(progress || 0)))
  const progressText = safeProgress >= 100 ? "100" : Math.min(99.9, safeProgress).toFixed(1)
  const completed = (items || []).filter(item => ["done", "warning"].includes(item.status)).length
  const waiting = (items || []).filter(item => item.status === "waiting").length
  const running = (items || []).filter(item => item.status === "running").length
  const background = (items || []).filter(item => item.status === "warning").length
  const failed = (items || []).filter(item => item.status === "error").length

  return (
    <div className="app">
      <div style={{
        minHeight: "100vh",
        width: "100%",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "24px",
        background: "radial-gradient(circle at top, rgba(255,255,255,0.08), rgba(0,0,0,0.95))"
      }}>
        <div style={{
          width: "min(520px, 92vw)",
          minHeight: "318px",
          boxSizing: "border-box",
          border: "1px solid rgba(255,255,255,0.14)",
          borderRadius: "22px",
          padding: "28px",
          background: "rgba(10,10,14,0.92)",
          boxShadow: "0 24px 70px rgba(0,0,0,0.45)",
          textAlign: "center",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center"
        }}>
          <img src={logo} className="logo" style={{ width: "90px", marginBottom: "14px" }} />
          <h2 style={{ margin: "8px 0 10px" }}>Loading CourtVision AI</h2>
          <p style={{
            color: "rgba(255,255,255,0.72)",
            lineHeight: 1.5,
            minHeight: "48px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto"
          }}>{step}</p>

          <div style={{
            marginTop: "8px",
            color: "rgba(255,255,255,0.9)",
            fontSize: "18px",
            fontWeight: 800,
            letterSpacing: "0.08em"
          }}>{progressText}%</div>

          <div style={{
            height: "10px",
            borderRadius: "999px",
            overflow: "hidden",
            background: "rgba(255,255,255,0.12)",
            marginTop: "20px"
          }}>
            <div style={{
              height: "100%",
              width: `${safeProgress}%`,
              borderRadius: "999px",
              background: "rgba(255,255,255,0.85)",
              transition: "width 0.18s linear"
            }} />
          </div>

          <div style={{
            marginTop: "12px",
            display: "flex",
            justifyContent: "center",
            gap: "14px",
            flexWrap: "wrap",
            color: "rgba(255,255,255,0.62)",
            fontSize: "12px",
            lineHeight: 1.35
          }}>
            <span>Estimated Time Remaining: <b style={{ color: "rgba(255,255,255,0.82)" }}>{formatRemainingTime(remainingSeconds)}</b></span>
            <span>Ready: <b style={{ color: "rgba(255,255,255,0.82)" }}>{completed}/{(items || []).length}</b></span>
            {running > 0 ? <span>Active: <b style={{ color: "#facc15" }}>{running}</b></span> : null}
            {waiting > 0 ? <span>Waiting: <b style={{ color: "rgba(255,255,255,0.82)" }}>{waiting}</b></span> : null}
            {background > 0 ? <span>Background refreshes: <b style={{ color: "#fb923c" }}>{background}</b></span> : null}
            {failed > 0 ? <span>Failed: <b style={{ color: "#f87171" }}>{failed}</b></span> : null}
          </div>

          <div style={{
            marginTop: "14px",
            maxHeight: "150px",
            overflowY: "auto",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: "14px",
            background: "rgba(255,255,255,0.045)",
            padding: "10px",
            textAlign: "left"
          }}>
            {(items || []).map(item => (
              <div key={item.key} style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1fr) auto",
                gap: "10px",
                alignItems: "center",
                padding: "6px 0",
                borderBottom: "1px solid rgba(255,255,255,0.06)",
                color: item.status === "done"
                  ? "rgba(255,255,255,0.48)"
                  : item.status === "warning"
                    ? "rgba(255,255,255,0.78)"
                    : item.status === "running"
                      ? "rgba(255,255,255,0.95)"
                      : item.status === "error"
                        ? "#f87171"
                        : "rgba(255,255,255,0.62)",
                fontSize: "12px",
                lineHeight: 1.25
              }}>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{item.label}</span>
                <b style={{
                  color: item.status === "done"
                    ? "#4ade80"
                    : item.status === "warning"
                      ? "#fb923c"
                      : item.status === "running"
                        ? "#facc15"
                        : item.status === "error"
                          ? "#f87171"
                          : "rgba(255,255,255,0.46)",
                  textTransform: "uppercase",
                  fontSize: "10px",
                  letterSpacing: "0.08em"
                }}>
                  {item.status === "running" && Number(item.running_progress || 0) > 0
                    ? `active ${Math.round(Number(item.running_progress || 0))}%`
                    : item.status === "warning"
                      ? "background"
                      : item.status}
                </b>
              </div>
            ))}
          </div>

          {error ? (
            <div style={{
              marginTop: "14px",
              padding: "14px",
              border: "1px solid rgba(248,113,113,0.5)",
              borderRadius: "14px",
              background: "rgba(127,29,29,0.22)",
              textAlign: "left"
            }}>
              <strong style={{ display: "block", color: "#fca5a5", marginBottom: "6px", fontSize: "17px" }}>Startup verification failed</strong>
              <div style={{ color: "rgba(255,255,255,0.88)", lineHeight: 1.45 }}>
                CourtVision could not verify every required section. Open the details below for the exact task, endpoint, HTTP status, timeout, or response-validation error.
              </div>
              <button type="button" onClick={onToggleTechnicalDetails} style={{
                marginTop: "10px",
                padding: 0,
                border: 0,
                background: "transparent",
                color: "#fca5a5",
                cursor: "pointer",
                fontWeight: 700
              }}>{showTechnicalDetails ? "Hide details" : "Show more"}</button>
              {showTechnicalDetails ? (
                <pre style={{
                  marginTop: "10px",
                  maxHeight: "120px",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  color: "rgba(255,255,255,0.72)",
                  fontSize: "11px"
                }}>{error}</pre>
              ) : null}
              <button type="button" onClick={onRetry} style={{
                marginTop: "10px",
                width: "100%",
                border: "1px solid rgba(255,255,255,0.18)",
                borderRadius: "10px",
                padding: "10px 12px",
                background: "#c8102e",
                color: "white",
                cursor: "pointer",
                fontWeight: 800
              }}>Retry Startup</button>
            </div>
          ) : null}

          <small style={{ display: "block", marginTop: "16px", color: "rgba(255,255,255,0.5)" }}>
            {phase === "video" ? "Syncing channel videos and public stats..." :
              phase === "revenue" ? "Syncing YouTube Analytics revenue and RPM..." :
              phase === "data" ? "Loading saved data and verifying all tabs..." :
              phase === "complete" ? "All required CourtVision features are ready." :
              "Connecting to saved CourtVision data..."}
          </small>
        </div>
      </div>
    </div>
  )
}
