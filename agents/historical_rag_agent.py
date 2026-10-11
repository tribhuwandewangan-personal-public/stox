"""
Historical Data RAG Agent.
Fast quantitative extraction of price action history, volume surges,
52-week High/Low, and delivery percentage trends.
"""

from typing import Dict, Any
from tools.bhavcopy_rag import BhavcopyRAGEngine

class HistoricalRAGAgent:
    def __init__(self, rag_engine: BhavcopyRAGEngine = None):
        self.rag_engine = rag_engine or BhavcopyRAGEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        stats = self.rag_engine.get_historical_summary(symbol)
        
        last_close = stats.get("last_close", 0)
        p30d = stats.get("pct_change_30d", 0)
        deliv = stats.get("latest_deliv_per", 0)
        surge = stats.get("volume_surge_ratio", 1.0)

        trend_label = "Uptrend / Accumulation" if p30d > 0 and deliv > 40 else "Downtrend / Distribution" if p30d < 0 else "Consolidation"
        analysis_text = f"30-Day Return: {p30d}% | 52W Range: Rs.{stats.get('52w_low')} - Rs.{stats.get('52w_high')} | Delivery: {deliv}% | Vol Surge: {surge}x ({trend_label})"

        return {
            "agent_name": "Historical Data RAG Agent",
            "symbol": symbol,
            "raw_stats": stats,
            "analysis": analysis_text
        }
