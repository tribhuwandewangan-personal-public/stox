"""
Global Macro Market Sentiment Engine.
Fetches global market indicators (S&P 500, Nasdaq, Crude Oil, Dollar Index DXY, USD/INR, Gold, US 10Y)
in parallel and turns them into a deterministic, rule-based macro sentiment for Indian equities.

No LLM and no invented numbers: if live data cannot be fetched, the last cached readings (clearly flagged
as stale) are returned, and if there are none the result is explicitly "unavailable".
"""

import concurrent.futures
import threading
import time
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
BULLISH_THRESHOLD = 0.25
BEARISH_THRESHOLD = -0.25
MIN_USABLE_INDICATORS = 2


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_macro_sentiment(indicators: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Deterministic macro sentiment for Indian equities from daily % changes.
    Returns {"label": Bullish|Neutral|Bearish, "available": bool, "score": float in [-1, 1],
             "drivers": [..], "summary": str}.
    """
    contributions = []
    total_weight = 0.0
    for ind in indicators or []:
        rule = MACRO_RULES.get(ind.get("indicator"))
        pct = ind.get("pct_change")
        if rule is None or pct is None:
            continue
        weight, full_scale, direction = rule
        try:
            contrib = direction * _clamp(float(pct) / full_scale) * weight
        except (TypeError, ValueError):
            continue
        contributions.append((ind["indicator"], float(pct), contrib))
        total_weight += weight

    if len(contributions) < MIN_USABLE_INDICATORS or total_weight <= 0:
        return {
            "label": "Neutral",
            "available": False,
            "score": 0.0,
            "drivers": [],
            "summary": "Global macro data is unavailable right now; no macro tailwind or headwind is assumed."
        }

    score = round(sum(c for _, _, c in contributions) / total_weight, 3)
    if score >= BULLISH_THRESHOLD:
        label, tone = "Bullish", "Favorable"
    elif score <= BEARISH_THRESHOLD:
        label, tone = "Bearish", "Unfavorable"
    else:
        label, tone = "Neutral", "Neutral"

    ranked = sorted(contributions, key=lambda t: abs(t[2]), reverse=True)[:3]
    drivers = [
        f"{name} {pct:+.2f}% ({'supportive' if contrib > 0 else 'headwind' if contrib < 0 else 'neutral'})"
        for name, pct, contrib in ranked
    ]
    summary = (
        f"Global macro backdrop is {tone} for Indian equities (rule-based score {score:+.2f}). "
        f"Key drivers: {'; '.join(drivers)}."
    )
    return {"label": label, "available": True, "score": score, "drivers": drivers, "summary": summary}


def _fetch_one(name: str, meta: tuple) -> Optional[Dict[str, Any]]:
    ticker_code, unit, category = meta
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker_code).history(period="5d", timeout=FETCH_TIMEOUT_SECONDS)
        if hist is None or hist.empty:
            return None
        closes = hist["Close"].dropna()
        if closes.empty:
            return None
        last_close = float(closes.iloc[-1])
        pct_change = None
        if len(closes) > 1:
            prev_close = float(closes.iloc[-2])
            if prev_close > 0:
                pct_change = round((last_close - prev_close) / prev_close * 100, 2)
        summary = f"Trading at {last_close:.2f}" + (f" ({pct_change:+.2f}%)" if pct_change is not None else "")
        return {
            "indicator": name,
            "value": round(last_close, 2),
            "unit": unit,
            "category": category,
            "pct_change": pct_change,
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
                with concurrent.futures.ThreadPoolExecutor(max_workers=len(MACRO_TICKERS)) as pool:
                    futures = [pool.submit(_fetch_one, name, meta) for name, meta in MACRO_TICKERS.items()]
                    for fut in concurrent.futures.as_completed(futures):
                        res = fut.result()
                        if res:
                            live[res["indicator"]] = res
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
            meta = MACRO_TICKERS.get(it.get("indicator"))
            if meta and "category" not in it:
                it["category"] = meta[2]
        return items
