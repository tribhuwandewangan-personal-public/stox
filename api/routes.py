"""
REST API routes for the Starlette app.

These are thin wrappers around service functions in api/services.py.
The actual logic is handler-independent and can be reused by any HTTP framework.
"""

import os
import sys
import threading
import urllib.parse
from datetime import datetime
from typing import Dict, Any
from starlette.routing import Route
from starlette.responses import Response
from starlette.requests import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH, ENGINE_LABEL, MAX_CONCURRENT_TRIGGERS
from tools.web_security import valid_symbol, resolve_within
from tools.quote_tools import build_quotes_response
from tools.outcome_tracker import compute_accuracy
from tools.symbol_search_tools import search_internet_symbols, add_symbol_to_json, remove_symbol_from_json
from api.services import (
    safe_json_dumps, get_stocks_response_body, get_history_response_body,
    get_top_pattern_picks, get_pre_breakout_projections, _load_symbols_list,
)
from tools import events_bus

_trigger_slots = threading.BoundedSemaphore(MAX_CONCURRENT_TRIGGERS)
_running_symbols = set()
_running_lock = threading.Lock()


def _json_response(data: Any, status_code: int = 200) -> Response:
    """Emit NaN/Infinity-safe JSON with consistent HTTP status code and no-store caching."""
    return Response(
        content=safe_json_dumps(data),
        status_code=status_code,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


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

async def status(request: Request) -> Response:
    """GET /api/status: Server status, queue, and macro indicators."""
    try:
        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]

        q_status = queue_mgr.get_queue_status()
        shared_bulletin = cache_mgr.get_latest_market_bulletin()
        macro_items = cache_mgr.get_cached_macro(max_age_hours=24)

        resp_data = {
            "model": ENGINE_LABEL,
            "timestamp": datetime.now().isoformat(),
            "ws_enabled": True,
            "queue_status": q_status,
            "bulletin": shared_bulletin,
            "macro_items": macro_items
        }
        return _json_response(resp_data)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


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
        return Response(content=body, media_type="application/json", headers={"Cache-Control": "no-store"})
    except Exception as e:
        return _json_response({"error": str(e), "stocks": []}, status_code=500)


async def quotes(request: Request) -> Response:
    """GET /api/quotes: Current live quotes for all symbols."""
    try:
        cache_mgr = _managers["cache_mgr"]
        quote_poller = _managers["quote_poller"]

        resp = build_quotes_response(cache_mgr, quote_poller)
        return _json_response(resp)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def accuracy(request: Request) -> Response:
    """GET /api/accuracy: Prediction accuracy report."""
    try:
        cache_mgr = _managers["cache_mgr"]
        resp = compute_accuracy(cache_mgr)
        return _json_response(resp)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def history(request: Request) -> Response:
    """GET /api/history?symbol=XXX&days=365&interval=1d: Chart data for a symbol."""
    try:
        cache_mgr = _managers["cache_mgr"]
        tech_engine = _managers["tech_engine"]

        query_params = request.query_params
        sym = query_params.get("symbol", "").upper().strip()
        if not sym:
            return _json_response({"error": "Missing symbol", "candles": []}, status_code=400)
        if not valid_symbol(sym):
            return _json_response({"error": "Invalid symbol", "candles": []}, status_code=400)

        raw_days = query_params.get("days", "365")
        try:
            days = int(''.join(c for c in str(raw_days) if c.isdigit())) or 365
        except Exception:
            days = 365

        interval = query_params.get("interval", "1d").strip() or "1d"
        body = get_history_response_body(sym, days, cache_mgr, tech_engine, interval=interval)
        return Response(content=body, media_type="application/json", headers={"Cache-Control": "no-store"})
    except Exception as e:
        print(f"Error fetching chart data: {e}", flush=True)
        return _json_response({"error": str(e), "candles": []}, status_code=500)


