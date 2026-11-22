"""
REST API routes for the Starlette app.

These are thin wrappers around service functions in api/services.py.
The actual logic is handler-independent and can be reused by any HTTP framework.
"""

import os
import sys
import urllib.parse
from datetime import datetime
from typing import Dict, Any
from starlette.routing import Route
from starlette.responses import JSONResponse, FileResponse, HTMLResponse, Response
from starlette.requests import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH
from tools.web_security import valid_symbol, resolve_within
from tools.quote_tools import build_quotes_response
from tools.outcome_tracker import compute_accuracy
from tools.symbol_search_tools import search_internet_symbols, add_symbol_to_json, remove_symbol_from_json
from api.services import safe_json_dumps, get_stocks_response_body, get_history_response_body, get_top_pattern_picks
from api.services import _load_symbols_list


# Injected by app factory; these are set during app startup
_managers: Dict[str, Any] = {}


def set_managers(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, quote_poller, quote_service, get_workflow):
    """Called by the app factory to inject dependencies."""
    global _managers
    _managers = {
        "cache_mgr": cache_mgr,
        "queue_mgr": queue_mgr,
        "hist_engine": hist_engine,
        "tech_engine": tech_engine,
        "events_engine": events_engine,
        "quote_poller": quote_poller,
        "quote_service": quote_service,
        "get_workflow": get_workflow,
    }


# ===================================================================================== Routes

async def status(request: Request) -> JSONResponse:
    """GET /api/status: Server status, queue, and macro indicators."""
    try:
        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]

        q_status = queue_mgr.get_queue_status()
        shared_bulletin = cache_mgr.get_latest_market_bulletin()
        macro_items = cache_mgr.get_cached_macro(max_age_hours=24)

        resp_data = {
            "timestamp": datetime.now().isoformat(),
            "queue_status": q_status,
            "bulletin": shared_bulletin,
            "macro_items": macro_items
        }
        return JSONResponse(resp_data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def stocks(request: Request) -> Response:
    """GET /api/stocks: All stocks with latest analysis and live quotes. Supports ?universe=curated|midcap250|all_nse"""
    try:
        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]
        hist_engine = _managers["hist_engine"]
        tech_engine = _managers["tech_engine"]
        events_engine = _managers["events_engine"]

        universe = request.query_params.get("universe", "curated").lower().strip()
        if universe not in ("curated", "midcap250", "all_nse"):
            universe = "curated"

        body = get_stocks_response_body(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe=universe)
        return Response(content=body, media_type="application/json")
    except Exception as e:
        return JSONResponse({"error": str(e), "stocks": []}, status_code=500)


async def quotes(request: Request) -> JSONResponse:
    """GET /api/quotes: Current live quotes for all symbols."""
    try:
        cache_mgr = _managers["cache_mgr"]
        quote_poller = _managers["quote_poller"]

        resp = build_quotes_response(cache_mgr, quote_poller)
        return JSONResponse(resp)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def accuracy(request: Request) -> JSONResponse:
    """GET /api/accuracy: Prediction accuracy report."""
    try:
        cache_mgr = _managers["cache_mgr"]
        resp = compute_accuracy(cache_mgr)
        return JSONResponse(resp)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def history(request: Request) -> JSONResponse:
    """GET /api/history?symbol=XXX&days=90: Chart data for a symbol."""
    try:
        cache_mgr = _managers["cache_mgr"]
        tech_engine = _managers["tech_engine"]

        query_params = request.query_params
        sym = query_params.get("symbol", "").upper().strip()
        if sym and not valid_symbol(sym):
            return JSONResponse({"error": "Invalid symbol", "candles": []}, status_code=400)

        raw_days = query_params.get("days", "90")
        try:
            days = int(''.join(c for c in str(raw_days) if c.isdigit())) or 90
        except Exception:
            days = 90

        if not sym:
            return JSONResponse({"error": "Missing symbol", "candles": []})

        body = get_history_response_body(sym, days, cache_mgr, tech_engine)
        return Response(content=body, media_type="application/json")
    except Exception as e:
        print(f"Error fetching chart data: {e}", flush=True)
        return JSONResponse({"error": str(e), "candles": []}, status_code=500)


