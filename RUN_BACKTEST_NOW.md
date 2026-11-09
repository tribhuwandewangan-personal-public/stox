# Run Backtest Now (5 Minutes)

**Fixed!** The import errors are resolved. Here's how to validate if this app is profitable:

---

## Step 1: Sync Historical Data (2 min)

```powershell
python tools/historical_data_tools.py --sync
```

**What it does:**
- Downloads 5 years of stock data from Yahoo Finance
- Saves to SQLite database (`stox.db`)
- Takes ~2 minutes for 10 stocks

**If it works:**
✅ You'll see "✅ SYMBOL | XXXX candles synced" for each stock

---

## Step 2: Generate Analysis Verdicts (2 min)

```powershell
python main.py --force
```

**What it does:**
- Runs multi-agent analysis on historical data
- Generates BUY/SELL verdicts for each day
- Creates analysis summary

**If it works:**
✅ You'll see analysis progress messages

---

## Step 3: Run Backtest (1 min)

```powershell
python tools/backtest_runner.py `
  --start 2024-01-01 `
  --end 2026-11-10 `
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"
```

**What it does:**
- Tests analysis verdicts against historical prices
- Calculates P&L for each signal
- Shows win rate and accuracy

**Output:** `backtest_results.json` with all results

---

## Step 4: Generate HTML Report (instant)

```powershell
python tools/backtest_reporter.py backtest_results.json
```

**What it does:**
- Creates beautiful HTML report
- Shows charts and trade breakdown
- Gives verdict: STRONG/GOOD/RISKY/POOR

**Output:** `backtest_report.html` — Open in browser!

---

## Complete Example (Copy & Paste)

```powershell
# All 4 steps in order:
python tools/historical_data_tools.py --sync
python main.py --force
python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols "INFY,TCS,RELIANCE,ITC,HDFC"
python tools/backtest_reporter.py backtest_results.json

# Then open backtest_report.html in your browser
```

**Total time: ~5-10 minutes**

---

## What You're Looking For

```
Win Rate > 60%: ✅ STRONG → Ready to paper trade
Win Rate 55-60%: ✅ GOOD → Paper trade 2 weeks
Win Rate 50-55%: ⚠️ RISKY → Needs improvement
Win Rate < 50%: ❌ POOR → DO NOT TRADE
```

---

## Troubleshooting

**Q: "No module named yfinance"?**
A: Install it: `pip install yfinance pandas openpyxl`

**Q: No trades generated?**
A: Make sure Step 2 (python main.py --force) completed successfully

**Q: Database locked?**
A: Close other Python processes, then try again

**Q: Report shows 0 trades?**
A: Check if historical data was synced (Step 1) and analysis generated (Step 2)

---

## Next Steps After Report

- **If win_rate > 55%:** ✅ Paper trade for 2-4 weeks
- **If win_rate < 50%:** ❌ Do NOT trade real money yet

---

**Ready? Run Step 1 now: `python tools/historical_data_tools.py --sync`** 🚀
