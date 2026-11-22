"""
Deterministic offline tests for Phase 3 (Tasks 3.1 – 3.6):
- Eliminates lookahead bias in prediction outcome resolution
- Validates matured vs in-flight cohorts, direction bucket isolation (no HOLD contamination),
  model_version tracking, expectancy / profit factor / median return / Student t-test stats
- Validates corporate-action split re-baselining protecting OPEN predictions
- Validates live-aligned BacktestEngine (t+1 Open entry, gap invalidation, gap-down stop fills,
  NSE delivery friction, equal-capital sizing, Indian T-Bill ddof=1 Sharpe, 0-trade handling)
- Validates ^NSEI / ^CRSMID benchmark alpha comparison & expectancy-based HTML reporting.
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import datetime, timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from storage.cache_manager import CacheManager
from tools import outcome_tracker as ot
from tools.backtest_framework import BacktestEngine, Trade
from tools.backtest_reporter import generate_html_report, grade_backtest_performance
from tools.backtest_runner import run_backtest_job
from tools.historical_data_tools import HistoricalDataEngine


def _candle(sym: str, d: str, o: float, h: float, l: float, c: float, vol: int = 100000, splits: float = 0.0):
    return {
        "symbol": sym,
        "date": d,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "adj_close": c,
        "volume": vol,
        "splits": splits,
    }


class Phase3OutcomeTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "p3_ot.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_eliminates_lookahead_bias_against_made_at(self):
        # Prediction claims as_of="2026-11-02" (Monday), but made_at was Thursday post-close (2026-11-05 16:30 IST).
        # Candles on Tue/Wed/Thu ALREADY existed before made_at and must NOT resolve the signal!
        self.cm.log_prediction({
            "symbol": "AAA",
            "as_of_date": "2026-11-02",
            "made_at": "2026-11-05T16:30:00+05:30",
            "verdict": "BUY",
            "confidence_pct": 80,
            "price_at_signal": 100.0,
            "target": 110.0,
            "stop": 95.0,
            "horizon_days": 5,
        })
        self.cm.save_historical_candles([
            _candle("AAA", "2026-11-03", 101, 115, 100, 112),  # lookahead target hit - must be ignored
            _candle("AAA", "2026-11-04", 112, 113, 111, 112),
            _candle("AAA", "2026-11-05", 112, 114, 110, 111),  # same day as made_at - ignored
        ])
        counts = ot.resolve_open_predictions(self.cm)
        self.assertEqual(counts["still_open"], 1)
        self.assertEqual(self.cm.get_predictions()[0]["status"], "OPEN")

        # Next session (2026-11-06) hits stop -> resolves legitimately on 2026-11-06+
        self.cm.save_historical_candles([
            _candle("AAA", "2026-11-06", 94, 96, 93, 95),
        ])
        counts2 = ot.resolve_open_predictions(self.cm)
        self.assertEqual(counts2["HIT_STOP"], 1)
        row = self.cm.get_predictions()[0]
        self.assertEqual(row["status"], "HIT_STOP")
        self.assertEqual(row["outcome_price"], 94.0)

        # Pre-market prediction (< 09:15 IST) on 2026-11-10 CAN score the 2026-11-10 session
        self.cm.log_prediction({
            "symbol": "BBB",
            "as_of_date": "2026-11-09",
            "made_at": "2026-11-10T08:45:00+05:30",
            "verdict": "BUY",
            "confidence_pct": 78,
            "price_at_signal": 100.0,
            "target": 110.0,
            "stop": 95.0,
            "horizon_days": 5,
        })
        self.cm.save_historical_candles([_candle("BBB", "2026-11-10", 101, 112, 100, 111)])
        ot.resolve_open_predictions(self.cm)
        self.assertEqual(self.cm.get_predictions()[1]["status"], "HIT_TARGET")

    def test_matured_cohorts_bucket_isolation_model_version_and_t_stats(self):
        # Log matured actionable BUY predictions (2026-10-01 .. 2026-10-08), HOLD noise, a SELL win,
        # and an in-flight resolved prediction (2026-11-18) when market date is 2026-11-20.
        for idx, d in enumerate(("2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07")):
            self.cm.log_prediction({
                "symbol": f"WIN{idx}",
                "as_of_date": d,
                "made_at": f"{d}T16:15:00+05:30",
                "verdict": "BUY",
                "confidence_pct": 82,
                "price_at_signal": 100.0,
                "target": 110.0,
                "stop": 95.0,
                "horizon_days": 5,
                "model_version": "2.1.0",
            })
            self.cm.save_historical_candles([_candle(f"WIN{idx}", "2026-10-08", 101, 112, 100, 111)])

        # Matured SELL prediction
        self.cm.log_prediction({
            "symbol": "SHRT1",
            "as_of_date": "2026-10-05",
            "made_at": "2026-10-05T16:15:00+05:30",
            "verdict": "SELL",
            "confidence_pct": 70,
            "price_at_signal": 100.0,
            "target": 92.0,
            "stop": 105.0,
            "horizon_days": 5,
            "model_version": "2.1.0",
        })
        self.cm.save_historical_candles([_candle("SHRT1", "2026-10-06", 99, 100, 91, 92)])

        # HOLD prediction resolving as losing EXPIRED (-2%) - must NOT contaminate actionable `overall` or `by_confidence`!
        self.cm.log_prediction({
            "symbol": "HLD1",
            "as_of_date": "2026-10-01",
            "made_at": "2026-10-01T16:15:00+05:30",
            "verdict": "HOLD",
            "confidence_pct": 85,
            "price_at_signal": 100.0,
            "target": 110.0,
            "stop": 95.0,
            "horizon_days": 2,
            "model_version": "2.1.0",
        })
        self.cm.save_historical_candles([
            _candle("HLD1", "2026-10-02", 100, 102, 98, 99),
            _candle("HLD1", "2026-10-05", 99, 100, 97, 98),
        ])

        # In-flight BUY prediction on 2026-11-18 resolved on 2026-11-19 when horizon=5 & latest_date=2026-11-20
        self.cm.log_prediction({
            "symbol": "INF1",
            "as_of_date": "2026-11-18",
            "made_at": "2026-11-18T16:15:00+05:30",
            "verdict": "BUY",
            "confidence_pct": 60,
            "price_at_signal": 100.0,
            "target": 106.0,
            "stop": 96.0,
            "horizon_days": 5,
            "model_version": "1.0.0",
        })
        self.cm.save_historical_candles([_candle("INF1", "2026-11-19", 101, 107, 100, 106)])
        self.cm.save_historical_candles([_candle("WIN0", "2026-11-20", 110, 111, 109, 110)])

        ot.resolve_open_predictions(self.cm)
        acc = ot.compute_accuracy(self.cm, as_of_market_date="2026-11-20")

        # 8 total resolved: 6 long + 1 short actionable (= 7) + 1 HOLD (excluded from overall)
        self.assertEqual(acc["resolved"], 8)
        self.assertEqual(acc["actionable_resolved"], 7)
        self.assertEqual(acc["overall"]["n"], 7)
        self.assertEqual(acc["overall"]["win_rate_pct"], 100.0)
        self.assertEqual(acc["by_direction"]["long"]["n"], 6)
        self.assertEqual(acc["by_direction"]["short"]["n"], 1)
        self.assertEqual(acc["by_direction"]["hold"]["n"], 1)
        # HOLD had conf=85 -> high-confidence bucket must remain purely actionable (5 wins from WIN0..4, 100% WR)
        self.assertEqual(acc["by_confidence"]["75+"]["n"], 5)
        self.assertEqual(acc["by_confidence"]["75+"]["win_rate_pct"], 100.0)
        # Maturity cohort isolation: 6 actionable matured, 1 actionable in-flight
        self.assertEqual(acc["matured_cohort"]["actionable_resolved"], 6)
        self.assertEqual(acc["in_flight_resolved"]["n"], 1)
        self.assertIn("2.1.0", acc["by_model_version"])
        self.assertIn("1.0.0", acc["by_model_version"])
        # Statistical fields populated & finite
        self.assertGreater(acc["overall"]["t_stat"], 0)
        self.assertLess(acc["overall"]["p_value"], 0.05)

    def test_corporate_action_rebaselining_protects_open_predictions(self):
        # 1. Direct HistoricalDataEngine._full_refresh() 2:1 split re-baselining
        class SplitEngine(HistoricalDataEngine):
            def fetch_from_source(self, symbol, period="5y", start=None):
                return pd.DataFrame({
                    "DATE": pd.to_datetime(["2026-11-02", "2026-11-03", "2026-11-04"]),
                    "OPEN_PRICE": [500.0, 505.0, 520.0],
                    "HIGH_PRICE": [510.0, 515.0, 555.0],
                    "LOW_PRICE": [495.0, 500.0, 515.0],
                    "CLOSE_PRICE": [500.0, 510.0, 550.0],
                    "ADJ_CLOSE": [500.0, 510.0, 550.0],
                    "VOLUME": [10000, 10000, 10000],
                    "DIVIDENDS": [0.0, 0.0, 0.0],
                    "SPLITS": [0.0, 2.0, 0.0],
                })

        # Unadjusted pre-split history + OPEN prediction logged at Rs. 1,000
        self.cm.save_historical_candles([_candle("SPLITCO", "2026-11-02", 990, 1010, 985, 1000)])
        self.cm.log_prediction({
            "symbol": "SPLITCO",
            "as_of_date": "2026-11-02",
            "made_at": "2026-11-02T16:15:00+05:30",
            "verdict": "BUY",
            "confidence_pct": 84,
            "price_at_signal": 1000.0,
            "entry_lo": 990.0,
            "entry_hi": 1010.0,
            "target": 1100.0,
            "stop": 950.0,
            "horizon_days": 5,
        })

        eng = SplitEngine(cache_manager=self.cm)
        eng.sync_symbol_data("SPLITCO", force=True)

        pred = self.cm.get_predictions("OPEN")[0]
        self.assertEqual(pred["price_at_signal"], 500.0)
        self.assertEqual(pred["target"], 550.0)
        self.assertEqual(pred["stop"], 475.0)
        self.assertAlmostEqual(pred["split_adjusted_factor"], 0.5, places=3)

        # Resolve: post-split high 555 hits rebased target 550 (instead of fake -50% stop!)
        ot.resolve_open_predictions(self.cm)
        resolved = self.cm.get_predictions()[0]
        self.assertEqual(resolved["status"], "HIT_TARGET")
        self.assertEqual(resolved["return_pct"], 10.0)

        # 2. Belt-and-suspenders protection inside resolve_open_predictions if DB was replaced externally
        self.cm.save_historical_candles([
            _candle("EXTSPL", "2026-11-02", 495, 505, 490, 500),
            _candle("EXTSPL", "2026-11-03", 502, 560, 498, 555, splits=2.0),
        ])
        self.cm.log_prediction({
            "symbol": "EXTSPL",
            "as_of_date": "2026-11-02",
            "made_at": "2026-11-02T16:15:00+05:30",
            "verdict": "BUY",
            "confidence_pct": 80,
            "price_at_signal": 1000.0,
            "target": 1100.0,
            "stop": 950.0,
            "horizon_days": 5,
        })
        counts = ot.resolve_open_predictions(self.cm)
        self.assertGreaterEqual(counts["rebased"], 1)
        ext_row = [r for r in self.cm.get_predictions() if r["symbol"] == "EXTSPL"][0]
        self.assertEqual(ext_row["status"], "HIT_TARGET")


class Phase3BacktestTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "p3_bt.db")
        self.cm = CacheManager(db_path=self.db_path)

    def tearDown(self):
        self.tmp.cleanup()

    def _seed_series(self, sym: str, bars: list):
        self.cm.save_historical_candles([
            _candle(sym, d, o, h, l, c, vol=v) for (d, o, h, l, c, v) in bars
        ])

    def test_next_day_open_entry_gap_skip_and_gap_down_stop_fill(self):
        # 55 steady-rising warmup bars (index 0..54 -> dates 2026-06-01 ..), triggering signal on bar 54
        dates = pd.bdate_range("2026-06-01", periods=62)
        bars = []
        for i, dt_i in enumerate(dates[:55]):
            px = 100.0 + i * 1.2
            bars.append((dt_i.strftime("%Y-%m-%d"), px - 0.5, px + 1.0, px - 1.0, px, 200000))
        # Bar 55 (t+1): Open at 172.0 (HIGHER than bar 54 close 164.8!), intraday low stays above stop, close 175
        bars.append((dates[55].strftime("%Y-%m-%d"), 172.0, 176.0, 170.0, 175.0, 200000))
        # Bar 56 (t+2): Overnight gap DOWN to Open 120.0 (below stop!) -> stop must fill at min(120, stop) = 120.0!
        bars.append((dates[56].strftime("%Y-%m-%d"), 120.0, 125.0, 118.0, 122.0, 200000))
        for j in range(57, 62):
            bars.append((dates[j].strftime("%Y-%m-%d"), 122.0, 124.0, 120.0, 122.0, 100000))
        self._seed_series("GAPCO", bars)

        eng = BacktestEngine(db_path=self.db_path)
        sig_date = dates[54].strftime("%Y-%m-%d")
        t1_date = dates[55].strftime("%Y-%m-%d")

        # Mock synthesizer to emit a clean BUY signal only on sig_date (tests exact t+1 execution mechanics)
        def fake_synth(sym, ind_df, idx, bench_df=None, enable_patterns=True):
            d_s = str(ind_df.iloc[idx]["DATE_STR"])
            if d_s == sig_date:
                return {"verdict": "BUY", "confidence": 85, "target": 200.0, "stop": 158.0, "price": 164.8}
            return None

        with unittest.mock.patch.object(eng, "_synthesize_at_index", side_effect=fake_synth):
            trades, metrics = eng.backtest_symbol("GAPCO", dates[0].strftime("%Y-%m-%d"), dates[61].strftime("%Y-%m-%d"))

        self.assertEqual(len(trades), 1)
        tr = trades[0]
        self.assertEqual(tr.signal_date, sig_date)
        self.assertEqual(tr.entry_date, t1_date)
        self.assertEqual(tr.entry_price, 172.0)   # entered at t+1 Open, NOT t Close (164.8)
        self.assertEqual(tr.status, "STOPPED_OUT")
        self.assertEqual(tr.exit_price, 120.0)    # gap-down filled at Open 120.0, NOT stop 158.0
        self.assertLess(tr.pnl_pct, tr.gross_pnl_pct)  # NSE friction deducted

        # Now test overnight gap BELOW stop at t+1 Open -> trade skipped!
        bars_gap_skip = list(bars)
        bars_gap_skip[55] = (dates[55].strftime("%Y-%m-%d"), 145.0, 150.0, 140.0, 148.0, 200000)
        self.cm.save_historical_candles([_candle("SKIPCO", *b) for b in bars_gap_skip])
        with unittest.mock.patch.object(eng, "_synthesize_at_index", side_effect=fake_synth):
            trades_sk, metrics_sk = eng.backtest_symbol("SKIPCO", dates[0].strftime("%Y-%m-%d"), dates[61].strftime("%Y-%m-%d"))
        self.assertEqual(len(trades_sk), 0)
        self.assertEqual(metrics_sk.skipped_gap_entries, 1)

    def test_live_pipeline_alignment_equal_capital_tbill_sharpe_and_zero_trades(self):
        # Verify real causal indicator + live synthesizer runs cleanly (without mocked synthesizer):
        # 235 bars building Stage-2 uptrend (SMA50 > SMA200), brief pullback keeping RSI ~55-62, then volume breakout
        dates = pd.bdate_range("2026-01-01", periods=235)
        bars_low = []
        bars_hi = []
        rel_prices = []
        rel_vols = []
        px = 1.0
        for i in range(235):
            if i < 205:
                px *= 1.0018 if (i % 5 != 0) else 0.9985
                v = 120000 if (i % 5 != 0) else 90000
            elif i < 214:
                px *= 0.9965  # healthy pullback on light volume (keeps RSI off 100 & builds U/D volume)
                v = 60000
            elif i < 222:
                px *= 1.0085  # high-volume breakout days
                v = 260000
            else:
                px *= 1.0040
                v = 160000
            rel_prices.append(px)
            rel_vols.append(v)

        for i, dt_i in enumerate(dates):
            d_s = dt_i.strftime("%Y-%m-%d")
            c_low = round(200.0 * rel_prices[i], 2)
            c_hi = round(4000.0 * rel_prices[i], 2)
            v = rel_vols[i]
            bars_low.append((d_s, round(c_low * 0.996, 2), round(c_low * 1.012, 2), round(c_low * 0.990, 2), c_low, v))
            bars_hi.append((d_s, round(c_hi * 0.996, 2), round(c_hi * 1.012, 2), round(c_hi * 0.990, 2), c_hi, v))
        self._seed_series("LOWPX", bars_low)
        self._seed_series("HIGHPX", bars_hi)
        # Seed benchmarks ^NSEI and ^CRSMID
        self._seed_series("^NSEI", [(dt_i.strftime("%Y-%m-%d"), 24000 + i * 10, 24050 + i * 10, 23950 + i * 10, 24000 + i * 10, 1000000) for i, dt_i in enumerate(dates)])
        self._seed_series("^CRSMID", [(dt_i.strftime("%Y-%m-%d"), 18000 + i * 8, 18040 + i * 8, 17960 + i * 8, 18000 + i * 8, 500000) for i, dt_i in enumerate(dates)])

        eng = BacktestEngine(db_path=self.db_path)
        t_low, m_low = eng.backtest_symbol("LOWPX", dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d"), enable_patterns=False)
        t_hi, m_hi = eng.backtest_symbol("HIGHPX", dates[0].strftime("%Y-%m-%d"), dates[-1].strftime("%Y-%m-%d"), enable_patterns=False)
        # Identical % return profile at Rs 200 vs Rs 4,000 must allocate nearly equal rupee capital (~Rs 2L per slot)
        self.assertGreater(len(t_low), 0)
        self.assertEqual(len(t_low), len(t_hi))
        self.assertAlmostEqual(t_low[0].position_capital, t_hi[0].position_capital, delta=12000.0)
        self.assertEqual(m_low.risk_free_rate_pct, 6.5)

        # Verify 0-trade run_backtest_job succeeds without UnboundLocalError and emits benchmark alpha
        out_json = os.path.join(self.tmp.name, "zero_bt.json")
        zero_res = run_backtest_job(
            symbols=["NONEXISTENT"],
            start_date="2026-01-01",
            end_date="2026-05-01",
            db_path=self.db_path,
            output_path=out_json,
        )
        self.assertEqual(zero_res["aggregate"]["total_trades"], 0)
        self.assertEqual(zero_res["aggregate"]["total_pnl"], 0.0)
        self.assertTrue(zero_res["benchmarks"]["available"])
        self.assertIn("^NSEI", zero_res["benchmarks"]["benchmarks"])
        self.assertIn("^CRSMID", zero_res["benchmarks"]["benchmarks"])

    def test_expectancy_based_grading_and_html_reporter(self):
        # 42% win rate trend-following strategy with large R:R (+2.1% expectancy, PF 1.85, 8% DD)
        # MUST be graded STRONG/GOOD, never "POOR / losing strategy"!
        agg_trend = {
            "total_trades": 35,
            "winning_trades": 15,
            "losing_trades": 20,
            "win_rate": 42.9,
            "expectancy_pct": 2.10,
            "profit_factor": 1.85,
            "breakeven_win_rate": 32.0,
            "total_pnl": 145000.0,
            "total_pnl_pct": 14.5,
            "max_drawdown_pct": 8.0,
            "sharpe_ratio": 1.65,
            "calmar_ratio": 2.40,
            "total_friction_rs": 5600.0,
            "risk_free_rate_pct": 6.5,
        }
        graded = grade_backtest_performance(agg_trend)
        self.assertIn(graded["grade"], ("STRONG", "GOOD"))

        payload = {
            "metadata": {"start_date": "2026-01-01", "end_date": "2026-11-01", "symbols": ["INFY"], "hold_days": 20},
            "aggregate": agg_trend,
            "benchmarks": {
                "available": True,
                "benchmarks": {
                    "^NSEI": {"name": "Nifty 50", "available": True, "start_date": "2026-01-01", "end_date": "2026-11-01", "return_pct": 8.2, "max_drawdown_pct": 6.5, "alpha_pct": 6.3},
                },
            },
            "symbol_results": {"INFY": {"total_trades": 35, "win_rate": 42.9, "expectancy_pct": 2.1, "profit_factor": 1.85, "total_pnl": 145000.0, "max_drawdown_pct": 8.0, "avg_hold_days": 11.0}},
            "trades": [],
        }
        html_ok = generate_html_report(payload)
        self.assertIn("Expectancy / Trade", html_ok)
        self.assertIn("Benchmark Alpha Comparison", html_ok)
        self.assertIn("+6.30%", html_ok)
        self.assertNotIn("losing strategy", html_ok.lower())

        # Zero-trade JSON renders safely without error
        html_empty = generate_html_report({
            "metadata": {"start_date": "2026-01-01", "end_date": "2026-03-01", "symbols": ["X"]},
            "aggregate": {"total_trades": 0},
            "symbol_results": {},
            "trades": [],
        })
        self.assertIn("NO TRADES", html_empty)


if __name__ == "__main__":
    unittest.main()
