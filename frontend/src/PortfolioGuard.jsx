import { useState, useEffect, useCallback, useRef } from "react";

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Configuration
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const API = "/api/v1";

const STRATEGIES = [
  { id: "combined", label: "Combined" },
  { id: "ma_crossover", label: "MA Crossover" },
  { id: "rsi_reversion", label: "RSI Reversion" },
  { id: "bollinger_breakout", label: "Bollinger" },
  { id: "macd_momentum", label: "MACD" },
];

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  API Client
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async function post(endpoint, body = {}) {
  const r = await fetch(`${API}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `API ${r.status}`);
  }
  return r.json();
}

async function get(endpoint) {
  const r = await fetch(`${API}${endpoint}`);
  if (!r.ok) {
    const e = await r.json().catch(() => ({}));
    throw new Error(e.detail || `API ${r.status}`);
  }
  return r.json();
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Formatters
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const usd = (n) =>
  "$" +
  Math.abs(n ?? 0).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
const signedUsd = (n) => (n >= 0 ? "+" : "-") + usd(n);
const pct = (n) =>
  ((n ?? 0) >= 0 ? "+" : "") + ((n ?? 0) * 100).toFixed(2) + "%";
const num = (n, d = 2) => (n ?? 0).toFixed(d);

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Theme
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const C = {
  // Core background layers
  bg: "#06080d",
  surface: "#0c1017",
  card: "#111620",
  cardHover: "#161c28",
  border: "#1a2235",
  borderLight: "#243049",

  // Signal colors
  buy: "#00d4aa",
  buyDim: "#00d4aa30",
  sell: "#ff4976",
  sellDim: "#ff497630",
  hold: "#5e6e8a",
  holdDim: "#5e6e8a25",

  // Accent
  accent: "#4f8eff",
  accentDim: "#4f8eff25",

  // Status
  green: "#00d4aa",
  red: "#ff4976",
  yellow: "#ffb020",
  orange: "#ff8844",

  // Text
  text: "#e6eaf0",
  textSecondary: "#8896ab",
  textMuted: "#5a6878",

  // Sectors
  sectors: {
    Technology: "#8b5cf6",
    "Financial Services": "#4f8eff",
    Healthcare: "#00d4aa",
    Energy: "#ff8844",
    "Consumer Cyclical": "#ec4899",
    "Consumer Defensive": "#ffb020",
    Industrials: "#6366f1",
    "Communication Services": "#f43f5e",
    "Real Estate": "#14b8a6",
    Utilities: "#84cc16",
    "Basic Materials": "#d97706",
    Unknown: "#5a6878",
  },
};

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Primitives
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

const base = {
  fontFamily: "'JetBrains Mono', 'SF Mono', 'Fira Code', monospace",
};

function Card({ title, action, children, style = {} }) {
  return (
    <div
      style={{
        background: C.card,
        borderRadius: 8,
        border: `1px solid ${C.border}`,
        overflow: "hidden",
        ...style,
      }}
    >
      {(title || action) && (
        <div
          style={{
            padding: "10px 14px",
            borderBottom: `1px solid ${C.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: C.textSecondary,
              textTransform: "uppercase",
              letterSpacing: 1.2,
              ...base,
            }}
          >
            {title}
          </span>
          {action}
        </div>
      )}
      <div style={{ padding: 14 }}>{children}</div>
    </div>
  );
}

function SignalBadge({ signal, strength, size = "md" }) {
  const s = signal?.toUpperCase?.() || "HOLD";
  const color = s === "BUY" ? C.buy : s === "SELL" ? C.sell : C.hold;
  const bg = s === "BUY" ? C.buyDim : s === "SELL" ? C.sellDim : C.holdDim;
  const p = size === "sm" ? "2px 6px" : "3px 10px";
  const fs = size === "sm" ? 9 : 10;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        padding: p,
        background: bg,
        color,
        borderRadius: 4,
        fontSize: fs,
        fontWeight: 700,
        letterSpacing: 0.5,
        ...base,
      }}
    >
      {s === "BUY" ? "\u25B2" : s === "SELL" ? "\u25BC" : "\u25CF"} {s}
      {strength != null && (
        <span style={{ opacity: 0.7 }}>
          {" "}
          {(Math.abs(strength) * 100).toFixed(0)}%
        </span>
      )}
    </span>
  );
}

function Btn({ children, onClick, variant = "default", disabled, style = {} }) {
  const styles = {
    default: {
      background: C.cardHover,
      color: C.textSecondary,
      border: `1px solid ${C.border}`,
    },
    primary: { background: C.accent, color: "#fff", border: "none" },
    buy: { background: C.buy + "20", color: C.buy, border: `1px solid ${C.buy}40` },
    sell: {
      background: C.sell + "20",
      color: C.sell,
      border: `1px solid ${C.sell}40`,
    },
    danger: {
      background: C.red + "18",
      color: C.red,
      border: `1px solid ${C.red}30`,
    },
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "6px 12px",
        borderRadius: 5,
        fontSize: 11,
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: "all 0.15s",
        ...base,
        ...styles[variant],
        ...style,
      }}
    >
      {children}
    </button>
  );
}

