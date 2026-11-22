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
            "sector": "",
            "available": False,
            "pe_ratio": "N/A",
            "peg_ratio": "N/A",
            "earnings_growth_pct": "N/A",
            "pb_ratio": "N/A",
            "roe_pct": "N/A",
            "debt_to_equity": "N/A",
            "total_debt": "N/A",
            "total_cash": "N/A",
            "net_debt": "N/A",
            "net_cash_status": "N/A",
            "current_ratio": "N/A",
            "quick_ratio": "N/A",
            "free_cashflow": "N/A",
            "revenue_growth_pct": "N/A",
            "profit_margin_pct": "N/A",
            "book_value": "N/A",
            "eps": "N/A",
            "ev_to_ebitda": "N/A",
            "enterprise_value": "N/A",
            "ebitda": "N/A",
            "roa_pct": "N/A",
            "shares_outstanding": "N/A",
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
                raw_peg = info.get("pegRatio") or info.get("trailingPegRatio")
                peg_val = _num(raw_peg)
                eg_val = _num(info.get("earningsGrowth"), 100)
                rg_val = _num(info.get("revenueGrowth"), 100)

                # Ensure negative PEG from data feed is flagged rather than misconstrued as a bargain multiple
                if isinstance(peg_val, (int, float)) and peg_val <= 0:
                    peg_val = "N/A (Negative Growth)"

                # Fallback: calculate PEG from P/E and earningsGrowth if pegRatio is not provided directly
                if (peg_val == "N/A" or not isinstance(peg_val, (int, float))) and isinstance(pe_val, (int, float)) and pe_val > 0:
                    if isinstance(eg_val, (int, float)):
                        if eg_val > 2.0:
                            # Normalize extreme base-effect surge (e.g. >100%) so PEG does not artificially collapse to 0.00
                            denom_g = min(eg_val, 100.0)
                            peg_val = round(pe_val / denom_g, 2)
                        elif eg_val <= 0:
                            # Earnings contraction: never mask declining profit with a revenue-growth PEG proxy
                            peg_val = "N/A (Negative Growth)"
                    elif isinstance(rg_val, (int, float)) and rg_val > 5.0:
                        # Earnings growth unavailable; use top-line revenue expansion proxy
                        peg_val = round(pe_val / min(rg_val, 100.0), 2)

                # Balance Sheet & Solvency metrics (freely available via market feed)
                total_debt = _num(info.get("totalDebt"))
                total_cash = _num(info.get("totalCash"))
                current_ratio = _num(info.get("currentRatio"))
                quick_ratio = _num(info.get("quickRatio"))
                free_cashflow = _num(info.get("freeCashflow"))
                de_ratio = _num(info.get("debtToEquity"))

                net_debt = "N/A"
                net_cash_status = "N/A"
                if isinstance(total_debt, (int, float)) and isinstance(total_cash, (int, float)):
                    net_debt = round(total_debt - total_cash, 2)
                    if net_debt <= 0:
                        net_cash_status = "Net Cash Positive (Debt-Free)"
                    else:
                        net_cash_status = f"Net Debt: Rs. {net_debt:,.0f}"
                elif isinstance(de_ratio, (int, float)):
                    if de_ratio < 15:
                        net_cash_status = "Virtually Debt-Free"
                    elif de_ratio > 150:
                        net_cash_status = "High Leverage"
                    else:
                        net_cash_status = "Moderate Leverage"

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
                    "sector": info.get("sector") or info.get("industry") or "",
                    "available": True,
                    "pe_ratio": pe_val,
                    "peg_ratio": peg_val,
                    "earnings_growth_pct": eg_val,
                    "pb_ratio": _num(info.get("priceToBook")),
                    "roe_pct": _num(info.get("returnOnEquity"), 100),
                    "roa_pct": _num(info.get("returnOnAssets"), 100),
                    "book_value": _num(info.get("bookValue")),
                    "eps": _num(info.get("trailingEps") or info.get("forwardEps")),
                    "ev_to_ebitda": _num(info.get("enterpriseToEbitda")),
                    "enterprise_value": _num(info.get("enterpriseValue")),
                    "ebitda": _num(info.get("ebitda")),
                    "shares_outstanding": _num(info.get("sharesOutstanding")),
                    "debt_to_equity": de_ratio,
                    "total_debt": total_debt,
                    "total_cash": total_cash,
                    "net_debt": net_debt,
                    "net_cash_status": net_cash_status,
                    "current_ratio": current_ratio,
                    "quick_ratio": quick_ratio,
                    "free_cashflow": free_cashflow,
                    "revenue_growth_pct": _num(info.get("revenueGrowth"), 100),
                    "profit_margin_pct": _num(info.get("profitMargins"), 100),
                    "valuation_assessment": val_status,
                    "market_cap": market_cap if market_cap else "N/A"
                }
            except Exception:
                continue
        return None
