"""
Starlette ASGI application factory for the NSE Stock Predictor.

Replaces the stdlib http.server handler with a modern async framework:
  - Same REST routes and responses as the legacy handler
  - WebSocket endpoint for real-time updates
  - Security middleware (Host, CSRF, Origin checks)
  - SPA serving with deep-link fallback (placeholder, built Angular app goes here)
  - Lifespan context to start QuotePoller and Scheduler threads
"""

import os
import sys
import asyncio
import threading
from datetime import datetime
from typing import Callable, Any

from starlette.applications import Starlette
from starlette.routing import Route, Mount, WebSocketRoute
from starlette.responses import JSONResponse, FileResponse, HTMLResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import (
    CACHE_DB_PATH, ENGINE_LABEL, SYMBOLS_FILE_PATH, DASHBOARD_HOST,
    QUOTE_SOURCES, QUOTE_POLL_SECONDS, AUTO_SCHEDULE, MAX_SYMBOL_WORKERS
)
from storage.cache_manager import CacheManager
from storage.queue_manager import ValkeyQueueManager
from graph import MultiAgentWorkflow
from tools.historical_data_tools import HistoricalDataEngine
from tools.tech_tools import TechnicalAnalysisEngine
from tools.events_tools import EventsEngine
from tools.long_term_strategy import long_term_engine
from agents.macro_sentinel import BackgroundMacroSentinel
from tools.quote_tools import QuoteService, QuotePoller
from tools.scheduler import Scheduler
from tools import events_bus
from api.routes import routes, set_managers
from api.services import load_active_monitored_symbols
from api.security import SecurityMiddleware, WebSocketSecurityMiddleware
from api.ws import websocket_endpoint, manager as ws_manager


# ===================================================================================== Singletons

cache_mgr = CacheManager()
queue_mgr = ValkeyQueueManager()
hist_engine = HistoricalDataEngine(cache_manager=cache_mgr)
tech_engine = TechnicalAnalysisEngine(rag_engine=hist_engine, cache_manager=cache_mgr)
events_engine = EventsEngine(cache_manager=cache_mgr)
quote_service = QuoteService(cache_mgr, sources=QUOTE_SOURCES)
quote_poller = QuotePoller(
    quote_service,
    symbols_loader=lambda: [x["symbol"] for x in load_active_monitored_symbols()],
    poll_seconds=QUOTE_POLL_SECONDS,
)
_workflow_instance = None
_scheduler_instance = None
_sentinel_instance = None


def get_workflow():
    """Lazy-load workflow instance."""
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = MultiAgentWorkflow(cache_mgr)
    return _workflow_instance


# ===================================================================================== Lifespan


async def lifespan(app: Starlette):
    """Startup and shutdown context for the app."""
    global _scheduler_instance, _sentinel_instance

    # Startup
    print("🚀 [Starlette] Starting up...", flush=True)

    # Start quote poller
    quote_poller.start()
    print(f"📊 [QuotePoller] Started (polls every {QUOTE_POLL_SECONDS}s while market is open)", flush=True)

    # Start scheduler & market-hours aware macro sentinel if enabled
    if AUTO_SCHEDULE:
        _scheduler_instance = Scheduler(
            cache_mgr,
            workflow_getter=get_workflow,
            symbols_loader=load_active_monitored_symbols,
            max_workers=MAX_SYMBOL_WORKERS,
            on_symbol_done=queue_mgr.mark_completed,
        )
        _scheduler_instance.start()
        _sentinel_instance = BackgroundMacroSentinel(cache_mgr)
        _sentinel_instance.start()
        print("🗓️ [Scheduler] Auto-schedule ON (pre-market 08:45 IST, post-close 16:00 IST) + MacroSentinel", flush=True)

    # Subscribe to events_bus for WebSocket broadcast
    event_loop = asyncio.get_event_loop()

    def event_handler(event_type: str, payload: dict):
        """Broadcast events from backend threads to WebSocket clients."""
        async def broadcast():
            await ws_manager.broadcast({
                "type": event_type,
                "payload": payload,
                "timestamp": datetime.now().isoformat()
            })

        # Schedule the coroutine on the event loop (safe from threads)
        if event_loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(), event_loop)

    events_bus.subscribe(event_handler)

    yield

    # Shutdown
    print("🛑 [Starlette] Shutting down...", flush=True)
    quote_poller.stop()
    if _scheduler_instance:
        _scheduler_instance.stop()
    if _sentinel_instance:
        _sentinel_instance.stop()


# ===================================================================================== Middleware


class HostOnlyMiddleware(BaseHTTPMiddleware):
    """Return 403 for non-loopback Host headers when DASHBOARD_HOST is loopback."""
    async def dispatch(self, request: Request, call_next):
        from tools.web_security import host_header_ok, LOOPBACK_NAMES
        enforce = DASHBOARD_HOST in LOOPBACK_NAMES
        if enforce:
            host = request.headers.get("host", "")
            if not host_header_ok(host, enforce):
                return JSONResponse({"error": "Forbidden host"}, status_code=403)
        return await call_next(request)


# ===================================================================================== App Factory


def create_app() -> Starlette:
    """Create and configure the Starlette app."""

    # Pass managers to routes so they can use them
    set_managers(
        cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine,
        quote_poller, quote_service, get_workflow
    )

    # WebSocket route
    ws_routes = [
        WebSocketRoute("/ws", endpoint=websocket_endpoint),
    ]

    # API routes
    api_routes = routes

    # Merged routes
    all_routes = api_routes + ws_routes

    # Create app with lifespan
    app = Starlette(
        routes=all_routes,
        lifespan=lifespan,
        debug=False
    )

    # Add middleware (enforces loopback Host check and POST CSRF/Content-Type guard)
    app.add_middleware(SecurityMiddleware)

    # WebSocket security
    app = WebSocketSecurityMiddleware(app)

    return app


# For uvicorn: "uvicorn api.main:app"
app = create_app()
