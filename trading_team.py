"""
AI Trading Team — Streamlit App
Real market data from Massive/Polygon API feeds 5 Grok AI agents
for swing trade analysis with precise entry prices and stops.
"""

import streamlit as st
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Trading Team",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  html, body, [class*="css"] { background-color: #020817 !important; color: #f1f5f9 !important; }
  .stApp { background-color: #020817; }
  .header-label { font-family: monospace; font-size: 11px; letter-spacing: 3px; color: #00d4ff; text-align: center; margin-bottom: 4px; }
  .header-title { font-size: 30px; font-weight: 800; text-align: center; color: #f1f5f9; }
  .header-sub   { font-size: 13px; color: #475569; text-align: center; margin-top: 4px; margin-bottom: 24px; }
  div[data-testid="stTextArea"] textarea { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; font-family: monospace !important; font-size: 13px !important; }
  div[data-testid="stSelectbox"] > div  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  div[data-testid="stTextInput"] input  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  .stButton > button { width:100%; background:transparent !important; border:1px solid #00d4ff44 !important; color:#00d4ff !important; font-family:monospace !important; font-weight:700 !important; letter-spacing:1px !important; font-size:14px !important; padding:12px !important; border-radius:8px !important; }
  .stButton > button:hover { background:#00d4ff11 !important; border-color:#00d4ff !important; }
</style>
""", unsafe_allow_html=True)

GRADE_COLORS = {"A+": "#10b981", "A": "#22c55e", "B+": "#84cc16", "B": "#eab308", "C": "#f97316"}

# ══════════════════════════════════════════════════════════════════════════════
# MASSIVE / POLYGON MARKET DATA
# ══════════════════════════════════════════════════════════════════════════════

def massive_get(path, poly_key):
    url = f"https://api.polygon.io{path}"
    sep = "&" if "?" in url else "?"
    url = url + sep + f"apiKey={poly_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradingTeam/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())

def fetch_ticker_data(ticker, poly_key):
    result = {"ticker": ticker, "error": None}
    try:
        # Snapshot
        snap = massive_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", poly_key)
        t    = snap.get("ticker", {})
        day  = t.get("day", {})
        prev = t.get("prevDay", {})
        result["price"]      = day.get("c") or prev.get("c", 0)
        result["open"]       = day.get("o", 0)
        result["high"]       = day.get("h", 0)
        result["low"]        = day.get("l", 0)
        result["volume"]     = day.get("v", 0)
        result["prev_close"] = prev.get("c", 0)
        result["change_pct"] = round(
            ((result["price"] - result["prev_close"]) / result["prev_close"] * 100)
            if result["prev_close"] else 0, 2)

        # Daily bars 90 days
        end   = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")
        bars  = massive_get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=100",
            poly_key)
        rb     = bars.get("results", [])
        closes = [b["c"] for b in rb]
        highs  = [b["h"] for b in rb]
        lows   = [b["l"] for b in rb]
        vols   = [b["v"] for b in rb]

        result["high_52w"]   = round(max(highs), 2) if highs else 0
        result["low_52w"]    = round(min(lows),  2) if lows  else 0
        result["avg_vol_20"] = round(sum(vols[-20:]) / min(20, len(vols)), 0) if vols else 0
        result["rvol"]       = round(result["volume"] / result["avg_vol_20"], 2) if result["avg_vol_20"] else 0

        # ATR(14)
        if len(rb) >= 15:
            trs = []
            for i in range(1, min(15, len(rb))):
                h, l, pc = highs[i], lows[i], closes[i-1]
                trs.append(max(h - l, abs(h - pc), abs(l - pc)))
            result["atr14"] = round(sum(trs) / len(trs), 2)
        else:
            result["atr14"] = round(result["price"] * 0.02, 2)

        # EMA
        def ema(prices, period):
            if len(prices) < period:
                return None
            k = 2 / (period + 1)
            e = sum(prices[:period]) / period
            for p in prices[period:]:
                e = p * k + e * (1 - k)
            return round(e, 2)

        result["ema10"] = ema(closes, 10)
        result["ema21"] = ema(closes, 21)
        result["ema50"] = ema(closes, 50)

        p   = result["price"]
        e10 = result["ema10"]
        e21 = result["ema21"]
        e50 = result["ema50"]

        if e10 and e21 and e50:
            if p > e10 > e21 > e50:
                result["ema_alignment"] = "Bullish stack (10>21>50)"
            elif p < e10 < e21 < e50:
                result["ema_alignment"] = "Bearish stack"
            elif p > e21 > e50:
                result["ema_alignment"] = "Bullish (above 21 & 50)"
            elif p < e21:
                result["ema_alignment"] = "Bearish (below 21)"
            else:
                result["ema_alignment"] = "Mixed"
        else:
            result["ema_alignment"] = "Insufficient data"

        if e50:
            if p > e50 and e10 and e10 > e50:
                result["stage"] = "Stage 2 (Uptrend)"
            elif p < e50 and e10 and e10 < e50:
                result["stage"] = "Stage 4 (Downtrend)"
            elif p > e50:
                result["stage"] = "Stage 1/2"
            else:
                result["stage"] = "Stage 3/4"
        else:
            result["stage"] = "Unknown"

        # RSI(14)
        if len(closes) >= 15:
            gains, losses = [], []
            for i in range(1, 15):
                d = closes[-14 + i] - closes[-15 + i]
                (gains if d > 0 else losses).append(abs(d))
            ag = sum(gains) / 14
            al = sum(losses) / 14
            result["rsi14"] = round(100 - (100 / (1 + ag / al)), 1) if al else 100.0
        else:
            result["rsi14"] = None

        result["pct_from_high"] = round((p - result["high_52w"]) / result["high_52w"] * 100, 1) if result["high_52w"] else 0

        # VCP contraction
        if len(highs) >= 20:
            r1 = max(highs[-20:-10]) - min(lows[-20:-10])
            r2 = max(highs[-10:-5])  - min(lows[-10:-5])
            r3 = max(highs[-5:])     - min(lows[-5:])
            result["vcp_contracting"] = bool(r1 > r2 > r3)
            result["vcp_ranges"]      = [round(r1,2), round(r2,2), round(r3,2)]
        else:
            result["vcp_contracting"] = False
            result["vcp_ranges"]      = []

    except Exception as e:
        result["error"] = str(e)
    return result

def market_data_summary(market_data):
    lines = []
    for ticker, d in market_data.items():
        if d.get("error"):
            lines.append(f"{ticker}: ERROR — {d['error']}")
            continue
        lines.append(
            f"{ticker}: price=${d['price']} chg={d['change_pct']}% | "
            f"EMA10={d['ema10']} EMA21={d['ema21']} EMA50={d['ema50']} | "
            f"alignment={d['ema_alignment']} | stage={d['stage']} | "
            f"RSI={d['rsi14']} | ATR14={d['atr14']} | RVol={d['rvol']}x | "
            f"52wH={d['high_52w']} ({d['pct_from_high']}% from high) | "
            f"VCP_contracting={d['vcp_contracting']} ranges={d['vcp_ranges']}"
        )
    return "\n".join(lines)

# ══════════════════════════════════════════════════════════════════════════════
# AGENTS
# ══════════════════════════════════════════════════════════════════════════════

AGENTS = [
    {
        "id": "scanner", "name": "Market Scanner", "role": "Ranks candidates by setup quality",
        "icon": "🔭", "color": "#00d4ff",
        "system": """You are a Market Scanner. You receive REAL live market data.
Use actual prices, EMAs, RSI, RVol, stage, and VCP data to rank stocks by swing trade setup quality.
Select top 3-5. Prioritize: Stage 2, bullish EMA stack, RSI 50-70, VCP contracting, RVol > 1.
Return ONLY valid JSON:
{"candidates":[{"ticker":"AAPL","price":185.50,"stage":"Stage 2 (Uptrend)","ema_alignment":"Bullish stack (10>21>50)","rsi":62.3,"rvol":1.4,"vcp_contracting":true,"setup":"VCP base tightening","conviction":"High","rank_reason":"Why ranked here"}],"market_context":"One sentence on market conditions"}"""
    },
    {
        "id": "technicals", "name": "Technical Analyst", "role": "Entry levels using real prices",
        "icon": "📈", "color": "#7c3aed",
        "system": """You are a Technical Analyst. You have REAL price data: ATR, EMAs, 52w high, VCP ranges.
Entry = pivot (recent consolidation high) + 0.1 * ATR14.
Stop = below 21 EMA or 1.5x ATR below entry (tighter).
Return ONLY valid JSON:
{"analysis":[{"ticker":"AAPL","current_price":185.50,"atr14":3.20,"pivot_price":187.00,"entry_price":187.32,"entry_zone":"187.00 - 187.50","stop_loss":183.80,"key_resistance":192.00,"key_support":181.00,"ema21":182.40,"setup_quality":"A+","pattern":"VCP breakout","notes":"Specific observation from real data"}]}"""
    },
    {
        "id": "risk", "name": "Risk Manager", "role": "Position sizing from real prices",
        "icon": "🛡️", "color": "#f59e0b",
        "system": """You are a Risk Manager. Use REAL entry/stop prices to calculate R:R and sizing.
Min 2:1 R:R. Target1 = entry + 2x risk. Target2 = entry + 3.5x risk.
Position size for $1000 risk = floor(1000 / risk_per_share).
Return ONLY valid JSON:
{"risk_plans":[{"ticker":"AAPL","entry":187.32,"stop_loss":183.80,"risk_per_share":3.52,"target_1":194.36,"target_2":199.64,"reward_risk_ratio":"2.0:1","position_size_1k_risk":284,"stop_rationale":"Below 21 EMA buffer","invalidation":"Daily close below 183.50"}]}"""
    },
    {
        "id": "sentiment", "name": "Sentiment Analyst", "role": "Macro context + momentum signals",
        "icon": "🌊", "color": "#10b981",
        "system": """You are a Sentiment Analyst. Use real RSI, RVol, % from 52w high, price change data.
Return ONLY valid JSON:
{"sentiment":{"market_phase":"Risk-On","breadth":"Expanding","vix_regime":"Low (<20)","sector_leaders":["Technology"],"avoid_sectors":["Utilities"]},"stock_sentiment":[{"ticker":"AAPL","momentum":"Strong","rsi_signal":"Bullish, not overbought","rvol_signal":"Accumulation","pct_from_high":"-2.1%","institutional_bias":"Accumulation","earnings_risk":"Low","sentiment_score":8}]}"""
    },
    {
        "id": "strategist", "name": "Head Strategist", "role": "Final trade cards with real prices",
        "icon": "🎯", "color": "#ef4444",
        "system": """You are the Head Strategist. Use EXACT prices from technical and risk agents — do not invent numbers.
Return ONLY valid JSON:
{"recommendations":[{"rank":1,"ticker":"AAPL","action":"BUY","buy_price":187.32,"stop_loss":183.80,"target_1":194.36,"target_2":199.64,"holding_period":"5-15 days","strategy":"VCP breakout swing","conviction":"High","grade":"A+","rationale":"Two sentences using real data points.","entry_trigger":"Buy above 187.00 pivot on volume > 1.5x 20-day average","key_risk":"Specific risk from chart structure"}],"portfolio_notes":"Correlation and sizing note"}"""
    },
]

# ══════════════════════════════════════════════════════════════════════════════
# GROK API
# ══════════════════════════════════════════════════════════════════════════════

def call_grok(api_key, system, user_msg):
    payload = json.dumps({
        "model": "grok-3",
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_msg}
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    raw = data["choices"][0]["message"]["content"].strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def agent_row(agent, status, note=""):
    icons  = {"idle": "○", "running": "●", "done": "✓", "error": "✗"}
    colors = {"idle": "#475569", "running": agent["color"], "done": "#10b981", "error": "#ef4444"}
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            f"<div style='font-family:monospace;font-size:13px;color:{colors[status]};padding:4px 0'>"
            f"{agent['icon']} <b>{agent['name']}</b> "
            f"<span style='color:#475569;font-size:11px;'>— {agent['role']}</span></div>",
            unsafe_allow_html=True)
    with c2:
        st.markdown(
            f"<div style='font-family:monospace;font-size:11px;color:{colors[status]};text-align:right;padding:4px 0'>"
            f"{icons[status]} {status.upper()}</div>",
            unsafe_allow_html=True)
    if note:
        st.markdown(
            f"<div style='color:#475569;font-size:11px;font-family:monospace;padding-left:26px;margin-bottom:2px'>{note}</div>",
            unsafe_allow_html=True)

def market_data_table(market_data):
    rows = ""
    for t, d in market_data.items():
        if d.get("error"):
            rows += f"<tr><td style='color:#ef4444;font-family:monospace'>{t}</td><td colspan='7' style='color:#475569;font-size:11px;'>Error: {d['error']}</td></tr>"
            continue
        chg_c  = "#10b981" if d["change_pct"] >= 0 else "#ef4444"
        rvol_c = "#10b981" if d.get("rvol", 0) >= 1.5 else "#94a3b8"
        vcp    = "✓ VCP" if d.get("vcp_contracting") else "—"
        vcp_c  = "#10b981" if d.get("vcp_contracting") else "#475569"
        rows += (
            f"<tr>"
            f"<td style='color:#f1f5f9;font-weight:700;font-family:monospace;padding:5px 8px'>{t}</td>"
            f"<td style='color:#00d4ff;font-family:monospace;padding:5px 8px'>${d['price']}</td>"
            f"<td style='color:{chg_c};font-family:monospace;padding:5px 8px'>{d['change_pct']:+.2f}%</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d['ema_alignment']}</td>"
            f"<td style='color:#94a3b8;font-family:monospace;padding:5px 8px'>{d['rsi14']}</td>"
            f"<td style='color:{rvol_c};font-family:monospace;padding:5px 8px'>{d['rvol']}x</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d['stage']}</td>"
            f"<td style='color:{vcp_c};font-size:11px;padding:5px 8px'>{vcp}</td>"
            f"</tr>"
        )
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-bottom:16px;overflow-x:auto;'>
      <div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>LIVE MARKET DATA — MASSIVE/POLYGON</div>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='color:#475569;font-size:10px;letter-spacing:1px;border-bottom:1px solid #1e293b;'>
          <th style='text-align:left;padding:4px 8px;'>TICKER</th>
          <th style='text-align:left;padding:4px 8px;'>PRICE</th>
          <th style='text-align:left;padding:4px 8px;'>CHG%</th>
          <th style='text-align:left;padding:4px 8px;'>EMA ALIGNMENT</th>
          <th style='text-align:left;padding:4px 8px;'>RSI</th>
          <th style='text-align:left;padding:4px 8px;'>RVOL</th>
          <th style='text-align:left;padding:4px 8px;'>STAGE</th>
          <th style='text-align:left;padding:4px 8px;'>VCP</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>""", unsafe_allow_html=True)

def trade_card(trade):
    grade = trade.get("grade", "B")
    color = GRADE_COLORS.get(grade, "#64748b")
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-left:3px solid {color};border-radius:10px;padding:18px;margin-bottom:14px;'>
      <div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;'>
        <div style='display:flex;align-items:center;gap:10px;'>
          <span style='background:{color};color:#000;border-radius:5px;padding:1px 8px;font-size:11px;font-weight:800;font-family:monospace;'>#{trade.get("rank","")}</span>
          <span style='color:#f1f5f9;font-size:20px;font-weight:800;font-family:monospace;'>{trade.get("ticker","")}</span>
          <span style='background:#10b98122;color:#10b981;border:1px solid #10b98144;border-radius:4px;padding:1px 8px;font-size:11px;font-weight:700;'>{trade.get("action","BUY")}</span>
        </div>
        <span style='background:{color}22;color:{color};border:1px solid {color}44;border-radius:6px;padding:2px 12px;font-size:14px;font-weight:800;font-family:monospace;'>{grade}</span>
      </div>
      <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;'>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'>
          <div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>BUY AT</div>
          <div style='color:#00d4ff;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("buy_price","")}</div>
        </div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'>
          <div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>STOP</div>
          <div style='color:#ef4444;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("stop_loss","")}</div>
        </div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'>
          <div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>TARGET 1</div>
          <div style='color:#10b981;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("target_1","")}</div>
        </div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'>
          <div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>TARGET 2</div>
          <div style='color:#10b981;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("target_2","")}</div>
        </div>
      </div>
      <div style='background:#1e293b;border-radius:6px;padding:10px 12px;margin-bottom:10px;'>
        <div style='color:#00d4ff;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:4px;'>ENTRY TRIGGER</div>
        <div style='color:#cbd5e1;font-size:13px;'>{trade.get("entry_trigger","")}</div>
      </div>
      <div style='color:#94a3b8;font-size:13px;line-height:1.6;margin-bottom:10px;'>{trade.get("rationale","")}</div>
      <div>
        <span style='background:#1e293b;color:#64748b;border-radius:4px;padding:2px 8px;font-size:11px;margin-right:6px;'>⏱ {trade.get("holding_period","")}</span>
        <span style='background:#1e293b;color:#64748b;border-radius:4px;padding:2px 8px;font-size:11px;margin-right:6px;'>📊 {trade.get("strategy","")}</span>
        <span style='background:#1e293b;color:#f59e0b;border-radius:4px;padding:2px 8px;font-size:11px;'>⚠ {trade.get("key_risk","")}</span>
      </div>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def main():
    st.markdown('<div class="header-label">MULTI-AGENT SYSTEM · LIVE MARKET DATA</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-title">AI Trading Team</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-sub">Massive/Polygon real data · 5 Grok AI agents · Precise entry prices & stops</div>', unsafe_allow_html=True)

    secrets  = st.secrets if hasattr(st, "secrets") else {}

    col1, col2 = st.columns(2)
    with col1:
        grok_secret = secrets.get("GROK_API_KEY", "")
        if grok_secret:
            grok_key = grok_secret
            st.markdown("<div style='color:#10b981;font-size:11px;font-family:monospace;padding:8px 0;'>🔑 Grok key from secrets</div>", unsafe_allow_html=True)
        else:
            grok_key = st.text_input("Grok API Key", type="password", placeholder="xai-...", label_visibility="collapsed")
    with col2:
        poly_secret = secrets.get("POLYGON_API_KEY", "")
        if poly_secret:
            poly_key = poly_secret
            st.markdown("<div style='color:#10b981;font-size:11px;font-family:monospace;padding:8px 0;'>🔑 Massive/Polygon key from secrets</div>", unsafe_allow_html=True)
        else:
            poly_key = st.text_input("Massive / Polygon API Key", type="password", placeholder="Polygon key...", label_visibility="collapsed")

    col3, col4 = st.columns([4, 1])
    with col3:
        watchlist_raw = st.text_area("Watchlist", value="NVDA, AAPL, MSFT, META, AMD, TSLA, AVGO, SMCI",
                                      height=60, label_visibility="collapsed")
    with col4:
        sector = st.selectbox("Sector", ["Technology","Healthcare","Financials","Energy","Consumer","Industrials","Mixed"],
                               label_visibility="collapsed")

    tickers = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
    ready   = bool(grok_key and poly_key and tickers)
    run     = st.button("▶  DEPLOY TRADING TEAM", disabled=not ready)

    if not poly_key:
        st.caption("ℹ️ Massive/Polygon key required — free tier at polygon.io works fine")

    st.markdown("---")

    agent_col, result_col = st.columns([1, 2])
    with agent_col:
        st.markdown("<div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>AGENTS</div>", unsafe_allow_html=True)
        placeholders = {a["id"]: st.empty() for a in AGENTS}
        for agent in AGENTS:
            with placeholders[agent["id"]].container():
                agent_row(agent, "idle")
        st.markdown("<br>", unsafe_allow_html=True)
        log_ph = st.empty()

    with result_col:
        data_ph   = st.empty()
        result_ph = st.empty()

    if run and ready:
        logs    = []
        results = {}

        def refresh_log():
            log_ph.markdown(
                "<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;font-family:monospace;font-size:11px;'>" +
                "".join(f"<div style='color:#475569;margin-bottom:2px;'>{l}</div>" for l in logs[:-1]) +
                (f"<div style='color:#94a3b8;'>{logs[-1]}</div>" if logs else "") +
                "</div>", unsafe_allow_html=True)

        def upd(aid, status, note=""):
            agent = next(a for a in AGENTS if a["id"] == aid)
            with placeholders[aid].container():
                agent_row(agent, status, note)

        try:
            # Step 0: Market data
            logs.append("📡 Fetching live market data from Massive/Polygon...")
            refresh_log()
            market_data = {}
            for ticker in tickers:
                logs[-1] = f"📡 Fetching {ticker}..."
                refresh_log()
                market_data[ticker] = fetch_ticker_data(ticker, poly_key)
            logs[-1] = f"✓ Market data ready — {len(market_data)} tickers"
            refresh_log()

            with data_ph.container():
                market_data_table(market_data)

            md_summary = market_data_summary(market_data)

            # Steps 1-5: Agents
            for agent in AGENTS:
                upd(agent["id"], "running")
                logs.append(f"{agent['icon']} {agent['name']}: analyzing...")
                refresh_log()

                aid = agent["id"]
                if aid == "scanner":
                    msg = f"REAL live market data for {sector} sector:\n\n{md_summary}\n\nRank and select top 3-5 swing trade candidates."
                elif aid == "technicals":
                    cands = results["scanner"].get("candidates", [])
                    sel   = {c["ticker"]: market_data[c["ticker"]] for c in cands if c["ticker"] in market_data}
                    msg   = f"Real data for selected candidates:\n\n{market_data_summary(sel)}\n\nScanner:\n{json.dumps(cands)}\n\nCalculate precise entries using real ATR, EMA, price data."
                elif aid == "risk":
                    msg = f"Technical analysis with real prices:\n{json.dumps(results['technicals'].get('analysis',[]))}\n\nCalculate exact risk parameters."
                elif aid == "sentiment":
                    msg = f"Real market data:\n\n{md_summary}\n\nSector: {sector}. Evaluate sentiment using real RSI, RVol, price change data."
                else:
                    msg = (f"Synthesize final recommendations using REAL prices:\n\n"
                           f"MARKET DATA:\n{md_summary}\n\n"
                           f"SCANNER:\n{json.dumps(results['scanner'])}\n\n"
                           f"TECHNICALS:\n{json.dumps(results['technicals'])}\n\n"
                           f"RISK:\n{json.dumps(results['risk'])}\n\n"
                           f"SENTIMENT:\n{json.dumps(results['sentiment'])}")

                result = call_grok(grok_key, agent["system"], msg)
                results[aid] = result

                notes_map = {
                    "scanner":    f"Found {len(result.get('candidates',[]))} candidates",
                    "technicals": "Entry levels calculated",
                    "risk":       "Risk plans ready",
                    "sentiment":  f"Market: {result.get('sentiment',{}).get('market_phase','')}",
                    "strategist": f"{len(result.get('recommendations',[]))} trades ranked",
                }
                note = notes_map[aid]
                upd(aid, "done", note)
                logs[-1] = f"✓ {agent['name']}: {note}"
                refresh_log()

            # Render
            recs = results["strategist"].get("recommendations", [])
            with result_ph.container():
                st.markdown("<div style='color:#10b981;font-size:11px;letter-spacing:2px;font-family:monospace;margin-bottom:14px;'>▸ TRADE RECOMMENDATIONS</div>", unsafe_allow_html=True)
                for trade in recs:
                    trade_card(trade)
                pnotes = results["strategist"].get("portfolio_notes", "")
                if pnotes:
                    st.markdown(f"""<div style='background:#0f172a;border:1px solid #1e293b;border-left:3px solid #f59e0b;border-radius:10px;padding:14px;margin-top:4px;'>
                      <div style='color:#f59e0b;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:6px;'>PORTFOLIO NOTES</div>
                      <div style='color:#94a3b8;font-size:13px;line-height:1.6;'>{pnotes}</div></div>""", unsafe_allow_html=True)
                st.markdown("<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px;text-align:center;color:#475569;font-size:11px;margin-top:12px;'>⚠ For educational purposes only. Not financial advice.</div>", unsafe_allow_html=True)

        except urllib.error.HTTPError as e:
            st.error(f"API error {e.code}: {e.read().decode()}")
        except json.JSONDecodeError as e:
            st.error(f"JSON parse error: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()

            
