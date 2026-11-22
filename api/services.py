"""
Service functions extracted from dashboard_server.py: handler-independent logic for both
the legacy http.server handler and the new Starlette app.

These functions:
  - Have no dependency on HTTP request/response objects
  - Can be called from any HTTP framework
  - Are testable via direct calls
  - Publish events to tools/events_bus when data changes
"""

import json
import math
import os
import sys
import time
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Any, Optional, Dict, List
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import ENGINE_LABEL, SYMBOLS_FILE_PATH, ALL_NSE_SYMBOLS_FILE_PATH, MIDCAP_250_SYMBOLS_FILE_PATH
from tools.quote_tools import build_price_info
from tools.long_term_strategy import long_term_engine


# ===================================================================================== Constants

SYNTH_AGENT = "Master Prediction Synthesizer Agent"
TECH_AGENT = "Technical Analysis Agent"
HIST_AGENT = "Historical Data RAG Agent"
NEWS_AGENT = "News & Sentiment Agent"
RISK_AGENT = "Risk & Volatility Agent"
FUND_AGENT = "Fundamental Analyst Agent"

STALE_SYNTH_HOURS = 72          # older synthesizer output is still shown, flagged as "previous run"
STOCKS_CACHE_SECONDS = 30       # /api/stocks response is rebuilt at least this often (prices, sparklines)
_stocks_lock = threading.Lock()
_stocks_cache = {}
_pattern_memo = {}              # (symbol, newest candle date) -> detected patterns
_pattern_memo_lock = threading.Lock()
_symbols_cache: Dict[str, Dict[str, Any]] = {}
_symbols_cache_lock = threading.Lock()


# ===================================================================================== Utilities

class NaNSafeEncoder(json.JSONEncoder):
    """
    JSON encoder that converts NaN/Infinity floats to null and handles numpy scalars.
    Python's json module emits bare NaN/Infinity by default, which is invalid JSON,
    and fails on numpy scalars like np.bool_. This encoder fixes that globally.
    """
    def iterencode(self, obj, _one_shot=False):
        # Pre-sanitize the object tree before encoding
        return super().iterencode(self._sanitize(obj), _one_shot)

    def _sanitize(self, obj):
        if hasattr(obj, 'item') and callable(obj.item):
            try:
                obj = obj.item()
            except Exception:
                pass

        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        elif isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize(v) for v in obj]
        return obj

    def default(self, o):
        if hasattr(o, 'item') and callable(o.item):
            return o.item()
        if hasattr(o, '__bool__'):
            return bool(o)
        return str(o)

def safe_json_dumps(obj) -> bytes:
    """Serialize obj to JSON bytes, replacing NaN/Infinity with null."""
    return json.dumps(obj, cls=NaNSafeEncoder).encode("utf-8")


def _load_symbols_list(universe: str = "curated"):
    """Load and mtime-cache symbols list from curated symbols.json, midcap 250, or all NSE."""
    target_path = SYMBOLS_FILE_PATH
    if universe == "midcap250":
        target_path = MIDCAP_250_SYMBOLS_FILE_PATH
    elif universe == "all_nse":
        target_path = ALL_NSE_SYMBOLS_FILE_PATH

    if not os.path.exists(target_path):
        target_path = SYMBOLS_FILE_PATH

    try:
        mtime = os.path.getmtime(target_path)
    except OSError:
        return []

    with _symbols_cache_lock:
        hit = _symbols_cache.get(target_path)
        if hit and hit.get("mtime") == mtime:
            return list(hit["data"])

    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f).get("symbols", [])
        with _symbols_cache_lock:
            _symbols_cache[target_path] = {"mtime": mtime, "data": data}
        return list(data)
    except Exception as e:
        print(f"⚠️ [Services] Could not parse {target_path}: {e}", flush=True)
        return []


