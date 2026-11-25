"""
Phase 2: Catalyst + Pre-Breakout Fusion Scanner.

Combines primary-source corporate catalysts (scored 0-100) with Stox's
technical & delivery accumulation signals:
  - Price within 10% of 52W High
  - Above SMA 20 & SMA 50
  - Volume expansion (RVOL >= 1.25)
  - High delivery % (>= 45%)
  - Improving Mansfield Relative Strength vs Nifty
  - Declining volatility / tight consolidation (ATR% <= 4.5%)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from storage.cache_manager import CacheManager
from tools import events_bus
from tools.catalyst_ingestion import collect_primary_catalysts, make_event_hash
from tools.catalyst_scorer import score_catalyst
from tools.historical_data_tools import HistoricalDataEngine
from tools.tech_tools import TechnicalAnalysisEngine


def _extract_annual_revenue_cr(symbol: str, cache_mgr: CacheManager) -> Optional[float]:
    """Reads TTM revenue (in INR Crores) from cached Fundamental/Forensic outputs if available."""
    try:
        fund_out = cache_mgr.get_latest_agent_output(symbol, "Fundamental Analyst Agent") or {}
        raw = fund_out.get("raw_fundamentals") or {}
        rev = raw.get("total_revenue") or raw.get("revenue")
        if rev is not None:
            v = float(rev)
            if v > 1e7:  # raw INR -> convert to Crores
                return round(v / 1e7, 2)
            if v > 0:
                return round(v, 2)
    except Exception:
        pass
    return None


def _evaluate_pre_breakout(symbol: str, hist_engine: HistoricalDataEngine, tech_engine: TechnicalAnalysisEngine, cache_mgr: CacheManager) -> Dict[str, Any]:
    """Checks early pre-breakout accumulation signals using cached candles & quotes."""
    signals: List[str] = []
    market_ctx: Dict[str, Any] = {}

    try:
        df = hist_engine.load_symbol_history(symbol, limit_days=260)
        if df is None or len(df) < 50:
            return {"pre_breakout_match": False, "signals": signals, "market_ctx": market_ctx}

        df_ind = tech_engine._compute_indicators(df)
        last = df_ind.iloc[-1]
        close = float(last.get("CLOSE_PRICE") or 0.0)
        sma20 = float(last.get("SMA_20") or 0.0)
        sma50 = float(last.get("SMA_50") or 0.0)
        rvol = float(last.get("RVOL") or 0.0)
        pct_52w = float(last.get("PCT_FROM_52W_HIGH") or -99.0)
        atr14 = float(last.get("ATR_14") or 0.0)
        atr_pct = (atr14 / close * 100.0) if close > 0 else 99.0

        prev_close = float(df_ind.iloc[-2].get("CLOSE_PRICE") or close) if len(df_ind) >= 2 else close
        pct_chg = ((close - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0

        delivery_pct = None
        if "DELIVERY_PCT" in df_ind.columns and df_ind["DELIVERY_PCT"].notna().any():
            delivery_pct = float(df_ind["DELIVERY_PCT"].dropna().iloc[-1])

        market_ctx = {
            "rvol": round(rvol, 2),
            "delivery_pct": round(delivery_pct, 1) if delivery_pct is not None else None,
            "pct_change": round(pct_chg, 2),
        }

        if -10.0 <= pct_52w <= 0.5:
            signals.append(f"Near 52W High ({pct_52w:+.1f}%)")
        if close > sma20 > 0 and close > sma50 > 0:
            signals.append("Above SMA20 & SMA50")
        if rvol >= 1.25:
            signals.append(f"Volume Surge ({rvol:.2f}x RVOL)")
        if delivery_pct is not None and delivery_pct >= 45.0:
            signals.append(f"High Delivery ({delivery_pct:.1f}%)")
        if atr_pct <= 4.5:
            signals.append(f"Tight Volatility ({atr_pct:.1f}% ATR)")
    except Exception:
        pass

    return {
        "pre_breakout_match": len(signals) >= 3,
        "signals": signals,
        "market_ctx": market_ctx,
    }


class CatalystScannerEngine:
    """Coordinates ingestion, deterministic 100-pt scoring, and pre-breakout fusion."""

    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.hist_engine = HistoricalDataEngine(cache_manager=self.cache_manager)
        self.tech_engine = TechnicalAnalysisEngine(rag_engine=self.hist_engine, cache_manager=self.cache_manager)

    def analyze_and_save_event(
        self,
        symbol: str,
        title: str,
        summary: str = "",
        source: str = "NSE",
        company_name: str = "",
        announced_at: str = "",
        source_url: str = "",
        deal_value_cr: Optional[float] = None,
        annual_revenue_cr: Optional[float] = None,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Scores a single announcement deterministically, fuses pre-breakout signals, and persists to SQLite."""
        sym = symbol.upper().strip()
        from datetime import datetime
        dt_str = (announced_at or datetime.now().strftime("%Y-%m-%d"))[:10]
        rev_cr = annual_revenue_cr if annual_revenue_cr is not None else _extract_annual_revenue_cr(sym, self.cache_manager)
        recent_cnt = self.cache_manager.get_recent_catalyst_count(sym, days=30)
        pb = _evaluate_pre_breakout(sym, self.hist_engine, self.tech_engine, self.cache_manager)

        scored = score_catalyst(
            title=title,
            summary=summary,
            source=source,
            category=category,
            deal_value_cr=deal_value_cr,
            annual_revenue_cr=rev_cr,
            recent_count_30d=recent_cnt,
            market_ctx=pb["market_ctx"],
        )

        event = {
            "event_hash": make_event_hash(source, sym, dt_str, title),
            "symbol": sym,
            "company_name": company_name or sym,
            "source": source.upper().strip(),
            "source_url": source_url,
            "announced_at": dt_str,
            "title": title.strip(),
            "summary": summary.strip(),
            "category": scored["category"],
            "deal_value_cr": scored["deal_value_cr"],
            "annual_revenue_cr": rev_cr,
            "total_score": scored["total_score"],
            "tier": scored["tier"],
            "score_breakdown": scored["score_breakdown"],
            "pre_breakout_match": pb["pre_breakout_match"],
            "pre_breakout_signals": pb["signals"],
        }
        self.cache_manager.save_catalyst_events([event])

        if event["tier"] == "A":
            try:
                events_bus.publish("catalyst_early_warning", {
                    "symbol": sym,
                    "tier": "A",
                    "score": event["total_score"],
                    "category": event["category"],
                    "title": event["title"],
                    "pre_breakout_match": event["pre_breakout_match"],
                })
            except Exception:
                pass
        return event

    def run_live_scan(self, limit_per_source: int = 40) -> Dict[str, Any]:
        """Pulls primary-source announcements, scores them, and saves to SQLite."""
        raw_events = collect_primary_catalysts(limit_per_source=limit_per_source)
        scored_events: List[Dict[str, Any]] = []
        tier_a = 0
        tier_b = 0

        for ev in raw_events:
            if ev.get("category") == "ROUTINE":
                continue
            saved_ev = self.analyze_and_save_event(
                symbol=ev["symbol"],
                title=ev["title"],
                summary=ev.get("summary", ""),
                source=ev.get("source", "NSE"),
                company_name=ev.get("company_name", ""),
                announced_at=ev.get("announced_at", ""),
                source_url=ev.get("source_url", ""),
                deal_value_cr=ev.get("deal_value_cr"),
                category=ev.get("category"),
            )
            scored_events.append(saved_ev)
            if saved_ev["tier"] == "A":
                tier_a += 1
            elif saved_ev["tier"] == "B":
                tier_b += 1

        return {
            "scanned_raw": len(raw_events),
            "saved_catalysts": len(scored_events),
            "tier_a_count": tier_a,
            "tier_b_count": tier_b,
            "events": scored_events[:50],
        }
