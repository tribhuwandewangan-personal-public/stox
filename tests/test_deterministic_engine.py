"""
Tests for the LLM-free analysis engine: macro rules, evidence scoring / verdict invariants,
cache layer behaviour and the "no invented data" guarantees.

Run:  python -m unittest discover -s tests -v          (no third-party packages needed)
      uv run --no-project --with pandas --with numpy python -m unittest discover -s tests -v   (adds history tests)
"""

import itertools
import os
import sys
import tempfile
import unittest
import unittest.mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from agents.news_sentiment_agent import NewsSentimentAgent
from agents.synthesizer_agent import (
    MasterPredictionSynthesizerAgent as Synth,
    score_evidence, ACCUMULATE_THRESHOLD, BUY_THRESHOLD, SELL_THRESHOLD,
)
from storage.cache_manager import CacheManager
from tools.macro_tools import compute_macro_sentiment


def ind(name, pct):
    return {"indicator": name, "pct_change": pct}


def rs(text):
    """First number in a 'Rs. 123.45' / 'Rs. 100.00 - 102.00' string."""
    return float(str(text).replace("Rs.", "").split("-")[0].replace(",", "").strip())


class MacroSentimentTests(unittest.TestCase):
    def test_risk_on_is_bullish(self):
        r = compute_macro_sentiment([ind("S&P 500", 1.2), ind("Nasdaq", 1.5), ind("Brent Crude Oil", -1.5),
                                     ind("US Dollar Index (DXY)", -0.4), ind("USD / INR (Rupee)", -0.2)])
        self.assertEqual(r["label"], "Bullish")
        self.assertTrue(r["available"])
        self.assertGreater(r["score"], 0.25)

    def test_oil_dollar_rupee_shock_is_bearish(self):
        r = compute_macro_sentiment([ind("S&P 500", -0.2), ind("Brent Crude Oil", 3.5),
                                     ind("US Dollar Index (DXY)", 0.8), ind("USD / INR (Rupee)", 0.5)])
        self.assertEqual(r["label"], "Bearish")
        self.assertLess(r["score"], -0.25)

    def test_mixed_is_neutral(self):
        r = compute_macro_sentiment([ind("S&P 500", 0.5), ind("Brent Crude Oil", 1.0),
                                     ind("US Dollar Index (DXY)", 0.0), ind("USD / INR (Rupee)", 0.0)])
        self.assertEqual(r["label"], "Neutral")
        self.assertTrue(r["available"])

    def test_unavailable_when_too_little_data(self):
        for data in ([], [ind("S&P 500", 1.0)], [ind("S&P 500", None), ind("Brent Crude Oil", None)],
                     [ind("Gold Futures", 5.0), ind("WTI Crude Oil", 5.0)]):
            r = compute_macro_sentiment(data)
            self.assertFalse(r["available"], data)
            self.assertEqual(r["label"], "Neutral")
            self.assertEqual(r["score"], 0.0)

    def test_score_bounded(self):
        r = compute_macro_sentiment([ind("S&P 500", 50), ind("Nasdaq", 50), ind("Brent Crude Oil", -50),
                                     ind("US Dollar Index (DXY)", -50)])
        self.assertLessEqual(r["score"], 1.0)


def make_tech(lp, sma50, sma200, rsi):
    return {"last_price": lp, "sma_50": sma50, "sma_200": sma200, "rsi_14": rsi}


BULL = {"name": "Cup & Handle", "direction": "Bullish", "quality_score": 88,
        "target_price": 118.0, "stop_loss": 96.0, "entry_trigger": 101.0}
BEAR = {"name": "Head & Shoulders", "direction": "Bearish", "quality_score": 86,
        "target_price": 85.0, "stop_loss": 106.0, "entry_trigger": 99.0}


