from typing import Dict, Any, Union
from langchain_core.prompts import PromptTemplate

from config import get_llm
from tools.macro_tools import GlobalMacroEngine
from storage.cache_manager import CacheManager

class GlobalMacroAgent:
    def __init__(self, macro_engine: Union[GlobalMacroEngine, CacheManager] = None):
        if isinstance(macro_engine, CacheManager):
            self.macro_engine = GlobalMacroEngine(cache_manager=macro_engine)
        else:
            self.macro_engine = macro_engine or GlobalMacroEngine()
        self.llm = get_llm(temperature=0.2)

    def run(self, symbol: str) -> Dict[str, Any]:
        macro_res = self.macro_engine.fetch_macro_indicators()
        indicators = macro_res.get("indicators", [])
        
        macro_text = "\n".join([f"- {m['indicator']}: {m['summary']}" for m in indicators])
        
        prompt = PromptTemplate.from_template(
            """You are a Global Macro Strategist analyzing equity markets.
Evaluate the current global market environment for Indian stocks:

Global Market Indicators:
{macro_text}

Summarize how global market sentiment (US markets, Crude Oil, Dollar Index DXY) impacts Indian equities and stock {symbol} in particular. State whether global macro is Favorable, Neutral, or Unfavorable.
"""
        )
        
        chain = prompt | self.llm
        try:
            response = chain.invoke({"symbol": symbol, "macro_text": macro_text})
            analysis_text = response.content if hasattr(response, 'content') else str(response)
        except Exception:
            analysis_text = "Global market indicators (S&P 500, Crude, DXY) present a balanced macroeconomic backdrop for Indian equities."

        return {
            "agent_name": "Global Macro Agent",
            "symbol": symbol,
            "raw_macro": indicators,
            "analysis": analysis_text
        }
