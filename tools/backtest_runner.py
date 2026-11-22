#!/usr/bin/env python3
"""
Backtest Runner: Execute live-aligned deterministic backtests and export JSON results.

Usage:
    python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols INFY,TCS,RELIANCE
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_TOOLS_DIR = str(Path(__file__).resolve().parent)
_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from api.services import NaNSafeEncoder
from tools.backtest_framework import (
    BacktestEngine,
    BacktestMetrics,
    DEFAULT_INITIAL_CAPITAL,
    DEFAULT_ROUND_TRIP_COST_PCT,
)


def run_backtest_job(
    symbols: List[str],
    start_date: str,
    end_date: str,
    db_path: str = "stox.db",
    stop_loss_pct: float = 5.0,
    take_profit_pct: float = 10.0,
    hold_days: int = 20,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    round_trip_cost_pct: float = DEFAULT_ROUND_TRIP_COST_PCT,
    enable_patterns: bool = True,
    sync_benchmarks: bool = False,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Runs portfolio backtest across `symbols`, computes equal-capital metrics + NSE friction +
    benchmark alpha (^NSEI, ^CRSMID), handles 0-trade runs safely, and writes JSON if `output_path` is set.
    """
    engine = BacktestEngine(db_path=db_path)

    if sync_benchmarks:
        try:
            from storage.cache_manager import CacheManager
            from tools.historical_data_tools import HistoricalDataEngine
            HistoricalDataEngine(cache_manager=CacheManager(db_path=engine.db_path)).sync_benchmarks()
        except Exception:
            pass

    results = engine.backtest_portfolio(
        symbols,
        start_date,
        end_date,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        hold_days=hold_days,
        initial_capital=initial_capital,
        round_trip_cost_pct=round_trip_cost_pct,
        enable_patterns=enable_patterns,
    )

    all_trades = []
    total_skipped = 0
    for sym, (trades, metrics) in results.items():
        all_trades.extend(trades)
        total_skipped += metrics.skipped_gap_entries

    agg: BacktestMetrics = BacktestEngine.calculate_portfolio_metrics(
        all_trades,
        initial_capital=initial_capital,
        skipped_gap_entries=total_skipped,
    )

    # Zero-trade safe breakeven win rate
    avg_win = agg.avg_win
    avg_loss_abs = abs(agg.avg_loss)
    breakeven_wr = (
        round(avg_loss_abs / (avg_win + avg_loss_abs) * 100.0, 1)
        if (all_trades and (avg_win + avg_loss_abs) > 0)
        else 50.0
    )

    bench_comp = engine.compute_benchmark_comparison(start_date, end_date, agg.total_pnl_pct)

    output_data: Dict[str, Any] = {
        "metadata": {
            "start_date": start_date,
            "end_date": end_date,
            "symbols": symbols,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "hold_days": hold_days,
            "initial_capital": initial_capital,
            "round_trip_cost_pct": round_trip_cost_pct,
            "enable_patterns": enable_patterns,
            "execution_model": "t+1 Open (live deterministic engine)",
            "run_date": datetime.now().isoformat(),
        },
        "aggregate": {
            "total_trades": agg.total_trades,
            "winning_trades": agg.winning_trades,
            "losing_trades": agg.losing_trades,
            "win_rate": agg.win_rate,
            "avg_win_pct": round(agg.avg_win, 3),
            "avg_loss_pct": round(agg.avg_loss, 3),
            "expectancy_pct": agg.expectancy_pct,
            "profit_factor": agg.profit_factor,
            "breakeven_win_rate": breakeven_wr,
            "total_pnl": agg.total_pnl,
            "total_pnl_pct": agg.total_pnl_pct,
            "initial_capital": agg.initial_capital,
            "final_capital": agg.final_capital,
            "max_drawdown": agg.max_drawdown,
            "max_drawdown_pct": agg.max_drawdown_pct,
            "sharpe_ratio": agg.sharpe_ratio,
            "calmar_ratio": agg.calmar_ratio,
            "cagr_pct": agg.cagr_pct,
            "avg_hold_days": agg.avg_hold_days,
            "total_friction_rs": agg.total_friction_rs,
            "skipped_gap_entries": agg.skipped_gap_entries,
            "risk_free_rate_pct": agg.risk_free_rate_pct,
        },
        "benchmarks": bench_comp,
        "symbol_results": {
            symbol: {
                "total_trades": m.total_trades,
                "win_rate": m.win_rate,
                "expectancy_pct": m.expectancy_pct,
                "profit_factor": m.profit_factor,
                "total_pnl": m.total_pnl,
                "total_pnl_pct": m.total_pnl_pct,
                "max_drawdown_pct": m.max_drawdown_pct,
                "sharpe_ratio": m.sharpe_ratio,
                "avg_hold_days": m.avg_hold_days,
                "best_trade": m.best_trade,
                "worst_trade": m.worst_trade,
            }
            for symbol, (_, m) in results.items()
        },
        "trades": [
            {
                "symbol": t.symbol,
                "signal_date": t.signal_date,
                "entry_date": t.entry_date,
                "entry_price": t.entry_price,
                "exit_date": t.exit_date,
                "exit_price": t.exit_price,
                "shares": t.shares,
                "position_capital": t.position_capital,
                "days_held": t.days_held,
                "bars_held": t.bars_held,
                "gross_pnl_pct": t.gross_pnl_pct,
                "transaction_cost_rs": t.transaction_cost_rs,
                "transaction_cost_pct": t.transaction_cost_pct,
                "pnl_pct": t.pnl_pct,
                "pnl_abs": t.pnl_abs,
                "status": t.status,
            }
            for t in all_trades
        ],
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, cls=NaNSafeEncoder)

    return output_data


