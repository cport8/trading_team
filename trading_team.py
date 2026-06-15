import streamlit as st
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from statistics import mean

st.set_page_config(
    page_title="AI Trading Team v2.3",
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
  .header-sub   { font-size: 13px; color: #64748b; text-align: center; margin-top: 4px; margin-bottom: 20px; }
  div[data-testid="stTextArea"] textarea { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; font-family: monospace !important; font-size: 13px !important; }
  div[data-testid="stSelectbox"] > div  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  div[data-testid="stTextInput"] input  { background: #0f172a !important; border: 1px solid #334155 !important; color: #f1f5f9 !important; }
  .stButton > button { width:100%; background:transparent !important; border:1px solid #00d4ff44 !important; color:#00d4ff !important; font-family:monospace !important; font-weight:700 !important; letter-spacing:1px !important; font-size:14px !important; padding:12px !important; border-radius:8px !important; }
  .stButton > button:hover { background:#00d4ff11 !important; border-color:#00d4ff !important; }
</style>
""", unsafe_allow_html=True)

GRADE_COLORS = {"A+": "#10b981", "A": "#22c55e", "B+": "#84cc16", "B": "#eab308", "C": "#f97316", "D": "#ef4444"}

AGENTS = [
    {
        "id": "scanner",
        "name": "Quant Scanner",
        "role": "Deterministic scoring + top candidate ranking",
        "icon": "🔭",
        "color": "#00d4ff",
        "system": """You are a quant swing-trade scanner. Use ONLY the structured JSON payload provided. Do not invent prices. Favor Stage 2 trends, strong moving-average alignment, constructive volume, VCP/base behavior, Oliver Kell cycle quality, and manageable extension from the 50MA. Return ONLY valid JSON:
{"candidates":[{"ticker":"NVDA","score":92.4,"conviction":"High","setup":"Fresh breakout","rank_reason":"One concise sentence"}],"market_context":"One sentence."}"""
    },
    {
        "id": "kell_cycle",
        "name": "Oliver Kell Cycle Analyst",
        "role": "Classifies post-breakout cycle stage",
        "icon": "🌀",
        "color": "#22c55e",
        "system": """You are an Oliver Kell-style cycle analyst. Use ONLY the structured JSON fields provided. Determine whether each ticker is in Base building, Fresh breakout, First pullback, Add-on continuation, or Late cycle / extended. Prefer first pullbacks to the 10EMA/21EMA after a valid breakout, tight closes, and controlled volume contraction. Return ONLY valid JSON:
{"cycle_analysis":[{"ticker":"NVDA","cycle_stage":"First pullback","cycle_score":8.8,"entry_type":"21EMA pullback buy","too_extended":false,"too_late":false,"notes":"One concise sentence."}]}"""
    },
    {
        "id": "technicals",
        "name": "Technical Executor",
        "role": "Entry, stop, trigger, resistance, support",
        "icon": "📈",
        "color": "#7c3aed",
        "system": """You are a technical execution analyst. Use ONLY the exact values from the structured JSON. Do not invent numbers outside the provided data and obvious arithmetic. Prefer breakout, pullback, and add-on entries based on pivot, ATR, and moving-average support. Return ONLY valid JSON:
{"analysis":[{"ticker":"NVDA","current_price":145.22,"entry_type":"Breakout","pivot_price":146.1,"entry_price":146.42,"entry_zone":"146.10 - 146.70","stop_loss":141.8,"key_support":141.6,"key_resistance":152.4,"setup_quality":"A","notes":"One concise sentence."}]}"""
    },
    {
        "id": "risk",
        "name": "Risk Architect",
        "role": "Sizing, targets, invalidation, risk model",
        "icon": "🛡️",
        "color": "#f59e0b",
        "system": """You are a swing-trade risk manager. Use ONLY the structured technical outputs provided. Calculate risk per share, target_1 at 2R, target_2 at 3.5R, and position size for a $1000 account risk. Return ONLY valid JSON:
{"risk_plans":[{"ticker":"NVDA","entry":146.42,"stop_loss":141.8,"risk_per_share":4.62,"target_1":155.66,"target_2":162.59,"reward_risk_ratio":"2.0:1","position_size_1k_risk":216,"invalidation":"One sentence.","stop_rationale":"One sentence."}]}"""
    },
    {
        "id": "strategist",
        "name": "Head Strategist",
        "role": "Final ranked trade cards",
        "icon": "🎯",
        "color": "#ef4444",
        "system": """You are the head strategist. Use ONLY exact numbers from prior structured outputs. Do not change entry, stop, or target values. Rank the best swing opportunities and summarize the setup using real data points from the payload. Return ONLY valid JSON:
{"recommendations":[{"rank":1,"ticker":"NVDA","action":"BUY","buy_price":146.42,"stop_loss":141.8,"target_1":155.66,"target_2":162.59,"holding_period":"5-15 days","strategy":"Fresh breakout swing","conviction":"High","grade":"A","rationale":"Two concise sentences.","entry_trigger":"One concise sentence.","key_risk":"One concise sentence."}],"portfolio_notes":"One sentence."}"""
    },
]


def massive_get(path, poly_key):
    url = f"https://api.polygon.io{path}"
    sep = "&" if "?" in url else "?"
    url = f"{url}{sep}apiKey={poly_key}"
    req = urllib.request.Request(url, headers={"User-Agent": "TradingTeamV2/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())


def safe_round(value, digits=2):
    return round(value, digits) if value is not None else None


def sma(values, period):
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def ema(values, period):
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for price in values[period:]:
        e = price * k + e * (1 - k)
    return e


def wilder_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def wilder_atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return None
    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    atr = sum(trs[:period]) / period
    for tr in trs[period:]:
        atr = ((atr * (period - 1)) + tr) / period
    return atr


def percentile_rank(series, value):
    if not series:
        return None
    count = sum(1 for x in series if x <= value)
    return 100 * count / len(series)


def classify_stage(price, sma50_v, sma150_v, sma200_v, ema10_v, ema21_v):
    if None in (sma50_v, sma150_v, sma200_v, ema10_v, ema21_v):
        return "Unknown"
    if price > sma50_v > sma150_v > sma200_v and ema10_v > ema21_v > sma50_v:
        return "Stage 2 (Uptrend)"
    if price < sma50_v < sma150_v < sma200_v and ema10_v < ema21_v < sma50_v:
        return "Stage 4 (Downtrend)"
    if price > sma50_v and sma50_v >= sma150_v:
        return "Stage 1/2"
    return "Stage 3/4"


def compute_vcp(highs, lows, vols):
    if len(highs) < 30 or len(lows) < 30:
        return False, [], None
    windows = [(30, 20), (20, 10), (10, 5)]
    ranges = []
    for a, b in windows:
        h = max(highs[-a:-b])
        l = min(lows[-a:-b])
        ranges.append(h - l)
    contracting = ranges[0] > ranges[1] > ranges[2]
    recent_vol = vols[-5:] if len(vols) >= 5 else vols
    prior_vol = vols[-20:-5] if len(vols) >= 20 else vols[:-5]
    dry_up = (sum(recent_vol) / len(recent_vol)) / (sum(prior_vol) / len(prior_vol)) if recent_vol and prior_vol else None
    return contracting, [safe_round(x, 2) for x in ranges], safe_round(dry_up, 2) if dry_up is not None else None


def find_recent_pivot(highs, lookback=20):
    if len(highs) < lookback:
        return max(highs) if highs else None
    return max(highs[-lookback:])


def recent_support(lows, period=10):
    if len(lows) < period:
        return min(lows) if lows else None
    return min(lows[-period:])


def tight_closes_count(closes, atr, bars=10):
    if atr is None or len(closes) < bars:
        return 0
    cnt = 0
    recent = closes[-bars:]
    for i in range(1, len(recent)):
        if abs(recent[i] - recent[i - 1]) <= atr * 0.35:
            cnt += 1
    return cnt


def compute_jeff_sun_metrics(price, atr14, sma50_v, sma150_v, sma200_v, volume, avg_vol_20):
    atr_multiple_from_50ma = None
    if atr14 and sma50_v:
        atr_multiple_from_50ma = (price - sma50_v) / atr14
    rvol = (volume / avg_vol_20) if avg_vol_20 else None
    pct_from_50ma = ((price - sma50_v) / sma50_v * 100) if sma50_v else None
    pct_from_150ma = ((price - sma150_v) / sma150_v * 100) if sma150_v else None
    pct_from_200ma = ((price - sma200_v) / sma200_v * 100) if sma200_v else None

    extension_label = "Unknown"
    if sma50_v is None:
        extension_label = "Unknown"
    elif price < sma50_v:
        extension_label = "Below 50MA"
    elif atr_multiple_from_50ma is not None and atr_multiple_from_50ma <= 1.5:
        extension_label = "Near 50MA"
    elif atr_multiple_from_50ma is not None and atr_multiple_from_50ma <= 3.0:
        extension_label = "Extended but workable"
    elif atr_multiple_from_50ma is not None:
        extension_label = "Hot / extended"

    return {
        "atr_multiple_from_50ma": safe_round(atr_multiple_from_50ma, 2),
        "atr_percent_of_50ma": safe_round((atr14 / sma50_v * 100), 2) if atr14 and sma50_v else None,
        "pct_from_50ma": safe_round(pct_from_50ma, 2),
        "pct_from_150ma": safe_round(pct_from_150ma, 2),
        "pct_from_200ma": safe_round(pct_from_200ma, 2),
        "rvol": safe_round(rvol, 2),
        "extension_label": extension_label,
    }


def compute_kell_cycle(price, closes, highs, lows, volumes, atr14, ema10_v, ema21_v, pivot_price):
    breakout_threshold = pivot_price * 1.002 if pivot_price else None
    days_since_breakout = None
    breakout_index = None
    if breakout_threshold is not None:
        for i in range(len(closes) - 1, -1, -1):
            if closes[i] > breakout_threshold:
                breakout_index = i
            else:
                break
        if breakout_index is None:
            for i, c in enumerate(closes):
                if c > breakout_threshold:
                    breakout_index = i
                    break
        if breakout_index is not None:
            days_since_breakout = len(closes) - 1 - breakout_index

    max_run_from_pivot_pct = ((max(highs[-30:]) - pivot_price) / pivot_price * 100) if pivot_price and len(highs) >= 30 else None
    pullback_depth_pct = ((max(highs[-10:]) - min(lows[-10:])) / max(highs[-10:]) * 100) if len(highs) >= 10 else None
    extended_from_pivot_pct = ((price - pivot_price) / pivot_price * 100) if pivot_price else None
    dist_to_10ema_atr = ((price - ema10_v) / atr14) if atr14 and ema10_v else None
    dist_to_21ema_atr = ((price - ema21_v) / atr14) if atr14 and ema21_v else None
    closes_above_pivot = sum(1 for c in closes[-10:] if pivot_price and c > pivot_price)
    tight_count = tight_closes_count(closes, atr14, 10)

    stage = "Base building"
    entry_type = "Watch for pivot"
    too_extended = False
    too_late = False

    if breakout_index is not None and days_since_breakout is not None:
        if days_since_breakout <= 5 and (extended_from_pivot_pct or 0) <= 8:
            stage = "Fresh breakout"
            entry_type = "Breakout buy"
        elif days_since_breakout <= 20 and ema10_v and ema21_v and price >= ema21_v and (extended_from_pivot_pct or 0) <= 12:
            stage = "First pullback"
            entry_type = "10EMA/21EMA pullback buy"
        elif days_since_breakout <= 35 and tight_count >= 4 and closes_above_pivot >= 5:
            stage = "Add-on continuation"
            entry_type = "Mini-pivot add-on"
        else:
            stage = "Late cycle / extended"
            entry_type = "Avoid or only tactical"

    if dist_to_10ema_atr is not None and dist_to_10ema_atr > 3:
        too_extended = True
    if extended_from_pivot_pct is not None and extended_from_pivot_pct > 15:
        too_extended = True
    if days_since_breakout is not None and days_since_breakout > 35:
        too_late = True

    cycle_score = 5.0
    if stage == "Fresh breakout":
        cycle_score = 8.7
    elif stage == "First pullback":
        cycle_score = 9.1
    elif stage == "Add-on continuation":
        cycle_score = 8.2
    elif stage == "Base building":
        cycle_score = 6.0
    else:
        cycle_score = 4.5
    if too_extended:
        cycle_score -= 1.5
    if too_late:
        cycle_score -= 1.0

    return {
        "cycle_stage": stage,
        "entry_type": entry_type,
        "days_since_breakout": days_since_breakout,
        "max_run_from_pivot_pct": safe_round(max_run_from_pivot_pct, 2),
        "pullback_depth_pct": safe_round(pullback_depth_pct, 2),
        "extended_from_pivot_pct": safe_round(extended_from_pivot_pct, 2),
        "dist_to_10ema_atr": safe_round(dist_to_10ema_atr, 2),
        "dist_to_21ema_atr": safe_round(dist_to_21ema_atr, 2),
        "tight_closes_count": tight_count,
        "closed_above_pivot_last10": closes_above_pivot,
        "too_extended": too_extended,
        "too_late": too_late,
        "cycle_score": safe_round(max(cycle_score, 1), 2),
    }


def compute_setup_scores(d):
    trend = 0
    base = 0
    cycle = 0
    volume = 0
    risk = 0
    market = 0

    if d["stage"] == "Stage 2 (Uptrend)":
        trend += 10
    elif d["stage"] == "Stage 1/2":
        trend += 7
    if d["price"] > (d.get("sma50") or 0):
        trend += 5
    if d["price"] > (d.get("sma150") or 0):
        trend += 5
    if d["price"] > (d.get("sma200") or 0):
        trend += 5

    if d.get("vcp_contracting"):
        base += 10
    if d.get("volume_dry_up_ratio") is not None and d["volume_dry_up_ratio"] < 0.8:
        base += 5
    if d.get("tight_closes_count", 0) >= 4:
        base += 5

    cycle_stage = d.get("kell_cycle", {}).get("cycle_stage")
    if cycle_stage == "First pullback":
        cycle += 20
    elif cycle_stage == "Fresh breakout":
        cycle += 18
    elif cycle_stage == "Add-on continuation":
        cycle += 16
    elif cycle_stage == "Base building":
        cycle += 10
    else:
        cycle += 4
    if d.get("kell_cycle", {}).get("too_extended"):
        cycle -= 6
    if d.get("kell_cycle", {}).get("too_late"):
        cycle -= 4

    rvol = d.get("rvol") or 0
    if rvol >= 2:
        volume += 15
    elif rvol >= 1.2:
        volume += 10
    elif rvol >= 0.8:
        volume += 6

    ext = d.get("jeff_sun", {}).get("extension_label")
    if ext == "Near 50MA":
        risk += 10
    elif ext == "Extended but workable":
        risk += 7
    elif ext == "Hot / extended":
        risk += 2
    elif ext == "Below 50MA":
        risk += 0
    if (d.get("atr14") or 0) > 0 and (d.get("rsi14") or 0) <= 72:
        risk += 4

    if (d.get("rsi14") or 0) >= 50 and (d.get("rsi14") or 0) <= 70:
        market += 10
    elif (d.get("rsi14") or 0) > 70:
        market += 6
    else:
        market += 4

    total = trend + base + cycle + volume + risk + market
    return {
        "trend_score": trend,
        "base_score": base,
        "cycle_score_weighted": cycle,
        "volume_score": volume,
        "risk_geometry_score": risk,
        "market_alignment_score": market,
        "composite_score": safe_round(total, 2),
    }


def fetch_ticker_data(ticker, poly_key):
    result = {"ticker": ticker, "error": None}
    try:
        snap = massive_get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}", poly_key)
        t = snap.get("ticker", {})
        day = t.get("day", {})
        prev = t.get("prevDay", {})
        minbar = t.get("min", {})

        result["price"] = day.get("c") or prev.get("c") or minbar.get("c") or 0
        result["open"] = day.get("o") or 0
        result["high"] = day.get("h") or 0
        result["low"] = day.get("l") or 0
        result["volume"] = day.get("v") or 0
        result["prev_close"] = prev.get("c") or 0
        result["change_pct"] = safe_round((((result["price"] - result["prev_close"]) / result["prev_close"]) * 100) if result["prev_close"] else 0, 2)

        end = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        start = (datetime.now(timezone.utc) - timedelta(days=420)).strftime("%Y-%m-%d")
        bars = massive_get(f"/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}?adjusted=true&sort=asc&limit=500", poly_key)
        rb = bars.get("results", [])
        if len(rb) < 60:
            raise ValueError("Insufficient bar history")

        closes = [b["c"] for b in rb]
        highs = [b["h"] for b in rb]
        lows = [b["l"] for b in rb]
        vols = [b["v"] for b in rb]
        opens = [b["o"] for b in rb]

        result["bars_count"] = len(rb)
        result["high_52w"] = safe_round(max(highs[-252:]) if len(highs) >= 252 else max(highs), 2)
        result["low_52w"] = safe_round(min(lows[-252:]) if len(lows) >= 252 else min(lows), 2)
        result["avg_vol_20"] = safe_round(sum(vols[-20:]) / min(20, len(vols)), 0)
        result["avg_vol_50"] = safe_round(sum(vols[-50:]) / min(50, len(vols)), 0)
        result["rvol"] = safe_round((result["volume"] / result["avg_vol_20"]) if result["avg_vol_20"] else 0, 2)
        result["atr14"] = safe_round(wilder_atr(highs, lows, closes, 14), 2)
        result["rsi14"] = safe_round(wilder_rsi(closes, 14), 1)
        result["ema10"] = safe_round(ema(closes, 10), 2)
        result["ema21"] = safe_round(ema(closes, 21), 2)
        result["ema50"] = safe_round(ema(closes, 50), 2)
        result["sma50"] = safe_round(sma(closes, 50), 2)
        result["sma150"] = safe_round(sma(closes, 150), 2)
        result["sma200"] = safe_round(sma(closes, 200), 2)

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

        result["stage"] = classify_stage(p, result["sma50"], result["sma150"], result["sma200"], e10, e21)
        result["pct_from_high_52w"] = safe_round(((p - result["high_52w"]) / result["high_52w"] * 100) if result["high_52w"] else 0, 2)

        vcp_contracting, vcp_ranges, dry_up_ratio = compute_vcp(highs, lows, vols)
        result["vcp_contracting"] = vcp_contracting
        result["vcp_ranges"] = vcp_ranges
        result["volume_dry_up_ratio"] = dry_up_ratio

        result["pivot_price"] = safe_round(find_recent_pivot(highs[:-1], 20), 2)
        result["support_price"] = safe_round(recent_support(lows, 10), 2)
        result["tight_closes_count"] = tight_closes_count(closes, result["atr14"], 10)
        result["close_percentile_20"] = safe_round(percentile_rank(closes[-20:], p), 1) if len(closes) >= 20 else None

        result["jeff_sun"] = compute_jeff_sun_metrics(
            price=p,
            atr14=result["atr14"],
            sma50_v=result["sma50"],
            sma150_v=result["sma150"],
            sma200_v=result["sma200"],
            volume=result["volume"],
            avg_vol_20=result["avg_vol_20"],
        )
        result.update({"rvol": result["jeff_sun"]["rvol"]})

        result["kell_cycle"] = compute_kell_cycle(
            price=p,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=vols,
            atr14=result["atr14"],
            ema10_v=result["ema10"],
            ema21_v=result["ema21"],
            pivot_price=result["pivot_price"],
        )

        result["scores"] = compute_setup_scores(result)

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
            "pivot_price": d.get("pivot_price"),
            "support_price": d.get("support_price"),
            "rvol": d.get("rvol"),
            "vcp_contracting": d.get("vcp_contracting"),
            "volume_dry_up_ratio": d.get("volume_dry_up_ratio"),
            "tight_closes_count": d.get("tight_closes_count"),
            "jeff_sun": d.get("jeff_sun"),
            "kell_cycle": d.get("kell_cycle"),
            "scores": d.get("scores"),
        })
    return payload


def market_data_table(market_data):
    rows = ""
    for t, d in market_data.items():
        if d.get("error"):
            rows += f"<tr><td style='color:#ef4444;font-family:monospace'>{t}</td><td colspan='10' style='color:#475569;font-size:11px;'>Error: {d['error']}</td></tr>"
            continue
        chg_c = "#10b981" if (d.get("change_pct") or 0) >= 0 else "#ef4444"
        ext = d.get("jeff_sun", {}).get("extension_label", "")
        ext_c = "#10b981" if ext == "Near 50MA" else ("#eab308" if ext == "Extended but workable" else "#ef4444" if ext in ["Hot / extended", "Below 50MA"] else "#94a3b8")
        cycle = d.get("kell_cycle", {}).get("cycle_stage", "")
        rows += (
            f"<tr>"
            f"<td style='color:#f1f5f9;font-weight:700;font-family:monospace;padding:5px 8px'>{t}</td>"
            f"<td style='color:#00d4ff;font-family:monospace;padding:5px 8px'>${d.get('price','')}</td>"
            f"<td style='color:{chg_c};font-family:monospace;padding:5px 8px'>{(d.get('change_pct') or 0):+.2f}%</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d.get('stage','')}</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{d.get('ema_alignment','')}</td>"
            f"<td style='color:#94a3b8;font-family:monospace;padding:5px 8px'>{d.get('rsi14','')}</td>"
            f"<td style='color:#94a3b8;font-family:monospace;padding:5px 8px'>{d.get('rvol','')}x</td>"
            f"<td style='color:{ext_c};font-size:11px;padding:5px 8px'>{ext}</td>"
            f"<td style='color:#94a3b8;font-size:11px;padding:5px 8px'>{cycle}</td>"
            f"<td style='color:#10b981;font-family:monospace;padding:5px 8px'>{d.get('scores',{}).get('composite_score','')}</td>"
            f"</tr>"
        )
    st.markdown(f"""
    <div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-bottom:16px;overflow-x:auto;'>
      <div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>LIVE MARKET DATA — DETERMINISTIC ENGINE</div>
      <table style='width:100%;border-collapse:collapse;font-size:12px;'>
        <thead><tr style='color:#475569;font-size:10px;letter-spacing:1px;border-bottom:1px solid #1e293b;'>
          <th style='text-align:left;padding:4px 8px;'>TICKER</th>
          <th style='text-align:left;padding:4px 8px;'>PRICE</th>
          <th style='text-align:left;padding:4px 8px;'>CHG%</th>
          <th style='text-align:left;padding:4px 8px;'>STAGE</th>
          <th style='text-align:left;padding:4px 8px;'>EMA ALIGNMENT</th>
          <th style='text-align:left;padding:4px 8px;'>RSI</th>
          <th style='text-align:left;padding:4px 8px;'>RVOL</th>
          <th style='text-align:left;padding:4px 8px;'>JEFF SUN</th>
          <th style='text-align:left;padding:4px 8px;'>KELL CYCLE</th>
          <th style='text-align:left;padding:4px 8px;'>SCORE</th>
        </tr></thead>
        <tbody>{rows}</tbody>
      </table>
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
        st.markdown(
            f"<div style='color:#475569;font-size:11px;font-family:monospace;padding-left:26px;margin-bottom:2px'>{note}</div>",
            unsafe_allow_html=True,
        )


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


def call_grok(api_key, system, user_payload):
    payload = json.dumps({
        "model": "grok-4.3",
        "max_tokens": 2000,
        "stream": False,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(user_payload)}
        ]
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.x.ai/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read().decode())
    raw = data["choices"][0]["message"]["content"].strip().replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def deterministic_technical_plan(d):
    price = d["price"]
    atr = d.get("atr14") or max(price * 0.02, 0.01)
    pivot = d.get("pivot_price") or price
    support = d.get("support_price") or min(d.get("ema21") or price, d.get("sma50") or price)
    cycle_stage = d.get("kell_cycle", {}).get("cycle_stage")

    if cycle_stage == "First pullback":
        entry_type = "Pullback"
        base_ref = max(d.get("ema10") or 0, d.get("ema21") or 0, support)
        entry = max(price, base_ref + 0.15 * atr)
    elif cycle_stage == "Add-on continuation":
        entry_type = "Add-on"
        entry = max(price, pivot + 0.08 * atr)
    else:
        entry_type = "Breakout"
        entry = max(price, pivot + 0.10 * atr)

    structural_stop = support - 0.25 * atr
    atr_stop = entry - 1.5 * atr
    stop = max(0.01, min(structural_stop, atr_stop))
    resistance = entry + 2.0 * atr
    risk_per_share = max(entry - stop, 0.01)
    grade_score = d.get("scores", {}).get("composite_score", 0)
    if grade_score >= 82:
        grade = "A+"
    elif grade_score >= 74:
        grade = "A"
    elif grade_score >= 66:
        grade = "B+"
    elif grade_score >= 58:
        grade = "B"
    elif grade_score >= 50:
        grade = "C"
    else:
        grade = "D"

    return {
        "ticker": d["ticker"],
        "current_price": safe_round(price, 2),
        "entry_type": entry_type,
        "atr14": safe_round(atr, 2),
        "pivot_price": safe_round(pivot, 2),
        "entry_price": safe_round(entry, 2),
        "entry_zone": f"{safe_round(entry - 0.15 * atr, 2)} - {safe_round(entry + 0.15 * atr, 2)}",
        "stop_loss": safe_round(stop, 2),
        "key_support": safe_round(support, 2),
        "key_resistance": safe_round(resistance, 2),
        "setup_quality": grade,
        "notes": f"{cycle_stage}; {d.get('jeff_sun',{}).get('extension_label','Unknown extension')}."
    }


def deterministic_risk_plan(tech):
    entry = tech["entry_price"]
    stop = tech["stop_loss"]
    risk = max(entry - stop, 0.01)
    t1 = entry + 2 * risk
    t2 = entry + 3.5 * risk
    return {
        "ticker": tech["ticker"],
        "entry": safe_round(entry, 2),
        "stop_loss": safe_round(stop, 2),
        "risk_per_share": safe_round(risk, 2),
        "target_1": safe_round(t1, 2),
        "target_2": safe_round(t2, 2),
        "reward_risk_ratio": "2.0:1",
        "position_size_1k_risk": math.floor(1000 / risk),
        "stop_rationale": "Structural support or 1.5 ATR below entry, whichever is tighter.",
        "invalidation": f"Exit on decisive close below {safe_round(stop, 2)}."
    }


def main():
    st.markdown('<div class="header-label">MULTI-AGENT SYSTEM · LIVE MARKET DATA · V2.3</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-title">AI Trading Team</div>', unsafe_allow_html=True)
    st.markdown('<div class="header-sub">Deterministic trade math · Oliver Kell cycle · Jeff Sun ATR/50MA extension · Grok synthesis</div>', unsafe_allow_html=True)

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
        poly_secret = secrets.get("POLYGON_API_KEY", "") or secrets.get("MASSIVE_API_KEY", "")
        if poly_secret:
            poly_key = poly_secret
            st.markdown("<div style='color:#10b981;font-size:11px;font-family:monospace;padding:8px 0;'>🔑 Polygon/Massive key from secrets</div>", unsafe_allow_html=True)
        else:
            poly_key = st.text_input("Polygon / Massive API Key", type="password", placeholder="Polygon key...", label_visibility="collapsed")

    col3, col4 = st.columns([4, 1])
    with col3:
        watchlist_raw = st.text_area("Watchlist", value="NVDA, AAPL, MSFT, META, AMD, TSLA, AVGO, SMCI", height=60, label_visibility="collapsed")
    with col4:
        sector = st.selectbox("Sector", ["Technology", "Healthcare", "Financials", "Energy", "Consumer", "Industrials", "Mixed"], label_visibility="collapsed")

    tickers = [t.strip().upper() for t in watchlist_raw.split(",") if t.strip()]
    ready = bool(grok_key and poly_key and tickers)
    run = st.button("▶  DEPLOY TRADING TEAM V2.3", disabled=not ready)

    st.markdown("---")
    agent_col, result_col = st.columns([1, 2])
    with agent_col:
        st.markdown("<div style='color:#64748b;font-size:10px;letter-spacing:2px;font-family:monospace;margin-bottom:10px;'>AGENTS</div>", unsafe_allow_html=True)
        placeholders = {a["id"]: st.empty() for a in AGENTS}
        for agent in AGENTS:
            with placeholders[agent["id"]].container():
                agent_row(agent, "idle")
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
            logs.append("📡 Fetching live market data from Polygon/Massive...")
            refresh_log()
            market_data = {}
            for ticker in tickers:
                logs[-1] = f"📡 Fetching {ticker}..."
                refresh_log()
                market_data[ticker] = fetch_ticker_data(ticker, poly_key)
            logs[-1] = f"✓ Data engine ready — {len(market_data)} tickers"
            refresh_log()

            with data_ph.container():
                market_data_table(market_data)

            clean_payload = compact_market_payload(market_data)
            local_ranked = sorted([d for d in market_data.values() if not d.get("error")], key=lambda x: x.get("scores", {}).get("composite_score", 0), reverse=True)
            local_top = clean_payload[:]
            local_top = sorted(local_top, key=lambda x: x.get("scores", {}).get("composite_score", 0), reverse=True)[:5]

            for agent in AGENTS:
                upd(agent["id"], "running")
                logs.append(f"{agent['icon']} {agent['name']}: analyzing...")
                refresh_log()

                aid = agent["id"]
                if aid == "scanner":
                    msg = {"sector": sector, "market_data": local_top}
                    result = call_grok(grok_key, agent["system"], msg)
                elif aid == "kell_cycle":
                    msg = {"sector": sector, "market_data": local_top}
                    result = call_grok(grok_key, agent["system"], msg)
                elif aid == "technicals":
                    selected = []
                    selected_tickers = [c["ticker"] for c in results["scanner"].get("candidates", []) if c.get("ticker") in market_data]
                    for t in selected_tickers:
                        selected.append({
                            **market_data[t],
                            "ticker": t,
                            "cycle_overlay": next((x for x in results["kell_cycle"].get("cycle_analysis", []) if x.get("ticker") == t), None)
                        })
                    local_analysis = [deterministic_technical_plan(x) for x in selected]
                    msg = {"analysis_inputs": local_analysis}
                    ai_overlay = call_grok(grok_key, agent["system"], msg)
                    merged = []
                    for item in local_analysis:
                        overlay = next((x for x in ai_overlay.get("analysis", []) if x.get("ticker") == item["ticker"]), {})
                        merged.append({**item, **{k: v for k, v in overlay.items() if k in ["notes", "setup_quality"] and v is not None}})
                    result = {"analysis": merged}
                elif aid == "risk":
                    local_risk = [deterministic_risk_plan(x) for x in results["technicals"].get("analysis", [])]
                    msg = {"risk_inputs": local_risk}
                    ai_overlay = call_grok(grok_key, agent["system"], msg)
                    merged = []
                    for item in local_risk:
                        overlay = next((x for x in ai_overlay.get("risk_plans", []) if x.get("ticker") == item["ticker"]), {})
                        merged.append({**item, **{k: v for k, v in overlay.items() if k in ["invalidation", "stop_rationale"] and v is not None}})
                    result = {"risk_plans": merged}
                else:
                    msg = {
                        "scanner": results.get("scanner", {}),
                        "kell_cycle": results.get("kell_cycle", {}),
                        "technicals": results.get("technicals", {}),
                        "risk": results.get("risk", {}),
                        "market_data": local_top,
                    }
                    result = call_grok(grok_key, agent["system"], msg)

                results[aid] = result
                notes_map = {
                    "scanner": f"Found {len(result.get('candidates', []))} candidates",
                    "kell_cycle": f"Classified {len(result.get('cycle_analysis', []))} cycles",
                    "technicals": "Execution levels calculated",
                    "risk": "Risk plans ready",
                    "strategist": f"{len(result.get('recommendations', []))} trades ranked",
                }
                note = notes_map[aid]
                upd(aid, "done", note)
                logs[-1] = f"✓ {agent['name']}: {note}"
                refresh_log()

            with result_ph.container():
                st.markdown("<div style='color:#10b981;font-size:11px;letter-spacing:2px;font-family:monospace;margin-bottom:14px;'>▸ TRADE RECOMMENDATIONS</div>", unsafe_allow_html=True)
                for trade in results.get("strategist", {}).get("recommendations", []):
                    trade_card(trade)
                pnotes = results.get("strategist", {}).get("portfolio_notes", "")
                if pnotes:
                    st.markdown(f"<div style='background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-top:4px;'><div style='color:#f59e0b;font-size:9px;letter-spacing:1.5px;font-family:monospace;margin-bottom:6px;'>PORTFOLIO NOTES</div><div style='color:#94a3b8;font-size:13px;line-height:1.6;'>{pnotes}</div></div>", unsafe_allow_html=True)
                st.markdown("<div style='background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px;text-align:center;color:#475569;font-size:11px;margin-top:12px;'>⚠ Educational use only. Not financial advice.</div>", unsafe_allow_html=True)

                with st.expander("Deterministic engine details"):
                    st.json({
                        "local_top": local_top,
                        "technicals": results.get("technicals", {}),
                        "risk": results.get("risk", {}),
                    })

        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode()
            except Exception:
                err_body = str(e)
            st.error(f"API error {e.code}: {err_body}")
        except json.JSONDecodeError as e:
            st.error(f"JSON parse error: {e}")
        except Exception as e:
            st.error(f"Error: {e}")


if __name__ == "__main__":
    main()