class VerdictInvariantTests(unittest.TestCase):
    """For every combination of inputs the levels must agree with the verdict direction."""

    def test_levels_consistent_across_input_grid(self):
        lp = 100.0
        patterns = [[], [BULL], [BEAR]]
        smas = [(90.0, 80.0), (110.0, 120.0), (95.0, 105.0), (None, None)]
        rsis = [None, 25.0, 50.0, 80.0]
        macros = [None, {"available": True, "score": 0.6, "label": "Bullish"},
                  {"available": True, "score": -0.6, "label": "Bearish"}]
        news = [None, {"bullish": 5, "bearish": 0, "total": 5}, {"bullish": 0, "bearish": 4, "total": 4}]
        funds = [None, {"available": False}, {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "roe_pct": 20}]
        # Deliberately hostile risk-tool output: stop above price, target below price
        risks = [{}, {"suggested_target_price": 90.0, "suggested_stop_loss": 120.0},
                 {"suggested_target_price": 112.0, "suggested_stop_loss": 93.0}]

        seen = set()
        for pat, (s50, s200), rsi, mac, nw, fu, risk in itertools.product(patterns, smas, rsis, macros, news, funds, risks):
            ctx = {"news": nw, "macro": mac, "fundamental": fu, "historical": {"pct_change_30d": 4.0}}
            sig = Synth.compute_quantitative_verdict("TEST", "Test Co", lp, make_tech(lp, s50, s200, rsi), risk, pat, {}, ctx)
            v = sig["action_verdict"]
            seen.add(v)
            target, stop = rs(sig["when_to_sell_target"]), rs(sig["stop_loss"])
            label = (v, pat and pat[0]["direction"], s50, rsi, mac and mac["label"], risk)
            if v in ("BUY", "ACCUMULATE"):
                self.assertTrue(stop < lp < target, label)
                entry_hi = float(sig["when_to_buy_entry"].split("-")[1])
                entry_lo = rs(sig["when_to_buy_entry"])
                self.assertTrue(entry_lo < entry_hi < target, (label, sig["when_to_buy_entry"]))
            elif v == "SELL":
                self.assertTrue(target < lp < stop, label)
            else:  # HOLD defensive: downside target / upside stop ; HOLD range: upside target / downside stop
                if sig["when_to_buy_entry"].startswith("Hold existing"):
                    self.assertTrue(target < lp < stop, label)
                else:
                    self.assertTrue(stop < lp < target, label)
            self.assertTrue(0 <= sig["confidence_percentage"] <= 92)
            self.assertTrue(sig["confidence_rating"].startswith(("HIGH", "MEDIUM", "LOW")))
        self.assertEqual(seen, {"BUY", "ACCUMULATE", "HOLD", "SELL"}, "grid should reach every verdict")

    def test_clear_bullish_setup_is_buy(self):
        ctx = {"news": {"bullish": 5, "bearish": 0, "total": 5},
               "macro": {"available": True, "score": 0.5, "label": "Bullish"},
               "fundamental": {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "roe_pct": 22},
               "historical": {"pct_change_30d": 6.0}}
        sig = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 92, 85, 55), {}, [BULL], {}, ctx)
        self.assertEqual(sig["action_verdict"], "BUY")
        self.assertTrue(sig["confidence_rating"].startswith("HIGH"))

    def test_clear_bearish_setup_is_sell(self):
        ctx = {"news": {"bullish": 0, "bearish": 5, "total": 5},
               "macro": {"available": True, "score": -0.5, "label": "Bearish"}}
        sig = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 112, 120, 75), {}, [BEAR], {}, ctx)
        self.assertEqual(sig["action_verdict"], "SELL")

    def test_single_signal_is_not_enough_to_sell_or_buy(self):
        # Downtrend only (no pattern, neutral RSI): one bearish signal -> HOLD, not SELL
        down = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 110, 120, 40), {}, [], {}, None)
        self.assertEqual(down["action_verdict"], "HOLD")
        # Same downtrend plus bearish news -> two agreeing signals -> SELL
        ctx = {"news": {"bullish": 0, "bearish": 5, "total": 5}}
        sell = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 110, 120, 40), {}, [], {}, ctx)
        self.assertEqual(sell["action_verdict"], "SELL")
        # Uptrend only, soft RSI -> HOLD ; add healthy RSI -> ACCUMULATE
        up = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 90, 80, 40), {}, [], {}, None)
        self.assertEqual(up["action_verdict"], "HOLD")
        up2 = Synth.compute_quantitative_verdict("T", "T", 100.0, make_tech(100, 90, 80, 55), {}, [], {}, None)
        self.assertEqual(up2["action_verdict"], "ACCUMULATE")

    def test_more_agreeing_evidence_never_lowers_bullish_score(self):
        base = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {})["score"]
        more = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL,
                              {"news": {"bullish": 4, "bearish": 0, "total": 4}})["score"]
        self.assertGreaterEqual(more, base - 1e-9)

    def test_missing_inputs_are_excluded_not_defaulted(self):
        ev = score_evidence(100.0, {}, None, None)
        names = [b["signal"] for b in ev["breakdown"]]
        self.assertEqual(names, ["pattern"])           # only "no pattern" counts; nothing invented
        self.assertLess(ev["coverage"], 0.5)
        self.assertEqual(Synth.compute_quantitative_verdict("T", "T", 100.0, {}, {}, [], {}, None)["action_verdict"], "HOLD")

    def test_unavailable_fundamentals_do_not_move_score(self):
        a = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {})
        b = score_evidence(100.0, make_tech(100, 92, 85, 55), BULL, {"fundamental": {"available": False}})
        self.assertEqual(a["score"], b["score"])

    def test_peg_ratio_rewards_garp_and_penalizes_expensive_growth(self):
        from agents.synthesizer_agent import _fundamental_signal
        # High growth with premium P/E alone receives negative penalty (-0.3)
        pure_premium = {"available": True, "valuation_assessment": "High Growth / Premium Valuation"}
        val_pure, _ = _fundamental_signal(pure_premium)
        self.assertLess(val_pure, 0)

        # High growth with PEG < 1.0 (GARP justified) turns positive
        garp = {"available": True, "valuation_assessment": "High Growth / Premium Valuation", "peg_ratio": 0.85}
        val_garp, note_garp = _fundamental_signal(garp)
        self.assertGreater(val_garp, 0)
        self.assertIn("attractive growth at discount", note_garp)

        # Low P/E with poor growth / negative PEG is dampened compared to genuine value
        true_value = {"available": True, "valuation_assessment": "Undervalued / Value Opportunity"}
        val_true, _ = _fundamental_signal(true_value)
        trap_value = {"available": True, "valuation_assessment": "Undervalued / Value Opportunity", "peg_ratio": -1.2}
        val_trap, note_trap = _fundamental_signal(trap_value)
        self.assertLess(val_trap, val_true)
        self.assertIn("growth concern", note_trap)

    def test_invalid_price_yields_no_levels(self):
        for bad in (None, "N/A", float("nan"), 0, -5):
            sig = Synth.compute_quantitative_verdict("T", "T", bad, {}, {}, [BULL], {}, None)
            self.assertEqual(sig["action_verdict"], "HOLD", bad)
            self.assertEqual(sig["confidence_percentage"], 0)
            for k in ("when_to_buy_entry", "when_to_sell_target", "stop_loss", "long_term_target"):
                self.assertEqual(sig[k], "N/A", (bad, k))

    def test_frontend_price_string_format(self):
        sig = Synth.compute_quantitative_verdict("T", "T", 123.456, make_tech(123.456, 110, 100, 55), {}, [BULL], {}, None)
        import re
        self.assertRegex(sig["when_to_sell_target"], r"^Rs\. \d+(\.\d+)?$")
        self.assertRegex(sig["stop_loss"], r"^Rs\. \d+(\.\d+)?$")
        self.assertRegex(sig["when_to_buy_entry"], r"^Rs\. \d+\.\d{2} - \d+\.\d{2}$")

    def test_thresholds_are_ordered(self):
        self.assertLess(SELL_THRESHOLD, 0)
        self.assertLess(ACCUMULATE_THRESHOLD, BUY_THRESHOLD)


