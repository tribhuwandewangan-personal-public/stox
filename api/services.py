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
from tools.forensic_financial_engine import ForensicFinancialEngine, _is_bfsi_sector
from tools.pattern_engine import compute_pattern_projection, HIGH_CONVICTION_PRE_BREAKOUT_PATTERNS

_forensic_recalc_engine = ForensicFinancialEngine()


# ===================================================================================== Constants

SYNTH_AGENT = "Master Prediction Synthesizer Agent"
TECH_AGENT = "Technical Analysis Agent"
HIST_AGENT = "Historical Data RAG Agent"
NEWS_AGENT = "News & Sentiment Agent"
RISK_AGENT = "Risk & Volatility Agent"
FUND_AGENT = "Fundamental Analyst Agent"

STALE_SYNTH_HOURS = 72          # older synthesizer output is still shown, flagged as "previous run"
STOCKS_CACHE_SECONDS = 60       # /api/stocks response is rebuilt at least this often (prices, sparklines)
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
    """Load and mtime-cache symbols list from unified symbols.json (optionally filtered by universe tag)."""
    target_path = SYMBOLS_FILE_PATH
    if not os.path.exists(target_path):
        return []

    try:
        mtime = os.path.getmtime(target_path)
    except OSError:
        return []

    with _symbols_cache_lock:
        hit = _symbols_cache.get(target_path)
        if hit and hit.get("mtime") == mtime:
            data = list(hit["data"])
        else:
            data = None

    if data is None:
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f).get("symbols", [])
            with _symbols_cache_lock:
                _symbols_cache[target_path] = {"mtime": mtime, "data": data}
            data = list(data)
        except Exception as e:
            print(f"⚠️ [Services] Could not parse {target_path}: {e}", flush=True)
            return []

    if universe == "midcap250":
        filtered = [s for s in data if "Midcap 100" in (s.get("tags") or [])]
        if filtered:
            return filtered
    elif universe == "all_nse":
        filtered = [s for s in data if "Nifty 100" in (s.get("tags") or [])]
        if filtered:
            return filtered
    return data


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

    if os.path.exists(ALL_NSE_SYMBOLS_FILE_PATH):   # Nifty 100 large caps
        for item in _load_symbols_list("all_nse"):
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
        rag = getattr(tech_engine, "rag_engine", None)
        df = rag._load_cached_df(sym).tail(120).reset_index(drop=True) if rag else None
        if df is not None and not df.empty and len(df) >= 20:
            df = tech_engine._compute_indicators(df)
            patterns = tech_engine.detect_chart_patterns(df)
        else:
            patterns = []
    except Exception:
        patterns = []
    with _pattern_memo_lock:
        for stale_key in [k for k in _pattern_memo if k[0] == sym]:
            del _pattern_memo[stale_key]
        _pattern_memo[key] = patterns
    return patterns


