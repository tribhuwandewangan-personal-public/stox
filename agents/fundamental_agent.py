"""
Fundamental Analyst Agent.
Quantitative valuation metrics (P/E, P/B, ROE, Debt/Equity) combined with
upcoming corporate event catalysts (Earnings dates, Dividends, Corporate Actions).
"""

from typing import Dict, Any, Optional
from tools.fundamental_tools import FundamentalAnalysisEngine
from tools.events_tools import EventsEngine
from storage.cache_manager import CacheManager


class FundamentalAgent:
    def __init__(self, fund_engine: Optional[FundamentalAnalysisEngine] = None, events_engine: Optional[EventsEngine] = None, cache_manager: Optional[CacheManager] = None):
        self.fund_engine = fund_engine or FundamentalAnalysisEngine()
        self.events_engine = events_engine or EventsEngine(cache_manager=cache_manager)

    def run(self, symbol: str) -> Dict[str, Any]:
        fund_data = self.fund_engine.get_fundamental_metrics(symbol)
        events_data = self.events_engine.fetch_stock_events(symbol)
        
        pe = fund_data.get("pe_ratio", "N/A")
        roe = fund_data.get("roe_pct", "N/A")
        val = fund_data.get("valuation_assessment", "Fairly Valued")
        earnings_dt = events_data.get("earnings_date", "TBD")
        div_dt = events_data.get("dividend_ex_date", "N/A")
        div_amt = events_data.get("dividend_amount", "N/A")
        corp_action = events_data.get("corporate_action", "None")

        events_summary = f"Next Earnings: {earnings_dt} ({events_data.get('earnings_quarter', '')}) | Dividend: {div_amt} (Ex-Date: {div_dt}) | Catalyst: {corp_action}"
        analysis_text = f"P/E Ratio: {pe} | ROE: {roe}% | Valuation: {val} | Upcoming Events: {events_summary}"

        return {
            "agent_name": "Fundamental Analyst Agent",
            "symbol": symbol,
            "raw_fundamentals": fund_data,
            "upcoming_events": events_data,
            "analysis": analysis_text
        }
