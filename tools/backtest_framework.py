"""
Backtesting framework: Validate analysis engine profitability.
Runs historical analysis and tracks simulated P&L with structural risk management.
"""

import os
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import json
import pandas as pd
import numpy as np

@dataclass
class Trade:
    """Single trade entry/exit"""
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
    pnl_pct: float = 0.0
    pnl_abs: float = 0.0
    status: str = "OPEN"  # OPEN, PROFIT_TARGET, STOPPED_OUT, TIME_LIMIT, CLOSED_EOD

@dataclass
class BacktestMetrics:
    """Performance metrics"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    avg_hold_days: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

class BacktestEngine:
    """Core backtesting engine with automatic schema discovery and deterministic synthesis."""

    def __init__(self, db_path: str = "stox.db"):
        # Auto-detect database: if stox.db is missing or 0 bytes, fallback to storage/cache.db
        if (db_path == "stox.db" or not os.path.exists(db_path) or os.path.getsize(db_path) == 0) and os.path.exists("storage/cache.db"):
            self.db_path = "storage/cache.db"
        else:
            self.db_path = db_path
        self.trades: List[Trade] = []
        self._table_name = None
        self._indicators_cache: Dict[str, pd.DataFrame] = {}

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
        """Fetch historical OHLCV data from SQLite, supporting both schema naming conventions."""
        if not os.path.exists(self.db_path):
            return []
            
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            tbl = self._discover_table(conn)
            clean_sym = symbol.upper().replace(".NS", "")
            ns_sym = clean_sym + ".NS"

            if tbl == "historical_candles":
                cursor.execute("""
                    SELECT date as DATE, open as OPEN_PRICE, high as HIGH_PRICE,
                           low as LOW_PRICE, close as CLOSE_PRICE, volume as VOLUME
                    FROM historical_candles
                    WHERE (symbol = ? OR symbol = ?) AND date BETWEEN ? AND ?
                    ORDER BY date ASC
                """, (clean_sym, ns_sym, start_date, end_date))
            else:
                cursor.execute("""
                    SELECT DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
                    FROM historical_data
                    WHERE (symbol = ? OR symbol = ?) AND DATE BETWEEN ? AND ?
                    ORDER BY DATE ASC
                """, (clean_sym, ns_sym, start_date, end_date))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            return []
        finally:
            conn.close()

    def get_analysis_signal(self, symbol: str, as_of_date: str, candles_up_to_date: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        Get analysis verdict for symbol on specific date.
        1. Checks stored prediction_log / stocks table.
        2. If not found, dynamically synthesizes verdict from price history.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # 1. Check prediction_log if present
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
                        'verdict': row['verdict'],
                        'confidence': row['confidence_pct'],
                        'target': row['target'],
                        'stop': row['stop'],
                        'price': row['price_at_signal']
                    }

            # 2. Check legacy stocks table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT synth_output FROM stocks WHERE symbol = ? AND as_of_date = ? LIMIT 1
                """, (symbol.upper(), as_of_date))
                row = cursor.fetchone()
                if row and row['synth_output']:
                    synth = json.loads(row['synth_output'])
                    sig = synth.get('structured_signal', {})
                    return {
                        'verdict': sig.get('action_verdict', 'PENDING'),
                        'confidence': sig.get('confidence_percentage', 0),
                        'target': sig.get('short_term_target'),
                        'stop': sig.get('stop_loss'),
                    }
        except Exception:
            pass
        finally:
            conn.close()

        # 3. Dynamic synthesis if historical candles are provided
        if candles_up_to_date and len(candles_up_to_date) >= 30:
            return self._synthesize_signal_dynamically(symbol, candles_up_to_date)

        return None

    def _synthesize_signal_dynamically(self, symbol: str, candles: List[Dict]) -> Optional[Dict]:
        """Runs the deterministic synthesizer logic on the candle history up to current date.

        Entry gates (must ALL pass before scoring):
          1. Stage-2 regime: SMA-50 > SMA-200 AND SMA-50 trending up (slope > 0)
          2. RSI in healthy zone: 40–68 (not oversold dump, not overbought)
          3. RVOL >= 0.8 (not dead-volume drift)
        Then: score_evidence() >= ACCUMULATE_THRESHOLD with >= 2 support points.
        """
        try:
            from agents.synthesizer_agent import score_evidence, BUY_THRESHOLD, ACCUMULATE_THRESHOLD

            df = pd.DataFrame(candles)
            if df.empty or len(df) < 50:   # need 50 bars for SMA-50
                return None

            close = df['CLOSE_PRICE'].astype(float)
            high = df['HIGH_PRICE'].astype(float)
            low = df['LOW_PRICE'].astype(float)
            vol = df['VOLUME'].astype(float)

            lp = float(close.iloc[-1])
            sma50 = float(close.tail(50).mean())
            sma200 = float(close.tail(200).mean()) if len(close) >= 200 else float(close.mean())

            # ── Stage-2 pre-filter: SMA-50 must be above SMA-200 AND rising ──
            sma50_prev = float(close.tail(55).head(50).mean()) if len(close) >= 55 else sma50
            sma50_slope = sma50 - sma50_prev          # positive = rising
            if sma50 < sma200:                         # Stage-4: distribution / downtrend
                return None
            if sma50_slope <= 0:                       # SMA-50 flattening/falling
                return None

            # ── Price must be above SMA-50 (trend alignment) ──
            if lp < sma50 * 1.001:    # allow tiny tolerance for exact touch
                return None

            # ── Price must NOT be extended: within 12% of SMA-50 (avoid chasing) ──
            if lp > sma50 * 1.12:
                return None

            # Wilder RSI (14)
            diff = close.diff()
            gain = np.where(diff > 0, diff, 0.0)
            loss = np.where(diff < 0, -diff, 0.0)
            roll_gain = pd.Series(gain).tail(14).mean()
            roll_loss = pd.Series(loss).tail(14).mean()
            rsi_14 = 100.0 - (100.0 / (1.0 + (roll_gain / (roll_loss + 1e-9))))

            # ── RSI zone gate: skip oversold dumps and overbought chases ──
            if rsi_14 < 40 or rsi_14 > 68:
                return None

            # ATR 14
            prev_close = close.shift(1)
            tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
            atr_14 = float(tr.tail(14).mean()) if len(tr) >= 14 else lp * 0.025

            # RVOL (20-day average volume comparison)
            avg_vol_20 = float(vol.tail(20).mean()) if len(vol) >= 20 else None
            last_vol = float(vol.iloc[-1])
            rvol = round(last_vol / avg_vol_20, 2) if (avg_vol_20 and avg_vol_20 > 0) else None

            # ── RVOL gate: skip dead-volume drift ──
            if rvol is not None and rvol < 0.8:
                return None

            # 15-day Swing Low stop
            recent_low = float(low.tail(15).min()) if len(low) >= 15 else lp * 0.95
            raw_sl = min(recent_low * 0.995, lp - (1.8 * atr_14))
            risk_dist = max(0.01, lp - raw_sl)
            risk_pct = risk_dist / lp

            # Enforce noise buffer: 3.8%–7.5%
            if risk_pct < 0.038:
                sl = round(lp * 0.962, 2)
            elif risk_pct > 0.075:
                sl = round(lp * 0.925, 2)
            else:
                sl = round(raw_sl, 2)

            risk_amount = max(0.01, lp - sl)
            # Minimum 1:2.0 R:R target
            tp = round(lp + max(2.0 * risk_amount, 2.5 * atr_14), 2)

            raw_tech = {
                "last_price": lp,
                "sma_50": sma50,
                "sma_200": sma200,
                "sma_50_slope": sma50_slope,
                "rsi_14": rsi_14,
                "rvol": rvol,
                "atr_14": atr_14,
            }

            ev = score_evidence(lp, raw_tech, top_pattern=None)
            score = ev["score"]

            # Require true multi-signal confluence
            if score >= ACCUMULATE_THRESHOLD and ev["support_points"] >= 2:
                verdict = "BUY" if score >= BUY_THRESHOLD else "ACCUMULATE"
                return {
                    'verdict': verdict,
                    'confidence': ev["confidence_pct"],
                    'target': tp,
                    'stop': sl,
                    'price': lp
                }
        except Exception:
            pass
        return None

    def backtest_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        hold_days: int = 20,
        use_structural_levels: bool = True
    ) -> Tuple[List[Trade], BacktestMetrics]:
        """
        Backtest a single symbol over date range with structural risk-reward levels.
        """
        data = self.get_historical_data(symbol, start_date, end_date)
        if not data:
            return [], BacktestMetrics()

        trades = []
        open_trade: Optional[Trade] = None

        for i, candle in enumerate(data):
            current_date = candle['DATE']
            current_price = candle['CLOSE_PRICE']
            high_price = candle.get('HIGH_PRICE', current_price)
            low_price = candle.get('LOW_PRICE', current_price)

            # Check if open trade should close
            if open_trade:
                days_held = self._days_between(open_trade.entry_date, current_date)
                should_close = False
                close_reason = ""
                exit_price = current_price

                # 1. Structural stop / target check if available
                if use_structural_levels and open_trade.target_price and open_trade.stop_loss_price:
                    tgt = open_trade.target_price
                    sl = open_trade.stop_loss_price
                    
                    hit_stop = low_price <= sl
                    hit_target = high_price >= tgt

                    if hit_stop and hit_target:
                        should_close = True
                        close_reason = "STOPPED_OUT"
                        exit_price = sl
                    elif hit_stop:
                        should_close = True
                        close_reason = "STOPPED_OUT"
                        exit_price = sl
                    elif hit_target:
                        should_close = True
                        close_reason = "PROFIT_TARGET"
                        exit_price = tgt
                else:
                    # Percentage fallback
                    pnl_pct = ((current_price - open_trade.entry_price) / open_trade.entry_price) * 100
                    if pnl_pct < -stop_loss_pct:
                        should_close = True
                        close_reason = "STOPPED_OUT"
                        exit_price = current_price
                    elif pnl_pct > take_profit_pct:
                        should_close = True
                        close_reason = "PROFIT_TARGET"
                        exit_price = current_price

                # Max hold days limit
                if not should_close and days_held >= hold_days:
                    should_close = True
                    close_reason = "TIME_LIMIT"
                    exit_price = current_price

                if should_close:
                    open_trade.exit_date = current_date
                    open_trade.exit_price = exit_price
                    open_trade.days_held = days_held
                    open_trade.pnl_pct = ((exit_price - open_trade.entry_price) / open_trade.entry_price) * 100
                    open_trade.pnl_abs = exit_price - open_trade.entry_price
                    open_trade.status = close_reason
                    trades.append(open_trade)
                    open_trade = None

            # Check for new signal if not currently holding
            if not open_trade and i >= 20:
                history_so_far = data[:i+1]
                signal = self.get_analysis_signal(symbol, current_date, candles_up_to_date=history_so_far)
                if signal and signal['verdict'] in ['BUY', 'ACCUMULATE']:
                    target = signal.get('target')
                    stop = signal.get('stop')
                    if isinstance(target, str):
                        target = float(target.replace("Rs.", "").replace(",", "").strip())
                    if isinstance(stop, str):
                        stop = float(stop.replace("Rs.", "").replace(",", "").strip())

                    open_trade = Trade(
                        symbol=symbol,
                        entry_date=current_date,
                        entry_price=current_price,
                        entry_verdict=signal['verdict'],
                        target_price=target,
                        stop_loss_price=stop
                    )

        # Close any remaining open trade at end of period
        if open_trade:
            last_price = data[-1]['CLOSE_PRICE']
            last_date = data[-1]['DATE']
            days_held = self._days_between(open_trade.entry_date, last_date)

            open_trade.exit_date = last_date
            open_trade.exit_price = last_price
            open_trade.days_held = days_held
            open_trade.pnl_pct = ((last_price - open_trade.entry_price) / open_trade.entry_price) * 100
            open_trade.pnl_abs = last_price - open_trade.entry_price
            open_trade.status = "CLOSED_EOD"
            trades.append(open_trade)

        metrics = self._calculate_metrics(trades)
        return trades, metrics

    def backtest_portfolio(
        self,
        symbols: List[str],
        start_date: str,
        end_date: str,
        **kwargs
    ) -> Dict[str, Tuple[List[Trade], BacktestMetrics]]:
        """Backtest multiple symbols"""
        results = {}
        for symbol in symbols:
            trades, metrics = self.backtest_symbol(symbol, start_date, end_date, **kwargs)
            results[symbol] = (trades, metrics)
        return results

    @staticmethod
    def _calculate_metrics(trades: List[Trade]) -> BacktestMetrics:
        """Calculate performance metrics from trades"""
        metrics = BacktestMetrics()
        if not trades:
            return metrics

        metrics.total_trades = len(trades)
        winning_trades = [t for t in trades if t.pnl_pct > 0]
        losing_trades = [t for t in trades if t.pnl_pct <= 0]

        metrics.winning_trades = len(winning_trades)
        metrics.losing_trades = len(losing_trades)
        metrics.win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0

        metrics.total_pnl = sum(t.pnl_abs for t in trades)
        total_entry = sum(t.entry_price for t in trades)
        metrics.total_pnl_pct = (metrics.total_pnl / total_entry * 100) if total_entry > 0 else 0

        if winning_trades:
            metrics.avg_win = sum(t.pnl_pct for t in winning_trades) / len(winning_trades)
        if losing_trades:
            metrics.avg_loss = sum(t.pnl_pct for t in losing_trades) / len(losing_trades)

        total_wins = sum(t.pnl_abs for t in winning_trades)
        total_losses = abs(sum(t.pnl_abs for t in losing_trades))
        metrics.profit_factor = round(total_wins / total_losses, 2) if total_losses > 0 else float('inf')

        metrics.avg_hold_days = sum(t.days_held for t in trades) / len(trades) if trades else 0
        metrics.best_trade = max((t.pnl_pct for t in trades), default=0)
        metrics.worst_trade = min((t.pnl_pct for t in trades), default=0)

        # Max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for t in trades:
            cumulative += t.pnl_abs
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        metrics.max_drawdown = max_dd

        # Sharpe ratio approximation
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            std = float(np.std(returns))
            mean_ret = float(np.mean(returns))
            metrics.sharpe_ratio = round((mean_ret / (std + 1e-9)) * np.sqrt(252 / max(1, metrics.avg_hold_days)), 2)

        return metrics

    @staticmethod
    def _days_between(date1: str, date2: str) -> int:
        """Calculate days between two YYYY-MM-DD dates"""
        d1 = datetime.strptime(date1, "%Y-%m-%d")
        d2 = datetime.strptime(date2, "%Y-%m-%d")
        return abs((d2 - d1).days)


class BacktestComparator:
    """Compare backtest results vs benchmarks"""

    @staticmethod
    def buy_and_hold(data: List[Dict]) -> float:
        """Calculate buy-and-hold returns"""
        if not data or len(data) < 2:
            return 0
        entry = data[0]['CLOSE_PRICE']
        exit = data[-1]['CLOSE_PRICE']
        return ((exit - entry) / entry) * 100

    @staticmethod
    def compare_strategies(strategy_pnl: float, benchmark_pnl: float) -> Dict:
        """Compare strategy vs benchmark"""
        return {
            'strategy_return': strategy_pnl,
            'benchmark_return': benchmark_pnl,
            'outperformance': strategy_pnl - benchmark_pnl,
            'outperformance_pct': ((strategy_pnl - benchmark_pnl) / abs(benchmark_pnl)) * 100 if benchmark_pnl != 0 else 0,
            'better': strategy_pnl > benchmark_pnl
        }
