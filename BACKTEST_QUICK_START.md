# Backtest Quick Start (30 minutes to validation)

## Before You Trade Real Money

You MUST validate the analysis engine. This takes 30 minutes and will tell you if the app is profitable.

---

## The Plan

```
Step 1: Prepare Data (5 min)
  → python tools/historical_data_tools.py --sync

Step 2: Generate Verdicts (10 min)
  → python main.py --force

Step 3: Run Backtest (10 min)
  → python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols "INFY,TCS,RELIANCE"

Step 4: View Report (5 min)
  → Open backtest_report.html in browser

Step 5: Make Decision (instant)
  → If win_rate > 55%: Paper trade, then live
  → If win_rate < 50%: DO NOT TRADE
```

---

## Run It Now

```powershell
# Terminal 1: Prepare data
python tools/historical_data_tools.py --sync

# Terminal 2: Generate analysis
python main.py --force

# Terminal 3: Run backtest
python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols "INFY,TCS,RELIANCE,ITC,HDFC"

# View results
python tools/backtest_reporter.py backtest_results.json
# Open backtest_report.html in browser
```

---

## What You're Looking For

**Winning Results (Start Trading):**
```
Win Rate: 62%
Total Trades: 45
P&L: +2,450

✅ STRONG → Paper trade 2 weeks → Live trading (1-5% capital)
```

**Borderline Results (Be Cautious):**
```
Win Rate: 56%
Total Trades: 40
P&L: +1,200

✅ GOOD → Paper trade 4 weeks → Live trading (0.5-2% capital)
```

**Failing Results (Stop Immediately):**
```
Win Rate: 45%
Total Trades: 35
P&L: -2,000

❌ POOR → DO NOT TRADE REAL MONEY
```

---

## Parameters Explained

```
--start 2024-01-01      Start date for backtest
--end 2026-11-10        End date for backtest
--symbols "INFY,TCS"    Stocks to test (comma-separated)
--stop-loss 5.0         Exit if down 5% (default)
--take-profit 10.0      Exit if up 10% (default)
--hold-days 20          Max 20 days per trade (default)
```

---

## Common Issues

**Q: No trades generated?**
A: Run `python main.py --force` first to generate analysis verdicts

**Q: Database locked?**
A: Make sure other Python processes aren't running

**Q: Results look too good (>90% win rate)?**
A: Might be data errors. Test on longer period or different symbols.

**Q: Results look too bad (<40% win rate)?**
A: Try adjusting parameters or testing different time periods.

---

## Next: Paper Trading

If backtest shows > 55% win rate:

```
1. Run the app live: npx ng serve + python dashboard_server.py
2. For 2-4 weeks: Log every BUY/SELL signal
3. Track actual prices vs. verdicts
4. Calculate paper P&L
5. If profitable in paper: Start live with 1-5% capital
```

---

## The Golden Rule

> **Never trade real money without validating with backtesting first.**

This 30-minute exercise could save you from losing thousands.

---

**Ready? Start with Step 1 above! 🚀**
