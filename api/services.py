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
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import ENGINE_LABEL, SYMBOLS_FILE_PATH
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
_stocks_cache = {"key": None, "body": b"[]"}
_pattern_memo = {}              # (symbol, newest candle date) -> detected patterns


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


def _load_symbols_list():
    """Load the list of symbols from symbols.json."""
    if not os.path.exists(SYMBOLS_FILE_PATH):
        return []
    try:
        with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("symbols", [])
    except Exception as e:
        print(f"⚠️ [Services] Could not parse {SYMBOLS_FILE_PATH}: {e}", flush=True)
        return []


# ===================================================================================== Service Functions

def _patterns_from_cached_candles(sym, cache_mgr, tech_engine):
    """
    Chart patterns for a symbol that has no stored analysis yet. Uses stored candles only (never the network)
    and is computed at most once per symbol per new candle.
    """
    last_date = cache_mgr.get_latest_candle_date(sym)
    if not last_date:
        return []
    key = (sym, last_date)
    if key in _pattern_memo:
        return _pattern_memo[key]
    try:
        df = tech_engine._load_cached_df(sym).tail(90).reset_index(drop=True)
        patterns = tech_engine.detect_chart_patterns(df) if not df.empty else []
    except Exception:
        patterns = []
    for stale_key in [k for k in _pattern_memo if k[0] == sym]:
        del _pattern_memo[stale_key]
    _pattern_memo[key] = patterns
    return patterns


def get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine):
    """
    Assemble the complete stock data for all symbols: latest analysis, queue status, patterns, events, sparklines.
    Called by GET /api/stocks and via WebSocket snapshot.
    """
    symbols_list = _load_symbols_list()

    # Live queue statuses from SQLite queue; every agent's latest output for every symbol in ONE query
    queue_statuses = queue_mgr.get_symbol_statuses()
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk()
    quotes = cache_mgr.get_all_quotes()
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

        # Latest synthesizer output; flagged stale when older than 72h
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

        # Detected patterns: stored analysis first, else computed once from stored candles
        if tech_output and "detected_patterns" in tech_output:
            patterns = tech_output.get("detected_patterns", [])
        elif tech_output and "raw_indicators" in tech_output and "detected_patterns" in tech_output["raw_indicators"]:
            patterns = tech_output["raw_indicators"].get("detected_patterns", [])
        else:
            patterns = _patterns_from_cached_candles(sym, cache_mgr, tech_engine)

        # Upcoming events: stored analysis first, else whatever the events cache holds (no live fetch here)
        if fund_output and "upcoming_events" in fund_output:
            events = fund_output.get("upcoming_events", {})
        else:
            events = events_engine.get_cached_events(sym)

        # Quick sparkline data (last 25 candles) & full 52-week lookback
        try:
            full_candles = cache_mgr.get_cached_candles(sym, limit_days=260)
        except Exception:
            full_candles = []
        candles = full_candles[-25:] if len(full_candles) > 25 else full_candles
        sparkline = [round(float(c.get("CLOSE_PRICE", 0)), 2) for c in candles]
        latest_close = sparkline[-1] if sparkline else None
        latest_close_date = str(candles[-1]["DATE"])[:10] if candles else None

        # Price when the analysis ran (levels were computed from it) vs the best current price
        analysis_price = None
        if tech_output and "raw_indicators" in tech_output and tech_output["raw_indicators"].get("last_price"):
            try:
                analysis_price = float(tech_output["raw_indicators"]["last_price"])
            except (TypeError, ValueError):
                analysis_price = None
        price_info = build_price_info(
            quotes.get(sym), latest_close, latest_close_date, analysis_price,
            (synth_output or {}).get("as_of_date"),
        )
        last_price = price_info["price"]      # None when unknown (no invented price)

        # Guarantee high_52w, low_52w, and pct_from_52w_high are populated from candles if missing
        if full_candles:
            try:
                h_52w_val = max(float(c.get("HIGH_PRICE") or c.get("CLOSE_PRICE") or 0.0) for c in full_candles)
                l_52w_val = min(float(c.get("LOW_PRICE") or c.get("CLOSE_PRICE") or 1e9) for c in full_candles)
                eff_p = last_price or float(full_candles[-1].get("CLOSE_PRICE") or 0.0)
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
                            "last_price": eff_p
                        }
                    }
            except Exception:
                pass

        short_verdict = "HOLD"
        if synth_output and "structured_signal" in synth_output:
            short_verdict = synth_output["structured_signal"].get("action_verdict", "HOLD")

        long_term_signal = long_term_engine.evaluate_long_term_stock(
            symbol=sym,
            name=name,
            sector=sector,
            last_price=last_price,
            short_verdict=short_verdict
        )

        # Enrich structured_signal with long-term metrics
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
            "price_info": price_info
        })
    return results


def get_stocks_response_body(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine) -> bytes:
    """
    JSON body for /api/stocks. Rebuilt only when something changed (new analysis written, queue status or
    symbols.json changed) or after STOCKS_CACHE_SECONDS, so repeated polling is nearly free.
    """
    try:
        symbols_mtime = os.path.getmtime(SYMBOLS_FILE_PATH)
    except OSError:
        symbols_mtime = 0
    key = (
        cache_mgr.get_agent_runs_marker(),
        tuple(sorted(queue_mgr.get_symbol_statuses().items())),
        symbols_mtime,
        int(time.time() // STOCKS_CACHE_SECONDS),
    )
    with _stocks_lock:   # concurrent requests wait for one build instead of each doing the work
        if _stocks_cache["key"] != key:
            _stocks_cache["body"] = safe_json_dumps(get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine))
            _stocks_cache["key"] = key
        return _stocks_cache["body"]


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
