"""
Global & Domestic Macro Market Sentiment Engine.
Fetches global and Indian market indicators (S&P 500, Nasdaq, Crude Oil, Dollar Index DXY,
USD/INR, Gold, US 10Y, India VIX, Nifty 50, Nifty Midcap 150), optionally blends FII/DII flows
and local market breadth (% > 50/200 DMA), applies 5D/20D EWMA & level Z-score smoothing,
and computes sector-beta-adjusted sentiment for Indian equities.

No LLM and no invented numbers: if live data cannot be fetched, the last cached readings (clearly flagged
as stale) are returned, and if there are none the result is explicitly "unavailable".
"""

import concurrent.futures
import json
import math
import re
import threading
import time
import urllib.request
from typing import Dict, Any, List, Optional
from storage.cache_manager import CacheManager
from tools.yf_quiet import silence_yfinance_logging

silence_yfinance_logging()

# name -> (yfinance ticker, unit, category)
MACRO_TICKERS: Dict[str, tuple] = {
    "S&P 500": ("^GSPC", "pts", "Equities"),
    "Nasdaq": ("^IXIC", "pts", "Equities"),
    "Brent Crude Oil": ("BZ=F", "USD", "Energy"),
    "WTI Crude Oil": ("CL=F", "USD", "Energy"),
    "USD / INR (Rupee)": ("USDINR=X", "INR", "Currency"),
    "US Dollar Index (DXY)": ("DX-Y.NYB", "pts", "Currency"),
    "US 10Y Treasury Yield": ("^TNX", "%", "Bonds"),
    "Gold Futures": ("GC=F", "USD", "Commodities"),
    "India VIX": ("^INDIAVIX", "pts", "Volatility"),
    "Nifty 50": ("^NSEI", "pts", "Domestic Equities"),
    "Nifty Midcap 150": ("^CRSMID", "pts", "Domestic Equities"),
}

STALE_MAX_AGE_HOURS = 72
FETCH_TIMEOUT_SECONDS = 10
LIVE_RETRY_COOLDOWN_SECONDS = 120

# Impact on Indian equities of a +1 "full-scale" move in each indicator.
# (weight, full_scale_pct, direction): contribution = direction * clamp(pct / full_scale, -1, 1) * weight
# direction +1: rising is supportive (global risk appetite); -1: rising is a headwind
# (India is a net oil importer; a stronger dollar / higher US yields pull FII money out of emerging markets;
#  a weaker rupee raises import costs). WTI and Gold are intentionally excluded (WTI duplicates Brent).
MACRO_RULES: Dict[str, tuple] = {
    "S&P 500": (1.00, 1.0, +1),
    "Nasdaq": (0.50, 1.5, +1),
    "Brent Crude Oil": (1.00, 2.0, -1),
    "US Dollar Index (DXY)": (0.75, 0.5, -1),
    "USD / INR (Rupee)": (0.75, 0.3, -1),
    "US 10Y Treasury Yield": (0.50, 2.0, -1),
}

