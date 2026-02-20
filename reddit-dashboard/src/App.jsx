

import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  AreaChart, Area, BarChart, Bar, ScatterChart, Scatter,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell
} from "recharts";

// ─── API ─────────────────────────────────────────────────────────────────────
const api = axios.create({ baseURL: "http://localhost:8000/api" });
const fetchPosts  = () => api.get("/posts/?page_size=100");
const fetchStats  = (start, end) => api.get(`/stats/?start=${start}&end=${end}`);

// ─── UTILS ───────────────────────────────────────────────────────────────────
const getSentiment = (p) =>
  p?.sentiment_score ??
  p?.sentiment ??
  p?.compound ??
  0;

const today = () => new Date().toISOString().split("T")[0];
const fmt = n => n >= 1000 ? `${(n/1000).toFixed(1)}k` : String(n ?? 0);
const ago = (utc) => {
  if (!utc) return "—";
  const ts = typeof utc === "string" ? Number(utc) : utc;
  if (!ts || isNaN(ts)) return "—";
  // auto detect milliseconds vs seconds
  const seconds = ts > 1e12 ? Math.floor(ts / 1000) : ts;
  const diff = Math.floor(Date.now()/1000 - seconds);
  if (diff < 0) return "—";
  const m = Math.floor(diff/60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m/60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h/24)}d ago`;
};
const sentColor = s => s > 0.2 ? "#4ade80" : s < -0.2 ? "#f87171" : "#94a3b8";
const priorityBadge = p => ({
  aggressive: { label: "HOT",    bg: "#ff4500", text: "#fff" },
  normal:     { label: "ACTIVE", bg: "#ff6b35", text: "#fff" },
  slow:       { label: "COOL",   bg: "#1e3a5f", text: "#7fb3e8" },
  inactive:   { label: "OLD",    bg: "#1a1a2e", text: "#4a5568" },
}[p] ?? { label: "—", bg: "#1a1a2e", text: "#4a5568" });

// ─── DESIGN TOKENS ───────────────────────────────────────────────────────────
const CSS = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:wght@300;400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #080c10;
    --surface:   #0d1117;
    --border:    rgba(255,69,0,0.15);
    --accent:    #ff4500;
    --accent2:   #ff6b35;
    --text:      #e8eaf0;
    --muted:     #64748b;
    --green:     #4ade80;
    --red:       #f87171;
    --blue:      #60a5fa;
    --glow:      0 0 40px rgba(255,69,0,0.08);
  }

  html, body, #root { height: 100%; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    overflow-x: hidden;
  }

  ::-webkit-scrollbar { width: 4px; }
  ::-webkit-scrollbar-track { background: var(--bg); }
  ::-webkit-scrollbar-thumb { background: #ff450040; border-radius: 2px; }

  .app { display: grid; grid-template-rows: 56px 1fr; height: 100vh; }

  /* HEADER */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
    background: rgba(8,12,16,0.9);
    backdrop-filter: blur(12px);
    position: sticky; top: 0; z-index: 100;
  }
  .logo {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 16px;
    letter-spacing: 0.05em;
    display: flex; align-items: center; gap: 10px;
  }
  .logo-dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--accent);
    animation: pulse 2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(255,69,0,0.5); }
    50% { opacity: 0.7; box-shadow: 0 0 0 6px rgba(255,69,0,0); }
  }
  .header-meta { display: flex; align-items: center; gap: 16px; color: var(--muted); font-size: 11px; }
  .live-badge {
    display: flex; align-items: center; gap: 6px;
    padding: 3px 10px; border-radius: 20px;
    border: 1px solid rgba(74,222,128,0.3);
    color: var(--green); font-size: 10px; letter-spacing: 0.1em;
  }
  .live-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--green); animation: pulse 1.5s infinite; }

  /* LAYOUT */
  .main { display: grid; grid-template-columns: 280px 1fr 320px; height: 100%; overflow: hidden; }
  .panel { height: 100%; overflow-y: auto; border-right: 1px solid var(--border); }
  .panel:last-child { border-right: none; border-left: 1px solid var(--border); }
  .center { overflow-y: auto; }

  /* PANELS */
  .section { padding: 16px; border-bottom: 1px solid var(--border); }
  .section-title {
    font-family: 'Syne', sans-serif;
    font-size: 10px; font-weight: 700;
    letter-spacing: 0.12em;
    color: var(--muted);
    text-transform: uppercase;
    margin-bottom: 12px;
    display: flex; align-items: center; justify-content: space-between;
  }
  .section-count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--accent);
  }

  /* METRIC CARDS */
  .metric-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    position: relative;
    overflow: hidden;
    transition: border-color 0.2s;
  }
  .metric-card:hover { border-color: rgba(255,69,0,0.4); }
  .metric-card::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px;
    background: linear-gradient(90deg, var(--accent), transparent);
  }
  .metric-label { color: var(--muted); font-size: 10px; letter-spacing: 0.08em; margin-bottom: 6px; text-transform: uppercase; }
  .metric-value { font-family: 'Syne', sans-serif; font-size: 22px; font-weight: 700; }
  .metric-sub { color: var(--muted); font-size: 10px; margin-top: 2px; }
  .metric-wide { grid-column: span 2; }

  /* POST FEED */
  .post-item {
    padding: 10px 16px;
    border-bottom: 1px solid rgba(255,69,0,0.06);
    cursor: pointer;
    transition: background 0.15s;
    position: relative;
  }
  .post-item:hover { background: rgba(255,69,0,0.04); }
  .post-item.selected { background: rgba(255,69,0,0.08); border-left: 2px solid var(--accent); }
  .post-momentum-bar {
    position: absolute; left: 0; top: 0; bottom: 0; width: 2px;
  }
  .post-subreddit { color: var(--accent); font-size: 10px; letter-spacing: 0.05em; margin-bottom: 3px; }
  .post-title { font-family: 'Syne', sans-serif; font-size: 12px; font-weight: 600; line-height: 1.35; margin-bottom: 5px; color: var(--text); }
  .post-meta { display: flex; align-items: center; gap: 10px; color: var(--muted); font-size: 10px; }
  .post-badge {
    padding: 1px 6px; border-radius: 3px; font-size: 9px;
    font-weight: 700; letter-spacing: 0.06em;
  }

  /* CENTER — CHARTS */
  .chart-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }
  .chart-title { font-family: 'Syne', sans-serif; font-size: 14px; font-weight: 700; }
  .chart-subtitle { color: var(--muted); font-size: 10px; margin-top: 2px; }

  .tab-bar { display: flex; gap: 2px; padding: 2px; background: var(--surface); border-radius: 8px; border: 1px solid var(--border); }
  .tab {
    padding: 6px 14px; border-radius: 6px; font-size: 11px;
    cursor: pointer; transition: all 0.15s; color: var(--muted);
    font-family: 'Syne', sans-serif; font-weight: 600;
    letter-spacing: 0.05em;
  }
  .tab.active { background: var(--accent); color: #fff; }

  .chart-box {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 12px;
  }

  /* POST DETAIL */
  .detail-header { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 12px; }
  .detail-title { font-family: 'Syne', sans-serif; font-size: 16px; font-weight: 700; line-height: 1.4; margin-bottom: 12px; }
  .detail-stat { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid var(--border); font-size: 11px; }
  .detail-stat:last-child { border-bottom: none; }
  .detail-stat-label { color: var(--muted); }
  .detail-stat-value { font-weight: 500; }

  .sentiment-bar {
    height: 6px; border-radius: 3px; margin-top: 8px;
    background: linear-gradient(90deg, var(--red), #94a3b8, var(--green));
    position: relative;
  }
  .sentiment-needle {
    position: absolute; top: -3px;
    width: 12px; height: 12px; border-radius: 50%;
    background: #fff;
    border: 2px solid var(--accent);
    transform: translateX(-50%);
    transition: left 0.5s ease;
  }

  /* LEADERBOARD */
  .leaderboard-item {
    display: flex; align-items: center; gap: 10px;
    padding: 8px 0; border-bottom: 1px solid rgba(255,69,0,0.06);
    font-size: 11px;
  }
  .rank { color: var(--accent); font-weight: 700; font-size: 12px; min-width: 20px; }
  .lb-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .lb-val { color: var(--muted); min-width: 40px; text-align: right; }

  /* SEARCH */
  .search-box {
    width: 100%; padding: 8px 12px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 6px; color: var(--text); font-family: 'JetBrains Mono', monospace;
    font-size: 12px; outline: none; transition: border-color 0.2s;
    margin-bottom: 8px;
  }
  .search-box:focus { border-color: rgba(255,69,0,0.5); }
  .search-box::placeholder { color: var(--muted); }

  /* CUSTOM TOOLTIP */
  .recharts-tooltip-wrapper .custom-tooltip {
    background: #0d1117 !important;
    border: 1px solid rgba(255,69,0,0.3) !important;
    border-radius: 6px !important;
    padding: 8px 12px !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px !important;
  }

  /* EMPTY STATE */
  .empty { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 40px; color: var(--muted); gap: 8px; }
  .empty-icon { font-size: 32px; opacity: 0.4; }

  /* ANIMATIONS */
  @keyframes fadeInUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
  .fade-in { animation: fadeInUp 0.3s ease both; }

  /* SCROLL FIX */
  .panel, .center { scrollbar-width: thin; scrollbar-color: #ff450020 transparent; }
`;

