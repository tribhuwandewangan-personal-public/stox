"""
Background Market & Macro Sentinel Worker Thread.
Runs continuously in parallel to poll global macro indicators (S&P 500, GIFT Nifty, Crude, DXY, Gold)
and global news. When significant shifts occur, the LLM merges and updates a shared Common Market Bulletin
in SQLite (storage/cache.db) so all stock prediction streams automatically incorporate the latest market context.
"""

import threading
import time
from typing import Dict, Any, Optional

from config import get_llm, VERBOSE_LOGGING, FAST_MODE
from storage.cache_manager import CacheManager
from tools.macro_tools import GlobalMacroEngine
from langchain_core.prompts import PromptTemplate

class BackgroundMacroSentinel:
    def __init__(self, cache_manager: CacheManager = None, poll_interval_seconds: int = 300):
        self.cache_manager = cache_manager or CacheManager()
        self.macro_engine = GlobalMacroEngine(self.cache_manager)
        self._llm = None
        self.poll_interval = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.1, max_tokens=150, timeout=12)
        return self._llm

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
        """Continuous background polling loop."""
        # Initial run on startup
        self.update_market_bulletin()

        while not self._stop_event.is_set():
            if self._stop_event.wait(self.poll_interval):
                break
            self.update_market_bulletin()

    def update_market_bulletin(self) -> Dict[str, Any]:
        """Fetches macro indicators, uses LLM to merge insights, and updates shared bulletin in SQLite."""
        try:
            macro_res = self.macro_engine.fetch_macro_indicators()
            indicators = macro_res.get("indicators", [])

            if FAST_MODE:
                sentiment_label = "Neutral"
                summary_text = "Global market indicators reflect a stable, neutral-to-balanced macroeconomic backdrop for Indian equities."
                self.cache_manager.save_market_bulletin(
                    sentiment_label=sentiment_label,
                    macro_summary=summary_text,
                    raw_indicators={"indicators": indicators}
                )
                return {
                    "sentiment_label": sentiment_label,
                    "summary": summary_text,
                    "indicators": indicators
                }

            indic_text = "\n".join([f"- {m['indicator']}: {m['summary']}" for m in indicators])

            prompt = PromptTemplate.from_template(
                """You are a Chief Market Strategist monitoring common global market factors.
Synthesize the following live global market indicators into a unified Common Market Context Bulletin:

Live Indicators:
{indic_text}

Produce a 2-sentence Common Market Context Bulletin assessing whether global tailwinds are Bullish, Bearish, or Neutral for Indian equities today.
"""
            )

            chain = prompt | self.llm
            response = chain.invoke({"indic_text": indic_text})
            summary_text = response.content if hasattr(response, 'content') else str(response)

            sentiment_label = "Neutral"
            if "bullish" in summary_text.lower():
                sentiment_label = "Bullish"
            elif "bearish" in summary_text.lower():
                sentiment_label = "Bearish"

            # Save to shared SQLite database table
            self.cache_manager.save_market_bulletin(
                sentiment_label=sentiment_label,
                macro_summary=summary_text,
                raw_indicators={"indicators": indicators}
            )

            if VERBOSE_LOGGING:
                print(f"🌐 [Macro Sentinel Update] Shared Bulletin: [{sentiment_label}] {summary_text[:90]}...")

            return {
                "sentiment_label": sentiment_label,
                "summary": summary_text,
                "indicators": indicators
            }
        except Exception as e:
            if VERBOSE_LOGGING:
                print(f"⚠️ [Macro Sentinel Notice] Bulletin update deferred: {e}")
            return {"sentiment_label": "Neutral", "summary": "Global markets present a stable backdrop.", "indicators": []}
