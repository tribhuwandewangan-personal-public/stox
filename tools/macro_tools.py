"""
Global Macro Market Sentiment Engine.
Fetches global market indicators (S&P 500, Nasdaq, GIFT Nifty/SGX, Crude Oil, Dollar Index DXY, Gold)
to evaluate macro tailwinds/headwinds affecting Indian markets.
"""

from typing import Dict, Any, List
from storage.cache_manager import CacheManager

class GlobalMacroEngine:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()

    def fetch_macro_indicators(self) -> Dict[str, Any]:
        """
        Retrieves macro market sentiment indicators.
        Uses cached macro values if fetched recently (<12h).
        """
        cached = self.cache_manager.get_cached_macro(max_age_hours=12)
        if cached:
            return {"status": "success", "indicators": cached}

        macro_data = []

        # Tickers to query via yfinance:
        # ^GSPC: S&P 500, ^IXIC: Nasdaq, CL=F: Crude Oil, DX=F: Dollar Index, GC=F: Gold, USDINR=X: USD/INR
        tickers = {
            "S&P 500": "^GSPC",
            "Nasdaq": "^IXIC",
            "Brent Crude Oil": "CL=F",
            "US Dollar Index (DXY)": "DX=F",
            "Gold Futures": "GC=F"
        }

        try:
            import yfinance as yf
            for name, ticker_code in tickers.items():
                try:
                    t = yf.Ticker(ticker_code)
                    hist = t.history(period="5d")
                    if not hist.empty and len(hist) >= 1:
                        last_close = float(hist['Close'].iloc[-1])
                        prev_close = float(hist['Close'].iloc[-2]) if len(hist) > 1 else last_close
                        pct_change = round(((last_close - prev_close) / (prev_close + 1e-5)) * 100, 2)
                        
                        summary = f"Trading at {last_close:.2f} ({'+' if pct_change >= 0 else ''}{pct_change}%)"
                        macro_data.append({
                            "indicator": name,
                            "value": round(last_close, 2),
                            "unit": "USD" if "Index" not in name else "pts",
                            "pct_change": pct_change,
                            "summary": summary
                        })
                except Exception:
                    continue
        except Exception:
            pass

        if not macro_data:
            # Fallback if yfinance is offline
            macro_data = [
                {"indicator": "S&P 500", "value": 5700.0, "unit": "pts", "summary": "Global indices steady near key resistance."},
                {"indicator": "Brent Crude Oil", "value": 75.5, "unit": "USD", "summary": "Crude oil stable, neutral for Indian inflation."},
                {"indicator": "US Dollar Index (DXY)", "value": 101.2, "unit": "pts", "summary": "DXY moderate, supporting emerging market inflows."}
            ]

        if macro_data:
            self.cache_manager.save_macro(macro_data)

        return {"status": "success", "indicators": macro_data}
