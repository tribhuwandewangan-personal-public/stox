"""
Backtesting framework: Validate analysis engine profitability.
Runs historical analysis and tracks simulated P&L.
"""

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json

@dataclass
class Trade:
    """Single trade entry/exit"""
    symbol: str
    entry_date: str
    entry_price: float
    entry_verdict: str
    exit_date: Optional[str] = None
    exit_price: Optional[float] = None
    exit_verdict: Optional[str] = None
    days_held: int = 0
    pnl_pct: float = 0.0
    pnl_abs: float = 0.0
    status: str = "OPEN"  # OPEN, CLOSED, STOPPED_OUT

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
    profit_factor: float = 0.0  # Sum of wins / Sum of losses
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    avg_hold_days: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0

class BacktestEngine:
    """Core backtesting engine"""

    def __init__(self, db_path: str = "stox.db"):
        self.db_path = db_path
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        self.daily_returns: List[float] = []

    def get_historical_data(self, symbol: str, start_date: str, end_date: str) -> List[Dict]:
        """Fetch historical OHLCV data from SQLite"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT DATE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, CLOSE_PRICE, VOLUME
                FROM historical_data
                WHERE symbol = ? AND DATE BETWEEN ? AND ?
                ORDER BY DATE ASC
            """, (symbol, start_date, end_date))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()

    def get_analysis_signal(self, symbol: str, as_of_date: str) -> Optional[Dict]:
        """
        Get analysis verdict for symbol on specific date.
        Returns stored analysis or None if not found.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT synth_output, patterns, events
                FROM stocks
                WHERE symbol = ? AND as_of_date = ?
                LIMIT 1
            """, (symbol, as_of_date))

            row = cursor.fetchone()
            if not row:
                return None

            synth = json.loads(row['synth_output']) if row['synth_output'] else {}
            return {
                'verdict': synth.get('structured_signal', {}).get('action_verdict', 'PENDING'),
                'confidence': synth.get('structured_signal', {}).get('confidence_score', 0),
                'target': synth.get('structured_signal', {}).get('target_num'),
                'stop': synth.get('structured_signal', {}).get('stop_num'),
            }
        finally:
            conn.close()

    def backtest_symbol(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        stop_loss_pct: float = 5.0,
        take_profit_pct: float = 10.0,
        hold_days: int = 20
    ) -> Tuple[List[Trade], BacktestMetrics]:
        """
        Backtest a single symbol over date range.

        Args:
            symbol: Stock symbol
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD
            stop_loss_pct: Exit if down X%
            take_profit_pct: Exit if up X%
            hold_days: Max hold period before forced exit
        """

        data = self.get_historical_data(symbol, start_date, end_date)
        if not data:
            return [], BacktestMetrics()

        trades = []
        open_trade: Optional[Trade] = None

        for i, candle in enumerate(data):
            current_date = candle['DATE']
            current_price = candle['CLOSE_PRICE']

            # Check if open trade should close
            if open_trade:
                days_held = self._days_between(open_trade.entry_date, current_date)
                pnl_pct = ((current_price - open_trade.entry_price) / open_trade.entry_price) * 100

                # Check exit conditions
                should_close = False
                close_reason = ""

                # Stop loss
                if pnl_pct < -stop_loss_pct:
                    should_close = True
                    close_reason = "STOPPED_OUT"

                # Take profit
                if pnl_pct > take_profit_pct:
                    should_close = True
                    close_reason = "PROFIT_TARGET"

                # Hold period limit
                if days_held >= hold_days:
                    should_close = True
                    close_reason = "TIME_LIMIT"

                if should_close:
                    open_trade.exit_date = current_date
                    open_trade.exit_price = current_price
                    open_trade.days_held = days_held
                    open_trade.pnl_pct = pnl_pct
                    open_trade.pnl_abs = current_price - open_trade.entry_price
                    open_trade.status = close_reason
                    trades.append(open_trade)
                    open_trade = None

            # Check for new signal
            if not open_trade:
                signal = self.get_analysis_signal(symbol, current_date)
                if signal and signal['verdict'] in ['BUY', 'ACCUMULATE']:
                    open_trade = Trade(
                        symbol=symbol,
                        entry_date=current_date,
                        entry_price=current_price,
                        entry_verdict=signal['verdict']
                    )

        # Close any remaining open trade at end of period
        if open_trade:
            last_price = data[-1]['CLOSE_PRICE']
            last_date = data[-1]['DATE']
            pnl_pct = ((last_price - open_trade.entry_price) / open_trade.entry_price) * 100
            days_held = self._days_between(open_trade.entry_date, last_date)

            open_trade.exit_date = last_date
            open_trade.exit_price = last_price
            open_trade.days_held = days_held
            open_trade.pnl_pct = pnl_pct
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
        losing_trades = [t for t in trades if t.pnl_pct < 0]

        metrics.winning_trades = len(winning_trades)
        metrics.losing_trades = len(losing_trades)
        metrics.win_rate = (len(winning_trades) / len(trades)) * 100 if trades else 0

        metrics.total_pnl = sum(t.pnl_abs for t in trades)
        metrics.total_pnl_pct = (metrics.total_pnl / sum(t.entry_price for t in trades)) * 100 if trades else 0

        if winning_trades:
            metrics.avg_win = sum(t.pnl_pct for t in winning_trades) / len(winning_trades)
        if losing_trades:
            metrics.avg_loss = sum(t.pnl_pct for t in losing_trades) / len(losing_trades)

        total_wins = sum(t.pnl_abs for t in winning_trades)
        total_losses = abs(sum(t.pnl_abs for t in losing_trades))
        metrics.profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        metrics.avg_hold_days = sum(t.days_held for t in trades) / len(trades) if trades else 0
        metrics.best_trade = max((t.pnl_pct for t in trades), default=0)
        metrics.worst_trade = min((t.pnl_pct for t in trades), default=0)

        # Calculate max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for t in trades:
            cumulative += t.pnl_abs
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)
        metrics.max_drawdown = max_dd

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
