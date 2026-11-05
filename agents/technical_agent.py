"""
Technical Analysis Agent.
Fast quantitative computation of moving averages (20, 50, 200), RSI, MACD crossovers,
Bollinger Bands, and advanced chart patterns:
- Head and Shoulders (and Inverse Head & Shoulders)
- Bollinger Band Squeeze, Band Walk, and Mean Reversion
- Saucer Pattern (Rounding Bottom / Accumulation Bowl)
- Double Bottom (W) / Double Top (M) formations.
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
        sma200 = tech_data.get("sma_200", 0)
        last_price = tech_data.get("last_price", 0)
        bb_upper = tech_data.get("bollinger_upper", 0)
        bb_lower = tech_data.get("bollinger_lower", 0)
        pct_b = tech_data.get("bollinger_pct_b", 0.5)
        signals = ", ".join(tech_data.get("technical_signals", []))
        patterns = tech_data.get("detected_patterns", [])

        if patterns:
            p_summary = "; ".join([f"{p['name']} [Score: {p.get('quality_score', 'N/A')}/100, Status: {p.get('status', 'Active')}, Target: Rs.{p.get('target_price', 'N/A')}]: {p['description']}" for p in patterns])
            patterns_line = f"Detected Chart Patterns: {p_summary}"
        else:
            patterns_line = "Detected Chart Patterns: No major reversal/continuation patterns confirmed (Consolidation)."

        analysis_text = (
            f"Last Price: Rs.{last_price} | RSI(14): {rsi} | SMA50: Rs.{sma50} | SMA200: Rs.{sma200} | "
            f"Bollinger Bands: [{bb_lower} - {bb_upper}] (%B: {pct_b}) | "
            f"{patterns_line} | "
            f"Key Technical Signals: {signals}"
        )

        return {
            "agent_name": "Technical Analysis Agent",
            "symbol": symbol,
            "raw_indicators": tech_data,
            "detected_patterns": patterns,
            "analysis": analysis_text
        }
