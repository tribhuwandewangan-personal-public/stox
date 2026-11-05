"""
Quantitative Technical Pattern Recognition Engine.
Provides institutional-grade, mathematically verified pattern detection:
1. Head and Shoulders & Inverse Head and Shoulders (with Neckline regression & volume divergence)
2. Cup and Handle (William O'Neil / CANSLIM standard with U-base and handle volume contraction)
3. Saucer Pattern (Rounding Bottom / Institutional Accumulation Bowl via Quadratic Regression)
4. John Carter's TTM Squeeze (Bollinger Bands compressed inside Keltner Channels + Momentum)
5. Ascending & Descending Triangles (Horizontal support/resistance + directional slope)
6. Double Bottom (W-Pattern) & Double Top (M-Pattern) with neckline confirmation
7. Harmonic Patterns (Gartley & Bat: Bullish and Bearish PRZ via exact Fibonacci retracements)
8. Bull Flag & Bear Flag (High-Tight Impulse Pole + Controlled Channel Consolidation)
9. Wyckoff Accumulation Spring & Upthrust (Phase C Test with institutional volume signature)
10. Multi-Pivot Quantitative RSI Divergence (Regular Bullish & Bearish momentum divergences)
11. High-Conviction Reversal Candlesticks (Morning/Evening Star, Bullish/Bearish Engulfing with volume surges)
"""

import numpy as np
import pandas as pd
from typing import Dict, Any, List, Optional, Tuple