def load_active_monitored_symbols(
    include_midcap: bool = True,
    include_holdings: bool = True,
) -> List[Dict[str, Any]]:
    """
    Deduplicated active universe for QuotePoller & Scheduler:
    curated symbols.json + Midcap 250 + local Kite holdings snapshot (if present).
    """
    seen: Dict[str, Dict[str, Any]] = {}
    for item in _load_symbols_list("curated"):
        sym = str(item.get("symbol") or "").upper().strip()
        if sym and sym not in seen:
            seen[sym] = dict(item, symbol=sym)

    if include_midcap and os.path.exists(MIDCAP_250_SYMBOLS_FILE_PATH):
        for item in _load_symbols_list("midcap250"):
            sym = str(item.get("symbol") or "").upper().strip()
            if sym and sym not in seen:
                seen[sym] = dict(item, symbol=sym)

    if include_holdings:
        holdings_path = os.path.join(PROJECT_ROOT, "storage", "my_holdings.json")
        if os.path.exists(holdings_path):
            try:
                with open(holdings_path, "r", encoding="utf-8") as f:
                    h_data = json.load(f)
                h_list = h_data.get("holdings", []) if isinstance(h_data, dict) else []
                for h in h_list:
                    sym = str(h.get("symbol") or "").upper().strip()
                    if sym and sym not in seen:
                        seen[sym] = {"symbol": sym, "name": sym, "sector": ""}
            except Exception:
                pass
    return list(seen.values())


# ===================================================================================== Service Functions

def _patterns_from_cached_candles(sym, cache_mgr, tech_engine):
    """
    Chart patterns for a symbol that has no stored analysis yet. Uses stored candles only (never the network)
    and is computed at most once per symbol per new candle (thread-safe).
    """
    last_date = cache_mgr.get_latest_candle_date(sym)
    if not last_date:
        return []
    key = (sym, last_date)
    with _pattern_memo_lock:
        if key in _pattern_memo:
            return _pattern_memo[key]
    try:
        df = tech_engine._load_cached_df(sym).tail(90).reset_index(drop=True)
        patterns = tech_engine.detect_chart_patterns(df) if not df.empty else []
    except Exception:
        patterns = []
    with _pattern_memo_lock:
        for stale_key in [k for k in _pattern_memo if k[0] == sym]:
            del _pattern_memo[stale_key]
        _pattern_memo[key] = patterns
    return patterns


