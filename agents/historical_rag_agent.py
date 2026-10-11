"""
Historical Data RAG Agent.
Fast quantitative extraction of corporate-action adjusted price action history,
volume surges, 52-week High/Low, and momentum trends.
"""

from typing import Dict, Any, Optional
from tools.historical_data_tools import HistoricalDataEngine


class HistoricalRAGAgent:
    def __init__(self, rag_engine: Optional[HistoricalDataEngine] = None):
        self.rag_engine = rag_engine or HistoricalDataEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        stats = self.rag_engine.get_historical_summary(symbol)
        
        last_close = stats.get("last_close", 0)
        p30d = stats.get("pct_change_30d", 0)
        p1y = stats.get("pct_change_1y", 0)
        surge = stats.get("volume_surge_ratio", 1.0)

        trend_label = "Strong Uptrend / Accumulation" if p30d > 5 and surge > 1.2 else "Uptrend" if p30d > 0 else "Downtrend" if p30d < 0 else "Consolidation"
        analysis_text = f"30-Day Return: {p30d}% | 1Y Return: {p1y}% | 52W Range: Rs.{stats.get('52w_low')} - Rs.{stats.get('52w_high')} | Vol Surge: {surge}x ({trend_label})"

        return {
            "agent_name": "Historical Data RAG Agent",
            "symbol": symbol,
            "raw_stats": stats,
            "analysis": analysis_text
        }