class QuantitativePatternEngine:
    """
    State-of-the-art quantitative pattern recognition engine.
    Uses ATR-adaptive swing extraction, polynomial curve fitting,
    and Fibonacci geometry to compute quality scores (0-100),
    exact breakout triggers, price targets, and structural stop losses.
    """

    def __init__(self):
        pass

    @staticmethod
    def compute_atr_and_keltner(df: pd.DataFrame, period: int = 20) -> pd.DataFrame:
        """Computes True Range, ATR, Keltner Channels, RSI, and TTM Momentum."""
        df = df.copy()
        high = df['HIGH_PRICE']
        low = df['LOW_PRICE']
        close = df['CLOSE_PRICE']

        # True Range
        prev_close = close.shift(1).fillna(close)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['TR'] = tr
        df['ATR_14'] = tr.rolling(window=14).mean().fillna(tr)
        df['ATR_20'] = tr.rolling(window=period).mean().fillna(tr)

        # 20 SMA & Bollinger Bands
        df['SMA_20'] = close.rolling(window=period).mean().fillna(close)
        std_20 = close.rolling(window=period).std().fillna(0)
        df['BB_UPPER'] = df['SMA_20'] + (std_20 * 2.0)
        df['BB_LOWER'] = df['SMA_20'] - (std_20 * 2.0)
        df['BB_WIDTH'] = (df['BB_UPPER'] - df['BB_LOWER']) / np.where(df['SMA_20'] > 0, df['SMA_20'], 1.0)
        denom = np.where((df['BB_UPPER'] - df['BB_LOWER']) > 0, (df['BB_UPPER'] - df['BB_LOWER']), 1e-6)
        df['BB_PCT_B'] = (close - df['BB_LOWER']) / denom

        # Keltner Channels (20 SMA, 1.5 * ATR_20)
        df['KC_UPPER'] = df['SMA_20'] + (df['ATR_20'] * 1.5)
        df['KC_LOWER'] = df['SMA_20'] - (df['ATR_20'] * 1.5)

        # TTM Squeeze Condition: Bollinger Bands strictly inside Keltner Channels
        df['IN_SQUEEZE'] = (df['BB_UPPER'] < df['KC_UPPER']) & (df['BB_LOWER'] > df['KC_LOWER'])

        # Momentum Oscillator for Squeeze Direction
        highest_20 = high.rolling(window=period).max()
        lowest_20 = low.rolling(window=period).min()
        donchian_mid = (highest_20 + lowest_20) / 2.0
        delta = close - ((donchian_mid + df['SMA_20']) / 2.0)
        df['TTM_MOMENTUM'] = delta.rolling(window=12).mean().fillna(0)

        # RSI (14) if not present
        if 'RSI_14' not in df:
            d_price = close.diff()
            gain = (d_price.where(d_price > 0, 0)).rolling(window=14).mean()
            loss = (-d_price.where(d_price < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            df['RSI_14'] = 100 - (100 / (1 + rs))

        return df

    @staticmethod
    def extract_zigzag_swings(df: pd.DataFrame, delta_pct: float = 0.035) -> List[Dict[str, Any]]:
        """
        Extracts structural swing highs and lows using an ATR-adaptive ZigZag filter.
        Eliminates minor bar-to-bar noise and preserves major structural turning points.
        """
        if len(df) < 15:
            return []

        highs = df['HIGH_PRICE'].values
        lows = df['LOW_PRICE'].values
        closes = df['CLOSE_PRICE'].values
        volumes = df['VOLUME'].values if 'VOLUME' in df else np.zeros(len(df))
        dates = df['DATE'].astype(str).values if 'DATE' in df else [str(i) for i in range(len(df))]
        rsi_series = df['RSI_14'].values if 'RSI_14' in df else np.zeros(len(df))
        n = len(closes)

        atr_series = df['ATR_14'].values if 'ATR_14' in df else closes * 0.02
        swings = []

        trend = 0
        curr_high = highs[0]
        curr_high_idx = 0
        curr_low = lows[0]
        curr_low_idx = 0

        for i in range(1, n):
            threshold = max(closes[i] * delta_pct, atr_series[i] * 1.4)

            if trend >= 0:
                if highs[i] > curr_high:
                    curr_high = highs[i]
                    curr_high_idx = i
                elif curr_high - lows[i] >= threshold:
                    swings.append({
                        "type": "high",
                        "idx": curr_high_idx,
                        "date": dates[curr_high_idx],
                        "price": float(curr_high),
                        "volume": float(volumes[curr_high_idx]),
                        "rsi": float(rsi_series[curr_high_idx]) if not np.isnan(rsi_series[curr_high_idx]) else 50.0
                    })
                    curr_low = lows[i]
                    curr_low_idx = i
                    trend = -1
            else:
                if lows[i] < curr_low:
                    curr_low = lows[i]
                    curr_low_idx = i
                elif highs[i] - curr_low >= threshold:
                    swings.append({
                        "type": "low",
                        "idx": curr_low_idx,
                        "date": dates[curr_low_idx],
                        "price": float(curr_low),
                        "volume": float(volumes[curr_low_idx]),
                        "rsi": float(rsi_series[curr_low_idx]) if not np.isnan(rsi_series[curr_low_idx]) else 50.0
                    })
                    curr_high = highs[i]
                    curr_high_idx = i
                    trend = 1

        if trend == 1 and curr_high_idx > (swings[-1]["idx"] if swings else -1):
            swings.append({
                "type": "high",
                "idx": curr_high_idx,
                "date": dates[curr_high_idx],
                "price": float(curr_high),
                "volume": float(volumes[curr_high_idx]),
                "rsi": float(rsi_series[curr_high_idx]) if not np.isnan(rsi_series[curr_high_idx]) else 50.0
            })
        elif trend == -1 and curr_low_idx > (swings[-1]["idx"] if swings else -1):
            swings.append({
                "type": "low",
                "idx": curr_low_idx,
                "date": dates[curr_low_idx],
                "price": float(curr_low),
                "volume": float(volumes[curr_low_idx]),
                "rsi": float(rsi_series[curr_low_idx]) if not np.isnan(rsi_series[curr_low_idx]) else 50.0
            })

        return swings

    # =========================================================================
    # Pattern 1: Head and Shoulders & Inverse Head and Shoulders
    # =========================================================================
    @classmethod
    def detect_head_and_shoulders(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 5 or len(df) < 30:
            return patterns

        curr_close = float(df['CLOSE_PRICE'].iloc[-1])
        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]

        # Regular Head & Shoulders (Bearish)
        # Search backwards from the most recent peaks so only active recent patterns are found
        if len(peaks) >= 3:
            for i in range(len(peaks) - 3, -1, -1):
                p1, p2, p3 = peaks[i], peaks[i + 1], peaks[i + 2]
                # Right shoulder must be recent (formed within last 45 bars)
                if (len(df) - 1 - p3["idx"]) > 45:
                    continue

                if p2["price"] > p1["price"] * 1.018 and p2["price"] > p3["price"] * 1.018:
                    shoulder_diff = abs(p1["price"] - p3["price"]) / min(p1["price"], p3["price"])
                    if shoulder_diff <= 0.065:
                        t1_candidates = [t for t in troughs if p1["idx"] < t["idx"] < p2["idx"]]
                        t2_candidates = [t for t in troughs if p2["idx"] < t["idx"] < p3["idx"]]
                        if t1_candidates and t2_candidates:
                            t1 = min(t1_candidates, key=lambda x: x["price"])
                            t2 = min(t2_candidates, key=lambda x: x["price"])
                            # Neckline troughs must be below shoulders
                            if t1["price"] < min(p1["price"], p2["price"]) and t2["price"] < min(p2["price"], p3["price"]):
                                avg_neckline = (t1["price"] + t2["price"]) / 2.0
                                slope = (t2["price"] - t1["price"]) / max(1, t2["idx"] - t1["idx"])
                                projected_neckline = t2["price"] + slope * (len(df) - 1 - t2["idx"])
                                # Protect against extreme slope extrapolation
                                if abs(projected_neckline - avg_neckline) / avg_neckline > 0.08:
                                    projected_neckline = avg_neckline

                                # Pattern neckline must be in proximity to current price (within 15%)
                                if abs(curr_close - projected_neckline) / curr_close > 0.15:
                                    continue
                                
                                head_height = p2["price"] - projected_neckline
                                if head_height > 0 and projected_neckline < min(p1["price"], p3["price"]):
                                    target = projected_neckline - head_height
                                    # Bearish target must be below current price and below neckline
                                    if target >= curr_close or target >= projected_neckline:
                                        continue
                                    # If price already collapsed far beyond target (>10%), pattern has expired
                                    if curr_close < target * 0.90:
                                        continue

                                    is_confirmed = curr_close < projected_neckline

                                    score = 75
                                    if shoulder_diff <= 0.035: score += 10
                                    if p1["volume"] > p3["volume"]: score += 10
                                    if is_confirmed: score += 5

                                    status = "Confirmed Breakdown" if is_confirmed else "Forming / Testing Neckline"
                                    rr = round(abs(projected_neckline - target) / max(1.0, abs(p3["price"] - projected_neckline)), 2)

                                    patterns.append({
                                        "name": "Head and Shoulders",
                                        "category": "Reversal",
                                        "type": "Bearish Breakdown" if is_confirmed else "Bearish Caution",
                                        "direction": "Bearish",
                                        "quality_score": min(98, score),
                                        "significance": "High",
                                        "confidence": "High" if is_confirmed else "Medium",
                                        "status": status,
                                        "entry_trigger": round(float(projected_neckline), 2),
                                        "target_price": round(float(target), 2),
                                        "stop_loss": round(float(p3["price"]), 2),
                                        "risk_reward_ratio": rr,
                                        "description": (
                                            f"Head at Rs.{p2['price']:.2f}, Shoulders at ~Rs.{p1['price']:.2f}. "
                                            f"Neckline at Rs.{projected_neckline:.2f} ({status}). "
                                            f"Downside target: Rs.{target:.2f} (Stop: Rs.{p3['price']:.2f}, R:R: {rr})."
                                        ),
                                        "key_levels": {
                                            "head": round(float(p2["price"]), 2),
                                            "left_shoulder": round(float(p1["price"]), 2),
                                            "right_shoulder": round(float(p3["price"]), 2),
                                            "neckline": round(float(projected_neckline), 2)
                                        },
                                        "metrics": {
                                            "head": round(float(p2["price"]), 2),
                                            "neckline": round(float(projected_neckline), 2),
                                            "target": round(float(target), 2),
                                            "stop_loss": round(float(p3["price"]), 2)
                                        }
                                    })
                                    break

        # Inverse Head & Shoulders (Bullish Reversal)
        # Search backwards from the most recent troughs so only active recent patterns are found
        if len(troughs) >= 3:
            for i in range(len(troughs) - 3, -1, -1):
                t1, t2, t3 = troughs[i], troughs[i + 1], troughs[i + 2]
                # Right shoulder must be recent (formed within last 45 bars)
                if (len(df) - 1 - t3["idx"]) > 45:
                    continue

                if t2["price"] < t1["price"] * 0.982 and t2["price"] < t3["price"] * 0.982:
                    shoulder_diff = abs(t1["price"] - t3["price"]) / max(t1["price"], t3["price"])
                    if shoulder_diff <= 0.065:
                        p1_candidates = [p for p in peaks if t1["idx"] < p["idx"] < t2["idx"]]
                        p2_candidates = [p for p in peaks if t2["idx"] < p["idx"] < t3["idx"]]
                        if p1_candidates and p2_candidates:
                            p1 = max(p1_candidates, key=lambda x: x["price"])
                            p2 = max(p2_candidates, key=lambda x: x["price"])
                            # Neckline peaks must be above shoulders
                            if p1["price"] > max(t1["price"], t2["price"]) and p2["price"] > max(t2["price"], t3["price"]):
                                avg_neckline = (p1["price"] + p2["price"]) / 2.0
                                slope = (p2["price"] - p1["price"]) / max(1, p2["idx"] - p1["idx"])
                                projected_neckline = p2["price"] + slope * (len(df) - 1 - p2["idx"])
                                # Protect against extreme slope extrapolation
                                if abs(projected_neckline - avg_neckline) / avg_neckline > 0.08:
                                    projected_neckline = avg_neckline

                                # Pattern neckline must be in proximity to current price (within 15%)
                                if abs(curr_close - projected_neckline) / curr_close > 0.15:
                                    continue

                                head_depth = projected_neckline - t2["price"]
                                if head_depth > 0 and projected_neckline > max(t1["price"], t3["price"]):
                                    target = projected_neckline + head_depth
                                    # Bullish target must be ABOVE current price and above neckline
                                    if target <= curr_close or target <= projected_neckline:
                                        continue
                                    # If price already surged far beyond target (>10%), pattern has expired
                                    if curr_close > target * 1.10:
                                        continue

                                    is_confirmed = curr_close > projected_neckline

                                    score = 75
                                    if shoulder_diff <= 0.035: score += 10
                                    if t3["volume"] > t2["volume"]: score += 10
                                    if is_confirmed: score += 5

                                    status = "Confirmed Breakout" if is_confirmed else "Accumulating Near Neckline"
                                    rr = round(abs(target - projected_neckline) / max(1.0, abs(projected_neckline - t3["price"])), 2)

                                    patterns.append({
                                        "name": "Inverse Head and Shoulders",
                                        "category": "Reversal",
                                        "type": "Bullish Breakout" if is_confirmed else "Bullish Reversal Watch",
                                        "direction": "Bullish",
                                        "quality_score": min(98, score),
                                        "significance": "High",
                                        "confidence": "High" if is_confirmed else "Medium",
                                        "status": status,
                                        "entry_trigger": round(float(projected_neckline), 2),
                                        "target_price": round(float(target), 2),
                                        "stop_loss": round(float(t3["price"]), 2),
                                        "risk_reward_ratio": rr,
                                        "description": (
                                            f"Inverted Head at Rs.{t2['price']:.2f}, Shoulders at ~Rs.{t1['price']:.2f}. "
                                            f"Neckline at Rs.{projected_neckline:.2f} ({status}). "
                                            f"Upside target: Rs.{target:.2f} (Stop: Rs.{t3['price']:.2f}, R:R: {rr})."
                                        ),
                                        "key_levels": {
                                            "head_trough": round(float(t2["price"]), 2),
                                            "left_shoulder": round(float(t1["price"]), 2),
                                            "right_shoulder": round(float(t3["price"]), 2),
                                            "neckline": round(float(projected_neckline), 2)
                                        },
                                        "metrics": {
                                            "head_trough": round(float(t2["price"]), 2),
                                            "neckline": round(float(projected_neckline), 2),
                                            "target": round(float(target), 2),
                                            "stop_loss": round(float(t3["price"]), 2)
                                        }
                                    })
                                    break

        return patterns

    # =========================================================================
    # Pattern 2: Cup and Handle Pattern (O'Neil Standard)
    # =========================================================================
    @classmethod
    def detect_cup_and_handle(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 45 or len(swings) < 4:
            return patterns

        closes = df['CLOSE_PRICE'].values
        volumes = df['VOLUME'].values if 'VOLUME' in df else np.ones(len(df))
        curr_close = float(closes[-1])
        n = len(closes)

        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]

        if len(peaks) >= 2 and len(troughs) >= 1:
            for p_idx in range(len(peaks) - 1):
                p_left = peaks[p_idx]
                p_right = peaks[p_idx + 1]

                prior_start = max(0, p_left["idx"] - 40)
                if prior_start < p_left["idx"]:
                    prior_gain = (p_left["price"] - closes[prior_start]) / closes[prior_start]
                    if prior_gain < 0.10:
                        continue

                cup_bars = p_right["idx"] - p_left["idx"]
                if not (20 <= cup_bars <= 120):
                    continue

                rim_diff = abs(p_left["price"] - p_right["price"]) / p_left["price"]
                if rim_diff > 0.08:
                    continue

                inter_troughs = [t for t in troughs if p_left["idx"] < t["idx"] < p_right["idx"]]
                if not inter_troughs:
                    continue
                cup_trough = min(inter_troughs, key=lambda x: x["price"])
                cup_depth = (p_left["price"] - cup_trough["price"]) / p_left["price"]

                if not (0.10 <= cup_depth <= 0.38):
                    continue

                handle_bars = n - 1 - p_right["idx"]
                if not (3 <= handle_bars <= 25):
                    continue

                handle_closes = closes[p_right["idx"]:]
                handle_low = float(np.min(handle_closes))
                handle_depth = (p_right["price"] - handle_low) / p_right["price"]

                if handle_depth > 0.16 or handle_low < (p_left["price"] + cup_trough["price"]) / 2.0:
                    continue

                avg_vol_cup = np.mean(volumes[p_left["idx"]:p_right["idx"]])
                avg_vol_handle = np.mean(volumes[p_right["idx"]:])
                vol_dry_up = avg_vol_handle < avg_vol_cup * 0.9

                pivot_entry = round(float(p_right["price"]), 2)
                target = round(float(pivot_entry + (p_right["price"] - cup_trough["price"])), 2)
                stop_loss = round(float(handle_low), 2)
                is_breakout = curr_close >= pivot_entry

                score = 80
                if vol_dry_up: score += 10
                if rim_diff <= 0.04: score += 5
                if is_breakout: score += 5

                status = "Confirmed Pivot Breakout" if is_breakout else "Handle Pullback Ready for Breakout"
                rr = round(abs(target - pivot_entry) / max(1.0, abs(pivot_entry - stop_loss)), 2)

                patterns.append({
                    "name": "Cup and Handle",
                    "category": "Continuation / Accumulation",
                    "type": "High-Conviction Bullish",
                    "direction": "Bullish",
                    "quality_score": min(98, score),
                    "significance": "High",
                    "confidence": "High",
                    "status": status,
                    "entry_trigger": pivot_entry,
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": rr,
                    "description": (
                        f"O'Neil Cup formed over {cup_bars} bars (depth: {cup_depth*100:.1f}%), Handle over {handle_bars} bars. "
                        f"Pivot entry: Rs.{pivot_entry} ({status}). "
                        f"Target: Rs.{target} (Stop: Rs.{stop_loss}, R:R: {rr})."
                    ),
                    "key_levels": {
                        "cup_rim": pivot_entry,
                        "cup_low": round(float(cup_trough["price"]), 2),
                        "handle_low": stop_loss,
                        "target": target
                    },
                    "metrics": {
                        "cup_depth_pct": round(cup_depth * 100, 1),
                        "handle_bars": handle_bars,
                        "pivot": pivot_entry,
                        "target": target
                    }
                })
                break

        return patterns

    # =========================================================================
    # Pattern 3: Saucer Pattern (Rounding Bottom / Accumulation Bowl)
    # =========================================================================
    @classmethod
    def detect_saucer_pattern(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 35:
            return patterns

        closes = df['CLOSE_PRICE'].values
        volumes = df['VOLUME'].values if 'VOLUME' in df else np.ones(len(df))
        n = len(closes)
        curr_close = float(closes[-1])

        for lookback in [55, 40, 75]:
            if lookback <= n:
                sub_close = closes[-lookback:]
                sub_vol = volumes[-lookback:]
                x = np.arange(lookback)
                x_norm = x / float(lookback - 1)
                y_min, y_max = np.min(sub_close), np.max(sub_close)

                if y_max - y_min > 0:
                    y_norm = (sub_close - y_min) / (y_max - y_min)
                    poly = np.polyfit(x_norm, y_norm, 2)
                    a, b, c = poly

                    if a >= 0.85:
                        vertex_x = -b / (2.0 * a)
                        if 0.25 <= vertex_x <= 0.75:
                            residuals = y_norm - (a * x_norm**2 + b * x_norm + c)
                            ss_res = np.sum(residuals**2)
                            ss_tot = np.sum((y_norm - np.mean(y_norm))**2)
                            r2 = 1.0 - (ss_res / (ss_tot + 1e-9))

                            trough_idx = int(vertex_x * (lookback - 1))
                            trough_val = float(sub_close[trough_idx])
                            left_rim = float(sub_close[0])

                            if r2 >= 0.55 and curr_close > trough_val * 1.01:
                                bowl_depth = max(left_rim, curr_close) - trough_val
                                target = round(float(curr_close + bowl_depth * 0.85), 2)
                                stop_loss = round(float(trough_val + bowl_depth * 0.25), 2)
                                pivot_rim = round(float(left_rim), 2)
                                # If left_rim is far away (>15%), entry trigger is recent local breakout level
                                if abs(curr_close - pivot_rim) / curr_close > 0.15:
                                    pivot_rim = round(float(curr_close * 1.02), 2)
                                is_breakout = curr_close >= pivot_rim

                                # Bullish target sanity
                                if target <= curr_close:
                                    target = round(float(curr_close + (curr_close - stop_loss) * 1.8), 2)

                                mid_third_start, mid_third_end = int(lookback * 0.33), int(lookback * 0.67)
                                center_vol = np.mean(sub_vol[mid_third_start:mid_third_end])
                                outer_vol = (np.mean(sub_vol[:mid_third_start]) + np.mean(sub_vol[mid_third_end:])) / 2.0
                                vol_bowl = center_vol < outer_vol

                                score = 75
                                if r2 >= 0.70: score += 10
                                if vol_bowl: score += 10
                                if is_breakout: score += 5

                                status = "Confirmed Rim Breakout" if is_breakout else "Rounding Accumulation Base"
                                rr = round(abs(target - curr_close) / max(1.0, abs(curr_close - stop_loss)), 2)

                                patterns.append({
                                    "name": "Saucer Pattern (Rounding Bottom)",
                                    "category": "Accumulation",
                                    "type": "Bullish Reversal",
                                    "direction": "Bullish",
                                    "quality_score": min(98, score),
                                    "significance": "High",
                                    "confidence": "High" if r2 >= 0.65 else "Medium",
                                    "status": status,
                                    "entry_trigger": pivot_rim,
                                    "target_price": target,
                                    "stop_loss": stop_loss,
                                    "risk_reward_ratio": rr,
                                    "description": (
                                        f"Mathematical Saucer curvature across {lookback} sessions (R²={r2:.2f}, Curvature={a:.2f}). "
                                        f"Trough support at Rs.{trough_val:.2f}, Rim at Rs.{pivot_rim:.2f} ({status}). "
                                        f"Upside target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f}, R:R: {rr})."
                                    ),
                                    "key_levels": {
                                        "saucer_trough": round(trough_val, 2),
                                        "rim_resistance": pivot_rim,
                                        "target": target,
                                        "stop_loss": stop_loss
                                    },
                                    "metrics": {
                                        "r2": round(float(r2), 2),
                                        "saucer_trough": round(float(trough_val), 2),
                                        "target": round(float(target), 2),
                                        "sessions": lookback
                                    }
                                })
                                break

        return patterns

    # =========================================================================
    # Pattern 4: John Carter's TTM Squeeze (Bollinger Inside Keltner)
    # =========================================================================
    @classmethod
    def detect_ttm_squeeze(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 25 or 'IN_SQUEEZE' not in df:
            return patterns

        in_squeeze = df['IN_SQUEEZE'].values
        momentum = df['TTM_MOMENTUM'].values
        closes = df['CLOSE_PRICE'].values
        atr = df['ATR_20'].values
        curr_close = float(closes[-1])
        curr_atr = float(atr[-1])

        squeeze_len = 0
        for val in reversed(in_squeeze):
            if val: squeeze_len += 1
            else: break

        is_currently_squeezed = in_squeeze[-1]
        just_fired = (not in_squeeze[-1]) and in_squeeze[-2] if len(in_squeeze) > 1 else False
        mom_val = float(momentum[-1])

        if is_currently_squeezed and squeeze_len >= 4:
            direction = "Bullish" if mom_val > 0 else "Bearish" if mom_val < 0 else "Neutral"
            target = round(float(curr_close + (curr_atr * 2.2 if mom_val >= 0 else -curr_atr * 2.2)), 2)
            stop_loss = round(float(curr_close - (curr_atr * 1.1 if mom_val >= 0 else -curr_atr * 1.1)), 2)
            score = 80 + min(15, squeeze_len * 2)

            patterns.append({
                "name": "TTM Bollinger Squeeze",
                "category": "Volatility Breakout",
                "type": f"{direction} Energy Compression",
                "direction": direction,
                "quality_score": min(98, score),
                "significance": "High",
                "confidence": "High",
                "status": f"Compressed ({squeeze_len} bars in squeeze)",
                "entry_trigger": round(curr_close, 2),
                "target_price": target,
                "stop_loss": stop_loss,
                "risk_reward_ratio": 2.0,
                "description": (
                    f"Institutional TTM Squeeze active for {squeeze_len} consecutive bars (Bollinger inside Keltner). "
                    f"Momentum: {'+Positive (Bullish bias)' if mom_val >= 0 else '-Negative (Bearish bias)'}. "
                    f"Explosive directional expansion target: Rs.{target} (Stop: Rs.{stop_loss})."
                ),
                "key_levels": {
                    "squeeze_bars": squeeze_len,
                    "target": target,
                    "stop_loss": stop_loss
                },
                "metrics": {
                    "squeeze_bars": squeeze_len,
                    "momentum": round(mom_val, 3),
                    "target": target
                }
            })
        elif just_fired:
            direction = "Bullish" if mom_val >= 0 else "Bearish"
            target = round(float(curr_close + (curr_atr * 2.5 if mom_val >= 0 else -curr_atr * 2.5)), 2)
            stop_loss = round(float(curr_close - (curr_atr * 1.2 if mom_val >= 0 else -curr_atr * 1.2)), 2)

            patterns.append({
                "name": "TTM Squeeze Fired (Breakout)",
                "category": "Volatility Breakout",
                "type": f"Active {direction} Expansion",
                "direction": direction,
                "quality_score": 92,
                "significance": "High",
                "confidence": "High",
                "status": "Breakout Fired",
                "entry_trigger": round(curr_close, 2),
                "target_price": target,
                "stop_loss": stop_loss,
                "risk_reward_ratio": 2.1,
                "description": (
                    f"TTM Squeeze has FIRED with {direction} momentum. "
                    f"Volatility expansion in progress with upside target Rs.{target} (Stop: Rs.{stop_loss})."
                ),
                "key_levels": {"target": target, "stop_loss": stop_loss},
                "metrics": {"momentum": round(mom_val, 3), "target": target}
            })

        return patterns

    # =========================================================================
    # Pattern 5: Triangles (Ascending, Descending & Symmetrical)
    # =========================================================================
    @classmethod
    def detect_triangles(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 5 or len(df) < 30:
            return patterns

        curr_close = float(df['CLOSE_PRICE'].iloc[-1])
        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]

        # Ascending Triangle: Flat Resistance + Rising Lows
        if len(peaks) >= 2 and len(troughs) >= 2:
            p1, p2 = peaks[-2], peaks[-1]
            t1, t2 = troughs[-2], troughs[-1]

            peak_diff = abs(p1["price"] - p2["price"]) / p1["price"]
            if peak_diff <= 0.018 and t2["price"] > t1["price"] * 1.015:
                resistance = (p1["price"] + p2["price"]) / 2.0
                height = resistance - t1["price"]
                target = round(float(resistance + height), 2)
                stop_loss = round(float(t2["price"]), 2)
                is_breakout = curr_close >= resistance

                patterns.append({
                    "name": "Ascending Triangle",
                    "category": "Continuation / Breakout",
                    "type": "Bullish Breakout",
                    "direction": "Bullish",
                    "quality_score": 86,
                    "significance": "High",
                    "confidence": "High" if is_breakout else "Medium",
                    "status": "Confirmed Breakout" if is_breakout else "Consolidating Against Resistance",
                    "entry_trigger": round(float(resistance), 2),
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": round(abs(target - resistance) / max(1.0, abs(resistance - stop_loss)), 2),
                    "description": (
                        f"Flat resistance at Rs.{resistance:.2f} with rising higher lows (L1: Rs.{t1['price']:.2f} -> L2: Rs.{t2['price']:.2f}). "
                        f"Breakout target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f})."
                    ),
                    "key_levels": {"resistance": round(float(resistance), 2), "support": stop_loss, "target": target},
                    "metrics": {"resistance": round(float(resistance), 2), "support": stop_loss, "target": target}
                })

            # Descending Triangle: Flat Support + Lower Highs
            trough_diff = abs(t1["price"] - t2["price"]) / t1["price"]
            if trough_diff <= 0.018 and p2["price"] < p1["price"] * 0.985:
                support = (t1["price"] + t2["price"]) / 2.0
                height = p1["price"] - support
                target = round(float(support - height), 2)
                stop_loss = round(float(p2["price"]), 2)
                is_breakdown = curr_close <= support

                patterns.append({
                    "name": "Descending Triangle",
                    "category": "Breakdown",
                    "type": "Bearish Breakdown",
                    "direction": "Bearish",
                    "quality_score": 84,
                    "significance": "High",
                    "confidence": "High" if is_breakdown else "Medium",
                    "status": "Confirmed Breakdown" if is_breakdown else "Testing Horizontal Support",
                    "entry_trigger": round(float(support), 2),
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": round(abs(support - target) / max(1.0, abs(stop_loss - support)), 2),
                    "description": (
                        f"Horizontal support at Rs.{support:.2f} with lower highs (H1: Rs.{p1['price']:.2f} -> H2: Rs.{p2['price']:.2f}). "
                        f"Breakdown target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f})."
                    ),
                    "key_levels": {"support": round(float(support), 2), "resistance": stop_loss, "target": target},
                    "metrics": {"support": round(float(support), 2), "resistance": stop_loss, "target": target}
                })

        return patterns

    # =========================================================================
    # Pattern 6: Double Bottom (W) & Double Top (M)
    # =========================================================================
    @classmethod
    def detect_double_patterns(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 3 or len(df) < 25:
            return patterns

        curr_close = float(df['CLOSE_PRICE'].iloc[-1])
        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]

        # Double Bottom (W-Pattern)
        if len(troughs) >= 2:
            t1, t2 = troughs[-2], troughs[-1]
            # Must be recent (second trough formed within last 40 bars)
            if (len(df) - 1 - t2["idx"]) <= 40:
                diff = abs(t1["price"] - t2["price"]) / t1["price"]
                if diff <= 0.028 and (t2["idx"] - t1["idx"]) >= 8:
                    mid_peaks = [p for p in peaks if t1["idx"] < p["idx"] < t2["idx"]]
                    if mid_peaks:
                        neckline = mid_peaks[0]["price"]
                        depth = neckline - min(t1["price"], t2["price"])
                        target = round(float(neckline + depth), 2)
                        stop_loss = round(float(min(t1["price"], t2["price"]) * 0.99), 2)
                        is_breakout = curr_close >= neckline

                        # Target must be above current price, and current close cannot be > 10% past target
                        if target > curr_close and curr_close <= target * 1.10 and abs(curr_close - neckline) / curr_close <= 0.15:
                            patterns.append({
                                "name": "Double Bottom (W-Pattern)",
                                "category": "Reversal",
                                "type": "Bullish Reversal",
                                "direction": "Bullish",
                                "quality_score": 85,
                                "significance": "High",
                                "confidence": "High" if is_breakout else "Medium",
                                "status": "Confirmed Neckline Breakout" if is_breakout else "Formed / Approaching Neckline",
                                "entry_trigger": round(float(neckline), 2),
                                "target_price": target,
                                "stop_loss": stop_loss,
                                "risk_reward_ratio": round(abs(target - neckline) / max(1.0, abs(neckline - stop_loss)), 2),
                                "description": (
                                    f"Double bottom support established at Rs.{t1['price']:.2f}. "
                                    f"Neckline pivot at Rs.{neckline:.2f} ({'Breakout Confirmed' if is_breakout else 'Testing'}). "
                                    f"Target: Rs.{target} (Stop: Rs.{stop_loss})."
                                ),
                                "key_levels": {"support": round(float(t1["price"]), 2), "neckline": round(float(neckline), 2), "target": target},
                                "metrics": {"support": round(float(t1["price"]), 2), "neckline": round(float(neckline), 2), "target": target}
                            })

        # Double Top (M-Pattern)
        if len(peaks) >= 2:
            p1, p2 = peaks[-2], peaks[-1]
            # Must be recent (second peak formed within last 40 bars)
            if (len(df) - 1 - p2["idx"]) <= 40:
                diff = abs(p1["price"] - p2["price"]) / p1["price"]
                if diff <= 0.028 and (p2["idx"] - p1["idx"]) >= 8:
                    mid_troughs = [t for t in troughs if p1["idx"] < t["idx"] < p2["idx"]]
                    if mid_troughs:
                        neckline = mid_troughs[0]["price"]
                        depth = max(p1["price"], p2["price"]) - neckline
                        target = round(float(neckline - depth), 2)
                        stop_loss = round(float(max(p1["price"], p2["price"]) * 1.01), 2)
                        is_breakdown = curr_close <= neckline

                        # Downside target must be below current price
                        if target < curr_close and curr_close >= target * 0.90 and abs(curr_close - neckline) / curr_close <= 0.15:
                            patterns.append({
                                "name": "Double Top (M-Pattern)",
                        "category": "Reversal",
                        "type": "Bearish Reversal",
                        "direction": "Bearish",
                        "quality_score": 85,
                        "significance": "High",
                        "confidence": "High" if is_breakdown else "Medium",
                        "status": "Confirmed Breakdown" if is_breakdown else "Testing Neckline Support",
                        "entry_trigger": round(float(neckline), 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(neckline - target) / max(1.0, abs(stop_loss - neckline)), 2),
                        "description": (
                            f"Double top resistance confirmed near Rs.{p1['price']:.2f}. "
                            f"Neckline support at Rs.{neckline:.2f} ({'Breakdown Confirmed' if is_breakdown else 'Testing'}). "
                            f"Downside target: Rs.{target} (Stop: Rs.{stop_loss})."
                        ),
                        "key_levels": {"resistance": round(float(p1["price"]), 2), "neckline": round(float(neckline), 2), "target": target},
                        "metrics": {"resistance": round(float(p1["price"]), 2), "neckline": round(float(neckline), 2), "target": target}
                    })

        return patterns

    # =========================================================================
    # Pattern 7: Harmonic Patterns (Bullish & Bearish Gartley & Bat)
    # =========================================================================
    @classmethod
    def detect_harmonic_patterns(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 5:
            return patterns

        last_5 = swings[-5:]
        curr_close = float(df['CLOSE_PRICE'].iloc[-1])

        # 1. Bullish Gartley / Bat: X(low) -> A(high) -> B(low) -> C(high) -> D(low)
        if last_5[0]["type"] == "low" and last_5[1]["type"] == "high" and last_5[2]["type"] == "low" and last_5[3]["type"] == "high" and last_5[4]["type"] == "low":
            X, A, B, C, D = [s["price"] for s in last_5]
            XA = A - X
            if XA > 0:
                ab_retrace = (A - B) / XA
                cd_retrace = (A - D) / XA

                if 0.55 <= ab_retrace <= 0.68 and 0.73 <= cd_retrace <= 0.84:
                    target = round(float(D + (C - D) * 0.618), 2)
                    stop_loss = round(float(X * 0.99), 2)
                    patterns.append({
                        "name": "Bullish Gartley (Harmonic 0.786)",
                        "category": "Harmonic Reversal",
                        "type": "Precision Bullish Turning Point",
                        "direction": "Bullish",
                        "quality_score": 90,
                        "significance": "High",
                        "confidence": "High",
                        "status": "In Potential Reversal Zone (PRZ)",
                        "entry_trigger": round(float(D), 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(target - D) / max(1.0, abs(D - stop_loss)), 2),
                        "description": (
                            f"Institutional Harmonic Gartley pattern completed at point D (Rs.{D:.2f}). "
                            f"Fibonacci B=0.618, D=0.786. Target (0.618 CD extension): Rs.{target} (Stop: Rs.{stop_loss})."
                        ),
                        "key_levels": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target},
                        "metrics": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target}
                    })

                elif 0.35 <= ab_retrace <= 0.54 and 0.84 <= cd_retrace <= 0.93:
                    target = round(float(D + (C - D) * 0.618), 2)
                    stop_loss = round(float(X * 0.99), 2)
                    patterns.append({
                        "name": "Bullish Bat (Harmonic 0.886)",
                        "category": "Harmonic Reversal",
                        "type": "Precision Bullish Turning Point",
                        "direction": "Bullish",
                        "quality_score": 91,
                        "significance": "High",
                        "confidence": "High",
                        "status": "In Potential Reversal Zone (PRZ)",
                        "entry_trigger": round(float(D), 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(target - D) / max(1.0, abs(D - stop_loss)), 2),
                        "description": (
                            f"Institutional Harmonic Bat pattern completed at point D (Rs.{D:.2f}). "
                            f"Fibonacci D=0.886 PRZ. Target: Rs.{target} (Stop: Rs.{stop_loss})."
                        ),
                        "key_levels": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target},
                        "metrics": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target}
                    })

        # 2. Bearish Gartley / Bat: X(high) -> A(low) -> B(high) -> C(low) -> D(high)
        if last_5[0]["type"] == "high" and last_5[1]["type"] == "low" and last_5[2]["type"] == "high" and last_5[3]["type"] == "low" and last_5[4]["type"] == "high":
            X, A, B, C, D = [s["price"] for s in last_5]
            XA = X - A
            if XA > 0:
                ab_retrace = (B - A) / XA
                cd_retrace = (D - A) / XA

                if 0.55 <= ab_retrace <= 0.68 and 0.73 <= cd_retrace <= 0.84:
                    target = round(float(D - (D - C) * 0.618), 2)
                    stop_loss = round(float(X * 1.01), 2)
                    patterns.append({
                        "name": "Bearish Gartley (Harmonic 0.786)",
                        "category": "Harmonic Reversal",
                        "type": "Precision Bearish Turning Point",
                        "direction": "Bearish",
                        "quality_score": 89,
                        "significance": "High",
                        "confidence": "High",
                        "status": "In Potential Reversal Zone (PRZ)",
                        "entry_trigger": round(float(D), 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(D - target) / max(1.0, abs(stop_loss - D)), 2),
                        "description": (
                            f"Bearish Harmonic Gartley completed at point D (Rs.{D:.2f}). "
                            f"Fibonacci B=0.618, D=0.786 PRZ. Downside target: Rs.{target} (Stop: Rs.{stop_loss})."
                        ),
                        "key_levels": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target},
                        "metrics": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target}
                    })

                elif 0.35 <= ab_retrace <= 0.54 and 0.84 <= cd_retrace <= 0.93:
                    target = round(float(D - (D - C) * 0.618), 2)
                    stop_loss = round(float(X * 1.01), 2)
                    patterns.append({
                        "name": "Bearish Bat (Harmonic 0.886)",
                        "category": "Harmonic Reversal",
                        "type": "Precision Bearish Turning Point",
                        "direction": "Bearish",
                        "quality_score": 90,
                        "significance": "High",
                        "confidence": "High",
                        "status": "In Potential Reversal Zone (PRZ)",
                        "entry_trigger": round(float(D), 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(D - target) / max(1.0, abs(stop_loss - D)), 2),
                        "description": (
                            f"Bearish Harmonic Bat completed at point D (Rs.{D:.2f}). "
                            f"Fibonacci D=0.886 PRZ. Downside target: Rs.{target} (Stop: Rs.{stop_loss})."
                        ),
                        "key_levels": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target},
                        "metrics": {"point_X": round(X, 2), "point_D": round(D, 2), "target": target}
                    })

        return patterns

    # =========================================================================
    # Pattern 8: Bull Flag & Bear Flag (High-Tight Impulse + Channel Consolidation)
    # =========================================================================
    @classmethod
    def detect_flag_pennant_patterns(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 25:
            return patterns

        closes = df['CLOSE_PRICE'].values
        highs = df['HIGH_PRICE'].values
        lows = df['LOW_PRICE'].values
        volumes = df['VOLUME'].values if 'VOLUME' in df else np.ones(len(df))
        n = len(closes)
        curr_close = float(closes[-1])

        # Flag duration: 4 to 12 bars; Pole duration: 5 to 15 bars preceding flag
        for flag_len in [5, 8, 12]:
            if n < flag_len + 10:
                continue

            flag_start_idx = n - flag_len
            flag_highs = highs[flag_start_idx:]
            flag_lows = lows[flag_start_idx:]
            flag_volumes = volumes[flag_start_idx:]

            pole_lookback = min(15, flag_start_idx)
            pole_start_idx = flag_start_idx - pole_lookback
            pole_closes = closes[pole_start_idx:flag_start_idx]
            pole_volumes = volumes[pole_start_idx:flag_start_idx]

            pole_change = (closes[flag_start_idx - 1] - pole_closes[0]) / pole_closes[0]
            avg_pole_vol = np.mean(pole_volumes) if len(pole_volumes) > 0 else 1.0
            avg_flag_vol = np.mean(flag_volumes) if len(flag_volumes) > 0 else 1.0

            # 1. Bull Flag: Strong upward pole (+7% to +30%) followed by slight downward channel with lower volume
            if pole_change >= 0.07:
                pole_height = closes[flag_start_idx - 1] - pole_closes[0]
                flag_top = float(np.max(flag_highs))
                flag_bottom = float(np.min(flag_lows))
                flag_retrace = (flag_top - flag_bottom) / pole_height

                # Flag shouldn't retrace more than 40% of the pole
                if flag_retrace <= 0.42 and avg_flag_vol < avg_pole_vol * 0.95:
                    target = round(float(flag_top + pole_height * 0.90), 2)
                    stop_loss = round(float(flag_bottom * 0.995), 2)
                    is_breakout = curr_close >= flag_top

                    patterns.append({
                        "name": "Bull Flag Continuation",
                        "category": "Momentum Continuation",
                        "type": "High-Conviction Bullish",
                        "direction": "Bullish",
                        "quality_score": 88 if is_breakout else 82,
                        "significance": "High",
                        "confidence": "High" if is_breakout else "Medium",
                        "status": "Breakout Confirmed" if is_breakout else f"Coiling in Flag ({flag_len} bars)",
                        "entry_trigger": round(flag_top, 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(target - flag_top) / max(1.0, abs(flag_top - stop_loss)), 2),
                        "description": (
                            f"Bull flag formed after +{pole_change*100:.1f}% impulse pole. "
                            f"Orderly {flag_len}-bar consolidation on reduced volume. "
                            f"Continuation target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f})."
                        ),
                        "key_levels": {"flag_top": round(flag_top, 2), "flag_bottom": round(flag_bottom, 2), "target": target},
                        "metrics": {"pole_gain_pct": round(pole_change * 100, 1), "flag_bars": flag_len, "target": target}
                    })
                    break

            # 2. Bear Flag: Sharp downward pole (-7% to -30%) followed by slight upward drift on low volume
            elif pole_change <= -0.07:
                pole_height = pole_closes[0] - closes[flag_start_idx - 1]
                flag_top = float(np.max(flag_highs))
                flag_bottom = float(np.min(flag_lows))
                flag_retrace = (flag_top - flag_bottom) / pole_height

                if flag_retrace <= 0.42 and avg_flag_vol < avg_pole_vol * 0.95:
                    target = round(float(flag_bottom - pole_height * 0.90), 2)
                    stop_loss = round(float(flag_top * 1.005), 2)
                    is_breakdown = curr_close <= flag_bottom

                    patterns.append({
                        "name": "Bear Flag Breakdown",
                        "category": "Momentum Continuation",
                        "type": "High-Conviction Bearish",
                        "direction": "Bearish",
                        "quality_score": 87 if is_breakdown else 81,
                        "significance": "High",
                        "confidence": "High" if is_breakdown else "Medium",
                        "status": "Breakdown Confirmed" if is_breakdown else f"Consolidating in Bear Flag ({flag_len} bars)",
                        "entry_trigger": round(flag_bottom, 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(flag_bottom - target) / max(1.0, abs(stop_loss - flag_bottom)), 2),
                        "description": (
                            f"Bear flag following {pole_change*100:.1f}% downward impulse pole. "
                            f"Flag consolidation over {flag_len} bars. Breakdown target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f})."
                        ),
                        "key_levels": {"flag_top": round(flag_top, 2), "flag_bottom": round(flag_bottom, 2), "target": target},
                        "metrics": {"pole_loss_pct": round(pole_change * 100, 1), "flag_bars": flag_len, "target": target}
                    })
                    break

        return patterns

    # =========================================================================
    # Pattern 9: Wyckoff Accumulation Phase C Spring & Upthrust (UTAD)
    # =========================================================================
    @classmethod
    def detect_wyckoff_spring(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 35:
            return patterns

        lows = df['LOW_PRICE'].values
        highs = df['HIGH_PRICE'].values
        closes = df['CLOSE_PRICE'].values
        volumes = df['VOLUME'].values if 'VOLUME' in df else np.ones(len(df))
        curr_close = float(closes[-1])
        n = len(closes)

        # Baseline Trading Range: lookback 30 to 60 bars (excluding last 3 bars)
        tr_lows = lows[-35:-3]
        tr_highs = highs[-35:-3]
        tr_support = float(np.percentile(tr_lows, 10))
        tr_resistance = float(np.percentile(tr_highs, 90))

        # Range must be meaningful (> 5%)
        if (tr_resistance - tr_support) / tr_support < 0.05:
            return patterns

        # 1. Wyckoff Spring: Within last 3 bars, low dipped below TR support by 0.5% - 4%, but price snapped back inside
        recent_min = float(np.min(lows[-3:]))
        if recent_min < tr_support and (tr_support - recent_min) / tr_support <= 0.045:
            if curr_close > tr_support:
                spring_vol = np.mean(volumes[-3:])
                baseline_vol = np.mean(volumes[-35:-3])
                vol_divergence = spring_vol < baseline_vol * 1.15  # Low volume indicates lack of institutional supply (bear trap)

                target = round(float(tr_resistance), 2)
                stop_loss = round(float(recent_min * 0.99), 2)
                rr = round(abs(target - curr_close) / max(1.0, abs(curr_close - stop_loss)), 2)

                patterns.append({
                    "name": "Wyckoff Accumulation Spring (Phase C)",
                    "category": "Institutional Order Flow",
                    "type": "High-Probability Bear Trap",
                    "direction": "Bullish",
                    "quality_score": 93 if vol_divergence else 86,
                    "significance": "High",
                    "confidence": "High",
                    "status": "Confirmed Spring & Recovery",
                    "entry_trigger": round(curr_close, 2),
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": rr,
                    "description": (
                        f"Wyckoff Phase C 'Spring' detected. False breakdown below trading range support (Rs.{tr_support:.2f}) "
                        f"to Rs.{recent_min:.2f} rapidly reclaimed. Supply absorption confirmed. "
                        f"Targeting upper TR boundary at Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f}, R:R: {rr})."
                    ),
                    "key_levels": {
                        "range_support": round(tr_support, 2),
                        "spring_low": round(recent_min, 2),
                        "range_resistance": target
                    },
                    "metrics": {
                        "range_support": round(tr_support, 2),
                        "spring_low": round(recent_min, 2),
                        "target": target,
                        "stop_loss": stop_loss
                    }
                })

        # 2. Wyckoff Upthrust (UTAD - Phase C Distribution): False breakout above TR resistance, price snaps back inside
        recent_max = float(np.max(highs[-3:]))
        if recent_max > tr_resistance and (recent_max - tr_resistance) / tr_resistance <= 0.045:
            if curr_close < tr_resistance:
                target = round(float(tr_support), 2)
                stop_loss = round(float(recent_max * 1.01), 2)
                rr = round(abs(curr_close - target) / max(1.0, abs(stop_loss - curr_close)), 2)

                patterns.append({
                    "name": "Wyckoff Upthrust After Distribution (UTAD)",
                    "category": "Institutional Order Flow",
                    "type": "High-Probability Bull Trap",
                    "direction": "Bearish",
                    "quality_score": 91,
                    "significance": "High",
                    "confidence": "High",
                    "status": "Confirmed Upthrust Failure",
                    "entry_trigger": round(curr_close, 2),
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": rr,
                    "description": (
                        f"Wyckoff UTAD detected. Failed breakout above range resistance (Rs.{tr_resistance:.2f}) "
                        f"peaked at Rs.{recent_max:.2f} and fell back inside range. Bull trap complete. "
                        f"Targeting lower TR support at Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f}, R:R: {rr})."
                    ),
                    "key_levels": {
                        "range_resistance": round(tr_resistance, 2),
                        "upthrust_high": round(recent_max, 2),
                        "range_support": target
                    },
                    "metrics": {
                        "range_resistance": round(tr_resistance, 2),
                        "upthrust_high": round(recent_max, 2),
                        "target": target,
                        "stop_loss": stop_loss
                    }
                })

        return patterns

    # =========================================================================
    # Pattern 10: Multi-Pivot Quantitative RSI Divergence
    # =========================================================================
    @classmethod
    def detect_rsi_divergence(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 4 or 'RSI_14' not in df:
            return patterns

        curr_close = float(df['CLOSE_PRICE'].iloc[-1])
        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]

        # 1. Regular Bullish Divergence: Lower Low in Price, but Higher Low in RSI
        if len(troughs) >= 2:
            t1, t2 = troughs[-2], troughs[-1]
            if t2["price"] < t1["price"] * 0.99:
                rsi1 = t1.get("rsi", 50.0)
                rsi2 = t2.get("rsi", 50.0)
                if rsi2 > rsi1 + 2.5 and rsi2 <= 48.0:
                    atr = float(df['ATR_14'].iloc[-1]) if 'ATR_14' in df else curr_close * 0.02
                    target = round(float(curr_close + (atr * 2.8)), 2)
                    stop_loss = round(float(t2["price"] * 0.99), 2)
                    rr = round(abs(target - curr_close) / max(1.0, abs(curr_close - stop_loss)), 2)

                    patterns.append({
                        "name": "Bullish RSI Momentum Divergence",
                        "category": "Momentum Divergence",
                        "type": "High-Conviction Reversal",
                        "direction": "Bullish",
                        "quality_score": 88,
                        "significance": "High",
                        "confidence": "High",
                        "status": "Divergence Established",
                        "entry_trigger": round(curr_close, 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": rr,
                        "description": (
                            f"Quantitative Bullish Divergence: Price printed lower low (Rs.{t1['price']:.2f} -> Rs.{t2['price']:.2f}) "
                            f"while RSI printed higher low ({rsi1:.1f} -> {rsi2:.1f}). Downward selling momentum exhausted. "
                            f"Target: Rs.{target} (Stop: Rs.{stop_loss}, R:R: {rr})."
                        ),
                        "key_levels": {"swing_low_1": round(t1["price"], 2), "swing_low_2": round(t2["price"], 2), "target": target},
                        "metrics": {"price_l1": round(t1["price"], 2), "price_l2": round(t2["price"], 2), "rsi_l1": round(rsi1, 1), "rsi_l2": round(rsi2, 1)}
                    })

        # 2. Regular Bearish Divergence: Higher High in Price, but Lower High in RSI
        if len(peaks) >= 2:
            p1, p2 = peaks[-2], peaks[-1]
            if p2["price"] > p1["price"] * 1.01:
                rsi1 = p1.get("rsi", 50.0)
                rsi2 = p2.get("rsi", 50.0)
                if rsi2 < rsi1 - 2.5 and rsi2 >= 55.0:
                    atr = float(df['ATR_14'].iloc[-1]) if 'ATR_14' in df else curr_close * 0.02
                    target = round(float(curr_close - (atr * 2.8)), 2)
                    stop_loss = round(float(p2["price"] * 1.01), 2)
                    rr = round(abs(curr_close - target) / max(1.0, abs(stop_loss - curr_close)), 2)

                    patterns.append({
                        "name": "Bearish RSI Momentum Divergence",
                        "category": "Momentum Divergence",
                        "type": "Exhaustion Bearish Reversal",
                        "direction": "Bearish",
                        "quality_score": 87,
                        "significance": "High",
                        "confidence": "High",
                        "status": "Divergence Established",
                        "entry_trigger": round(curr_close, 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": rr,
                        "description": (
                            f"Quantitative Bearish Divergence: Price printed higher high (Rs.{p1['price']:.2f} -> Rs.{p2['price']:.2f}) "
                            f"while RSI printed lower high ({rsi1:.1f} -> {rsi2:.1f}). Buying thrust failing. "
                            f"Downside target: Rs.{target} (Stop: Rs.{stop_loss}, R:R: {rr})."
                        ),
                        "key_levels": {"swing_high_1": round(p1["price"], 2), "swing_high_2": round(p2["price"], 2), "target": target},
                        "metrics": {"price_h1": round(p1["price"], 2), "price_h2": round(p2["price"], 2), "rsi_h1": round(rsi1, 1), "rsi_h2": round(rsi2, 1)}
                    })

        return patterns

    # =========================================================================
    # Pattern 11: Candlestick Multi-Bar Formations (Morning/Evening Star & Engulfing)
    # =========================================================================
    @classmethod
    def detect_candlestick_patterns(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 5:
            return patterns

        c0 = df.iloc[-1]
        c1 = df.iloc[-2]
        c2 = df.iloc[-3]

        vol_avg = df['VOLUME'].tail(20).mean() if 'VOLUME' in df else 1.0
        c0_vol = c0.get('VOLUME', 0)
        high_vol = c0_vol > vol_avg * 1.25

        c2_is_bear = c2['CLOSE_PRICE'] < c2['OPEN_PRICE']
        c2_is_bull = c2['CLOSE_PRICE'] > c2['OPEN_PRICE']
        c2_body = abs(c2['CLOSE_PRICE'] - c2['OPEN_PRICE'])
        c1_body = abs(c1['CLOSE_PRICE'] - c1['OPEN_PRICE'])
        c0_is_bull = c0['CLOSE_PRICE'] > c0['OPEN_PRICE']
        c0_is_bear = c0['CLOSE_PRICE'] < c0['OPEN_PRICE']
        c2_mid = (c2['OPEN_PRICE'] + c2['CLOSE_PRICE']) / 2.0

        # 1. Bullish Morning Star (3-candle high-conviction bottom reversal)
        if c2_is_bear and (c1_body < c2_body * 0.4) and c0_is_bull and (c0['CLOSE_PRICE'] > c2_mid):
            patterns.append({
                "name": "Morning Star Reversal",
                "category": "Candlestick",
                "type": "Bullish 3-Bar Reversal",
                "direction": "Bullish",
                "quality_score": 87 if high_vol else 80,
                "significance": "High",
                "confidence": "High",
                "status": "Confirmed",
                "entry_trigger": round(float(c0['CLOSE_PRICE']), 2),
                "target_price": round(float(c0['CLOSE_PRICE'] + c2_body * 1.5), 2),
                "stop_loss": round(float(min(c1['LOW_PRICE'], c0['LOW_PRICE'])), 2),
                "risk_reward_ratio": 1.8,
                "description": f"Morning Star bottom reversal confirmed with {'high volume expansion' if high_vol else 'penetration above prior bar midpoint'}.",
                "key_levels": {"stop_loss": round(float(min(c1['LOW_PRICE'], c0['LOW_PRICE'])), 2)},
                "metrics": {"pattern": "Morning Star", "volume_surge": high_vol}
            })

        # 2. Bearish Evening Star (3-candle top reversal)
        elif c2_is_bull and (c1_body < c2_body * 0.4) and c0_is_bear and (c0['CLOSE_PRICE'] < c2_mid):
            patterns.append({
                "name": "Evening Star Reversal",
                "category": "Candlestick",
                "type": "Bearish 3-Bar Reversal",
                "direction": "Bearish",
                "quality_score": 87 if high_vol else 80,
                "significance": "High",
                "confidence": "High",
                "status": "Confirmed",
                "entry_trigger": round(float(c0['CLOSE_PRICE']), 2),
                "target_price": round(float(c0['CLOSE_PRICE'] - c2_body * 1.5), 2),
                "stop_loss": round(float(max(c1['HIGH_PRICE'], c0['HIGH_PRICE'])), 2),
                "risk_reward_ratio": 1.8,
                "description": f"Evening Star top reversal confirmed with {'high volume distribution' if high_vol else 'close below prior bar midpoint'}.",
                "key_levels": {"stop_loss": round(float(max(c1['HIGH_PRICE'], c0['HIGH_PRICE'])), 2)},
                "metrics": {"pattern": "Evening Star", "volume_surge": high_vol}
            })

        # 3. Bullish Engulfing with volume surge
        elif (c1['CLOSE_PRICE'] < c1['OPEN_PRICE']) and (c0['CLOSE_PRICE'] > c0['OPEN_PRICE']) and \
             (c0['OPEN_PRICE'] <= c1['CLOSE_PRICE']) and (c0['CLOSE_PRICE'] >= c1['OPEN_PRICE']) and high_vol:
            patterns.append({
                "name": "Bullish Engulfing (Volume Surge)",
                "category": "Candlestick",
                "type": "Bullish Momentum Reversal",
                "direction": "Bullish",
                "quality_score": 84,
                "significance": "High",
                "confidence": "High",
                "status": "Confirmed",
                "entry_trigger": round(float(c0['CLOSE_PRICE']), 2),
                "target_price": round(float(c0['CLOSE_PRICE'] + (c0['CLOSE_PRICE'] - c0['LOW_PRICE']) * 2.0), 2),
                "stop_loss": round(float(c0['LOW_PRICE']), 2),
                "risk_reward_ratio": 2.0,
                "description": f"Bullish Engulfing pattern backed by {c0_vol/vol_avg:.1f}x average trading volume.",
                "key_levels": {"stop_loss": round(float(c0['LOW_PRICE']), 2)},
                "metrics": {"pattern": "Bullish Engulfing", "relative_volume": round(float(c0_vol / vol_avg), 2)}
            })

        # 4. Bearish Engulfing with volume surge
        elif (c1['CLOSE_PRICE'] > c1['OPEN_PRICE']) and (c0['CLOSE_PRICE'] < c0['OPEN_PRICE']) and \
             (c0['OPEN_PRICE'] >= c1['CLOSE_PRICE']) and (c0['CLOSE_PRICE'] <= c1['OPEN_PRICE']) and high_vol:
            patterns.append({
                "name": "Bearish Engulfing (Volume Surge)",
                "category": "Candlestick",
                "type": "Bearish Momentum Reversal",
                "direction": "Bearish",
                "quality_score": 84,
                "significance": "High",
                "confidence": "High",
                "status": "Confirmed",
                "entry_trigger": round(float(c0['CLOSE_PRICE']), 2),
                "target_price": round(float(c0['CLOSE_PRICE'] - (c0['HIGH_PRICE'] - c0['CLOSE_PRICE']) * 2.0), 2),
                "stop_loss": round(float(c0['HIGH_PRICE']), 2),
                "risk_reward_ratio": 2.0,
                "description": f"Bearish Engulfing pattern accompanied by {c0_vol/vol_avg:.1f}x average trading volume.",
                "key_levels": {"stop_loss": round(float(c0['HIGH_PRICE']), 2)},
                "metrics": {"pattern": "Bearish Engulfing", "relative_volume": round(float(c0_vol / vol_avg), 2)}
            })

        return patterns

    # =========================================================================
    # Master Scanner
    # =========================================================================
    def scan_all_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """
        Executes all quantitative pattern algorithms over the OHLCV dataset.
        Returns deduplicated, sorted list by Quality Score (highest conviction first).
        """
        if df.empty or len(df) < 20:
            return []

        df_calc = self.compute_atr_and_keltner(df)
        swings = self.extract_zigzag_swings(df_calc)

        all_detected = []
        all_detected.extend(self.detect_cup_and_handle(df_calc, swings))
        all_detected.extend(self.detect_saucer_pattern(df_calc))
        all_detected.extend(self.detect_head_and_shoulders(df_calc, swings))
        all_detected.extend(self.detect_ttm_squeeze(df_calc))
        all_detected.extend(self.detect_wyckoff_spring(df_calc))
        all_detected.extend(self.detect_flag_pennant_patterns(df_calc))
        all_detected.extend(self.detect_rsi_divergence(df_calc, swings))
        all_detected.extend(self.detect_harmonic_patterns(df_calc, swings))
        all_detected.extend(self.detect_triangles(df_calc, swings))
        all_detected.extend(self.detect_double_patterns(df_calc, swings))
        all_detected.extend(self.detect_candlestick_patterns(df_calc))

        # Smart conflict resolution for directly opposing reversal patterns
        # 1. H&S vs Inverse H&S: Keep only the higher conviction pattern
        hs_patterns = [p for p in all_detected if "Head and Shoulders" in p["name"]]
        if len(hs_patterns) > 1:
            best_hs = max(hs_patterns, key=lambda x: (x.get("status", "").startswith("Confirmed"), x.get("quality_score", 0)))
            all_detected = [p for p in all_detected if ("Head and Shoulders" not in p["name"]) or (p is best_hs)]

        # 2. Double Bottom vs Double Top: Keep only the higher conviction pattern
        double_patterns = [p for p in all_detected if "Double" in p["name"]]
        if len(double_patterns) > 1:
            best_double = max(double_patterns, key=lambda x: (x.get("status", "").startswith("Confirmed"), x.get("quality_score", 0)))
            all_detected = [p for p in all_detected if ("Double" not in p["name"]) or (p is best_double)]

        # Sort by quality score descending
        all_detected.sort(key=lambda x: x.get("quality_score", 0), reverse=True)

        # Deduplicate overlapping patterns
        seen_names = set()
        deduped = []
        for p in all_detected:
            base_name = p["name"].split(" (")[0]
            if base_name not in seen_names:
                seen_names.add(base_name)
                deduped.append(p)

        return deduped
