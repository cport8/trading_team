import streamlit as st
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from statistics import mean

st.set_page_config(
    page_title="AI Trading Team v2",
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
  .header-sub   { font-size: 13px; color: #64748b; text-align: center; margin-top: 4px; margin-bottom: 24px; }
  div[data-testid="stTextArea"] textarea { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; font-family: monospace !important; font-size: 13px !important; }
  div[data-testid="stSelectbox"] > div  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  div[data-testid="stTextInput"] input  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  .stButton > button { width:100%; background:transparent !important; border:1px solid #00d4ff44 !important; color:#00d4ff !important; font-family:monospace !important; font-weight:700 !important; letter-spacing:1px !important; font-size:14px !important; padding:12px !important; border-radius:8px !important; }
  .stButton > button:hover { background:#00d4ff11 !important; border-color:#00d4ff !important; }
  .metric-card {background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;}
</style>
""", unsafe_allow_html=True)

GRADE_COLORS = {"A+": "#10b981", "A": "#22c55e", "B+": "#84cc16", "B": "#eab308", "C": "#f97316", "D": "#ef4444"}

AGENTS = [
    {
        "id": "scanner",
        "name": "Quant Scanner",
        "role": "Deterministic ranking from precomputed factors",
        "icon": "🔭",
        "color": "#00d4ff",
        "system": """You are a quantitative swing trade scanner. Use ONLY the provided structured JSON and do not invent numbers. Rank the best candidates based on trend quality, setup quality, Oliver Kell cycle quality, Jeff Sun extension state, relative strength, volume sponsorship, and risk geometry. Prefer Stage 2, RS leaders, constructive Cycle 1 or Cycle 2, reasonable extension from the 50MA, and adequate liquidity. Return ONLY valid JSON: {"candidates":[{"ticker":"AAPL","rank":1,"scanner_score":89.4,"setup":"First pullback","conviction":"High","why":"Two short sentences."}],"market_context":"One sentence."}"""
    },
    {
        "id": "kell_cycle",
        "name": "Oliver Kell Cycle Analyst",
        "role": "Classifies cycle stage and add-on timing",
        "icon": "🌀",
        "color": "#22c55e",
        "system": """You are an Oliver Kell-style cycle analyst. Use ONLY the provided structured JSON. Determine whether each stock is in Base building, Fresh breakout, First pullback, Add-on continuation, or Late cycle / extended. Prefer a valid breakout followed by a controlled pullback to the 10EMA/21EMA, tight closes, and orderly digestion. Flag late, loose, and extended names. Return ONLY valid JSON: {"cycle_analysis":[{"ticker":"AAPL","cycle_stage":"First pullback","cycle_score":8.7,"entry_type":"10EMA pullback","too_extended":false,"too_late":false,"notes":"Short note."}]}"""
    },
    {
        "id": "executor",
        "name": "Technical Executor",
        "role": "Produces exact entries, triggers, and structural stops",
        "icon": "📈",
        "color": "#7c3aed",
        "system": """You are a technical execution agent. Use ONLY the provided structured JSON and exact computed fields. Select the best entry archetype for each ticker: breakout above pivot, 10EMA pullback reclaim, 21EMA support, mini-pivot add-on, or undercut-and-reclaim. Use the provided pivot, ATR, EMA, support, and extension fields. Return ONLY valid JSON: {"analysis":[{"ticker":"AAPL","entry_type":"Breakout","entry_price":187.32,"entry_zone":"187.00-187.60","stop_loss":183.8,"stop_type":"Structural","trigger":"Buy above pivot with volume > 1.5x avg","support":181.0,"resistance":192.0,"setup_quality":"A","notes":"Short note."}]}"""
    },
    {
        "id": "risk",
        "name": "Risk Architect",
        "role": "Position sizing, targets, and invalidation",
        "icon": "🛡️",
        "color": "#f59e0b",
        "system": """You are a risk architect. Use ONLY the provided structured JSON with exact entry and stop values. Compute risk per share, target 1, target 2, reward/risk, and 1R- and 0.5%-of-equity sizing. Prefer at least 2:1 reward/risk unless cycle quality is exceptional. Return ONLY valid JSON: {"risk_plans":[{"ticker":"AAPL","entry":187.32,"stop_loss":183.80,"risk_per_share":3.52,"target_1":194.36,"target_2":199.64,"reward_risk_ratio":"2.0:1","shares_1k_risk":284,"shares_halfpct_100k":142,"invalidation":"Daily close below support","risk_note":"Short note."}]}"""
    },
    {
        "id": "strategist",
        "name": "Head Strategist",
        "role": "Final ranked trade cards and portfolio guardrails",
        "icon": "🎯",
        "color": "#ef4444",
        "system": """You are the head strategist. Use EXACT values from the scanner, cycle, execution, and risk payloads. Do not invent numbers. Rank the trade ideas, penalize overlapping sector exposure and excessive correlation, and note earnings/event risk if present. Return ONLY valid JSON: {"recommendations":[{"rank":1,"ticker":"AAPL","action":"BUY","buy_price":187.32,"stop_loss":183.80,"target_1":194.36,"target_2":199.64,"holding_period":"5-15 days","strategy":"First pullback","conviction":"High","grade":"A","rationale":"Two short sentences.","entry_trigger":"Exact trigger text","key_risk":"Specific risk"}],"portfolio_notes":"One short paragraph."}"""
    },
]


def massive_get(path, poly_key):
    url = f"https://api.polygon.io{path}"
    sep = "&" if "?" in url else "?"
    url = url + sep + f"apiKey={poly_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradingTeamV2/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def xai_post_responses(api_key, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=data,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode())


def call_grok(api_key, system, user_msg):
    payload = {
        "model": "grok-4.3",
        "store": False,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
    }
    data = xai_post_responses(api_key, payload)
    text_chunks = []
    for item in data.get("output", []):
        if item.get("type") == "message":
            for c in item.get("content", []):
                if c.get("type") == "output_text":
                    text_chunks.append(c.get("text", ""))
    raw = "\n".join(text_chunks).strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def ema_series(prices, period):
    if len(prices) < period:
        return [None] * len(prices)
    k = 2 / (period + 1)
    out = [None] * len(prices)
    seed = sum(prices[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(prices)):
        prev = prices[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def sma_series(prices, period):
    out = [None] * len(prices)
    if len(prices) < period:
        return out
    s = sum(prices[:period])
    out[period - 1] = s / period
    for i in range(period, len(prices)):
        s += prices[i] - prices[i - period]
        out[i] = s / period
    return out


def wilder_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains = []
    losses = []
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(abs(min(d, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        gain = max(d, 0)
        loss = abs(min(d, 0))
        avg_gain = ((avg_gain * (period - 1)) + gain) / period
        avg_loss = ((avg_loss * (period - 1)) + loss) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def atr_series(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return [None] * len(closes)
    trs = [None]
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        trs.append(tr)
    out = [None] * len(closes)
    first = mean([t for t in trs[1:period + 1] if t is not None])
    out[period] = first
    prev = first
    for i in range(period + 1, len(closes)):
        prev = ((prev * (period - 1)) + trs[i]) / period
        out[i] = prev
    return out


def pct_change(a, b):
    return round(((a - b) / b) * 100, 2) if b else 0.0


def compute_relative_strength(stock_closes, benchmark_closes, lookback=63):
    n = min(len(stock_closes), len(benchmark_closes), lookback)
    if n < 20:
        return None
    s0, s1 = stock_closes[-n], stock_closes[-1]
    b0, b1 = benchmark_closes[-n], benchmark_closes[-1]
    if s0 <= 0 or b0 <= 0:
        return None
    sret = (s1 / s0) - 1
    bret = (b1 / b0) - 1
    return round((sret - bret) * 100, 2)


def compute_vcp(highs, lows, volumes):
    if len(highs) < 25:
        return False, []
    windows = [(25, 15), (15, 8), (8, 0)]
    ranges = []
    for start_back, end_back in windows:
        seg_high = highs[-start_back:] if end_back == 0 else highs[-start_back:-end_back]
        seg_low = lows[-start_back:] if end_back == 0 else lows[-start_back:-end_back]
        if not seg_high or not seg_low:
            return False, []
        ranges.append(max(seg_high) - min(seg_low))
    vol_contract = False
    if len(volumes) >= 30:
        v1 = mean(volumes[-30:-15]) if len(volumes[-30:-15]) else 0
        v2 = mean(volumes[-15:-5]) if len(volumes[-15:-5]) else 0
        v3 = mean(volumes[-5:]) if len(volumes[-5:]) else 0
        vol_contract = bool(v1 > v2 > v3)
    return bool(ranges[0] > ranges[1] > ranges[2] and vol_contract), [round(x, 2) for x in ranges]


def recent_pivot(highs, closes, lookback=20):
    if len(highs) < lookback:
        return max(highs) if highs else 0
    return round(max(highs[-lookback:]), 2)


def detect_tight_closes(closes, days=5, threshold=1.8):
    if len(closes) < days:
        return 0
    seg = closes[-days:]
    hi, lo = max(seg), min(seg)
    if lo == 0:
        return 0
    spread_pct = ((hi - lo) / lo) * 100
    return days if spread_pct <= threshold else 0


def nearest_earnings_placeholder():
    return {"has_earnings_data": False, "days_to_earnings": None, "earnings_risk": "Unknown"}


def correlation_proxy(series_a, series_b, lookback=30):
    n = min(len(series_a), len(series_b), lookback)
    if n < 10:
        return None
    a = series_a[-n:]
    b = series_b[-n:]
    ar = [(a[i] / a[i - 1] - 1) for i in range(1, n) if a[i - 1] != 0]
    br = [(b[i] / b[i - 1] - 1) for i in range(1, n) if b[i - 1] != 0]
    m = min(len(ar), len(br))
    if m < 8:
        return None
    ar, br = ar[-m:], br[-m:]
    ma, mb = mean(ar), mean(br)
    num = sum((x - ma) * (y - mb) for x, y in zip(ar, br))
    da = math.sqrt(sum((x - ma) ** 2 for x in ar))
    db = math.sqrt(sum((y - mb) ** 2 for y in br))
    if da == 0 or db == 0:
        return None
    return round(num / (da * db), 2)


def compute_jeff_sun_metrics(price, atr14, sma50, sma150, sma200, avg_vol_20, volume):
    atr_multiple_from_50ma = round((price - sma50) / atr14, 2) if atr14 and sma50 else None
    atr_percent_of_50ma = round((atr14 / sma50) * 100, 2) if atr14 and sma50 else None
    pct_from_50ma = round(((price - sma50) / sma50) * 100, 2) if sma50 else None
    pct_from_150ma = round(((price - sma150) / sma150) * 100, 2) if sma150 else None
    pct_from_200ma = round(((price - sma200) / sma200) * 100, 2) if sma200 else None
    rvol = round(volume / avg_vol_20, 2) if avg_vol_20 else 0.0
    label = "Unknown"
    if sma50 and price < sma50:
        label = "Below 50MA"
    elif atr_multiple_from_50ma is None:
        label = "Unknown"
    elif atr_multiple_from_50ma < 0.75:
        label = "Near 50MA"
    elif atr_multiple_from_50ma < 2.5:
        label = "Extended but workable"
    else:
        label = "Hot / extended"
    return {
        "atr_multiple_from_50ma": atr_multiple_from_50ma,
        "atr_percent_of_50ma": atr_percent_of_50ma,
        "pct_from_50ma": pct_from_50ma,
        "pct_from_150ma": pct_from_150ma,
        "pct_from_200ma": pct_from_200ma,
        "rvol": rvol,
        "extension_label": label,
    }


def classify_stage(price, sma50, sma150, sma200):
    if not sma50 or not sma150 or not sma200:
        return "Unknown"
    if price > sma50 > sma150 > sma200:
        return "Stage 2 (Uptrend)"
    if price < sma50 < sma150 < sma200:
        return "Stage 4 (Downtrend)"
    if price > sma200 and sma50 > sma200:
        return "Stage 1/2"
    return "Stage 3/4"


def classify_kell_cycle(closes, highs, lows, ema10, ema21, pivot, atr14):
    price = closes[-1]
    base_len = min(35, len(closes))
    recent_breakout = price > pivot * 0.995 and len(closes) >= 10
    breakout_idx = None
    for i in range(max(0, len(closes) - 25), len(closes)):
        if closes[i] >= pivot * 0.995:
            breakout_idx = i
            break
    days_since_breakout = (len(closes) - 1 - breakout_idx) if breakout_idx is not None else None
    max_run_from_pivot_pct = round(((max(highs[-20:]) - pivot) / pivot) * 100, 2) if pivot and len(highs) >= 20 else 0
    pullback_depth_pct = round(((max(highs[-10:]) - price) / max(highs[-10:])) * 100, 2) if len(highs) >= 10 and max(highs[-10:]) else 0
    tight_closes_count = detect_tight_closes(closes, days=5, threshold=1.8)
    distance_to_10 = round((price - ema10) / atr14, 2) if ema10 and atr14 else None
    distance_to_21 = round((price - ema21) / atr14, 2) if ema21 and atr14 else None
    extended_from_pivot_pct = round(((price - pivot) / pivot) * 100, 2) if pivot else 0

    if breakout_idx is None and abs(price - pivot) / pivot < 0.03:
        cycle_stage = "Base building"
    elif breakout_idx is not None and days_since_breakout is not None and days_since_breakout <= 7 and extended_from_pivot_pct <= 8:
        cycle_stage = "Fresh breakout"
    elif breakout_idx is not None and days_since_breakout is not None and days_since_breakout <= 25 and pullback_depth_pct <= 10 and distance_to_10 is not None and distance_to_10 > -1.2:
        cycle_stage = "First pullback"
    elif breakout_idx is not None and tight_closes_count >= 3 and extended_from_pivot_pct <= 15:
        cycle_stage = "Add-on continuation"
    else:
        cycle_stage = "Late cycle / extended"

    too_extended = bool(extended_from_pivot_pct > 12 or (distance_to_10 is not None and distance_to_10 > 2.5))
    too_late = bool(cycle_stage == "Late cycle / extended")

    return {
        "cycle_stage": cycle_stage,
        "days_since_breakout": days_since_breakout,
        "max_run_from_pivot_pct": max_run_from_pivot_pct,
        "pullback_depth_pct": pullback_depth_pct,
        "tight_closes_count": tight_closes_count,
        "distance_atr_from_10ema": distance_to_10,
        "distance_atr_from_21ema": distance_to_21,
        "extended_from_pivot_pct": extended_from_pivot_pct,
        "too_extended": too_extended,
        "too_late": too_late,
        "recent_breakout": recent_breakout,
    }


def compute_score(d):
    trend = 0
    if d["stage"] == "Stage 2 (Uptrend)":
        trend += 25
    elif d["stage"] == "Stage 1/2":
        trend += 15
    if d["ema_alignment"] == "Bullish stack (10>21>50)":
        trend += 15
    elif "Bullish" in d["ema_alignment"]:
        trend += 8

    rs = max(min((d.get("rs_vs_spy_3m") or 0) / 2, 10), -5) + max(min((d.get("rs_vs_qqq_3m") or 0) / 2, 10), -5)
    rs = max(rs, 0)

    setup = 0
    if d.get("vcp_contracting"):
        setup += 10
    if d.get("tight_closes_count", 0) >= 3:
        setup += 8
    if 50 <= (d.get("rsi14") or 0) <= 72:
        setup += 7
    if d.get("breakout_volume_ratio", 0) >= 1.3:
        setup += 7

    cycle_score = {
        "Fresh breakout": 18,
        "First pullback": 20,
        "Add-on continuation": 14,
        "Base building": 8,
        "Late cycle / extended": 2,
    }.get(d.get("cycle_stage"), 0)

    ext = 0
    label = d.get("extension_label")
    if label == "Near 50MA":
        ext = 10
    elif label == "Extended but workable":
        ext = 7
    elif label == "Hot / extended":
        ext = 2
    elif label == "Below 50MA":
        ext = 1

    liquidity = 0
    if d.get("avg_vol_20", 0) >= 1_000_000:
        liquidity += 4
    if d.get("rvol", 0) >= 1.3:
        liquidity += 6

    score = trend + rs + setup + cycle_score + ext + liquidity
    if d.get("too_extended"):
        score -= 8
    if d.get("too_late"):
        score -= 8
    if d.get("earnings_penalty", 0):
        score -= d["earnings_penalty"]
    return round(max(score, 0), 1)


def choose_entry_and_stop(d):
    price = d["price"]
    atr = d["atr14"] or max(price * 0.02, 0.01)
    pivot = d["pivot_price"]
    ema10 = d.get("ema10")
    ema21 = d.get("ema21")
    support = d.get("support_level") or min(price, ema21 or price)
    resistance = d.get("resistance_level") or pivot
    cycle = d.get("cycle_stage")

    if cycle == "Fresh breakout":
        entry_type = "Breakout above pivot"
        entry = round(pivot + atr * 0.10, 2)
        stop_struct = min(d.get("base_low", support), (ema21 or support))
        stop_atr = entry - atr * 1.5
        stop = round(max(stop_struct, stop_atr), 2)
        trigger = f"Buy above {pivot:.2f} pivot with volume > 1.5x 20-day average"
    elif cycle == "First pullback":
        anchor = ema10 or ema21 or price
        entry_type = "10EMA/21EMA reclaim"
        entry = round(max(price, anchor + atr * 0.15), 2)
        stop = round(min((ema21 or support) - atr * 0.35, d.get("swing_low_10", support)), 2)
        trigger = "Buy on reclaim of short-term moving average support with closing strength"
    elif cycle == "Add-on continuation":
        mini_pivot = round(max(d.get("recent_5d_high", pivot), pivot), 2)
        entry_type = "Mini-pivot add-on"
        entry = round(mini_pivot + atr * 0.08, 2)
        stop = round(min(d.get("swing_low_5", support), (ema21 or support) - atr * 0.25), 2)
        trigger = f"Buy above mini-pivot {mini_pivot:.2f} on expanding volume"
    else:
        entry_type = "Watch / base trigger"
        entry = round(pivot + atr * 0.1, 2)
        stop = round(min(support, entry - atr * 1.8), 2)
        trigger = "Wait for decisive breakout or tighter pullback structure"

    if stop >= entry:
        stop = round(entry - atr * 1.2, 2)

    risk = round(entry - stop, 2)
    t1 = round(entry + risk * 2, 2)
    t2 = round(entry + risk * 3.5, 2)
    rr = round((t1 - entry) / risk, 2) if risk > 0 else 0

    return {
        "entry_type": entry_type,
        "entry_price": entry,
        "entry_zone": f"{round(entry - atr*0.1,2):.2f} - {round(entry + atr*0.2,2):.2f}",
        "stop_loss": stop,
        "risk_per_share": risk,
        "target_1": t1,
        "target_2": t2,
        "reward_risk_ratio": f"{rr}:1",
        "trigger": trigger,
        "support": round(support, 2),
        "resistance": round(resistance, 2),
    }


def fetch_reference_series(symbols, poly_key):
    data = {}
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=420)).strftime("%Y-%m-%d")
    for s in symbols:
        bars = massive_get(f"/v2/aggs/ticker/{s}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=500", poly_key)
        rb = bars.get("results", [])
        data[s] = [b.get("c", 0) for b in rb]
    return data


def fetch_ticker_data(ticker, poly_key, benchmarks):
    result = {"ticker": ticker, "error": None}
    try:
        snap = massive_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", poly_key)
        t = snap.get("ticker", {})
        day = t.get("day", {})
        prev = t.get("prevDay", {})
        result["price"] = day.get("c") or prev.get("c", 0)
        result["open"] = day.get("o", 0)
        result["high"] = day.get("h", 0)
        result["low"] = day.get("l", 0)
        result["volume"] = day.get("v", 0)
        result["prev_close"] = prev.get("c", 0)
        result["change_pct"] = pct_change(result["price"], result["prev_close"]) if result["prev_close"] else 0

        end = datetime.utcnow().strftime("%Y-%m-%d")
        start = (datetime.utcnow() - timedelta(days=420)).strftime("%Y-%m-%d")
        bars = massive_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=500", poly_key)
        rb = bars.get("results", [])
        if len(rb) < 60:
            raise ValueError("Not enough historical bars")
        closes = [b["c"] for b in rb]
        highs = [b["h"] for b in rb]
        lows = [b["l"] for b in rb]
        opens = [b["o"] for b in rb]
        vols = [b["v"] for b in rb]

        result["bar_count"] = len(rb)
        result["high_52w"] = round(max(highs[-252:]), 2) if len(highs) >= 252 else round(max(highs), 2)
        result["low_52w"] = round(min(lows[-252:]), 2) if len(lows) >= 252 else round(min(lows), 2)
        result["avg_vol_20"] = round(mean(vols[-20:]), 0)
        result["rvol"] = round(result["volume"] / result["avg_vol_20"], 2) if result["avg_vol_20"] else 0

        ema10s = ema_series(closes, 10)
        ema21s = ema_series(closes, 21)
        ema50s = ema_series(closes, 50)
        sma50s = sma_series(closes, 50)
        sma150s = sma_series(closes, 150)
        sma200s = sma_series(closes, 200)
        atr14s = atr_series(highs, lows, closes, 14)

        result["ema10"] = round(ema10s[-1], 2) if ema10s[-1] else None
        result["ema21"] = round(ema21s[-1], 2) if ema21s[-1] else None
        result["ema50"] = round(ema50s[-1], 2) if ema50s[-1] else None
        result["sma50"] = round(sma50s[-1], 2) if sma50s[-1] else None
        result["sma150"] = round(sma150s[-1], 2) if sma150s[-1] else None
        result["sma200"] = round(sma200s[-1], 2) if sma200s[-1] else None
        result["atr14"] = round(atr14s[-1], 2) if atr14s[-1] else round(result["price"] * 0.02, 2)
        result["rsi14"] = wilder_rsi(closes, 14)
        result["pct_from_high"] = round(((result["price"] - result["high_52w"]) / result["high_52w"]) * 100, 2) if result["high_52w"] else 0

        p = result["price"]
        e10, e21, e50 = result["ema10"], result["ema21"], result["ema50"]
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

        result["stage"] = classify_stage(p, result["sma50"], result["sma150"], result["sma200"])
        vcp_contracting, vcp_ranges = compute_vcp(highs, lows, vols)
        result["vcp_contracting"] = vcp_contracting
        result["vcp_ranges"] = vcp_ranges
        result["pivot_price"] = recent_pivot(highs[:-1], closes[:-1], 20)
        result["recent_5d_high"] = round(max(highs[-5:]), 2)
        result["swing_low_5"] = round(min(lows[-5:]), 2)
        result["swing_low_10"] = round(min(lows[-10:]), 2)
        result["base_low"] = round(min(lows[-25:]), 2)
        result["support_level"] = round(min(result["ema21"] or p, result["swing_low_10"]), 2)
        result["resistance_level"] = round(max(highs[-10:]), 2)
        result["tight_closes_count"] = detect_tight_closes(closes, 5, 1.8)
        result["breakout_volume_ratio"] = round(mean(vols[-3:]) / mean(vols[-20:]), 2) if len(vols) >= 20 and mean(vols[-20:]) else 0
        result["volume_dry_up"] = round(mean(vols[-5:]) / mean(vols[-20:]), 2) if len(vols) >= 20 and mean(vols[-20:]) else 0

        kell = classify_kell_cycle(closes, highs, lows, result["ema10"], result["ema21"], result["pivot_price"], result["atr14"])
        result.update(kell)

        js = compute_jeff_sun_metrics(p, result["atr14"], result["sma50"], result["sma150"], result["sma200"], result["avg_vol_20"], result["volume"])
        result.update(js)

        result["rs_vs_spy_3m"] = compute_relative_strength(closes, benchmarks.get("SPY", []), 63)
        result["rs_vs_qqq_3m"] = compute_relative_strength(closes, benchmarks.get("QQQ", []), 63)
        result["returns_series"] = closes
        result.update(nearest_earnings_placeholder())
        result["earnings_penalty"] = 0

        result["scanner_score"] = compute_score(result)
        plan = choose_entry_and_stop(result)
        result.update(plan)
        result["grade"] = "A+" if result["scanner_score"] >= 88 else "A" if result["scanner_score"] >= 80 else "B+" if result["scanner_score"] >= 72 else "B" if result["scanner_score"] >= 64 else "C"
    except Exception as e:
        result["error"] = str(e)
    return result


def compact_market_payload(market_data):
    payload = []
    for ticker, d in market_data.items():
        if d.get("error"):
            continue
        payload.append({
            "ticker": ticker,
            "price": d.get("price"),
            "change_pct": d.get("change_pct"),
            "stage": d.get("stage"),
            "ema_alignment": d.get("ema_alignment"),
            "rsi14": d.get("rsi14"),
            "atr14": d.get("atr14"),
            "rvol": d.get("rvol"),
            "avg_vol_20": d.get("avg_vol_20"),
            "high_52w": d.get("high_52w"),
            "pct_from_high": d.get("pct_from_high"),
            "vcp_contracting": d.get("vcp_contracting"),
            "vcp_ranges": d.get("vcp_ranges"),
            "pivot_price": d.get("pivot_price"),
            "support_level": d.get("support_level"),
            "resistance_level": d.get("resistance_level"),
            "cycle_stage": d.get("cycle_stage"),
            "days_since_breakout": d.get("days_since_breakout"),
            "tight_closes_count": d.get("tight_closes_count"),
            "breakout_volume_ratio": d.get("breakout_volume_ratio"),
            "volume_dry_up": d.get("volume_dry_up"),
            "too_extended": d.get("too_extended"),
            "too_late": d.get("too_late"),
            "atr_multiple_from_50ma": d.get("atr_multiple_from_50ma"),
            "pct_from_50ma": d.get("pct_from_50ma"),
            "pct_from_150ma": d.get("pct_from_150ma"),
            "pct_from_200ma": d.get("pct_from_200ma"),
            "extension_label": d.get("extension_label"),
            "rs_vs_spy_3m": d.get("rs_vs_spy_3m"),
            "rs_vs_qqq_3m": d.get("rs_vs_qqq_3m"),
            "scanner_score": d.get("scanner_score"),
            "entry_type": d.get("entry_type"),
            "entry_price": d.get("entry_price"),
            "entry_zone": d.get("entry_zone"),
            "stop_loss": d.get("stop_loss"),
            "risk_per_share": d.get("risk_per_share"),
            "target_1": d.get("target_1"),
            "target_2": d.get("target_2"),
            "reward_risk_ratio": d.get("reward_risk_ratio"),
            "grade": d.get("grade"),
        })
    return payload


def market_data_table(market_data):
    rows = ""
    for t, d in market_data.items():
        if d.get("error"):
            rows += f"<tr><td style='color:#ef4444;font-family:monospace'>{t}</td><td colspan='10' style='color:#475569;font-size:11px;'>Error: {d['error']}</td></tr>"
            continue
        chg_c = "#10b981" if d["change_pct"] >= 0 else "#ef4444"
        rvol_c = "#10b981" if d.get("rvol", 0) >= 1.5 else "#94a3b8"
        ext_c = "#ef4444" if d.get("extension_label") == "Hot / extended" else "#10b981" if d.get("extension_label") == "Near 50MA" else "#94a3b8"
        rows += (
            f"<tr>"
            f"<td style='color:#f1f5f9;font-weight:700;font-family:monospace;padding:5px 8px'>{t}</td>"
            f"<td style='color:#00d4ff;font-family:monospace;padding:5px 8px'>${d['price']}</td>"
            f"<td style='color:{chg_c};font-family:monospace;padding:5px 8px'>{d['change_pct']:+.2f}%</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d['stage']}</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d['cycle_stage']}</td>"
            f"<td style='color:#94a3b8;font-family:monospace;padding:5px 8px'>{d['rsi14']}</td>"
            f"<td style='color:{rvol_c};font-family:monospace;padding:5px 8px'>{d['rvol']}x</td>"
            f"<td style='color:{ext_c};font-size:11px;padding:5px 8px'>{d['extension_label']}</td>"
            f"<td style='color:#94a3b8;font-family:monospace;padding:5px 8px'>{d.get('rs_vs_spy_3m')}</td>"
            f"<td style='color:#10b981;font-family:monospace;padding:5px 8px'>{d['scanner_score']}</td>"
            f"</tr>"
        )
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-bottom:16px;overflow-x:auto;'>
      <div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>DETERMINISTIC MARKET ENGINE — POLYGON + RULES</div>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='color:#475569;font-size:10px;letter-spacing:1px;border-bottom:1px solid #1e293b;'>
          <th style='text-align:left;padding:4px 8px;'>TICKER</th>
          <th style='text-align:left;padding:4px 8px;'>PRICE</th>
          <th style='text-align:left;padding:4px 8px;'>CHG%</th>
          <th style='text-align:left;padding:4px 8px;'>STAGE</th>
          <th style='text-align:left;padding:4px 8px;'>KELL CYCLE</th>
          <th style='text-align:left;padding:4px 8px;'>RSI</th>
          <th style='text-align:left;padding:4px 8px;'>RVOL</th>
          <th style='text-align:left;padding:4px 8px;'>SUN EXTENSION</th>
          <th style='text-align:left;padding:4px 8px;'>RS vs SPY</th>
          <th style='text-align:left;padding:4px 8px;'>SCORE</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>""", unsafe_allow_html=True)


def trade_card(trade):
    grade = trade.get("grade", "B")
    color = GRADE_COLORS.get(grade, "#64748b")
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:18px;margin-bottom:14px;'>
      <div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;'>
        <div style='display:flex;align-items:center;gap:10px;'>
          <span style='background:{color};color:#000;border-radius:5px;padding:1px 8px;font-size:11px;font-weight:800;font-family:monospace;'>#{trade.get("rank","")}</span>
          <span style='color:#f1f5f9;font-size:20px;font-weight:800;font-family:monospace;'>{trade.get("ticker","")}</span>
          <span style='background:#10b98122;color:#10b981;border:1px solid #10b98144;border-radius:4px;padding:1px 8px;font-size:11px;font-weight:700;'>{trade.get("action","BUY")}</span>
        </div>
        <span style='background:{color}22;color:{color};border:1px solid {color}44;border-radius:6px;padding:2px 12px;font-size:14px;font-weight:800;font-family:monospace;'>{grade}</span>
      </div>
      <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px;'>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'><div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>BUY AT</div><div style='color:#00d4ff;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("buy_price","")}</div></div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'><div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>STOP</div><div style='color:#ef4444;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("stop_loss","")}</div></div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'><div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>TARGET 1</div><div style='color:#10b981;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("target_1","")}</div></div>
        <div style='background:#1e293b;border-radius:6px;padding:10px;'><div style='color:#475569;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:3px;'>TARGET 2</div><div style='color:#10b981;font-size:16px;font-weight:700;font-family:monospace;'>${trade.get("target_2","")}</div></div>
      </div>
      <div style='background:#1e293b;border-radius:6px;padding:10px 12px;margin-bottom:10px;'><div style='color:#00d4ff;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:4px;'>ENTRY TRIGGER</div><div style='color:#cbd5e1;font-size:13px;'>{trade.get("entry_trigger","")}</div></div>
      <div style='color:#94a3b8;font-size:13px;line-height:1.6;margin-bottom:10px;'>{trade.get("rationale","")}</div>
      <div>
        <span style='background:#1e293b;color:#64748b;border-radius:4px;padding:2px 8px;font-size:11px;margin-right:6px;'>⏱ {trade.get("holding_period","")}</span>
        <span style='background:#1e293b;color:#64748b;border-radius:4px;padding:2px 8px;font-size:11px;margin-right:6px;'>📊 {trade.get("strategy","")}</span>
        <span style='background:#1e293b;color:#f59e0b;border-radius:4px;padding:2px 8px;font-size:11px;'>⚠ {trade.get("key_risk","")}</span>
      </div>
    </div>""", unsafe_allow_html=True)


def agent_row(agent, status, note=""):
    icons = {"idle": "○", "running": "●", "done": "✓", "error": "✗"}
    colors = {"idle": "#475569", "running": agent["color"], "done": "#10b981", "error": "#ef4444"}
    c1, c2 = st.columns([3, 1])
    with c1:
        st.markdown(
            f"<div style='font-family:monospace;font-size:13px;color:{colors[status]};padding:4px 0'>{agent['icon']} <b>{agent['name']}</b> <span style='color:#475569;font-size:11px;'>— {agent['role']}</span></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"<div style='font-family:monospace;font-size:11px;color:{colors[status]};text-align:right;padding:4px 0'>{icons[status]} {status.upper()}</div>",
            unsafe_allow_html=True,
        )
    if note:
        st.markdown(f"<div style='color:#475569;font-size:11px;font-family:monospace;padding-left:26px;margin-bottom:2px'>{note}</div>", unsafe_allow_html=True)


def summarize_portfolio_overlap(market_data, selected):
    notes = []
    tickers = [x["ticker"] for x in selected]
    for i in range(len(tickers)):
        for j in range(i + 1, len(tickers)):
            a = market_data[tickers[i]]
            b = market_data[tickers[j]]
            corr = correlation_proxy(a.get("returns_series", []), b.get("returns_series", []), 30)
            if corr is not None and corr >= 0.8:
                notes.append(f"{tickers[i]}/{tickers[j]} correlation proxy {corr}")
    return "; ".join(notes[:4]) if notes else "No major correlation clusters detected in top names."


def main():
    st.markdown('<div class="header-label">MULTI-AGENT SYSTEM · DETERMINISTIC SWING ENGINE</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-title">AI Trading Team v2</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-sub">Polygon data · Oliver Kell cycle · Jeff Sun extension metrics · Structured Grok orchestration</div>', unsafe_allow_html=True)

    secrets = st.secrets if hasattr(st, "secrets") else {}
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
            st.markdown("<div style='color:#10b981;font-size:11px;font-family:monospace;padding:8px 0;'>🔑 Polygon key from secrets</div>", unsafe_allow_html=True)
        else:
            poly_key = st.text_input("Polygon API Key", type="password", placeholder="Polygon key...", label_visibility="collapsed")

    col3, col4 = st.columns([4, 1])
    with col3:
        watchlist_raw = st.text_area("Watchlist", value="NVDA, AAPL, MSFT, META, AMD, TSLA, AVGO, SMCI", height=60, label_visibility="collapsed")
    with col4:
        sector = st.selectbox("Sector", ["Technology", "Healthcare", "Financials", "Energy", "Consumer", "Industrials", "Mixed"], label_visibility="collapsed")

    tickers = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
    ready = bool(grok_key and poly_key and tickers)
    run = st.button("▶  DEPLOY TRADING TEAM V2", disabled=not ready)
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
        data_ph = st.empty()
        result_ph = st.empty()

    if run and ready:
        logs = []
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
            logs.append("📡 Loading benchmark series (SPY, QQQ)...")
            refresh_log()
            benchmarks = fetch_reference_series(["SPY", "QQQ"], poly_key)

            logs.append("📡 Fetching watchlist and computing deterministic factors...")
            refresh_log()
            market_data = {}
            for ticker in tickers:
                logs[-1] = f"📡 Computing {ticker}..."
                refresh_log()
                market_data[ticker] = fetch_ticker_data(ticker, poly_key, benchmarks)
            logs[-1] = f"✓ Market engine ready — {len(market_data)} tickers"
            refresh_log()

            with data_ph.container():
                market_data_table(market_data)

            clean_payload = compact_market_payload(market_data)
            for agent in AGENTS:
                upd(agent["id"], "running")
                logs.append(f"{agent['icon']} {agent['name']}: analyzing...")
                refresh_log()

                if agent["id"] == "scanner":
                    user_msg = json.dumps({"sector": sector, "watchlist": clean_payload}, indent=2)
                elif agent["id"] == "kell_cycle":
                    cands = results["scanner"].get("candidates", [])
                    sel = [x for x in clean_payload if x["ticker"] in {c["ticker"] for c in cands}]
                    user_msg = json.dumps({"selected_candidates": sel}, indent=2)
                elif agent["id"] == "executor":
                    cands = results["scanner"].get("candidates", [])
                    sel = [x for x in clean_payload if x["ticker"] in {c["ticker"] for c in cands}]
                    user_msg = json.dumps({"selected_candidates": sel, "cycle_analysis": results["kell_cycle"]}, indent=2)
                elif agent["id"] == "risk":
                    user_msg = json.dumps({"execution": results["executor"], "selected_candidates": clean_payload}, indent=2)
                else:
                    top = results["scanner"].get("candidates", [])
                    overlap = summarize_portfolio_overlap(market_data, top)
                    user_msg = json.dumps({
                        "scanner": results["scanner"],
                        "cycle": results["kell_cycle"],
                        "execution": results["executor"],
                        "risk": results["risk"],
                        "portfolio_overlap": overlap,
                    }, indent=2)

                result = call_grok(grok_key, agent["system"], user_msg)
                results[agent["id"]] = result
                notes_map = {
                    "scanner": f"Found {len(result.get('candidates', []))} candidates",
                    "kell_cycle": f"Cycle review on {len(result.get('cycle_analysis', []))} names",
                    "executor": "Entries and stops mapped",
                    "risk": "Sizing and targets ready",
                    "strategist": f"{len(result.get('recommendations', []))} trades ranked",
                }
                note = notes_map[agent["id"]]
                upd(agent["id"], "done", note)
                logs[-1] = f"✓ {agent['name']}: {note}"
                refresh_log()

            recs = results["strategist"].get("recommendations", [])
            with result_ph.container():
                st.markdown("<div style='color:#10b981;font-size:11px;letter-spacing:2px;font-family:monospace;margin-bottom:14px;'>▸ TRADE RECOMMENDATIONS</div>", unsafe_allow_html=True)
                for trade in recs:
                    trade_card(trade)
                pnotes = results["strategist"].get("portfolio_notes", "")
                if pnotes:
                    st.markdown(f"""<div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-top:4px;'><div style='color:#f59e0b;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:6px;'>PORTFOLIO NOTES</div><div style='color:#94a3b8;font-size:13px;line-height:1.6;'>{pnotes}</div></div>""", unsafe_allow_html=True)
                st.markdown("<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px;text-align:center;color:#475569;font-size:11px;margin-top:12px;'>⚠ Educational use only. Validate against your own process before trading.</div>", unsafe_allow_html=True)

        except urllib.error.HTTPError as e:
            st.error(f"API error {e.code}: {e.read().decode()}")
        except json.JSONDecodeError as e:
            st.error(f"JSON parse error from model output: {e}")
        except Exception as e:
            st.error(f"Error: {e}")

if __name__ == "__main__":
    main()