def _refresh_peg_and_forensic(
    sym: str,
    sector: str,
    last_price: Optional[float],
    raw_fund: Dict[str, Any],
    forensic_d: Optional[Dict[str, Any]],
    fund_output: Optional[Dict[str, Any]],
    synth_output: Optional[Dict[str, Any]],
) -> None:
    """
    Normalizes sustainable PEG ratio and recalculates forensic intrinsic valuation & margin of safety
    against the latest market price in-place.
    """
    if isinstance(raw_fund, dict):
        pe_v = raw_fund.get("pe_ratio")
        eg_v = raw_fund.get("earnings_growth_pct")
        sec_l = str(sector or raw_fund.get("sector") or "").lower()
        if isinstance(eg_v, (int, float)) and eg_v <= 0:
            raw_fund["peg_ratio"] = "N/A (Negative Growth)"
        elif isinstance(pe_v, (int, float)) and isinstance(eg_v, (int, float)) and pe_v > 0 and eg_v > 2.0:
            max_g = 24.0 if any(k in sec_l for k in ("financial", "bank", "nbfc", "insurance")) else 32.0
            sust_g = min(float(eg_v), max_g)
            norm_peg = round(float(pe_v) / sust_g, 2)
            cur_peg = raw_fund.get("peg_ratio")
            if not isinstance(cur_peg, (int, float)) or cur_peg <= 0 or cur_peg < norm_peg * 0.75 or cur_peg < 0.35:
                raw_fund["peg_ratio"] = norm_peg
        if synth_output and "peg_ratio" in synth_output and raw_fund.get("peg_ratio") is not None:
            synth_output["peg_ratio"] = raw_fund["peg_ratio"]
        if synth_output and isinstance(synth_output.get("agent_outputs"), dict):
            f_sub = synth_output["agent_outputs"].get("fundamental")
            if isinstance(f_sub, dict) and raw_fund.get("peg_ratio") is not None:
                f_sub["peg_ratio"] = raw_fund["peg_ratio"]

    if isinstance(forensic_d, dict) and forensic_d.get("verdict") not in (None, "UNAUDITED") and last_price and last_price > 0:
        try:
            eq = forensic_d.get("earnings_quality") or {}
            cf = forensic_d.get("cash_conversion") or {}
            solv = forensic_d.get("solvency_health") or {}
            sub = forensic_d.get("subsidiary_attribution") or {}
            gov = forensic_d.get("governance_telemetry") or {}
            peer_b = forensic_d.get("peer_benchmarks")
            f_sc = forensic_d.get("piotroski_f_score_details")
            ben = forensic_d.get("beneish_m_score")
            fresh = forensic_d.get("filing_freshness")
            eff_sec = sector or forensic_d.get("sector") or raw_fund.get("sector") or ""
            is_bfsi = _is_bfsi_sector(eff_sec, sym)
            bfsi_h = forensic_d.get("bfsi_health") if is_bfsi else None
            old_mb = (forensic_d.get("valuation_metrics") or {}).get("method_breakdown") or {}
            stmts_proxy = {
                "symbol": sym,
                "shares_outstanding_cr": old_mb.get("shares_cr"),
                "roe_pct": raw_fund.get("roe_pct") if raw_fund.get("roe_pct") != "N/A" else old_mb.get("roe_pct"),
                "book_value_per_share": raw_fund.get("book_value") if raw_fund.get("book_value") != "N/A" else old_mb.get("bvps"),
            }
            val = _forensic_recalc_engine._calculate_sustainable_valuation(
                eq, cf, solv, raw_fund, float(last_price), stmts=stmts_proxy, sector=eff_sec, bfsi_health=bfsi_h
            )
            wc_proxy = {"debtor_days": forensic_d.get("debtor_days")}
            r_flags, cats = _forensic_recalc_engine._compile_forensic_signals(
                eq, cf, sub, solv, val, gov, peer_b, f_sc, wc_proxy,
                is_bfsi=is_bfsi, bfsi_health=bfsi_h, beneish=ben, filing_freshness=fresh,
            )
            rec = _forensic_recalc_engine._synthesize_recommendation(
                eq, cf, solv, val, r_flags, cats, float(last_price), gov, f_sc,
                is_bfsi=is_bfsi, bfsi_health=bfsi_h, beneish=ben,
            )
            forensic_d["sector"] = eff_sec or forensic_d.get("sector")
            forensic_d["market_price"] = float(last_price)
            forensic_d["fair_value"] = val["intrinsic_fair_value"]
            forensic_d["margin_of_safety_pct"] = val["margin_of_safety_pct"]
            forensic_d["valuation_metrics"] = val
            forensic_d["bfsi_health"] = bfsi_h
            forensic_d["red_flags"] = r_flags
            forensic_d["positive_catalysts"] = cats
            forensic_d["verdict"] = rec["verdict"]
            forensic_d["verdict_badge"] = rec["verdict_badge"]
            forensic_d["confidence_score"] = rec["confidence_score"]
            forensic_d["investment_thesis"] = rec["investment_thesis"]
            if fund_output:
                fund_output["forensic_verdict"] = rec["verdict"]
                fund_output["forensic_badge"] = rec["verdict_badge"]
                fund_output["forensic_red_flags"] = r_flags
        except Exception:
            pass


