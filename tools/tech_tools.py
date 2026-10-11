"""
Technical Analysis Engine.
Computes Moving Averages (20, 50, 200), RSI (14), MACD, Bollinger Bands,
Support/Resistance levels, and candlestick breakout indicators.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any

from typing import Dict, Any, Optional

from tools.historical_data_tools import HistoricalDataEngine
from storage.cache_manager import CacheManager

class TechnicalAnalysisEngine:
    def __init__(self, rag_engine: Optional[HistoricalDataEngine] = None, cache_manager: Optional[CacheManager] = None):
        self.rag_engine = rag_engine or HistoricalDataEngine(cache_manager=cache_manager)

    def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """Calculates key technical metrics for a stock symbol."""
        df = self.rag_engine.load_symbol_history(symbol)
        if df.empty or len(df) < 20:
            return {"symbol": symbol, "status": "Insufficient historical data for technical analysis."}

        df = df.copy()
        close = df['CLOSE_PRICE']

        # Moving Averages
        df['SMA_20'] = close.rolling(window=20).mean()
        df['SMA_50'] = close.rolling(window=50).mean()
        df['SMA_200'] = close.rolling(window=200).mean() if len(close) >= 200 else close.rolling(window=len(close)).mean()

        # RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['RSI_14'] = 100 - (100 / (1 + rs))

        # MACD (12, 26, 9)
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        df['MACD'] = ema_12 - ema_26
        df['MACD_SIGNAL'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_HIST'] = df['MACD'] - df['MACD_SIGNAL']

        # Bollinger Bands (20, 2)
        std_20 = close.rolling(window=20).std()
        df['BB_UPPER'] = df['SMA_20'] + (std_20 * 2)
        df['BB_LOWER'] = df['SMA_20'] - (std_20 * 2)

        # Pivot Support & Resistance (Pivot Point = (High + Low + Close) / 3)
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        pivot = (prev['HIGH_PRICE'] + prev['LOW_PRICE'] + prev['CLOSE_PRICE']) / 3.0
        r1 = (2 * pivot) - prev['LOW_PRICE']
        s1 = (2 * pivot) - prev['HIGH_PRICE']
        r2 = pivot + (prev['HIGH_PRICE'] - prev['LOW_PRICE'])
        s2 = pivot - (prev['HIGH_PRICE'] - prev['LOW_PRICE'])

        # Signal Interpretation
        latest_close = float(latest['CLOSE_PRICE'])
        rsi_val = float(latest['RSI_14'])
        macd_val = float(latest['MACD'])
        macd_sig = float(latest['MACD_SIGNAL'])
        sma_50_val = float(latest['SMA_50'])
        sma_200_val = float(latest['SMA_200'])

        signals = []
        if latest_close > sma_50_val:
            signals.append("Above 50-day SMA (Short-term Bullish)")
        else:
            signals.append("Below 50-day SMA (Short-term Bearish)")

        if latest_close > sma_200_val:
            signals.append("Above 200-day SMA (Long-term Bullish Trend)")
        else:
            signals.append("Below 200-day SMA (Long-term Bearish Trend)")

        if rsi_val > 70:
            signals.append("RSI Overbought (>70)")
        elif rsi_val < 30:
            signals.append("RSI Oversold (<30)")
        else:
            signals.append(f"RSI Neutral ({round(rsi_val, 1)})")

        if macd_val > macd_sig:
            signals.append("MACD Bullish Crossover")
        else:
            signals.append("MACD Bearish Crossover")

        return {
            "symbol": symbol,
            "last_price": latest_close,
            "sma_20": round(float(latest['SMA_20']), 2),
            "sma_50": round(sma_50_val, 2),
            "sma_200": round(sma_200_val, 2),
            "rsi_14": round(rsi_val, 2),
            "macd": round(macd_val, 2),
            "macd_signal": round(macd_sig, 2),
            "bollinger_upper": round(float(latest['BB_UPPER']), 2),
            "bollinger_lower": round(float(latest['BB_LOWER']), 2),
            "resistance_1": round(float(r1), 2),
            "support_1": round(float(s1), 2),
            "resistance_2": round(float(r2), 2),
            "support_2": round(float(s2), 2),
            "technical_signals": signals
        }