async def events(request: Request) -> Response:
    """GET /api/events?symbol=XXX: Stock events and macro catalysts."""
    try:
        events_engine = _managers["events_engine"]

        query_params = request.query_params
        sym = query_params.get("symbol", "").upper().strip()
        if sym and not valid_symbol(sym):
            return _json_response({"error": "Invalid symbol"}, status_code=400)

        if sym:
            events_data = events_engine.fetch_stock_events(sym)
        else:
            events_data = {"upcoming_macro_catalysts": events_engine.get_upcoming_macro_events()}

        return _json_response(events_data)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def search_symbol(request: Request) -> Response:
    """GET /api/search-symbol?q=ABC: Search for symbols by partial ticker, company name, or sector."""
    try:
        query_params = request.query_params
        q_str = query_params.get("q", "").strip()
        matches = search_internet_symbols(q_str)
        return _json_response({"query": q_str, "results": matches})
    except Exception as e:
        return _json_response({"error": str(e), "results": []}, status_code=500)


async def trigger(request: Request) -> Response:
    """POST /api/trigger: Manually trigger re-analysis of a single stock (semaphore-bounded)."""
    try:
        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]
        get_workflow = _managers["get_workflow"]

        data = await request.json()
        symbol = str(data.get("symbol", "")).upper().strip()

        if not symbol:
            return _json_response({"status": "error", "message": "Missing symbol"}, status_code=400)
        if not valid_symbol(symbol):
            return _json_response({"status": "error", "message": "Invalid symbol"}, status_code=400)

        c_name, c_sec = "", ""
        for univ in ("curated", "midcap250", "all_nse"):
            for s_item in _load_symbols_list(universe=univ):
                if s_item.get("symbol", "").upper() == symbol:
                    c_name = s_item.get("name", "")
                    c_sec = s_item.get("sector", "")
                    break
            if c_name:
                break

        with _running_lock:
            if symbol in _running_symbols:
                return _json_response({
                    "status": "already_running",
                    "symbol": symbol,
                    "message": f"{symbol} is already being analyzed.",
                })
            if not _trigger_slots.acquire(blocking=False):
                return _json_response({
                    "status": "busy",
                    "symbol": symbol,
                    "message": f"{MAX_CONCURRENT_TRIGGERS} analyses are already running. Try again shortly.",
                }, status_code=429)
            _running_symbols.add(symbol)

        def run_single():
            try:
                with cache_mgr._get_connection() as conn:
                    conn.execute("UPDATE persistent_stock_queue SET status = 'in_progress' WHERE symbol = ?", (symbol,))
                try:
                    get_workflow().run_analysis(symbol, company_name=c_name, sector=c_sec, force_refresh=True)
                    queue_mgr.mark_completed(symbol)
                    events_bus.publish(events_bus.ANALYSIS_DONE, {
                        "symbol": symbol,
                        "timestamp": datetime.now().isoformat(),
                    })
                except Exception as e:
                    print(f"⚠️ Error in single stock analysis for {symbol}: {e}")
                    with cache_mgr._get_connection() as conn:
                        conn.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE symbol = ?", (symbol,))
            finally:
                with _running_lock:
                    _running_symbols.discard(symbol)
                _trigger_slots.release()

        threading.Thread(target=run_single, daemon=True).start()
        return _json_response({"status": "triggered", "symbol": symbol})
    except Exception as e:
        return _json_response({"status": "error", "message": str(e)}, status_code=500)


async def add_symbol(request: Request) -> Response:
    """POST /api/add-symbol: Add a symbol to the watchlist."""
    try:
        data = await request.json()
        sym = str(data.get("symbol", "")).upper().strip()
        name = str(data.get("name", "")).strip()[:120]
        sector = str(data.get("sector", "")).strip()[:80]
        exchange = str(data.get("exchange", "NSE")).strip()[:10]

        if not valid_symbol(sym):
            return _json_response({"status": "error", "message": "Invalid symbol"}, status_code=400)

        result = add_symbol_to_json(symbol=sym, name=name, sector=sector, exchange=exchange)
        return _json_response(result)
    except Exception as e:
        return _json_response({"status": "error", "message": str(e)}, status_code=500)


