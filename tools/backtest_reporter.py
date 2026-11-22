#!/usr/bin/env python3
"""
Backtest Reporter: Generate Expectancy, Risk & Benchmark-Aware HTML Reports.

Usage:
    python tools/backtest_reporter.py backtest_results.json
"""

import argparse
import html as _html
import json
from datetime import datetime
from typing import Any, Dict, List


def grade_backtest_performance(agg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Grades strategy credibility using net expectancy, profit factor, max drawdown %,
    Sharpe ratio, and sample size (never penalizes trend-following strategies merely
    for < 50% win rate when R:R and expectancy are strong).
    """
    n = int(agg.get("total_trades") or 0)
    exp = float(agg.get("expectancy_pct") or 0.0)
    pf = float(agg.get("profit_factor") or 0.0)
    max_dd = float(agg.get("max_drawdown_pct") or 0.0)
    sharpe = float(agg.get("sharpe_ratio") or 0.0)

    if n == 0:
        return {
            "grade": "NO_TRADES",
            "verdict": "⚪ NO TRADES",
            "headline": "No actionable entries triggered in the tested window.",
            "color": "#94a3b8",
            "sample_warning": False,
        }

    sample_warning = n < 20
    if exp > 0.75 and pf >= 1.50 and max_dd <= 20.0:
        grade, verdict, color = "STRONG", "✅ STRONG", "#10b981"
        headline = f"Positive net expectancy ({exp:+.2f}%/trade), Profit Factor {pf:.2f}, controlled {max_dd:.1f}% max drawdown."
    elif exp > 0.15 and pf >= 1.15:
        grade, verdict, color = "GOOD", "✅ GOOD", "#10b981"
        headline = f"Profitable risk-reward asymmetry (Expectancy {exp:+.2f}%/trade, Profit Factor {pf:.2f}, Sharpe {sharpe:.2f})."
    elif exp > 0.0 and pf >= 1.0:
        grade, verdict, color = "MARGINAL", "⚠️ MARGINAL", "#f59e0b"
        headline = f"Slim positive edge after friction (Expectancy {exp:+.2f}%, PF {pf:.2f}) — monitor slippage closely."
    else:
        grade, verdict, color = "POOR", "❌ POOR", "#ef4444"
        headline = f"Negative net expectancy ({exp:+.2f}%/trade, PF {pf:.2f}) after transaction costs."

    return {
        "grade": grade,
        "verdict": verdict,
        "headline": headline,
        "color": color,
        "sample_warning": sample_warning,
    }


def generate_html_report(results: Dict[str, Any]) -> str:
    """Generates a self-contained HTML backtest report with expectancy, risk & benchmark alpha."""
    meta = results.get("metadata", {})
    agg = results.get("aggregate", {})
    symbol_results = results.get("symbol_results", {})
    trades: List[Dict[str, Any]] = results.get("trades", [])
    bm_wrap = results.get("benchmarks") or {}
    bm_map = bm_wrap.get("benchmarks") or {}

    graded = grade_backtest_performance(agg)
    win_rate = float(agg.get("win_rate") or 0.0)
    breakeven_wr = float(agg.get("breakeven_win_rate") or 50.0)
    exp = float(agg.get("expectancy_pct") or 0.0)
    pf = float(agg.get("profit_factor") or 0.0)
    max_dd_pct = float(agg.get("max_drawdown_pct") or 0.0)
    sharpe = float(agg.get("sharpe_ratio") or 0.0)
    calmar = float(agg.get("calmar_ratio") or 0.0)
    pnl = float(agg.get("total_pnl") or 0.0)
    pnl_pct = float(agg.get("total_pnl_pct") or 0.0)
    friction_rs = float(agg.get("total_friction_rs") or 0.0)
    pnl_class = "positive" if pnl >= 0 else "negative"

    sample_note_html = (
        "<p class='note-warn'>⚠️ Small sample size (&lt; 20 trades): treat metrics as exploratory only.</p>"
        if graded["sample_warning"]
        else ""
    )

    doc = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Backtest Analysis Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0a0e27; color: #e2e8f0; margin: 0; padding: 20px; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #38bdf8; border-bottom: 2px solid #38bdf8; padding-bottom: 10px; }}
        .section {{ background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; margin: 20px 0; }}
        .metric {{ display: inline-block; margin: 10px 24px 10px 0; vertical-align: top; }}
        .metric-label {{ font-size: 11px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.04em; }}
        .metric-value {{ font-size: 22px; font-weight: 700; color: #f8fafc; }}
        .verdict-pill {{ padding: 8px 14px; border-radius: 6px; border: 1px solid {graded['color']}; color: {graded['color']}; display: inline-block; margin-top: 10px; font-weight: 700; }}
        .note-warn {{ color: #fbbf24; font-weight: 600; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #334155; }}
        th {{ background: #0f172a; font-weight: 600; color: #38bdf8; }}
        tr:hover {{ background: #0f172a; }}
        .positive {{ color: #10b981; font-weight: 600; }}
        .negative {{ color: #ef4444; font-weight: 600; }}
        .metadata {{ font-size: 12px; color: #94a3b8; margin-top: 20px; }}
    </style>
</head>
<body>
<div class="container">
    <h1>📊 Live-Aligned Backtest Analysis Report</h1>

    <div class="section">
        <h3>Test Parameters</h3>
        <p>
            <strong>Period:</strong> {_html.escape(str(meta.get('start_date', 'N/A')))} to {_html.escape(str(meta.get('end_date', 'N/A')))}<br>
            <strong>Symbols:</strong> {_html.escape(', '.join(meta.get('symbols', [])))}<br>
            <strong>Execution:</strong> {_html.escape(str(meta.get('execution_model', 't+1 Open')))} |
            <strong>Initial Capital:</strong> Rs. {float(meta.get('initial_capital') or 1000000):,.0f} |
            <strong>NSE Friction:</strong> {float(meta.get('round_trip_cost_pct') or 0.40):.2f}% |
            <strong>Max Hold:</strong> {int(meta.get('hold_days') or 20)} bars
        </p>
    </div>

    <div class="section">
        <h3>Expectancy, Risk & Performance Summary</h3>
        <div class="metric"><div class="metric-label">Expectancy / Trade</div><div class="metric-value {'positive' if exp > 0 else 'negative'}">{exp:+.2f}%</div></div>
        <div class="metric"><div class="metric-label">Profit Factor</div><div class="metric-value">{pf:.2f}</div></div>
        <div class="metric"><div class="metric-label">Net Return (Portfolio)</div><div class="metric-value {pnl_class}">{pnl_pct:+.2f}% (Rs. {pnl:+,.0f})</div></div>
        <div class="metric"><div class="metric-label">Max Drawdown %</div><div class="metric-value negative">{max_dd_pct:.2f}%</div></div>
        <div class="metric"><div class="metric-label">Sharpe (vs {float(agg.get('risk_free_rate_pct') or 6.5):.1f}% T-Bill)</div><div class="metric-value">{sharpe:.2f}</div></div>
        <div class="metric"><div class="metric-label">Calmar Ratio</div><div class="metric-value">{calmar:.2f}</div></div>
        <div class="metric"><div class="metric-label">Win Rate (BE: {breakeven_wr:.1f}%)</div><div class="metric-value">{win_rate:.1f}% ({int(agg.get('total_trades') or 0)} trades)</div></div>
        <div class="metric"><div class="metric-label">Total Friction</div><div class="metric-value">Rs. {friction_rs:,.0f}</div></div>
        <div><span class="verdict-pill">{graded['verdict']}</span> &nbsp; <span>{_html.escape(graded['headline'])}</span></div>
        {sample_note_html}
    </div>
"""

    if bm_map:
        doc += """
    <div class="section">
        <h3>Benchmark Alpha Comparison</h3>
        <table>
            <tr><th>Benchmark</th><th>Period</th><th>Benchmark Return</th><th>Benchmark Max DD</th><th>Strategy Alpha</th></tr>
"""
        for code, b_info in bm_map.items():
            if not b_info.get("available"):
                doc += f"            <tr><td><strong>{_html.escape(str(b_info.get('name', code)))}</strong> ({_html.escape(code)})</td><td colspan='4'>Benchmark history unavailable in local cache</td></tr>\n"
            else:
                al = float(b_info.get("alpha_pct") or 0.0)
                al_cls = "positive" if al >= 0 else "negative"
                doc += (
                    f"            <tr><td><strong>{_html.escape(str(b_info.get('name', code)))}</strong> ({_html.escape(code)})</td>"
                    f"<td>{_html.escape(str(b_info.get('start_date')))} -> {_html.escape(str(b_info.get('end_date')))}</td>"
                    f"<td>{float(b_info.get('return_pct') or 0):+.2f}%</td>"
                    f"<td>{float(b_info.get('max_drawdown_pct') or 0):.2f}%</td>"
                    f"<td class='{al_cls}'>{al:+.2f}%</td></tr>\n"
                )
        doc += "        </table>\n    </div>\n"

    doc += """
    <div class="section">
        <h3>Results by Symbol</h3>
        <table>
            <tr><th>Symbol</th><th>Trades</th><th>Win Rate</th><th>Expectancy</th><th>Profit Factor</th><th>Net P&L (Rs.)</th><th>Max DD %</th><th>Avg Hold (days)</th></tr>
"""
    for symbol, data in sorted(symbol_results.items()):
        wr = float(data.get("win_rate") or 0.0)
        s_exp = float(data.get("expectancy_pct") or 0.0)
        s_pf = float(data.get("profit_factor") or 0.0)
        s_pnl = float(data.get("total_pnl") or 0.0)
        s_cls = "positive" if s_exp > 0 else "negative"
        doc += (
            f"            <tr><td><strong>{_html.escape(symbol)}</strong></td><td>{int(data.get('total_trades') or 0)}</td>"
            f"<td>{wr:.1f}%</td><td class='{s_cls}'>{s_exp:+.2f}%</td><td>{s_pf:.2f}</td>"
            f"<td class='{s_cls}'>Rs. {s_pnl:+,.0f}</td><td>{float(data.get('max_drawdown_pct') or 0):.2f}%</td>"
            f"<td>{float(data.get('avg_hold_days') or 0):.1f}</td></tr>\n"
        )
    doc += "        </table>\n    </div>\n"

    if trades:
        sorted_trades = sorted(trades, key=lambda t: t.get("pnl_pct", 0), reverse=True)
        doc += """
    <div class="section">
        <h3>Top 5 Winners & Bottom 5 Trades (Net After Friction)</h3>
        <h4>Top 5 Winners</h4>
        <table><tr><th>Symbol</th><th>Entry Date</th><th>Entry</th><th>Exit</th><th>Net %</th><th>Hold (days)</th><th>Status</th></tr>
"""
        for t in sorted_trades[:5]:
            doc += (
                f"            <tr><td>{_html.escape(str(t['symbol']))}</td><td>{_html.escape(str(t['entry_date']))}</td>"
                f"<td>{float(t['entry_price']):.2f}</td><td>{float(t['exit_price']):.2f}</td>"
                f"<td class='positive'>{float(t['pnl_pct']):+.2f}%</td><td>{int(t.get('days_held') or 0)}</td>"
                f"<td>{_html.escape(str(t.get('status') or ''))}</td></tr>\n"
            )
        doc += "        </table>\n        <h4>Bottom 5 Trades</h4>\n        <table><tr><th>Symbol</th><th>Entry Date</th><th>Entry</th><th>Exit</th><th>Net %</th><th>Hold (days)</th><th>Status</th></tr>\n"
        for t in sorted_trades[-5:]:
            cls = "negative" if float(t.get("pnl_pct") or 0) <= 0 else "positive"
            doc += (
                f"            <tr><td>{_html.escape(str(t['symbol']))}</td><td>{_html.escape(str(t['entry_date']))}</td>"
                f"<td>{float(t['entry_price']):.2f}</td><td>{float(t['exit_price']):.2f}</td>"
                f"<td class='{cls}'>{float(t['pnl_pct']):+.2f}%</td><td>{int(t.get('days_held') or 0)}</td>"
                f"<td>{_html.escape(str(t.get('status') or ''))}</td></tr>\n"
            )
        doc += "        </table>\n    </div>\n"

    doc += f"""
    <div class="metadata">
        <p>Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p><strong>Advisory Disclaimer:</strong> Strictly read-only quantitative validation. Past simulated performance does not guarantee future results.</p>
    </div>
</div>
</body>
</html>"""
    return doc


def main():
    parser = argparse.ArgumentParser(description="Generate HTML backtest report")
    parser.add_argument("input", help="Backtest results JSON file")
    parser.add_argument("--output", default="backtest_report.html", help="Output HTML file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        results = json.load(f)

    html = generate_html_report(results)
    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"✅ Report saved to: {args.output}")


if __name__ == "__main__":
    main()
