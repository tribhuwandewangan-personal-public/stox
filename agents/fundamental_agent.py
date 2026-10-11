"""
Fundamental Analyst Agent.
Fast quantitative analysis of valuation metrics (P/E, P/B, ROE, Debt/Equity).
"""

from typing import Dict, Any
from tools.fundamental_tools import FundamentalAnalysisEngine

class FundamentalAgent:
    def __init__(self, fund_engine: FundamentalAnalysisEngine = None):
        self.fund_engine = fund_engine or FundamentalAnalysisEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        fund_data = self.fund_engine.get_fundamental_metrics(symbol)
        
        pe = fund_data.get("pe_ratio", "N/A")
        roe = fund_data.get("roe_pct", "N/A")
        val = fund_data.get("valuation_assessment", "Fairly Valued")
        analysis_text = f"P/E Ratio: {pe} | ROE: {roe}% | Valuation Profile: {val}"

        return {
            "agent_name": "Fundamental Analyst Agent",
            "symbol": symbol,
            "raw_fundamentals": fund_data,
            "analysis": analysis_text
        }