async def remove_symbol(request: Request) -> Response:
    """POST /api/remove-symbol: Remove a symbol from the watchlist."""
    try:
        data = await request.json()
        sym = str(data.get("symbol", "")).upper().strip()

        if not valid_symbol(sym):
            return _json_response({"status": "error", "message": "Invalid symbol"}, status_code=400)

        result = remove_symbol_from_json(symbol=sym)
        return _json_response(result)
    except Exception as e:
        return _json_response({"status": "error", "message": str(e)}, status_code=500)


async def portfolio(request: Request) -> Response:
    """GET /api/portfolio: User's portfolio holdings with multi-agent long-term & swing diagnostics."""
    try:
        from tools.kite_portfolio import KitePortfolioEngine
        cache_mgr = _managers.get("cache_mgr")
        engine = KitePortfolioEngine(cache_manager=cache_mgr)
        data = engine.evaluate_portfolio()
        return _json_response(data)
    except Exception as e:
        return _json_response({"error": str(e), "summary": {}, "holdings": []}, status_code=500)


async def fundamental_picks(request: Request) -> Response:
    """GET /api/fundamental-picks: Top 10 fundamentally sound stocks at the right technical entry."""
    try:
        from api.services import get_fundamental_picks_data
        cache_mgr = _managers.get("cache_mgr")
        universe = request.query_params.get("universe", "curated").lower().strip()
        data = get_fundamental_picks_data(cache_mgr, universe=universe)
        return _json_response(data)
    except Exception as e:
        return _json_response({"error": str(e), "picks": [], "count": 0}, status_code=500)


async def macro_risk_shield(request: Request) -> Response:
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
        return _json_response(shield_data)
    except Exception as e:
        return _json_response({"error": str(e), "risk_key": "UNAVAILABLE", "risk_label": "⚪ UNAVAILABLE"}, status_code=500)


async def market_scanner(request: Request) -> Response:
    """GET /api/market-scanner: Returns latest market scan results of strong non-symbols.json stocks."""
    try:
        from tools.market_scanner import get_latest_cached_scan, run_market_scan
        cached = get_latest_cached_scan()
        if cached.get("stocks"):
            return _json_response(cached)

        threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 25, "top_n": 10}, daemon=True).start()
        return _json_response({"status": "scanning", "stocks": [], "message": "Initial market scan in progress..."})
    except Exception as e:
        return _json_response({"error": str(e), "stocks": []}, status_code=500)


async def market_scanner_trigger(request: Request) -> Response:
    """POST /api/market-scanner/scan: Triggers a fresh scan of non-watchlist stocks."""
    try:
        from tools.market_scanner import run_market_scan
        threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 50, "top_n": 15}, daemon=True).start()
        return _json_response({"status": "triggered", "message": "Market scan started in background"})
    except Exception as e:
        return _json_response({"status": "error", "message": str(e)}, status_code=500)


async def top_patterns(request: Request) -> Response:
    """GET /api/patterns/top: High-conviction technical chart patterns across all analyzed stocks."""
    try:
        cache_mgr = _managers["cache_mgr"]
        tech_engine = _managers["tech_engine"]
        min_upside = float(request.query_params.get("min_upside", 0.0))
        picks = get_top_pattern_picks(cache_mgr, tech_engine, min_upside=min_upside)
        return _json_response({"count": len(picks), "picks": picks})
    except Exception as e:
        return _json_response({"error": str(e), "picks": []}, status_code=500)


async def pre_breakout_patterns(request: Request) -> Response:
    """GET /api/patterns/pre-breakout: Forming bullish setups about to break out with 4-week projections."""
    try:
        cache_mgr = _managers["cache_mgr"]
        tech_engine = _managers["tech_engine"]
        universe = request.query_params.get("universe", "monitored").lower().strip()
        if universe not in ("monitored", "curated", "midcap250", "all_nse", "all"):
            universe = "monitored"
        include_fresh = request.query_params.get("include_fresh", "1").strip() not in ("0", "false", "no")
        high_conviction = request.query_params.get("high_conviction", "1").strip() not in ("0", "false", "no")
        try:
            limit = max(1, min(int(request.query_params.get("limit", "60")), 200))
        except (ValueError, TypeError):
            limit = 60
        payload = get_pre_breakout_projections(
            cache_mgr,
            tech_engine,
            universe=universe,
            include_fresh=include_fresh,
            limit=limit,
            high_conviction_only=high_conviction,
        )
        return _json_response(payload)
    except Exception as e:
        return _json_response({"error": str(e), "count": 0, "picks": []}, status_code=500)