def get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe: str = "curated"):
    """
    Assemble the complete stock data for all symbols: latest analysis, queue status, patterns, events, sparklines.
    Uses bulk SQLite queries (single pass) instead of N+1 per-symbol queries.
    """
    symbols_list = _load_symbols_list(universe=universe)
    sym_names = [s.get("symbol", "").upper() for s in symbols_list if s.get("symbol")]

    queue_statuses = queue_mgr.get_symbol_statuses()
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk()
    quotes = cache_mgr.get_all_quotes()
    candle_summaries = (
        cache_mgr.get_candles_bulk_summary(sym_names, limit_days=260, sparkline_days=25)
        if hasattr(cache_mgr, "get_candles_bulk_summary")
        else {}
    )
    events_bulk = cache_mgr.get_cached_events_bulk() if hasattr(cache_mgr, "get_cached_events_bulk") else {}
    stale_cutoff = datetime.now() - timedelta(hours=STALE_SYNTH_HOURS)

    results = []
    for s in symbols_list:
        sym = s.get("symbol", "").upper()
        name = s.get("name", "")
        sector = s.get("sector", "")
        q_status = queue_statuses.get(sym, "pending")
        agents = bulk_outputs.get(sym, {})

        def _out(agent_name):
            rec = agents.get(agent_name)
            return rec["output"] if rec else None

        synth_output = _out(SYNTH_AGENT)
        is_stale = False
        if synth_output:
            try:
                is_stale = datetime.fromisoformat(agents[SYNTH_AGENT]["timestamp"]) < stale_cutoff
            except Exception:
                is_stale = False

        tech_output = _out(TECH_AGENT)
        hist_output = _out(HIST_AGENT)
        news_output = _out(NEWS_AGENT)
        risk_output = _out(RISK_AGENT)
        fund_output = _out(FUND_AGENT)

        if tech_output and "detected_patterns" in tech_output:
            patterns = tech_output.get("detected_patterns", [])
        elif tech_output and "raw_indicators" in tech_output and "detected_patterns" in tech_output["raw_indicators"]:
            patterns = tech_output["raw_indicators"].get("detected_patterns", [])
        else:
            patterns = _patterns_from_cached_candles(sym, cache_mgr, tech_engine)

        if fund_output and "upcoming_events" in fund_output:
            events = fund_output.get("upcoming_events", {})
        elif sym in events_bulk:
            events = events_bulk[sym]
        else:
            events = {}

        c_sum = candle_summaries.get(sym)
        if c_sum is None and not hasattr(cache_mgr, "get_candles_bulk_summary"):
            try:
                full_candles = cache_mgr.get_cached_candles(sym, limit_days=260)
            except Exception:
                full_candles = []
            if full_candles:
                c_sum = {
                    "sparkline": [round(float(c.get("CLOSE_PRICE", 0)), 2) for c in full_candles[-25:]],
                    "latest_close": round(float(full_candles[-1].get("CLOSE_PRICE") or 0.0), 2),
                    "latest_date": str(full_candles[-1]["DATE"])[:10],
                    "prev_close": round(float(full_candles[-2].get("CLOSE_PRICE") or full_candles[-1].get("CLOSE_PRICE") or 0.0), 2) if len(full_candles) > 1 else None,
                    "high_52w": round(max(float(c.get("HIGH_PRICE") or c.get("CLOSE_PRICE") or 0.0) for c in full_candles), 2),
                    "low_52w": round(min(float(c.get("LOW_PRICE") or c.get("CLOSE_PRICE") or 1e9) for c in full_candles), 2),
                }

        sparkline = c_sum["sparkline"] if c_sum else []
        latest_close = c_sum["latest_close"] if c_sum else None
        latest_close_date = c_sum["latest_date"] if c_sum else None
        prev_close_candle = c_sum.get("prev_close") if c_sum else None

        analysis_price = None
        if tech_output and "raw_indicators" in tech_output and tech_output["raw_indicators"].get("last_price"):
            try:
                analysis_price = float(tech_output["raw_indicators"]["last_price"])
            except (TypeError, ValueError):
                analysis_price = None
        price_info = build_price_info(
            quotes.get(sym), latest_close, latest_close_date, analysis_price,
            (synth_output or {}).get("as_of_date"),
            prev_close_from_candle=prev_close_candle,
        )
        last_price = price_info["price"]

        if c_sum and c_sum.get("high_52w"):
            try:
                h_52w_val = float(c_sum["high_52w"])
                l_52w_val = float(c_sum.get("low_52w") or 0.0)
                eff_p = last_price or latest_close or 0.0
                pct_52w_val = round((eff_p - h_52w_val) / h_52w_val * 100, 2) if h_52w_val > 0 else 0.0

                if tech_output is not None:
                    raw_ind = tech_output.setdefault("raw_indicators", {})
                    if raw_ind.get("high_52w") is None or raw_ind.get("high_52w") == 0:
                        raw_ind["high_52w"] = round(h_52w_val, 2)
                    if raw_ind.get("low_52w") is None or raw_ind.get("low_52w") == 0:
                        raw_ind["low_52w"] = round(l_52w_val, 2)
                    if raw_ind.get("pct_from_52w_high") is None:
                        raw_ind["pct_from_52w_high"] = pct_52w_val
                else:
                    tech_output = {
                        "agent_name": "Technical Analysis Agent",
                        "symbol": sym,
                        "raw_indicators": {
                            "high_52w": round(h_52w_val, 2),
                            "low_52w": round(l_52w_val, 2),
                            "pct_from_52w_high": pct_52w_val,
                            "last_price": eff_p,
                        },
                    }
            except Exception:
                pass

        short_verdict = "HOLD"
        if synth_output and "structured_signal" in synth_output:
            short_verdict = synth_output["structured_signal"].get("action_verdict", "HOLD")

        raw_fund = (fund_output or {}).get("raw_fundamentals") or {}
        forensic_d = (fund_output or {}).get("forensic_analysis")
        long_term_signal = long_term_engine.evaluate_long_term_stock(
            symbol=sym,
            name=name,
            sector=sector,
            last_price=last_price,
            short_verdict=short_verdict,
            fund_data=raw_fund,
            forensic_data=forensic_d,
        )

        if synth_output and "structured_signal" in synth_output:
            synth_output["structured_signal"]["long_term_signal"] = long_term_signal
            synth_output["structured_signal"]["long_term_target"] = long_term_signal["long_term_target"]
            synth_output["structured_signal"]["long_term_verdict"] = long_term_signal["long_term_verdict"]
            synth_output["structured_signal"]["long_term_horizon"] = long_term_signal["long_term_horizon"]
            synth_output["structured_signal"]["suggested_long_term_peers"] = long_term_signal["suggested_long_term_peers"]

        results.append({
            "long_term_signal": long_term_signal,
            "symbol": sym,
            "name": name,
            "sector": sector,
            "queue_status": q_status,
            "is_stale": is_stale,
            "has_analysis": synth_output is not None,
            "synth_output": synth_output,
            "tech_output": tech_output,
            "hist_output": hist_output,
            "news_output": news_output,
            "risk_output": risk_output,
            "fund_output": fund_output,
            "patterns": patterns,
            "events": events,
            "sparkline": sparkline,
            "price_info": price_info,
        })
    return results


