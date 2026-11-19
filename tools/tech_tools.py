"""
Technical Analysis Engine.
Computes Moving Averages (20, 50, 200), RSI (14), MACD, Bollinger Bands,
Support/Resistance levels, and detects advanced chart patterns:
- Head and Shoulders & Inverse Head and Shoulders
- Bollinger Band Squeeze, %B expansion, and mean-reversion bounces
- Saucer Pattern (Rounding Bottom / Accumulation Bowl)
- Double Bottom (W) & Double Top (M) formations.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional

from tools.historical_data_tools import HistoricalDataEngine
from storage.cache_manager import CacheManager
from tools.pattern_engine import QuantitativePatternEngine


def wilder_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index with Wilder's smoothing: the first average is the simple mean of the first `period`
    changes, then avg = (previous_avg * (period - 1) + current) / period. NaN until `period` changes exist.
    A series with no losses is 100, and one with no movement at all is 50.
    """
    values = close.astype(float).to_numpy()
    out = np.full(len(values), np.nan)
    if len(values) <= period:
        return pd.Series(out, index=close.index)
    delta = np.diff(values)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = gain[:period].mean()
    avg_loss = loss[:period].mean()

    def _rsi(g, l):
        if l == 0:
            return 50.0 if g == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return pd.Series(out, index=close.index)


def _safe_float(value, decimals: int = 2):
    """Convert a value to float, returning None for NaN/Inf (which are invalid JSON)."""
    try:
        v = float(value)
        if v != v or v == float('inf') or v == float('-inf'):  # NaN or Inf check
            return None
        return round(v, decimals) if decimals >= 0 else v
    except (TypeError, ValueError):
        return None