async def favicon(request: Request) -> Response:
    """GET /favicon.ico: Empty response."""
    return Response(status_code=204)


async def company_profile(request: Request) -> Response:
    """GET /api/company/{ticker}: Full company profile including forensic analysis, governance, and peers."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return _json_response({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)

        gov = analysis.get("governance_telemetry", {})
        eq = analysis.get("earnings_quality", {})

        exc_amt = eq.get("exceptional_items")
        exc_items = [
            {
                "description": "Exceptional Items",
                "amount": exc_amt,
                "type": "income" if exc_amt >= 0 else "expense",
                "category": "Other",
            }
        ] if (exc_amt is not None and exc_amt != 0.0) else []

        company_data = {
            "ticker": ticker,
            "exchange": "NSE",
            "name": analysis.get("company_name", ticker),
            "sector": analysis.get("sector", "N/A"),
            "promoterHoldingPct": gov.get("promoter_holding_pct"),
            "promoterPledgePct": gov.get("promoter_pledge_pct"),
            "auditRiskScore": gov.get("audit_risk_score"),
            "governanceGrade": gov.get("governance_grade", "UNAUDITED"),
            "earningsQuality": {
                "reportedPAT": eq.get("reported_pat"),
                "adjustedPAT": eq.get("adjusted_pat"),
                "sustainablePAT": eq.get("sustainable_pat"),
                "exceptionalItems": exc_items,
                "redFlag": eq.get("quality_grade") in ("SEVERELY_DISTORTED", "MODERATELY_DISTORTED")
            },
            "forensicAnalysis": analysis
        }
        return _json_response(company_data)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def earnings_profile(request: Request) -> Response:
    """GET /api/earnings/{ticker}: Earnings quality and exceptional items breakdown."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return _json_response({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        eq = analysis.get("earnings_quality", {})
        exc_amt = eq.get("exceptional_items")

        return _json_response({
            "reportedPAT": eq.get("reported_pat"),
            "adjustedPAT": eq.get("adjusted_pat"),
            "sustainablePAT": eq.get("sustainable_pat"),
            "exceptionalItems": [
                {
                    "description": "Exceptional Items",
                    "amount": exc_amt,
                    "type": "income" if exc_amt >= 0 else "expense",
                    "category": "Other"
                }
            ] if (exc_amt is not None and exc_amt != 0.0) else []
        })
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def financial_income(request: Request) -> Response:
    """GET /api/financial/{ticker}/income: Income statements."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return _json_response({"error": "Invalid ticker"}, status_code=400)

        cache_mgr = _managers.get("cache_mgr")
        from tools.forensic_financial_engine import ForensicFinancialEngine
        forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
        analysis = forensic_engine.analyze_company(ticker)
        eq = analysis.get("earnings_quality", {})
        cf = analysis.get("cash_conversion", {})

        statements = [
            {
                "period": "LTM",
                "revenue": eq.get("revenue"),
                "revenueGrowthPct": cf.get("revenue_growth_pct"),
                "reportedPAT": eq.get("reported_pat"),
                "exceptionalItems": eq.get("exceptional_items"),
                "sustainablePAT": eq.get("sustainable_pat")
            }
        ]
        return _json_response(statements)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def financial_balance(request: Request) -> Response:
    """GET /api/financial/{ticker}/balance: Balance sheet telemetry."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return _json_response({"error": "Invalid ticker"}, status_code=400)

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
        return _json_response(statements)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def financial_cashflow(request: Request) -> Response:
    """GET /api/financial/{ticker}/cashflow: Cash flow statements."""
    try:
        ticker = request.path_params.get("ticker", "").upper().strip()
        if not ticker or not valid_symbol(ticker):
            return _json_response({"error": "Invalid ticker"}, status_code=400)

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
        return _json_response(statements)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def sector_research_list(request: Request) -> Response:
    """GET /api/sector-research: List saved LLM sector research runs from SQLite."""
    try:
        cache_mgr = _managers["cache_mgr"]
        runs = cache_mgr.list_sector_research_runs()
        return _json_response({"runs": runs})
    except Exception as e:
        return _json_response({"error": str(e), "runs": []}, status_code=500)


