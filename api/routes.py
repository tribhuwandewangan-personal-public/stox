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
from starlette.responses import JSONResponse, FileResponse, HTMLResponse
from starlette.requests import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH
from tools.web_security import valid_symbol, resolve_within
from tools.quote_tools import build_quotes_response
from tools.outcome_tracker import compute_accuracy
from tools.symbol_search_tools import search_internet_symbols, add_symbol_to_json, remove_symbol_from_json
from api.services import safe_json_dumps, get_stocks_response_body, get_history_response_body
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


async def stocks(request: Request) -> JSONResponse:
    """GET /api/stocks: All stocks with latest analysis and live quotes."""
    try:
        cache_mgr = _managers["cache_mgr"]
        queue_mgr = _managers["queue_mgr"]
        hist_engine = _managers["hist_engine"]
        tech_engine = _managers["tech_engine"]
        events_engine = _managers["events_engine"]

        body = get_stocks_response_body(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine)
        return JSONResponse(body)
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
        return JSONResponse(body)
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


async def favicon(request: Request) -> Response:
    """GET /favicon.ico: Empty response."""
    return Response(status_code=204)


# Route definitions
routes = [
    Route("/api/status", endpoint=status, methods=["GET"]),
    Route("/api/stocks", endpoint=stocks, methods=["GET"]),
    Route("/api/quotes", endpoint=quotes, methods=["GET"]),
    Route("/api/accuracy", endpoint=accuracy, methods=["GET"]),
    Route("/api/history", endpoint=history, methods=["GET"]),
    Route("/api/events", endpoint=events, methods=["GET"]),
    Route("/api/search-symbol", endpoint=search_symbol, methods=["GET"]),
    Route("/api/portfolio", endpoint=portfolio, methods=["GET"]),
    Route("/api/trigger", endpoint=trigger, methods=["POST"]),
    Route("/api/add-symbol", endpoint=add_symbol, methods=["POST"]),
    Route("/api/remove-symbol", endpoint=remove_symbol, methods=["POST"]),
    Route("/favicon.ico", endpoint=favicon, methods=["GET"]),
]
