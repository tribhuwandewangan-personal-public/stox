from datetime import datetime
from typing import Dict, Any, Optional

from storage.cache_manager import CacheManager
from tools.yf_quiet import silence_yfinance_logging

silence_yfinance_logging()

# yfinance .info is slow and flaky: cache good results for a day, failures only briefly.
FUNDAMENTALS_TTL_SECONDS = 24 * 3600
FUNDAMENTALS_FAILURE_TTL_SECONDS = 1 * 3600


def _num(value, scale: float = 1.0):
    """Round a numeric yfinance field, or 'N/A' when missing/non-numeric."""
    if value is None or isinstance(value, bool):
        return "N/A"
    try:
        return round(float(value) * scale, 2)
    except (TypeError, ValueError):
        return "N/A"


class FundamentalAnalysisEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager

    @staticmethod
    def _unavailable(symbol: str) -> Dict[str, Any]:
        return {
            "symbol": symbol,
            "available": False,
            "pe_ratio": "N/A",
            "peg_ratio": "N/A",
            "earnings_growth_pct": "N/A",
            "pb_ratio": "N/A",
            "roe_pct": "N/A",
            "debt_to_equity": "N/A",
            "revenue_growth_pct": "N/A",
            "profit_margin_pct": "N/A",
            "valuation_assessment": "Unavailable",
            "market_cap": "N/A",
            "status": "Fundamental data unavailable from market feed",
        }

    def get_fundamental_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Retrieves fundamental financial ratios for the given NSE symbol (cached).
        Tries .NS and .BO suffixes with silent error redirection. When nothing can be fetched the result is
        explicitly marked available=False -- no placeholder or "baseline" numbers are invented.
        """
        symbol_clean = symbol.upper().strip()

        if self.cache_manager:
            hit = self.cache_manager.get_cached_fundamentals(symbol_clean)
            if hit:
                age = (datetime.now() - hit["fetched_at"]).total_seconds()
                ttl = FUNDAMENTALS_TTL_SECONDS if hit["data"].get("available") else FUNDAMENTALS_FAILURE_TTL_SECONDS
                if age < ttl:
                    return hit["data"]

        data = self._fetch_live(symbol_clean) or self._unavailable(symbol_clean)

        if self.cache_manager:
            try:
                self.cache_manager.save_fundamentals(symbol_clean, data)
            except Exception:
                pass
        return data

    def _fetch_live(self, symbol_clean: str) -> Optional[Dict[str, Any]]:
        alias_map = {
            "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS", "TATAMOTORS.BO"],
            "NSE": ["NSE.BO", "NSE.NS"]
        }
        candidates = alias_map.get(symbol_clean, [f"{symbol_clean}.NS", f"{symbol_clean}.BO"])

        try:
            import yfinance as yf
        except Exception:
            return None

        for sym in candidates:
            try:
                info = yf.Ticker(sym).info or {}

                pe_ratio = info.get("trailingPE") or info.get("forwardPE")
                market_cap = info.get("marketCap")
                if not (pe_ratio or market_cap):
                    continue

                pe_val = _num(pe_ratio)
                peg_val = _num(info.get("pegRatio"))
                eg_val = _num(info.get("earningsGrowth"), 100)

                # Fallback: calculate PEG from P/E and earningsGrowth if pegRatio is not provided directly
                if peg_val == "N/A" and isinstance(pe_val, (int, float)) and pe_val > 0:
                    if isinstance(eg_val, (int, float)) and eg_val > 2.0:
                        peg_val = round(pe_val / eg_val, 2)

                val_status = "Fairly Valued"
                if pe_val == "N/A" or pe_val <= 0:
                    # Negative / missing earnings: a P/E-based valuation label would be meaningless
                    val_status = "Not Assessable (no positive earnings multiple)"
                elif pe_val < 18:
                    val_status = "Undervalued / Value Opportunity"
                elif pe_val > 45:
                    val_status = "High Growth / Premium Valuation"

                return {
                    "symbol": symbol_clean,
                    "available": True,
                    "pe_ratio": pe_val,
                    "peg_ratio": peg_val,
                    "earnings_growth_pct": eg_val,
                    "pb_ratio": _num(info.get("priceToBook")),
                    "roe_pct": _num(info.get("returnOnEquity"), 100),
                    "debt_to_equity": _num(info.get("debtToEquity")),
                    "revenue_growth_pct": _num(info.get("revenueGrowth"), 100),
                    "profit_margin_pct": _num(info.get("profitMargins"), 100),
                    "valuation_assessment": val_status,
                    "market_cap": market_cap if market_cap else "N/A"
                }
            except Exception:
                continue
        return None
