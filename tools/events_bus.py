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
from typing import Callable, Any, Dict, List
import logging

logger = logging.getLogger(__name__)

# Thread-safe registry of subscribers
_subscribers: List[Callable[[str, Dict[str, Any]], None]] = []
_lock = threading.Lock()


def subscribe(callback: Callable[[str, Dict[str, Any]], None]):
    """
    Register a callback to receive events.
    callback(event_type: str, payload: dict) is called synchronously for each event.
    """
    with _lock:
        _subscribers.append(callback)


def publish(event_type: str, payload: Dict[str, Any]):
    """
    Publish an event to all subscribers.

    Args:
        event_type: e.g. 'quotes', 'analysis_done', 'job', 'market'
        payload: event-specific dict
    """
    with _lock:
        subs = list(_subscribers)  # snapshot

    for cb in subs:
        try:
            cb(event_type, payload)
        except Exception as e:
            logger.error(f"[events_bus] subscriber failed on {event_type}: {e}", exc_info=True)


# Event type constants (for documentation)
QUOTES = "quotes"               # payload: {quotes: {SYM: {...}, ...}, market_state, market_open}
ANALYSIS_DONE = "analysis_done" # payload: {symbol: str, ...}
JOB = "job"                     # payload: {job_id, status, ...}
MARKET = "market"               # payload: {state: str}
