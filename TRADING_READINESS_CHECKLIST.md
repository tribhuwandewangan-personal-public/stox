# Trading Readiness Checklist

**Goal:** Determine if this app is safe to trade with  
**Timeline:** 4-8 weeks from validation to live trading  
**Risk:** High until validated  

---

## Phase 1: Component Validation (Week 1)

### Browser Testing
- [ ] Run `npx ng serve` (frontend dev server)
- [ ] Open `http://localhost:4200`
- [ ] Check grid displays 50+ stocks
- [ ] Click card → modal opens
- [ ] Modal shows chart
- [ ] Search filters work
- [ ] Verdict tabs filter work
- [ ] Mobile responsive (test at 375px)

### Backend Testing
- [ ] Run `python dashboard_server.py`
- [ ] Check WebSocket connection
- [ ] Monitor `/api/status` endpoint
- [ ] Verify price updates in real-time
- [ ] Check that verdicts appear for stocks

### Document Findings
- [ ] Note any UI bugs or crashes
- [ ] Track which features work/don't work
- [ ] Screenshot working UI
- [ ] List what needs fixing

**Milestone:** UI works and shows live data correctly

---

## Phase 2: Analysis Validation (Week 2)

### Historical Data Quality
- [ ] Verify historical data exists (2+ years)
- [ ] Check for data gaps or missing candles
- [ ] Confirm splits/dividends are handled
- [ ] Spot-check prices vs. external sources (Yahoo Finance, NSE)
- [ ] Ensure no duplicate or corrupted records

### Analysis Engine Accuracy
- [ ] Run analysis on historical data: `python main.py --force`
- [ ] Generate verdicts for all symbols
- [ ] Check verdicts make sense (e.g., BUY when price low, SELL when high)
- [ ] Review pattern detections
- [ ] Verify confidence scores

### Backtest Run 1: 2-Year Test
```powershell
python tools/backtest_runner.py `
  --start 2024-01-01 `
  --end 2026-11-10 `
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC,LT,MARUTI,WIPRO,BAJAJFINSV,AXISBANK"
```

- [ ] Record total trades
- [ ] Record win rate
- [ ] Record total P&L
- [ ] Generate HTML report

### Backtest Run 2: 1-Year Test (2023)
```powershell
python tools/backtest_runner.py `
  --start 2023-01-01 `
  --end 2023-12-31 `
  --symbols "INFY,TCS,RELIANCE,ITC,HDFC"
```

- [ ] Compare 2023 results vs 2024-2026
- [ ] Check if strategy consistent across years
- [ ] Identify best/worst performing symbols

### Decision Point

| Win Rate | Action |
|----------|--------|
| > 60% | ✅ **STRONG** → Proceed to Phase 3 |
| 55-60% | ✅ **GOOD** → Proceed to Phase 3 |
| 50-55% | ⚠️ **RISKY** → Improve analysis, test more |
| < 50% | ❌ **POOR** → DO NOT PROCEED |

**Milestone:** Backtest shows > 55% win rate

---

## Phase 3: Paper Trading (Weeks 3-4)

### Setup
- [ ] Frontend running: `npx ng serve`
- [ ] Backend running: `python dashboard_server.py`
- [ ] Browser open to `http://localhost:4200`

### Daily Process (4 weeks)
- [ ] Check app every trading day
- [ ] Note all BUY/SELL signals
- [ ] Record entry date, symbol, verdict
- [ ] Record actual price at entry
- [ ] Track for next 5-10 days
- [ ] Record exit price
- [ ] Calculate paper P&L

### Weekly Analysis
- [ ] Tally wins vs. losses
- [ ] Calculate win rate
- [ ] Check if matching backtest
- [ ] Note any patterns
- [ ] Identify surprises

### Decision Point After 4 Weeks

| Paper Results | Action |
|---------------|--------|
| Win rate > 55% | ✅ Ready for Phase 4 (live) |
| Win rate 50-55% | ⚠️ Continue paper trading |
| Win rate < 50% | ❌ DO NOT TRADE REAL MONEY |

**Milestone:** 4 weeks paper trading with > 55% win rate

---

## Phase 4: Live Trading (Week 5+)

### Position Sizing (DO NOT SKIP)
- [ ] Decide position size per trade (1-5% of account)
- [ ] Set max account risk (typically 2% max loss per trade)
- [ ] Calculate share quantity per trade
- [ ] Use stop losses religiously

### First Trade Setup
- [ ] Deposit small amount (enough for 10-20 trades)
- [ ] Set up broker account with order management
- [ ] Test execution on first live trade (small size)
- [ ] Verify order filled correctly
- [ ] Monitor position in real-time

### Ongoing Management
- [ ] Check app signals every trading day
- [ ] Execute trades following signals
- [ ] Track actual P&L vs. paper
- [ ] Log all trades with timestamps
- [ ] Review weekly (wins, losses, surprises)
- [ ] Scale up only if consistently profitable

### Scaling Rules
| Period | Capital | Status |
|--------|---------|--------|
| Weeks 1-4 | 1-5% | Testing |
| Weeks 5-8 | 5-10% | If profitable |
| Weeks 9-12 | 10-25% | If still profitable |
| Months 4+ | 25-50% | Only if 3+ months green |

---

## Red Flags (Stop Everything)

⛔ **If ANY of these happen, PAUSE trading:**

- [ ] Live P&L drops > 10% in a month
- [ ] Win rate in live trades < 50%
- [ ] UI crashes or shows wrong data
- [ ] WebSocket disconnects frequently
- [ ] Prices look incorrect (way off from market)
- [ ] Verdicts don't make sense (e.g., BUY at all-time high)
- [ ] Losing 3+ trades in a row for no clear reason
- [ ] Finding errors in data or analysis

**If any red flag:** Stop trading and investigate!

---

## Success Criteria for "Ready to Trade"

✅ **Must have ALL of these:**

- [ ] Browser UI works without errors
- [ ] Grid displays real-time stock data
- [ ] Modal shows all analysis panels
- [ ] Historical backtest: win rate > 55%
- [ ] Backtest on 2+ different years: consistent results
- [ ] Paper trading: win rate > 55% for 4 weeks
- [ ] Actual live trades: first 5 trades profitable (or break-even)
- [ ] Position sizing: defined and documented
- [ ] Stop losses: enabled and tested

**If you have all of these, you're good to go! 🚀**

---

## Timeline Summary

```
Week 1:  Component validation (UI works, data displays)
Week 2:  Analysis validation (backtest shows > 55% win)
Week 3-4: Paper trading (4 weeks with > 55% win)
Week 5+: Live trading (1-5% capital, scale carefully)
```

---

## Remember

> ⚠️ **NEVER trade real money without completing ALL phases first.**

This isn't optional. This is the difference between:
- Validating your strategy vs. losing money on untested signals
- Confidence vs. panic when markets move
- Sustainable trading vs. blowing up your account

**Don't skip steps. Don't rush. Take 4-8 weeks to be sure.**

---

## Questions to Ask Yourself

Before you trade, answer YES to all:

1. ✓ Have I backtest on 2+ years of data?
2. ✓ Did the backtest show > 55% win rate?
3. ✓ Have I paper traded for 4 weeks?
4. ✓ Did paper trading match backtest results?
5. ✓ Do I have a position sizing plan?
6. ✓ Do I have stop losses on every trade?
7. ✓ Can I afford to lose the capital I'm risking?
8. ✓ Do I have an emergency exit plan?

**If you answered NO to any question: NOT READY YET**

---

**Start with Phase 1. Complete each phase fully. Then decide if you trust this app with your money.**

Good luck! 🎯