class FakeNewsEngine:
    def __init__(self, items):
        self.items = items

    def fetch_stock_news(self, symbol, company_name=""):
        return self.items


class NewsAgentTests(unittest.TestCase):
    def test_counts_mildly_labels_and_exposes_score(self):
        items = [{"title": "a", "sentiment_label": "Mildly Bullish"}, {"title": "b", "sentiment_label": "Bullish"},
                 {"title": "c", "sentiment_label": "Bearish"}, {"title": "d", "sentiment_label": "Neutral"}]
        out = NewsSentimentAgent(FakeNewsEngine(items)).run("X", "X Ltd")
        self.assertEqual(out["news_score"]["bullish"], 2)
        self.assertEqual(out["news_score"]["bearish"], 1)
        self.assertIn("Positive", out["analysis"])

    def test_no_news_is_reported_as_unavailable(self):
        out = NewsSentimentAgent(FakeNewsEngine([])).run("X", "X Ltd")
        self.assertEqual(out["news_score"]["total"], 0)
        self.assertIn("No recent news", out["analysis"])


class CacheManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "cache.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def candles(self, n, start_close=100.0):
        return [{"symbol": "AAA", "date": f"2026-01-{i + 1:02d}", "open": start_close + i, "high": start_close + i + 1,
                 "low": start_close + i - 1, "close": start_close + i, "volume": 1000 + i} for i in range(n)]

    def test_wal_enabled(self):
        with self.cm._get_connection() as c:
            self.assertEqual(c.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")

    def test_candle_limit_in_sql_keeps_prev_close(self):
        self.cm.save_historical_candles(self.candles(20))
        full = self.cm.get_cached_candles("AAA", limit_days=500)
        tail = self.cm.get_cached_candles("AAA", limit_days=5)
        self.assertEqual(len(full), 20)
        self.assertEqual(len(tail), 5)
        self.assertEqual([c["DATE"] for c in tail], [c["DATE"] for c in full[-5:]])
        self.assertEqual(tail[0]["PREV_CLOSE"], full[-6]["CLOSE_PRICE"])      # true previous close, not own close
        self.assertEqual(full[0]["PREV_CLOSE"], full[0]["CLOSE_PRICE"])        # legacy behaviour for first row
        self.assertEqual(self.cm.get_cached_candles("AAA", limit_days=1)[0]["DATE"], "2026-01-20")
        self.assertEqual(self.cm.get_cached_candles("NOPE"), [])

    def test_replace_symbol_drops_old_basis(self):
        self.cm.save_historical_candles(self.candles(10))
        self.cm.save_historical_candles(self.candles(3, start_close=50.0), replace_symbol="AAA")
        rows = self.cm.get_cached_candles("AAA")
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["CLOSE_PRICE"], 50.0)

    def test_macro_cache_latest_per_indicator_with_pct(self):
        self.cm.save_macro([{"indicator": "S&P 500", "value": 1.0, "unit": "pts", "summary": "a", "pct_change": 0.5}])
        self.cm.save_macro([{"indicator": "S&P 500", "value": 2.0, "unit": "pts", "summary": "b", "pct_change": -0.3},
                            {"indicator": "Nasdaq", "value": 9.0, "unit": "pts", "summary": "c", "pct_change": None}])
        rows = {r["indicator"]: r for r in self.cm.get_cached_macro(12)}
        self.assertEqual(len(rows), 2)                      # no duplicates
        self.assertEqual(rows["S&P 500"]["value"], 2.0)     # latest wins
        self.assertEqual(rows["S&P 500"]["pct_change"], -0.3)
        self.assertIsNone(rows["Nasdaq"]["pct_change"])

    def test_bulk_latest_outputs(self):
        self.cm.save_agent_output("AAA", "Technical Analysis Agent", {"v": 1})
        self.cm.save_agent_output("BBB", "Technical Analysis Agent", {"v": 2})
        self.cm.save_agent_output("AAA", "Risk & Volatility Agent", {"v": 3})
        bulk = self.cm.get_latest_agent_outputs_bulk()
        self.assertEqual(bulk["AAA"]["Technical Analysis Agent"]["output"], {"v": 1})
        self.assertEqual(bulk["BBB"]["Technical Analysis Agent"]["output"], {"v": 2})
        self.assertEqual(bulk["AAA"]["Risk & Volatility Agent"]["output"], {"v": 3})
        self.assertTrue(self.cm.get_agent_runs_marker())

    def test_fundamentals_roundtrip(self):
        self.assertIsNone(self.cm.get_cached_fundamentals("AAA"))
        self.cm.save_fundamentals("aaa", {"available": True, "pe_ratio": 12.5})
        hit = self.cm.get_cached_fundamentals("AAA")
        self.assertEqual(hit["data"]["pe_ratio"], 12.5)

    def test_reinit_is_idempotent_and_migrates_legacy_macro_table(self):
        path = os.path.join(self.tmp.name, "legacy.db")
        import sqlite3
        legacy = sqlite3.connect(path)
        try:
            legacy.execute("CREATE TABLE macro_cache (indicator_name TEXT, fetch_date TEXT, value REAL, unit TEXT, summary TEXT, PRIMARY KEY (indicator_name, fetch_date))")
            legacy.execute("CREATE TABLE bhavcopy_cache (x INTEGER)")
            legacy.commit()
        finally:
            legacy.close()
        cm = CacheManager(db_path=path)
        CacheManager(db_path=path)
        cm.save_macro([{"indicator": "S&P 500", "value": 1.0, "unit": "pts", "summary": "s", "pct_change": 1.1}])
        self.assertEqual(cm.get_cached_macro(12)[0]["pct_change"], 1.1)
        with cm._get_connection() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM sqlite_master WHERE name='bhavcopy_cache'").fetchone())


