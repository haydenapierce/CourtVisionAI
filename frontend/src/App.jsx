import "./App.css"
import { useEffect, useState } from "react"
import logo from "./assets/nbatop10-logo.png"

const API = "http://127.0.0.1:8002"

function App() {
  const [tab, setTab] = useState("dashboard")

  const [stats, setStats] = useState({})
  const [savedVideos, setSavedVideos] = useState([])
  const [rankings, setRankings] = useState([])
  const [players, setPlayers] = useState([])
  const [missingLegends, setMissingLegends] = useState([])

  const [playerSearch, setPlayerSearch] = useState("")
  const [playerResults, setPlayerResults] = useState([])
  const [prediction, setPrediction] = useState(null)

  const [simPlayer, setSimPlayer] = useState("")
  const [simLength, setSimLength] = useState(3)
  const [simType, setSimType] = useState("Top 10")
  const [simulation, setSimulation] = useState(null)

  const [thumbnailPreview, setThumbnailPreview] = useState(null)
  const [thumbnailAnalysis, setThumbnailAnalysis] = useState(null)

  const [loading, setLoading] = useState(false)

  function loadData() {
    fetch(`${API}/dashboard/stats`)
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})

    fetch(`${API}/dashboard/saved-videos`)
      .then(r => r.json())
      .then(d => setSavedVideos(d.saved_videos || []))
      .catch(() => {})

    fetch(`${API}/dashboard/player-rankings`)
      .then(r => r.json())
      .then(d => setRankings(d.player_rankings || []))
      .catch(() => {})

    fetch(`${API}/idea-lab/top-50`)
      .then(r => r.json())
      .then(d => setPlayers(d.top_50 || []))
      .catch(() => {})

    fetch(`${API}/missing-legends`)
      .then(r => r.json())
      .then(d => setMissingLegends(d.missing_legends || []))
      .catch(() => {})
  }

  useEffect(() => {
    loadData()
  }, [])

  function syncChannel() {
    setLoading(true)

    fetch(`${API}/dashboard/sync`)
      .then(r => r.json())
      .then(() => loadData())
      .finally(() => setLoading(false))
  }

  function searchPlayers(value) {
    setPlayerSearch(value)
    setPrediction(null)

    if (!value.trim()) {
      setPlayerResults([])
      return
    }

    fetch(`${API}/player-predictor/search?q=${encodeURIComponent(value)}`)
      .then(r => r.json())
      .then(d => setPlayerResults(d.results || []))
      .catch(() => {})
  }

  function predictPlayer(name) {
    setPlayerSearch(name)
    setPlayerResults([])

    fetch(`${API}/player-predictor/predict?name=${encodeURIComponent(name)}`)
      .then(r => r.json())
      .then(d => {
        if (d.found) {
          setPrediction(d.prediction)
        }
      })
      .catch(() => {})
  }

  function runSimulation() {
    if (!simPlayer.trim()) return

    fetch(
      `${API}/revenue-simulator?name=${encodeURIComponent(simPlayer)}&video_length=${simLength}&title_type=${encodeURIComponent(simType)}`
    )
      .then(r => r.json())
      .then(d => {
        if (d.found) {
          setSimulation(d.simulation)
        }
      })
      .catch(() => {})
  }

  function analyzeThumbnail(file) {
    if (!file) return

    setThumbnailPreview(URL.createObjectURL(file))
    setThumbnailAnalysis(null)

    const formData = new FormData()
    formData.append("file", file)

    fetch(`${API}/thumbnail-analyzer/analyze`, {
      method: "POST",
      body: formData
    })
      .then(r => r.json())
      .then(d => setThumbnailAnalysis(d.analysis))
      .catch(() => {})
  }

  function riskColor(risk) {
    if (risk <= 35) return "#4ade80"
    if (risk <= 60) return "#facc15"
    return "#f87171"
  }

  function scoreColor(score) {
    if (score >= 80) return "#4ade80"
    if (score >= 60) return "#facc15"
    return "#f87171"
  }

  function viewsRange(item) {
    if (!item) return "—"

    if (item.projected_views_low && item.projected_views_high) {
      return `${item.projected_views_low.toLocaleString()}–${item.projected_views_high.toLocaleString()}`
    }

    return item.projected_views?.toLocaleString() || "—"
  }

  function revenueRange(item) {
    if (!item) return "—"

    if (item.projected_revenue_low && item.projected_revenue_high) {
      return `$${item.projected_revenue_low}–$${item.projected_revenue_high}`
    }

    return `$${item.projected_revenue || "—"}`
  }

  function subscriberRange(item) {
    if (!item) return "—"

    if (item.projected_subscribers_low && item.projected_subscribers_high) {
      return `${item.projected_subscribers_low.toLocaleString()}–${item.projected_subscribers_high.toLocaleString()}`
    }

    return item.projected_subscribers?.toLocaleString() || "—"
  }

  const nextIdea = players[0]
  const topMissing = missingLegends.slice(0, 3)
  const topPlayers = rankings.slice(0, 5)

  const totalEstimatedRevenue = rankings.reduce(
    (sum, p) => sum + Number(p.estimated_revenue || 0),
    0
  )

  const bestMoneyPlayer = rankings[0]

  return (
    <div className="app">
      <div className="sidebar">
        <img src={logo} className="logo" />

        <button onClick={() => setTab("dashboard")}>Dashboard</button>
        <button onClick={() => setTab("videos")}>Videos</button>
        <button onClick={() => setTab("rankings")}>Player Rankings</button>
        <button onClick={() => setTab("ai")}>AI Report</button>
        <button onClick={() => setTab("ideas")}>Idea Lab</button>
        <button onClick={() => setTab("predictor")}>Player Predictor</button>
        <button onClick={() => setTab("simulator")}>Revenue Simulator</button>
        <button onClick={() => setTab("missing")}>Missing Legends</button>
        <button onClick={() => setTab("thumbnail")}>Thumbnail Analyzer</button>

        <button className="sync" onClick={syncChannel}>
          {loading ? "Syncing..." : "Sync Channel"}
        </button>
      </div>

      <div className="main">
        {tab === "dashboard" && (
          <>
            <div className="hero">
              <div>
                <h1 className="title">NBATop10 Analytics</h1>
                <p className="subtitle">AI-powered YouTube growth engine</p>
              </div>

              <div className="live-status">LIVE</div>
            </div>

            <div className="grid">
              <div className="card stat-card">
                <h2>{stats.subscribers?.toLocaleString() || "—"}</h2>
                <p>Subscribers</p>
              </div>

              <div className="card stat-card">
                <h2>{stats.total_views?.toLocaleString() || "—"}</h2>
                <p>Total Views</p>
              </div>

              <div className="card stat-card">
                <h2>{stats.video_count || "—"}</h2>
                <p>Total Videos</p>
              </div>

              <div className="card stat-card">
                <h2>{savedVideos.length}</h2>
                <p>Synced Videos</p>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Next Best Upload</h2>

                {nextIdea ? (
                  <>
                    <h3>{nextIdea.name}</h3>
                    <p>{nextIdea.video_idea}</p>

                    <div className="quick-stat">
                      <span>Projected Views</span>
                      <b>{viewsRange(nextIdea)}</b>
                    </div>

                    <div className="quick-stat">
                      <span>Projected Revenue</span>
                      <b>{revenueRange(nextIdea)}</b>
                    </div>

                    <div className="quick-stat">
                      <span>Copyright Risk</span>
                      <b style={{ color: riskColor(nextIdea.copyright_risk) }}>
                        {nextIdea.copyright_risk}%
                      </b>
                    </div>
                  </>
                ) : (
                  <p>Sync channel to generate ideas.</p>
                )}
              </div>

              <div className="card dashboard-card">
                <h2>Revenue Snapshot</h2>

                <div className="quick-stat">
                  <span>Estimated Revenue</span>
                  <b>${totalEstimatedRevenue.toFixed(2)}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Money Player</span>
                  <b>{bestMoneyPlayer?.player || "—"}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Player Revenue</span>
                  <b>${bestMoneyPlayer?.estimated_revenue || "—"}</b>
                </div>

                <div className="quick-stat">
                  <span>Best Money Pattern</span>
                  <b>Legends / Nostalgia</b>
                </div>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Top Missing Legends</h2>

                {topMissing.map((p, i) => (
                  <div className="mini-row" key={i}>
                    <span>#{i + 1} {p.name}</span>
                    <span>{revenueRange(p)}</span>
                  </div>
                ))}

                {topMissing.length === 0 && (
                  <p>No missing legends loaded yet.</p>
                )}
              </div>

              <div className="card dashboard-card">
                <h2>Copyright Safety</h2>

                <div className="quick-stat">
                  <span>Safest Strategy</span>
                  <b>Older legends</b>
                </div>

                <div className="quick-stat">
                  <span>Riskier Strategy</span>
                  <b>Modern clips</b>
                </div>

                <div className="quick-stat">
                  <span>Current Channel Risk</span>
                  <b style={{ color: "#facc15" }}>Moderate</b>
                </div>

                <div className="quick-stat">
                  <span>Best Format</span>
                  <b>Top 10 Career</b>
                </div>
              </div>
            </div>

            <div className="dashboard-row">
              <div className="card dashboard-card">
                <h2>Top Performing Players</h2>

                {topPlayers.map((p, i) => (
                  <div className="mini-row" key={i}>
                    <span>#{i + 1} {p.player}</span>
                    <span>{p.total_views?.toLocaleString()} views</span>
                  </div>
                ))}
              </div>

              <div className="card dashboard-card">
                <h2>Thumbnail Score Shortcut</h2>

                {thumbnailAnalysis ? (
                  <>
                    <div className="quick-stat">
                      <span>Last CTR Score</span>
                      <b style={{ color: scoreColor(thumbnailAnalysis.ctr_score) }}>
                        {thumbnailAnalysis.ctr_score}/100
                      </b>
                    </div>

                    <div className="quick-stat">
                      <span>Verdict</span>
                      <b>{thumbnailAnalysis.verdict}</b>
                    </div>
                  </>
                ) : (
                  <>
                    <p>No thumbnail analyzed yet.</p>
                    <button className="sync" onClick={() => setTab("thumbnail")}>
                      Analyze Thumbnail
                    </button>
                  </>
                )}
              </div>
            </div>
          </>
        )}

        {tab === "videos" && (
          <div className="card big">
            <h2>Saved Channel Videos</h2>

            {savedVideos.map((v, i) => (
              <div className="row" key={i}>
                <b>{v.title}</b>
                <span>Views: {v.views?.toLocaleString()}</span>
                <span>Likes: {v.likes?.toLocaleString()}</span>
                <span>Comments: {v.comments?.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "rankings" && (
          <div className="card big">
            <h2>Player Rankings</h2>

            {rankings.map((p, i) => (
              <div className="row" key={i}>
                <b>#{i + 1} {p.player}</b>
                <span>Total Views: {p.total_views?.toLocaleString()}</span>
                <span>Average Views: {p.average_views?.toLocaleString()}</span>
                <span>Revenue: ${p.estimated_revenue}</span>
                <span>Videos: {p.videos}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "ai" && (
          <div className="card big">
            <h2>AI Report</h2>
            <p>
              Next upgrade: full AI report with revenue trends, title insights,
              and copyright safety analysis.
            </p>
          </div>
        )}

        {tab === "ideas" && (
          <div className="card big">
            <h2>NBA Idea Lab - Top Money Opportunities</h2>

            {players.map((p, i) => (
              <div className="row" key={i}>
                <b>#{i + 1} {p.name}</b>
                <span>{p.video_idea}</span>
                <span>Projected Revenue: {revenueRange(p)}</span>
                <span>Projected Views: {viewsRange(p)}</span>
                <span>RPM: ${p.expected_rpm}</span>
                <span style={{ color: riskColor(p.copyright_risk) }}>
                  Copyright Risk: {p.copyright_risk}%
                </span>
              </div>
            ))}
          </div>
        )}

        {tab === "predictor" && (
          <div className="card big">
            <h2>Player Predictor</h2>

            <input
              value={playerSearch}
              onChange={(e) => searchPlayers(e.target.value)}
              placeholder="Search player..."
              className="search-box"
            />

            {playerResults.map((p, i) => (
              <div
                key={i}
                className="search-result"
                onClick={() => predictPlayer(p.name)}
              >
                <b>{p.name}</b>
                <span>{p.position} | {p.era} | {p.priority}</span>
              </div>
            ))}

            {prediction && (
              <div className="prediction-card">
                <h2>{prediction.name}</h2>

                <div className="quick-stat">
                  <span>Video Idea</span>
                  <b>{prediction.video_idea}</b>
                </div>

                <div className="quick-stat">
                  <span>Projected Views</span>
                  <b>{viewsRange(prediction)}</b>
                </div>

                <div className="quick-stat">
                  <span>Projected Revenue</span>
                  <b>{revenueRange(prediction)}</b>
                </div>

                <div className="quick-stat">
                  <span>Expected RPM</span>
                  <b>${prediction.expected_rpm}</b>
                </div>

                <div className="quick-stat">
                  <span>Subscriber Gain</span>
                  <b>{subscriberRange(prediction)}</b>
                </div>

                <div className="quick-stat">
                  <span>Copyright Risk</span>
                  <b style={{ color: riskColor(prediction.copyright_risk) }}>
                    {prediction.copyright_risk}%
                  </b>
                </div>

                <p>{prediction.recommendation}</p>
              </div>
            )}
          </div>
        )}

        {tab === "simulator" && (
          <div className="card big">
            <h2>Revenue Simulator</h2>

            <input
              value={simPlayer}
              onChange={(e) => setSimPlayer(e.target.value)}
              placeholder="Player name..."
              className="search-box"
            />

            <select
              value={simLength}
              onChange={(e) => setSimLength(e.target.value)}
              className="search-box"
            >
              <option value={1}>1 Minute</option>
              <option value={2}>2 Minutes</option>
              <option value={3}>3 Minutes</option>
              <option value={5}>5 Minutes</option>
              <option value={8}>8 Minutes</option>
            </select>

            <select
              value={simType}
              onChange={(e) => setSimType(e.target.value)}
              className="search-box"
            >
              <option>Top 10</option>
              <option>Career</option>
              <option>Clutch</option>
              <option>Poster</option>
            </select>

            <button className="sync" onClick={runSimulation}>
              Simulate Revenue
            </button>

            {simulation && (
              <div className="prediction-card">
                <h2>{simulation.name}</h2>

                <div className="quick-stat">
                  <span>Projected Views</span>
                  <b>{viewsRange(simulation)}</b>
                </div>

                <div className="quick-stat">
                  <span>Projected Revenue</span>
                  <b>{revenueRange(simulation)}</b>
                </div>

                <div className="quick-stat">
                  <span>Expected RPM</span>
                  <b>${simulation.expected_rpm}</b>
                </div>

                <div className="quick-stat">
                  <span>Projected Subscribers</span>
                  <b>{subscriberRange(simulation)}</b>
                </div>

                <div className="quick-stat">
                  <span>Copyright Risk</span>
                  <b style={{ color: riskColor(simulation.copyright_risk) }}>
                    {simulation.copyright_risk}%
                  </b>
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "missing" && (
          <div className="card big">
            <h2>Missing Legends - Untapped Videos</h2>

            <p>
              These are high-potential players that do not appear to have a Top 10 video yet.
            </p>

            {missingLegends.map((p, i) => (
              <div className="row" key={i}>
                <b>#{i + 1} {p.name}</b>
                <span>{p.video_idea}</span>
                <span>Projected Revenue: {revenueRange(p)}</span>
                <span>Projected Views: {viewsRange(p)}</span>
                <span>RPM: ${p.expected_rpm}</span>
                <span style={{ color: riskColor(p.copyright_risk) }}>
                  Copyright Risk: {p.copyright_risk}%
                </span>
                <span>Priority: {p.priority}</span>
                <span>Era: {p.era}</span>
                <span>{p.recommendation}</span>
              </div>
            ))}
          </div>
        )}

        {tab === "thumbnail" && (
          <div className="card big">
            <h2>Thumbnail Analyzer</h2>

            <p>
              Upload a thumbnail to score brightness, contrast, color separation,
              aspect ratio, and estimated CTR potential.
            </p>

            <input
              type="file"
              accept="image/*"
              onChange={(e) => analyzeThumbnail(e.target.files[0])}
              className="search-box"
            />

            {thumbnailPreview && (
              <img
                src={thumbnailPreview}
                alt="Thumbnail preview"
                style={{
                  width: "100%",
                  maxWidth: "640px",
                  borderRadius: "18px",
                  marginTop: "20px",
                  border: "1px solid #333"
                }}
              />
            )}

            {thumbnailAnalysis && (
              <div className="prediction-card">
                <h2>
                  CTR Score:
                  <span style={{ color: scoreColor(thumbnailAnalysis.ctr_score) }}>
                    {" "}{thumbnailAnalysis.ctr_score}/100
                  </span>
                </h2>

                <div className="quick-stat">
                  <span>Size</span>
                  <b>{thumbnailAnalysis.width} x {thumbnailAnalysis.height}</b>
                </div>

                <div className="quick-stat">
                  <span>Aspect Ratio</span>
                  <b>{thumbnailAnalysis.aspect_ratio}</b>
                </div>

                <div className="quick-stat">
                  <span>Brightness</span>
                  <b>{thumbnailAnalysis.brightness}</b>
                </div>

                <div className="quick-stat">
                  <span>Contrast</span>
                  <b>{thumbnailAnalysis.contrast}</b>
                </div>

                <div className="quick-stat">
                  <span>Color Separation</span>
                  <b>{thumbnailAnalysis.color_separation}</b>
                </div>

                <div className="quick-stat">
                  <span>Verdict</span>
                  <b>{thumbnailAnalysis.verdict}</b>
                </div>

                <h3>Recommendations</h3>

                {thumbnailAnalysis.recommendations?.map((r, i) => (
                  <p key={i}>• {r}</p>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default App