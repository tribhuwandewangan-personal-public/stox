"""
Backtesting Framework: Live-Aligned Deterministic Engine Validation.

Key anti-bias & realistic NSE execution guarantees:
  * Uses the actual live TechnicalAnalysisEngine (Wilder RSI-14, ATR-14, ADX-14),
    QuantitativePatternEngine, and MasterPredictionSynthesizerAgent.compute_quantitative_verdict().
  * Strict causal slicing: no future candles ever leak into indicator or pattern computation.
  * Realistic execution: signals generated at bar `t` Close execute at bar `t+1` Open
    (skipping setups whose overnight open gaps past Stop Loss or Target).
  * Conservative intraday exit: Stop Loss takes precedence on dual-hit bars, and gap-downs
    through Stop Loss fill at `min(open, stop)`.
  * Realistic NSE delivery friction (~0.40% round-trip STT, stamp, fees & slippage + Rs 15.93 DP).
  * Equal-capital fixed-fractional position sizing, max % drawdown, Calmar, expectancy,
    profit factor, ddof=1 Sharpe over Indian T-Bill Rf (6.5%), and benchmark alpha comparison.
"""

import json
import math
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from agents.synthesizer_agent import MasterPredictionSynthesizerAgent
from tools.indicators import compute_weekly_trend, mansfield_relative_strength
from tools.outcome_tracker import parse_price
from tools.tech_tools import TechnicalAnalysisEngine, _safe_float

DEFAULT_INITIAL_CAPITAL = 1_000_000.0
DEFAULT_POSITION_FRACTION = 0.20
DEFAULT_ROUND_TRIP_COST_PCT = 0.40
DEFAULT_DP_CHARGE_RS = 15.93
DEFAULT_RISK_FREE_ANNUAL = 0.065


@dataclass
class Trade:
    """Single executed swing trade entry/exit record."""
    symbol: str
    entry_date: str
    entry_price: float
    entry_verdict: str
    target_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_verdict: Optional[str] = None
    days_held: int = 0
    bars_held: int = 0
    signal_date: Optional[str] = None
    pnl_pct: float = 0.0             # net return % after transaction friction
    gross_pnl_pct: float = 0.0       # gross price move % before friction
    pnl_abs: float = 0.0             # net rupee P&L after transaction friction
    transaction_cost_pct: float = 0.0
    transaction_cost_rs: float = 0.0
    position_capital: float = 0.0
    shares: int = 0
    status: str = "OPEN"             # OPEN, PROFIT_TARGET, STOPPED_OUT, TIME_LIMIT, CLOSED_EOD


@dataclass
class BacktestMetrics:
    """Portfolio & trade-level validation metrics."""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy_pct: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    calmar_ratio: float = 0.0
    cagr_pct: float = 0.0
    avg_hold_days: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    final_capital: float = DEFAULT_INITIAL_CAPITAL
    total_friction_rs: float = 0.0
    skipped_gap_entries: int = 0
    risk_free_rate_pct: float = round(DEFAULT_RISK_FREE_ANNUAL * 100.0, 2)