def get_stocks_response_body(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe: str = "curated") -> bytes:
    """
    JSON body for /api/stocks. Rebuilt only when something changed (new analysis written, queue status or
    symbols file changed) or after STOCKS_CACHE_SECONDS, so repeated polling is nearly free.
    """
    target_path = SYMBOLS_FILE_PATH
    if universe == "midcap250":
        target_path = MIDCAP_250_SYMBOLS_FILE_PATH
    elif universe == "all_nse":
        target_path = ALL_NSE_SYMBOLS_FILE_PATH

    try:
        symbols_mtime = os.path.getmtime(target_path)
    except OSError:
        symbols_mtime = 0
    key = (
        universe,
        cache_mgr.get_agent_runs_marker(),
        tuple(sorted(queue_mgr.get_symbol_statuses().items())),
        symbols_mtime,
        int(time.time() // STOCKS_CACHE_SECONDS),
    )
    with _stocks_lock:   # concurrent requests wait for one build instead of each doing the work
        cached_entry = _stocks_cache.get(universe)
        if not cached_entry or cached_entry.get("key") != key:
            body = safe_json_dumps(get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe=universe))
            _stocks_cache[universe] = {"key": key, "body": body}
        return _stocks_cache[universe]["body"]


# /api/history: computed indicators + patterns memoized per (symbol, days, newest candle date)
_HISTORY_MEMO_MAX = 128
_history_memo = OrderedDict()
_history_lock = threading.Lock()


def get_history_response_body(sym: str, days: int, cache_mgr, tech_engine) -> bytes:
    """Get cached or compute chart data (candles + indicators) for a symbol."""
    key = (sym, days, cache_mgr.get_latest_candle_date(sym) or "")
    with _history_lock:
        if key in _history_memo:
            _history_memo.move_to_end(key)
            return _history_memo[key]
    chart_data = tech_engine.get_chart_data(sym, limit_days=days)
    body = safe_json_dumps(chart_data)
    if chart_data.get("candles"):
        key = (sym, days, cache_mgr.get_latest_candle_date(sym) or "")  # may have just been downloaded
        with _history_lock:
            _history_memo[key] = body
            while len(_history_memo) > _HISTORY_MEMO_MAX:
                _history_memo.popitem(last=False)
    return body


# ===================================================================================== Pattern Screener
def _extract_numeric_val(val: Any) -> Optional[float]:
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val) if not (isinstance(val, float) and (val != val or val == float('inf') or val == float('-inf'))) else None
    import re
    match = re.search(r'([0-9]+\.?[0-9]*)', str(val).replace(',', ''))
    return float(match.group(1)) if match else None


_picks_cache: Dict[str, Any] = {}
_picks_lock = threading.Lock()
PICKS_CACHE_SECONDS = 45


