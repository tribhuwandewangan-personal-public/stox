# ✅ START HERE: Run Backtest in 5 Minutes

**All errors fixed!** Everything is ready. Follow these exact steps:

---

## Prerequisites (One-Time Setup)

```powershell
# Install required packages
pip install yfinance pandas openpyxl

# Verify installation
python -c "import yfinance, pandas; print('✅ Ready')"
```

---

## Step 1: Sync Historical Data (2 minutes)

```powershell
python tools/historical_data_tools.py --sync
```

**What it does:**
- Downloads 5 years of stock data from Yahoo Finance
- Saves to `stox.db` (SQLite database)
- Handles splits and dividends automatically

**Expected output:**
```
📥 Syncing reliable historical data for 10 symbols...
  [1/10] ✅ INFY     | 1200+ candles synced | Latest: 2026-11-08
  [2/10] ✅ TCS      | 1200+ candles synced | Latest: 2026-11-08
  ...
```

---

## Step 2: Generate Analysis Verdicts (2 minutes)

```powershell
python main.py --force
```

**What it does:**
- Runs multi-agent analysis on historical data
- Generates BUY/SELL/HOLD verdicts for each day
- Creates analysis summary

**Expected output:**
```
Processing symbol: INFY
Processing symbol: TCS
...
Analysis complete
```

---

## Step 3: Run Backtest (1 minute)

```powershell
python tools/backtest_runner.py `
  --start 2024-01-01 `
  --end 2026-11-10 `
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"
```

**What it does:**
- Tests all BUY/SELL signals from Step 2
- Calculates profit/loss for each trade
- Shows win rate and accuracy

**Expected output:**
```
Win Rate: 62%
Total Trades: 45
Winning: 28
Total P&L: +2,450

AGGREGATE:
  Total Trades: 45
  Win Rate: 62%
✅ Results saved to: backtest_results.json
```

---

## Step 4: Generate Beautiful Report (Instant)

```powershell
python tools/backtest_reporter.py backtest_results.json
```

**What it does:**
- Creates `backtest_report.html` with charts
- Shows best/worst trades
- Gives verdict: STRONG/GOOD/RISKY/POOR

**Then:** Open `backtest_report.html` in your browser!

---

## All 4 Steps (Copy & Paste)

```powershell
# Step 1: Sync data
python tools/historical_data_tools.py --sync

# Step 2: Generate verdicts
python main.py --force

# Step 3: Run backtest
python tools/backtest_runner.py `
  --start 2024-01-01 `
  --end 2026-11-10 `
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"

# Step 4: Generate report
python tools/backtest_reporter.py backtest_results.json

# Then open the HTML file
start backtest_report.html
```

**Total time: ~5-10 minutes**

---

## Interpreting Results

After report opens in browser, look for:

```
Win Rate: 62%  →  ✅ STRONG - Ready to trade
Win Rate: 57%  →  ✅ GOOD - Paper trade first
Win Rate: 52%  →  ⚠️ RISKY - Needs improvement
Win Rate: 45%  →  ❌ POOR - DO NOT TRADE
```

---

## Next Steps Based on Results

### If Win Rate > 55%

1. ✅ Paper trade for 2-4 weeks (simulate trades, no real money)
2. ✅ Track signals vs actual market prices
3. ✅ If paper profitable: Start live with 1-5% capital
4. ✅ Scale up slowly as confidence grows

### If Win Rate < 50%

1. ❌ **DO NOT TRADE REAL MONEY**
2. ❌ Analysis needs improvement
3. ❌ Try different parameters
4. ❌ Run backtest again after changes

---

## Troubleshooting

**Q: "No module named yfinance"**
```powershell
pip install yfinance
```

**Q: "sqlite3.OperationalError: no such table"**
A: Make sure Step 1 (sync) completed successfully

**Q: "No trades generated"**
A: Check Step 2 (main.py --force) completed, then try Step 3 again

**Q: Database locked?**
A: Close other Python processes, try again

---

## What Each File Does

| File | Purpose |
|------|---------|
| `historical_data_tools.py` | Downloads market data from Yahoo Finance |
| `main.py` | Runs analysis and generates BUY/SELL verdicts |
| `backtest_framework.py` | Core backtest engine |
| `backtest_runner.py` | Runs backtests on historical data |
| `backtest_reporter.py` | Generates HTML report |
| `stox.db` | SQLite database with prices & analysis |
| `backtest_results.json` | Raw backtest results (JSON) |
| `backtest_report.html` | Beautiful visual report (open in browser) |

---

## Summary

```
Your goal: Know if this app can make money

Method: Backtest on historical data
         (what would have happened if you followed the signals?)

Success if: Win rate > 55% on 2+ years of data

Time needed: ~5-10 minutes to find out

Let's go! Start with Step 1 above. 🚀
```

---

**Ready? Run this now:**
```powershell
python tools/historical_data_tools.py --sync
```

Then follow Steps 2-4 above. ✅
