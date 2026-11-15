"""
Risk & Volatility Management Engine.
Calculates Beta, Maximum Drawdown, Value at Risk (VaR 95%),
optimal stop-loss placement, and target risk-reward ratios for stock symbols.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from tools.historical_data_tools import HistoricalDataEngine
from storage.cache_manager import CacheManager

class RiskManagementEngine:
    def __init__(self, rag_engine: Optional[HistoricalDataEngine] = None, cache_manager: Optional[CacheManager] = None):
        self.rag_engine = rag_engine or HistoricalDataEngine(cache_manager=cache_manager)

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

        # True Structural Risk Management (Average True Range & Swing Pivots)
        last_price = float(close.iloc[-1])
        high = df['HIGH_PRICE']
        low = df['LOW_PRICE']
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        atr_14 = float(tr.tail(14).mean()) if len(tr) >= 14 else float(last_price * 0.025)

        # 15-day Structural Swing Support (Low)
        recent_lows = low.tail(15)
        swing_low = float(recent_lows.min()) if not recent_lows.empty else last_price * 0.95

        # Structural Stop Loss: Below swing low with buffer, or 1.8x ATR below price
        raw_sl = min(swing_low * 0.995, last_price - (1.8 * atr_14))
        risk_dist = last_price - raw_sl
        risk_pct = risk_dist / last_price

        # Enforce healthy noise buffer: minimum 3.8% risk to prevent intraday noise shakeout, max 7.5%
        if risk_pct < 0.038:
            suggested_stop_loss = round(last_price * 0.962, 2)
        elif risk_pct > 0.075:
            suggested_stop_loss = round(last_price * 0.925, 2)
        else:
            suggested_stop_loss = round(raw_sl, 2)

        risk_amount = max(0.01, last_price - suggested_stop_loss)

        # Structural Target: Enforce minimum 1:2.0 Risk-to-Reward Ratio for profitable swing trading
        suggested_target_1 = round(last_price + max(2.0 * risk_amount, 2.5 * atr_14), 2)
        risk_reward_ratio = round((suggested_target_1 - last_price) / risk_amount, 2)

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