def main():
    parser = argparse.ArgumentParser(description="Run backtests on historical data")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--symbols", required=True, help="Comma-separated symbols (e.g., INFY,TCS)")
    parser.add_argument("--stop-loss", type=float, default=5.0, help="Fallback stop loss percentage (default: 5)")
    parser.add_argument("--take-profit", type=float, default=10.0, help="Fallback take profit percentage (default: 10)")
    parser.add_argument("--hold-days", type=int, default=20, help="Max hold bars (default: 20)")
    parser.add_argument("--capital", type=float, default=DEFAULT_INITIAL_CAPITAL, help="Initial equal-capital portfolio (Rs)")
    parser.add_argument("--cost-pct", type=float, default=DEFAULT_ROUND_TRIP_COST_PCT, help="Round-trip NSE delivery friction pct")
    parser.add_argument("--sync-benchmarks", action="store_true", help="Sync ^NSEI and ^CRSMID benchmarks before run")
    parser.add_argument("--no-patterns", action="store_true", help="Skip chart pattern scan inside bar loop for faster runs")
    parser.add_argument("--db", default="stox.db", help="SQLite database path")
    parser.add_argument("--output", default="backtest_results.json", help="Output JSON file")

    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    print(f"\n{'='*72}")
    print("  BACKTEST RUNNER - Live-Aligned Deterministic Engine Validation")
    print(f"{'='*72}")
    print(f"  Period: {args.start} -> {args.end} | Symbols: {', '.join(symbols)}")
    print(f"  Capital: Rs. {args.capital:,.0f} | Round-Trip Friction: {args.cost_pct:.2f}% | Max Hold: {args.hold_days} bars\n")

    output_data = run_backtest_job(
        symbols=symbols,
        start_date=args.start,
        end_date=args.end,
        db_path=args.db,
        stop_loss_pct=args.stop_loss,
        take_profit_pct=args.take_profit,
        hold_days=args.hold_days,
        initial_capital=args.capital,
        round_trip_cost_pct=args.cost_pct,
        enable_patterns=not args.no_patterns,
        sync_benchmarks=args.sync_benchmarks,
        output_path=args.output,
    )

    for sym, s_res in output_data["symbol_results"].items():
        print(
            f"  {sym:<12} | Trades: {s_res['total_trades']:3d} | WR: {s_res['win_rate']:5.1f}% | "
            f"Exp: {s_res['expectancy_pct']:+6.2f}% | PF: {s_res['profit_factor']:5.2f} | MaxDD: {s_res['max_drawdown_pct']:5.1f}%"
        )

    agg = output_data["aggregate"]
    print(f"\n{'-'*72}")
    if agg["total_trades"] == 0:
        print("  NO TRADES TRIGGERED across the selected period and universe.")
    else:
        print(
            f"  AGGREGATE | Trades: {agg['total_trades']} | Expectancy: {agg['expectancy_pct']:+.2f}% | "
            f"Profit Factor: {agg['profit_factor']:.2f} | Net Return: {agg['total_pnl_pct']:+.2f}% (Rs. {agg['total_pnl']:+,.0f})"
        )
        print(
            f"  RISK      | Max DD: {agg['max_drawdown_pct']:.2f}% | Sharpe (vs {agg['risk_free_rate_pct']}% T-Bill): {agg['sharpe_ratio']:.2f} | "
            f"Calmar: {agg['calmar_ratio']:.2f} | Friction: Rs. {agg['total_friction_rs']:,.0f}"
        )

    bms = (output_data.get("benchmarks") or {}).get("benchmarks") or {}
    for code, b_info in bms.items():
        if b_info.get("available"):
            print(
                f"  ALPHA vs {b_info['name']} ({code}): Benchmark {b_info['return_pct']:+.2f}% | Alpha {b_info['alpha_pct']:+.2f}%"
            )

    print(f"\n✅ Results saved to: {args.output}\n")


if __name__ == "__main__":
    main()
