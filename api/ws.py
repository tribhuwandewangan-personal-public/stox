"""
WebSocket endpoint for real-time updates to connected clients.

Handles:
  - Client connection and disconnection
  - Broadcasting events from the events_bus to all connected clients
  - Periodic ping/pong for connection keep-alive (Heroku routers drop idle after 55s)
  - Fallback to polling on client disconnect (browser will reconnect)
"""

import asyncio
import json
import sys
import os
from typing import Set, Dict, Any
from starlette.websockets import WebSocket, WebSocketDisconnect
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.services import safe_json_dumps


class ConnectionManager:
    """Manages connected WebSocket clients and broadcasts events to them."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        """Register a new WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        """Unregister a WebSocket connection."""
        async with self._lock:
            self.active_connections.discard(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to all connected clients."""
        async with self._lock:
            disconnected = set()
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception:
                    disconnected.add(connection)
            # Clean up disconnected clients
            for conn in disconnected:
                self.active_connections.discard(conn)


manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint at /ws.

    Client receives JSON messages:
      {type: "quotes", quotes: {...}, market_state, market_open, timestamp}
      {type: "analysis_done", symbol, timestamp}
      {type: "ping"}
      ...

    Client can send:
      {type: "pong"}
    """
    await manager.connect(websocket)

    # Send initial snapshot of all stock data
    try:
        from api.routes import _managers
        cache_mgr = _managers.get("cache_mgr")
        queue_mgr = _managers.get("queue_mgr")
        hist_engine = _managers.get("hist_engine")
        tech_engine = _managers.get("tech_engine")
        events_engine = _managers.get("events_engine")

        if all([cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine]):
            from api.services import get_all_stock_data
            snapshot = get_all_stock_data(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine)
            await websocket.send_json({
                "type": "snapshot",
                "data": snapshot,
                "timestamp": datetime.now().isoformat()
            })
    except Exception as e:
        print(f"⚠️ [WebSocket] Error sending snapshot: {e}", flush=True)

    # Ping task to keep the connection alive (Heroku 55s idle timeout)
    ping_task = None

    async def ping_task_fn():
        try:
            while True:
                await asyncio.sleep(20)  # Ping every 20 seconds
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
        except Exception:
            pass

    try:
        ping_task = asyncio.create_task(ping_task_fn())

        while True:
            try:
                data = await websocket.receive_json()
                # Client can send pong or other client messages here
                msg_type = data.get("type")
                if msg_type == "pong":
                    pass  # Just acknowledge, connection is alive
                else:
                    pass  # Ignore other client messages for now
            except WebSocketDisconnect:
                break
            except json.JSONDecodeError:
                break
            except Exception as e:
                print(f"⚠️ [WebSocket] Error receiving: {e}", flush=True)
                break
    finally:
        if ping_task:
            ping_task.cancel()
        await manager.disconnect(websocket)


def broadcast_event(event_type: str, payload: Dict[str, Any]):
    """
    Called from events_bus subscribers (running in threads) to broadcast to WebSocket clients.
    This is a sync function that schedules async work.
    """
    try:
        import asyncio
        loop = asyncio.get_event_loop()
    except RuntimeError:
        # No event loop in this thread; this is being called from a background thread
        # We would need to use run_coroutine_threadsafe() in the app, deferred for now
        return

    message = {
        "type": event_type,
        "payload": payload,
        "timestamp": datetime.now().isoformat()
    }

    # Schedule the broadcast
    task = asyncio.create_task(manager.broadcast(message))
