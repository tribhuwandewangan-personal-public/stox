#!/usr/bin/env python3
"""
Backtest runner: Execute backtests and generate reports.

Usage:
    python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols INFY,TCS,RELIANCE
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

from backtest_framework import BacktestEngine, BacktestComparator, BacktestMetrics

def main():
    parser = argparse.ArgumentParser(description="Run backtests on historical data")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols (e.g., INFY,TCS)")
    parser.add_argument("--stop-loss", type=float, default=5.0, help="Stop loss % (default: 5)")
    parser.add_argument("--take-profit", type=float, default=10.0, help="Take profit % (default: 10)")
    parser.add_argument("--hold-days", type=int, default=20, help="Max hold days (default: 20)")
    parser.add_argument("--db", default="stox.db", help="SQLite database path")
    parser.add_argument("--output", default="backtest_results.json", help="Output file")

    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]

    print(f"\n{'='*70}")
    print(f"  BACKTEST RUNNER - Analysis Engine Validation")
    print(f"{'='*70}\n")
    print(f"Parameters:")
    print(f"  Start Date:    {args.start}")
    print(f"  End Date:      {args.end}")
    print(f"  Symbols:       {', '.join(symbols)}")
    print(f"  Stop Loss:     {args.stop_loss}%")
    print(f"  Take Profit:   {args.take_profit}%")
    print(f"  Max Hold:      {args.hold_days} days")
    print(f"  Database:      {args.db}\n")

    # Initialize engine
    engine = BacktestEngine(db_path=args.db)

    # Run backtests
    print(f"Running backtests...")
    results = engine.backtest_portfolio(
        symbols,
        args.start,
        args.end,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        hold_days=args.hold_days
    )

    # Aggregate results
    all_trades = []
    aggregate_metrics = BacktestMetrics()

    for symbol, (trades, metrics) in results.items():
        all_trades.extend(trades)

        # Print symbol results
        print(f"\n{symbol}:")
        print(f"  Trades:        {metrics.total_trades}")
        print(f"  Win Rate:      {metrics.win_rate:.1f}%")
        print(f"  Total P&L:     {metrics.total_pnl:.2f} ({metrics.total_pnl_pct:.2f}%)")
        print(f"  Avg Hold:      {metrics.avg_hold_days:.0f} days")
        print(f"  Best/Worst:    +{metrics.best_trade:.2f}% / {metrics.worst_trade:.2f}%")

        # Aggregate
        aggregate_metrics.total_trades += metrics.total_trades
        aggregate_metrics.winning_trades += metrics.winning_trades
        aggregate_metrics.losing_trades += metrics.losing_trades
        aggregate_metrics.total_pnl += metrics.total_pnl

    # Print aggregate
    if aggregate_metrics.total_trades > 0:
        aggregate_metrics.win_rate = (aggregate_metrics.winning_trades / aggregate_metrics.total_trades) * 100
        print(f"\n{'-'*70}")
        print(f"AGGREGATE ({len(symbols)} symbols):")
        print(f"  Total Trades:   {aggregate_metrics.total_trades}")
        print(f"  Win Rate:       {aggregate_metrics.win_rate:.1f}%")
        print(f"  Winning:        {aggregate_metrics.winning_trades}")
        print(f"  Losing:         {aggregate_metrics.losing_trades}")
        print(f"  Total P&L:      {aggregate_metrics.total_pnl:.2f}")

        # Interpretation
        print(f"\n{'-'*70}")
        print(f"INTERPRETATION:")
        if aggregate_metrics.win_rate > 60:
            print(f"  ✅ STRONG: {aggregate_metrics.win_rate:.1f}% win rate is excellent for trading")
        elif aggregate_metrics.win_rate > 55:
            print(f"  ✅ GOOD: {aggregate_metrics.win_rate:.1f}% win rate is acceptable for trading")
        elif aggregate_metrics.win_rate > 50:
            print(f"  ⚠️  WEAK: {aggregate_metrics.win_rate:.1f}% win rate is risky but could work with good risk management")
        else:
            print(f"  ❌ POOR: {aggregate_metrics.win_rate:.1f}% win rate is not profitable - DO NOT TRADE")

        if aggregate_metrics.total_pnl > 0:
            print(f"  ✅ Backtest PROFITABLE: +{aggregate_metrics.total_pnl:.2f}")
        else:
            print(f"  ❌ Backtest UNPROFITABLE: {aggregate_metrics.total_pnl:.2f}")

    # Save results
    output_data = {
        "metadata": {
            "start_date": args.start,
            "end_date": args.end,
            "symbols": symbols,
            "stop_loss_pct": args.stop_loss,
            "take_profit_pct": args.take_profit,
            "hold_days": args.hold_days,
            "run_date": datetime.now().isoformat()
        },
        "aggregate": {
            "total_trades": aggregate_metrics.total_trades,
            "winning_trades": aggregate_metrics.winning_trades,
            "losing_trades": aggregate_metrics.losing_trades,
            "win_rate": aggregate_metrics.win_rate,
            "total_pnl": aggregate_metrics.total_pnl
        },
        "symbol_results": {
            symbol: {
                "total_trades": metrics.total_trades,
                "win_rate": metrics.win_rate,
                "total_pnl": metrics.total_pnl,
                "avg_hold_days": metrics.avg_hold_days,
                "best_trade": metrics.best_trade,
                "worst_trade": metrics.worst_trade
            }
            for symbol, (_, metrics) in results.items()
        },
        "trades": [
            {
                "symbol": t.symbol,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "days_held": t.days_held,
                "pnl_pct": t.pnl_pct,
                "pnl_abs": t.pnl_abs,
                "status": t.status
            }
            for t in all_trades
        ]
    }

    # Write results
    with open(args.output, 'w') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n✅ Results saved to: {args.output}\n")

if __name__ == "__main__":
    main()
