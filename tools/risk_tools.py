"""
Risk & Volatility Management Engine.
Calculates Beta, Maximum Drawdown, Value at Risk (VaR 95%),
optimal stop-loss placement, and target risk-reward ratios for stock symbols.
"""

import os
import json
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional

from tools.historical_data_tools import HistoricalDataEngine
from tools.indicators import wilder_atr, snap_nse_tick
from storage.cache_manager import CacheManager

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check_circuit_and_surveillance(
    df: pd.DataFrame,
    symbol: str = "",
    surveillance_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Detects recent 20-bar NSE circuit freezes, optional ASM/GSM surveillance status
    from `data/nse_surveillance.json`, and 20-day average daily turnover (Rs Cr).
    """
    sym_u = str(symbol or "").upper().strip()
    surv_list_status: Optional[str] = None
    s_path = surveillance_path or os.path.join(PROJECT_ROOT, "data", "nse_surveillance.json")
    if sym_u and s_path and os.path.exists(s_path):
        try:
            with open(s_path, "r", encoding="utf-8") as f:
                sdata = json.load(f) or {}
            asm_set = {str(x).upper().strip() for x in (sdata.get("asm") or [])}
            gsm_set = {str(x).upper().strip() for x in (sdata.get("gsm") or [])}
            if sym_u in gsm_set:
                surv_list_status = "GSM"
            elif sym_u in asm_set:
                surv_list_status = "ASM"
        except Exception:
            pass

    circuit_lock_days_20d = 0
    avg_daily_turnover_cr: Optional[float] = None
    if df is not None and not df.empty and "CLOSE_PRICE" in df.columns:
        tail_df = df.tail(20).copy()
        c = pd.to_numeric(tail_df["CLOSE_PRICE"], errors="coerce")
        h = pd.to_numeric(tail_df["HIGH_PRICE"], errors="coerce") if "HIGH_PRICE" in tail_df.columns else c
        l = pd.to_numeric(tail_df["LOW_PRICE"], errors="coerce") if "LOW_PRICE" in tail_df.columns else c
        prev_c = c.shift(1)
        ret = (c - prev_c).abs() / prev_c.replace(0, np.nan)
        hl_spread = (h - l).abs() / c.clip(lower=1e-6)

        freeze_mask = (((h - l).abs() <= 1e-6) & (ret.fillna(0.0) >= 0.018)) | (
            (ret.fillna(0.0) >= 0.048) & (hl_spread < 0.005)
        )
        circuit_lock_days_20d = int(freeze_mask.sum())

        if "VOLUME" in tail_df.columns:
            vol = pd.to_numeric(tail_df["VOLUME"], errors="coerce").fillna(0.0)
            turnover = (c.fillna(0.0) * vol)
            if (turnover > 0).any():
                avg_daily_turnover_cr = round(float(turnover.mean()) / 1e7, 2)

    surveillance_flag = bool(surv_list_status) or (circuit_lock_days_20d >= 2)
    if surv_list_status == "GSM" or circuit_lock_days_20d >= 3:
        circuit_risk = "HIGH"
    elif surveillance_flag:
        circuit_risk = "ELEVATED"
    else:
        circuit_risk = "LOW"

    warning_parts = []
    if surv_list_status:
        warning_parts.append(f"NSE {surv_list_status} surveillance list")
    if circuit_lock_days_20d >= 2:
        warning_parts.append(f"{circuit_lock_days_20d} recent circuit-locked sessions")
    surveillance_warning = (
        f"Circuit/Surveillance caution ({', '.join(warning_parts)})"
        if warning_parts
        else None
    )

    return {
        "circuit_lock_days_20d": circuit_lock_days_20d,
        "surveillance_status": surv_list_status,
        "surveillance_flag": surveillance_flag,
        "circuit_risk": circuit_risk,
        "avg_daily_turnover_cr": avg_daily_turnover_cr,
        "surveillance_warning": surveillance_warning,
    }


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

        # True Structural Risk Management (Wilder ATR-14 & Swing Pivots)
        last_price = float(close.iloc[-1])
        high = df['HIGH_PRICE']
        low = df['LOW_PRICE']
        atr_series = wilder_atr(high, low, close, 14).dropna()
        atr_14 = float(atr_series.iloc[-1]) if not atr_series.empty else float(last_price * 0.025)
        atr_pct = (atr_14 / last_price) if last_price > 0 else 0.025

        # 15-day Structural Swing Support (Low)
        recent_lows = low.tail(15)
        swing_low = float(recent_lows.min()) if not recent_lows.empty else last_price * 0.95

        # ATR-Adaptive Stop Loss: bounds scale naturally between calm blue-chips & high-beta midcaps
        min_risk_pct = max(0.015, min(0.06, 1.5 * atr_pct))
        max_risk_pct = max(min_risk_pct + 0.015, min(0.12, 3.0 * atr_pct))
        raw_sl = min(swing_low * 0.995, last_price - (1.8 * atr_14))
        risk_dist = last_price - raw_sl
        risk_pct = (risk_dist / last_price) if last_price > 0 else min_risk_pct

        if risk_pct < min_risk_pct:
            raw_sl = last_price * (1.0 - min_risk_pct)
        elif risk_pct > max_risk_pct:
            raw_sl = last_price * (1.0 - max_risk_pct)

        tick_size = 0.01 if last_price < 250.0 else 0.05
        suggested_stop_loss = snap_nse_tick(raw_sl, direction="down")
        if suggested_stop_loss >= last_price:
            suggested_stop_loss = round(max(0.05, last_price - tick_size), 2)

        risk_amount = max(0.01, last_price - suggested_stop_loss)

        # Structural Target: Enforce minimum 1:2.0 Risk-to-Reward Ratio, snapped to NSE tick
        raw_target = last_price + max(2.0 * risk_amount, 2.5 * atr_14)
        suggested_target_1 = snap_nse_tick(raw_target, direction="nearest")
        if suggested_target_1 <= last_price:
            suggested_target_1 = snap_nse_tick(last_price + tick_size, direction="up")
        risk_reward_ratio = round((suggested_target_1 - last_price) / risk_amount, 2)

        # Risk Classification
        risk_level = "Moderate Risk"
        if annualized_vol > 35:
            risk_level = "High Risk / High Volatility"
        elif annualized_vol < 18:
            risk_level = "Low Volatility / Stable"

        circ = check_circuit_and_surveillance(df, symbol=symbol)

        return {
            "symbol": symbol,
            "last_price": last_price,
            "atr_14": round(atr_14, 2),
            "atr_pct": round(atr_pct * 100.0, 2),
            "tick_size": tick_size,
            "stop_method": "ATR-Adaptive",
            "annualized_volatility_pct": annualized_vol,
            "value_at_risk_95_pct": abs(var_95),
            "max_drawdown_pct": abs(max_drawdown),
            "suggested_stop_loss": suggested_stop_loss,
            "suggested_target_price": suggested_target_1,
            "risk_reward_ratio": f"1:{risk_reward_ratio}",
            "risk_classification": risk_level,
            "circuit_lock_days_20d": circ["circuit_lock_days_20d"],
            "surveillance_flag": circ["surveillance_flag"],
            "circuit_risk": circ["circuit_risk"],
            "avg_daily_turnover_cr": circ["avg_daily_turnover_cr"],
            "surveillance_warning": circ["surveillance_warning"],
        }
