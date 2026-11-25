"""
Thread-safe event publication bus for backend events.

This is a simple pub/sub system that allows various parts of the backend (quote poller,
scheduler, trigger, etc.) to publish domain events without knowing about HTTP frameworks
or WebSocket clients. The Starlette app will wire this to broadcast updates to connected
WebSocket clients.

Events are published synchronously; if a subscriber is slow, it will block the publisher.
For this codebase's scale (52 stocks), that's acceptable.
"""

import threading
from collections import deque
from datetime import datetime
from typing import Callable, Any, Dict, List
import logging

logger = logging.getLogger(__name__)

# Thread-safe registry of subscribers & in-memory activity feed ring buffer
_subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
_history: deque = deque(maxlen=250)
_next_event_id = 1
_lock = threading.Lock()
_SKIP_FEED_TYPES = {"quotes"}


def subscribe(callback: Callable[[str, Dict[str, Any]], None]):
    """
    Register a callback to receive events.
    callback(event_type: str, payload: dict) is called synchronously for each event.
    """
    with _lock:
        _subscribers.append(callback)


def publish(event_type: str, payload: Dict[str, Any]):
    """
    Publish an event to all subscribers and append meaningful changes to the activity feed.

    Args:
        event_type: e.g. 'quotes', 'analysis_done', 'verdict_change', 'catalyst_early_warning', 'scheduler', 'system_alert'
        payload: event-specific dict
    """
    global _next_event_id
    with _lock:
        subs = list(_subscribers)  # snapshot
        if event_type not in _SKIP_FEED_TYPES:
            _history.append({
                "id": _next_event_id,
                "type": event_type,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "payload": dict(payload or {}),
            })
            _next_event_id += 1

    for cb in subs:
        try:
            cb(event_type, payload)
        except Exception as e:
            logger.error(f"[events_bus] subscriber failed on {event_type}: {e}", exc_info=True)


def get_recent_events(since_id: int = 0, limit: int = 60) -> List[Dict[str, Any]]:
    """Returns recent non-quote activity feed events with id > since_id."""
    with _lock:
        items = [e for e in _history if e["id"] > since_id]
    if limit > 0 and len(items) > limit:
        items = items[-limit:]
    return items


# Event type constants (for documentation)
QUOTES = "quotes"               # payload: {quotes: {SYM: {...}, ...}, market_state, market_open}
ANALYSIS_DONE = "analysis_done" # payload: {symbol: str, ...}
JOB = "job"                     # payload: {job_id, status, ...}
MARKET = "market"               # payload: {state: str}