class TechnicalAnalysisEngine:
    def __init__(self, rag_engine: Optional[HistoricalDataEngine] = None, cache_manager: Optional[CacheManager] = None, pattern_engine: Optional[QuantitativePatternEngine] = None):
        self.rag_engine = rag_engine or HistoricalDataEngine(cache_manager=cache_manager)
        self.pattern_engine = pattern_engine or QuantitativePatternEngine()

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Computes technical indicator series over candles dataframe."""
        df = df.copy()
        close = df['CLOSE_PRICE']

        # Moving Averages
        df['SMA_20'] = close.rolling(window=20).mean()
        df['EMA_20'] = close.ewm(span=20, adjust=False).mean()
        df['SMA_50'] = close.rolling(window=50).mean()
        df['SMA_200'] = close.rolling(window=200).mean() if len(close) >= 200 else close.rolling(window=len(close)).mean()
        df['SMA_50_SLOPE'] = (df['SMA_50'] - df['SMA_50'].shift(10)) / df['SMA_50'].shift(10).replace(0, 1) * 100

        # Volume MA & RVOL
        vol = df['VOLUME'] if 'VOLUME' in df else pd.Series(1, index=df.index)
        vol_ma20 = vol.rolling(window=20).mean()
        df['RVOL'] = vol / (vol_ma20 + 1e-5)

        # 20-day Up/Down Volume Ratio (William O'Neil / CANSLIM institutional accumulation standard)
        diff_close = close.diff()
        up_vol = vol.where(diff_close > 0, 0.0)
        down_vol = vol.where(diff_close < 0, 0.0)
        sum_up_20 = up_vol.rolling(window=20).sum()
        sum_down_20 = down_vol.rolling(window=20).sum()
        df['UP_DOWN_VOL_RATIO_20'] = np.where(sum_down_20 > 0, sum_up_20 / (sum_down_20 + 1e-5), 1.0)

        # Structural Support & Resistance Lookbacks (Multi-week Swings)
        high_s = df['HIGH_PRICE'] if 'HIGH_PRICE' in df else close
        low_s = df['LOW_PRICE'] if 'LOW_PRICE' in df else close
        df['SWING_HIGH_20'] = high_s.rolling(window=20).max()
        df['SWING_LOW_20'] = low_s.rolling(window=20).min()
        df['SWING_HIGH_60'] = high_s.rolling(window=60).max() if len(df) >= 60 else high_s.rolling(window=len(df)).max()
        df['SWING_LOW_60'] = low_s.rolling(window=60).min() if len(df) >= 60 else low_s.rolling(window=len(df)).min()

        # 52-Week High & Low and Proximity Percentage
        w52_len = min(250, len(df))
        df['HIGH_52W'] = high_s.rolling(window=w52_len).max()
        df['LOW_52W'] = low_s.rolling(window=w52_len).min()
        df['PCT_FROM_52W_HIGH'] = (close - df['HIGH_52W']) / np.where(df['HIGH_52W'] > 0, df['HIGH_52W'], 1.0) * 100

        # Average True Range (ATR 14)
        if 'HIGH_PRICE' in df and 'LOW_PRICE' in df:
            prev_close = close.shift(1)
            tr = pd.concat([df['HIGH_PRICE'] - df['LOW_PRICE'], (df['HIGH_PRICE'] - prev_close).abs(), (df['LOW_PRICE'] - prev_close).abs()], axis=1).max(axis=1)
            df['ATR_14'] = tr.rolling(window=14).mean()
        else:
            df['ATR_14'] = close * 0.025

        # RSI (14), Wilder smoothing (the definition charting platforms use)
        df['RSI_14'] = wilder_rsi(close, 14)

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
        df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / np.where(df['SMA_20'] > 0, df['SMA_20'], 1.0)
        denom = np.where((df['BB_UPPER'] - df['BB_LOWER']) > 0, (df['BB_UPPER'] - df['BB_LOWER']), 1e-6)
        df['BB_PCT_B'] = (close - df['BB_LOWER']) / denom

        return df

    def detect_chart_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Detects comprehensive quantitative chart patterns:
        - Cup and Handle (William O'Neil / CANSLIM standard)
        - Saucer Pattern (Rounding Bottom / Accumulation Bowl via Quadratic Regression)
        - Head & Shoulders and Inverse Head & Shoulders (Neckline Regression)
        - John Carter's TTM Bollinger/Keltner Squeeze & Breakouts
        - Wyckoff Accumulation Spring (Phase C) & Upthrust (UTAD)
        - Bull Flag & Bear Flag (High-Tight Impulse continuations)
        - Multi-Pivot Quantitative RSI Divergence (Bullish & Bearish)
        - Harmonic Gartley & Bat (Bullish & Bearish PRZ Fibonacci Geometry)
        - Ascending & Descending Triangles
        - Double Bottom (W-Pattern) & Double Top (M-Pattern)
        - Candlestick Reversals (Morning/Evening Star, Bullish/Bearish Engulfing with Volume)
        - Bollinger Band Expansion & Mean Reversion Piercings
        """
        if df.empty or len(df) < 15:
            return []

        # 1. Run Quantitative Pattern Engine (mathematically verified swing & curve patterns)
        try:
            quant_patterns = self.pattern_engine.scan_all_patterns(df)
        except Exception:
            quant_patterns = []

        patterns = list(quant_patterns)
        seen_names = {p["name"].split(" (")[0] for p in patterns}

        # 2. Bollinger Band expansion & piercing signals
        if 'BB_WIDTH' in df and 'BB_PCT_B' in df:
            bandwidth = df['BB_WIDTH'].dropna().values
            pct_b = float(df['BB_PCT_B'].iloc[-1])
            curr_bw = float(df['BB_WIDTH'].iloc[-1])
            bb_upper_val = float(df['BB_UPPER'].iloc[-1])
            bb_lower_val = float(df['BB_LOWER'].iloc[-1])

            lookback_bw = min(60, len(bandwidth))
            if lookback_bw > 10:
                recent_bw = bandwidth[-lookback_bw:]
                bw_percentile = float((recent_bw < curr_bw).sum() / len(recent_bw) * 100)

                if "TTM Bollinger Squeeze" not in seen_names and bw_percentile <= 18:
                    patterns.append({
                        "name": "Bollinger Band Squeeze",
                        "category": "Volatility Breakout",
                        "type": "Breakout Watch",
                        "direction": "Neutral / Expansion Imminent",
                        "quality_score": 82,
                        "significance": "High",
                        "confidence": "High",
                        "status": "Energy Compression",
                        "entry_trigger": round(float(df['CLOSE_PRICE'].iloc[-1]), 2),
                        "target_price": round(bb_upper_val, 2),
                        "stop_loss": round(bb_lower_val, 2),
                        "risk_reward_ratio": 1.5,
                        "description": f"Volatility compression (BandWidth at {bw_percentile:.0f}th percentile). Coiled energy signals sharp directional breakout imminent.",
                        "metrics": {"bandwidth": round(curr_bw, 4), "percentile": round(bw_percentile, 1), "target": round(bb_upper_val, 2)}
                    })
                elif pct_b >= 0.98 and "Bollinger Upper Band Walk" not in seen_names:
                    patterns.append({
                        "name": "Bollinger Upper Band Walk",
                        "category": "Trend Continuation",
                        "type": "Bullish Expansion",
                        "direction": "Bullish",
                        "quality_score": 80,
                        "significance": "Medium",
                        "confidence": "Medium",
                        "status": "Trending Along Band",
                        "entry_trigger": round(float(df['CLOSE_PRICE'].iloc[-1]), 2),
                        "target_price": round(bb_upper_val * 1.03, 2),
                        "stop_loss": round(float(df['SMA_20'].iloc[-1]), 2) if 'SMA_20' in df else round(bb_lower_val, 2),
                        "risk_reward_ratio": 1.8,
                        "description": f"Price pushing upper Bollinger Band (%B: {pct_b:.2f}, Upper: Rs.{bb_upper_val:.2f}). Strong bullish trend expansion.",
                        "metrics": {"pct_b": round(pct_b, 2), "upper_band": round(bb_upper_val, 2)}
                    })
                elif pct_b <= 0.05 and "Bollinger Lower Band Piercing" not in seen_names:
                    patterns.append({
                        "name": "Bollinger Lower Band Piercing",
                        "category": "Mean Reversion",
                        "type": "Oversold Reversal",
                        "direction": "Bullish Reversal Watch",
                        "quality_score": 79,
                        "significance": "Medium",
                        "confidence": "Medium",
                        "status": "Testing Lower Band",
                        "entry_trigger": round(float(df['CLOSE_PRICE'].iloc[-1]), 2),
                        "target_price": round(float(df['SMA_20'].iloc[-1]), 2) if 'SMA_20' in df else round(bb_upper_val, 2),
                        "stop_loss": round(bb_lower_val * 0.98, 2),
                        "risk_reward_ratio": 2.0,
                        "description": f"Price testing lower Bollinger Band (%B: {pct_b:.2f}, Lower: Rs.{bb_lower_val:.2f}). Mean-reversion bounce opportunity.",
                        "metrics": {"pct_b": round(pct_b, 2), "lower_band": round(bb_lower_val, 2)}
                    })

        # Ensure all patterns conform to schema with defaults
        for p in patterns:
            score = p.get("quality_score", 75)
            if "significance" not in p:
                p["significance"] = "High" if score >= 80 else "Medium"
            if "confidence" not in p:
                p["confidence"] = "High" if score >= 80 else "Medium"
            if "metrics" not in p:
                p["metrics"] = {
                    "target": p.get("target_price"),
                    "stop_loss": p.get("stop_loss"),
                    "quality_score": score
                }

        # Sort by quality score descending
        patterns.sort(key=lambda x: x.get("quality_score", 0), reverse=True)
        return patterns

    def analyze_symbol(self, symbol: str) -> Dict[str, Any]:
        """Calculates key technical metrics and detects chart patterns for a stock symbol."""
        df = self.rag_engine.load_symbol_history(symbol)
        if df.empty or len(df) < 20:
            return {
                "symbol": symbol,
                "status": "Insufficient historical data for technical analysis.",
                "detected_patterns": [],
                "technical_signals": []
            }

        df = self._compute_indicators(df)

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        pivot = (prev['HIGH_PRICE'] + prev['LOW_PRICE'] + prev['CLOSE_PRICE']) / 3.0
        r1 = (2 * pivot) - prev['LOW_PRICE']
        s1 = (2 * pivot) - prev['HIGH_PRICE']
        r2 = pivot + (prev['HIGH_PRICE'] - prev['LOW_PRICE'])
        s2 = pivot - (prev['HIGH_PRICE'] - prev['LOW_PRICE'])

        latest_close = _safe_float(latest['CLOSE_PRICE'])
        rsi_val = _safe_float(latest['RSI_14']) or 50.0
        macd_val = _safe_float(latest['MACD']) or 0.0
        macd_sig = _safe_float(latest['MACD_SIGNAL']) or 0.0
        sma_20_val = _safe_float(latest['SMA_20']) or latest_close
        sma_50_val = _safe_float(latest['SMA_50']) or latest_close
        sma_200_val = _safe_float(latest['SMA_200']) or latest_close
        bb_upper = _safe_float(latest['BB_UPPER']) or latest_close
        bb_lower = _safe_float(latest['BB_LOWER']) or latest_close
        bb_width = _safe_float(latest['BB_WIDTH'], 4) or 0.0
        bb_pct_b = _safe_float(latest['BB_PCT_B']) or 0.5

        # Detect advanced patterns
        patterns = self.detect_chart_patterns(df)

        ema_20_val = _safe_float(latest.get('EMA_20', sma_20_val)) or latest_close
        sma_50_slope = _safe_float(latest.get('SMA_50_SLOPE', 0.0)) or 0.0
        atr_14_val = _safe_float(latest.get('ATR_14', latest_close * 0.025)) or (latest_close * 0.025)
        rvol_val = _safe_float(latest.get('RVOL', 1.0)) or 1.0
        ud_vol_ratio = _safe_float(latest.get('UP_DOWN_VOL_RATIO_20', 1.0)) or 1.0

        swing_h20 = _safe_float(latest.get('SWING_HIGH_20', r1)) or r1
        swing_l20 = _safe_float(latest.get('SWING_LOW_20', s1)) or s1
        swing_h60 = _safe_float(latest.get('SWING_HIGH_60', r2)) or r2
        swing_l60 = _safe_float(latest.get('SWING_LOW_60', s2)) or s2
        h_52w = _safe_float(latest.get('HIGH_52W', swing_h60)) or swing_h60
        l_52w = _safe_float(latest.get('LOW_52W', swing_l60)) or swing_l60
        pct_52w = _safe_float(latest.get('PCT_FROM_52W_HIGH', 0.0)) or 0.0

        signals = []
        if latest_close > sma_50_val:
            slope_txt = " (Rising)" if sma_50_slope > 0.2 else (" (Declining)" if sma_50_slope < -0.2 else "")
            signals.append(f"Above 50-day SMA{slope_txt} (Short-term Bullish)")
        else:
            signals.append("Below 50-day SMA (Short-term Bearish)")

        if rvol_val >= 1.25:
            signals.append(f"Volume Surge (RVOL {rvol_val:.1f}x)")

        if ud_vol_ratio >= 1.25:
            signals.append(f"Institutional Accumulation (20d U/D Vol Ratio {ud_vol_ratio:.2f}x)")
        elif ud_vol_ratio <= 0.75:
            signals.append(f"Institutional Distribution (20d U/D Vol Ratio {ud_vol_ratio:.2f}x)")

        if pct_52w >= -5.0:
            signals.append(f"Near 52-Week High ({pct_52w:+.1f}% - Leader Relative Strength)")

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

        for p in patterns:
            signals.append(f"Pattern: {p['name']} ({p['type']})")

        return {
            "symbol": symbol,
            "last_price": latest_close,
            "ema_20": _safe_float(ema_20_val),
            "sma_20": _safe_float(sma_20_val),
            "sma_50": _safe_float(sma_50_val),
            "sma_200": _safe_float(sma_200_val),
            "sma_50_slope": _safe_float(sma_50_slope),
            "atr_14": _safe_float(atr_14_val),
            "rvol": _safe_float(rvol_val),
            "up_down_vol_ratio": _safe_float(ud_vol_ratio),
            "rsi_14": _safe_float(rsi_val),
            "macd": _safe_float(macd_val),
            "macd_signal": _safe_float(macd_sig),
            "bollinger_upper": _safe_float(bb_upper),
            "bollinger_middle": _safe_float(sma_20_val),
            "bollinger_lower": _safe_float(bb_lower),
            "bollinger_bandwidth": _safe_float(bb_width, 4),
            "bollinger_pct_b": _safe_float(bb_pct_b),
            "resistance_1": _safe_float(r1),
            "support_1": _safe_float(s1),
            "resistance_2": _safe_float(r2),
            "support_2": _safe_float(s2),
            "swing_high_20": _safe_float(swing_h20),
            "swing_low_20": _safe_float(swing_l20),
            "swing_high_60": _safe_float(swing_h60),
            "swing_low_60": _safe_float(swing_l60),
            "high_52w": _safe_float(h_52w),
            "low_52w": _safe_float(l_52w),
            "pct_from_52w_high": _safe_float(pct_52w),
            "technical_signals": signals,
            "detected_patterns": patterns
        }

    def get_chart_data(self, symbol: str, limit_days: int = 90) -> Dict[str, Any]:
        """
        Extracts formatted historical candles, technical indicators, and patterns
        for interactive frontend charts (Canvas / SVG / Chart.js).
        """
        df = self.rag_engine.load_symbol_history(symbol, limit_days=limit_days + 40)
        if df.empty or len(df) < 15:
            return {"symbol": symbol, "candles": [], "patterns": []}

        df = self._compute_indicators(df)
        df_chart = df.tail(limit_days).reset_index(drop=True)

        candles = []
        for _, row in df_chart.iterrows():
            candles.append({
                "date": str(row['DATE'])[:10],
                "open": round(float(row.get('OPEN_PRICE', row['CLOSE_PRICE'])), 2),
                "high": round(float(row.get('HIGH_PRICE', row['CLOSE_PRICE'])), 2),
                "low": round(float(row.get('LOW_PRICE', row['CLOSE_PRICE'])), 2),
                "close": round(float(row['CLOSE_PRICE']), 2),
                "volume": int(row.get('VOLUME', 0)),
                "sma_20": round(float(row['SMA_20']), 2) if pd.notna(row.get('SMA_20')) else None,
                "sma_50": round(float(row['SMA_50']), 2) if pd.notna(row.get('SMA_50')) else None,
                "sma_200": round(float(row['SMA_200']), 2) if pd.notna(row.get('SMA_200')) else None,
                "bb_upper": round(float(row['BB_UPPER']), 2) if pd.notna(row.get('BB_UPPER')) else None,
                "bb_middle": round(float(row['SMA_20']), 2) if pd.notna(row.get('SMA_20')) else None,
                "bb_lower": round(float(row['BB_LOWER']), 2) if pd.notna(row.get('BB_LOWER')) else None,
                "rsi": round(float(row['RSI_14']), 1) if pd.notna(row.get('RSI_14')) else None
            })

        patterns = self.detect_chart_patterns(df)

        return {
            "symbol": symbol,
            "candles": candles,
            "patterns": patterns,
            "last_price": round(float(df_chart['CLOSE_PRICE'].iloc[-1]), 2),
            "bb_upper": round(float(df_chart['BB_UPPER'].iloc[-1]), 2) if pd.notna(df_chart['BB_UPPER'].iloc[-1]) else None,
            "bb_lower": round(float(df_chart['BB_LOWER'].iloc[-1]), 2) if pd.notna(df_chart['BB_LOWER'].iloc[-1]) else None,
            "sma_20": round(float(df_chart['SMA_20'].iloc[-1]), 2) if pd.notna(df_chart['SMA_20'].iloc[-1]) else None
        }