# Unified thresholds shared with tools/macro_risk_shield.py
BULLISH_THRESHOLD = 0.20
BEARISH_THRESHOLD = -0.20
DANGER_THRESHOLD = -0.50
MIN_USABLE_INDICATORS = 2


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _to_float_safe(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        cleaned = str(val).replace(",", "").strip() if isinstance(val, str) else val
        f = float(cleaned)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def compute_ewma_and_zscore(
    closes: List[float], short_span: int = 5, long_span: int = 20
) -> Dict[str, Optional[float]]:
    """
    Computes 5D/20D EWMA of daily % returns, blended smoothed return, and 20D level z-score
    from a chronological sequence of closing prices.
    """
    clean = [float(c) for c in (closes or []) if _to_float_safe(c) is not None and float(c) > 0]
    if len(clean) < 2:
        return {
            "ewma_5_pct": None,
            "ewma_20_pct": None,
            "smoothed_pct_change": None,
            "z_score_20d": None,
        }

    returns_pct = [
        (clean[i] - clean[i - 1]) / clean[i - 1] * 100.0
        for i in range(1, len(clean))
    ]

    def _ewma(vals: List[float], span: int) -> Optional[float]:
        if not vals:
            return None
        alpha = 2.0 / (span + 1.0)
        acc = vals[0]
        for v in vals[1:]:
            acc = alpha * v + (1.0 - alpha) * acc
        return acc

    ewma_5 = _ewma(returns_pct[-max(short_span * 2, len(returns_pct)):], short_span)
    ewma_20 = _ewma(returns_pct[-max(long_span * 2, len(returns_pct)):], long_span)
    smoothed = (
        round(0.6 * ewma_5 + 0.4 * ewma_20, 3)
        if (ewma_5 is not None and ewma_20 is not None)
        else None
    )

    window = clean[-long_span:]
    z_score: Optional[float] = None
    if len(window) >= 5:
        mean_w = sum(window) / len(window)
        var_w = sum((x - mean_w) ** 2 for x in window) / max(1, len(window) - 1)
        std_w = math.sqrt(var_w)
        if std_w > 1e-9:
            z_score = round((window[-1] - mean_w) / std_w, 3)

    return {
        "ewma_5_pct": round(ewma_5, 3) if ewma_5 is not None else None,
        "ewma_20_pct": round(ewma_20, 3) if ewma_20 is not None else None,
        "smoothed_pct_change": smoothed,
        "z_score_20d": z_score,
    }


def derive_brent_in_inr(indicators: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Computes Brent Crude landed cost in INR/barrel (Brent USD * USD/INR) when both are present.
    """
    by_name = {str(ind.get("indicator", "")): ind for ind in (indicators or []) if isinstance(ind, dict)}
    brent = by_name.get("Brent Crude Oil")
    fx = by_name.get("USD / INR (Rupee)")
    if not brent or not fx:
        return None
    b_val = _to_float_safe(brent.get("value"))
    fx_val = _to_float_safe(fx.get("value"))
    if b_val is None or fx_val is None or b_val <= 0 or fx_val <= 0:
        return None

    inr_val = round(b_val * fx_val, 2)
    b_pct = _to_float_safe(brent.get("pct_change"))
    fx_pct = _to_float_safe(fx.get("pct_change"))
    comp_pct = None
    if b_pct is not None and fx_pct is not None:
        comp_pct = round(((1.0 + b_pct / 100.0) * (1.0 + fx_pct / 100.0) - 1.0) * 100.0, 2)

    b_smooth = _to_float_safe(brent.get("smoothed_pct_change"))
    fx_smooth = _to_float_safe(fx.get("smoothed_pct_change"))
    comp_smooth = None
    if b_smooth is not None and fx_smooth is not None:
        comp_smooth = round(((1.0 + b_smooth / 100.0) * (1.0 + fx_smooth / 100.0) - 1.0) * 100.0, 3)

    summary = f"Trading at ₹{inr_val:,.2f}/bbl" + (f" ({comp_pct:+.2f}%)" if comp_pct is not None else "")
    return {
        "indicator": "Brent Crude (INR)",
        "value": inr_val,
        "unit": "INR/bbl",
        "category": "Energy (INR)",
        "pct_change": comp_pct,
        "smoothed_pct_change": comp_smooth,
        "summary": summary,
    }


def parse_fii_dii_payload(
    payload: Any, fno_payload: Any = None
) -> Optional[Dict[str, Any]]:
    """
    Parses NSE /api/fiidiiTradeReact JSON rows and optional F&O net flows.
    Returns None cleanly when payload is empty or malformed (never invents defaults).
    """
    if not isinstance(payload, list) or not payload:
        return None

    fii_net: Optional[float] = None
    dii_net: Optional[float] = None
    trade_date: Optional[str] = None

    for row in payload:
        if not isinstance(row, dict):
            continue
        cat = str(row.get("category") or "").upper()
        net = _to_float_safe(row.get("netValue"))
        if net is None:
            buy = _to_float_safe(row.get("buyValue"))
            sell = _to_float_safe(row.get("sellValue"))
            if buy is not None and sell is not None:
                net = round(buy - sell, 2)
        if net is None:
            continue
        if not trade_date and row.get("date"):
            trade_date = str(row.get("date")).strip()
        if "FII" in cat or "FPI" in cat:
            fii_net = round(net, 2)
        elif "DII" in cat:
            dii_net = round(net, 2)

    if fii_net is None and dii_net is None:
        return None

    combined = round((fii_net or 0.0) + (dii_net or 0.0), 2)
    fii_fno_net: Optional[float] = None
    if isinstance(fno_payload, dict):
        fii_fno_net = _to_float_safe(
            fno_payload.get("fii_fno_net_cr") or fno_payload.get("net_cr") or fno_payload.get("netValue")
        )
        if fii_fno_net is not None:
            fii_fno_net = round(fii_fno_net, 2)

    fii_v = fii_net or 0.0
    dii_v = dii_net or 0.0
    if fii_v >= 1000.0 and combined >= 0.0:
        regime = "FII_INFLOW"
    elif fii_v < -500.0 and dii_v >= abs(fii_v) * 0.7:
        regime = "DII_CUSHIONED"
    elif combined <= -1000.0:
        regime = "BROAD_OUTFLOW"
    else:
        regime = "NEUTRAL"

    return {
        "date": trade_date,
        "fii_net_cr": fii_net,
        "dii_net_cr": dii_net,
        "combined_net_cr": combined,
        "fii_fno_net_cr": fii_fno_net,
        "flow_regime": regime,
    }


def fetch_fii_dii_flows(timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    """
    Fetches daily FII/DII cash activity from NSE India API with browser cookie warm-up.
    Degrades gracefully to None on network block or offline mode.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/reports/fii-dii",
    }
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        req_home = urllib.request.Request("https://www.nseindia.com", headers=headers)
        with opener.open(req_home, timeout=timeout):
            pass
        req_api = urllib.request.Request("https://www.nseindia.com/api/fiidiiTradeReact", headers=headers)
        with opener.open(req_api, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="ignore"))
        return parse_fii_dii_payload(payload)
    except Exception:
        return None


