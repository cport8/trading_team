"""
AI Trading Team — Streamlit App
Multi-agent swing trade analysis using Anthropic Claude
"""

import streamlit as st
import anthropic
import json
import time

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Trading Team",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Styling ────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Inter:wght@400;600;700;800&display=swap');

  html, body, [class*="css"] { background-color: #020817 !important; color: #f1f5f9 !important; }
  .stApp { background-color: #020817; }

  .header-label { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: 3px; color: #00d4ff; text-align: center; margin-bottom: 4px; }
  .header-title { font-family: 'Inter', sans-serif; font-size: 30px; font-weight: 800; text-align: center; color: #f1f5f9; }
  .header-sub   { font-family: 'Inter', sans-serif; font-size: 13px; color: #475569; text-align: center; margin-top: 4px; margin-bottom: 24px; }

  .agent-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 14px 16px; margin-bottom: 8px; }
  .agent-card.active { border-color: var(--agent-color); background: color-mix(in srgb, var(--agent-color) 8%, #0f172a); }
  .agent-card.done   { border-color: #10b98144; }

  .trade-card { background: #0f172a; border: 1px solid #1e293b; border-radius: 10px; padding: 18px; margin-bottom: 14px; }
  .price-box  { background: #1e293b; border-radius: 6px; padding: 10px 12px; text-align: center; }
  .price-label{ font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: 1.5px; color: #475569; margin-bottom: 4px; }
  .price-val  { font-family: 'JetBrains Mono', monospace; font-size: 16px; font-weight: 700; }

  .log-box { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 12px; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #475569; }

  .tag { display: inline-block; background: #1e293b; border-radius: 4px; padding: 2px 8px; font-size: 11px; color: #64748b; margin-right: 6px; }
  .disclaimer { background: #0f172a; border: 1px solid #1e293b; border-radius: 8px; padding: 10px; text-align: center; color: #475569; font-size: 11px; margin-top: 12px; }

  div[data-testid="stTextArea"] textarea { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; font-family: 'JetBrains Mono', monospace !important; font-size: 13px !important; }
  div[data-testid="stSelectbox"] > div { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  div[data-testid="stTextInput"] input { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  .stButton > button { width: 100%; background: transparent !important; border: 1px solid #00d4ff44 !important; color: #00d4ff !important; font-family: 'JetBrains Mono', monospace !important; font-weight: 700 !important; letter-spacing: 1px !important; font-size: 14px !important; padding: 12px !important; border-radius: 8px !important; }
  .stButton > button:hover { background: #00d4ff11 !important; border-color: #00d4ff !important; }
  .stButton > button:disabled { color: #475569 !important; border-color: #334155 !important; }
  div[data-testid="stProgress"] > div { background: #1e293b !important; }
  div[data-testid="stProgress"] > div > div { background: #00d4ff !important; }
</style>
""", unsafe_allow_html=True)

# ── Agent definitions ──────────────────────────────────────────────────────────
AGENTS = [
    {
        "id": "scanner",
        "name": "Market Scanner",
        "role": "Finds swing trade candidates",
        "icon": "🔭",
        "color": "#00d4ff",
        "system": """You are a Market Scanner agent specializing in identifying swing trade candidates.
Analyze the provided watchlist and identify 3-5 stocks with the strongest swing trade setups.
Evaluate: Stage Analysis (Weinstein 1-4), EMA alignment (10/21/50), relative strength, volume patterns, VCP characteristics.
Return ONLY valid JSON, no markdown, no explanation:
{
  "candidates": [
    {
      "ticker": "AAPL",
      "stage": "Stage 2",
      "trend": "Uptrend",
      "ema_alignment": "Bullish stack",
      "rs": "Strong",
      "setup": "VCP base, 3 contractions",
      "conviction": "High"
    }
  ],
  "market_context": "One-sentence market context"
}"""
    },
    {
        "id": "technicals",
        "name": "Technical Analyst",
        "role": "Entry levels & chart patterns",
        "icon": "📈",
        "color": "#7c3aed",
        "system": """You are a Technical Analyst agent for precise swing trade entry timing.
Given candidate stocks, perform deep technical analysis for each.
Focus on: pivot levels, ATR-based entries (Jeff Sun methodology), key S/R, breakout patterns, entry zones.
Return ONLY valid JSON:
{
  "analysis": [
    {
      "ticker": "AAPL",
      "pattern": "Ascending base breakout",
      "pivot_price": 185.50,
      "entry_zone": "185.50 - 186.20",
      "atr_entry": "Above pivot + 0.25x daily ATR",
      "key_resistance": 190.00,
      "key_support": 181.00,
      "setup_quality": "A+",
      "notes": "3rd-week tight, volume drying up"
    }
  ]
}"""
    },
    {
        "id": "risk",
        "name": "Risk Manager",
        "role": "Stops, targets & position sizing",
        "icon": "🛡️",
        "color": "#f59e0b",
        "system": """You are a Risk Manager agent for swing trading.
Rules: max 1-2% account risk per trade, stop below key support or 2x ATR below entry, minimum 2:1 R:R.
Return ONLY valid JSON:
{
  "risk_plans": [
    {
      "ticker": "AAPL",
      "entry": 185.75,
      "stop_loss": 182.00,
      "target_1": 192.00,
      "target_2": 198.00,
      "risk_per_share": 3.75,
      "reward_risk_ratio": "2.6:1",
      "position_size_1k_risk": 267,
      "stop_rationale": "Below 21 EMA and last pivot low",
      "invalidation": "Close below 181.50"
    }
  ]
}"""
    },
    {
        "id": "sentiment",
        "name": "Sentiment Analyst",
        "role": "Macro & sector tailwinds",
        "icon": "🌊",
        "color": "#10b981",
        "system": """You are a Sentiment Analyst evaluating macro and sector dynamics for swing trades.
Assess: sector rotation, institutional flow, earnings calendar risk, market phase (risk-on/off), VIX regime.
Return ONLY valid JSON:
{
  "sentiment": {
    "market_phase": "Risk-On",
    "breadth": "Expanding",
    "vix_regime": "Low (<20)",
    "sector_leaders": ["Technology", "Industrials"],
    "avoid_sectors": ["Utilities"]
  },
  "stock_sentiment": [
    {
      "ticker": "AAPL",
      "sector_tailwind": "Strong",
      "institutional_bias": "Accumulation",
      "earnings_risk": "Low - 6 weeks away",
      "options_skew": "Bullish",
      "sentiment_score": 8
    }
  ]
}"""
    },
    {
        "id": "strategist",
        "name": "Head Strategist",
        "role": "Final ranked recommendations",
        "icon": "🎯",
        "color": "#ef4444",
        "system": """You are the Head Strategist synthesizing all agent reports into final swing trade recommendations.
Rank trades by conviction. Combine scanner, technical, risk, and sentiment data.
Return ONLY valid JSON:
{
  "recommendations": [
    {
      "rank": 1,
      "ticker": "AAPL",
      "action": "BUY",
      "buy_price": 185.75,
      "stop_loss": 182.00,
      "target_1": 192.00,
      "target_2": 198.00,
      "holding_period": "5-15 days",
      "strategy": "Breakout swing",
      "conviction": "High",
      "grade": "A+",
      "rationale": "Two-sentence summary of why this trade works.",
      "entry_trigger": "Buy on break above 185.50 with volume >1.5x average",
      "key_risk": "Broad market selloff invalidates setup"
    }
  ],
  "portfolio_notes": "Brief note on portfolio construction and correlation"
}"""
    },
]

GRADE_COLORS = {"A+": "#10b981", "A": "#22c55e", "B+": "#84cc16", "B": "#eab308", "C": "#f97316"}

# ── Claude call ────────────────────────────────────────────────────────────────
def call_claude(api_key: str, system: str, user_msg: str) -> dict:
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=system,
        messages=[{"role": "user", "content": user_msg}]
    )
    raw = msg.content[0].text.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)

# ── UI helpers ─────────────────────────────────────────────────────────────────
def agent_status_row(agent: dict, status: str, note: str = ""):
    icons = {"idle": "○", "running": "●", "done": "✓", "error": "✗"}
    colors = {"idle": "#475569", "running": agent["color"], "done": "#10b981", "error": "#ef4444"}
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown(
            f"<div style='font-family:JetBrains Mono,monospace;font-size:13px;color:{colors[status]};padding:4px 0'>"
            f"{agent['icon']} <b>{agent['name']}</b> <span style='color:#475569;font-size:11px;'>— {agent['role']}</span>"
            f"</div>", unsafe_allow_html=True
        )
    with col2:
        st.markdown(
            f"<div style='font-family:JetBrains Mono,monospace;font-size:11px;color:{colors[status]};text-align:right;padding:4px 0'>"
            f"{icons[status]} {status.upper()}</div>", unsafe_allow_html=True
        )
    if note:
        st.markdown(f"<div style='color:#475569;font-size:11px;font-family:monospace;padding-left:26px;margin-bottom:4px'>{note}</div>", unsafe_allow_html=True)

def trade_card(trade: dict):
    grade = trade.get("grade", "B")
    color = GRADE_COLORS.get(grade, "#64748b")
    ticker = trade.get("ticker", "")
    
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-left:3px solid {color};border-radius:10px;padding:18px;margin-bottom:14px;'>
      <div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;'>
        <div style='display:flex;align-items:center;gap:10px;'>
          <span style='background:{color};color:#000;border-radius:5px;padding:1px 8px;font-size:11px;font-weight:800;font-family:monospace;'>#{trade.get("rank","")}</span>
          <span style='color:#f1f5f9;font-size:20px;font-weight:800;font-family:monospace;'>{ticker}</span>
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
    </div>
    """, unsafe_allow_html=True)

# ── Main app ───────────────────────────────────────────────────────────────────
def main():
    # Header
    st.markdown('<div class="header-label">MULTI-AGENT SYSTEM</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-title">AI Trading Team</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-sub">5 specialist agents · Swing trade analysis · Entry prices & stops</div>', unsafe_allow_html=True)

    # API Key + Inputs
    with st.container():
        col_key, col_sector = st.columns([3, 1])
        with col_key:
            api_key = st.text_input("Anthropic API Key", type="password", placeholder="sk-ant-...", label_visibility="collapsed")
        with col_sector:
            sector = st.selectbox("Sector", ["Technology", "Healthcare", "Financials", "Energy", "Consumer", "Industrials", "Mixed"], label_visibility="collapsed")

        watchlist = st.text_area(
            "Watchlist",
            value="NVDA, AAPL, MSFT, META, AMD, TSLA, AVGO, SMCI",
            height=68,
            label_visibility="collapsed",
            placeholder="Enter tickers separated by commas..."
        )

        run = st.button("▶  DEPLOY TRADING TEAM", disabled=not api_key)

    st.markdown("---")

    # Agent status panel
    agent_col, result_col = st.columns([1, 2])

    with agent_col:
        st.markdown("<div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>AGENTS</div>", unsafe_allow_html=True)
        agent_placeholders = {a["id"]: st.empty() for a in AGENTS}
        for agent in AGENTS:
            with agent_placeholders[agent["id"]].container():
                agent_status_row(agent, "idle")

        st.markdown("<br>", unsafe_allow_html=True)
        log_header = st.empty()
        log_placeholder = st.empty()

    with result_col:
        result_placeholder = st.empty()

    # ── Run pipeline ────────────────────────────────────────────────────────────
    if run and api_key:
        logs = []
        results = {}

        def refresh_log():
            log_header.markdown("<div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:6px;'>LOG</div>", unsafe_allow_html=True)
            log_placeholder.markdown(
                "<div class='log-box'>" +
                "".join(f"<div style='margin-bottom:3px;color:#475569'>{l}</div>" for l in logs[:-1]) +
                (f"<div style='color:#94a3b8'>{logs[-1]}</div>" if logs else "") +
                "</div>", unsafe_allow_html=True
            )

        def update_agent(agent_id, status, note=""):
            agent = next(a for a in AGENTS if a["id"] == agent_id)
            with agent_placeholders[agent_id].container():
                agent_status_row(agent, status, note)

        try:
            # ── Scanner ──────────────────────────────────────────────────────
            update_agent("scanner", "running")
            logs.append(f"🔭 Scanner: Scanning {watchlist[:40]}...")
            refresh_log()

            scanner_result = call_claude(
                api_key, AGENTS[0]["system"],
                f"Analyze these tickers for swing trade setups: {watchlist}. Sector: {sector}."
            )
            results["scanner"] = scanner_result
            candidates = scanner_result.get("candidates", [])
            update_agent("scanner", "done", f"Found {len(candidates)} candidates")
            logs.append(f"✓ Scanner: {len(candidates)} candidates — {scanner_result.get('market_context','')}")
            refresh_log()

            # ── Technicals ───────────────────────────────────────────────────
            update_agent("technicals", "running")
            logs.append("📈 Technical Analyst: Running entry level analysis...")
            refresh_log()

            tech_result = call_claude(
                api_key, AGENTS[1]["system"],
                f"Analyze these candidates technically: {json.dumps(candidates)}"
            )
            results["technicals"] = tech_result
            update_agent("technicals", "done", "Setup analysis complete")
            logs.append(f"✓ Technicals: {len(tech_result.get('analysis',[]))} setups analyzed")
            refresh_log()

            # ── Risk ─────────────────────────────────────────────────────────
            update_agent("risk", "running")
            logs.append("🛡️ Risk Manager: Calculating stops & position sizing...")
            refresh_log()

            risk_result = call_claude(
                api_key, AGENTS[2]["system"],
                f"Calculate risk parameters for: {json.dumps(tech_result.get('analysis',[]))}"
            )
            results["risk"] = risk_result
            update_agent("risk", "done", "Risk plans ready")
            logs.append(f"✓ Risk: {len(risk_result.get('risk_plans',[]))} plans calculated")
            refresh_log()

            # ── Sentiment ────────────────────────────────────────────────────
            update_agent("sentiment", "running")
            logs.append("🌊 Sentiment Analyst: Evaluating macro & sector dynamics...")
            refresh_log()

            sent_result = call_claude(
                api_key, AGENTS[3]["system"],
                f"Evaluate macro sentiment for these stocks: {watchlist}. Sector: {sector}."
            )
            results["sentiment"] = sent_result
            market_phase = sent_result.get("sentiment", {}).get("market_phase", "Unknown")
            update_agent("sentiment", "done", f"Market: {market_phase}")
            logs.append(f"✓ Sentiment: {market_phase} — VIX {sent_result.get('sentiment',{}).get('vix_regime','')}")
            refresh_log()

            # ── Strategist ───────────────────────────────────────────────────
            update_agent("strategist", "running")
            logs.append("🎯 Head Strategist: Synthesizing final recommendations...")
            refresh_log()

            strat_result = call_claude(
                api_key, AGENTS[4]["system"],
                f"""Synthesize final swing trade recommendations from all agent reports:
SCANNER: {json.dumps(results['scanner'])}
TECHNICALS: {json.dumps(results['technicals'])}
RISK: {json.dumps(results['risk'])}
SENTIMENT: {json.dumps(results['sentiment'])}"""
            )
            results["strategist"] = strat_result
            recs = strat_result.get("recommendations", [])
            update_agent("strategist", "done", f"{len(recs)} trades ranked")
            logs.append(f"✅ Complete — {len(recs)} trade recommendations ready")
            refresh_log()

            # ── Render results ────────────────────────────────────────────────
            with result_placeholder.container():
                st.markdown("<div style='color:#10b981;font-size:11px;letter-spacing:2px;font-family:monospace;margin-bottom:14px;'>▸ TRADE RECOMMENDATIONS</div>", unsafe_allow_html=True)
                for trade in recs:
                    trade_card(trade)

                portfolio_notes = strat_result.get("portfolio_notes", "")
                if portfolio_notes:
                    st.markdown(f"""
                    <div style='background:#0f172a;border:1px solid #1e293b;border-left:3px solid #f59e0b;border-radius:10px;padding:14px;margin-top:4px;'>
                      <div style='color:#f59e0b;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:6px;'>PORTFOLIO NOTES</div>
                      <div style='color:#94a3b8;font-size:13px;line-height:1.6;'>{portfolio_notes}</div>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("<div class='disclaimer'>⚠ For educational purposes only. Not financial advice. Always do your own due diligence.</div>", unsafe_allow_html=True)

        except json.JSONDecodeError as e:
            st.error(f"JSON parse error from Claude: {e}")
        except anthropic.AuthenticationError:
            st.error("Invalid API key. Check your Anthropic API key.")
        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
