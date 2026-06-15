import streamlit as st
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta

st.set_page_config(
    page_title="AI Trading Team v2.1",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
  html, body, [class*="css"] { background-color: #020817 !important; color: #e2e8f0 !important; }
  .stApp { background: #020817; }
  .block-container { padding-top: 1.2rem; padding-bottom: 2rem; }
  .mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
  .kpi { background:#0f172a; border:1px solid #1e293b; border-radius:12px; padding:14px 16px; }
  .panel { background:#0f172a; border:1px solid #1e293b; border-radius:14px; padding:16px; }
  .small-label { color:#64748b; font-size:11px; letter-spacing:1.6px; text-transform:uppercase; }
  .title-lg { font-size:30px; font-weight:800; color:#f8fafc; }
  .muted { color:#94a3b8; }
  .good { color:#22c55e; }
  .warn { color:#f59e0b; }
  .bad { color:#ef4444; }
  .tag { display:inline-block; padding:3px 8px; border-radius:999px; border:1px solid #334155; background:#111827; font-size:11px; margin:2px 6px 2px 0; }
  .trade-card { background:#0f172a; border:1px solid #1e293b; border-radius:14px; padding:18px; margin-bottom:14px; }
</style>
""", unsafe_allow_html=True)

GRADE_COLORS = {"A+": "#10b981", "A": "#22c55e", "B+": "#84cc16", "B": "#eab308", "C": "#f97316", "D": "#ef4444"}
XAI_CHAT_ENDPOINT = "https://api.x.ai/v1/chat/completions"

AGENTS = [
    {
        "id": "scanner",
        "name": "Quant Scanner",
        "role": "Ranks deterministic setups using score outputs",
        "icon": "🔭",
        "color": "#00d4ff",
        "system": """You are a swing trade scanner. Use ONLY the structured JSON fields provided. Do not invent prices or indicators. Rank the best 3-5 candidates using trend quality, base quality, Oliver Kell cycle, Jeff Sun extension metrics, market alignment, and event risk. Return ONLY valid JSON: {"candidates":[{"ticker":"AAPL","rank":1,"score":92.4,"setup":"Cycle 2 pullback","conviction":"High","rank_reason":"One sentence."}],"market_context":"One sentence."}"""
    },
    {
        "id": "kell_cycle",
        "name": "Oliver Kell Cycle Analyst",
        "role": "Classifies fresh breakout, first pullback, add-on, or late cycle",
        "icon": "🌀",
        "color": "#22c55e",
        "system": """You are an Oliver Kell style cycle analyst. Use ONLY supplied structured data. Prefer fresh breakouts and first pullbacks with tight action above key moving averages. Penalize late-stage, extended, loose, obvious names, and names near event risk. Return ONLY valid JSON: {"cycle_analysis":[{"ticker":"AAPL","cycle_stage":"First pullback","cycle_score":8.5,"entry_type":"21EMA pullback","too_extended":false,"too_late":false,"notes":"One sentence."}]}"""
    },
    {
        "id": "options_flow",
        "name": "Options Context Analyst",
        "role": "Reads option-chain snapshots from Massive starter options data",
        "icon": "⛓️",
        "color": "#38bdf8",
        "system": """You are an options context analyst. Use ONLY the supplied option chain summary and stock metrics. Assess whether options open interest, call/put distribution, and implied volatility context support or weaken the swing setup. Return ONLY valid JSON: {"options_context":[{"ticker":"AAPL","options_bias":"Bullish","iv_context":"Moderate","oi_signal":"Calls dominant near upside strikes","notes":"One sentence."}]}"""
    },
    {
        "id": "technicals",
        "name": "Technical Executor",
        "role": "Builds entry, stop, target from deterministic pivots and ATR",
        "icon": "📈",
        "color": "#7c3aed",
        "system": """You are a technical execution analyst. Use ONLY the exact prices and metrics in the JSON payload. Choose the best trigger type for each ticker: breakout, pullback, or add-on. Use the provided pivot, mini-pivot, ATR, MA, and structural levels. Return ONLY valid JSON: {"analysis":[{"ticker":"AAPL","entry_style":"Breakout","entry_price":187.32,"entry_zone":"186.90-187.50","stop_loss":183.80,"target_1":194.36,"target_2":199.64,"setup_quality":"A","notes":"One sentence."}]}"""
    },
    {
        "id": "risk",
        "name": "Risk Architect",
        "role": "Validates R multiples, dollar risk, and position sizing",
        "icon": "🛡️",
        "color": "#f59e0b",
        "system": """You are a risk manager. Use ONLY given entry, stop, and price metrics. Validate reward-to-risk, suggest size for fixed dollar risk, identify invalidation, and penalize setups with earnings/event risk. Return ONLY valid JSON: {"risk_plans":[{"ticker":"AAPL","entry":187.32,"stop_loss":183.80,"risk_per_share":3.52,"target_1":194.36,"target_2":199.64,"reward_risk_ratio":"2.0:1","position_size_1k_risk":284,"invalidation":"Daily close below 183.50","notes":"One sentence."}]}"""
    },
    {
        "id": "strategist",
        "name": "Head Strategist",
        "role": "Synthesizes final trade cards from deterministic numbers",
        "icon": "🎯",
        "color": "#ef4444",
        "system": """You are the head strategist. Use ONLY exact values from prior agent outputs. Do not invent numbers. Produce concise final swing-trade recommendations and explicitly respect event risk and options context. Return ONLY valid JSON: {"recommendations":[{"rank":1,"ticker":"AAPL","action":"BUY","buy_price":187.32,"stop_loss":183.80,"target_1":194.36,"target_2":199.64,"holding_period":"5-15 days","strategy":"Cycle 2 continuation","conviction":"High","grade":"A","entry_trigger":"Buy through pivot on strong volume","rationale":"Two short sentences.","key_risk":"One sentence."}],"portfolio_notes":"One sentence."}"""
    },
]


def massive_get(path, api_key):
    url = f"https://api.polygon.io{path}"
    sep = "&" if "?" in url else "?"
    req = urllib.request.Request(url + sep + f"apiKey={api_key}", headers={"User-Agent": "TradingTeamV21/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def extract_json_object(raw):
    raw = raw.strip().replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end+1])
        raise


def call_grok(api_key, system, payload):
    body = json.dumps({
        "model": "grok-3",
        "max_tokens": 2000,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, indent=2)},
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        XAI_CHAT_ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=70) as resp:
        data = json.loads(resp.read().decode())
    raw = data["choices"][0]["message"]["content"]
    return extract_json_object(raw)


def sma(values, period):
    if len(values) < period:
        return None
    return round(sum(values[-period:]) / period, 2)


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    out = sum(values[:period]) / period
    for p in values[period:]:
        out = p * k + out * (1 - k)
    return round(out, 2)


def atr_wilder(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    return round(atr, 2)


def rsi_wilder(closes, period=14):
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def nearest_support(lows, lookback=20):
    window = lows[-lookback:] if len(lows) >= lookback else lows
    return round(min(window), 2) if window else None


def volume_dryup(vols, lookback=10, baseline=50):
    if len(vols) < baseline:
        return None
    recent = sum(vols[-lookback:]) / min(lookback, len(vols))
    base = sum(vols[-baseline:]) / baseline
    return round(recent / base, 2) if base else None


def detect_vcp(highs, lows):
    if len(highs) < 25 or len(lows) < 25:
        return False, []
    r1 = max(highs[-25:-15]) - min(lows[-25:-15])
    r2 = max(highs[-15:-8]) - min(lows[-15:-8])
    r3 = max(highs[-8:]) - min(lows[-8:])
    return bool(r1 > r2 > r3), [round(r1, 2), round(r2, 2), round(r3, 2)]


def true_pivot(highs, closes, lookback=20):
    if len(highs) < lookback:
        return round(max(highs[:-1]), 2) if len(highs) > 1 else None
    window_highs = highs[-lookback:-1]
    return round(max(window_highs), 2) if window_highs else None


def mini_pivot(highs, lookback=5):
    if len(highs) < lookback:
        return None
    return round(max(highs[-lookback:-1]), 2) if len(highs[-lookback:-1]) else None


def weekly_series(closes, highs, lows, vols):
    wc, wh, wl, wv = [], [], [], []
    chunk = 5
    for i in range(0, len(closes), chunk):
        c = closes[i:i+chunk]
        h = highs[i:i+chunk]
        l = lows[i:i+chunk]
        v = vols[i:i+chunk]
        if not c:
            continue
        wc.append(c[-1])
        wh.append(max(h))
        wl.append(min(l))
        wv.append(sum(v))
    return wc, wh, wl, wv


def compute_relative_strength(stock_closes, bench_closes, lookback=63):
    if len(stock_closes) < lookback or len(bench_closes) < lookback:
        return None
    sr = stock_closes[-1] / stock_closes[-lookback]
    br = bench_closes[-1] / bench_closes[-lookback]
    return round(((sr / br) - 1) * 100, 2) if br else None


def compute_event_risk(days_to_earnings):
    if days_to_earnings is None:
        return {"earnings_days": None, "event_risk": "Unknown", "event_penalty": 1}
    if days_to_earnings <= 3:
        return {"earnings_days": days_to_earnings, "event_risk": "High", "event_penalty": -10}
    if days_to_earnings <= 7:
        return {"earnings_days": days_to_earnings, "event_risk": "Elevated", "event_penalty": -5}
    return {"earnings_days": days_to_earnings, "event_risk": "Low", "event_penalty": 0}


def compute_kell_cycle(d):
    price = d["price"]
    pivot = d.get("pivot_price")
    mini = d.get("mini_pivot")
    atr = d.get("atr14") or 0
    e10 = d.get("ema10")
    e21 = d.get("ema21")
    closes = d["closes"]
    highs = d["highs"]
    lows = d["lows"]
    base_lookback = min(40, len(closes))
    base_high = max(highs[-base_lookback:]) if base_lookback else price
    base_low = min(lows[-base_lookback:]) if base_lookback else price
    base_depth_pct = round(((base_high - base_low) / base_high) * 100, 2) if base_high else None

    breakout_idx = None
    if pivot:
        for i in range(max(0, len(closes) - 25), len(closes)):
            if closes[i] > pivot:
                breakout_idx = i
                break
    days_since_breakout = (len(closes) - 1 - breakout_idx) if breakout_idx is not None else None
    max_run_from_pivot_pct = round(((max(highs[breakout_idx:]) - pivot) / pivot) * 100, 2) if breakout_idx is not None and pivot else None
    pullback_depth_pct = round(((max(highs[-10:]) - min(lows[-10:])) / max(highs[-10:])) * 100, 2) if len(highs) >= 10 else None
    tight_closes_count = sum(1 for i in range(max(1, len(closes)-5), len(closes)) if abs(closes[i]-closes[i-1]) / closes[i-1] < 0.012)
    extended_from_pivot = round(((price - pivot) / pivot) * 100, 2) if pivot else None
    to_10 = round((price - e10) / atr, 2) if e10 and atr else None
    to_21 = round((price - e21) / atr, 2) if e21 and atr else None

    cycle_stage = "Base building"
    cycle_score = 5.0
    add_on_candidate = False
    too_extended = False
    too_late = False
    preferred_trigger = "None"

    if pivot and price > pivot:
        if days_since_breakout is not None and days_since_breakout <= 5 and (extended_from_pivot or 0) <= 8:
            cycle_stage = "Fresh breakout"
            cycle_score = 8.4
            preferred_trigger = "Pivot breakout"
        if days_since_breakout is not None and 3 <= days_since_breakout <= 15 and e10 and e21 and price >= e21 and (to_21 is not None and to_21 <= 1.2):
            cycle_stage = "First pullback"
            cycle_score = 9.0
            preferred_trigger = "10/21EMA pullback"
        if days_since_breakout is not None and days_since_breakout > 10 and tight_closes_count >= 3 and mini and price <= mini * 1.03:
            cycle_stage = "Add-on continuation"
            cycle_score = max(cycle_score, 8.1)
            preferred_trigger = "Mini-pivot add-on"
            add_on_candidate = True
    if extended_from_pivot is not None and extended_from_pivot > 12:
        too_extended = True
        cycle_score -= 1.5
    if max_run_from_pivot_pct is not None and max_run_from_pivot_pct > 20 and pullback_depth_pct and pullback_depth_pct > 12:
        too_late = True
        cycle_stage = "Late cycle / extended"
        cycle_score = min(cycle_score, 4.4)
        preferred_trigger = "Avoid"

    return {
        "base_depth_pct": base_depth_pct,
        "days_since_breakout": days_since_breakout,
        "max_run_from_pivot_pct": max_run_from_pivot_pct,
        "pullback_depth_pct": pullback_depth_pct,
        "tight_closes_count": tight_closes_count,
        "extended_from_pivot_pct": extended_from_pivot,
        "price_to_10ema_atr": to_10,
        "price_to_21ema_atr": to_21,
        "cycle_stage": cycle_stage,
        "cycle_score": round(cycle_score, 2),
        "add_on_candidate": add_on_candidate,
        "too_extended": too_extended,
        "too_late": too_late,
        "preferred_trigger": preferred_trigger,
    }


def compute_jeff_sun_metrics(d):
    price = d["price"]
    atr = d.get("atr14") or 0
    sma50 = d.get("sma50")
    sma150 = d.get("sma150")
    sma200 = d.get("sma200")
    rvol = d.get("rvol")
    out = {}
    if atr and sma50:
        out["atr_multiple_from_50ma"] = round((price - sma50) / atr, 2)
        out["atr_percent_of_50ma"] = round((atr / sma50) * 100, 2)
    else:
        out["atr_multiple_from_50ma"] = None
        out["atr_percent_of_50ma"] = None
    out["pct_from_50ma"] = round(((price - sma50) / sma50) * 100, 2) if sma50 else None
    out["pct_from_150ma"] = round(((price - sma150) / sma150) * 100, 2) if sma150 else None
    out["pct_from_200ma"] = round(((price - sma200) / sma200) * 100, 2) if sma200 else None
    out["rvol"] = rvol
    m = out["atr_multiple_from_50ma"]
    if m is None:
        out["extension_label"] = "Insufficient data"
    elif m < -1:
        out["extension_label"] = "Below 50MA"
    elif m <= 1.5:
        out["extension_label"] = "Near 50MA"
    elif m <= 3.0:
        out["extension_label"] = "Extended but workable"
    else:
        out["extension_label"] = "Hot / extended"
    return out


def summarize_option_chain(chain):
    results = chain.get("results", []) if isinstance(chain, dict) else []
    if not results:
        return {"contracts": 0}
    call_oi = put_oi = 0
    call_vol = put_vol = 0
    ivs = []
    nearest_exp = None
    sample = []
    for c in results[:200]:
        details = c.get("details", {})
        oi = c.get("open_interest") or 0
        day = c.get("day", {})
        vol = day.get("volume") or 0
        iv = c.get("implied_volatility")
        exp = details.get("expiration_date")
        if exp and (nearest_exp is None or exp < nearest_exp):
            nearest_exp = exp
        if details.get("contract_type") == "call":
            call_oi += oi
            call_vol += vol
        elif details.get("contract_type") == "put":
            put_oi += oi
            put_vol += vol
        if iv is not None:
            ivs.append(iv)
        if len(sample) < 5:
            sample.append({
                "type": details.get("contract_type"),
                "strike": details.get("strike_price"),
                "exp": exp,
                "oi": oi,
                "vol": vol,
            })
    total_oi = call_oi + put_oi
    return {
        "contracts": len(results),
        "nearest_expiration": nearest_exp,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_put_oi_ratio": round(call_oi / put_oi, 2) if put_oi else None,
        "call_volume": call_vol,
        "put_volume": put_vol,
        "call_put_volume_ratio": round(call_vol / put_vol, 2) if put_vol else None,
        "avg_iv": round(sum(ivs) / len(ivs), 4) if ivs else None,
        "sample_contracts": sample,
        "dominance": "Calls" if call_oi > put_oi else "Puts" if put_oi > call_oi else "Balanced",
        "total_oi": total_oi,
    }


def compute_score(d):
    price = d["price"]
    trend = base = cycle = volume = risk = market = 0
    if d.get("sma50") and d.get("sma150") and d.get("sma200"):
        if price > d["sma50"] > d["sma150"] > d["sma200"]:
            trend += 25
        elif price > d["sma50"] > d["sma200"]:
            trend += 18
        elif price > d["sma50"]:
            trend += 12
    if d.get("weekly_sma10") and d.get("weekly_sma30") and d["weekly_sma10"] > d["weekly_sma30"]:
        trend += 6
    if d.get("ema10") and d.get("ema21") and d.get("ema50") and price > d["ema10"] > d["ema21"] > d["ema50"]:
        trend += 8
    if d.get("vcp_contracting"):
        base += 10
    if d.get("volume_dryup_10v50") is not None and d["volume_dryup_10v50"] < 0.85:
        base += 5
    if d.get("base_depth_pct") is not None and d["base_depth_pct"] < 30:
        base += 5
    if d.get("mini_pivot") and d.get("pivot_price") and d["mini_pivot"] <= d["pivot_price"]:
        base += 2
    cycle += min(20, d.get("cycle_score", 0) * 2)
    if d.get("too_extended"):
        cycle -= 5
    if d.get("too_late"):
        cycle -= 7
    if d.get("rvol") is not None:
        if d["rvol"] >= 1.5:
            volume += 10
        elif d["rvol"] >= 1.0:
            volume += 6
        elif d["rvol"] >= 0.7:
            volume += 3
    if d.get("change_pct") and d["change_pct"] > 0:
        volume += 5
    if d.get("atr_multiple_from_50ma") is not None:
        m = d["atr_multiple_from_50ma"]
        if -0.5 <= m <= 2.5:
            risk += 8
        elif m <= 3.5:
            risk += 5
        else:
            risk += 1
    if d.get("rsi14") is not None and 50 <= d["rsi14"] <= 72:
        risk += 7
    elif d.get("rsi14") is not None and 40 <= d["rsi14"] < 50:
        risk += 4
    if d.get("rs_vs_spy_63d") is not None and d["rs_vs_spy_63d"] > 0:
        market += 5
    if d.get("pct_from_200ma") is not None and d["pct_from_200ma"] > 0:
        market += 5
    market += d.get("event_penalty", 0)
    if d.get("options_summary", {}).get("dominance") == "Calls":
        market += 2
    return round(trend + base + cycle + volume + risk + market, 2)


def fetch_stock_snapshot(ticker, api_key):
    return massive_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", api_key)


def fetch_daily_bars(ticker, api_key):
    end = datetime.utcnow().strftime("%Y-%m-%d")
    start = (datetime.utcnow() - timedelta(days=430)).strftime("%Y-%m-%d")
    return massive_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=500", api_key)


def fetch_option_chain_snapshot(ticker, api_key, limit=120):
    try:
        return massive_get(f"/v3/snapshot/options/{ticker}?limit={limit}&sort=strike_price&order=asc", api_key)
    except Exception as e:
        return {"error": str(e), "results": []}


def fetch_benchmark_series(ticker, api_key):
    bars = fetch_daily_bars(ticker, api_key)
    return [b["c"] for b in bars.get("results", [])]


def fetch_ticker_data(ticker, api_key, benchmark_closes=None, earnings_days=None, include_options=True):
    result = {"ticker": ticker, "error": None}
    try:
        snap = fetch_stock_snapshot(ticker, api_key)
        t = snap.get("ticker", {})
        day = t.get("day", {})
        prev = t.get("prevDay", {})
        result["price"] = day.get("c") or prev.get("c", 0)
        result["open"] = day.get("o", 0)
        result["high"] = day.get("h", 0)
        result["low"] = day.get("l", 0)
        result["volume"] = day.get("v", 0)
        result["prev_close"] = prev.get("c", 0)
        result["todays_change_pct"] = t.get("todaysChangePerc")
        result["updated"] = t.get("updated")
        result["change_pct"] = round(((result["price"] - result["prev_close"]) / result["prev_close"] * 100), 2) if result["prev_close"] else 0

        bars = fetch_daily_bars(ticker, api_key)
        rb = bars.get("results", [])
        if len(rb) < 40:
            raise ValueError("Not enough daily bars returned")
        closes = [b["c"] for b in rb]
        highs = [b["h"] for b in rb]
        lows = [b["l"] for b in rb]
        vols = [b["v"] for b in rb]
        result["closes"] = closes
        result["highs"] = highs
        result["lows"] = lows
        result["volumes"] = vols
        result["bars_count"] = len(rb)
        result["high_52w"] = round(max(highs[-252:]), 2) if len(highs) >= 252 else round(max(highs), 2)
        result["low_52w"] = round(min(lows[-252:]), 2) if len(lows) >= 252 else round(min(lows), 2)
        result["avg_vol_20"] = round(sum(vols[-20:]) / min(20, len(vols)), 0)
        result["avg_vol_50"] = round(sum(vols[-50:]) / min(50, len(vols)), 0)
        result["rvol"] = round(result["volume"] / result["avg_vol_20"], 2) if result["avg_vol_20"] else None
        result["volume_dryup_10v50"] = volume_dryup(vols)
        result["atr14"] = atr_wilder(highs, lows, closes, 14)
        result["rsi14"] = rsi_wilder(closes, 14)
        result["ema10"] = ema(closes, 10)
        result["ema21"] = ema(closes, 21)
        result["ema50"] = ema(closes, 50)
        result["sma50"] = sma(closes, 50)
        result["sma150"] = sma(closes, 150)
        result["sma200"] = sma(closes, 200)
        result["pct_from_high_52w"] = round(((result["price"] - result["high_52w"]) / result["high_52w"]) * 100, 2) if result["high_52w"] else None
        result["pivot_price"] = true_pivot(highs, closes, 20)
        result["mini_pivot"] = mini_pivot(highs, 5)
        result["support_20d"] = nearest_support(lows, 20)
        vcp, ranges = detect_vcp(highs, lows)
        result["vcp_contracting"] = vcp
        result["vcp_ranges"] = ranges

        if result["ema10"] and result["ema21"] and result["ema50"]:
            p, e10, e21, e50 = result["price"], result["ema10"], result["ema21"], result["ema50"]
            if p > e10 > e21 > e50:
                result["ema_alignment"] = "Bullish stack"
            elif p < e10 < e21 < e50:
                result["ema_alignment"] = "Bearish stack"
            elif p > e21 > e50:
                result["ema_alignment"] = "Bullish above 21/50"
            else:
                result["ema_alignment"] = "Mixed"
        else:
            result["ema_alignment"] = "Insufficient data"

        if result["sma50"] and result["sma150"] and result["sma200"]:
            p, s50, s150, s200 = result["price"], result["sma50"], result["sma150"], result["sma200"]
            if p > s50 > s150 > s200:
                result["stage"] = "Stage 2"
            elif p < s50 < s150 < s200:
                result["stage"] = "Stage 4"
            elif p > s200:
                result["stage"] = "Stage 1/2"
            else:
                result["stage"] = "Stage 3/4"
        else:
            result["stage"] = "Unknown"

        wc, wh, wl, wv = weekly_series(closes, highs, lows, vols)
        result["weekly_sma10"] = sma(wc, 10)
        result["weekly_sma30"] = sma(wc, 30)
        result["weekly_rsi14"] = rsi_wilder(wc, 14) if len(wc) >= 15 else None
        if benchmark_closes:
            result["rs_vs_spy_63d"] = compute_relative_strength(closes, benchmark_closes, 63)
        else:
            result["rs_vs_spy_63d"] = None

        result.update(compute_kell_cycle(result))
        result.update(compute_jeff_sun_metrics(result))
        result.update(compute_event_risk(earnings_days))

        if include_options:
            chain = fetch_option_chain_snapshot(ticker, api_key)
            result["options_summary"] = summarize_option_chain(chain)
            result["options_error"] = chain.get("error") if isinstance(chain, dict) else None
        else:
            result["options_summary"] = {"contracts": 0}
            result["options_error"] = None

        result["quant_score"] = compute_score(result)
    except Exception as e:
        result["error"] = str(e)
    return result


def compact_payload(data):
    keys = [
        "ticker", "price", "change_pct", "stage", "ema_alignment", "rsi14", "atr14", "rvol",
        "high_52w", "pct_from_high_52w", "ema10", "ema21", "ema50", "sma50", "sma150", "sma200",
        "pivot_price", "mini_pivot", "support_20d", "vcp_contracting", "vcp_ranges", "volume_dryup_10v50",
        "cycle_stage", "cycle_score", "days_since_breakout", "max_run_from_pivot_pct", "pullback_depth_pct",
        "tight_closes_count", "too_extended", "too_late", "preferred_trigger", "atr_multiple_from_50ma",
        "atr_percent_of_50ma", "pct_from_50ma", "pct_from_150ma", "pct_from_200ma", "extension_label",
        "weekly_sma10", "weekly_sma30", "weekly_rsi14", "rs_vs_spy_63d", "earnings_days", "event_risk",
        "options_summary", "quant_score"
    ]
    return {t: {k: d.get(k) for k in keys} for t, d in data.items()}


def build_trade_levels(d):
    atr = d.get("atr14") or 0
    trigger = d.get("preferred_trigger") or "Pivot breakout"
    if trigger == "10/21EMA pullback" and d.get("ema21"):
        entry = round(max(d["ema21"], d["price"]) + atr * 0.15, 2)
    elif trigger == "Mini-pivot add-on" and d.get("mini_pivot"):
        entry = round(d["mini_pivot"] + atr * 0.1, 2)
    else:
        entry = round((d.get("pivot_price") or d["price"]) + atr * 0.1, 2)
    stop_ema = d.get("ema21")
    stop_atr = round(entry - atr * 1.5, 2) if atr else None
    structural = d.get("support_20d")
    stop_candidates = [x for x in [stop_ema, stop_atr, structural] if x is not None and x < entry]
    stop = round(max(stop_candidates), 2) if stop_candidates else round(entry * 0.95, 2)
    rps = round(entry - stop, 2)
    t1 = round(entry + rps * 2, 2)
    t2 = round(entry + rps * 3.5, 2)
    rr = round((t1 - entry) / rps, 2) if rps > 0 else None
    return {"entry": entry, "stop": stop, "risk_per_share": rps, "target_1": t1, "target_2": t2, "rr": rr}


def trade_card(trade):
    grade = trade.get("grade", "B")
    color = GRADE_COLORS.get(grade, "#64748b")
    st.markdown(f"""
    <div class='trade-card'>
      <div style='display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:12px;'>
        <div style='display:flex;align-items:center;gap:10px;'>
          <span style='background:{color};color:#000;padding:2px 8px;border-radius:6px;font-weight:800;' class='mono'>#{trade.get("rank","")}</span>
          <span class='mono' style='font-size:22px;font-weight:800;color:#f8fafc;'>{trade.get("ticker","")}</span>
          <span style='padding:2px 8px;border-radius:999px;border:1px solid #14532d;background:#052e16;color:#4ade80;font-size:11px;'>{trade.get("action","BUY")}</span>
        </div>
        <div style='padding:3px 10px;border-radius:999px;border:1px solid {color}66;color:{color};' class='mono'>{grade}</div>
      </div>
      <div style='display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px;'>
        <div class='kpi'><div class='small-label'>Buy</div><div class='mono' style='font-size:18px;color:#38bdf8;'>${trade.get("buy_price","")}</div></div>
        <div class='kpi'><div class='small-label'>Stop</div><div class='mono bad' style='font-size:18px;'>${trade.get("stop_loss","")}</div></div>
        <div class='kpi'><div class='small-label'>Target 1</div><div class='mono good' style='font-size:18px;'>${trade.get("target_1","")}</div></div>
        <div class='kpi'><div class='small-label'>Target 2</div><div class='mono good' style='font-size:18px;'>${trade.get("target_2","")}</div></div>
      </div>
      <div style='margin-bottom:8px;'><span class='small-label'>Trigger</span><div style='color:#cbd5e1'>{trade.get("entry_trigger","")}</div></div>
      <div style='color:#94a3b8;margin-bottom:8px;'>{trade.get("rationale","")}</div>
      <div style='display:flex;flex-wrap:wrap;gap:8px;'>
        <span class='tag'>⏱ {trade.get("holding_period","")}</span>
        <span class='tag'>📊 {trade.get("strategy","")}</span>
        <span class='tag'>⚠ {trade.get("key_risk","")}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def main():
    st.markdown("<div class='small-label'>MULTI-AGENT SYSTEM · DETERMINISTIC ANALYTICS</div>", unsafe_allow_html=True)
    st.markdown("<div class='title-lg'>AI Trading Team v2.1</div>", unsafe_allow_html=True)
    st.markdown("<div class='muted'>xAI chat completions endpoint included · Massive.com starter stocks + options context · Oliver Kell cycle · Jeff Sun ATR% extension metrics</div>", unsafe_allow_html=True)
    st.markdown("---")

    secrets = st.secrets if hasattr(st, "secrets") else {}
    c1, c2 = st.columns(2)
    with c1:
        grok_secret = secrets.get("GROK_API_KEY", "")
        grok_key = grok_secret if grok_secret else st.text_input("Grok API Key", type="password", placeholder="xai-...")
    with c2:
        poly_secret = secrets.get("POLYGON_API_KEY", "")
        poly_key = poly_secret if poly_secret else st.text_input("Massive / Polygon API Key", type="password", placeholder="Polygon key...")

    c3, c4, c5 = st.columns([5, 2, 2])
    with c3:
        watchlist_raw = st.text_area("Watchlist", value="NVDA, AAPL, MSFT, META, AMD, TSLA, AVGO, SMCI", height=70)
    with c4:
        sector = st.selectbox("Sector", ["Technology", "Healthcare", "Financials", "Energy", "Consumer", "Industrials", "Mixed"])
    with c5:
        dollar_risk = st.number_input("$ Risk per trade", min_value=100, value=1000, step=100)

    c6, c7, c8 = st.columns(3)
    with c6:
        use_ai = st.toggle("Run Grok synthesis agents", value=True)
    with c7:
        include_options = st.toggle("Use Massive options context", value=True)
    with c8:
        default_earnings_days = st.number_input("Default days to earnings", min_value=0, value=10, step=1)

    tickers = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
    ready = bool(poly_key and tickers and ((use_ai and grok_key) or not use_ai))
    run = st.button("▶ Deploy Trading Team v2.1", disabled=not ready, use_container_width=True)

    st.markdown(f"<div class='panel'><div class='small-label'>API configuration</div><div class='muted'>xAI endpoint: <span class='mono'>{XAI_CHAT_ENDPOINT}</span><br>Massive starter support: stock snapshots/aggs plus options chain snapshot requests when available on your package.</div></div>", unsafe_allow_html=True)

    if not run:
        return

    spy_closes = []
    try:
        spy_closes = fetch_benchmark_series("SPY", poly_key)
    except Exception:
        spy_closes = []

    progress = st.progress(0)
    status = st.empty()
    market_data = {}
    for i, ticker in enumerate(tickers, start=1):
        status.info(f"Fetching {ticker}...")
        market_data[ticker] = fetch_ticker_data(
            ticker,
            poly_key,
            benchmark_closes=spy_closes,
            earnings_days=default_earnings_days,
            include_options=include_options,
        )
        progress.progress(i / len(tickers))

    valid = {k: v for k, v in market_data.items() if not v.get("error")}
    invalid = {k: v for k, v in market_data.items() if v.get("error")}
    for t, d in invalid.items():
        st.error(f"{t}: {d['error']}")
    if not valid:
        st.stop()

    ranked = sorted(valid.values(), key=lambda x: x.get("quant_score", 0), reverse=True)
    top = ranked[:min(5, len(ranked))]
    compact = compact_payload({d["ticker"]: d for d in top})

    st.subheader("Quant dashboard")
    table_rows = []
    for d in ranked:
        osum = d.get("options_summary", {})
        table_rows.append({
            "Ticker": d["ticker"],
            "Score": d.get("quant_score"),
            "Stage": d.get("stage"),
            "Cycle": d.get("cycle_stage"),
            "Trigger": d.get("preferred_trigger"),
            "Price": d.get("price"),
            "Pivot": d.get("pivot_price"),
            "MiniPivot": d.get("mini_pivot"),
            "ATR": d.get("atr14"),
            "RSI": d.get("rsi14"),
            "RVol": d.get("rvol"),
            "ATRx50": d.get("atr_multiple_from_50ma"),
            "RS vs SPY": d.get("rs_vs_spy_63d"),
            "Event": d.get("event_risk"),
            "OptBias": osum.get("dominance"),
            "CP OI": osum.get("call_put_oi_ratio"),
        })
    st.dataframe(table_rows, use_container_width=True, hide_index=True)

    st.subheader("Top setups")
    precomputed_levels = {}
    for d in top:
        levels = build_trade_levels(d)
        precomputed_levels[d["ticker"]] = levels
        size = math.floor(dollar_risk / levels["risk_per_share"]) if levels["risk_per_share"] > 0 else 0
        osum = d.get("options_summary", {})
        st.markdown(f"""
        <div class='panel'>
          <div style='display:flex;justify-content:space-between;align-items:flex-start;gap:12px;'>
            <div>
              <div class='small-label'>{d['stage']} · score {d['quant_score']}</div>
              <div class='mono' style='font-size:24px;font-weight:800;color:#f8fafc;'>{d['ticker']}</div>
              <div class='muted'>{d['cycle_stage']} · {d['extension_label']} · event {d.get('event_risk')}</div>
            </div>
            <div>
              <span class='tag'>RVol {d.get('rvol')}</span>
              <span class='tag'>RSvsSPY {d.get('rs_vs_spy_63d')}</span>
              <span class='tag'>ATRx50 {d.get('atr_multiple_from_50ma')}</span>
              <span class='tag'>Opt {osum.get('dominance')}</span>
            </div>
          </div>
          <div style='display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:10px;margin-top:12px;'>
            <div class='kpi'><div class='small-label'>Price</div><div class='mono'>${d['price']}</div></div>
            <div class='kpi'><div class='small-label'>Pivot</div><div class='mono'>${d.get('pivot_price')}</div></div>
            <div class='kpi'><div class='small-label'>Entry</div><div class='mono'>${levels['entry']}</div></div>
            <div class='kpi'><div class='small-label'>Stop</div><div class='mono bad'>${levels['stop']}</div></div>
            <div class='kpi'><div class='small-label'>1k Size</div><div class='mono'>{size}</div></div>
          </div>
          <div style='margin-top:12px;display:flex;flex-wrap:wrap;'>
            <span class='tag'>T1 ${levels['target_1']}</span>
            <span class='tag'>T2 ${levels['target_2']}</span>
            <span class='tag'>Risk/share ${levels['risk_per_share']}</span>
            <span class='tag'>R:R {levels['rr']}:1</span>
            <span class='tag'>Days to earnings {d.get('earnings_days')}</span>
            <span class='tag'>Call/Put OI {osum.get('call_put_oi_ratio')}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    if not use_ai:
        st.subheader("Structured payload")
        st.code(json.dumps(compact, indent=2), language="json")
        return

    results = {}
    agent_status = st.empty()

    def run_agent(agent_id, payload):
        agent = next(a for a in AGENTS if a["id"] == agent_id)
        agent_status.info(f"{agent['icon']} {agent['name']} running...")
        out = call_grok(grok_key, agent["system"], payload)
        results[agent_id] = out
        return out

    scanner = run_agent("scanner", {"sector": sector, "tickers": compact})
    kell = run_agent("kell_cycle", {"tickers": compact, "scanner": scanner})
    options_context = run_agent("options_flow", {"tickers": compact}) if include_options else {"options_context": []}

    selected_tickers = [c["ticker"] for c in scanner.get("candidates", []) if c.get("ticker") in compact]
    selected = {t: compact[t] for t in selected_tickers} if selected_tickers else compact
    analysis_input = []
    for t in selected:
        levels = precomputed_levels[t]
        analysis_input.append({
            **selected[t],
            "precomputed_entry": levels["entry"],
            "precomputed_stop": levels["stop"],
            "precomputed_risk_per_share": levels["risk_per_share"],
            "precomputed_target_1": levels["target_1"],
            "precomputed_target_2": levels["target_2"],
        })

    technicals = run_agent("technicals", {"analysis_input": analysis_input, "kell": kell, "options_context": options_context})
    risk = run_agent("risk", {"analysis": technicals, "dollar_risk": dollar_risk})
    strategist = run_agent("strategist", {
        "scanner": scanner,
        "kell": kell,
        "options_context": options_context,
        "technicals": technicals,
        "risk": risk,
    })
    agent_status.success("All agents complete.")

    st.subheader("Agent synthesis")
    for trade in strategist.get("recommendations", []):
        trade_card(trade)
    if strategist.get("portfolio_notes"):
        st.markdown(f"<div class='panel'><div class='small-label'>Portfolio notes</div><div class='muted'>{strategist['portfolio_notes']}</div></div>", unsafe_allow_html=True)

    with st.expander("Debug JSON"):
        st.code(json.dumps({
            "scanner": scanner,
            "kell_cycle": kell,
            "options_context": options_context,
            "technicals": technicals,
            "risk": risk,
            "strategist": strategist,
        }, indent=2), language="json")

    st.caption("For educational purposes only. Not financial advice.")


if __name__ == "__main__":
    main()
