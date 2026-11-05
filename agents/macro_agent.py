import time
from typing import Dict, Any, Union, Optional
from langchain_core.prompts import PromptTemplate

from config import get_llm, FAST_MODE
from tools.macro_tools import GlobalMacroEngine
from storage.cache_manager import CacheManager

class GlobalMacroAgent:
    _global_macro_summary: Optional[str] = None
    _global_macro_time: float = 0.0

    def __init__(self, macro_engine: Union[GlobalMacroEngine, CacheManager] = None):
        if isinstance(macro_engine, CacheManager):
            self.macro_engine = GlobalMacroEngine(cache_manager=macro_engine)
        else:
            self.macro_engine = macro_engine or GlobalMacroEngine()
        self.cache_manager = getattr(self.macro_engine, 'cache_manager', None) or CacheManager()
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.2, max_tokens=150, timeout=12)
        return self._llm

    def run(self, symbol: str) -> Dict[str, Any]:
        macro_res = self.macro_engine.fetch_macro_indicators()
        indicators = macro_res.get("indicators", [])

        # 1. Check in-memory batch cache (< 4 hours)
        now = time.time()
        if GlobalMacroAgent._global_macro_summary and (now - GlobalMacroAgent._global_macro_time) < 14400:
            analysis_text = f"Global Macro Backdrop for {symbol}: {GlobalMacroAgent._global_macro_summary}"
            return {
                "agent_name": "Global Macro Agent",
                "symbol": symbol,
                "raw_macro": indicators,
                "analysis": analysis_text
            }

        # 2. Check SQLite Market Bulletin from BackgroundMacroSentinel
        bulletin = self.cache_manager.get_latest_market_bulletin()
        if bulletin and bulletin.get("summary"):
            summary = bulletin.get("summary")
            GlobalMacroAgent._global_macro_summary = summary
            GlobalMacroAgent._global_macro_time = now
            analysis_text = f"Global Macro Backdrop for {symbol}: {summary}"
            return {
                "agent_name": "Global Macro Agent",
                "symbol": symbol,
                "raw_macro": indicators,
                "analysis": analysis_text
            }

        # 3. Fast deterministic heuristic summary if FAST_MODE or offline
        macro_text = "; ".join([f"{m['indicator']}: {m['summary']}" for m in indicators])
        if FAST_MODE:
            summary = f"Global macro signals remain balanced ({macro_text[:140]}). Neutral to favorable environment for domestic Indian equities."
            GlobalMacroAgent._global_macro_summary = summary
            GlobalMacroAgent._global_macro_time = now
            return {
                "agent_name": "Global Macro Agent",
                "symbol": symbol,
                "raw_macro": indicators,
                "analysis": f"Global Macro Backdrop for {symbol}: {summary}"
            }

        # 4. Generate once with LLM and cache for all other stocks in the batch
        prompt = PromptTemplate.from_template(
            """You are a Global Macro Strategist analyzing equity markets.
Evaluate the current global market environment for Indian stocks based on these indicators:
{macro_text}

Provide a concise 2-sentence market sentiment summary stating whether global macro is Favorable, Neutral, or Unfavorable for Indian equities.
"""
        )
        chain = prompt | self.llm
        try:
            response = chain.invoke({"macro_text": macro_text})
            summary = response.content if hasattr(response, 'content') else str(response)
        except Exception:
            summary = "Global market indicators (S&P 500, Crude Oil, DXY) present a balanced macroeconomic backdrop for Indian equities."

        GlobalMacroAgent._global_macro_summary = summary.strip()
        GlobalMacroAgent._global_macro_time = now
        analysis_text = f"Global Macro Backdrop for {symbol}: {summary.strip()}"

        return {
            "agent_name": "Global Macro Agent",
            "symbol": symbol,
            "raw_macro": indicators,
            "analysis": analysis_text
        }
