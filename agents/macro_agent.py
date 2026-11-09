"""
Global Macro Agent.
Deterministic: converts live global indicators (S&P 500, Nasdaq, Brent, DXY, USD/INR, US 10Y) into a
Bullish / Neutral / Bearish macro backdrop for Indian equities using explicit rules
(see tools/macro_tools.py: compute_macro_sentiment). No LLM involved.
"""

from typing import Dict, Any, Union

from tools.macro_tools import GlobalMacroEngine, compute_macro_sentiment
from storage.cache_manager import CacheManager


class GlobalMacroAgent:
    def __init__(self, macro_engine: Union[GlobalMacroEngine, CacheManager] = None):
        if isinstance(macro_engine, CacheManager):
            self.macro_engine = GlobalMacroEngine(cache_manager=macro_engine)
        else:
            self.macro_engine = macro_engine or GlobalMacroEngine()
        self.cache_manager = getattr(self.macro_engine, 'cache_manager', None) or CacheManager()

    def run(self, symbol: str) -> Dict[str, Any]:
        macro_res = self.macro_engine.fetch_macro_indicators()
        indicators = macro_res.get("indicators", [])
        sentiment = compute_macro_sentiment(indicators)

        summary = sentiment["summary"]
        if macro_res.get("status") == "stale" and sentiment["available"]:
            summary += " (Some readings are from older cached data.)"

        return {
            "agent_name": "Global Macro Agent",
            "symbol": symbol,
            "raw_macro": indicators,
            "macro_sentiment": {
                "label": sentiment["label"],
                "score": sentiment["score"],
                "available": sentiment["available"],
                "data_status": macro_res.get("status", "unavailable"),
            },
            "analysis": f"Global Macro Backdrop for {symbol}: {summary}"
        }