// ─── CUSTOM TOOLTIP ───────────────────────────────────────────────────────────
function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#0d1117", border: "1px solid rgba(255,69,0,0.3)",
      borderRadius: 6, padding: "8px 12px",
      fontFamily: "'JetBrains Mono', monospace", fontSize: 11
    }}>
      {label && <div style={{ color: "#64748b", marginBottom: 4 }}>{label}</div>}
      {payload.map((p, i) => (
        <div key={i} style={{ color: p.color || "#e8eaf0" }}>
          {p.name}: <strong>{fmt(p.value)}</strong>
        </div>
      ))}
    </div>
  );
}

// ─── MAIN APP ─────────────────────────────────────────────────────────────────
export default function App() {
  const [posts, setPosts]           = useState([]);
  const [stats, setStats]           = useState(null);
  const [selectedPost, setSelected] = useState(null);
  const [activeTab, setActiveTab]   = useState("engagement");
  const [search, setSearch]         = useState("");
  const [lastRefresh, setRefresh]   = useState(null);
  const [loading, setLoading]       = useState(true);
  const [postCount, setPostCount]   = useState(0);
  const prevScores = useRef({});

  const load = useCallback(async () => {
    try {
      const [postsRes, statsRes] = await Promise.all([
        fetchPosts(),
        fetchStats(today(), today()),
      ]);
      const incoming = postsRes.data?.results ?? postsRes.data ?? [];
      // track score changes for flash effect
      
      setPosts(incoming);
      setStats(statsRes.data);
      setPostCount(postsRes.data?.count ?? incoming.length);
      setRefresh(new Date());
      setLoading(false);
    } catch (e) {
      console.error("API error:", e);
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);

  const filtered = posts.filter(p =>
    !search || p.title?.toLowerCase().includes(search.toLowerCase()) ||
    p.subreddit?.toLowerCase().includes(search.toLowerCase())
  );

  const topPosts = [...posts].sort((a, b) => b.engagement_score - a.engagement_score).slice(0, 20);
  const subredditMap = {};
  posts.forEach(p => {
    const s = p.subreddit || "unknown";
    if (!subredditMap[s]) subredditMap[s] = { subreddit: s, posts: 0, totalScore: 0 };
    subredditMap[s].posts++;
    subredditMap[s].totalScore += p.current_score || 0;
  });
  const subredditData = Object.values(subredditMap)
    .sort((a, b) => b.totalScore - a.totalScore).slice(0, 12);

  const scatterData = posts.map(p => ({
    id: p.id,
    x: Math.round(p.age_minutes || 0),
    y: p.engagement_score || 0,
    name: p.title?.slice(0, 40),
    subreddit: p.subreddit,
  }));

  const momentumData = [...posts]
    .sort((a, b) => b.momentum - a.momentum)
    .slice(0, 15)
    .map(p => ({ name: p.subreddit, momentum: parseFloat((p.momentum || 0).toFixed(2)), title: p.title?.slice(0, 30) }));

const overallSent = posts.length
  ? posts.reduce((s, p) => s + getSentiment(p), 0) / posts.length
  : 0;
  return (
    <>
      <style>{CSS}</style>
      <div className="app">
        {/* ── HEADER ── */}
        <header className="header">
          <div className="logo">
            <div className="logo-dot" />
            REDDIT·PULSE
          </div>
          <div className="header-meta">
            <span>{postCount.toLocaleString()} posts tracked</span>
            <span style={{ color: "#1e3a5f" }}>│</span>
            <span>{lastRefresh ? lastRefresh.toLocaleTimeString() : "—"}</span>
            <div className="live-badge">
              <div className="live-dot" /> LIVE
            </div>
          </div>
        </header>

        <div className="main">
          {/* ── LEFT — FEED ── */}
          <aside className="panel">
            <div className="section">
              <div className="section-title">
                Live Feed
                <span className="section-count">{filtered.length}</span>
              </div>
              <input
                className="search-box"
                placeholder="Filter posts…"
                value={search}
                onChange={e => setSearch(e.target.value)}
              />
            </div>

            {loading ? (
              <div className="empty"><div className="empty-icon">⟳</div><span>Connecting…</span></div>
            ) : filtered.length === 0 ? (
              <div className="empty"><div className="empty-icon">◌</div><span>No posts</span></div>
            ) : (
              <AnimatePresence initial={false}>
                {filtered.slice(0, 60).map((p, i) => {
                  const badge = priorityBadge(p.poll_priority);
                  const momentum = p.momentum || 0;
                  const barOpacity = Math.min(momentum / 10, 1);
                  return (
                    <motion.div
                      key={p.id}
                      initial={{ opacity: 0, x: -8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.015, duration: 0.25 }}
                      className={`post-item ${selectedPost?.id === p.id ? "selected" : ""}`}
                      onClick={() => setSelected(selectedPost?.id === p.id ? null : p)}
                    >
                      <div
                        className="post-momentum-bar"
                        style={{ background: `rgba(255,69,0,${barOpacity})` }}
                      />
                      <div className="post-subreddit">r/{p.subreddit}</div>
                      <div className="post-title">{p.title?.slice(0, 90)}{p.title?.length > 90 ? "…" : ""}</div>
                      <div className="post-meta">
                       {(() => {
  const prev = prevScores.current[p.id] ?? p.current_score;
  const delta = (p.current_score ?? 0) - (prev ?? 0);

  // update AFTER computing delta
  prevScores.current[p.id] = p.current_score;

  return (
    <span
      style={{
        color: delta > 0 ? "#4ade80" : delta < 0 ? "#f87171" : undefined,
        transition: "color .3s ease"
      }}
    >
      ▲ {fmt(p.current_score)}
      {delta !== 0 && (
        <span style={{ marginLeft: 4 }}>
          ({delta > 0 ? `+${delta}` : delta})
        </span>
      )}
    </span>
  );
})()}
                        <span>💬 {fmt(p.current_comments)}</span>
                        <span>{ago(p.created_utc)}</span>
                        <span
                          className="post-badge"
                          style={{ background: badge.bg, color: badge.text }}
                        >
                          {badge.label}
                        </span>
                      </div>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
            )}
          </aside>

          {/* ── CENTER — ANALYTICS ── */}
          <main className="center" style={{ padding: 20 }}>
            {/* KPI Row */}
            <div className="metric-grid" style={{ gridTemplateColumns: "repeat(4,1fr)", marginBottom: 16 }}>
              {[
                { label: "Total Posts",    value: fmt(stats?.overview?.total_posts ?? posts.length), sub: "today" },
                { label: "Avg Score",      value: fmt(Math.round(stats?.overview?.avg_score ?? 0)), sub: "upvotes" },
                { label: "Active Authors", value: fmt(stats?.overview?.active_users ?? 0), sub: "unique" },
                { label: "Sentiment",      value: overallSent > 0.1 ? "POS" : overallSent < -0.1 ? "NEG" : "NEU",
                  sub: overallSent.toFixed(3),
                  color: sentColor(overallSent) },
              ].map((m, i) => (
                <motion.div
                  key={m.label}
                  className="metric-card"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.06 }}
                >
                  <div className="metric-label">{m.label}</div>
                  <div className="metric-value" style={{ color: m.color || "var(--text)" }}>{m.value}</div>
                  <div className="metric-sub">{m.sub}</div>
                </motion.div>
              ))}
            </div>

            {/* Chart tabs */}
            <div style={{ marginBottom: 12, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div className="tab-bar">
                {["engagement", "subreddits", "momentum", "scatter"].map(t => (
                  <button key={t} className={`tab ${activeTab === t ? "active" : ""}`} onClick={() => setActiveTab(t)}>
                    {t.charAt(0).toUpperCase() + t.slice(1)}
                  </button>
                ))}
              </div>
            </div>

            {/* Charts */}
            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -8 }}
                transition={{ duration: 0.2 }}
              >
                {activeTab === "engagement" && (
                  <div className="chart-box">
                    <div className="chart-header">
                      <div>
                        <div className="chart-title">Engagement Score — Top 20</div>
                        <div className="chart-subtitle">score + (comments × 2)</div>
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={340}>
                      <BarChart data={topPosts} layout="vertical" margin={{ left: 4, right: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,69,0,0.08)" horizontal={false} />
                        <XAxis type="number" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <YAxis
                          type="category" dataKey="title"
                          width={180} tick={{ fill: "#94a3b8", fontSize: 10 }}
                          tickFormatter={v => v?.slice(0, 24) + (v?.length > 24 ? "…" : "")}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        <Bar dataKey="engagement_score" radius={[0, 4, 4, 0]}>
                          {topPosts.map((_, i) => (
                            <Cell key={i} fill={`rgba(255,69,0,${1 - i * 0.04})`} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {activeTab === "subreddits" && (
                  <div className="chart-box">
                    <div className="chart-header">
                      <div>
                        <div className="chart-title">Subreddit Activity</div>
                        <div className="chart-subtitle">post count & cumulative score</div>
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={340}>
                      <BarChart data={subredditData} margin={{ left: 4, right: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,69,0,0.08)" vertical={false} />
                        <XAxis dataKey="subreddit" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }}
                          tickFormatter={v => `r/${v}`} />
                        <YAxis yAxisId="left" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <YAxis yAxisId="right" orientation="right" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Bar yAxisId="left" dataKey="totalScore" name="Total Score" fill="#ff4500" opacity={0.8} radius={[4,4,0,0]} />
                        <Bar yAxisId="right" dataKey="posts" name="Posts" fill="#ff6b35" opacity={0.5} radius={[4,4,0,0]} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {activeTab === "momentum" && (
                  <div className="chart-box">
                    <div className="chart-header">
                      <div>
                        <div className="chart-title">Momentum Leaders</div>
                        <div className="chart-subtitle">score / age in minutes</div>
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={340}>
                      <AreaChart data={momentumData} margin={{ left: 4, right: 16 }}>
                        <defs>
                          <linearGradient id="momentumGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="#ff4500" stopOpacity={0.4} />
                            <stop offset="100%" stopColor="#ff4500" stopOpacity={0.02} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,69,0,0.08)" vertical={false} />
                        <XAxis dataKey="name" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }}
                          tickFormatter={v => `r/${v}`} />
                        <YAxis stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <Tooltip content={<CustomTooltip />} />
                        <Area dataKey="momentum" name="Momentum" stroke="#ff4500" strokeWidth={2}
                          fill="url(#momentumGrad)" dot={{ fill: "#ff4500", r: 3 }} />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                )}

                {activeTab === "scatter" && (
                  <div className="chart-box">
                    <div className="chart-header">
                      <div>
                        <div className="chart-title">Age vs. Engagement</div>
                        <div className="chart-subtitle">post age (minutes) × engagement score</div>
                      </div>
                    </div>
                    <ResponsiveContainer width="100%" height={340}>
                      <ScatterChart margin={{ left: 4, right: 16 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,69,0,0.08)" />
                        <XAxis dataKey="x" name="Age (min)" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <YAxis dataKey="y" name="Engagement" stroke="#334155" tick={{ fill: "#64748b", fontSize: 10 }} />
                        <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(255,69,0,0.3)" }} />
                        <Scatter
  data={scatterData}
  fill="#ff4500"
  opacity={0.7}
  onClick={(e) => {
    const post = posts.find(p => p.id === e?.payload?.id);
    if (post) setSelected(post);
  }}
/>
                      </ScatterChart>
                    </ResponsiveContainer>
                  </div>
                )}
              </motion.div>
            </AnimatePresence>

            {/* Top Posts Table */}
            <div className="chart-box">
              <div className="chart-header">
                <div className="chart-title">Top Posts Today</div>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ color: "#64748b", fontSize: 10, letterSpacing: "0.08em" }}>
                    {["#", "TITLE", "SUBREDDIT", "SCORE", "COMMENTS", "MOMENTUM", "AUTHOR"].map(h => (
                      <th key={h} style={{ textAlign: "left", padding: "6px 8px", borderBottom: "1px solid rgba(255,69,0,0.1)", fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(stats?.posts?.top_posts ?? topPosts).slice(0, 15).map((p, i) => (
                    <motion.tr
                      key={p.id || i}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.02 }}
                      style={{ borderBottom: "1px solid rgba(255,69,0,0.04)", cursor: "pointer" }}
                      onClick={() => { const full = posts.find(x => x.id === p.id); if (full) setSelected(full); }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(255,69,0,0.04)"}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}
                    >
                      <td style={{ padding: "7px 8px", color: "#ff4500", fontWeight: 700 }}>{i + 1}</td>
                      <td style={{ padding: "7px 8px", maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {(p.title || "—").slice(0, 60)}{(p.title?.length ?? 0) > 60 ? "…" : ""}
                      </td>
                      <td style={{ padding: "7px 8px", color: "#ff6b35" }}>r/{p.subreddit__name ?? p.subreddit ?? "—"}</td>
                      <td style={{ padding: "7px 8px" }}>▲ {fmt(p.current_score ?? p.engagement)}</td>
                      <td style={{ padding: "7px 8px" }}>💬 {fmt(p.current_comments)}</td>
                      <td style={{ padding: "7px 8px", color: "#4ade80" }}>{(p.momentum ?? 0).toFixed(2)}</td>
                      <td style={{ padding: "7px 8px", color: "#64748b" }}>{p.author ?? "—"}</td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          </main>

          {/* ── RIGHT — DETAIL + LEADERBOARDS ── */}
          <aside className="panel" style={{ borderRight: "none", borderLeft: "1px solid var(--border)" }}>
            {/* Post detail */}
            <AnimatePresence>
              {selectedPost && (
                <motion.div
                  initial={{ opacity: 0, y: -8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className="section"
                >
                  <div className="section-title">
                    Post Detail
                    <button
                      onClick={() => setSelected(null)}
                      style={{ background: "none", border: "none", color: "var(--muted)", cursor: "pointer", fontSize: 14 }}
                    >✕</button>
                  </div>
                  <div className="detail-header">
                    <div style={{ color: "#ff4500", fontSize: 10, marginBottom: 6 }}>r/{selectedPost.subreddit}</div>
                    <div className="detail-title">{selectedPost.title}</div>
                    {[
                      ["Score",      fmt(selectedPost.current_score)],
                      ["Comments",   fmt(selectedPost.current_comments)],
                      ["Ratio",      `${Math.round((selectedPost.current_ratio || 0) * 100)}%`],
                      ["Momentum",   (selectedPost.momentum || 0).toFixed(3)],
                      ["Engagement", fmt(selectedPost.engagement_score)],
                      ["Age",        `${Math.round(selectedPost.age_minutes || 0)} min`],
                      ["Author",     `u/${selectedPost.author}`],
                      ["Priority",   selectedPost.poll_priority ?? "—"],
                    ].map(([l, v]) => (
                      <div key={l} className="detail-stat">
                        <span className="detail-stat-label">{l}</span>
                        <span className="detail-stat-value">{v}</span>
                      </div>
                    ))}
                    {/* Sentiment bar */}
                    <div style={{ marginTop: 12 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#64748b", marginBottom: 4 }}>
                        <span>Sentiment</span>
                        <span style={{ color: sentColor(getSentiment(selectedPost))}}>
                          {(getSentiment(selectedPost).toFixed(3))}
                        </span>
                      </div>
                      <div className="sentiment-bar">
                        <div
                          className="sentiment-needle"
                          style={{ left: `${ ((getSentiment(selectedPost) + 1) / 2) * 100}%` }}
                        />
                      </div>
                    </div>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Top Authors Leaderboard */}
            <div className="section">
              <div className="section-title">Top Authors</div>
              {(stats?.users ?? []).slice(0, 10).map((u, i) => (
                <div key={u.author} className="leaderboard-item">
                  <span className="rank">#{i + 1}</span>
                  <span className="lb-name" title={u.author}>u/{u.author}</span>
                  <span className="lb-val" style={{ color: "#ff4500" }}>▲{fmt(u.total_score)}</span>
                  <span className="lb-val">{u.posts}p</span>
                </div>
              ))}
              {!stats?.users?.length && (
                <div style={{ color: "#334155", fontSize: 11, padding: "8px 0" }}>Loading…</div>
              )}
            </div>

            {/* Top Subreddits */}
            <div className="section">
              <div className="section-title">Subreddit Rankings</div>
              {(stats?.subreddits ?? []).slice(0, 10).map((s, i) => (
                <div key={s.subreddit__name} className="leaderboard-item">
                  <span className="rank">#{i + 1}</span>
                  <span className="lb-name">r/{s.subreddit__name}</span>
                  <span className="lb-val" style={{ color: "#ff6b35" }}>{s.count} posts</span>
                </div>
              ))}
            </div>

            {/* Most Commented */}
            {stats?.posts?.most_commented && (
              <div className="section">
                <div className="section-title">Most Commented</div>
                <div className="detail-header" style={{ marginBottom: 0 }}>
                  <div style={{ color: "#ff4500", fontSize: 10, marginBottom: 4 }}>
                    💬 {fmt(stats.posts.most_commented.current_comments)} comments
                  </div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 600, lineHeight: 1.4 }}>
                    {stats.posts.most_commented.title?.slice(0, 100)}
                  </div>
                  <div style={{ color: "#64748b", fontSize: 10, marginTop: 6 }}>
                    by u/{stats.posts.most_commented.author}
                  </div>
                </div>
              </div>
            )}

            {/* Most Upvoted */}
            {stats?.posts?.most_upvoted && (
              <div className="section">
                <div className="section-title">Most Upvoted</div>
                <div className="detail-header" style={{ marginBottom: 0 }}>
                  <div style={{ color: "#ff4500", fontSize: 10, marginBottom: 4 }}>
                    ▲ {fmt(stats.posts.most_upvoted.current_score)} points
                  </div>
                  <div style={{ fontFamily: "'Syne', sans-serif", fontSize: 12, fontWeight: 600, lineHeight: 1.4 }}>
                    {stats.posts.most_upvoted.title?.slice(0, 100)}
                  </div>
                  <div style={{ color: "#64748b", fontSize: 10, marginTop: 6 }}>
                    by u/{stats.posts.most_upvoted.author}
                  </div>
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </>
  );
}
