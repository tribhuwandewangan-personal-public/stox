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

from tools.indicators import wilder_rsi, wilder_atr, wilder_adx, snap_nse_tick

HIGH_CONVICTION_PRE_BREAKOUT_PATTERNS = frozenset({
    "Darvas Box / Flat Base",
    "Double Bottom (W-Pattern)",
    "Falling Wedge (Bullish)",
    "Volatility Contraction Coil (VCP)",
    "Inverse Head and Shoulders (Forming)",
    "Saucer Pattern (Rounding Bottom)",
})


def compute_pattern_projection(
    pattern: Dict[str, Any],
    curr_close: float,
    atr_14: Optional[float] = None,
    rsi_14: Optional[float] = None,
    rvol: Optional[float] = None,
    ud_ratio: Optional[float] = None,
    ret_10d: Optional[float] = None,
    sma_50: Optional[float] = None,
    symbol: str = "",
) -> Dict[str, Any]:
    """
    Computes deterministic pre-breakout lifecycle stage, anti-chasing flags,
    actionable breakout trigger, entry timing window, and 4-week price projection.
    """
    direction = str(pattern.get("direction", "Neutral"))
    dir_l = direction.lower()
    if "bullish" not in dir_l:
        return {
            "setup_stage": "BEARISH_SETUP" if "bearish" in dir_l else "NEUTRAL_SETUP",
            "is_pre_breakout": False,
            "is_late_entry": False,
            "entry_window": "N/A",
            "breakout_trigger": pattern.get("entry_trigger"),
            "distance_to_breakout_pct": None,
            "week4_target": pattern.get("target_price"),
            "week4_target_low": None,
            "week4_upside_pct": None,
            "week4_upside_from_ltp_pct": None,
            "full_pattern_target": pattern.get("target_price"),
            "readiness_score": 0,
            "projection_summary": "",
            "forming_evidence": [],
        }

    p_name = str(pattern.get("name", "Bullish Pattern"))
    eff_atr = float(atr_14) if (atr_14 is not None and atr_14 > 0) else curr_close * 0.022
    raw_trigger = pattern.get("entry_trigger") or curr_close
    trigger = snap_nse_tick(max(0.05, float(raw_trigger)), direction="up")
    if trigger <= 0:
        trigger = snap_nse_tick(max(0.05, float(curr_close)), direction="up")

    dist_pct = round(((trigger - curr_close) / max(curr_close, 1e-6)) * 100.0, 2)

    raw_sl = pattern.get("stop_loss")
    min_atr_sl = trigger - max(1.8 * eff_atr, trigger * 0.045)
    if raw_sl is None or float(raw_sl) <= 0 or float(raw_sl) >= trigger * 0.99:
        sl_candidate = min_atr_sl
    else:
        # Respect structural stop, but enforce a noise buffer of at least 1.5*ATR / 3.5%
        sl_candidate = min(float(raw_sl), trigger - max(1.5 * eff_atr, trigger * 0.035))
    sl_clamped = max(trigger * 0.88, min(trigger * 0.965, sl_candidate))
    stop_loss = snap_nse_tick(max(0.05, sl_clamped), direction="down")
    if curr_close <= trigger * 1.03 and stop_loss >= min(curr_close, trigger):
        stop_loss = snap_nse_tick(max(0.05, min(curr_close, trigger) * 0.96), direction="down")

    raw_target = float(pattern["target_price"]) if pattern.get("target_price") else None
    vol_reach_cap = trigger + min(trigger * 0.14, 3.4 * eff_atr)
    risk_unit = max(0.01, trigger - stop_loss)

    if raw_target is not None and raw_target > trigger:
        w4_raw = min(raw_target, vol_reach_cap)
        if w4_raw < trigger + max(trigger * 0.03, 1.2 * risk_unit):
            w4_raw = min(vol_reach_cap, max(raw_target, trigger + 1.5 * risk_unit))
    else:
        w4_raw = trigger + min(trigger * 0.11, 3.0 * eff_atr)

    week4_target = snap_nse_tick(max(w4_raw, trigger * 1.025), direction="nearest")
    week4_target_low = snap_nse_tick(trigger + (week4_target - trigger) * 0.70, direction="nearest")
    if week4_target_low >= week4_target:
        week4_target_low = snap_nse_tick(max(trigger * 1.01, week4_target * 0.985), direction="down")

    full_pattern_target = round(raw_target, 2) if (raw_target is not None and raw_target > week4_target) else week4_target
    week4_upside_pct = round(((week4_target - trigger) / max(trigger, 1e-6)) * 100.0, 2)
    week4_upside_from_ltp_pct = round(((week4_target - curr_close) / max(curr_close, 1e-6)) * 100.0, 2)
    projected_rr = round((week4_target - trigger) / max(0.01, trigger - stop_loss), 2)

    progress = (curr_close - trigger) / max(0.01, week4_target - trigger) if curr_close > trigger else 0.0
    name_l = p_name.lower()
    is_lagging = any(k in name_l for k in ("ma crossover", "golden cross", "band walk"))
    is_non_breakout_reversal = any(
        k in name_l for k in ("wyckoff", "rsi momentum divergence", "morning star", "engulfing", "lower band piercing")
    )
    below_sma50 = sma_50 is not None and sma_50 > 0 and curr_close < sma_50 * 0.985
    is_overbought = rsi_14 is not None and rsi_14 >= 73.0
    is_already_surged = ret_10d is not None and ret_10d >= 12.0
    is_past_pivot = dist_pct < -2.5
    is_too_far_along = progress >= 0.35

    if is_past_pivot or is_too_far_along or is_overbought or is_already_surged:
        setup_stage = "EXTENDED_LATE"
        is_pre_breakout = False
        is_late_entry = True
        entry_window = "Extended / Late"
    elif is_non_breakout_reversal:
        setup_stage = "REVERSAL_SIGNAL"
        is_pre_breakout = False
        is_late_entry = False
        entry_window = "Reversal Watch"
    elif below_sma50 and not is_lagging:
        setup_stage = "COUNTER_TREND_BASE"
        is_pre_breakout = False
        is_late_entry = False
        entry_window = "Below 50-DMA (Watch)"
    elif 0.0 < dist_pct <= 3.5 and not is_lagging:
        setup_stage = "IMMINENT_BREAKOUT"
        is_pre_breakout = True
        is_late_entry = False
        entry_window = "Near Pivot (Watch Close)"
    elif 3.5 < dist_pct <= 8.5 and not is_lagging:
        setup_stage = "FORMING_PRE_BREAKOUT"
        is_pre_breakout = True
        is_late_entry = False
        entry_window = "Forming Setup (2–5d)"
    elif -2.5 <= dist_pct <= 0.0 and not is_lagging:
        setup_stage = "FRESH_BREAKOUT"
        is_pre_breakout = True
        is_late_entry = False
        entry_window = "Confirmed Close > Pivot"
    elif dist_pct > 8.5 and not is_lagging:
        setup_stage = "EARLY_BASE"
        is_pre_breakout = False
        is_late_entry = False
        entry_window = "Early Watch"
    else:
        setup_stage = "EXTENDED_LATE"
        is_pre_breakout = False
        is_late_entry = True
        entry_window = "Extended / Late"

    readiness = int(round((pattern.get("quality_score") or 75) * 0.45))
    stage_bonus = {
        "IMMINENT_BREAKOUT": 28,
        "FRESH_BREAKOUT": 20,
        "FORMING_PRE_BREAKOUT": 18,
        "EARLY_BASE": 5,
        "EXTENDED_LATE": -30,
    }
    readiness += stage_bonus.get(setup_stage, 0)

    if 0.3 <= dist_pct <= 3.0:
        readiness += 10
    elif 3.0 < dist_pct <= 5.5:
        readiness += 6

    if rsi_14 is not None:
        if 46.0 <= rsi_14 <= 64.0:
            readiness += 8
        elif 38.0 <= rsi_14 < 46.0 or 64.0 < rsi_14 <= 68.0:
            readiness += 4
        elif rsi_14 > 70.0:
            readiness -= 15

    if ud_ratio is not None and ud_ratio >= 1.20:
        readiness += 6
    if sma_50 is not None and sma_50 > 0 and curr_close >= sma_50 * 0.98:
        readiness += 5
    if projected_rr >= 2.0:
        readiness += 6
    elif projected_rr < 1.3:
        readiness -= 10
    readiness = max(0, min(100, readiness))

    forming_evidence: List[str] = []
    if dist_pct > 0:
        forming_evidence.append(f"{dist_pct:.1f}% below trigger Rs.{trigger:.2f}")
    elif dist_pct >= -2.5:
        forming_evidence.append(f"At pivot Rs.{trigger:.2f} ({abs(dist_pct):.1f}% above)")
    else:
        forming_evidence.append(f"Extended {abs(dist_pct):.1f}% above trigger Rs.{trigger:.2f}")

    if rsi_14 is not None:
        if rsi_14 <= 65.0:
            forming_evidence.append(f"RSI {rsi_14:.1f} (room to run)")
        else:
            forming_evidence.append(f"RSI {rsi_14:.1f} (stretched)")
    if ud_ratio is not None and ud_ratio >= 1.15:
        forming_evidence.append(f"20D U/D vol {ud_ratio:.2f}x accumulation")
    elif rvol is not None and rvol >= 1.2:
        forming_evidence.append(f"RVOL {rvol:.2f}x")
    forming_evidence.append(f"R:R {projected_rr:.1f}x")

    sym_lbl = f"{symbol} is " if symbol else "Stock is "
    if setup_stage == "IMMINENT_BREAKOUT":
        summary = (
            f"{sym_lbl}forming {p_name} ({dist_pct:.1f}% below pivot). "
            f"Bullish confirmation on a daily close above Rs.{trigger:.2f} with volume; "
            f"invalidation below Rs.{stop_loss:.2f}. 4W projected target: Rs.{week4_target:.2f} (+{week4_upside_pct:.1f}%)."
        )
    elif setup_stage == "FORMING_PRE_BREAKOUT":
        summary = (
            f"{sym_lbl}forming {p_name} ({dist_pct:.1f}% below pivot). "
            f"Monitor for a daily close above Rs.{trigger:.2f}; "
            f"invalidation below Rs.{stop_loss:.2f}. 4W projected target: Rs.{week4_target:.2f} (+{week4_upside_pct:.1f}%)."
        )
    elif setup_stage == "FRESH_BREAKOUT":
        summary = (
            f"{sym_lbl}closed above {p_name} pivot Rs.{trigger:.2f} (+{abs(dist_pct):.1f}%). "
            f"Setup valid while holding above Rs.{stop_loss:.2f} (avoid chasing >3%); "
            f"4W projected target: Rs.{week4_target:.2f} (+{week4_upside_pct:.1f}%)."
        )
    elif setup_stage == "EXTENDED_LATE":
        summary = (
            f"{sym_lbl}extended past {p_name} trigger Rs.{trigger:.2f} — "
            f"late for fresh entry; wait for pullback toward Rs.{trigger:.2f}."
        )
    else:
        summary = (
            f"{sym_lbl}building early {p_name} base ({dist_pct:.1f}% below trigger Rs.{trigger:.2f}); "
            f"monitor before breakout."
        )

    return {
        "setup_stage": setup_stage,
        "is_pre_breakout": is_pre_breakout,
        "is_late_entry": is_late_entry,
        "entry_window": entry_window,
        "breakout_trigger": trigger,
        "distance_to_breakout_pct": dist_pct,
        "week4_target": week4_target,
        "week4_target_low": week4_target_low,
        "week4_upside_pct": week4_upside_pct,
        "week4_upside_from_ltp_pct": week4_upside_from_ltp_pct,
        "full_pattern_target": full_pattern_target,
        "projected_stop_loss": stop_loss,
        "projected_rr": projected_rr,
        "readiness_score": readiness,
        "projection_summary": summary,
        "forming_evidence": forming_evidence[:4],
    }


