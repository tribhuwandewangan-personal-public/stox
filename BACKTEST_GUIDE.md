# Backtest Framework Guide

**Purpose:** Validate whether the analysis engine actually makes profitable trading signals  
**Status:** Ready to use  
**Time to run:** 5-30 minutes (depending on data size)

---

## 🚀 Quick Start

### Step 1: Prepare Historical Data

First, ensure you have historical data in SQLite:

```powershell
python tools/historical_data_tools.py --sync
```

This populates `stox.db` with OHLCV data for all symbols in `symbols.json`.

### Step 2: Run Analysis on Historical Data

Generate analysis verdicts (BUY/SELL) for each date:

```powershell
python main.py --force
```

This populates the `stocks` table with analysis results for all dates.

### Step 3: Run Backtest

Test the analysis accuracy:

```powershell
# Default: Last 2 years, top symbols
python tools/backtest_runner.py ^
  --start 2024-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"

# Or: Test all symbols, custom parameters
python tools/backtest_runner.py ^
  --start 2023-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC,LT,MARUTI,WIPRO,BAJAJFINSV,AXISBANK" ^
  --stop-loss 7.5 ^
  --take-profit 15.0 ^
  --hold-days 30
```

This generates `backtest_results.json` with all trades and metrics.

### Step 4: Generate Report

Create an HTML report:

```powershell
python tools/backtest_reporter.py backtest_results.json
```

This creates `backtest_report.html` — open in your browser to see detailed analysis.

---

## 📊 Understanding Results

### Key Metrics

| Metric | Meaning | Target |
|--------|---------|--------|
| **Win Rate** | % of profitable trades | > 55% |
| **Total Trades** | Number of signals | > 20 |
| **Total P&L** | Total profit/loss | > 0 |
| **Avg Hold** | Average days per trade | 5-30 |
| **Best/Worst** | Best/worst single trade | Worst > -10% |

### Verdict Thresholds

- **Win Rate > 60%:** ✅ STRONG — Ready for trading
- **Win Rate 55-60%:** ✅ GOOD — Paper trade first
- **Win Rate 50-55%:** ⚠️ RISKY — Need improvements
- **Win Rate < 50%:** ❌ POOR — DO NOT TRADE

---

## 🔧 Advanced Usage

### Test Different Parameters

```powershell
# Conservative (wider stops, longer holds)
python tools/backtest_runner.py ^
  --start 2024-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY,TCS,RELIANCE" ^
  --stop-loss 10.0 ^
  --take-profit 20.0 ^
  --hold-days 45 ^
  --output backtest_conservative.json
```

```powershell
# Aggressive (tight stops, quick exits)
python tools/backtest_runner.py ^
  --start 2024-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY,TCS,RELIANCE" ^
  --stop-loss 3.0 ^
  --take-profit 5.0 ^
  --hold-days 10 ^
  --output backtest_aggressive.json
```

### Test Single Symbol

```powershell
python tools/backtest_runner.py ^
  --start 2024-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY"
```

### Test Long-Term (Multiple Years)

```powershell
python tools/backtest_runner.py ^
  --start 2021-01-01 ^
  --end 2026-11-10 ^
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"
```

---

## 📈 Example Workflow

```powershell
# Week 1: Prepare and validate
python tools/historical_data_tools.py --sync
python main.py --force

# Week 2: Test different time periods
python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols "INFY,TCS" --output backtest_2024_2026.json
python tools/backtest_runner.py --start 2023-01-01 --end 2023-12-31 --symbols "INFY,TCS" --output backtest_2023.json

# Generate reports
python tools/backtest_reporter.py backtest_2024_2026.json
python tools/backtest_reporter.py backtest_2023.json

# Week 3: Compare results and make decision
# If win_rate > 55%: Ready for paper trading
# If win_rate < 50%: Need to improve analysis
```

---

## 🎯 Interpretation Guide

### Example 1: Strong Results ✅

```
Backtest Results:
- Period: 2024-01-01 to 2026-11-10
- Symbols: INFY, TCS, RELIANCE
- Total Trades: 45
- Win Rate: 62%
- Winning: 28
- Losing: 17
- Total P&L: +2,450

Verdict: ✅ STRONG
Action: Ready for paper trading → then live trading (1-5% capital)
```

