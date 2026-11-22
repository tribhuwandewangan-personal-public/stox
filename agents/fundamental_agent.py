"""
Fundamental Analyst Agent.
Quantitative valuation metrics (P/E, P/B, ROE, Debt/Equity) combined with
upcoming corporate event catalysts (Earnings dates, Dividends, Corporate Actions).
"""

import re
from typing import Dict, Any, Optional, List
from tools.fundamental_tools import FundamentalAnalysisEngine
from tools.events_tools import EventsEngine
from tools.forensic_financial_engine import ForensicFinancialEngine
from storage.cache_manager import CacheManager


def _detect_order_book_catalyst(events_data: dict, news_items: List[Dict[str, Any]]) -> Optional[str]:
    """Detects corporate order book, contract wins, or order pipeline catalysts from events and news."""
    # 1. Check corporate action description in upcoming events
    corp = str(events_data.get("corporate_action") or "")
    if any(k in corp.lower() for k in ("orderbook", "order book", "order backlog", "contract", "pipeline")):
        return corp

    # 2. Scan recent news headlines for order wins or backlog milestones
    order_patterns = [
        re.compile(r"\b(?:order|contract|deal|bid|mandate|project)s?\s+(?:win|won|bag|bagged|worth|valued at|of)\b", re.I),
        re.compile(r"\b(?:order\s*book|order\s*backlog|order\s*pipeline)\b", re.I),
        re.compile(r"\b(?:secures|bags|awarded|wins)\s+(?:new\s+)?(?:order|contract|deal)\b", re.I)
    ]
    for item in (news_items or []):
        title = item.get("title", "")
        for pat in order_patterns:
            if pat.search(title):
                return title[:120]
    return None


class FundamentalAgent:
    def __init__(self, fund_engine: Optional[FundamentalAnalysisEngine] = None, events_engine: Optional[EventsEngine] = None, forensic_engine: Optional[ForensicFinancialEngine] = None, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.fund_engine = fund_engine or FundamentalAnalysisEngine(cache_manager=self.cache_manager)
        self.events_engine = events_engine or EventsEngine(cache_manager=self.cache_manager)
        self.forensic_engine = forensic_engine or ForensicFinancialEngine(cache_manager=self.cache_manager)

    def run(self, symbol: str) -> Dict[str, Any]:
        fund_data = self.fund_engine.get_fundamental_metrics(symbol)
        events_data = self.events_engine.fetch_stock_events(symbol)
        
        # Detect order book / contract pipeline from news or corporate events
        news_items = self.cache_manager.get_cached_news(symbol, max_age_hours=72) if self.cache_manager else []
        order_catalyst = _detect_order_book_catalyst(events_data, news_items)
        if order_catalyst:
            fund_data["order_book_catalyst"] = order_catalyst

        pe = fund_data.get("pe_ratio", "N/A")
        peg = fund_data.get("peg_ratio", "N/A")
        roe = fund_data.get("roe_pct", "N/A")
        de = fund_data.get("debt_to_equity", "N/A")
        cr = fund_data.get("current_ratio", "N/A")
        net_cash = fund_data.get("net_cash_status", "N/A")
        val = fund_data.get("valuation_assessment", "Unavailable")
        earnings_dt = events_data.get("earnings_date") or "TBD"
        div_dt = events_data.get("dividend_ex_date") or "N/A"
        div_amt = events_data.get("dividend_amount") or "N/A"
        corp_action = events_data.get("corporate_action") or "None"
        quarter = events_data.get("earnings_quarter")

        earnings_part = f"Next Earnings: {earnings_dt}" + (f" ({quarter})" if quarter else "")
        events_summary = f"{earnings_part} | Dividend: {div_amt} (Ex-Date: {div_dt}) | Catalyst: {corp_action}"
        # Forensic due diligence & earnings quality audit
        try:
            forensic_res = self.forensic_engine.analyze_company(symbol)
        except Exception as e:
            forensic_res = {"verdict": "UNAUDITED", "red_flags": [], "verdict_badge": "⚪ UNAUDITED", "error": str(e)}

        forensic_flags = forensic_res.get("red_flags", [])
        peer_benchmarks = forensic_res.get("peer_benchmarks", {})
        f_score_val = forensic_res.get("piotroski_f_score")
        if isinstance(f_score_val, dict):
            f_score_val = f_score_val.get("score")
        debtor_days = forensic_res.get("debtor_days")
        forensic_summary = f" | Forensic Due-Diligence: {forensic_res.get('verdict_badge', 'N/A')}"
        if f_score_val is not None:
            forensic_summary += f" [Piotroski F-Score: {f_score_val}/9]"
        if debtor_days is not None:
            forensic_summary += f" [Debtor Days: {debtor_days}d]"
        if forensic_flags:
            forensic_summary += f" [⚠️ Red Flags: {'; '.join(forensic_flags[:2])}]"
        if peer_benchmarks.get("peer_verdict"):
            forensic_summary += f" [📊 Peers: {peer_benchmarks.get('peer_verdict')}]"

        if fund_data.get("available", True):
            roe_txt = f"{roe}%" if roe != "N/A" else "N/A"
            peg_part = f" | PEG: {peg}" if peg != "N/A" else ""

            bs_parts = []
            if de != "N/A":
                bs_parts.append(f"D/E: {de}")
            if cr != "N/A":
                bs_parts.append(f"Current Ratio: {cr}")
            if net_cash != "N/A":
                bs_parts.append(f"{net_cash}")
            bs_text = f" | Balance Sheet: {', '.join(bs_parts)}" if bs_parts else ""
            order_text = f" | Order Pipeline: {order_catalyst}" if order_catalyst else ""

            analysis_text = f"P/E Ratio: {pe}{peg_part} | ROE: {roe_txt} | Valuation: {val}{bs_text}{order_text}{forensic_summary} | Upcoming Events: {events_summary}"
        else:
            analysis_text = f"Fundamentals unavailable from market feed{forensic_summary} | Upcoming Events: {events_summary}"

        return {
            "agent_name": "Fundamental Analyst Agent",
            "symbol": symbol,
            "raw_fundamentals": fund_data,
            "upcoming_events": events_data,
            "forensic_analysis": forensic_res,
            "forensic_verdict": forensic_res.get("verdict"),
            "forensic_badge": forensic_res.get("verdict_badge"),
            "forensic_red_flags": forensic_res.get("red_flags", []),
            "peer_benchmarks": peer_benchmarks,
            "analysis": analysis_text
        }
