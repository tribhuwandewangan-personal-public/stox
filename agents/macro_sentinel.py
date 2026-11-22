"""
Background Market & Macro Sentinel Worker Thread.
Polls global macro indicators (S&P 500, Nasdaq, Crude, DXY, USD/INR, US 10Y, Gold) on a timer, keeps the
shared macro cache fresh, and writes a Common Market Bulletin to SQLite (storage/cache.db) that the dashboard
shows. The bulletin is computed with deterministic rules (tools/macro_tools.py) -- no LLM.
"""

import threading
from datetime import datetime, time as dtime
from typing import Dict, Any, Optional

from config import VERBOSE_LOGGING
from storage.cache_manager import CacheManager
from tools import market_calendar
from tools.macro_tools import GlobalMacroEngine, compute_macro_sentiment

# Re-fetch whenever the cache is older than this (poll interval is 5 min, so every poll refreshes)
SENTINEL_MAX_CACHE_AGE_HOURS = 0.05
ACTIVE_START_IST = dtime(8, 30)
ACTIVE_END_IST = dtime(16, 30)


class BackgroundMacroSentinel:
    def __init__(
        self,
        cache_manager: CacheManager = None,
        poll_interval_seconds: int = 300,
        off_hours_interval_seconds: int = 3600,
    ):
        self.cache_manager = cache_manager or CacheManager()
        self.macro_engine = GlobalMacroEngine(self.cache_manager)
        self.poll_interval = max(30, int(poll_interval_seconds))
        self.off_hours_interval = max(self.poll_interval, int(off_hours_interval_seconds))
        self._stop_event = threading.Event()
        self._thread = None

    @staticmethod
    def is_active_window(now: Optional[datetime] = None) -> bool:
        """True on NSE trading days between 08:30 and 16:30 IST."""
        n = now or market_calendar.now_ist()
        n_ist = (
            n.astimezone(market_calendar.IST)
            if n.tzinfo is not None
            else n.replace(tzinfo=market_calendar.IST)
        )
        return market_calendar.is_trading_day(n_ist.date()) and (
            ACTIVE_START_IST <= n_ist.time() <= ACTIVE_END_IST
        )

    def next_wait_seconds(self, now: Optional[datetime] = None) -> int:
        return self.poll_interval if self.is_active_window(now) else self.off_hours_interval

    def start(self):
        """Starts the background sentinel monitor thread."""
        if self._thread is None or not self._thread.is_alive():
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MacroSentinelThread")
            self._thread.start()
            if VERBOSE_LOGGING:
                print("🌐 [Macro Sentinel] Background market monitoring thread started.")

    def stop(self):
        """Stops the background sentinel monitor thread."""
        if self._thread and self._thread.is_alive():
            self._stop_event.set()
            self._thread.join(timeout=2.0)

    def _run_loop(self):
        """Market-hours aware background polling loop."""
        self.update_market_bulletin()

        while not self._stop_event.is_set():
            wait_s = self.next_wait_seconds()
            if self._stop_event.wait(wait_s):
                break
            if self.is_active_window() or not self.cache_manager.get_latest_market_bulletin():
                self.update_market_bulletin()

    def update_market_bulletin(self) -> Dict[str, Any]:
        """Fetches macro indicators, computes rule-based sentiment, saves bulletin, and prunes history."""
        try:
            macro_res = self.macro_engine.fetch_macro_indicators(max_age_hours=SENTINEL_MAX_CACHE_AGE_HOURS)
            indicators = macro_res.get("indicators", [])
            sentiment = compute_macro_sentiment(indicators)

            # Don't overwrite a good bulletin with an "unavailable" one
            if sentiment["available"]:
                self.cache_manager.save_market_bulletin(
                    sentiment_label=sentiment["label"],
                    macro_summary=sentiment["summary"],
                    raw_indicators={"indicators": indicators},
                )
                if hasattr(self.cache_manager, "prune_macro_history"):
                    self.cache_manager.prune_macro_history(keep_bulletins=200, keep_days=14)
                if VERBOSE_LOGGING:
                    print(f"🌐 [Macro Sentinel Update] Shared Bulletin: [{sentiment['label']}] {sentiment['summary'][:90]}...")

            return {
                "sentiment_label": sentiment["label"],
                "summary": sentiment["summary"],
                "indicators": indicators
            }
        except Exception as e:
            if VERBOSE_LOGGING:
                print(f"⚠️ [Macro Sentinel Notice] Bulletin update deferred: {e}")
            return {
                "sentiment_label": "Neutral",
                "summary": "Global macro data is unavailable right now.",
                "indicators": []
            }