def get_top_pattern_picks(cache_mgr, tech_engine, min_upside: float = 0.0) -> List[Dict[str, Any]]:
    """
    Cached wrapper: the full ranked list is rebuilt only when new analyses land (agent-runs marker changes)
    or after PICKS_CACHE_SECONDS (live quotes); min_upside is applied as a cheap post-filter.
    """
    try:
        marker = cache_mgr.get_agent_runs_marker()
    except Exception:
        marker = None
    key = (marker, int(time.time() // PICKS_CACHE_SECONDS))
    with _picks_lock:
        if _picks_cache.get("key") != key:
            _picks_cache["data"] = _compute_top_pattern_picks(cache_mgr, tech_engine, 0.0)
            _picks_cache["key"] = key
        data = _picks_cache["data"]
    if min_upside and min_upside > 0:
        return [p for p in data if p["upside_pct"] >= min_upside]
    return list(data)


def _compute_top_pattern_picks(cache_mgr, tech_engine, min_upside: float = 0.0) -> List[Dict[str, Any]]:
    """
    Extracts and ranks confirmed chart pattern picks across analyzed stocks using bulk SQLite queries.
    """
    sym_meta: Dict[str, Dict[str, str]] = {}
    for univ in ("all_nse", "midcap250", "curated"):
        for item in _load_symbols_list(universe=univ):
            k = (item.get("symbol") or "").upper().strip()
            if k and (k not in sym_meta or item.get("sector") != "Indian Equities"):
                sym_meta[k] = {
                    "name": item.get("name") or k,
                    "sector": item.get("sector") or "Indian Equities",
                }

    quotes = cache_mgr.get_all_quotes()
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk()
    candle_summaries = (
        cache_mgr.get_candles_bulk_summary(list(bulk_outputs.keys()), limit_days=60, sparkline_days=25)
        if hasattr(cache_mgr, "get_candles_bulk_summary")
        else {}
    )

    picks: List[Dict[str, Any]] = []
    for sym, agents in bulk_outputs.items():
        synth_rec = agents.get(SYNTH_AGENT)
        if not synth_rec:
            continue
        sym_clean = sym.upper().strip()
        data = synth_rec.get("output") or {}
        ts = synth_rec.get("timestamp") or ""

        sig = data.get("structured_signal", {})
        pattern_str = sig.get("chart_patterns") or ""
        if not pattern_str or pattern_str == "N/A":
            continue

        verdict = str(sig.get("action_verdict", "HOLD")).upper()
        conf_score = _extract_numeric_val(sig.get("confidence_score") or sig.get("confidence_percentage")) or 70.0

        raw_lp = _extract_numeric_val(data.get("last_price"))
        quote_lp = quotes.get(sym_clean, {}).get("ltp")
        last_price = quote_lp or raw_lp

        target_price = _extract_numeric_val(sig.get("when_to_sell_target")) or _extract_numeric_val(sig.get("target_num"))
        entry_raw = sig.get("when_to_buy_entry") or "Near current levels"
        stop_loss = _extract_numeric_val(sig.get("stop_loss")) or _extract_numeric_val(sig.get("stop_num"))

        c_sum = candle_summaries.get(sym_clean)
        sparkline = c_sum["sparkline"] if c_sum else []
        if not last_price and c_sum:
            last_price = c_sum.get("latest_close")

        if not last_price or last_price <= 0:
            continue

        upside_pct = round(((target_price - last_price) / last_price) * 100, 2) if (target_price and target_price > last_price) else 0.0
        downside_pct = round(((last_price - stop_loss) / last_price) * 100, 2) if (stop_loss and stop_loss < last_price) else 4.0
        rr_ratio = round(upside_pct / downside_pct, 2) if (downside_pct > 0 and upside_pct > 0) else (_extract_numeric_val(sig.get("reward_to_risk_ratio")) or 1.5)

        if upside_pct < min_upside and min_upside > 0:
            continue

        meta = sym_meta.get(sym_clean, {"name": sym_clean, "sector": "Indian Equities"})
        p_lower = pattern_str.lower()
        if "cross" in p_lower or "moving average" in p_lower:
            category = "Moving Average"
        elif "saucer" in p_lower or "rounding bottom" in p_lower or "cup" in p_lower:
            category = "Accumulation & Cup"
        elif "head" in p_lower or "shoulder" in p_lower or "wyckoff" in p_lower or "double" in p_lower:
            category = "Reversal"
        elif "flag" in p_lower or "pennant" in p_lower or "triangle" in p_lower or "squeeze" in p_lower:
            category = "Breakout & Continuation"
        elif "star" in p_lower or "engulfing" in p_lower or "candle" in p_lower:
            category = "Candlestick"
        else:
            category = "Classical Chart"

        picks.append({
            "symbol": sym_clean,
            "name": meta["name"],
            "sector": meta["sector"],
            "last_price": round(last_price, 2),
            "pattern_name": pattern_str,
            "pattern_category": category,
            "direction": "Bullish" if ("bull" in p_lower or "golden" in p_lower or "inverse" in p_lower or "bottom" in p_lower or "spring" in p_lower or upside_pct > 0) else "Bearish",
            "action_verdict": verdict,
            "confidence_score": conf_score,
            "entry_range": entry_raw,
            "target_price": round(target_price, 2) if target_price else None,
            "stop_loss": round(stop_loss, 2) if stop_loss else None,
            "upside_pct": upside_pct,
            "downside_pct": round(downside_pct, 2),
            "risk_reward": rr_ratio,
            "sparkline": sparkline,
            "timestamp": ts[:10] if ts else "",
        })

    picks.sort(key=lambda x: (
        x["action_verdict"] in ("BUY", "ACCUMULATE"),
        x["upside_pct"] > 0,
        x["risk_reward"],
        x["upside_pct"],
    ), reverse=True)
    return picks


def get_fundamental_picks_data(cache_mgr, universe: str = "curated") -> Dict[str, Any]:
    """
    Compute Top 10 Fundamental Picks for the requested universe using single bulk SQLite queries.
    """
    from tools.fundamental_picks import score_fundamental_pick

    if universe not in ("curated", "midcap250", "all_nse"):
        universe = "curated"

    try:
        marker = cache_mgr.get_agent_runs_marker()
    except Exception:
        marker = None
    fkey = (universe, marker, int(time.time() // PICKS_CACHE_SECONDS))
    with _picks_lock:
        hit = _picks_cache.get("fund_" + universe)
        if hit and hit["key"] == fkey:
            return hit["data"]
    result = _compute_fundamental_picks(cache_mgr, universe)
    with _picks_lock:
        _picks_cache["fund_" + universe] = {"key": fkey, "data": result}
    return result


def _compute_fundamental_picks(cache_mgr, universe: str) -> Dict[str, Any]:
    from tools.fundamental_picks import score_fundamental_pick

    symbols_list = _load_symbols_list(universe=universe)
    sym_names = [str(s.get("symbol") or "").upper().strip() for s in symbols_list if s.get("symbol")]
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk()
    candle_summaries = (
        cache_mgr.get_candles_bulk_summary(sym_names, limit_days=260, sparkline_days=5)
        if hasattr(cache_mgr, "get_candles_bulk_summary")
        else {}
    )
    picks: List[Dict[str, Any]] = []

    for item in symbols_list:
        sym = str(item.get("symbol", "")).upper().strip()
        if not sym:
            continue
        cname = item.get("name", "")
        sec = item.get("sector", "")

        agents = bulk_outputs.get(sym, {})
        synth_res = agents.get(SYNTH_AGENT, {}).get("output")
        if not synth_res:
            continue

        tech_res = agents.get(TECH_AGENT, {}).get("output")
        fund_res = agents.get(FUND_AGENT, {}).get("output")

        raw_tech = (tech_res or {}).get("raw_indicators", {})
        if raw_tech.get("pct_from_52w_high") is None:
            c_sum = candle_summaries.get(sym)
            if c_sum and c_sum.get("high_52w") and c_sum.get("latest_close"):
                h_max = float(c_sum["high_52w"])
                p_now = float(c_sum["latest_close"])
                if h_max > 0 and p_now > 0:
                    tech_res = dict(tech_res or {"raw_indicators": {}})
                    tech_res["raw_indicators"] = dict(tech_res.get("raw_indicators", {}))
                    tech_res["raw_indicators"]["pct_from_52w_high"] = round((p_now - h_max) / h_max * 100, 2)
                    tech_res["raw_indicators"]["high_52w"] = round(h_max, 2)
                    tech_res["raw_indicators"]["last_price"] = p_now

        pick = score_fundamental_pick(sym, synth_res, tech_res, fund_res=fund_res, sector=sec)
        if pick is None:
            continue
        pick["company"] = cname
        pick["sector"] = sec
        picks.append(pick)

    picks.sort(key=lambda x: x["score"], reverse=True)
    top10 = picks[:10]
    return {"picks": top10, "count": len(top10), "universe": len(symbols_list)}