async def sector_research_create(request: Request) -> Response:
    """POST /api/sector-research: Run Gemini sector decomposition + existing Stox stock analysis."""
    try:
        cache_mgr = _managers["cache_mgr"]
        data = await request.json()
        if not isinstance(data, dict):
            return _json_response({"error": "Invalid JSON body"}, status_code=400)
        sector_query = str(data.get("sector", "")).strip()
        if not sector_query or len(sector_query) > 200:
            return _json_response({"error": "Provide a valid sector query (1-200 chars)"}, status_code=400)
        use_search = bool(data.get("use_search", False))
        force_refresh = bool(data.get("force_refresh", False))

        from tools.sector_research_engine import SectorResearchEngine
        engine = SectorResearchEngine(cache_manager=cache_mgr)
        result = await asyncio.to_thread(
            engine.run_research,
            sector_query,
            use_search=use_search,
            force_refresh=force_refresh,
        )
        return _json_response(result)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def sector_research_detail(request: Request) -> Response:
    """GET /api/sector-research/{run_id}: Get full value-chain & ranked stocks for a run."""
    try:
        cache_mgr = _managers["cache_mgr"]
        run_id = int(request.path_params.get("run_id", 0))
        run = cache_mgr.get_sector_research_run(run_id)
        if not run:
            return _json_response({"error": "Sector research run not found"}, status_code=404)
        return _json_response(run)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def sector_research_rescore(request: Request) -> Response:
    """POST /api/sector-research/{run_id}/rescore: Re-score stored stocks using existing Stox tools."""
    try:
        cache_mgr = _managers["cache_mgr"]
        run_id = int(request.path_params.get("run_id", 0))
        from tools.sector_research_engine import SectorResearchEngine
        engine = SectorResearchEngine(cache_manager=cache_mgr)
        result = await asyncio.to_thread(engine.rescore_run, run_id)
        if not result:
            return _json_response({"error": "Sector research run not found"}, status_code=404)
        return _json_response(result)
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


async def sector_research_delete(request: Request) -> Response:
    """DELETE / POST /api/sector-research/{run_id}/delete: Remove a saved run."""
    try:
        cache_mgr = _managers["cache_mgr"]
        run_id = int(request.path_params.get("run_id", 0))
        deleted = cache_mgr.delete_sector_research_run(run_id)
        if not deleted:
            return _json_response({"error": "Sector research run not found"}, status_code=404)
        return _json_response({"status": "deleted", "id": run_id})
    except Exception as e:
        return _json_response({"error": str(e)}, status_code=500)


# Route definitions
routes = [
    Route("/api/status", endpoint=status, methods=["GET"]),
    Route("/api/stocks", endpoint=stocks, methods=["GET"]),
    Route("/api/quotes", endpoint=quotes, methods=["GET"]),
    Route("/api/accuracy", endpoint=accuracy, methods=["GET"]),
    Route("/api/history", endpoint=history, methods=["GET"]),
    Route("/api/patterns/top", endpoint=top_patterns, methods=["GET"]),
    Route("/api/patterns/pre-breakout", endpoint=pre_breakout_patterns, methods=["GET"]),
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
    Route("/api/sector-research", endpoint=sector_research_list, methods=["GET"]),
    Route("/api/sector-research", endpoint=sector_research_create, methods=["POST"]),
    Route("/api/sector-research/{run_id:int}", endpoint=sector_research_detail, methods=["GET"]),
    Route("/api/sector-research/{run_id:int}", endpoint=sector_research_delete, methods=["DELETE"]),
    Route("/api/sector-research/{run_id:int}/rescore", endpoint=sector_research_rescore, methods=["POST"]),
    Route("/api/sector-research/{run_id:int}/delete", endpoint=sector_research_delete, methods=["POST"]),
    Route("/favicon.ico", endpoint=favicon, methods=["GET"]),
]