function Spinner({ size = 20 }) {
  return (
    <div
      style={{
        width: size,
        height: size,
        border: `2px solid ${C.border}`,
        borderTop: `2px solid ${C.accent}`,
        borderRadius: "50%",
        animation: "spin 0.7s linear infinite",
        margin: "0 auto",
      }}
    />
  );
}

function EquityCurve({ data, width = 600, height = 100, showBenchmark }) {
  if (!data || data.length < 2) return null;
  const vals = data.map((d) => d.equity);
  const min = Math.min(...vals) * 0.998;
  const max = Math.max(...vals) * 1.002;
  const range = max - min || 1;
  const start = vals[0];
  const end = vals[vals.length - 1];
  const color = end >= start ? C.green : C.red;
  const pts = vals
    .map(
      (v, i) =>
        `${(i / (vals.length - 1)) * width},${height - ((v - min) / range) * (height - 8) - 4}`
    )
    .join(" ");
  // Baseline
  const baseY = height - ((start - min) / range) * (height - 8) - 4;
  return (
    <svg
      width="100%"
      viewBox={`0 0 ${width} ${height}`}
      style={{ display: "block" }}
    >
      <line
        x1={0}
        y1={baseY}
        x2={width}
        y2={baseY}
        stroke={C.border}
        strokeDasharray="4 4"
      />
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function MiniBar({ value, max = 1, color }) {
  const pctW = Math.min(100, (Math.abs(value) / max) * 100);
  return (
    <div
      style={{
        width: 50,
        height: 4,
        background: C.bg,
        borderRadius: 2,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          width: `${pctW}%`,
          height: "100%",
          background: color,
          borderRadius: 2,
        }}
      />
    </div>
  );
}

// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
//  Main App
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

export default function PortfolioGuard() {
  const [tab, setTab] = useState("signals");
  const [strategy, setStrategy] = useState("combined");

  // Data states
  const [watchlist, setWatchlist] = useState(null);
  const [portfolioData, setPortfolio] = useState(null);
  const [orders, setOrders] = useState([]);
  const [backtestResult, setBacktestResult] = useState(null);
  const [signalDetail, setSignalDetail] = useState(null);

  // UI states
  const [loading, setLoading] = useState({});
  const [error, setError] = useState(null);
  const [toast, setToast] = useState(null);

  // Backtest form
  const [btTickers, setBtTickers] = useState("AAPL,MSFT,GOOGL,NVDA,AMZN");
  const [btStrategy, setBtStrategy] = useState("combined");
  const [btDays, setBtDays] = useState(504);

  // Order form
  const [orderTicker, setOrderTicker] = useState("");
  const [orderQty, setOrderQty] = useState(10);

  const toastTimer = useRef(null);
  const showToast = (msg, type = "info") => {
    setToast({ msg, type });
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4000);
  };

  // ── Fetchers ──

  const fetchWatchlist = useCallback(async () => {
    setLoading((l) => ({ ...l, watchlist: true }));
    try {
      const data = await get(`/signals/watchlist?strategy=${strategy}`);
      setWatchlist(data);
    } catch (e) {
      setError(e.message);
    }
    setLoading((l) => ({ ...l, watchlist: false }));
  }, [strategy]);

  const fetchPortfolio = useCallback(async () => {
    setLoading((l) => ({ ...l, portfolio: true }));
    try {
      const [state, hist] = await Promise.all([
        get("/portfolio"),
        get("/portfolio/orders?limit=30"),
      ]);
      setPortfolio(state);
      setOrders(hist.orders || []);
    } catch (e) {
      console.error(e);
    }
    setLoading((l) => ({ ...l, portfolio: false }));
  }, []);

  const runBacktest = useCallback(async () => {
    setLoading((l) => ({ ...l, backtest: true }));
    setBacktestResult(null);
    try {
      const tickers = btTickers
        .split(",")
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean);
      const data = await post("/backtest", {
        tickers,
        strategy: btStrategy,
        initial_capital: 100000,
        lookback_days: btDays,
        commission_pct: 0.001,
        position_size_pct: 0.1,
      });
      setBacktestResult(data);
    } catch (e) {
      showToast(`Backtest failed: ${e.message}`, "error");
    }
    setLoading((l) => ({ ...l, backtest: false }));
  }, [btTickers, btStrategy, btDays]);

  const executeTrade = async (ticker, side) => {
    try {
      const body = { ticker, side, quantity: orderQty, reason: "Manual trade" };
      const result = await post("/trade/order", body);
      if (result.status === "REJECTED") {
        showToast(`Rejected: ${result.rejection_reason}`, "error");
      } else {
        showToast(`${side} ${orderQty} ${ticker} @ $${result.price}`, "success");
        fetchPortfolio();
      }
    } catch (e) {
      showToast(e.message, "error");
    }
  };

  const signalTrade = async (ticker) => {
    try {
      const result = await post(
        `/trade/signal-trade?ticker=${ticker}&strategy=${strategy}&shares=0`
      );
      if (result.order?.status === "FILLED") {
        showToast(
          `${result.order.side} ${result.order.quantity} ${ticker} @ $${result.order.price}`,
          "success"
        );
        fetchPortfolio();
      } else if (result.order?.status === "REJECTED") {
        showToast(`Rejected: ${result.order.rejection_reason}`, "error");
      } else {
        showToast(result.message || "No action taken", "info");
      }
    } catch (e) {
      showToast(e.message, "error");
    }
  };

  const resetPortfolio = async () => {
    await post("/portfolio/reset?initial_cash=100000");
    showToast("Portfolio reset to $100,000", "success");
    fetchPortfolio();
  };

  const fetchDetail = async (ticker) => {
    setLoading((l) => ({ ...l, detail: true }));
    try {
      const data = await get(`/signals/detail/${ticker}`);
      setSignalDetail(data);
    } catch (e) {
      showToast(`Failed to load ${ticker} detail`, "error");
    }
    setLoading((l) => ({ ...l, detail: false }));
  };

  // ── Effects ──
  useEffect(() => {
    fetchWatchlist();
    fetchPortfolio();
  }, [fetchWatchlist, fetchPortfolio]);

  useEffect(() => {
    fetchWatchlist();
  }, [strategy, fetchWatchlist]);

  // Poll portfolio every 60s
  useEffect(() => {
    const id = setInterval(fetchPortfolio, 60000);
    return () => clearInterval(id);
  }, [fetchPortfolio]);

  // ── Computed ──
  const pd = portfolioData;

  const TABS = [
    { id: "signals", label: "Signal Scanner", icon: "\u26A1" },
    { id: "portfolio", label: "Portfolio", icon: "\u2261" },
    { id: "trade", label: "Trade", icon: "\u2194" },
    { id: "backtest", label: "Backtest", icon: "\u27F3" },
  ];

  return (
    <div
      style={{
        background: C.bg,
        minHeight: "100vh",
        color: C.text,
        ...base,
      }}
    >
      {/* ── HEADER ── */}
      <header
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          padding: "0 20px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          height: 52,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 28,
              height: 28,
              borderRadius: 6,
              background: `linear-gradient(135deg, ${C.accent}, ${C.buy})`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 13,
              fontWeight: 800,
              color: "#000",
            }}
          >
            PG
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: -0.3 }}>
              PortfolioGuard
            </div>
            <div style={{ fontSize: 9, color: C.textMuted, letterSpacing: 1 }}>
              QUANTITATIVE TRADING
            </div>
          </div>
        </div>

        {pd && (
          <div style={{ display: "flex", gap: 20, alignItems: "center" }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 9, color: C.textMuted }}>EQUITY</div>
              <div style={{ fontSize: 14, fontWeight: 700 }}>
                {usd(pd.total_equity)}
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 9, color: C.textMuted }}>P&L</div>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: pd.total_pnl >= 0 ? C.green : C.red,
                }}
              >
                {signedUsd(pd.total_pnl)} ({pct(pd.total_pnl_pct)})
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 9, color: C.textMuted }}>CASH</div>
              <div style={{ fontSize: 13, fontWeight: 600, color: C.accent }}>
                {usd(pd.cash)}
              </div>
            </div>
            <div
              style={{
                width: 7,
                height: 7,
                borderRadius: "50%",
                background: C.green,
                boxShadow: `0 0 8px ${C.green}80`,
                animation: "pulse 2s infinite",
              }}
            />
          </div>
        )}
      </header>

      {/* ── NAV TABS ── */}
      <nav
        style={{
          background: C.surface,
          borderBottom: `1px solid ${C.border}`,
          display: "flex",
          gap: 0,
          padding: "0 20px",
        }}
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: "10px 16px",
              background: "none",
              border: "none",
              borderBottom:
                tab === t.id
                  ? `2px solid ${C.accent}`
                  : "2px solid transparent",
              color: tab === t.id ? C.text : C.textMuted,
              fontSize: 11,
              fontWeight: tab === t.id ? 700 : 500,
              cursor: "pointer",
              letterSpacing: 0.3,
              ...base,
            }}
          >
            {t.icon} {t.label}
          </button>
        ))}

        {/* Strategy selector */}
        <div
          style={{
            marginLeft: "auto",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <span style={{ fontSize: 9, color: C.textMuted }}>STRATEGY</span>
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value)}
            style={{
              background: C.cardHover,
              color: C.text,
              border: `1px solid ${C.border}`,
              borderRadius: 4,
              padding: "4px 8px",
              fontSize: 10,
              ...base,
            }}
          >
            {STRATEGIES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
        </div>
      </nav>

      {/* ── BODY ── */}
      <main style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
        {/* ═══ SIGNALS TAB ═══ */}
        {tab === "signals" && (
          <div style={{ display: "grid", gap: 14 }}>
            {/* Signal detail overlay */}
            {signalDetail && (
              <Card
                title={`${signalDetail.ticker} — ${signalDetail.name}`}
                action={
                  <div style={{ display: "flex", gap: 6 }}>
                    <Btn variant="buy" onClick={() => signalTrade(signalDetail.ticker)}>
                      Execute Signal
                    </Btn>
                    <Btn onClick={() => setSignalDetail(null)}>Close</Btn>
                  </div>
                }
              >
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
                  <div>
                    <div style={{ marginBottom: 10 }}>
                      <SignalBadge
                        signal={signalDetail.combined_signal.signal}
                        strength={signalDetail.combined_signal.strength}
                      />
                      <span
                        style={{
                          marginLeft: 8,
                          fontSize: 11,
                          color: C.textSecondary,
                        }}
                      >
                        {signalDetail.sector}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: C.textSecondary,
                        lineHeight: 1.6,
                        marginBottom: 12,
                      }}
                    >
                      {signalDetail.combined_signal.reason}
                    </div>

                    <div style={{ fontSize: 10, color: C.textMuted, marginBottom: 8 }}>
                      STRATEGY BREAKDOWN
                    </div>
                    {Object.entries(signalDetail.strategies).map(([k, v]) => (
                      <div
                        key={k}
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "5px 0",
                          borderBottom: `1px solid ${C.border}`,
                        }}
                      >
                        <span style={{ fontSize: 11, color: C.textSecondary }}>
                          {k.replace(/_/g, " ")}
                        </span>
                        <SignalBadge signal={v.signal} strength={v.strength} size="sm" />
                      </div>
                    ))}
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: C.textMuted, marginBottom: 6 }}>
                      120-DAY PRICE
                    </div>
                    {signalDetail.price_history && (
                      <EquityCurve
                        data={signalDetail.price_history.map((p) => ({
                          equity: p.close,
                        }))}
                        height={120}
                      />
                    )}
                    <div style={{ fontSize: 10, color: C.textMuted, marginTop: 10, marginBottom: 6 }}>
                      KEY INDICATORS
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                      {Object.entries(signalDetail.combined_signal.indicators || {})
                        .slice(0, 8)
                        .map(([k, v]) => (
                          <div
                            key={k}
                            style={{
                              padding: "4px 8px",
                              background: C.bg,
                              borderRadius: 4,
                            }}
                          >
                            <div style={{ fontSize: 9, color: C.textMuted }}>{k}</div>
                            <div style={{ fontSize: 12, fontWeight: 600, color: C.text }}>
                              {typeof v === "number" ? v.toFixed(3) : String(v)}
                            </div>
                          </div>
                        ))}
                    </div>
                  </div>
                </div>
              </Card>
            )}

            {/* Watchlist table */}
            <Card
              title={`Signal Scanner — ${STRATEGIES.find((s) => s.id === strategy)?.label || ""}`}
              action={
                <Btn onClick={fetchWatchlist} disabled={loading.watchlist}>
                  {loading.watchlist ? "Scanning..." : "\u27F3 Refresh"}
                </Btn>
              }
            >
              {loading.watchlist && !watchlist ? (
                <div style={{ padding: 40, textAlign: "center" }}>
                  <Spinner />
                  <div style={{ fontSize: 11, color: C.textMuted, marginTop: 10 }}>
                    Scanning 15 tickers across 4 strategies...
                  </div>
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: 12,
                    }}
                  >
                    <thead>
                      <tr>
                        {[
                          "Ticker",
                          "Name",
                          "Price",
                          "Change",
                          "Signal",
                          "RSI",
                          "MACD",
                          "BB %B",
                          "Sector",
                          "",
                        ].map((h) => (
                          <th
                            key={h}
                            style={{
                              padding: "8px 6px",
                              textAlign: "left",
                              fontSize: 9,
                              fontWeight: 600,
                              color: C.textMuted,
                              textTransform: "uppercase",
                              letterSpacing: 0.8,
                              borderBottom: `1px solid ${C.border}`,
                            }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(watchlist || []).map((w) => (
                        <tr
                          key={w.ticker}
                          style={{ cursor: "pointer" }}
                          onClick={() => fetchDetail(w.ticker)}
                          onMouseOver={(e) =>
                            (e.currentTarget.style.background = C.cardHover)
                          }
                          onMouseOut={(e) =>
                            (e.currentTarget.style.background = "")
                          }
                        >
                          <td
                            style={{
                              padding: "8px 6px",
                              fontWeight: 700,
                              color: C.accent,
                            }}
                          >
                            {w.ticker}
                          </td>
                          <td
                            style={{
                              padding: "8px 6px",
                              color: C.textSecondary,
                              maxWidth: 120,
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {w.name}
                          </td>
                          <td
                            style={{
                              padding: "8px 6px",
                              fontWeight: 600,
                            }}
                          >
                            ${num(w.price)}
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            <span
                              style={{
                                color: w.change_pct >= 0 ? C.green : C.red,
                                fontWeight: 600,
                              }}
                            >
                              {pct(w.change_pct)}
                            </span>
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            <SignalBadge
                              signal={w.signal}
                              strength={w.strength}
                              size="sm"
                            />
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            {w.rsi != null && (
                              <span
                                style={{
                                  color:
                                    w.rsi < 30
                                      ? C.green
                                      : w.rsi > 70
                                        ? C.red
                                        : C.textSecondary,
                                  fontWeight: 600,
                                }}
                              >
                                {num(w.rsi, 1)}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            {w.macd_histogram != null && (
                              <span
                                style={{
                                  color:
                                    w.macd_histogram > 0
                                      ? C.green
                                      : C.red,
                                }}
                              >
                                {w.macd_histogram > 0 ? "+" : ""}
                                {w.macd_histogram.toFixed(2)}
                              </span>
                            )}
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            {w.bb_position != null && (
                              <div
                                style={{
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 4,
                                }}
                              >
                                <MiniBar
                                  value={w.bb_position}
                                  max={1}
                                  color={
                                    w.bb_position < 0.2
                                      ? C.green
                                      : w.bb_position > 0.8
                                        ? C.red
                                        : C.accent
                                  }
                                />
                                <span
                                  style={{
                                    fontSize: 10,
                                    color: C.textMuted,
                                  }}
                                >
                                  {(w.bb_position * 100).toFixed(0)}%
                                </span>
                              </div>
                            )}
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            <span
                              style={{
                                padding: "1px 6px",
                                borderRadius: 3,
                                fontSize: 9,
                                background:
                                  (C.sectors[w.sector] || C.textMuted) + "18",
                                color: C.sectors[w.sector] || C.textMuted,
                              }}
                            >
                              {w.sector}
                            </span>
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            <Btn
                              variant={
                                w.signal === "BUY"
                                  ? "buy"
                                  : w.signal === "SELL"
                                    ? "sell"
                                    : "default"
                              }
                              onClick={(e) => {
                                e.stopPropagation();
                                signalTrade(w.ticker);
                              }}
                              disabled={w.signal === "HOLD"}
                              style={{ fontSize: 9, padding: "3px 8px" }}
                            >
                              {w.signal === "HOLD" ? "—" : "Execute"}
                            </Btn>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* ═══ PORTFOLIO TAB ═══ */}
        {tab === "portfolio" && (
          <div style={{ display: "grid", gap: 14 }}>
            {/* Summary cards */}
            {pd && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
                  gap: 10,
                }}
              >
                {[
                  {
                    label: "Total Equity",
                    value: usd(pd.total_equity),
                    color: C.text,
                  },
                  {
                    label: "Total P&L",
                    value: signedUsd(pd.total_pnl),
                    color: pd.total_pnl >= 0 ? C.green : C.red,
                    sub: pct(pd.total_pnl_pct),
                  },
                  {
                    label: "Day P&L",
                    value: signedUsd(pd.day_pnl),
                    color: pd.day_pnl >= 0 ? C.green : C.red,
                  },
                  {
                    label: "Buying Power",
                    value: usd(pd.buying_power),
                    color: C.accent,
                  },
                  {
                    label: "Positions",
                    value: pd.num_positions,
                    color: C.text,
                  },
                  {
                    label: "Invested",
                    value: usd(pd.positions_value),
                    color: C.textSecondary,
                  },
                ].map((m, i) => (
                  <Card key={i}>
                    <div style={{ fontSize: 9, color: C.textMuted }}>{m.label}</div>
                    <div
                      style={{
                        fontSize: 18,
                        fontWeight: 700,
                        color: m.color,
                        marginTop: 2,
                      }}
                    >
                      {m.value}
                    </div>
                    {m.sub && (
                      <div
                        style={{
                          fontSize: 11,
                          color: m.color,
                          opacity: 0.7,
                        }}
                      >
                        {m.sub}
                      </div>
                    )}
                  </Card>
                ))}
              </div>
            )}

            {/* Positions table */}
            <Card
              title={`Open Positions (${pd?.num_positions || 0})`}
              action={
                <Btn variant="danger" onClick={resetPortfolio} style={{ fontSize: 9 }}>
                  Reset Account
                </Btn>
              }
            >
              {pd?.positions?.length === 0 ? (
                <div
                  style={{
                    textAlign: "center",
                    padding: 40,
                    color: C.textMuted,
                    fontSize: 12,
                  }}
                >
                  No open positions. Use the Signal Scanner or Trade tab to
                  enter positions.
                </div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: 12,
                    }}
                  >
                    <thead>
                      <tr>
                        {[
                          "Ticker",
                          "Qty",
                          "Avg Cost",
                          "Price",
                          "Value",
                          "P&L",
                          "P&L %",
                          "Weight",
                          "",
                        ].map((h) => (
                          <th
                            key={h}
                            style={{
                              padding: "8px 6px",
                              textAlign: "left",
                              fontSize: 9,
                              color: C.textMuted,
                              fontWeight: 600,
                              letterSpacing: 0.8,
                              textTransform: "uppercase",
                              borderBottom: `1px solid ${C.border}`,
                            }}
                          >
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(pd?.positions || []).map((p) => (
                        <tr key={p.ticker}>
                          <td
                            style={{
                              padding: "8px 6px",
                              fontWeight: 700,
                              color: C.accent,
                            }}
                          >
                            {p.ticker}
                          </td>
                          <td style={{ padding: "8px 6px" }}>{p.quantity}</td>
                          <td style={{ padding: "8px 6px" }}>
                            ${num(p.avg_cost)}
                          </td>
                          <td style={{ padding: "8px 6px", fontWeight: 600 }}>
                            ${num(p.current_price)}
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            {usd(p.market_value)}
                          </td>
                          <td
                            style={{
                              padding: "8px 6px",
                              fontWeight: 700,
                              color:
                                p.unrealized_pnl >= 0 ? C.green : C.red,
                            }}
                          >
                            {signedUsd(p.unrealized_pnl)}
                          </td>
                          <td
                            style={{
                              padding: "8px 6px",
                              color:
                                p.unrealized_pnl_pct >= 0 ? C.green : C.red,
                            }}
                          >
                            {pct(p.unrealized_pnl_pct)}
                          </td>
                          <td style={{ padding: "8px 6px", color: C.textSecondary }}>
                            {(p.weight * 100).toFixed(1)}%
                          </td>
                          <td style={{ padding: "8px 6px" }}>
                            <Btn
                              variant="sell"
                              onClick={() => {
                                executeTrade(p.ticker, "SELL");
                              }}
                              style={{ fontSize: 9, padding: "3px 8px" }}
                            >
                              Close
                            </Btn>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            {/* Order history */}
            <Card title="Recent Orders">
              {orders.length === 0 ? (
                <div
                  style={{
                    textAlign: "center",
                    padding: 24,
                    color: C.textMuted,
                    fontSize: 11,
                  }}
                >
                  No orders yet
                </div>
              ) : (
                <div style={{ maxHeight: 250, overflowY: "auto" }}>
                  {orders.map((o, i) => (
                    <div
                      key={i}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        padding: "6px 0",
                        borderBottom: `1px solid ${C.border}`,
                        fontSize: 11,
                      }}
                    >
                      <span
                        style={{
                          fontWeight: 700,
                          color: o.side === "BUY" ? C.buy : C.sell,
                          width: 34,
                        }}
                      >
                        {o.side}
                      </span>
                      <span
                        style={{ fontWeight: 600, color: C.accent, width: 48 }}
                      >
                        {o.ticker}
                      </span>
                      <span style={{ color: C.textSecondary, width: 40 }}>
                        x{o.quantity}
                      </span>
                      <span style={{ color: C.text, width: 70 }}>
                        @ ${num(o.price)}
                      </span>
                      <span
                        style={{
                          fontSize: 10,
                          padding: "1px 6px",
                          borderRadius: 3,
                          background:
                            o.status === "FILLED"
                              ? C.green + "20"
                              : C.red + "20",
                          color:
                            o.status === "FILLED" ? C.green : C.red,
                        }}
                      >
                        {o.status}
                      </span>
                      <span
                        style={{
                          marginLeft: "auto",
                          fontSize: 9,
                          color: C.textMuted,
                        }}
                      >
                        {o.timestamp?.slice(11, 19)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>
        )}

        {/* ═══ TRADE TAB ═══ */}
        {tab === "trade" && (
          <div style={{ display: "grid", gap: 14 }}>
            <Card title="Place Order">
              <div
                style={{
                  display: "flex",
                  gap: 10,
                  alignItems: "flex-end",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      color: C.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    TICKER
                  </div>
                  <input
                    value={orderTicker}
                    onChange={(e) => setOrderTicker(e.target.value.toUpperCase())}
                    placeholder="AAPL"
                    style={{
                      background: C.bg,
                      color: C.text,
                      border: `1px solid ${C.border}`,
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 12,
                      width: 80,
                      ...base,
                    }}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      color: C.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    QUANTITY
                  </div>
                  <input
                    type="number"
                    value={orderQty}
                    onChange={(e) => setOrderQty(parseInt(e.target.value) || 1)}
                    style={{
                      background: C.bg,
                      color: C.text,
                      border: `1px solid ${C.border}`,
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 12,
                      width: 70,
                      ...base,
                    }}
                  />
                </div>
                <Btn
                  variant="buy"
                  onClick={() => executeTrade(orderTicker, "BUY")}
                  disabled={!orderTicker}
                  style={{ padding: "7px 20px" }}
                >
                  \u25B2 BUY
                </Btn>
                <Btn
                  variant="sell"
                  onClick={() => executeTrade(orderTicker, "SELL")}
                  disabled={!orderTicker}
                  style={{ padding: "7px 20px" }}
                >
                  \u25BC SELL
                </Btn>
              </div>
            </Card>

            <Card title="Quick Trade from Signals">
              <div
                style={{
                  fontSize: 11,
                  color: C.textSecondary,
                  marginBottom: 12,
                }}
              >
                Click a ticker to auto-execute based on the current signal.
                Position auto-sizes to 10% of equity.
              </div>
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: 6,
                }}
              >
                {(watchlist || [])
                  .filter((w) => w.signal !== "HOLD")
                  .map((w) => (
                    <Btn
                      key={w.ticker}
                      variant={w.signal === "BUY" ? "buy" : "sell"}
                      onClick={() => signalTrade(w.ticker)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "6px 12px",
                      }}
                    >
                      <span style={{ fontWeight: 700 }}>{w.ticker}</span>
                      <SignalBadge
                        signal={w.signal}
                        strength={w.strength}
                        size="sm"
                      />
                    </Btn>
                  ))}
                {watchlist &&
                  watchlist.filter((w) => w.signal !== "HOLD").length === 0 && (
                    <div
                      style={{
                        padding: 20,
                        color: C.textMuted,
                        fontSize: 11,
                      }}
                    >
                      No actionable signals right now
                    </div>
                  )}
              </div>
            </Card>
          </div>
        )}

        {/* ═══ BACKTEST TAB ═══ */}
        {tab === "backtest" && (
          <div style={{ display: "grid", gap: 14 }}>
            <Card title="Backtest Configuration">
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-end",
                  flexWrap: "wrap",
                }}
              >
                <div style={{ flex: 1, minWidth: 200 }}>
                  <div
                    style={{
                      fontSize: 9,
                      color: C.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    TICKERS (comma-separated)
                  </div>
                  <input
                    value={btTickers}
                    onChange={(e) => setBtTickers(e.target.value.toUpperCase())}
                    style={{
                      width: "100%",
                      background: C.bg,
                      color: C.text,
                      border: `1px solid ${C.border}`,
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 11,
                      ...base,
                    }}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      color: C.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    STRATEGY
                  </div>
                  <select
                    value={btStrategy}
                    onChange={(e) => setBtStrategy(e.target.value)}
                    style={{
                      background: C.bg,
                      color: C.text,
                      border: `1px solid ${C.border}`,
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 11,
                      ...base,
                    }}
                  >
                    {STRATEGIES.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 9,
                      color: C.textMuted,
                      marginBottom: 4,
                    }}
                  >
                    LOOKBACK (days)
                  </div>
                  <input
                    type="number"
                    value={btDays}
                    onChange={(e) => setBtDays(parseInt(e.target.value) || 252)}
                    style={{
                      width: 80,
                      background: C.bg,
                      color: C.text,
                      border: `1px solid ${C.border}`,
                      borderRadius: 4,
                      padding: "6px 10px",
                      fontSize: 11,
                      ...base,
                    }}
                  />
                </div>
                <Btn
                  variant="primary"
                  onClick={runBacktest}
                  disabled={loading.backtest}
                  style={{ padding: "7px 24px" }}
                >
                  {loading.backtest ? "Running..." : "\u25B6 Run Backtest"}
                </Btn>
              </div>
            </Card>

            {loading.backtest && (
              <Card>
                <div style={{ textAlign: "center", padding: 40 }}>
                  <Spinner size={28} />
                  <div
                    style={{
                      fontSize: 11,
                      color: C.textMuted,
                      marginTop: 12,
                    }}
                  >
                    Running backtest... processing{" "}
                    {btTickers.split(",").length} tickers over {btDays} days
                  </div>
                </div>
              </Card>
            )}

            {backtestResult && (
              <>
                {/* Metrics */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fit, minmax(130px, 1fr))",
                    gap: 8,
                  }}
                >
                  {[
                    {
                      label: "Total Return",
                      value: pct(backtestResult.total_return),
                      color:
                        backtestResult.total_return >= 0 ? C.green : C.red,
                    },
                    {
                      label: "Ann. Return",
                      value: pct(backtestResult.annualized_return),
                      color:
                        backtestResult.annualized_return >= 0
                          ? C.green
                          : C.red,
                    },
                    {
                      label: "Sharpe Ratio",
                      value: num(backtestResult.sharpe_ratio),
                      color:
                        backtestResult.sharpe_ratio > 1 ? C.green : C.yellow,
                    },
                    {
                      label: "Sortino Ratio",
                      value: num(backtestResult.sortino_ratio),
                      color:
                        backtestResult.sortino_ratio > 1.5
                          ? C.green
                          : C.yellow,
                    },
                    {
                      label: "Max Drawdown",
                      value: pct(backtestResult.max_drawdown),
                      color: C.red,
                    },
                    {
                      label: "Win Rate",
                      value: (backtestResult.win_rate * 100).toFixed(1) + "%",
                      color:
                        backtestResult.win_rate > 0.5 ? C.green : C.yellow,
                    },
                    {
                      label: "Profit Factor",
                      value: num(backtestResult.profit_factor),
                      color:
                        backtestResult.profit_factor > 1 ? C.green : C.red,
                    },
                    {
                      label: "Benchmark",
                      value: pct(backtestResult.benchmark_return),
                      color: C.accent,
                    },
                    {
                      label: "Total Trades",
                      value: backtestResult.total_trades,
                      color: C.text,
                    },
                    {
                      label: "Avg Win",
                      value: usd(backtestResult.avg_win),
                      color: C.green,
                    },
                    {
                      label: "Avg Loss",
                      value: usd(Math.abs(backtestResult.avg_loss)),
                      color: C.red,
                    },
                  ].map((m, i) => (
                    <Card key={i}>
                      <div style={{ fontSize: 9, color: C.textMuted }}>
                        {m.label}
                      </div>
                      <div
                        style={{
                          fontSize: 16,
                          fontWeight: 700,
                          color: m.color,
                          marginTop: 2,
                        }}
                      >
                        {m.value}
                      </div>
                    </Card>
                  ))}
                </div>

                {/* Equity curve */}
                <Card title="Equity Curve">
                  <EquityCurve
                    data={backtestResult.equity_curve}
                    height={150}
                  />
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      marginTop: 6,
                    }}
                  >
                    <span style={{ fontSize: 9, color: C.textMuted }}>
                      {backtestResult.equity_curve[0]?.date}
                    </span>
                    <span style={{ fontSize: 9, color: C.textMuted }}>
                      {
                        backtestResult.equity_curve[
                          backtestResult.equity_curve.length - 1
                        ]?.date
                      }
                    </span>
                  </div>
                </Card>

                {/* Monthly returns */}
                {backtestResult.monthly_returns?.length > 0 && (
                  <Card title="Monthly Returns">
                    <div
                      style={{
                        display: "flex",
                        flexWrap: "wrap",
                        gap: 4,
                      }}
                    >
                      {backtestResult.monthly_returns.map((m) => (
                        <div
                          key={m.month}
                          style={{
                            padding: "4px 8px",
                            borderRadius: 4,
                            background:
                              m.return >= 0
                                ? C.green + Math.min(60, Math.round(Math.abs(m.return) * 600)).toString(16).padStart(2, "0")
                                : C.red + Math.min(60, Math.round(Math.abs(m.return) * 600)).toString(16).padStart(2, "0"),
                            fontSize: 10,
                            color: C.text,
                            textAlign: "center",
                            minWidth: 52,
                          }}
                        >
                          <div style={{ fontSize: 8, opacity: 0.7 }}>
                            {m.month}
                          </div>
                          <div style={{ fontWeight: 600 }}>
                            {pct(m.return)}
                          </div>
                        </div>
                      ))}
                    </div>
                  </Card>
                )}

                {/* Trade log */}
                <Card title={`Trade Log (${backtestResult.trades.length} shown)`}>
                  <div style={{ maxHeight: 250, overflowY: "auto" }}>
                    {backtestResult.trades.map((t, i) => (
                      <div
                        key={i}
                        style={{
                          display: "flex",
                          gap: 10,
                          alignItems: "center",
                          padding: "4px 0",
                          borderBottom: `1px solid ${C.border}`,
                          fontSize: 11,
                        }}
                      >
                        <span
                          style={{
                            fontSize: 10,
                            color: C.textMuted,
                            width: 70,
                          }}
                        >
                          {t.date}
                        </span>
                        <span
                          style={{
                            fontWeight: 700,
                            color: t.side === "BUY" ? C.buy : C.sell,
                            width: 34,
                          }}
                        >
                          {t.side}
                        </span>
                        <span
                          style={{
                            fontWeight: 600,
                            color: C.accent,
                            width: 50,
                          }}
                        >
                          {t.ticker}
                        </span>
                        <span style={{ color: C.textSecondary, width: 40 }}>
                          x{t.quantity}
                        </span>
                        <span style={{ color: C.text, width: 65 }}>
                          @ ${num(t.price)}
                        </span>
                        {t.side === "SELL" && (
                          <span
                            style={{
                              fontWeight: 700,
                              color: t.pnl >= 0 ? C.green : C.red,
                            }}
                          >
                            {signedUsd(t.pnl)}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              </>
            )}
          </div>
        )}
      </main>

      {/* ── Toast ── */}
      {toast && (
        <div
          style={{
            position: "fixed",
            bottom: 20,
            right: 20,
            padding: "10px 18px",
            borderRadius: 8,
            background:
              toast.type === "error"
                ? C.red + "20"
                : toast.type === "success"
                  ? C.green + "20"
                  : C.accent + "20",
            border: `1px solid ${
              toast.type === "error"
                ? C.red + "40"
                : toast.type === "success"
                  ? C.green + "40"
                  : C.accent + "40"
            }`,
            color:
              toast.type === "error"
                ? C.red
                : toast.type === "success"
                  ? C.green
                  : C.accent,
            fontSize: 12,
            fontWeight: 600,
            zIndex: 1000,
            animation: "fadeIn 0.2s ease",
            ...base,
          }}
        >
          {toast.type === "success" ? "\u2713" : toast.type === "error" ? "\u2717" : "\u2139"}{" "}
          {toast.msg}
        </div>
      )}

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: ${C.bg}; }
        ::-webkit-scrollbar-thumb { background: ${C.border}; border-radius: 3px; }
        ::-webkit-scrollbar-thumb:hover { background: ${C.borderLight}; }
        input:focus, select:focus { outline: 1px solid ${C.accent}; }
      `}</style>
    </div>
  );
}
