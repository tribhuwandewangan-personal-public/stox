"""
Standardized Technical Indicators, Relative Strength & NSE Price Helpers.

Provides canonical Wilder-smoothed RSI, ATR, and ADX, Mansfield Relative Strength
vs Nifty 50 (^NSEI), weekly multi-timeframe EMA trend classification, and NSE
equity tick-size snapping. Pure NumPy/Pandas with zero external I/O.
"""

import math
from typing import Dict, Any

import numpy as np
import pandas as pd


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

    def _rsi(g: float, l: float) -> float:
        if l == 0:
            return 50.0 if g == 0 else 100.0
        return 100.0 - 100.0 / (1.0 + g / l)

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period, len(delta)):
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period
        out[i + 1] = _rsi(avg_gain, avg_loss)
    return pd.Series(out, index=close.index)


def wilder_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    True Range smoothed via Wilder's RMA:
    atr[period - 1] = mean(tr[:period]), then atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period.
    NaN before `period - 1`.
    """
    n = len(close)
    out = np.full(n, np.nan)
    if n < period or period <= 0:
        return pd.Series(out, index=close.index)

    h = high.astype(float)
    l = low.astype(float)
    c = close.astype(float)
    prev_close = c.shift(1)
    tr_vals = pd.concat(
        [h - l, (h - prev_close).abs(), (l - prev_close).abs()],
        axis=1,
    ).max(axis=1).to_numpy()

    atr = float(np.nanmean(tr_vals[:period]))
    out[period - 1] = atr
    for i in range(period, n):
        cur = tr_vals[i]
        if np.isfinite(cur):
            atr = (atr * (period - 1) + cur) / period
        out[i] = atr
    return pd.Series(out, index=close.index)


def wilder_adx(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.DataFrame:
    """
    Average Directional Index (ADX), +DI, and -DI using Wilder's smoothing.
    Returns DataFrame with columns ['ADX_14', 'PLUS_DI_14', 'MINUS_DI_14'] indexed like `close`.
    """
    n = len(close)
    adx = np.full(n, np.nan)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    if n <= period or period <= 0:
        return pd.DataFrame(
            {"ADX_14": adx, "PLUS_DI_14": plus_di, "MINUS_DI_14": minus_di},
            index=close.index,
        )

    h = high.astype(float).to_numpy()
    l = low.astype(float).to_numpy()
    c = close.astype(float).to_numpy()

    tr = np.zeros(n)
    pdm = np.zeros(n)
    ndm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        up_move = h[i] - h[i - 1]
        down_move = l[i - 1] - l[i]
        pdm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        ndm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0

    dx = np.full(n, np.nan)
    sm_tr = float(np.sum(tr[1:period + 1]))
    sm_pdm = float(np.sum(pdm[1:period + 1]))
    sm_ndm = float(np.sum(ndm[1:period + 1]))

    for i in range(period, n):
        if i > period:
            sm_tr = sm_tr - (sm_tr / period) + tr[i]
            sm_pdm = sm_pdm - (sm_pdm / period) + pdm[i]
            sm_ndm = sm_ndm - (sm_ndm / period) + ndm[i]

        pdi = (100.0 * sm_pdm / sm_tr) if sm_tr > 0 else 0.0
        ndi = (100.0 * sm_ndm / sm_tr) if sm_tr > 0 else 0.0
        plus_di[i] = pdi
        minus_di[i] = ndi
        di_sum = pdi + ndi
        dx[i] = (100.0 * abs(pdi - ndi) / di_sum) if di_sum > 0 else 0.0

    if n >= 2 * period:
        adx_val = float(np.nanmean(dx[period:2 * period]))
        adx[2 * period - 1] = adx_val
        for i in range(2 * period, n):
            if np.isfinite(dx[i]):
                adx_val = (adx_val * (period - 1) + dx[i]) / period
            adx[i] = adx_val

    return pd.DataFrame(
        {"ADX_14": adx, "PLUS_DI_14": plus_di, "MINUS_DI_14": minus_di},
        index=close.index,
    )


def mansfield_relative_strength(
    stock_df: pd.DataFrame,
    bench_df: pd.DataFrame,
) -> Dict[str, Any]:
    """
    Computes Mansfield Relative Strength vs a benchmark index (e.g. Nifty 50 ^NSEI):
      RP = (Stock Close / Benchmark Close) * 100
      Mansfield RS = ((RP / SMA_N(RP)) - 1) * 100
    where N is 252 (1Y) if >=252 aligned bars, else 126 (6M) if >=126, else 60 (~3M).
    Returns None fields cleanly if fewer than 60 aligned trading days exist.
    """
    empty = {
        "mansfield_rs": None,
        "rs_63d_alpha_pct": None,
        "rs_rating": None,
        "benchmark_bars": 0,
    }
    if (
        stock_df is None
        or bench_df is None
        or stock_df.empty
        or bench_df.empty
        or "DATE" not in stock_df.columns
        or "CLOSE_PRICE" not in stock_df.columns
        or "DATE" not in bench_df.columns
        or "CLOSE_PRICE" not in bench_df.columns
    ):
        return empty

    s_df = stock_df[["DATE", "CLOSE_PRICE"]].copy()
    b_df = bench_df[["DATE", "CLOSE_PRICE"]].copy()
    s_df["_d"] = pd.to_datetime(s_df["DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    b_df["_d"] = pd.to_datetime(b_df["DATE"], errors="coerce").dt.strftime("%Y-%m-%d")
    s_df["_s"] = pd.to_numeric(s_df["CLOSE_PRICE"], errors="coerce")
    b_df["_b"] = pd.to_numeric(b_df["CLOSE_PRICE"], errors="coerce")

    s_df = s_df.dropna(subset=["_d", "_s"]).drop_duplicates(subset=["_d"], keep="last")
    b_df = b_df.dropna(subset=["_d", "_b"]).drop_duplicates(subset=["_d"], keep="last")

    merged = pd.merge(s_df[["_d", "_s"]], b_df[["_d", "_b"]], on="_d", how="inner")
    merged = merged[(merged["_s"] > 0) & (merged["_b"] > 0)].sort_values("_d").reset_index(drop=True)
    n_bars = len(merged)
    if n_bars < 60:
        return {**empty, "benchmark_bars": n_bars}

    rp = (merged["_s"] / merged["_b"]) * 100.0
    window = 252 if n_bars >= 252 else (126 if n_bars >= 126 else 60)
    sma_rp = float(rp.tail(window).mean())
    if sma_rp <= 0 or not np.isfinite(sma_rp):
        return {**empty, "benchmark_bars": n_bars}

    mrs = round(((float(rp.iloc[-1]) / sma_rp) - 1.0) * 100.0, 2)

    alpha_63d = None
    if n_bars >= 64:
        s_ret = (float(merged["_s"].iloc[-1]) / float(merged["_s"].iloc[-64]) - 1.0) * 100.0
        b_ret = (float(merged["_b"].iloc[-1]) / float(merged["_b"].iloc[-64]) - 1.0) * 100.0
        if np.isfinite(s_ret) and np.isfinite(b_ret):
            alpha_63d = round(s_ret - b_ret, 2)

    if mrs >= 8.0:
        rating = "Market Leader"
    elif mrs >= 2.0:
        rating = "Outperforming"
    elif mrs > -2.0:
        rating = "Inline"
    else:
        rating = "Lagging"

    return {
        "mansfield_rs": mrs,
        "rs_63d_alpha_pct": alpha_63d,
        "rs_rating": rating,
        "benchmark_bars": n_bars,
    }


def compute_weekly_trend(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Resamples daily OHLCV to W-FRI closing bars and computes 10-week & 30-week EMA
    (falling back to 20-week span if 20 <= weeks < 30, or `weeks` if 12 <= weeks < 20).
    Returns None fields if fewer than 12 weekly bars are available.
    """
    empty = {
        "weekly_trend": None,
        "weekly_ema_10": None,
        "weekly_ema_30": None,
        "weekly_bars": 0,
    }
    if df is None or df.empty or "DATE" not in df.columns or "CLOSE_PRICE" not in df.columns:
        return empty

    wdf = df[["DATE", "CLOSE_PRICE"]].copy()
    wdf["DATE"] = pd.to_datetime(wdf["DATE"], errors="coerce")
    wdf["CLOSE_PRICE"] = pd.to_numeric(wdf["CLOSE_PRICE"], errors="coerce")
    wdf = wdf.dropna(subset=["DATE", "CLOSE_PRICE"]).sort_values("DATE").set_index("DATE")
    if wdf.empty:
        return empty

    weekly = wdf["CLOSE_PRICE"].resample("W-FRI").last().dropna()
    n_weeks = len(weekly)
    if n_weeks < 12:
        return {**empty, "weekly_bars": n_weeks}

    ema_10 = float(weekly.ewm(span=10, adjust=False).mean().iloc[-1])
    slow_span = 30 if n_weeks >= 30 else (20 if n_weeks >= 20 else n_weeks)
    ema_30 = float(weekly.ewm(span=slow_span, adjust=False).mean().iloc[-1])
    last_w = float(weekly.iloc[-1])

    if last_w > ema_10 and ema_10 > ema_30:
        trend = "Bullish"
    elif last_w < ema_10 and ema_10 < ema_30:
        trend = "Bearish"
    else:
        trend = "Neutral"

    return {
        "weekly_trend": trend,
        "weekly_ema_10": round(ema_10, 2),
        "weekly_ema_30": round(ema_30, 2),
        "weekly_bars": n_weeks,
    }


def snap_nse_tick(price: float, direction: str = "nearest") -> float:
    """
    Snaps an NSE equity price to exchange tick size:
    Rs. 0.01 below Rs. 250.00, and Rs. 0.05 at/above Rs. 250.00.
    direction: "nearest" | "down" | "up".
    """
    val = float(price)
    if not math.isfinite(val) or val <= 0:
        return 0.0
    tick = 0.01 if val < 250.0 else 0.05
    if direction == "down":
        snapped = math.floor(val / tick + 1e-9) * tick
    elif direction == "up":
        snapped = math.ceil(val / tick - 1e-9) * tick
    else:
        snapped = round(val / tick) * tick
    return round(snapped, 2)