### Example 2: Acceptable Results ⚠️

```
Backtest Results:
- Period: 2024-01-01 to 2026-11-10
- Symbols: INFY, TCS, RELIANCE
- Total Trades: 40
- Win Rate: 57%
- Winning: 23
- Losing: 17
- Total P&L: +1,200

Verdict: ✅ GOOD
Action: Paper trade for 2-4 weeks → then live trading (0.5-2% capital)
```

### Example 3: Risky Results ⚠️

```
Backtest Results:
- Period: 2024-01-01 to 2026-11-10
- Symbols: INFY, TCS, RELIANCE
- Total Trades: 35
- Win Rate: 52%
- Winning: 18
- Losing: 17
- Total P&L: +150

Verdict: ⚠️ RISKY
Action: Improve analysis → Test different parameters → Paper trade longer
```

### Example 4: Poor Results ❌

```
Backtest Results:
- Period: 2024-01-01 to 2026-11-10
- Symbols: INFY, TCS, RELIANCE
- Total Trades: 30
- Win Rate: 43%
- Winning: 13
- Losing: 17
- Total P&L: -2,000

Verdict: ❌ POOR
Action: DO NOT TRADE - Review analysis logic, check data quality, try different approach
```

---

## 🔍 Troubleshooting

### Issue: No trades generated

**Cause:** Historical data or analysis verdicts missing  
**Solution:**
```powershell
# 1. Check historical data exists
python -c "import sqlite3; conn = sqlite3.connect('stox.db'); c = conn.cursor(); c.execute('SELECT COUNT(*) FROM historical_data'); print(f'Records: {c.fetchone()[0]}')"

# 2. Run analysis to generate verdicts
python main.py --force

# 3. Try again
python tools/backtest_runner.py --start 2024-01-01 --end 2026-11-10 --symbols "INFY"
```

### Issue: Win rate suspiciously high (>90%)

**Cause:** Look-ahead bias or data issues  
**Check:**
- Are entry and exit dates correct?
- Is data free of gaps?
- Are verdicts generated before trade entry?

### Issue: Win rate too low (<40%)

**Cause:** Parameters may be wrong  
**Try:**
- Increase take-profit target (10% → 15%)
- Increase stop-loss limit (5% → 10%)
- Increase hold period (20 → 30 days)
- Test different time periods

---

## 📚 Next Steps After Backtesting

### If Win Rate > 55%

1. ✅ Paper trade for 2-4 weeks
2. ✅ Log all signals and actual prices
3. ✅ Compare paper trades vs market
4. ✅ If paper profitable: Start live with 1-5% capital
5. ✅ Scale up slowly (5% → 10% → 25%)

### If Win Rate 50-55%

1. ⚠️ Experiment with different parameters
2. ⚠️ Test on different time periods
3. ⚠️ Improve analysis logic if possible
4. ⚠️ Longer paper trading (4-8 weeks)
5. ⚠️ Only start live if consistently profitable in paper

### If Win Rate < 50%

1. ❌ **DO NOT TRADE REAL MONEY**
2. ❌ Review analysis engine
3. ❌ Check data quality
4. ❌ Try alternative approaches
5. ❌ Retest after improvements

---

## 💡 Tips for Best Results

1. **Use sufficient data:** Backtest on 2+ years (includes different market conditions)
2. **Test multiple symbols:** Not just INFY, include mid-cap and small-cap
3. **Try different parameters:** Conservative vs aggressive settings
4. **Check for data quality:** Ensure no gaps, splits handled correctly
5. **Compare vs benchmark:** Calculate buy-and-hold returns (should outperform)
6. **Account for costs:** Real trading has commissions/slippage (reduce returns by 1-2%)
7. **Paper trade first:** Always validate with real timing before using capital

---

## 📞 Questions?

If backtest results are unclear:
1. Check `backtest_results.json` for detailed trade list
2. Open `backtest_report.html` in browser for visual analysis
3. Review individual trades to understand signals
4. Ask: "Does this verdict make sense for this stock on this date?"

**Remember:** Backtesting is essential. Never skip it. Past performance matters for validation.

---

**Ready to validate your analysis engine? Run the backtest and check the HTML report! 🚀**
