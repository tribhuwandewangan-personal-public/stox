"""
Global & Domestic Macro Agent.
Deterministic: converts live global & Indian macro indicators (S&P 500, Nasdaq, Brent, Brent-in-INR,
DXY, USD/INR, US 10Y, India VIX, Nifty 50/Midcap 150, plus local market breadth) into a
Bullish / Neutral / Bearish macro backdrop using explicit rules (tools/macro_tools.py).
"""

from typing import Dict, Any, Union

from tools.macro_tools import (
    GlobalMacroEngine,
    compute_macro_sentiment,
    compute_market_breadth,
    derive_brent_in_inr,
)
from storage.cache_manager import CacheManager


class GlobalMacroAgent:
    def __init__(self, macro_engine: Union[GlobalMacroEngine, CacheManager] = None):
        if isinstance(macro_engine, CacheManager):
            self.macro_engine = GlobalMacroEngine(cache_manager=macro_engine)
        else:
            self.macro_engine = macro_engine or GlobalMacroEngine()
        self.cache_manager = getattr(self.macro_engine, "cache_manager", None) or CacheManager()

    def run(self, symbol: str) -> Dict[str, Any]:
        macro_res = self.macro_engine.fetch_macro_indicators()
        indicators = list(macro_res.get("indicators", []))

        brent_inr = derive_brent_in_inr(indicators)
        if brent_inr and not any(i.get("indicator") == "Brent Crude (INR)" for i in indicators):
            indicators.append(brent_inr)

        breadth = compute_market_breadth(self.cache_manager)
        if breadth and not any(i.get("indicator") == "Market Breadth (% > 50 DMA)" for i in indicators):
            indicators.append({
                "indicator": "Market Breadth (% > 50 DMA)",
                "value": breadth["pct_above_50dma"],
                "unit": "%",
                "category": "Domestic Breadth",
                "pct_change": None,
                "summary": f"{breadth['pct_above_50dma']:.1f}% of stocks > 50 DMA ({breadth['breadth_regime']})",
            })
            if breadth.get("pct_above_200dma") is not None:
                indicators.append({
                    "indicator": "Market Breadth (% > 200 DMA)",
                    "value": breadth["pct_above_200dma"],
                    "unit": "%",
                    "category": "Domestic Breadth",
                    "pct_change": None,
                    "summary": f"{breadth['pct_above_200dma']:.1f}% of stocks > 200 DMA",
                })

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
                "brent_inr": sentiment.get("brent_inr"),
                "breadth": breadth,
                "thresholds": sentiment.get("thresholds"),
                "indicators": indicators,
            },
            "analysis": f"Global Macro Backdrop for {symbol}: {summary}",
        }
