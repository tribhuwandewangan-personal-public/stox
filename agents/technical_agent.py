"""
Technical Analysis Agent.
Fast quantitative computation of moving averages (20, 50, 200), RSI, MACD crossovers,
Bollinger Bands, and support/resistance levels.
"""

from typing import Dict, Any
from tools.tech_tools import TechnicalAnalysisEngine

class TechnicalAnalysisAgent:
    def __init__(self, tech_engine: TechnicalAnalysisEngine = None):
        self.tech_engine = tech_engine or TechnicalAnalysisEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        tech_data = self.tech_engine.analyze_symbol(symbol)
        
        rsi = tech_data.get("rsi_14", 50)
        sma50 = tech_data.get("sma_50", 0)
        last_price = tech_data.get("last_price", 0)
        signals = ", ".join(tech_data.get("technical_signals", []))
        
        analysis_text = f"Last Price: Rs.{last_price} | RSI(14): {rsi} | SMA50: Rs.{sma50} | Signals: {signals}"

        return {
            "agent_name": "Technical Analysis Agent",
            "symbol": symbol,
            "raw_indicators": tech_data,
            "analysis": analysis_text
        }