def compute_market_breadth(
    cache_manager: CacheManager, symbols: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """
    Pure local SQLite breadth calculation (% of stocks trading above 50-DMA & 200-DMA).
    Excludes index tickers ('^...') and degrades cleanly to None if < 5 stocks have >= 50 sessions.
    """
    if cache_manager is None:
        return None
    try:
        with cache_manager._get_connection() as conn:
            if symbols:
                sym_list = [str(s).upper().strip() for s in symbols if str(s).strip() and not str(s).startswith("^")]
            else:
                rows = conn.execute(
                    "SELECT DISTINCT symbol FROM historical_candles WHERE symbol NOT LIKE '^%'"
                ).fetchall()
                sym_list = [r[0] for r in rows]

            if not sym_list:
                return None

            above_50 = 0
            eval_50 = 0
            above_200 = 0
            eval_200 = 0

            for sym in sym_list:
                c_rows = conn.execute(
                    "SELECT close FROM historical_candles WHERE symbol = ? ORDER BY date DESC LIMIT 200",
                    (sym,),
                ).fetchall()
                closes = [float(r[0]) for r in reversed(c_rows) if r[0] is not None and float(r[0]) > 0]
                if len(closes) < 50:
                    continue
                last_c = closes[-1]
                sma50 = sum(closes[-50:]) / 50.0
                eval_50 += 1
                if last_c > sma50:
                    above_50 += 1
                if len(closes) >= 200:
                    sma200 = sum(closes[-200:]) / 200.0
                    eval_200 += 1
                    if last_c > sma200:
                        above_200 += 1
    except Exception:
        return None

    if eval_50 < 5:
        return None

    pct50 = round(above_50 / eval_50 * 100.0, 1)
    pct200 = round(above_200 / eval_200 * 100.0, 1) if eval_200 >= 5 else None
    if pct50 >= 60.0 and (pct200 is None or pct200 >= 55.0):
        regime = "BULLISH_BREADTH"
    elif pct50 <= 35.0 or (pct200 is not None and pct200 <= 35.0):
        regime = "WEAK_BREADTH"
    else:
        regime = "NEUTRAL_BREADTH"

    return {
        "stocks_evaluated_50": eval_50,
        "pct_above_50dma": pct50,
        "stocks_evaluated_200": eval_200,
        "pct_above_200dma": pct200,
        "breadth_regime": regime,
    }


def _india_vix_signal(val: Optional[float], pct: Optional[float]) -> Optional[float]:
    if val is None and pct is None:
        return None
    lvl_sig: Optional[float] = None
    if val is not None:
        if val < 13.0:
            lvl_sig = 0.35
        elif val < 18.0:
            lvl_sig = 0.0
        elif val < 24.0:
            lvl_sig = -0.35
        else:
            lvl_sig = -0.80
    chg_sig = _clamp(-pct / 8.0) if pct is not None else None
    if lvl_sig is not None and chg_sig is not None:
        return _clamp(0.6 * lvl_sig + 0.4 * chg_sig)
    return lvl_sig if lvl_sig is not None else chg_sig


def compute_macro_sentiment(indicators: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic macro sentiment for Indian equities from global + domestic indicators.
    Supports legacy daily pct_change lists seamlessly while incorporating EWMA/z-score smoothing,
    India VIX, FII/DII flows, market breadth (% > 50/200 DMA), and India 10Y G-Sec / Repo spread
    when supplied.
    """
    contributions = []
    total_weight = 0.0
    by_name = {
        str(ind.get("indicator", "")): ind
        for ind in (indicators or [])
        if isinstance(ind, dict)
    }

    has_raw_brent = (
        "Brent Crude Oil" in by_name
        and _to_float_safe(by_name["Brent Crude Oil"].get("pct_change")) is not None
    )

    for ind in indicators or []:
        if not isinstance(ind, dict):
            continue
        name = ind.get("indicator")
        pct = _to_float_safe(ind.get("pct_change"))
        val = _to_float_safe(ind.get("value"))

        # 1. Core global macro rules (with optional EWMA + Z-score refinement)
        rule = MACRO_RULES.get(name)
        if rule is not None and pct is not None:
            weight, full_scale, direction = rule
            smoothed = _to_float_safe(ind.get("smoothed_pct_change"))
            eff_pct = (0.6 * pct + 0.4 * smoothed) if smoothed is not None else pct
            raw_norm = _clamp(eff_pct / full_scale)
            z_val = _to_float_safe(ind.get("z_score_20d"))
            if z_val is not None and abs(z_val) >= 2.0:
                z_nudge = 0.15 if z_val > 0 else -0.15
                raw_norm = _clamp(raw_norm + z_nudge)
            contrib = direction * raw_norm * weight
            contributions.append((name, pct, contrib))
            total_weight += weight
            continue

        # 2. Domestic India VIX regime (volatility level + change)
        if name == "India VIX":
            vix_norm = _india_vix_signal(val, pct)
            if vix_norm is not None:
                weight = 0.90
                disp = pct if pct is not None else (val or 0.0)
                contributions.append((name, disp, vix_norm * weight))
                total_weight += weight
            continue

        # 3. FII/DII institutional net flow (Rs Cr)
        if name == "FII Net Flow (Rs Cr)" and val is not None:
            dii_ind = by_name.get("DII Net Flow (Rs Cr)")
            dii_val = _to_float_safe(dii_ind.get("value")) if dii_ind else None
            eff_flow = val + (0.55 * dii_val if dii_val is not None else 0.0)
            norm = _clamp(eff_flow / 3000.0)
            weight = 0.90
            contributions.append((name, val, norm * weight))
            total_weight += weight
            continue

        if name == "FII F&O Net Flow (Rs Cr)" and val is not None:
            norm = _clamp(val / 4000.0)
            weight = 0.40
            contributions.append((name, val, norm * weight))
            total_weight += weight
            continue

        # 4. Domestic market breadth (% > 50/200 DMA)
        if name == "Market Breadth (% > 50 DMA)" and val is not None:
            norm = _clamp((val - 50.0) / 30.0)
            weight = 0.75
            contributions.append((name, val, norm * weight))
            total_weight += weight
            continue

        if name == "Market Breadth (% > 200 DMA)" and val is not None:
            norm = _clamp((val - 50.0) / 30.0)
            weight = 0.50
            contributions.append((name, val, norm * weight))
            total_weight += weight
            continue

        # 5. Brent Crude (INR) only if raw Brent wasn't already scored (avoids double-counting)
        if name == "Brent Crude (INR)" and not has_raw_brent and pct is not None:
            weight = 1.10
            norm = _clamp(pct / 2.2)
            contributions.append((name, pct, -norm * weight))
            total_weight += weight
            continue

    # 6. India 10Y G-Sec vs RBI Repo policy spread (when supplied)
    gsec_val = _to_float_safe((by_name.get("India 10Y G-Sec Yield") or {}).get("value"))
    repo_val = _to_float_safe((by_name.get("RBI Repo Rate") or {}).get("value"))
    spread_ind = by_name.get("India 10Y G-Sec / Repo Spread")
    spread_val = _to_float_safe(spread_ind.get("value")) if spread_ind else None
    if spread_val is None and gsec_val is not None and repo_val is not None:
        spread_val = round(gsec_val - repo_val, 3)
    if spread_val is not None:
        # Normal positive term spread (+0.30 to +0.90%) is benign; inverted/tight (< +0.15%) or sharp steepening (> +1.40%) tightens equities
        if spread_val < 0.15:
            s_norm = -0.35
        elif spread_val <= 0.90:
            s_norm = 0.15
        elif spread_val <= 1.40:
            s_norm = -0.15
        else:
            s_norm = -0.45
        weight = 0.40
        contributions.append(("India 10Y-Repo Spread", spread_val, s_norm * weight))
        total_weight += weight

    brent_inr = derive_brent_in_inr(indicators or [])

    if len(contributions) < MIN_USABLE_INDICATORS or total_weight <= 0:
        return {
            "label": "Neutral",
            "available": False,
            "score": 0.0,
            "drivers": [],
            "brent_inr": brent_inr,
            "thresholds": {
                "bullish": BULLISH_THRESHOLD,
                "bearish": BEARISH_THRESHOLD,
                "danger": DANGER_THRESHOLD,
            },
            "summary": "Global macro data is unavailable right now; no macro tailwind or headwind is assumed.",
        }

    score = round(sum(c for _, _, c in contributions) / total_weight, 3)
    if score >= BULLISH_THRESHOLD:
        label, tone = "Bullish", "Favorable"
    elif score <= BEARISH_THRESHOLD:
        label, tone = "Bearish", "Unfavorable"
    else:
        label, tone = "Neutral", "Neutral"

    ranked = sorted(contributions, key=lambda t: abs(t[2]), reverse=True)[:3]
    drivers = []
    for name, metric, contrib in ranked:
        tone_lbl = "supportive" if contrib > 0 else "headwind" if contrib < 0 else "neutral"
        if "Breadth" in name:
            drivers.append(f"{name} {metric:.1f}% ({tone_lbl})")
        elif "Flow" in name:
            drivers.append(f"{name} Rs.{metric:+,.0f}Cr ({tone_lbl})")
        elif name == "India VIX":
            vix_item = by_name.get("India VIX", {})
            vix_v = _to_float_safe(vix_item.get("value"))
            vix_txt = f"at {vix_v:.1f}" if vix_v is not None else f"{metric:+.2f}%"
            drivers.append(f"India VIX {vix_txt} ({tone_lbl})")
        elif name == "India 10Y-Repo Spread":
            drivers.append(f"G-Sec/Repo spread {metric:+.2f}% ({tone_lbl})")
        else:
            drivers.append(f"{name} {metric:+.2f}% ({tone_lbl})")

    summary = (
        f"Global & domestic macro backdrop is {tone} for Indian equities (rule-based score {score:+.2f}). "
        f"Key drivers: {'; '.join(drivers)}."
    )
    return {
        "label": label,
        "available": True,
        "score": score,
        "drivers": drivers,
        "brent_inr": brent_inr,
        "thresholds": {
            "bullish": BULLISH_THRESHOLD,
            "bearish": BEARISH_THRESHOLD,
            "danger": DANGER_THRESHOLD,
        },
        "summary": summary,
    }


_SECTOR_BETA_RULES: List[tuple] = [
    # Defensives checked before generic consumer / finance terms
    (re.compile(r"\b(?:fmcg|fast moving consumer goods|consumer staples|consumer defensive|packaged foods?|beverages?)\b", re.I), 0.45, "defensive_staples"),
    (re.compile(r"\b(?:healthcare|hospitals?|diagnostics?)\b", re.I), 0.45, "defensive_healthcare"),
    (re.compile(r"\b(?:utilities|power transmission|power generation|power)\b", re.I), 0.50, "defensive_utilities"),
    # Exporters (INR weakness cushion)
    (re.compile(r"\b(?:information technology|it services|it|software|technology)\b", re.I), 0.70, "exporter_it"),
    (re.compile(r"\b(?:pharma|pharmaceuticals?)\b", re.I), 0.65, "exporter_pharma"),
    # Crude-input downstream sectors (extra Brent-in-INR sensitivity)
    (re.compile(r"\b(?:paints?|aviation|airlines?|tyres?|chemicals?|specialty chemicals?|refining|oil marketing)\b", re.I), 1.05, "crude_downstream"),
    # Rate & FII high-beta financials / realty
    (re.compile(r"\b(?:banking|bank|banks|nbfc|financial services|finance|real estate|realty|housing finance|insurance)\b", re.I), 1.25, "rate_fii_high_beta"),
    # Domestic capex / commodity cyclicals
    (re.compile(r"\b(?:metals?|mining|steel|capital goods|infrastructure|infra|automobiles?|automotive|cement)\b", re.I), 1.15, "cyclical"),
]


def apply_sector_macro_beta(
    base_macro_score: float,
    sector: str,
    indicators: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Adjusts the broad macro score by sector-specific macro beta and key India macro exposures:
    - Exporters (IT/Pharma) receive an INR-depreciation cushion when USD/INR rises.
    - Crude-sensitive downstream sectors (Paints, Aviation, Tyres, Chemicals) reflect Brent-in-INR moves.
    - Banks/NBFCs/Realty carry higher sensitivity (1.25x); FMCG/Utilities carry defensive beta (0.45–0.50x).
    """
    score = _to_float_safe(base_macro_score) or 0.0
    beta = 1.00
    bucket = "broad_market"
    for pat, b_val, b_tag in _SECTOR_BETA_RULES:
        if sector and pat.search(str(sector)):
            beta, bucket = b_val, b_tag
            break

    adj = score * beta
    notes = [f"beta {beta:.2f}x"]

    by_name = {
        str(ind.get("indicator", "")): ind
        for ind in (indicators or [])
        if isinstance(ind, dict)
    }
    fx_pct = _to_float_safe((by_name.get("USD / INR (Rupee)") or {}).get("pct_change"))
    brent_inr_pct = _to_float_safe((by_name.get("Brent Crude (INR)") or {}).get("pct_change"))
    if brent_inr_pct is None:
        derived_bi = derive_brent_in_inr(indicators or [])
        brent_inr_pct = _to_float_safe((derived_bi or {}).get("pct_change"))
        if brent_inr_pct is None:
            brent_inr_pct = _to_float_safe((by_name.get("Brent Crude Oil") or {}).get("pct_change"))

    if bucket in ("exporter_it", "exporter_pharma") and fx_pct is not None and fx_pct > 0.15:
        cushion = 0.25 * _clamp(fx_pct / 0.50, 0.0, 1.0)
        adj += cushion
        notes.append(f"INR weakness exporter cushion +{cushion:.2f}")

    if bucket == "crude_downstream" and brent_inr_pct is not None and abs(brent_inr_pct) >= 0.5:
        crude_effect = -0.30 * _clamp(brent_inr_pct / 2.50, -1.0, 1.0)
        adj += crude_effect
        notes.append(f"Brent-INR sensitivity {crude_effect:+.2f}")

    return {
        "adjusted_score": round(_clamp(adj), 3),
        "sector_beta": beta,
        "sector_bucket": bucket,
        "adjustment_note": "; ".join(notes),
    }


def _fetch_one(name: str, meta: tuple) -> Optional[Dict[str, Any]]:
    ticker_code, unit, category = meta
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker_code).history(period="1mo", timeout=FETCH_TIMEOUT_SECONDS)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        close_vals = [float(x) for x in closes.tolist()]
        last_close = close_vals[-1]
        pct_change = None
        if len(close_vals) > 1:
            prev_close = close_vals[-2]
            if prev_close > 0:
                pct_change = round((last_close - prev_close) / prev_close * 100, 2)
        ewma_stats = compute_ewma_and_zscore(close_vals)
        summary = f"Trading at {last_close:.2f}" + (f" ({pct_change:+.2f}%)" if pct_change is not None else "")
        return {
            "indicator": name,
            "value": round(last_close, 2),
            "unit": unit,
            "category": category,
            "pct_change": pct_change,
            "ewma_5_pct": ewma_stats["ewma_5_pct"],
            "ewma_20_pct": ewma_stats["ewma_20_pct"],
            "smoothed_pct_change": ewma_stats["smoothed_pct_change"],
            "z_score_20d": ewma_stats["z_score_20d"],
            "summary": summary,
        }
    except Exception:
        return None


class GlobalMacroEngine:
    _fetch_lock = threading.Lock()
    _last_attempt = 0.0

    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()

    def fetch_macro_indicators(self, max_age_hours: float = 12) -> Dict[str, Any]:
        """
        Retrieves macro indicators. Fresh cache (< max_age_hours) is returned as-is; otherwise all tickers are
        fetched in parallel. Missing tickers fall back to cached readings up to 72h old, flagged "stale".
        Returns {"status": "success"|"stale"|"unavailable", "indicators": [...]}.
        """
        cached = self.cache_manager.get_cached_macro(max_age_hours=max_age_hours)
        if cached and len(cached) >= len(MACRO_RULES):
            return {"status": "success", "indicators": self._with_category(cached)}

        live: Dict[str, Dict[str, Any]] = {}
        # One thread fetches; concurrent callers (many agent threads) wait, then reuse its cache write.
        with GlobalMacroEngine._fetch_lock:
            cached = self.cache_manager.get_cached_macro(max_age_hours=max_age_hours)
            if cached and len(cached) >= len(MACRO_RULES):
                return {"status": "success", "indicators": self._with_category(cached)}

            # Cool-down so a persistently failing ticker doesn't trigger a refetch on every call
            if time.time() - GlobalMacroEngine._last_attempt >= LIVE_RETRY_COOLDOWN_SECONDS:
                GlobalMacroEngine._last_attempt = time.time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(MACRO_TICKERS) + 1) as pool:
                    futures = [pool.submit(_fetch_one, name, meta) for name, meta in MACRO_TICKERS.items()]
                    fii_fut = pool.submit(fetch_fii_dii_flows)
                    for fut in concurrent.futures.as_completed(futures):
                        res = fut.result()
                        if res:
                            live[res["indicator"]] = res
                    try:
                        fii_res = fii_fut.result()
                    except Exception:
                        fii_res = None
                    if fii_res:
                        dt_lbl = fii_res.get("date") or "latest"
                        if fii_res.get("fii_net_cr") is not None:
                            live["FII Net Flow (Rs Cr)"] = {
                                "indicator": "FII Net Flow (Rs Cr)",
                                "value": fii_res["fii_net_cr"],
                                "unit": "Rs Cr",
                                "category": "Institutional Flows",
                                "pct_change": None,
                                "summary": f"FII cash net Rs. {fii_res['fii_net_cr']:+,.2f} Cr ({dt_lbl})",
                            }
                        if fii_res.get("dii_net_cr") is not None:
                            live["DII Net Flow (Rs Cr)"] = {
                                "indicator": "DII Net Flow (Rs Cr)",
                                "value": fii_res["dii_net_cr"],
                                "unit": "Rs Cr",
                                "category": "Institutional Flows",
                                "pct_change": None,
                                "summary": f"DII cash net Rs. {fii_res['dii_net_cr']:+,.2f} Cr ({dt_lbl})",
                            }
                        if fii_res.get("fii_fno_net_cr") is not None:
                            live["FII F&O Net Flow (Rs Cr)"] = {
                                "indicator": "FII F&O Net Flow (Rs Cr)",
                                "value": fii_res["fii_fno_net_cr"],
                                "unit": "Rs Cr",
                                "category": "Institutional Flows",
                                "pct_change": None,
                                "summary": f"FII F&O net Rs. {fii_res['fii_fno_net_cr']:+,.2f} Cr ({dt_lbl})",
                            }
                if live:
                    self.cache_manager.save_macro(list(live.values()))

        merged = dict(live)
        if not live and cached:
            # Cool-down path: serve what the (partial) fresh cache holds
            for item in cached:
                merged[item["indicator"]] = item
        stale_used = False
        if len(live) < len(MACRO_TICKERS):
            for item in self.cache_manager.get_cached_macro(max_age_hours=STALE_MAX_AGE_HOURS):
                if item["indicator"] not in merged:
                    item["stale"] = True
                    merged[item["indicator"]] = item
                    stale_used = True

        if not merged:
            return {"status": "unavailable", "indicators": []}
        status = "stale" if stale_used else "success"
        return {"status": status, "indicators": self._with_category(list(merged.values()))}

    @staticmethod
    def _with_category(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for it in items:
            name = it.get("indicator")
            meta = MACRO_TICKERS.get(name)
            if meta and "category" not in it:
                it["category"] = meta[2]
            elif "category" not in it and name in ("FII Net Flow (Rs Cr)", "DII Net Flow (Rs Cr)", "FII F&O Net Flow (Rs Cr)"):
                it["category"] = "Institutional Flows"
            elif "category" not in it and name == "Brent Crude (INR)":
                it["category"] = "Energy (INR)"
        return items