async def events(request: Request) -> JSONResponse:
    """GET /api/events?symbol=XXX: Stock events and macro catalysts."""
    try:
        events_engine = _managers["events_engine"]

        query_params = request.query_params
        sym = query_params.get("symbol", "").upper().strip()
        if sym and not valid_symbol(sym):
            return JSONResponse({"error": "Invalid symbol"}, status_code=400)

        if sym:
            events_data = events_engine.fetch_stock_events(sym)
        else:
            events_data = {"upcoming_macro_catalysts": events_engine.get_upcoming_macro_events()}

        return JSONResponse(events_data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def search_symbol(request: Request) -> JSONResponse:
    """GET /api/search-symbol?q=ABC: Search for symbols on the internet."""
    try:
        query_params = request.query_params
        q_str = query_params.get("q", "").strip()
        matches = search_internet_symbols(q_str) if q_str else []
        return JSONResponse({"query": q_str, "results": matches})
    except Exception as e:
        return JSONResponse({"error": str(e), "results": []}, status_code=500)


async def trigger(request: Request) -> JSONResponse:
    """POST /api/trigger: Manually trigger re-analysis of a single stock."""
    try:
        import threading
        from datetime import datetime

        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]
        get_workflow = _managers["get_workflow"]

        data = await request.json()
        symbol = str(data.get("symbol", "")).upper().strip()

        if not symbol:
            return JSONResponse({"status": "error", "message": "Missing symbol"}, status_code=400)
        if not valid_symbol(symbol):
            return JSONResponse({"status": "error", "message": "Invalid symbol"}, status_code=400)

        # Find company name and sector from symbols.json
        c_name, c_sec = "", ""
        for s_item in _load_symbols_list():
            if s_item.get("symbol", "").upper() == symbol:
                c_name = s_item.get("name", "")
                c_sec = s_item.get("sector", "")
                break

        # Placeholder: in the real implementation, this would check _trigger_slots and _running_symbols
        # For now, just launch it
        def run_single():
            try:
                with cache_mgr._get_connection() as conn:
                    conn.execute("UPDATE persistent_stock_queue SET status = 'in_progress' WHERE symbol = ?", (symbol,))
                try:
                    get_workflow().run_analysis(symbol, company_name=c_name, sector=c_sec, force_refresh=True)
                    queue_mgr.mark_completed(symbol)
                except Exception as e:
                    print(f"⚠️ Error in single stock analysis for {symbol}: {e}")
                    with cache_mgr._get_connection() as conn:
                        conn.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE symbol = ?", (symbol,))
            except Exception as e:
                print(f"⚠️ Error in run_single: {e}")

        threading.Thread(target=run_single, daemon=True).start()
        return JSONResponse({"status": "triggered", "symbol": symbol})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def add_symbol(request: Request) -> JSONResponse:
    """POST /api/add-symbol: Add a symbol to the watchlist."""
    try:
        data = await request.json()
        sym = str(data.get("symbol", "")).upper().strip()
        name = str(data.get("name", "")).strip()[:120]
        sector = str(data.get("sector", "")).strip()[:80]
        exchange = str(data.get("exchange", "NSE")).strip()[:10]

        if not valid_symbol(sym):
            return JSONResponse({"status": "error", "message": "Invalid symbol"}, status_code=400)

        result = add_symbol_to_json(symbol=sym, name=name, sector=sector, exchange=exchange)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def remove_symbol(request: Request) -> JSONResponse:
    """POST /api/remove-symbol: Remove a symbol from the watchlist."""
    try:
        data = await request.json()
        sym = str(data.get("symbol", "")).upper().strip()

        if not valid_symbol(sym):
            return JSONResponse({"status": "error", "message": "Invalid symbol"}, status_code=400)

        result = remove_symbol_from_json(symbol=sym)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def portfolio(request: Request) -> JSONResponse:
    """GET /api/portfolio: User's portfolio holdings with multi-agent long-term & swing diagnostics."""
    try:
        from tools.kite_portfolio import KitePortfolioEngine
        cache_mgr = _managers.get("cache_mgr")
        engine = KitePortfolioEngine(cache_manager=cache_mgr)
        data = engine.evaluate_portfolio()
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e), "summary": {}, "holdings": []}, status_code=500)


