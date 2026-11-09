#!/usr/bin/env python3
"""
Backtest reporter: Generate detailed HTML reports from backtest results.

Usage:
    python tools/backtest_reporter.py backtest_results.json
"""

import json
import argparse
from datetime import datetime
from pathlib import Path

def generate_html_report(results: dict) -> str:
    """Generate HTML report from backtest results"""

    meta = results.get('metadata', {})
    agg = results.get('aggregate', {})
    symbol_results = results.get('symbol_results', {})
    trades = results.get('trades', [])

    # Win rate color
    win_rate = agg.get('win_rate', 0)
    if win_rate > 60:
        verdict = "✅ STRONG"
        color = "green"
    elif win_rate > 55:
        verdict = "✅ ACCEPTABLE"
        color = "green"
    elif win_rate > 50:
        verdict = "⚠️ RISKY"
        color = "orange"
    else:
        verdict = "❌ POOR"
        color = "red"

    # P&L color
    pnl = agg.get('total_pnl', 0)
    pnl_color = "green" if pnl > 0 else "red"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Backtest Report</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0a0e27;
                color: #fff;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
            }}
            h1 {{
                color: #38bdf8;
                border-bottom: 2px solid #38bdf8;
                padding-bottom: 10px;
            }}
            .section {{
                background: #1e293b;
                border: 1px solid #38bdf8;
                border-radius: 8px;
                padding: 20px;
                margin: 20px 0;
            }}
            .metric {{
                display: inline-block;
                margin: 10px 20px 10px 0;
            }}
            .metric-label {{
                font-size: 12px;
                color: #9ca3af;
                text-transform: uppercase;
            }}
            .metric-value {{
                font-size: 24px;
                font-weight: bold;
                color: #fff;
            }}
            .verdict {{
                padding: 8px 12px;
                border-radius: 4px;
                background: #{color};
                opacity: 0.2;
                display: inline-block;
                margin-top: 10px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }}
            th, td {{
                padding: 10px;
                text-align: left;
                border-bottom: 1px solid #334155;
            }}
            th {{
                background: #0f172a;
                font-weight: bold;
                color: #38bdf8;
            }}
            tr:hover {{
                background: #0f172a;
            }}
            .positive {{
                color: #10b981;
            }}
            .negative {{
                color: #ef4444;
            }}
            .warning {{
                background: #f59e0b;
                opacity: 0.1;
            }}
            .good {{
                background: #10b981;
                opacity: 0.1;
            }}
            .poor {{
                background: #ef4444;
                opacity: 0.1;
            }}
            .metadata {{
                font-size: 12px;
                color: #9ca3af;
                margin-top: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📊 Backtest Analysis Report</h1>

            <!-- Metadata -->
            <div class="section">
                <h3>Test Parameters</h3>
                <p>
                    <strong>Period:</strong> {meta.get('start_date')} to {meta.get('end_date')}<br>
                    <strong>Symbols:</strong> {', '.join(meta.get('symbols', []))}<br>
                    <strong>Stop Loss:</strong> {meta.get('stop_loss_pct')}%<br>
                    <strong>Take Profit:</strong> {meta.get('take_profit_pct')}%<br>
                    <strong>Max Hold:</strong> {meta.get('hold_days')} days
                </p>
            </div>

            <!-- Aggregate Results -->
            <div class="section">
                <h3>Overall Performance</h3>
                <div class="metric">
                    <div class="metric-label">Win Rate</div>
                    <div class="metric-value">{win_rate:.1f}%</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total Trades</div>
                    <div class="metric-value">{agg.get('total_trades', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Winning</div>
                    <div class="metric-value positive">{agg.get('winning_trades', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Losing</div>
                    <div class="metric-value negative">{agg.get('losing_trades', 0)}</div>
                </div>
                <div class="metric">
                    <div class="metric-label">Total P&L</div>
                    <div class="metric-value {pnl_color}">{pnl:+.2f}</div>
                </div>
                <div class="verdict">{verdict}</div>
            </div>

            <!-- Verdict Interpretation -->
            <div class="section">
                <h3>📋 Verdict</h3>
    """

    if win_rate > 60:
        html += """
                <p><strong style="color: #10b981;">✅ STRONG PERFORMANCE</strong></p>
                <ul>
                    <li>Win rate > 60% is excellent for trading</li>
                    <li>Analysis engine shows strong predictive power</li>
                    <li>Ready for paper trading (risk-free)</li>
                    <li>Can proceed to live trading with proper position sizing</li>
                </ul>
        """
    elif win_rate > 55:
        html += """
                <p><strong style="color: #10b981;">✅ GOOD PERFORMANCE</strong></p>
                <ul>
                    <li>Win rate 55-60% is acceptable for profitable trading</li>
                    <li>Analysis engine shows decent predictive power</li>
                    <li>Recommend paper trading for 2-4 weeks first</li>
                    <li>Use conservative position sizing (1-2% per trade)</li>
                </ul>
        """
    elif win_rate > 50:
        html += """
                <p><strong style="color: #f59e0b;">⚠️ RISKY PERFORMANCE</strong></p>
                <ul>
                    <li>Win rate 50-55% is at break-even threshold</li>
                    <li>Analysis engine may need refinement</li>
                    <li>STRONGLY recommend paper trading before live</li>
                    <li>Use very conservative position sizing (0.5-1% per trade)</li>
                    <li>Consider improving analysis logic or parameters</li>
                </ul>
        """
    else:
        html += """
                <p><strong style="color: #ef4444;">❌ POOR PERFORMANCE</strong></p>
                <ul>
                    <li>Win rate < 50% means losing strategy</li>
                    <li><strong>DO NOT TRADE REAL MONEY</strong></li>
                    <li>Analysis engine needs significant improvement</li>
                    <li>Recommend:</li>
                    <li>  - Review analysis logic (patterns, indicators)</li>
                    <li>  - Check data quality for errors</li>
                    <li>  - Adjust parameters (stop loss, take profit)</li>
                    <li>  - Test on different time periods</li>
                    <li>  - Consider alternative analysis methods</li>
                </ul>
        """

    html += """
            </div>

            <!-- Symbol-Level Results -->
            <div class="section">
                <h3>Results by Symbol</h3>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>P&L</th>
                        <th>Avg Hold (days)</th>
                        <th>Best/Worst</th>
                    </tr>
    """

    for symbol, data in sorted(symbol_results.items()):
        wr = data.get('win_rate', 0)
        pnl = data.get('total_pnl', 0)
        pnl_class = "positive" if pnl > 0 else "negative"
        wr_class = "good" if wr > 55 else "warning" if wr > 50 else "poor"

        html += f"""
                    <tr>
                        <td><strong>{symbol}</strong></td>
                        <td>{data.get('total_trades', 0)}</td>
                        <td class="{wr_class}">{wr:.1f}%</td>
                        <td class="{pnl_class}">{pnl:+.2f}</td>
                        <td>{data.get('avg_hold_days', 0):.0f}</td>
                        <td>{data.get('best_trade', 0):+.1f}% / {data.get('worst_trade', 0):+.1f}%</td>
                    </tr>
        """

    html += """
                </table>
            </div>

            <!-- Top Trades -->
            <div class="section">
                <h3>Best & Worst Trades</h3>
                <h4>Top 5 Winners</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Entry Date</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>Gain %</th>
                        <th>Days Held</th>
                    </tr>
    """

    # Sort trades by P&L
    sorted_trades = sorted(trades, key=lambda t: t.get('pnl_pct', 0), reverse=True)
    for trade in sorted_trades[:5]:
        html += f"""
                    <tr class="good">
                        <td>{trade['symbol']}</td>
                        <td>{trade['entry_date']}</td>
                        <td>{trade['entry_price']:.2f}</td>
                        <td>{trade['exit_price']:.2f}</td>
                        <td class="positive">{trade['pnl_pct']:+.2f}%</td>
                        <td>{trade['days_held']}</td>
                    </tr>
        """

    html += """
                </table>

                <h4>Top 5 Losers</h4>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Entry Date</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>Loss %</th>
                        <th>Days Held</th>
                    </tr>
    """

    for trade in sorted_trades[-5:]:
        html += f"""
                    <tr class="poor">
                        <td>{trade['symbol']}</td>
                        <td>{trade['entry_date']}</td>
                        <td>{trade['entry_price']:.2f}</td>
                        <td>{trade['exit_price']:.2f}</td>
                        <td class="negative">{trade['pnl_pct']:+.2f}%</td>
                        <td>{trade['days_held']}</td>
                    </tr>
        """

    html += f"""
                </table>
            </div>

            <div class="metadata">
                <p>Report generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                <p><strong>Disclaimer:</strong> Past performance does not guarantee future results. Always use proper risk management and never trade more than you can afford to lose.</p>
            </div>
        </div>
    </body>
    </html>
    """

    return html

def main():
    parser = argparse.ArgumentParser(description="Generate HTML backtest report")
    parser.add_argument("input", help="Backtest results JSON file")
    parser.add_argument("--output", default="backtest_report.html", help="Output HTML file")

    args = parser.parse_args()

    # Load results
    with open(args.input) as f:
        results = json.load(f)

    # Generate HTML
    html = generate_html_report(results)

    # Save
    with open(args.output, 'w') as f:
        f.write(html)

    print(f"✅ Report saved to: {args.output}")
    print(f"   Open in browser to view results")

if __name__ == "__main__":
    main()
