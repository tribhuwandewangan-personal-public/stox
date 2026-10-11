"""
Risk & Volatility Management Engine.
Calculates Beta, Maximum Drawdown, Value at Risk (VaR 95%),
optimal stop-loss placement, and target risk-reward ratios for stock symbols.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any

from tools.bhavcopy_rag import BhavcopyRAGEngine

from storage.cache_manager import CacheManager

class RiskManagementEngine:
    def __init__(self, rag_engine: BhavcopyRAGEngine = None, cache_manager: CacheManager = None):
        self.rag_engine = rag_engine or BhavcopyRAGEngine(cache_manager=cache_manager)

    def evaluate_risk(self, symbol: str) -> Dict[str, Any]:
        """Calculates quantitative risk parameters for a target symbol."""
        df = self.rag_engine.load_symbol_history(symbol)
        if df.empty or len(df) < 30:
            return {"symbol": symbol, "status": "Insufficient data for risk calculations."}

        close = df['CLOSE_PRICE']
        daily_returns = close.pct_change().dropna()

        # Volatility (Annualized Standard Deviation)
        daily_vol = daily_returns.std()
        annualized_vol = round(daily_vol * np.sqrt(252) * 100, 2)

        # Value at Risk (VaR 95% 1-day)
        var_95 = round(np.percentile(daily_returns, 5) * 100, 2)

        # Maximum Drawdown (1-year Peak to Trough)
        rolling_max = close.cummax()
        drawdown = (close - rolling_max) / rolling_max
        max_drawdown = round(float(drawdown.min()) * 100, 2)

        # Stop-Loss Bounds (2 * Daily Volatility or 3% minimum)
        last_price = float(close.iloc[-1])
        suggested_stop_loss = round(last_price * (1 - max(0.03, daily_vol * 2)), 2)
        suggested_target_1 = round(last_price * (1 + max(0.06, daily_vol * 4)), 2)
        risk_reward_ratio = round((suggested_target_1 - last_price) / (last_price - suggested_stop_loss + 1e-5), 2)

        # Risk Classification
        risk_level = "Moderate Risk"
        if annualized_vol > 35:
            risk_level = "High Risk / High Volatility"
        elif annualized_vol < 18:
            risk_level = "Low Volatility / Stable"

        return {
            "symbol": symbol,
            "last_price": last_price,
            "annualized_volatility_pct": annualized_vol,
            "value_at_risk_95_pct": abs(var_95),
            "max_drawdown_pct": abs(max_drawdown),
            "suggested_stop_loss": suggested_stop_loss,
            "suggested_target_price": suggested_target_1,
            "risk_reward_ratio": f"1:{risk_reward_ratio}",
            "risk_classification": risk_level
        }