async def fundamental_picks(request: Request) -> JSONResponse:
    """GET /api/fundamental-picks: Top 10 fundamentally sound stocks at the right technical entry."""
    try:
        from tools.fundamental_picks import score_fundamental_pick
        cache_mgr = _managers.get("cache_mgr")
        symbols_list = _load_symbols_list()

        SYNTH_AGENT_NAME = "Master Prediction Synthesizer Agent"
        TECH_AGENT_NAME  = "Technical Analysis Agent"

        picks = []
        for item in symbols_list:
            sym   = item.get("symbol", "").upper()
            cname = item.get("name", "")
            sec   = item.get("sector", "")

            synth_res = cache_mgr.get_latest_agent_output(sym, SYNTH_AGENT_NAME, max_age_hours=168)
            if not synth_res:
                synth_res = cache_mgr.get_latest_agent_output(sym, SYNTH_AGENT_NAME, max_age_hours=None)
            if not synth_res:
                continue

            tech_res = cache_mgr.get_latest_agent_output(sym, TECH_AGENT_NAME, max_age_hours=168)
            fund_res = cache_mgr.get_latest_agent_output(sym, "Fundamental Analyst Agent", max_age_hours=168)
            if not fund_res:
                fund_res = cache_mgr.get_latest_agent_output(sym, "Fundamental Analyst Agent", max_age_hours=None)

            # Compute 52W metrics from cached candles if missing
            raw_tech = (tech_res or {}).get("raw_indicators", {})
            if raw_tech.get("pct_from_52w_high") is None:
                try:
                    c_list = cache_mgr.get_cached_candles(sym, limit_days=260)
                    if c_list:
                        h_max = max(float(c.get("HIGH_PRICE") or c.get("CLOSE_PRICE") or 0.0) for c in c_list)
                        p_now = float(c_list[-1].get("CLOSE_PRICE") or 0.0)
                        if h_max > 0 and p_now > 0:
                            if not tech_res:
                                tech_res = {"raw_indicators": {}}
                            tech_res.setdefault("raw_indicators", {})
                            tech_res["raw_indicators"]["pct_from_52w_high"] = round((p_now - h_max) / h_max * 100, 2)
                            tech_res["raw_indicators"]["high_52w"] = round(h_max, 2)
                            tech_res["raw_indicators"]["last_price"] = p_now
                except Exception:
                    pass

            pick = score_fundamental_pick(sym, synth_res, tech_res, fund_res=fund_res)
            if pick is None:
                continue

            pick["company"] = cname
            pick["sector"]  = sec
            picks.append(pick)

        picks.sort(key=lambda x: x["score"], reverse=True)
        top10 = picks[:10]

        return JSONResponse({"picks": top10, "count": len(top10), "universe": len(symbols_list)})
    except Exception as e:
        return JSONResponse({"error": str(e), "picks": [], "count": 0}, status_code=500)


async def macro_risk_shield(request: Request) -> JSONResponse:
    """GET /api/macro-risk-shield: Multi-tier macro risk level and portfolio safeguarding playbook."""
    try:
        from tools.macro_tools import GlobalMacroEngine, compute_macro_sentiment
        from tools.macro_risk_shield import build_macro_risk_shield
        from tools.kite_portfolio import KitePortfolioEngine

        cache_mgr = _managers.get("cache_mgr")
        macro_engine = GlobalMacroEngine(cache_mgr)
        macro_res = macro_engine.fetch_macro_indicators(max_age_hours=12)
        indicators = macro_res.get("indicators", [])
        sentiment = compute_macro_sentiment(indicators)

        holdings = []
        try:
            port_engine = KitePortfolioEngine(cache_manager=cache_mgr)
            port_data = port_engine.evaluate_portfolio()
            holdings = port_data.get("holdings", [])
        except Exception:
            pass

        shield_data = build_macro_risk_shield(sentiment, holdings)
        return JSONResponse(shield_data)
    except Exception as e:
        return JSONResponse({"error": str(e), "risk_key": "ELEVATED", "risk_label": "🟡 ELEVATED"}, status_code=500)