class LongTermTests(unittest.TestCase):
    def test_no_price_means_no_target(self):
        from tools.long_term_strategy import long_term_engine
        for sym in ("LT", "ZZZUNKNOWN"):
            r = long_term_engine.evaluate_long_term_stock(sym, last_price=None, short_verdict="BUY")
            self.assertEqual(r["long_term_target"], "N/A")
            self.assertIsNone(r["long_term_target_num"])
            self.assertEqual(r["target_basis"], "indicative_scenario")

    def test_target_is_scenario_multiple_of_price(self):
        from tools.long_term_strategy import long_term_engine
        r = long_term_engine.evaluate_long_term_stock("ZZZUNKNOWN", last_price=200.0, short_verdict="BUY")
        self.assertEqual(r["long_term_target_num"], 284.0)
        self.assertIn("indicative", r["long_term_thesis"])


try:
    import pandas as pd
    from tools.historical_data_tools import HistoricalDataEngine
    HAVE_PANDAS = True
except ImportError:  # pandas not installed: history tests are skipped
    HAVE_PANDAS = False


@unittest.skipUnless(HAVE_PANDAS, "pandas not installed")
class IncrementalHistoryTests(unittest.TestCase):
    """Price history refresh: only missing days are downloaded unless the series was re-adjusted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cm = CacheManager(db_path=os.path.join(self.tmp.name, "cache.db"))
        outer = self

        class FakeEngine(HistoricalDataEngine):
            def __init__(self):
                super().__init__(cache_manager=cm)
                self.calls = []          # (start, period)
                self.source = None       # callable(start) -> DataFrame
                self.fail = False

            def fetch_from_source(self, symbol, period="5y", start=None):
                self.calls.append((start, period))
                if self.fail:
                    return pd.DataFrame()
                return outer.make_df(outer.source_rows(start))

        self.engine = FakeEngine()
        self.cm = cm
        # Fixed clock: 18:00 IST (after the close + vendor buffer) on the latest business day, so the tests do not
        # depend on the time of day they run. Series ends on that day; cached history ends 8 business days earlier.
        from datetime import datetime as _dt, time as _t
        from tools import market_calendar as _mc
        self.today = pd.bdate_range(end=pd.Timestamp.now().normalize(), periods=1)[0]
        self._clock = unittest.mock.patch.object(
            _mc, "now_ist", return_value=_dt.combine(self.today.date(), _t(18, 0), tzinfo=_mc.IST))
        self._clock.start()
        self.all_days = pd.bdate_range(end=self.today, periods=60)
        self.rows = {d: 100.0 + i for i, d in enumerate(self.all_days)}
        self.cutoff_old = self.all_days[-8]    # cached history ends here
        self.shift = 1.0
        self.splits = {}

    def tearDown(self):
        self._clock.stop()
        self.tmp.cleanup()

    def source_rows(self, start):
        days = [d for d in self.all_days if (start is None or d >= pd.Timestamp(start))]
        return [(d, self.rows[d] * self.shift, self.splits.get(d, 0.0)) for d in days]

    @staticmethod
    def make_df(rows):
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame({
            "DATE": [r[0] for r in rows],
            "OPEN_PRICE": [r[1] for r in rows], "HIGH_PRICE": [r[1] + 1 for r in rows],
            "LOW_PRICE": [r[1] - 1 for r in rows], "CLOSE_PRICE": [r[1] for r in rows],
            "ADJ_CLOSE": [r[1] for r in rows], "VOLUME": [1000] * len(rows),
            "DIVIDENDS": [0.0] * len(rows), "SPLITS": [r[2] for r in rows],
        })
        return df

    def seed_cache(self):
        """Store history up to cutoff_old (as a previous run would have)."""
        seed = [(d, self.rows[d], 0.0) for d in self.all_days if d <= self.cutoff_old]
        self.cm.save_historical_candles(HistoricalDataEngine._df_to_records("AAA", self.make_df(seed)))

    def test_cold_start_does_one_full_download(self):
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(df), len(self.all_days))
        self.assertEqual(self.engine.calls, [(None, "5y")])

    def test_fresh_cache_needs_no_network(self):
        self.engine.sync_symbol_data("AAA")
        self.engine.calls.clear()
        self.engine.sync_symbol_data("AAA")
        self.assertEqual(self.engine.calls, [])

    def test_stale_cache_downloads_only_missing_days(self):
        self.seed_cache()
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(self.engine.calls), 1)
        start, period = self.engine.calls[0]
        self.assertIsNotNone(start, "must use a start date, not a 5y period")
        self.assertLess(pd.Timestamp(start), self.cutoff_old + pd.Timedelta(days=1))
        self.assertEqual(len(df), len(self.all_days))
        self.assertEqual(df["CLOSE_PRICE"].iloc[-1], self.rows[self.all_days[-1]])

    def test_readjusted_history_triggers_full_replace(self):
        self.seed_cache()
        self.shift = 0.95                       # dividend re-adjustment: every historical close moved 5%
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(self.engine.calls), 2)
        self.assertIsNotNone(self.engine.calls[0][0])                  # incremental attempt first
        self.assertEqual(self.engine.calls[1], (None, "5y"))           # then full refresh
        # one consistent basis: every stored close equals the new adjusted value
        for d, close in zip(df["DATE"], df["CLOSE_PRICE"]):
            self.assertAlmostEqual(close, self.rows[d] * 0.95, places=6)

    def test_split_in_window_triggers_full_replace(self):
        self.seed_cache()
        self.splits[self.all_days[-3]] = 2.0
        self.engine.sync_symbol_data("AAA")
        self.assertEqual(self.engine.calls[-1], (None, "5y"))

    def test_source_down_serves_cached_history(self):
        self.seed_cache()
        self.engine.fail = True
        df = self.engine.sync_symbol_data("AAA")
        self.assertEqual(len(df), len([d for d in self.all_days if d <= self.cutoff_old]))

    def test_small_limit_does_not_truncate_later_larger_request(self):
        self.engine.sync_symbol_data("AAA")
        self.engine.df_cache.clear()
        self.assertEqual(len(self.engine.load_symbol_history("AAA", limit_days=10)), 10)
        self.assertEqual(len(self.engine.load_symbol_history("AAA", limit_days=50)), 50)   # used to return 10

    def test_sync_all_symbols_parallel(self):
        res = self.engine.sync_all_symbols([{"symbol": "AAA"}, {"symbol": "BBB"}, {"symbol": "CCC"}])
        self.assertEqual(res, {"AAA": True, "BBB": True, "CCC": True})


if __name__ == "__main__":
    unittest.main()