def get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe: str = "curated"):
    """
    Assemble the complete stock data for all symbols: latest analysis, queue status, patterns, events, sparklines.
    Uses single-pass bulk Valkey queries (or SQLite fallback when Valkey is offline) instead of N+1 queries.
    """
    symbols_list = _load_symbols_list(universe=universe)
    sym_names = [s.get("symbol", "").upper() for s in symbols_list if s.get("symbol")]

    queue_statuses = queue_mgr.get_symbol_statuses()
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk(symbols=sym_names)
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
        if synth_output is not None and not is_stale and q_status == "pending":
            q_status = "completed"

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

        if patterns and last_price and last_price > 0:
            raw_ind_p = (tech_output or {}).get("raw_indicators") or {}
            ret_10d_p = None
            if len(sparkline) >= 11 and sparkline[-11] > 0:
                ret_10d_p = ((float(last_price) - float(sparkline[-11])) / float(sparkline[-11])) * 100.0
            enriched_patterns = []
            for p in patterns:
                if isinstance(p, dict):
                    p_copy = dict(p)
                    if "setup_stage" not in p_copy:
                        p_copy.update(compute_pattern_projection(
                            p_copy,
                            curr_close=float(last_price),
                            atr_14=_extract_numeric_val(raw_ind_p.get("atr_14")),
                            rsi_14=_extract_numeric_val(raw_ind_p.get("rsi_14")),
                            rvol=_extract_numeric_val(raw_ind_p.get("rvol")),
                            ud_ratio=_extract_numeric_val(raw_ind_p.get("up_down_vol_ratio")),
                            ret_10d=ret_10d_p,
                            sma_50=_extract_numeric_val(raw_ind_p.get("sma_50")),
                            symbol=sym,
                        ))
                    elif not str(p_copy.get("projection_summary", "")).startswith(sym):
                        p_copy.update(compute_pattern_projection(
                            p_copy,
                            curr_close=float(last_price),
                            atr_14=_extract_numeric_val(raw_ind_p.get("atr_14")),
                            rsi_14=_extract_numeric_val(raw_ind_p.get("rsi_14")),
                            rvol=_extract_numeric_val(raw_ind_p.get("rvol")),
                            ud_ratio=_extract_numeric_val(raw_ind_p.get("up_down_vol_ratio")),
                            ret_10d=ret_10d_p,
                            sma_50=_extract_numeric_val(raw_ind_p.get("sma_50")),
                            symbol=sym,
                        ))
                    enriched_patterns.append(p_copy)
            patterns = enriched_patterns

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
        _refresh_peg_and_forensic(sym, sector, last_price, raw_fund, forensic_d, fund_output, synth_output)

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
            sig_d = synth_output["structured_signal"]
            sig_d["long_term_signal"] = long_term_signal
            sig_d["long_term_target"] = long_term_signal["long_term_target"]
            sig_d["long_term_verdict"] = long_term_signal["long_term_verdict"]
            sig_d["long_term_horizon"] = long_term_signal["long_term_horizon"]
            sig_d["suggested_long_term_peers"] = long_term_signal["suggested_long_term_peers"]
            if isinstance(forensic_d, dict) and forensic_d.get("fair_value") is not None:
                sig_d["intrinsic_fair_value"] = forensic_d["fair_value"]
                sig_d["margin_of_safety_pct"] = forensic_d["margin_of_safety_pct"]

            # Ensure non-SELL stocks always expose a valid Rs. Floor - Ceiling entry range and upside target
            if short_verdict != "SELL" and last_price and last_price > 0:
                cur_entry = str(sig_d.get("when_to_buy_entry") or "")
                cur_tgt = _extract_numeric_val(sig_d.get("when_to_sell_target"))
                cur_sl = _extract_numeric_val(sig_d.get("stop_loss"))
                if cur_entry.startswith("Hold existing") or not cur_tgt or cur_tgt <= last_price or not cur_sl or cur_sl >= last_price:
                    from tools.indicators import snap_nse_tick
                    lp_f = float(last_price)
                    tick = 0.01 if lp_f < 250.0 else 0.05
                    fair_v = _extract_numeric_val((forensic_d or {}).get("fair_value"))
                    swing_l20 = _extract_numeric_val(((tech_output or {}).get("raw_indicators") or {}).get("swing_low_20"))
                    new_tgt = snap_nse_tick(lp_f * 1.08, direction="up")
                    if new_tgt <= lp_f:
                        new_tgt = round(lp_f + tick, 2)
                    new_sl = snap_nse_tick(lp_f * 0.95, direction="down")
                    if new_sl >= lp_f:
                        new_sl = round(max(0.05, lp_f - tick), 2)
                    if fair_v and fair_v > lp_f:
                        dip_fl = swing_l20 if (swing_l20 and 0.93 * lp_f <= swing_l20 < lp_f) else (lp_f * 0.965)
                        raw_ceil = lp_f * 1.005
                        raw_fl = min(dip_fl, raw_ceil * 0.98)
                    elif fair_v and fair_v < lp_f:
                        val_anc = max(lp_f * 0.92, min(fair_v, swing_l20 or (lp_f * 0.95)))
                        raw_ceil = min(lp_f * 0.99, max(val_anc * 1.025, lp_f * 0.965))
                        raw_fl = min(val_anc, raw_ceil * 0.975)
                    else:
                        dip_fl = swing_l20 if (swing_l20 and 0.94 * lp_f <= swing_l20 < lp_f) else (lp_f * 0.975)
                        raw_ceil = lp_f * 1.01
                        raw_fl = min(dip_fl, raw_ceil * 0.985)
                    e_ceil = snap_nse_tick(min(raw_ceil, new_tgt * 0.96), direction="down")
                    e_fl = snap_nse_tick(min(raw_fl, e_ceil * 0.985), direction="down")
                    sig_d["when_to_buy_entry"] = f"Rs. {e_fl:.2f} - {e_ceil:.2f}"
                    sig_d["when_to_sell_target"] = f"Rs. {new_tgt}"
                    sig_d["short_term_target"] = f"Rs. {new_tgt}"
                    sig_d["stop_loss"] = f"Rs. {new_sl}"
                    rr_v = round((new_tgt - lp_f) / max(0.01, lp_f - new_sl), 2)
                    sig_d["risk_reward_ratio"] = f"1:{rr_v:.2f}"

        results.append({
            "long_term_signal": long_term_signal,
            "symbol": sym,
            "name": name,
            "sector": sector,
            "tags": s.get("tags") or [],
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


def get_history_response_body(sym: str, days: int, cache_mgr, tech_engine, interval: str = "1d") -> bytes:
    """Get cached or compute chart data (candles + indicators) for a symbol and tick interval."""
    norm_interval = tech_engine.normalize_chart_interval(interval) if hasattr(tech_engine, "normalize_chart_interval") else (interval or "1d")
    is_intraday = norm_interval in ("15m", "30m", "1h")
    freshness = str(int(time.time() // 300)) if is_intraday else (cache_mgr.get_latest_candle_date(sym) or "")
    key = (sym, days, norm_interval, freshness)
    with _history_lock:
        if key in _history_memo:
            _history_memo.move_to_end(key)
            return _history_memo[key]
    chart_data = tech_engine.get_chart_data(sym, limit_days=days, interval=norm_interval)
    body = safe_json_dumps(chart_data)
    if chart_data.get("candles"):
        freshness = str(int(time.time() // 300)) if is_intraday else (cache_mgr.get_latest_candle_date(sym) or "")
        key = (sym, days, norm_interval, freshness)
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
_pre_breakout_cache: Dict[str, Any] = {}
_pre_breakout_lock = threading.Lock()


def get_pre_breakout_projections(
    cache_mgr,
    tech_engine,
    universe: str = "monitored",
    include_fresh: bool = True,
    limit: int = 60,
    high_conviction_only: bool = True,
) -> Dict[str, Any]:
    """
    Scans cached OHLCV history + live quotes for stocks forming bullish technical patterns
    that are about to break out (pre-breakout or fresh at pivot), strictly excluding extended/late runs.
    """
    try:
        marker = cache_mgr.get_agent_runs_marker()
    except Exception:
        marker = None
    eff_limit = max(1, min(int(limit or 60), 200))
    cache_key = (universe, bool(include_fresh), bool(high_conviction_only), eff_limit, marker, int(time.time() // PICKS_CACHE_SECONDS))
    with _pre_breakout_lock:
        hit = _pre_breakout_cache.get(universe)
        if hit and hit.get("key") == cache_key:
            return hit["data"]

    result = _compute_pre_breakout_projections(
        cache_mgr,
        tech_engine,
        universe=universe,
        include_fresh=include_fresh,
        limit=eff_limit,
        high_conviction_only=high_conviction_only,
    )
    with _pre_breakout_lock:
        _pre_breakout_cache[universe] = {"key": cache_key, "data": result}
    return result


def _compute_pre_breakout_projections(
    cache_mgr,
    tech_engine,
    universe: str = "monitored",
    include_fresh: bool = True,
    limit: int = 60,
    high_conviction_only: bool = True,
) -> Dict[str, Any]:
    sym_meta: Dict[str, Dict[str, str]] = {}
    if universe in ("curated", "midcap250", "all_nse"):
        symbols_list = _load_symbols_list(universe=universe)
    else:
        symbols_list = load_active_monitored_symbols()

    for item in symbols_list:
        k = str(item.get("symbol") or "").upper().strip()
        if k and k not in sym_meta:
            sym_meta[k] = {
                "symbol": k,
                "name": item.get("name") or k,
                "sector": item.get("sector") or "Indian Equities",
            }

    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk(symbols=None if universe == "all" else list(sym_meta.keys()))
    if universe == "all":
        for sym in bulk_outputs.keys():
            k = str(sym or "").upper().strip()
            if k and k not in sym_meta:
                sym_meta[k] = {"symbol": k, "name": k, "sector": "Indian Equities"}

    sym_names = list(sym_meta.keys())
    quotes = cache_mgr.get_all_quotes()
    candle_summaries = (
        cache_mgr.get_candles_bulk_summary(sym_names, limit_days=60, sparkline_days=25)
        if hasattr(cache_mgr, "get_candles_bulk_summary")
        else {}
    )

    allowed_stages = {"IMMINENT_BREAKOUT", "FORMING_PRE_BREAKOUT"}
    if include_fresh:
        allowed_stages.add("FRESH_BREAKOUT")

    stage_rank_map = {
        "IMMINENT_BREAKOUT": 3,
        "FORMING_PRE_BREAKOUT": 2,
        "FRESH_BREAKOUT": 1,
    }

    # Bulk-resolve patterns using _pattern_memo + single batched SQLite/Valkey OHLCV fetch
    patterns_by_sym: Dict[str, List[Dict[str, Any]]] = {}
    missing_syms: List[str] = []
    latest_dates: Dict[str, str] = {}
    for sym_clean in sym_names:
        c_sum = candle_summaries.get(sym_clean)
        last_date = (c_sum or {}).get("latest_date") or ""
        latest_dates[sym_clean] = last_date
        if last_date:
            with _pattern_memo_lock:
                hit = _pattern_memo.get((sym_clean, last_date))
            if hit is not None:
                patterns_by_sym[sym_clean] = hit
                continue
        missing_syms.append(sym_clean)

    if missing_syms:
        if hasattr(cache_mgr, "get_candles_bulk_ohlcv"):
            import pandas as pd
            bulk_ohlcv = cache_mgr.get_candles_bulk_ohlcv(missing_syms, limit_days=120)
            pat_engine = getattr(tech_engine, "pattern_engine", None)
            new_memo_entries: Dict[tuple, List[Dict[str, Any]]] = {}
            for sym_clean in missing_syms:
                rows = bulk_ohlcv.get(sym_clean) or []
                if len(rows) >= 20:
                    try:
                        df_b = pd.DataFrame(rows)
                        if pat_engine is not None:
                            pats = pat_engine.scan_all_patterns(df_b)
                        else:
                            pats = tech_engine.detect_chart_patterns(tech_engine._compute_indicators(df_b))
                    except Exception:
                        pats = []
                else:
                    pats = []
                patterns_by_sym[sym_clean] = pats
                ld = latest_dates.get(sym_clean) or (str(rows[-1].get("DATE", ""))[:10] if rows else "")
                if ld:
                    new_memo_entries[(sym_clean, ld)] = pats
            if new_memo_entries:
                with _pattern_memo_lock:
                    target_syms_set = {k[0] for k in new_memo_entries}
                    for stale_k in [k for k in _pattern_memo if k[0] in target_syms_set]:
                        del _pattern_memo[stale_k]
                    _pattern_memo.update(new_memo_entries)
        else:
            for sym_clean in missing_syms:
                patterns_by_sym[sym_clean] = _patterns_from_cached_candles(sym_clean, cache_mgr, tech_engine)

    # Compute deterministic market & sector breadth regime from cached candles/SMA50
    _mkt_total = 0
    _mkt_healthy = 0
    _sec_stats: Dict[str, List[int]] = {}  # sector -> [healthy, total]
    for s_k, s_meta in sym_meta.items():
        cs = candle_summaries.get(s_k)
        sp = cs["sparkline"] if cs else []
        if not sp:
            continue
        lp_s = _extract_numeric_val((quotes.get(s_k) or {}).get("ltp")) or _extract_numeric_val(cs.get("latest_close"))
        if not lp_s:
            continue
        ri = ((bulk_outputs.get(s_k, {}).get(TECH_AGENT) or {}).get("output") or {}).get("raw_indicators") or {}
        s50 = _extract_numeric_val(ri.get("sma_50"))
        healthy = (lp_s >= s50 * 0.98) if (s50 and s50 > 0) else (len(sp) >= 11 and lp_s >= sp[-11])
        _mkt_total += 1
        if healthy:
            _mkt_healthy += 1
        sec_name = s_meta.get("sector") or "Indian Equities"
        st = _sec_stats.setdefault(sec_name, [0, 0])
        st[1] += 1
        if healthy:
            st[0] += 1

    market_ok = (_mkt_healthy / _mkt_total >= 0.40) if _mkt_total >= 10 else None
    sector_ok_map = {
        sec: (vals[0] / vals[1] >= 0.40) if vals[1] >= 3 else None
        for sec, vals in _sec_stats.items()
    }

    picks: List[Dict[str, Any]] = []
    for sym_clean, meta in sym_meta.items():
        c_sum = candle_summaries.get(sym_clean)
        sparkline = c_sum["sparkline"] if c_sum else []
        quote_lp = _extract_numeric_val((quotes.get(sym_clean) or {}).get("ltp"))
        close_lp = _extract_numeric_val((c_sum or {}).get("latest_close"))
        last_price = quote_lp or close_lp
        if not last_price or last_price <= 0:
            continue

        agents = bulk_outputs.get(sym_clean, {})
        tech_out = (agents.get(TECH_AGENT) or {}).get("output") or {}
        raw_ind = tech_out.get("raw_indicators") or {}
        synth_out = (agents.get(SYNTH_AGENT) or {}).get("output") or {}
        synth_sig = synth_out.get("structured_signal") or {}
        ts = (agents.get(SYNTH_AGENT) or {}).get("timestamp") or (c_sum or {}).get("latest_date") or ""

        patterns = patterns_by_sym.get(sym_clean, [])
        if not patterns:
            continue

        ret_10d = None
        if len(sparkline) >= 11 and sparkline[-11] > 0:
            ret_10d = ((float(last_price) - float(sparkline[-11])) / float(sparkline[-11])) * 100.0

        atr_14 = _extract_numeric_val(raw_ind.get("atr_14"))
        rsi_14 = _extract_numeric_val(raw_ind.get("rsi_14"))
        rvol = _extract_numeric_val(raw_ind.get("rvol"))
        ud_ratio = _extract_numeric_val(raw_ind.get("up_down_vol_ratio"))
        sma_50 = _extract_numeric_val(raw_ind.get("sma_50"))
        daily_close = float(sparkline[-1]) if len(sparkline) >= 1 else None
        prev_close = float(sparkline[-2]) if len(sparkline) >= 2 else None
        sector_ok = sector_ok_map.get(meta["sector"])

        best_candidate = None
        best_sort_tuple = (-1, -1, -1.0)
        for p in patterns:
            if not isinstance(p, dict):
                continue
            if "bullish" not in str(p.get("direction", "")).lower():
                continue
            if high_conviction_only and p.get("name") not in HIGH_CONVICTION_PRE_BREAKOUT_PATTERNS:
                continue
            proj = compute_pattern_projection(
                p,
                curr_close=float(last_price),
                atr_14=atr_14,
                rsi_14=rsi_14,
                rvol=rvol,
                ud_ratio=ud_ratio,
                ret_10d=ret_10d,
                sma_50=sma_50,
                symbol=sym_clean,
                daily_close=daily_close,
                prev_close=prev_close,
                market_ok=market_ok,
                sector_ok=sector_ok,
            )
            stage = proj.get("setup_stage")
            if stage not in allowed_stages or proj.get("is_late_entry"):
                continue
            w4_tgt = proj.get("week4_target")
            if not w4_tgt or w4_tgt <= float(last_price):
                continue

            cand_tuple = (
                stage_rank_map.get(stage, 0),
                int(proj.get("readiness_score") or 0),
                float(proj.get("projected_rr") or 0.0),
            )
            if cand_tuple > best_sort_tuple:
                best_sort_tuple = cand_tuple
                best_candidate = (p, proj)

        if not best_candidate:
            continue

        top_p, proj = best_candidate
        bear_conflicts = [
            bp for bp in patterns
            if isinstance(bp, dict)
            and "bearish" in str(bp.get("direction", "")).lower()
            and float(bp.get("quality_score") or 0) >= 75
        ]
        if bear_conflicts:
            b_name = bear_conflicts[0].get("name", "Bearish Pattern")
            proj["projection_summary"] = f"{proj['projection_summary']} Caution: conflicting {b_name} overhead."
            proj["forming_evidence"] = (list(proj.get("forming_evidence") or []) + [f"Caution: {b_name}"])[:4]
        trigger = float(proj["breakout_trigger"])
        w4_tgt = float(proj["week4_target"])
        stop_loss = float(proj["projected_stop_loss"])
        upside_pct = float(proj["week4_upside_pct"] or 0.0)
        downside_pct = round(max(0.5, ((trigger - stop_loss) / max(trigger, 1e-6)) * 100.0), 2)
        rr_ratio = float(proj.get("projected_rr") or round(upside_pct / max(downside_pct, 0.5), 2))
        verdict = str(synth_sig.get("action_verdict") or ("BUY" if proj["readiness_score"] >= 72 else "ACCUMULATE")).upper()
        conf_score = _extract_numeric_val(synth_sig.get("confidence_score") or synth_sig.get("confidence_percentage")) or float(proj["readiness_score"])

        picks.append({
            "symbol": sym_clean,
            "name": meta["name"],
            "sector": meta["sector"],
            "last_price": round(float(last_price), 2),
            "pattern_name": top_p.get("name", "Bullish Setup"),
            "pattern_category": top_p.get("category", "Pre-Breakout"),
            "pattern_status": top_p.get("status", ""),
            "direction": "Bullish",
            "setup_stage": proj["setup_stage"],
            "is_pre_breakout": proj["is_pre_breakout"],
            "is_late_entry": proj["is_late_entry"],
            "entry_window": proj["entry_window"],
            "breakout_trigger": trigger,
            "distance_to_breakout_pct": proj["distance_to_breakout_pct"],
            "week4_target": w4_tgt,
            "week4_target_low": proj["week4_target_low"],
            "week4_upside_pct": upside_pct,
            "week4_upside_from_ltp_pct": proj["week4_upside_from_ltp_pct"],
            "full_pattern_target": proj["full_pattern_target"],
            "stop_loss": stop_loss,
            "risk_reward": rr_ratio,
            "readiness_score": proj["readiness_score"],
            "quality_score": int(top_p.get("quality_score") or 80),
            "rsi_14": round(rsi_14, 1) if rsi_14 is not None else None,
            "rvol": round(rvol, 2) if rvol is not None else None,
            "up_down_vol_ratio": round(ud_ratio, 2) if ud_ratio is not None else None,
            "confirmation_status": proj.get("confirmation_status"),
            "daily_close_confirmed": proj.get("daily_close_confirmed"),
            "volume_confirmed": proj.get("volume_confirmed"),
            "retest_hold_confirmed": proj.get("retest_hold_confirmed"),
            "regime_ok": proj.get("regime_ok"),
            "action_verdict": verdict,
            "confidence_score": conf_score,
            "entry_range": f"Buy above Rs. {trigger:.2f}",
            "target_price": w4_tgt,
            "upside_pct": upside_pct,
            "downside_pct": downside_pct,
            "projection_summary": proj["projection_summary"],
            "forming_evidence": proj["forming_evidence"],
            "sparkline": sparkline,
            "timestamp": str(ts)[:10] if ts else "",
        })

    picks.sort(
        key=lambda x: (
            stage_rank_map.get(x["setup_stage"], 0),
            x["readiness_score"],
            x["risk_reward"],
            x["week4_upside_pct"],
        ),
        reverse=True,
    )
    limited = picks[:limit]
    return {
        "count": len(limited),
        "total_matches": len(picks),
        "universe": universe,
        "scanned_symbols": len(sym_meta),
        "as_of": datetime.now().isoformat(),
        "advisory_note": (
            "Educational & research projection only — not SEBI-registered investment advice. "
            "Wait for breakout confirmation above the trigger level and observe stop loss."
        ),
        "picks": limited,
    }


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

    # Compute deterministic market & sector breadth regime from cached candles/SMA50
    _mkt_total = 0
    _mkt_healthy = 0
    _sec_stats: Dict[str, List[int]] = {}  # sector -> [healthy, total]
    for s_k, s_meta in sym_meta.items():
        cs = candle_summaries.get(s_k)
        sp = cs["sparkline"] if cs else []
        if not sp:
            continue
        lp_s = _extract_numeric_val((quotes.get(s_k) or {}).get("ltp")) or _extract_numeric_val(cs.get("latest_close"))
        if not lp_s:
            continue
        ri = ((bulk_outputs.get(s_k, {}).get(TECH_AGENT) or {}).get("output") or {}).get("raw_indicators") or {}
        s50 = _extract_numeric_val(ri.get("sma_50"))
        healthy = (lp_s >= s50 * 0.98) if (s50 and s50 > 0) else (len(sp) >= 11 and lp_s >= sp[-11])
        _mkt_total += 1
        if healthy:
            _mkt_healthy += 1
        sec_name = s_meta.get("sector") or "Indian Equities"
        st = _sec_stats.setdefault(sec_name, [0, 0])
        st[1] += 1
        if healthy:
            st[0] += 1

    market_ok = (_mkt_healthy / _mkt_total >= 0.40) if _mkt_total >= 10 else None
    sector_ok_map = {
        sec: (vals[0] / vals[1] >= 0.40) if vals[1] >= 3 else None
        for sec, vals in _sec_stats.items()
    }

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
        if not pattern_str or pattern_str in ("N/A", "Consolidation Range"):
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

        tech_out = (agents.get(TECH_AGENT) or {}).get("output") or {}
        raw_ind = tech_out.get("raw_indicators") or {}
        det_pats = tech_out.get("detected_patterns") or raw_ind.get("detected_patterns") or []
        p_lower = pattern_str.lower()
        inferred_dir = (
            "Bullish"
            if ("bull" in p_lower or "golden" in p_lower or "inverse" in p_lower or "bottom" in p_lower or "spring" in p_lower or "saucer" in p_lower or "cup" in p_lower or "ascending" in p_lower or "vcp" in p_lower)
            else ("Bearish" if ("bear" in p_lower or "death" in p_lower or "top" in p_lower or "descending" in p_lower or "evening" in p_lower or "utad" in p_lower) else "Neutral")
        )
        top_p = det_pats[0] if det_pats else {
            "name": pattern_str,
            "direction": inferred_dir,
            "entry_trigger": _extract_numeric_val(entry_raw),
            "target_price": target_price,
            "stop_loss": stop_loss,
            "quality_score": conf_score,
        }
        ret_10d = None
        if len(sparkline) >= 11 and sparkline[-11] > 0:
            ret_10d = ((float(last_price) - float(sparkline[-11])) / float(sparkline[-11])) * 100.0
        rvol_val = _extract_numeric_val(raw_ind.get("rvol"))
        rsi_val = _extract_numeric_val(raw_ind.get("rsi_14"))
        ud_val = _extract_numeric_val(raw_ind.get("up_down_vol_ratio"))
        proj = compute_pattern_projection(
            top_p,
            curr_close=float(last_price),
            atr_14=_extract_numeric_val(raw_ind.get("atr_14")),
            rsi_14=rsi_val,
            rvol=rvol_val,
            ud_ratio=ud_val,
            ret_10d=ret_10d,
            sma_50=_extract_numeric_val(raw_ind.get("sma_50")),
            symbol=sym_clean,
            daily_close=float(sparkline[-1]) if len(sparkline) >= 1 else None,
            prev_close=float(sparkline[-2]) if len(sparkline) >= 2 else None,
        )

        upside_pct = round(((target_price - last_price) / last_price) * 100, 2) if (target_price and target_price > last_price) else 0.0
        downside_pct = round(((last_price - stop_loss) / last_price) * 100, 2) if (stop_loss and stop_loss < last_price) else 4.0
        rr_ratio = round(upside_pct / downside_pct, 2) if (downside_pct > 0 and upside_pct > 0) else (_extract_numeric_val(sig.get("reward_to_risk_ratio")) or 1.5)

        if upside_pct < min_upside and min_upside > 0:
            continue

        meta = sym_meta.get(sym_clean, {"name": sym_clean, "sector": "Indian Equities"})
        if "cross" in p_lower or "moving average" in p_lower:
            category = "Moving Average"
        elif "saucer" in p_lower or "rounding bottom" in p_lower or "cup" in p_lower or "vcp" in p_lower:
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
            "direction": "Bullish" if (inferred_dir == "Bullish" or upside_pct > 0) else "Bearish",
            "action_verdict": verdict,
            "confidence_score": conf_score,
            "entry_range": entry_raw,
            "target_price": round(target_price, 2) if target_price else None,
            "stop_loss": round(stop_loss, 2) if stop_loss else None,
            "upside_pct": upside_pct,
            "downside_pct": round(downside_pct, 2),
            "risk_reward": rr_ratio,
            "setup_stage": proj["setup_stage"],
            "is_pre_breakout": proj["is_pre_breakout"],
            "is_late_entry": proj["is_late_entry"],
            "entry_window": proj["entry_window"],
            "breakout_trigger": proj["breakout_trigger"],
            "distance_to_breakout_pct": proj["distance_to_breakout_pct"],
            "week4_target": proj["week4_target"],
            "week4_target_low": proj["week4_target_low"],
            "week4_upside_pct": proj["week4_upside_pct"],
            "readiness_score": proj["readiness_score"],
            "rsi_14": round(rsi_val, 1) if rsi_val is not None else None,
            "rvol": round(rvol_val, 2) if rvol_val is not None else None,
            "up_down_vol_ratio": round(ud_val, 2) if ud_val is not None else None,
            "confirmation_status": proj.get("confirmation_status"),
            "daily_close_confirmed": proj.get("daily_close_confirmed"),
            "volume_confirmed": proj.get("volume_confirmed"),
            "retest_hold_confirmed": proj.get("retest_hold_confirmed"),
            "regime_ok": proj.get("regime_ok"),
            "projection_summary": proj["projection_summary"],
            "forming_evidence": proj["forming_evidence"],
            "sparkline": sparkline,
            "timestamp": ts[:10] if ts else "",
        })

    picks.sort(key=lambda x: (
        bool(x.get("is_pre_breakout", False)),
        x["action_verdict"] in ("BUY", "ACCUMULATE"),
        x["upside_pct"] > 0,
        x.get("readiness_score", 0),
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
    sym_meta: Dict[str, Dict[str, str]] = {}
    for s in symbols_list:
        k = str(s.get("symbol") or "").upper().strip()
        if k and k not in sym_meta:
            sym_meta[k] = {
                "name": s.get("name") or k,
                "sector": s.get("sector") or "Indian Equities",
            }
    sym_names = list(sym_meta.keys())
    quotes = cache_mgr.get_all_quotes()
    bulk_outputs = cache_mgr.get_latest_agent_outputs_bulk(symbols=sym_names)
    candle_summaries = (
        cache_mgr.get_candles_bulk_summary(sym_names, limit_days=260, sparkline_days=5)
        if hasattr(cache_mgr, "get_candles_bulk_summary")
        else {}
    )
    # Compute deterministic market & sector breadth regime from cached candles/SMA50
    _mkt_total = 0
    _mkt_healthy = 0
    _sec_stats: Dict[str, List[int]] = {}  # sector -> [healthy, total]
    for s_k, s_meta in sym_meta.items():
        cs = candle_summaries.get(s_k)
        sp = cs["sparkline"] if cs else []
        if not sp:
            continue
        lp_s = _extract_numeric_val((quotes.get(s_k) or {}).get("ltp")) or _extract_numeric_val(cs.get("latest_close"))
        if not lp_s:
            continue
        ri = ((bulk_outputs.get(s_k, {}).get(TECH_AGENT) or {}).get("output") or {}).get("raw_indicators") or {}
        s50 = _extract_numeric_val(ri.get("sma_50"))
        healthy = (lp_s >= s50 * 0.98) if (s50 and s50 > 0) else (len(sp) >= 11 and lp_s >= sp[-11])
        _mkt_total += 1
        if healthy:
            _mkt_healthy += 1
        sec_name = s_meta.get("sector") or "Indian Equities"
        st = _sec_stats.setdefault(sec_name, [0, 0])
        st[1] += 1
        if healthy:
            st[0] += 1

    market_ok = (_mkt_healthy / _mkt_total >= 0.40) if _mkt_total >= 10 else None
    sector_ok_map = {
        sec: (vals[0] / vals[1] >= 0.40) if vals[1] >= 3 else None
        for sec, vals in _sec_stats.items()
    }

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
        c_sum = candle_summaries.get(sym)
        if raw_tech.get("pct_from_52w_high") is None:
            if c_sum and c_sum.get("high_52w") and c_sum.get("latest_close"):
                h_max = float(c_sum["high_52w"])
                p_now = float(c_sum["latest_close"])
                if h_max > 0 and p_now > 0:
                    tech_res = dict(tech_res or {"raw_indicators": {}})
                    tech_res["raw_indicators"] = dict(tech_res.get("raw_indicators", {}))
                    tech_res["raw_indicators"]["pct_from_52w_high"] = round((p_now - h_max) / h_max * 100, 2)
                    tech_res["raw_indicators"]["high_52w"] = round(h_max, 2)
                    tech_res["raw_indicators"]["last_price"] = p_now

        raw_fund = (fund_res or {}).get("raw_fundamentals") or {}
        last_price = float(
            _extract_numeric_val((synth_res or {}).get("last_price"))
            or _extract_numeric_val(((tech_res or {}).get("raw_indicators") or {}).get("last_price"))
            or _extract_numeric_val((c_sum or {}).get("latest_close"))
            or 0.0
        )
        forensic_d = (fund_res or {}).get("forensic_analysis")
        _refresh_peg_and_forensic(sym, sec, last_price, raw_fund, forensic_d, fund_res, synth_res)

        if last_price > 0 and synth_res and isinstance(synth_res.get("structured_signal"), dict):
            short_verdict = synth_res["structured_signal"].get("action_verdict", "HOLD")
            lt_sig = long_term_engine.evaluate_long_term_stock(
                symbol=sym,
                name=cname,
                sector=sec,
                last_price=last_price,
                short_verdict=short_verdict,
                fund_data=raw_fund,
                forensic_data=forensic_d,
            )
            synth_res["structured_signal"]["long_term_verdict"] = lt_sig["long_term_verdict"]
            synth_res["structured_signal"]["long_term_target"] = lt_sig["long_term_target"]

        pick = score_fundamental_pick(sym, synth_res, tech_res, fund_res=fund_res, sector=sec)
        if pick is None or (pick.get("score") or 0) <= 20 or not pick.get("last_price"):
            continue
        pick["company"] = cname
        pick["sector"] = sec
        picks.append(pick)

    picks.sort(key=lambda x: x["score"], reverse=True)
    top10 = picks[:10]
    return {"picks": top10, "count": len(top10), "universe": len(symbols_list)}