async def market_scanner(request: Request) -> JSONResponse:
    """GET /api/market-scanner: Returns latest market scan results of strong non-symbols.json stocks."""
    try:
        import threading
        from tools.market_scanner import get_latest_cached_scan, run_market_scan
        cached = get_latest_cached_scan()
        if cached.get("stocks"):
            return JSONResponse(cached)

        # If no cached scan exists yet, run a quick background scan of top candidates
        threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 25, "top_n": 10}, daemon=True).start()
        return JSONResponse({"status": "scanning", "stocks": [], "message": "Initial market scan in progress..."})
    except Exception as e:
        return JSONResponse({"error": str(e), "stocks": []}, status_code=500)


async def market_scanner_trigger(request: Request) -> JSONResponse:
    """POST /api/market-scanner/scan: Triggers a fresh scan of non-watchlist stocks."""
    try:
        import threading
        from tools.market_scanner import run_market_scan
        threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 50, "top_n": 15}, daemon=True).start()
        return JSONResponse({"status": "triggered", "message": "Market scan started in background"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


async def top_patterns(request: Request) -> JSONResponse:
    """GET /api/patterns/top: High-conviction technical chart patterns across all analyzed stocks."""
    try:
        cache_mgr = _managers["cache_mgr"]
        tech_engine = _managers["tech_engine"]
        min_upside = float(request.query_params.get("min_upside", 0.0))
        picks = get_top_pattern_picks(cache_mgr, tech_engine, min_upside=min_upside)
        return JSONResponse({"count": len(picks), "picks": picks})
    except Exception as e:
        return JSONResponse({"error": str(e), "picks": []}, status_code=500)


async def favicon(request: Request) -> Response:
    """GET /favicon.ico: Empty response."""
    return Response(status_code=204)


async def company_profile(request: Request) -> JSONResponse:
    """GET /api/company/{ticker}: Full company profile including forensic analysis, governance, and peers."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return JSONResponse({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)

        gov = analysis.get("governance_telemetry", {})
        eq = analysis.get("earnings_quality", {})

        company_data = {
            "ticker": ticker,
            "exchange": "NSE",
            "name": analysis.get("company_name", ticker),
            "sector": analysis.get("sector", "N/A"),
            "promoterHoldingPct": gov.get("promoter_holding_pct"),
            "promoterPledgePct": 0.0 if gov.get("pledge_risk") == "LOW" else 25.0,
            "auditRiskScore": gov.get("audit_risk_score"),
            "governanceGrade": gov.get("governance_grade", "SOUND"),
            "earningsQuality": {
                "reportedPAT": eq.get("reported_pat", 0.0),
                "adjustedPAT": eq.get("adjusted_pat", 0.0),
                "sustainablePAT": eq.get("sustainable_pat", 0.0),
                "exceptionalItems": [],
                "redFlag": eq.get("quality_grade") in ("SEVERELY_DISTORTED", "MODERATELY_DISTORTED")
            },
            "forensicAnalysis": analysis
        }
        return JSONResponse(company_data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def earnings_profile(request: Request) -> JSONResponse:
    """GET /api/earnings/{ticker}: Earnings quality and exceptional items breakdown."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return JSONResponse({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        eq = analysis.get("earnings_quality", {})

        return JSONResponse({
            "reportedPAT": eq.get("reported_pat", 0.0),
            "adjustedPAT": eq.get("adjusted_pat", 0.0),
            "sustainablePAT": eq.get("sustainable_pat", 0.0),
            "exceptionalItems": [
                {
                    "description": "Exceptional Items",
                    "amount": eq.get("exceptional_items", 0.0),
                    "type": "income" if eq.get("exceptional_items", 0.0) >= 0 else "expense",
                    "category": "Other"
                }
            ] if eq.get("exceptional_items", 0.0) != 0.0 else []
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def financial_income(request: Request) -> JSONResponse:
    """GET /api/financial/{ticker}/income: Income statements."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return JSONResponse({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        eq = analysis.get("earnings_quality", {})
        cf = analysis.get("cash_conversion", {})

        statements = [
            {
                "period": "LTM",
                "revenue": cf.get("revenue_growth_pct"),
                "reportedPAT": eq.get("reported_pat"),
                "exceptionalItems": eq.get("exceptional_items"),
                "sustainablePAT": eq.get("sustainable_pat")
            }
        ]
        return JSONResponse(statements)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def financial_balance(request: Request) -> JSONResponse:
    """GET /api/financial/{ticker}/balance: Balance sheet telemetry."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return JSONResponse({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        solv = analysis.get("solvency_health", {})

        statements = [
            {
                "period": "LTM",
                "totalDebt": solv.get("total_debt"),
                "totalCash": solv.get("total_cash"),
                "netDebt": solv.get("net_debt"),
                "currentRatio": solv.get("current_ratio"),
                "debtToEquity": solv.get("debt_to_equity")
            }
        ]
        return JSONResponse(statements)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


async def financial_cashflow(request: Request) -> JSONResponse:
    """GET /api/financial/{ticker}/cashflow: Cash flow statements."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return JSONResponse({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        cf = analysis.get("cash_conversion", {})

        statements = [
            {
                "period": "LTM",
                "cashFromOperations": cf.get("cfo"),
                "capitalExpenditure": cf.get("capex"),
                "freeCashFlow": cf.get("fcf"),
                "cfoToPatRatio": cf.get("cfo_to_pat_ratio")
            }
        ]
        return JSONResponse(statements)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# Route definitions
routes = [
    Route("/api/status", endpoint=status, methods=["GET"]),
    Route("/api/stocks", endpoint=stocks, methods=["GET"]),
    Route("/api/quotes", endpoint=quotes, methods=["GET"]),
    Route("/api/accuracy", endpoint=accuracy, methods=["GET"]),
    Route("/api/history", endpoint=history, methods=["GET"]),
    Route("/api/patterns/top", endpoint=top_patterns, methods=["GET"]),
    Route("/api/pattern-screener", endpoint=top_patterns, methods=["GET"]),
    Route("/api/events", endpoint=events, methods=["GET"]),
    Route("/api/search-symbol", endpoint=search_symbol, methods=["GET"]),
    Route("/api/portfolio", endpoint=portfolio, methods=["GET"]),
    Route("/api/fundamental-picks", endpoint=fundamental_picks, methods=["GET"]),
    Route("/api/macro-risk-shield", endpoint=macro_risk_shield, methods=["GET"]),
    Route("/api/market-scanner", endpoint=market_scanner, methods=["GET"]),
    Route("/api/market-scanner/scan", endpoint=market_scanner_trigger, methods=["POST"]),
    Route("/api/company/{ticker}", endpoint=company_profile, methods=["GET"]),
    Route("/api/earnings/{ticker}", endpoint=earnings_profile, methods=["GET"]),
    Route("/api/financial/{ticker}/income", endpoint=financial_income, methods=["GET"]),
    Route("/api/financial/{ticker}/balance", endpoint=financial_balance, methods=["GET"]),
    Route("/api/financial/{ticker}/cashflow", endpoint=financial_cashflow, methods=["GET"]),
    Route("/api/trigger", endpoint=trigger, methods=["POST"]),
    Route("/api/add-symbol", endpoint=add_symbol, methods=["POST"]),
    Route("/api/remove-symbol", endpoint=remove_symbol, methods=["POST"]),
    Route("/favicon.ico", endpoint=favicon, methods=["GET"]),
]