def enrich_patterns_with_projections(
    df: pd.DataFrame,
    patterns: List[Dict[str, Any]],
    symbol: str = "",
    live_price: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Attaches pre-breakout projection metadata to each detected pattern in-place."""
    if not patterns or df is None or df.empty:
        return patterns

    closes = df["CLOSE_PRICE"].astype(float)
    curr_close = float(live_price) if (live_price is not None and live_price > 0) else float(closes.iloc[-1])

    atr_14 = None
    if "ATR_14" in df and pd.notna(df["ATR_14"].iloc[-1]):
        atr_14 = float(df["ATR_14"].iloc[-1])

    rsi_14 = None
    if "RSI_14" in df and pd.notna(df["RSI_14"].iloc[-1]):
        rsi_14 = float(df["RSI_14"].iloc[-1])

    sma_50 = None
    if "SMA_50" in df and pd.notna(df["SMA_50"].iloc[-1]):
        sma_50 = float(df["SMA_50"].iloc[-1])
    elif len(closes) >= 50:
        sma_50 = float(closes.tail(50).mean())

    rvol = None
    ud_ratio = None
    if "VOLUME" in df and len(df) >= 20:
        vols = df["VOLUME"].astype(float)
        v20 = float(vols.tail(20).mean())
        if v20 > 0:
            rvol = float(vols.iloc[-1]) / v20
        diff_c = closes.diff()
        up_v = float(vols.where(diff_c > 0, 0.0).tail(20).sum())
        dn_v = float(vols.where(diff_c < 0, 0.0).tail(20).sum())
        if dn_v > 0:
            ud_ratio = up_v / dn_v

    ret_10d = None
    if len(closes) >= 11 and float(closes.iloc[-11]) > 0:
        ret_10d = ((curr_close - float(closes.iloc[-11])) / float(closes.iloc[-11])) * 100.0

    for p in patterns:
        proj = compute_pattern_projection(
            p,
            curr_close=curr_close,
            atr_14=atr_14,
            rsi_14=rsi_14,
            rvol=rvol,
            ud_ratio=ud_ratio,
            ret_10d=ret_10d,
            sma_50=sma_50,
            symbol=symbol,
        )
        p.update(proj)
    return patterns


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
        df['ATR_14'] = wilder_atr(high, low, close, 14).fillna(tr)
        df['ATR_20'] = wilder_atr(high, low, close, period).fillna(tr)

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

        # Standardized Wilder RSI (14) and ADX (14)
        if 'RSI_14' not in df:
            df['RSI_14'] = wilder_rsi(close, 14)
        if 'ADX_14' not in df:
            df['ADX_14'] = wilder_adx(high, low, close, 14)['ADX_14']

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

                                # Pattern neckline must be in proximity to current price (within 15%) and not overly extended
                                if abs(curr_close - projected_neckline) / curr_close > 0.15:
                                    continue
                                if curr_close > projected_neckline * 1.07:
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

        # Forming Inverse Head & Shoulders (Right shoulder curling below neckline)
        if not any(p.get("name", "").startswith("Inverse Head and Shoulders") for p in patterns) and len(troughs) >= 2:
            for i in range(len(troughs) - 2, -1, -1):
                t1, t2 = troughs[i], troughs[i + 1]
                if t2["price"] >= t1["price"] * 0.982:
                    continue
                p1_cands = [p for p in peaks if t1["idx"] < p["idx"] < t2["idx"]]
                p2_cands = [p for p in peaks if p["idx"] > t2["idx"] and (len(df) - 1 - p["idx"]) <= 35]
                if not p1_cands or not p2_cands:
                    continue
                p1 = max(p1_cands, key=lambda x: x["price"])
                p2 = p2_cands[0]
                if (len(df) - 1 - p2["idx"]) < 3:
                    continue
                if p1["price"] <= max(t1["price"], t2["price"]) or p2["price"] <= t2["price"]:
                    continue

                avg_neckline = (p1["price"] + p2["price"]) / 2.0
                slope = (p2["price"] - p1["price"]) / max(1, p2["idx"] - p1["idx"])
                projected_neckline = p2["price"] + slope * (len(df) - 1 - p2["idx"])
                if abs(projected_neckline - avg_neckline) / max(avg_neckline, 1e-6) > 0.08:
                    projected_neckline = avg_neckline

                rs_low = float(df['LOW_PRICE'].iloc[p2["idx"] + 1:].min())
                shoulder_diff = abs(rs_low - t1["price"]) / max(rs_low, t1["price"], 1e-6)
                if (
                    shoulder_diff <= 0.075
                    and rs_low > t2["price"] * 1.015
                    and curr_close > rs_low * 1.01
                    and curr_close < projected_neckline
                    and (projected_neckline - curr_close) / max(curr_close, 1e-6) <= 0.12
                ):
                    head_depth = projected_neckline - t2["price"]
                    if head_depth > 0:
                        target = projected_neckline + head_depth
                        stop_loss = rs_low * 0.99
                        rr = round(abs(target - projected_neckline) / max(1.0, abs(projected_neckline - stop_loss)), 2)
                        patterns.append({
                            "name": "Inverse Head and Shoulders (Forming)",
                            "category": "Reversal",
                            "type": "Bullish Pre-Breakout",
                            "direction": "Bullish",
                            "quality_score": 84,
                            "significance": "High",
                            "confidence": "Medium",
                            "status": "Forming Right Shoulder — Watch Neckline",
                            "entry_trigger": round(float(projected_neckline), 2),
                            "target_price": round(float(target), 2),
                            "stop_loss": round(float(stop_loss), 2),
                            "risk_reward_ratio": rr,
                            "description": (
                                f"Forming Inverse H&S: Head at Rs.{t2['price']:.2f}, Left Shoulder Rs.{t1['price']:.2f}, "
                                f"Right Shoulder low Rs.{rs_low:.2f}. Buy-above neckline trigger Rs.{projected_neckline:.2f}. "
                                f"Pattern target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f}, R:R: {rr})."
                            ),
                            "key_levels": {
                                "head_trough": round(float(t2["price"]), 2),
                                "left_shoulder": round(float(t1["price"]), 2),
                                "right_shoulder": round(float(rs_low), 2),
                                "neckline": round(float(projected_neckline), 2),
                            },
                            "metrics": {
                                "head_trough": round(float(t2["price"]), 2),
                                "neckline": round(float(projected_neckline), 2),
                                "target": round(float(target), 2),
                                "stop_loss": round(float(stop_loss), 2),
                            },
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
                if curr_close > pivot_entry * 1.07:
                    continue
                target = round(float(pivot_entry + (p_right["price"] - cup_trough["price"])), 2)
                stop_loss = round(float(handle_low), 2)
                is_breakout = curr_close >= pivot_entry

                score = 80
                if vol_dry_up: score += 10
                if rim_diff <= 0.04: score += 5
                if not is_breakout and (pivot_entry - curr_close) / max(curr_close, 1e-6) <= 0.05:
                    score += 5
                elif is_breakout:
                    score += 3

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

                            mid_third_start, mid_third_end = int(lookback * 0.33), int(lookback * 0.67)
                            center_vol = np.mean(sub_vol[mid_third_start:mid_third_end])
                            outer_vol = (np.mean(sub_vol[:mid_third_start]) + np.mean(sub_vol[mid_third_end:])) / 2.0
                            vol_bowl = center_vol < outer_vol

                            # Catch forming saucer right-wall (88%-107% of left rim) curling higher, with dry center volume
                            right_curling = sub_close[-1] >= float(np.min(sub_close[-10:])) * 1.01
                            if (
                                r2 >= 0.72
                                and vol_bowl
                                and right_curling
                                and (left_rim * 0.88 <= curr_close <= left_rim * 1.07)
                                and curr_close > trough_val * 1.03
                            ):
                                recent_rim = float(np.max(sub_close[-8:]))
                                pivot_rim = round(float(max(left_rim, recent_rim)) if curr_close < left_rim else float(left_rim), 2)
                                bowl_depth = max(pivot_rim, curr_close) - trough_val
                                target = round(float(pivot_rim + bowl_depth * 0.85), 2)
                                stop_loss = round(float(trough_val + bowl_depth * 0.25), 2)
                                is_breakout = curr_close >= pivot_rim

                                # Bullish target sanity & minimum 1.8 R:R
                                if target <= curr_close or (target - curr_close) / max(0.01, curr_close - stop_loss) < 1.8:
                                    target = round(float(max(pivot_rim, curr_close) + max(0.01, curr_close - stop_loss) * 2.0), 2)

                                score = 70
                                if r2 >= 0.80: score += 10
                                if pivot_rim * 0.93 <= curr_close <= pivot_rim * 1.02:
                                    score += 12
                                else:
                                    score += 5

                                if is_breakout:
                                    status = "Confirmed Rim Breakout"
                                elif curr_close >= pivot_rim * 0.95:
                                    status = "Approaching Rim Breakout"
                                else:
                                    status = "Forming Right Wall (Saucer Base)"
                                rr = round(abs(target - pivot_rim) / max(1.0, abs(pivot_rim - stop_loss)), 2)

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
            if mom_val >= 0:
                box_high = float(df['HIGH_PRICE'].tail(10).max())
                box_low = float(df['LOW_PRICE'].tail(10).min())
                trigger = round(float(max(box_high, curr_close * 1.005)), 2)
                target = round(float(trigger + curr_atr * 3.0), 2)
                stop_loss = round(float(min(box_low, curr_close - curr_atr * 1.1)), 2)
                status_str = f"Coiling in Squeeze ({squeeze_len} bars) — Ready to Fire"
            else:
                trigger = round(curr_close, 2)
                target = round(float(curr_close - curr_atr * 2.2), 2)
                stop_loss = round(float(curr_close + curr_atr * 1.1), 2)
                status_str = f"Compressed ({squeeze_len} bars in squeeze)"
            score = 80 + min(15, squeeze_len * 2)

            patterns.append({
                "name": "TTM Bollinger Squeeze",
                "category": "Volatility Breakout",
                "type": f"{direction} Energy Compression",
                "direction": direction,
                "quality_score": min(98, score),
                "significance": "High",
                "confidence": "High",
                "status": status_str,
                "entry_trigger": trigger,
                "target_price": target,
                "stop_loss": stop_loss,
                "risk_reward_ratio": round(abs(target - trigger) / max(1.0, abs(trigger - stop_loss)), 2),
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

        # Ascending & Descending Triangles (require recency, bounded duration & un-invalidated levels)
        if len(peaks) >= 2 and len(troughs) >= 2:
            p1, p2 = peaks[-2], peaks[-1]
            t1, t2 = troughs[-2], troughs[-1]
            last_pivot_idx = max(p2["idx"], t2["idx"])
            first_pivot_idx = min(p1["idx"], t1["idx"])
            if (len(df) - 1 - last_pivot_idx) > 35 or not (10 <= (last_pivot_idx - first_pivot_idx) <= 120):
                return patterns

            peak_diff = abs(p1["price"] - p2["price"]) / p1["price"]
            if peak_diff <= 0.018 and t2["price"] > t1["price"] * 1.015:
                resistance = max(p1["price"], p2["price"])
                height = resistance - t1["price"]
                target = round(float(resistance + height), 2)
                stop_loss = round(float(t2["price"]), 2)
                is_breakout = curr_close >= resistance

                if (
                    height > 0
                    and curr_close > stop_loss
                    and target > curr_close
                    and curr_close <= resistance * 1.07
                    and curr_close <= target * 1.05
                    and abs(curr_close - resistance) / max(curr_close, 1e-6) <= 0.12
                ):
                    patterns.append({
                        "name": "Ascending Triangle",
                        "category": "Continuation / Breakout",
                        "type": "Bullish Breakout",
                        "direction": "Bullish",
                        "quality_score": 86,
                        "significance": "High",
                        "confidence": "High" if is_breakout else "Medium",
                        "status": "Confirmed Breakout" if is_breakout else "Coiling Below Resistance",
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

                if (
                    height > 0
                    and curr_close < stop_loss
                    and target < curr_close
                    and curr_close >= target * 0.95
                    and abs(curr_close - support) / max(curr_close, 1e-6) <= 0.12
                ):
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
                        neckline = max(p["price"] for p in mid_peaks)
                        depth = neckline - min(t1["price"], t2["price"])
                        target = round(float(neckline + depth), 2)
                        stop_loss = round(float(min(t1["price"], t2["price"]) * 0.99), 2)
                        is_breakout = curr_close >= neckline

                        # Target must be above current price, stop not violated, and close within valid zone
                        if (
                            depth > 0
                            and curr_close > stop_loss
                            and target > curr_close
                            and curr_close <= neckline * 1.07
                            and curr_close <= target * 1.10
                            and abs(curr_close - neckline) / curr_close <= 0.15
                        ):
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
                        neckline = min(t["price"] for t in mid_troughs)
                        depth = max(p1["price"], p2["price"]) - neckline
                        target = round(float(neckline - depth), 2)
                        stop_loss = round(float(max(p1["price"], p2["price"]) * 1.01), 2)
                        is_breakdown = curr_close <= neckline

                        # Downside target must be below current price and stop not violated
                        if (
                            depth > 0
                            and curr_close < stop_loss
                            and target < curr_close
                            and curr_close >= target * 0.90
                            and abs(curr_close - neckline) / curr_close <= 0.15
                        ):
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
        d_idx = last_5[4]["idx"]
        d_price = float(last_5[4]["price"])
        if (len(df) - 1 - d_idx) > 20 or abs(curr_close - d_price) / max(d_price, 1e-6) > 0.10:
            return patterns

        # 1. Bullish Gartley / Bat: X(low) -> A(high) -> B(low) -> C(high) -> D(low)
        if last_5[0]["type"] == "low" and last_5[1]["type"] == "high" and last_5[2]["type"] == "low" and last_5[3]["type"] == "high" and last_5[4]["type"] == "low":
            X, A, B, C, D = [s["price"] for s in last_5]
            XA = A - X
            if XA > 0:
                ab_retrace = (A - B) / XA
                cd_retrace = (A - D) / XA
                target = round(float(D + (C - D) * 0.618), 2)
                stop_loss = round(float(X * 0.99), 2)
                since_d_low = float(df['LOW_PRICE'].iloc[d_idx:].min())
                valid_bull_harmonic = curr_close > stop_loss and curr_close < target and since_d_low >= stop_loss * 0.995

                if valid_bull_harmonic and 0.55 <= ab_retrace <= 0.68 and 0.73 <= cd_retrace <= 0.84:
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

                elif valid_bull_harmonic and 0.35 <= ab_retrace <= 0.54 and 0.84 <= cd_retrace <= 0.93:
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
                target = round(float(D - (D - C) * 0.618), 2)
                stop_loss = round(float(X * 1.01), 2)
                since_d_high = float(df['HIGH_PRICE'].iloc[d_idx:].max())
                valid_bear_harmonic = curr_close < stop_loss and curr_close > target and since_d_high <= stop_loss * 1.005

                if valid_bear_harmonic and 0.55 <= ab_retrace <= 0.68 and 0.73 <= cd_retrace <= 0.84:
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

                elif valid_bear_harmonic and 0.35 <= ab_retrace <= 0.54 and 0.84 <= cd_retrace <= 0.93:
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
                    trigger_lvl = float(np.max(highs[pole_start_idx:]))
                    if curr_close > trigger_lvl * 1.06:
                        continue
                    target = round(float(trigger_lvl + pole_height * 0.90), 2)
                    stop_loss = round(float(flag_bottom * 0.995), 2)
                    is_breakout = curr_close >= trigger_lvl

                    patterns.append({
                        "name": "Bull Flag Continuation",
                        "category": "Momentum Continuation",
                        "type": "High-Conviction Bullish",
                        "direction": "Bullish",
                        "quality_score": 84 if is_breakout else 86,
                        "significance": "High",
                        "confidence": "High" if is_breakout else "Medium",
                        "status": "Breakout Confirmed" if is_breakout else f"Coiling in Flag ({flag_len} bars)",
                        "entry_trigger": round(trigger_lvl, 2),
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": round(abs(target - trigger_lvl) / max(1.0, abs(trigger_lvl - stop_loss)), 2),
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

        # Require genuine sideways trading range (5%-30% band, low net drift, non-trending ADX <= 28)
        range_pct = (tr_resistance - tr_support) / max(tr_support, 1e-6)
        base_drift = abs(float(closes[-4]) - float(closes[-35])) / max(tr_support, 1e-6)
        if not (0.05 <= range_pct <= 0.30) or base_drift > 0.15:
            return patterns
        if 'ADX_14' in df:
            base_adx = df['ADX_14'].iloc[-35:-3].dropna().tail(15)
            if not base_adx.empty and float(base_adx.mean()) > 28.0:
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

                if target > curr_close:
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

                if target < curr_close:
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
            if (
                (len(df) - 1 - t2["idx"]) <= 15
                and 5 <= (t2["idx"] - t1["idx"]) <= 60
                and (t2["price"] * 0.99 <= curr_close <= t2["price"] * 1.12)
                and t2["price"] < t1["price"] * 0.99
            ):
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
            if (
                (len(df) - 1 - p2["idx"]) <= 15
                and 5 <= (p2["idx"] - p1["idx"]) <= 60
                and (p2["price"] * 0.88 <= curr_close <= p2["price"] * 1.01)
                and p2["price"] > p1["price"] * 1.01
            ):
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

    # Pattern 12: Moving Average Crossovers & Trend Regimes (Golden Cross, Death Cross, 20/50 Cross)
    @classmethod
    def detect_ma_crossover_patterns(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 25:
            return patterns

        close = df['CLOSE_PRICE']
        sma_20 = close.rolling(window=20).mean()
        sma_50 = close.rolling(window=50).mean()
        sma_200 = close.rolling(window=200).mean() if len(close) >= 200 else None

        last_p = float(close.iloc[-1])

        # Scan recent 7 bars for 20/50 crossover
        for offset in range(1, min(8, len(df))):
            idx_curr = -offset
            idx_prev = -offset - 1
            if abs(idx_prev) > len(sma_50) or pd.isna(sma_50.iloc[idx_prev]) or pd.isna(sma_20.iloc[idx_prev]):
                continue

            prev_diff = sma_20.iloc[idx_prev] - sma_50.iloc[idx_prev]
            curr_diff = sma_20.iloc[idx_curr] - sma_50.iloc[idx_curr]

            # Bullish 20/50 Cross
            if prev_diff <= 0 and curr_diff > 0:
                bars_ago = offset - 1
                bars_text = "current bar" if bars_ago == 0 else f"{bars_ago} bars ago"
                patterns.append({
                    "name": "Bullish MA Crossover (20/50)",
                    "category": "Moving Average",
                    "type": "Bullish Trend Crossover",
                    "direction": "Bullish",
                    "quality_score": 86 if bars_ago <= 1 else 78,
                    "significance": "High",
                    "confidence": "High",
                    "status": "Confirmed",
                    "entry_trigger": round(last_p, 2),
                    "target_price": round(last_p * 1.08, 2),
                    "stop_loss": round(float(sma_50.iloc[-1] * 0.98), 2),
                    "risk_reward_ratio": 2.2,
                    "description": f"Fast 20-day SMA crossed above 50-day SMA ({bars_text}), confirming an active intermediate bullish trend.",
                    "key_levels": {"sma_20": round(float(sma_20.iloc[-1]), 2), "sma_50": round(float(sma_50.iloc[-1]), 2)},
                    "metrics": {"bars_ago": bars_ago, "crossover": "bullish_20_50"}
                })
                break

            # Bearish 20/50 Cross
            elif prev_diff >= 0 and curr_diff < 0:
                bars_ago = offset - 1
                bars_text = "current bar" if bars_ago == 0 else f"{bars_ago} bars ago"
                patterns.append({
                    "name": "Bearish MA Crossover (20/50)",
                    "category": "Moving Average",
                    "type": "Bearish Trend Crossover",
                    "direction": "Bearish",
                    "quality_score": 86 if bars_ago <= 1 else 78,
                    "significance": "High",
                    "confidence": "High",
                    "status": "Confirmed",
                    "entry_trigger": round(last_p, 2),
                    "target_price": round(last_p * 0.92, 2),
                    "stop_loss": round(float(sma_50.iloc[-1] * 1.02), 2),
                    "risk_reward_ratio": 2.0,
                    "description": f"Fast 20-day SMA crossed below 50-day SMA ({bars_text}), confirming an active intermediate bearish breakdown.",
                    "key_levels": {"sma_20": round(float(sma_20.iloc[-1]), 2), "sma_50": round(float(sma_50.iloc[-1]), 2)},
                    "metrics": {"bars_ago": bars_ago, "crossover": "bearish_20_50"}
                })
                break

        # Check Golden Cross / Death Cross (50/200) if 200 bars are available
        if sma_200 is not None:
            for offset in range(1, min(11, len(df))):
                idx_curr = -offset
                idx_prev = -offset - 1
                if abs(idx_prev) > len(sma_200) or pd.isna(sma_200.iloc[idx_prev]) or pd.isna(sma_50.iloc[idx_prev]):
                    continue
                prev_diff = sma_50.iloc[idx_prev] - sma_200.iloc[idx_prev]
                curr_diff = sma_50.iloc[idx_curr] - sma_200.iloc[idx_curr]

                if prev_diff <= 0 and curr_diff > 0:
                    bars_ago = offset - 1
                    patterns.append({
                        "name": "Golden Cross (50/200 MA)",
                        "category": "Moving Average",
                        "type": "Major Bullish Long-Term Trend",
                        "direction": "Bullish",
                        "quality_score": 92,
                        "significance": "Very High",
                        "confidence": "High",
                        "status": "Confirmed",
                        "entry_trigger": round(last_p, 2),
                        "target_price": round(last_p * 1.15, 2),
                        "stop_loss": round(float(sma_200.iloc[-1] * 0.97), 2),
                        "risk_reward_ratio": 2.8,
                        "description": f"Major institutional Golden Cross: 50-day SMA crossed above 200-day SMA ({bars_ago} bars ago).",
                        "key_levels": {"sma_50": round(float(sma_50.iloc[-1]), 2), "sma_200": round(float(sma_200.iloc[-1]), 2)},
                        "metrics": {"bars_ago": bars_ago, "crossover": "golden_cross"}
                    })
                    break
                elif prev_diff >= 0 and curr_diff < 0:
                    bars_ago = offset - 1
                    patterns.append({
                        "name": "Death Cross (50/200 MA)",
                        "category": "Moving Average",
                        "type": "Major Bearish Long-Term Breakdown",
                        "direction": "Bearish",
                        "quality_score": 92,
                        "significance": "Very High",
                        "confidence": "High",
                        "status": "Confirmed",
                        "entry_trigger": round(last_p, 2),
                        "target_price": round(last_p * 0.85, 2),
                        "stop_loss": round(float(sma_200.iloc[-1] * 1.03), 2),
                        "risk_reward_ratio": 2.5,
                        "description": f"Major institutional Death Cross: 50-day SMA crossed below 200-day SMA ({bars_ago} bars ago).",
                        "key_levels": {"sma_50": round(float(sma_50.iloc[-1]), 2), "sma_200": round(float(sma_200.iloc[-1]), 2)},
                        "metrics": {"bars_ago": bars_ago, "crossover": "death_cross"}
                    })
                    break

        return patterns

    # =========================================================================
    # Pattern 13: Volatility Contraction Coil (VCP Pre-Breakout Base)
    # =========================================================================
    @classmethod
    def detect_vcp_coil(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 50:
            return patterns

        closes = df['CLOSE_PRICE'].astype(float).values
        highs = df['HIGH_PRICE'].astype(float).values
        lows = df['LOW_PRICE'].astype(float).values
        volumes = df['VOLUME'].astype(float).values if 'VOLUME' in df else np.ones(len(df))
        curr_close = float(closes[-1])

        sma_20 = float(np.mean(closes[-20:]))
        sma_50 = float(np.mean(closes[-50:]))
        rsi_14 = float(df['RSI_14'].iloc[-1]) if ('RSI_14' in df and pd.notna(df['RSI_14'].iloc[-1])) else 55.0
        atr_14 = float(df['ATR_14'].iloc[-1]) if ('ATR_14' in df and pd.notna(df['ATR_14'].iloc[-1])) else curr_close * 0.02

        low_10 = float(np.min(lows[-10:]))
        high_10 = float(np.max(highs[-10:]))
        r10 = (high_10 - low_10) / max(low_10, 1e-6)

        low_20_prior = float(np.min(lows[-30:-10]))
        high_20_prior = float(np.max(highs[-30:-10]))
        r20 = (high_20_prior - low_20_prior) / max(low_20_prior, 1e-6)

        vol_5d = float(np.mean(volumes[-5:]))
        vol_20d = float(np.mean(volumes[-20:]))
        pivot = float(np.max(highs[-20:-1]))
        dist_to_pivot = (pivot - curr_close) / max(curr_close, 1e-6)

        if (
            curr_close >= sma_50 * 0.96
            and curr_close >= sma_20 * 0.985
            and 45.0 <= rsi_14 <= 67.0
            and 0.015 <= r10 <= 0.085
            and r20 > 0
            and r10 <= r20 * 0.78
            and vol_20d > 0
            and vol_5d < vol_20d * 0.95
            and curr_close < pivot
            and 0.003 <= dist_to_pivot <= 0.055
        ):
            stop_loss = round(low_10 * 0.99, 2)
            risk_d = max(0.01, pivot - stop_loss)
            target = round(float(pivot + max(atr_14 * 4.0, risk_d * 2.4)), 2)
            rr = round((target - pivot) / risk_d, 2)
            quality = 92 if vol_5d < vol_20d * 0.75 else 86

            patterns.append({
                "name": "Volatility Contraction Coil (VCP)",
                "category": "Pre-Breakout Base",
                "type": "Bullish Pre-Breakout",
                "direction": "Bullish",
                "quality_score": quality,
                "significance": "High",
                "confidence": "High",
                "status": "Tight Coil Below Pivot — Breakout Imminent",
                "entry_trigger": round(pivot, 2),
                "target_price": target,
                "stop_loss": stop_loss,
                "risk_reward_ratio": rr,
                "description": (
                    f"VCP volatility contraction ({r10*100:.1f}% 10D range vs {r20*100:.1f}% prior 20D) on drying volume. "
                    f"Coiling {dist_to_pivot*100:.1f}% below pivot Rs.{pivot:.2f}. "
                    f"Breakout target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f}, R:R: {rr})."
                ),
                "key_levels": {
                    "pivot": round(pivot, 2),
                    "coil_low": round(low_10, 2),
                    "target": target,
                    "stop_loss": stop_loss,
                },
                "metrics": {
                    "range_10d_pct": round(r10 * 100, 2),
                    "range_20d_pct": round(r20 * 100, 2),
                    "vol_dryup_ratio": round(vol_5d / vol_20d, 2),
                    "target": target,
                },
            })

        return patterns

    # =========================================================================
    # Pattern 14: Darvas Box / Flat-Base Consolidation (O'Neil / Darvas Standard)
    # =========================================================================
    @classmethod
    def detect_flat_base_darvas(cls, df: pd.DataFrame) -> List[Dict[str, Any]]:
        patterns = []
        if len(df) < 55:
            return patterns

        closes = df['CLOSE_PRICE'].astype(float).values
        highs = df['HIGH_PRICE'].astype(float).values
        lows = df['LOW_PRICE'].astype(float).values
        volumes = df['VOLUME'].astype(float).values if 'VOLUME' in df else np.ones(len(df))
        curr_close = float(closes[-1])

        sma_50 = float(np.mean(closes[-50:]))
        if curr_close < sma_50:
            return patterns

        # Prior uptrend into the base: >= +10% gain in the 40 bars preceding a 15-28 bar box
        for box_len in (25, 18):
            if len(df) < box_len + 30:
                continue
            box_start = len(df) - box_len
            prior_base_low = float(np.min(lows[max(0, box_start - 35):box_start]))
            box_high = float(np.max(highs[box_start:]))
            box_low = float(np.min(lows[box_start:]))
            if prior_base_low <= 0 or box_low <= 0:
                continue

            prior_gain = (box_high - prior_base_low) / prior_base_low
            box_depth = (box_high - box_low) / box_high
            dist_to_top = (box_high - curr_close) / max(curr_close, 1e-6)

            vol_5d = float(np.mean(volumes[-5:]))
            vol_box = float(np.mean(volumes[box_start:]))
            rsi_14 = float(df['RSI_14'].iloc[-1]) if ('RSI_14' in df and pd.notna(df['RSI_14'].iloc[-1])) else 55.0

            if (
                prior_gain >= 0.12
                and 0.03 <= box_depth <= 0.12
                and 0.002 <= dist_to_top <= 0.045
                and 46.0 <= rsi_14 <= 66.0
                and vol_box > 0
                and vol_5d <= vol_box * 0.95
            ):
                stop_loss = round(box_low * 0.99, 2)
                target = round(box_high + (box_high - box_low) * 1.4, 2)
                rr = round((target - box_high) / max(0.01, box_high - stop_loss), 2)
                patterns.append({
                    "name": "Darvas Box / Flat Base",
                    "category": "Pre-Breakout Base",
                    "type": "Bullish Pre-Breakout",
                    "direction": "Bullish",
                    "quality_score": 87 if vol_5d <= vol_box * 0.80 else 83,
                    "significance": "High",
                    "confidence": "High",
                    "status": f"Tight {box_len}-Bar Box Below Ceiling",
                    "entry_trigger": round(box_high, 2),
                    "target_price": target,
                    "stop_loss": stop_loss,
                    "risk_reward_ratio": rr,
                    "description": (
                        f"Darvas Flat Base over {box_len} sessions (depth {box_depth*100:.1f}%) after +{prior_gain*100:.1f}% advance. "
                        f"Coiling {dist_to_top*100:.1f}% below box ceiling Rs.{box_high:.2f} (Stop: Rs.{stop_loss:.2f})."
                    ),
                    "key_levels": {"box_high": round(box_high, 2), "box_low": round(box_low, 2), "target": target},
                    "metrics": {"box_bars": box_len, "box_depth_pct": round(box_depth * 100, 1), "target": target},
                })
                break

        return patterns

    # =========================================================================
    # Pattern 15: Falling Wedge (Converging Lower Highs & Lower Lows -> Bullish)
    # =========================================================================
    @classmethod
    def detect_falling_wedge(cls, df: pd.DataFrame, swings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        patterns = []
        if len(swings) < 4 or len(df) < 30:
            return patterns

        curr_close = float(df['CLOSE_PRICE'].iloc[-1])
        peaks = [s for s in swings if s["type"] == "high"]
        troughs = [s for s in swings if s["type"] == "low"]
        if len(peaks) < 2 or len(troughs) < 2:
            return patterns

        p1, p2 = peaks[-2], peaks[-1]
        t1, t2 = troughs[-2], troughs[-1]
        last_idx = max(p2["idx"], t2["idx"])
        first_idx = min(p1["idx"], t1["idx"])
        if (len(df) - 1 - last_idx) > 20 or not (10 <= (last_idx - first_idx) <= 85):
            return patterns

        # Both highs and lows must slope downward, with highs converging faster (steeper slope) than lows
        if p2["price"] < p1["price"] * 0.985 and t2["price"] < t1["price"] * 0.992:
            slope_high = (p2["price"] - p1["price"]) / max(1, p2["idx"] - p1["idx"])
            slope_low = (t2["price"] - t1["price"]) / max(1, t2["idx"] - t1["idx"])
            if slope_high < slope_low < 0:
                trigger = round(float(p2["price"]), 2)
                stop_loss = round(float(t2["price"] * 0.99), 2)
                height = max(0.01, p1["price"] - t1["price"])
                target = round(float(trigger + height * 0.80), 2)
                dist_pct = (trigger - curr_close) / max(curr_close, 1e-6)
                if curr_close > stop_loss and -0.02 <= dist_pct <= 0.085 and target > trigger:
                    rr = round((target - trigger) / max(0.01, trigger - stop_loss), 2)
                    is_breakout = curr_close >= trigger
                    patterns.append({
                        "name": "Falling Wedge (Bullish)",
                        "category": "Pre-Breakout Base",
                        "type": "Bullish Wedge Breakout" if is_breakout else "Bullish Pre-Breakout",
                        "direction": "Bullish",
                        "quality_score": 85 if not is_breakout else 82,
                        "significance": "High",
                        "confidence": "High" if is_breakout else "Medium",
                        "status": "Confirmed Wedge Breakout" if is_breakout else "Coiling Near Upper Wedge Trendline",
                        "entry_trigger": trigger,
                        "target_price": target,
                        "stop_loss": stop_loss,
                        "risk_reward_ratio": rr,
                        "description": (
                            f"Converging Falling Wedge (H1: Rs.{p1['price']:.2f} -> H2: Rs.{p2['price']:.2f}; "
                            f"L1: Rs.{t1['price']:.2f} -> L2: Rs.{t2['price']:.2f}). "
                            f"Breakout trigger: Rs.{trigger:.2f}, Target: Rs.{target:.2f} (Stop: Rs.{stop_loss:.2f})."
                        ),
                        "key_levels": {"upper_pivot": trigger, "lower_pivot": round(float(t2["price"]), 2), "target": target},
                        "metrics": {"slope_high": round(slope_high, 3), "slope_low": round(slope_low, 3), "target": target},
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
        all_detected.extend(self.detect_vcp_coil(df_calc))
        all_detected.extend(self.detect_flat_base_darvas(df_calc))
        all_detected.extend(self.detect_falling_wedge(df_calc, swings))
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
        all_detected.extend(self.detect_ma_crossover_patterns(df_calc))

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

        return enrich_patterns_with_projections(df_calc, deduped)