class BacktestEngine:
    """Core backtesting engine aligned to the live deterministic pipeline."""

    def __init__(self, db_path: str = "stox.db"):
        if (db_path == "stox.db" or not os.path.exists(db_path) or os.path.getsize(db_path) == 0) and os.path.exists("storage/cache.db"):
            self.db_path = "storage/cache.db"
        else:
            self.db_path = db_path
        self.trades: List[Trade] = []
        self._table_name: Optional[str] = None
        self._tech_engine = TechnicalAnalysisEngine()
        self._benchmark_df_cache: Dict[str, pd.DataFrame] = {}

    def _discover_table(self, conn: sqlite3.Connection) -> str:
        if self._table_name:
            return self._table_name
        cursor = conn.cursor()
        tables = [r[0] for r in cursor.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "historical_candles" in tables:
            self._table_name = "historical_candles"
        elif "historical_data" in tables:
            self._table_name = "historical_data"
        else:
            self._table_name = "historical_candles"
        return self._table_name

    def get_historical_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch historical OHLCV data from SQLite across [start_date, end_date]."""
        if not os.path.exists(self.db_path):
            return []

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        try:
            tbl = self._discover_table(conn)
            clean_sym = symbol.upper().replace(".NS", "")
            ns_sym = clean_sym + ".NS"
            candidates = (symbol.upper(), clean_sym) if clean_sym.startswith("^") else (clean_sym, ns_sym)

            if tbl == "historical_candles":
                cursor.execute("""
                    SELECT date as DATE, open as OPEN_PRICE, high as HIGH_PRICE,
                           low as LOW_PRICE, close as CLOSE_PRICE, volume as VOLUME
                    FROM historical_candles
                    WHERE (symbol = ? OR symbol = ?) AND date BETWEEN ? AND ?
                    ORDER BY date ASC
                """, (candidates[0], candidates[1], start_date, end_date))
            else:
                cursor.execute("""
                    SELECT DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
                    FROM historical_data
                    WHERE (symbol = ? OR symbol = ?) AND DATE BETWEEN ? AND ?
                    ORDER BY DATE ASC
                """, (candidates[0], candidates[1], start_date, end_date))

            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    def _get_data_with_warmup(
        self, symbol: str, start_date: str, end_date: str, warmup_calendar_days: int = 380
    ) -> Tuple[List[Dict], int]:
        """Loads candles from (start_date - warmup) .. end_date so indicators are seeded on start_date."""
        try:
            warmup_start = (
                datetime.strptime(start_date[:10], "%Y-%m-%d") - timedelta(days=warmup_calendar_days)
            ).strftime("%Y-%m-%d")
        except ValueError:
            warmup_start = start_date
        full_data = self.get_historical_data(symbol, warmup_start, end_date)
        if not full_data:
            return [], 0
        start_idx = 0
        for idx, row in enumerate(full_data):
            if str(row.get("DATE") or "")[:10] >= start_date:
                start_idx = idx
                break
        return full_data, start_idx

    def _get_benchmark_df(self, benchmark_sym: str, start_date: str, end_date: str) -> pd.DataFrame:
        key = f"{benchmark_sym}:{start_date}:{end_date}"
        if key in self._benchmark_df_cache:
            return self._benchmark_df_cache[key]
        rows = self.get_historical_data(benchmark_sym, start_date, end_date)
        df = pd.DataFrame(rows) if rows else pd.DataFrame()
        if not df.empty:
            df["DATE_STR"] = df["DATE"].astype(str).str[:10]
        self._benchmark_df_cache[key] = df
        return df

    def get_analysis_signal(
        self,
        symbol: str,
        as_of_date: str,
        candles_up_to_date: Optional[List[Dict]] = None,
        enable_patterns: bool = True,
    ) -> Optional[Dict]:
        """Get logged prediction_log verdict for `as_of_date` or run live deterministic synthesis cleanly."""
        if os.path.exists(self.db_path):
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='prediction_log'")
                if cursor.fetchone():
                    cursor.execute("""
                        SELECT verdict, confidence_pct, target, stop, price_at_signal
                        FROM prediction_log
                        WHERE symbol = ? AND as_of_date = ?
                        ORDER BY id DESC LIMIT 1
                    """, (symbol.upper(), as_of_date))
                    row = cursor.fetchone()
                    if row:
                        return {
                            "verdict": row["verdict"],
                            "confidence": row["confidence_pct"],
                            "target": row["target"],
                            "stop": row["stop"],
                            "price": row["price_at_signal"],
                        }
            except Exception:
                pass
            finally:
                conn.close()

        if candles_up_to_date and len(candles_up_to_date) >= 50:
            df = pd.DataFrame(candles_up_to_date)
            ind_df = self._prepare_indicator_frame(df)
            return self._synthesize_at_index(
                symbol, ind_df, len(ind_df) - 1, enable_patterns=enable_patterns
            )
        return None

    def _prepare_indicator_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Computes strictly causal live technical indicators across the full candle DataFrame using
        TechnicalAnalysisEngine._compute_indicators() (Wilder RSI-14, ATR-14, ADX-14, SMA/BB/MACD/RVOL).
        """
        if df is None or df.empty:
            return pd.DataFrame()
        work = df.copy()
        work["DATE_STR"] = work["DATE"].astype(str).str[:10]
        work["DATE"] = pd.to_datetime(work["DATE"])
        work["CLOSE_PRICE"] = work["CLOSE_PRICE"].astype(float)
        work["HIGH_PRICE"] = work["HIGH_PRICE"].astype(float)
        work["LOW_PRICE"] = work["LOW_PRICE"].astype(float)
        work["OPEN_PRICE"] = work["OPEN_PRICE"].astype(float)
        work["VOLUME"] = work["VOLUME"].fillna(0).astype(float)
        ind_df = self._tech_engine._compute_indicators(work)
        # Keep SMA_200 strictly causal (rolling(200), NaN before bar 200 rather than full-length window)
        ind_df["SMA_200"] = ind_df["CLOSE_PRICE"].rolling(window=200).mean()
        return ind_df

    def _synthesize_at_index(
        self,
        symbol: str,
        ind_df: pd.DataFrame,
        idx: int,
        bench_df: Optional[pd.DataFrame] = None,
        enable_patterns: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes the live MasterPredictionSynthesizerAgent at historical bar `idx` using strictly
        historical data `<= idx` (zero backtest-only pre-filters, zero lookahead).
        """
        if ind_df is None or idx < 49 or idx >= len(ind_df):
            return None

        row = ind_df.iloc[idx]
        prev = ind_df.iloc[idx - 1]
        lp = _safe_float(row.get("CLOSE_PRICE"))
        if lp is None or lp <= 0:
            return None

        prev_c = _safe_float(prev.get("CLOSE_PRICE"))
        day_chg = round((lp - prev_c) / prev_c * 100.0, 2) if (prev_c and prev_c > 0) else None
        atr_val = _safe_float(row.get("ATR_14"))
        rsi_val = _safe_float(row.get("RSI_14"))
        if rsi_val is None:
            return None

        weekly_trend_val = None
        if idx >= 60:
            try:
                wt = compute_weekly_trend(ind_df.iloc[max(0, idx - 210):idx + 1])
                weekly_trend_val = wt.get("weekly_trend")
            except Exception:
                weekly_trend_val = None

        mansfield_val = None
        if bench_df is not None and not bench_df.empty and idx >= 90:
            try:
                cur_d = str(row.get("DATE_STR") or "")[:10]
                b_slice = bench_df[bench_df["DATE_STR"] <= cur_d].tail(160)
                if len(b_slice) >= 70:
                    rs = mansfield_relative_strength(ind_df.iloc[max(0, idx - 160):idx + 1], b_slice)
                    mansfield_val = rs.get("mansfield_rs")
            except Exception:
                mansfield_val = None

        raw_tech = {
            "last_price": lp,
            "sma_20": _safe_float(row.get("SMA_20")),
            "sma_50": _safe_float(row.get("SMA_50")),
            "sma_200": _safe_float(row.get("SMA_200")),
            "sma_50_slope": _safe_float(row.get("SMA_50_SLOPE")),
            "rsi_14": rsi_val,
            "rvol": _safe_float(row.get("RVOL")),
            "up_down_vol_ratio": _safe_float(row.get("UP_DOWN_VOL_RATIO_20")),
            "atr_14": atr_val,
            "adx_14": _safe_float(row.get("ADX_14")),
            "plus_di_14": _safe_float(row.get("PLUS_DI_14")),
            "minus_di_14": _safe_float(row.get("MINUS_DI_14")),
            "day_change_pct": day_chg,
            "swing_high_20": _safe_float(row.get("SWING_HIGH_20")),
            "swing_low_20": _safe_float(row.get("SWING_LOW_20")),
            "weekly_trend": weekly_trend_val,
            "mansfield_rs": mansfield_val,
        }
        raw_risk = {
            "last_price": lp,
            "atr_14": atr_val,
            "suggested_stop_loss": round(lp - 2.0 * atr_val, 2) if (atr_val and atr_val > 0) else round(lp * 0.95, 2),
            "suggested_target_price": round(lp + 4.0 * atr_val, 2) if (atr_val and atr_val > 0) else round(lp * 1.08, 2),
        }

        patterns: List[Dict[str, Any]] = []
        if enable_patterns and idx >= 25:
            try:
                hist_window = ind_df.iloc[max(0, idx - 119):idx + 1]
                patterns = self._tech_engine.detect_chart_patterns(hist_window)
            except Exception:
                patterns = []

        hist_ctx: Dict[str, Any] = {}
        if idx >= 30:
            c30 = _safe_float(ind_df.iloc[idx - 30].get("CLOSE_PRICE"))
            if c30 and c30 > 0:
                hist_ctx["pct_change_30d"] = round((lp - c30) / c30 * 100.0, 2)

        sig = MasterPredictionSynthesizerAgent.compute_quantitative_verdict(
            symbol=symbol,
            company_name=symbol,
            last_price=lp,
            raw_tech=raw_tech,
            raw_risk=raw_risk,
            detected_patterns=patterns,
            events_data={},
            context={"historical": hist_ctx} if hist_ctx else None,
        )
        verdict = str(sig.get("action_verdict") or "HOLD").upper()
        if verdict not in ("BUY", "ACCUMULATE"):
            return None

        tgt = parse_price(sig.get("when_to_sell_target"))
        sl = parse_price(sig.get("stop_loss"))
        if tgt is None or sl is None or not (sl < lp < tgt):
            return None

        return {
            "verdict": verdict,
            "confidence": sig.get("confidence_percentage", 0),
            "target": round(tgt, 2),
            "stop": round(sl, 2),
            "price": lp,
        }

    def backtest_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        hold_days: int = 20,
        use_structural_levels: bool = True,
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        position_fraction: float = DEFAULT_POSITION_FRACTION,
        round_trip_cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT,
        dp_charge_rs: float = DEFAULT_DP_CHARGE_RS,
        enable_patterns: bool = True,
    ) -> Tuple[List[Trade], BacktestMetrics]:
        """
        Executes a causal walk-forward backtest for `symbol`:
        - Evaluates live synthesizer signals at EOD bar `i`
        - Enters on bar `i+1` Open (invalidating overnight gaps past Stop/Target)
        - Exits stops conservatively at `min(open, stop)` on gap-downs
        - Applies realistic NSE delivery friction & equal-capital fixed-fractional sizing.
        """
        data, start_idx = self._get_data_with_warmup(symbol, start_date, end_date)
        if not data or start_idx >= len(data):
            return [], BacktestMetrics(initial_capital=initial_capital, final_capital=initial_capital)

        ind_df = self._prepare_indicator_frame(pd.DataFrame(data))
        warmup_start = str(data[0].get("DATE") or "")[:10]
        bench_df = self._get_benchmark_df("^NSEI", warmup_start, end_date)

        trades: List[Trade] = []
        open_trade: Optional[Trade] = None
        pending_signal: Optional[Dict[str, Any]] = None
        skipped_gap_entries = 0
        capital_per_trade = max(1000.0, float(initial_capital) * float(position_fraction))

        def _finalize_trade(tr: Trade, exit_d: str, exit_px: float, reason: str, close_bar_count: int) -> None:
            tr.exit_date = exit_d
            tr.exit_price = round(float(exit_px), 2)
            tr.bars_held = close_bar_count
            tr.days_held = self._days_between(tr.entry_date, exit_d)
            shares = max(1, tr.shares)
            pos_cap = tr.position_capital or (shares * tr.entry_price)
            gross_rs = (tr.exit_price - tr.entry_price) * shares
            gross_pct = ((tr.exit_price - tr.entry_price) / tr.entry_price) * 100.0
            cost_rs = round(pos_cap * (round_trip_cost_pct / 100.0) + dp_charge_rs, 2)
            cost_pct = round((cost_rs / pos_cap) * 100.0, 3) if pos_cap > 0 else 0.0
            net_rs = round(gross_rs - cost_rs, 2)
            net_pct = round((net_rs / pos_cap) * 100.0, 3) if pos_cap > 0 else 0.0

            tr.gross_pnl_pct = round(gross_pct, 3)
            tr.transaction_cost_rs = cost_rs
            tr.transaction_cost_pct = cost_pct
            tr.pnl_abs = net_rs
            tr.pnl_pct = net_pct
            tr.status = reason
            trades.append(tr)

        for i in range(start_idx, len(data)):
            candle = data[i]
            current_date = str(candle["DATE"])[:10]
            open_price = float(candle.get("OPEN_PRICE") or candle["CLOSE_PRICE"])
            high_price = float(candle.get("HIGH_PRICE") or candle["CLOSE_PRICE"])
            low_price = float(candle.get("LOW_PRICE") or candle["CLOSE_PRICE"])
            close_price = float(candle["CLOSE_PRICE"])

            # 1. Execute any pending t+1 Open entry BEFORE scanning exits
            if pending_signal is not None and open_trade is None:
                entry_px = open_price if open_price > 0 else close_price
                tgt = pending_signal.get("target")
                sl = pending_signal.get("stop")
                gap_invalid = (
                    entry_px <= 0
                    or (sl is not None and entry_px <= sl)
                    or (tgt is not None and entry_px >= tgt)
                )
                if gap_invalid:
                    skipped_gap_entries += 1
                    pending_signal = None
                else:
                    shares = max(1, int(capital_per_trade // entry_px))
                    pos_cap = round(shares * entry_px, 2)
                    open_trade = Trade(
                        symbol=symbol,
                        entry_date=current_date,
                        entry_price=round(entry_px, 2),
                        entry_verdict=pending_signal["verdict"],
                        target_price=tgt,
                        stop_loss_price=sl,
                        signal_date=pending_signal["signal_date"],
                        position_capital=pos_cap,
                        shares=shares,
                    )
                    pending_signal = None

            # 2. Check exit on open trade (including entry day intraday touches)
            if open_trade is not None:
                open_trade.bars_held += 1
                should_close = False
                close_reason = ""
                exit_price = close_price

                if use_structural_levels and open_trade.target_price and open_trade.stop_loss_price:
                    tgt = open_trade.target_price
                    sl = open_trade.stop_loss_price
                    hit_stop = low_price <= sl
                    hit_target = high_price >= tgt
                    if hit_stop:
                        # Conservative dual-hit resolution & realistic gap-down fill at min(open, stop)
                        should_close = True
                        close_reason = "STOPPED_OUT"
                        exit_price = min(open_price, sl) if open_price > 0 else sl
                    elif hit_target:
                        should_close = True
                        close_reason = "PROFIT_TARGET"
                        exit_price = tgt
                else:
                    pct_stop_px = open_trade.entry_price * (1.0 - stop_loss_pct / 100.0)
                    pct_tgt_px = open_trade.entry_price * (1.0 + take_profit_pct / 100.0)
                    if low_price <= pct_stop_px:
                        should_close = True
                        close_reason = "STOPPED_OUT"
                        exit_price = min(open_price, pct_stop_px) if open_price > 0 else pct_stop_px
                    elif high_price >= pct_tgt_px:
                        should_close = True
                        close_reason = "PROFIT_TARGET"
                        exit_price = pct_tgt_px

                if not should_close and open_trade.bars_held >= hold_days:
                    should_close = True
                    close_reason = "TIME_LIMIT"
                    exit_price = close_price

                if should_close:
                    _finalize_trade(open_trade, current_date, exit_price, close_reason, open_trade.bars_held)
                    open_trade = None
                    continue  # avoid re-entering on exact exit candle

            # 3. EOD causal live-model signal evaluation (schedules entry for i+1 Open)
            if open_trade is None and pending_signal is None and i >= 49 and (i + 1) < len(data):
                sig = self._synthesize_at_index(
                    symbol, ind_df, i, bench_df=bench_df, enable_patterns=enable_patterns
                )
                if sig and sig["verdict"] in ("BUY", "ACCUMULATE"):
                    target = sig.get("target")
                    stop = sig.get("stop")
                    if isinstance(target, str):
                        target = parse_price(target)
                    if isinstance(stop, str):
                        stop = parse_price(stop)
                    pending_signal = {
                        "signal_date": current_date,
                        "verdict": sig["verdict"],
                        "target": target,
                        "stop": stop,
                    }

        # Close remaining trade at period end
        if open_trade is not None:
            last_price = float(data[-1]["CLOSE_PRICE"])
            last_date = str(data[-1]["DATE"])[:10]
            _finalize_trade(open_trade, last_date, last_price, "CLOSED_EOD", open_trade.bars_held)

        metrics = self.calculate_portfolio_metrics(
            trades,
            initial_capital=initial_capital,
            skipped_gap_entries=skipped_gap_entries,
        )
        return trades, metrics

    def backtest_portfolio(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        **kwargs,
    ) -> Dict[str, Tuple[List[Trade], BacktestMetrics]]:
        """Backtest multiple symbols."""
        results = {}
        for symbol in symbols:
            trades, metrics = self.backtest_symbol(symbol, start_date, end_date, **kwargs)
            results[symbol] = (trades, metrics)
        return results

    @staticmethod
    def calculate_portfolio_metrics(
        trades: List[Trade],
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_free_rate_annual: float = DEFAULT_RISK_FREE_ANNUAL,
        skipped_gap_entries: int = 0,
    ) -> BacktestMetrics:
        """
        Computes JSON-safe equal-capital portfolio metrics:
        net expectancy %, profit factor, max % drawdown on equity curve, Calmar, CAGR,
        and ddof=1 Sharpe ratio excess over Indian T-Bill risk-free rate (6.5%).
        """
        metrics = BacktestMetrics(
            initial_capital=round(float(initial_capital), 2),
            final_capital=round(float(initial_capital), 2),
            skipped_gap_entries=int(skipped_gap_entries),
            risk_free_rate_pct=round(risk_free_rate_annual * 100.0, 2),
        )
        if not trades:
            return metrics

        ordered = sorted(trades, key=lambda t: (t.exit_date or t.entry_date or "", t.entry_date or ""))
        n = len(ordered)
        winning = [t for t in ordered if t.pnl_pct > 0]
        losing = [t for t in ordered if t.pnl_pct <= 0]

        metrics.total_trades = n
        metrics.winning_trades = len(winning)
        metrics.losing_trades = len(losing)
        metrics.win_rate = round((len(winning) / n) * 100.0, 2)

        net_pnls = [float(t.pnl_abs) for t in ordered]
        net_pcts = [float(t.pnl_pct) for t in ordered]
        metrics.total_pnl = round(sum(net_pnls), 2)
        metrics.final_capital = round(initial_capital + metrics.total_pnl, 2)
        metrics.total_pnl_pct = round((metrics.total_pnl / initial_capital) * 100.0, 2) if initial_capital > 0 else 0.0
        metrics.total_friction_rs = round(sum(float(t.transaction_cost_rs) for t in ordered), 2)

        if winning:
            metrics.avg_win = round(sum(t.pnl_pct for t in winning) / len(winning), 3)
        if losing:
            metrics.avg_loss = round(sum(t.pnl_pct for t in losing) / len(losing), 3)
        metrics.expectancy_pct = round(sum(net_pcts) / n, 3)

        sum_wins_rs = sum(t.pnl_abs for t in winning)
        sum_losses_rs = abs(sum(t.pnl_abs for t in losing))
        if sum_losses_rs > 0:
            metrics.profit_factor = round(sum_wins_rs / sum_losses_rs, 2)
        elif sum_wins_rs > 0:
            metrics.profit_factor = 99.99
        else:
            metrics.profit_factor = 0.0

        hold_days_list = [max(1, t.days_held) for t in ordered]
        hold_bars_list = [max(1, t.bars_held or max(1, int(round(t.days_held * 5 / 7)))) for t in ordered]
        metrics.avg_hold_days = round(sum(hold_days_list) / n, 1)
        metrics.best_trade = round(max(net_pcts), 2)
        metrics.worst_trade = round(min(net_pcts), 2)

        # Equal-capital equity curve drawdown
        equity = float(initial_capital)
        peak = float(initial_capital)
        max_dd_rs = 0.0
        max_dd_pct = 0.0
        for t in ordered:
            equity += float(t.pnl_abs)
            if equity > peak:
                peak = equity
            dd_rs = max(0.0, peak - equity)
            dd_pct = (dd_rs / peak * 100.0) if peak > 0 else 0.0
            if dd_rs > max_dd_rs:
                max_dd_rs = dd_rs
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
        metrics.max_drawdown = round(max_dd_rs, 2)
        metrics.max_drawdown_pct = round(max_dd_pct, 2)

        # CAGR & Calmar over portfolio span
        try:
            d_first = min(datetime.strptime(t.entry_date[:10], "%Y-%m-%d") for t in ordered if t.entry_date)
            d_last = max(datetime.strptime((t.exit_date or t.entry_date)[:10], "%Y-%m-%d") for t in ordered if (t.exit_date or t.entry_date))
            span_days = max(1, (d_last - d_first).days)
            if span_days >= 30 and metrics.final_capital > 0 and initial_capital > 0:
                cagr = ((metrics.final_capital / initial_capital) ** (365.25 / span_days) - 1.0) * 100.0
                metrics.cagr_pct = round(cagr, 2)
            else:
                metrics.cagr_pct = metrics.total_pnl_pct
        except Exception:
            metrics.cagr_pct = metrics.total_pnl_pct

        if metrics.max_drawdown_pct > 0:
            metrics.calmar_ratio = round(metrics.cagr_pct / metrics.max_drawdown_pct, 2)

        # Sharpe ratio: excess return over Indian T-Bill Rf (6.5% p.a.), sample std with ddof=1
        if n > 1:
            excess = [
                t.pnl_pct - (risk_free_rate_annual * (b / 252.0) * 100.0)
                for t, b in zip(ordered, hold_bars_list)
            ]
            std_ex = float(np.std(excess, ddof=1))
            if math.isfinite(std_ex) and std_ex > 1e-9:
                mean_ex = float(np.mean(excess))
                avg_bars = max(1.0, float(np.mean(hold_bars_list)))
                metrics.sharpe_ratio = round((mean_ex / std_ex) * math.sqrt(252.0 / avg_bars), 2)

        return metrics

    @staticmethod
    def _calculate_metrics(
        trades: List[Trade],
        initial_capital: float = DEFAULT_INITIAL_CAPITAL,
        risk_free_rate_annual: float = DEFAULT_RISK_FREE_ANNUAL,
        skipped_gap_entries: int = 0,
    ) -> BacktestMetrics:
        return BacktestEngine.calculate_portfolio_metrics(
            trades,
            initial_capital=initial_capital,
            risk_free_rate_annual=risk_free_rate_annual,
            skipped_gap_entries=skipped_gap_entries,
        )

    def compute_benchmark_comparison(
        self,
        start_date: str,
        end_date: str,
        strategy_return_pct: float,
        benchmarks: Tuple[str, ...] = ("^NSEI", "^CRSMID"),
    ) -> Dict[str, Any]:
        """Computes Nifty 50 (^NSEI) & Nifty Midcap 150 (^CRSMID) buy-and-hold return and strategy alpha."""
        labels = {"^NSEI": "Nifty 50", "^CRSMID": "Nifty Midcap 150"}
        out: Dict[str, Any] = {}
        any_avail = False
        for bm in benchmarks:
            rows = self.get_historical_data(bm, start_date, end_date)
            if len(rows) < 2:
                out[bm] = {"name": labels.get(bm, bm), "available": False}
                continue
            closes = [float(r["CLOSE_PRICE"]) for r in rows if float(r.get("CLOSE_PRICE") or 0) > 0]
            if len(closes) < 2:
                out[bm] = {"name": labels.get(bm, bm), "available": False}
                continue
            bm_ret = round(((closes[-1] - closes[0]) / closes[0]) * 100.0, 2)
            # Benchmark max drawdown %
            peak = closes[0]
            max_dd = 0.0
            for c in closes:
                if c > peak:
                    peak = c
                dd = (peak - c) / peak * 100.0 if peak > 0 else 0.0
                if dd > max_dd:
                    max_dd = dd
            any_avail = True
            out[bm] = {
                "name": labels.get(bm, bm),
                "available": True,
                "start_date": str(rows[0]["DATE"])[:10],
                "end_date": str(rows[-1]["DATE"])[:10],
                "return_pct": bm_ret,
                "max_drawdown_pct": round(max_dd, 2),
                "alpha_pct": round(float(strategy_return_pct) - bm_ret, 2),
            }
        return {"available": any_avail, "benchmarks": out}

    @staticmethod
    def _days_between(date1: str, date2: str) -> int:
        d1 = datetime.strptime(date1[:10], "%Y-%m-%d")
        d2 = datetime.strptime(date2[:10], "%Y-%m-%d")
        return abs((d2 - d1).days)


class BacktestComparator:
    """Compare backtest results vs benchmarks."""

    @staticmethod
    def buy_and_hold(data: List[Dict]) -> float:
        if not data or len(data) < 2:
            return 0.0
        entry = float(data[0]["CLOSE_PRICE"])
        exit_p = float(data[-1]["CLOSE_PRICE"])
        return round(((exit_p - entry) / entry) * 100.0, 2) if entry > 0 else 0.0

    @staticmethod
    def compare_strategies(strategy_pnl: float, benchmark_pnl: float) -> Dict:
        return {
            "strategy_return": round(strategy_pnl, 2),
            "benchmark_return": round(benchmark_pnl, 2),
            "outperformance": round(strategy_pnl - benchmark_pnl, 2),
            "alpha_pct": round(strategy_pnl - benchmark_pnl, 2),
            "outperformance_pct": round(((strategy_pnl - benchmark_pnl) / abs(benchmark_pnl)) * 100.0, 2) if benchmark_pnl != 0 else 0.0,
            "better": strategy_pnl > benchmark_pnl,
        }
