"""
Tests for the live-quote / scheduler / prediction-tracking / web-security work.
All clocks are injected, no network is used.

Run:  python -m unittest discover -s tests -v
"""

import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import date, datetime, time, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from storage.cache_manager import CacheManager
from tools import market_calendar as mc
from tools import outcome_tracker as ot
from tools import quote_tools as qt
from tools.scheduler import Scheduler
from tools.web_security import host_header_ok, post_guard_error, resolve_within, valid_symbol

IST = mc.IST


def at(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=IST)


# 2026-11-09 is a Monday
MON, TUE, FRI, SAT = (2026, 11, 9), (2026, 11, 10), (2026, 11, 6), (2026, 11, 7)


class MarketCalendarTests(unittest.TestCase):
    def test_session_states(self):
        self.assertEqual(mc.session_state(at(*MON, 8, 0)), "pre_open")
        self.assertEqual(mc.session_state(at(*MON, 9, 14)), "pre_open")
        self.assertEqual(mc.session_state(at(*MON, 9, 15)), "open")
        self.assertEqual(mc.session_state(at(*MON, 15, 29)), "open")
        self.assertEqual(mc.session_state(at(*MON, 15, 30)), "closed")
        self.assertEqual(mc.session_state(at(*SAT, 11, 0)), "holiday")

    def test_naive_datetimes_are_treated_as_ist(self):
        self.assertTrue(mc.is_market_open(datetime(2026, 11, 9, 10, 0)))

    def test_utc_input_is_converted(self):
        utc_time = datetime(2026, 11, 9, 4, 30, tzinfo=mc.timezone.utc)   # 10:00 IST
        self.assertTrue(mc.is_market_open(utc_time))

    def test_last_completed_session_waits_for_vendor_buffer(self):
        self.assertEqual(mc.last_completed_session(at(*MON, 11, 0)), date(*FRI))        # mid-session -> Friday
        self.assertEqual(mc.last_completed_session(at(*MON, 15, 40)), date(*FRI))       # bell rang, candle not final
        self.assertEqual(mc.last_completed_session(at(*MON, 15, 46)), date(*MON))       # buffer elapsed
        self.assertEqual(mc.last_completed_session(at(*SAT, 12, 0)), date(*FRI))
        self.assertEqual(mc.last_completed_session(at(2026, 11, 8, 12, 0)), date(*FRI))  # Sunday

    def test_next_open(self):
        self.assertEqual(mc.next_open(at(*MON, 8, 0)), at(*MON, 9, 15))
        self.assertEqual(mc.next_open(at(*MON, 10, 0)), at(*TUE, 9, 15))
        self.assertEqual(mc.next_open(at(*FRI, 16, 0)), at(*MON, 9, 15))

    def test_holidays_file_is_honoured(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "h.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"holidays": ["2026-11-10"]}')
            with unittest.mock.patch.object(mc, "HOLIDAYS_PATH", path):
                self.assertFalse(mc.is_trading_day(date(*TUE)))
                self.assertEqual(mc.session_state(at(*TUE, 11, 0)), "holiday")
                self.assertEqual(mc.next_open(at(*MON, 16, 0)), at(2026, 11, 11, 9, 15))
                self.assertEqual(mc.trading_days_after(date(*MON), date(2026, 11, 11)), 1)   # Tuesday skipped

    def test_missing_or_corrupt_holiday_file_is_harmless(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertEqual(mc.load_holidays(bad), set())
            self.assertEqual(mc.load_holidays(os.path.join(d, "missing.json")), set())

    def test_trading_days_after(self):
        self.assertEqual(mc.trading_days_after(date(*FRI), date(*MON)), 1)
        self.assertEqual(mc.trading_days_after(date(*MON), date(*MON)), 0)
        self.assertEqual(mc.trading_days_after(date(*MON), date(2026, 11, 13)), 4)


# ----------------------------------------------------------------------------------------------- quotes
class FakeProvider:
    def __init__(self, name, data=None, error=None):
        self.name, self.data, self.error, self.calls = name, data or {}, error, []

    def fetch(self, symbols):
        self.calls.append(list(symbols))
        if self.error:
            raise self.error
        return {s: dict(self.data[s]) for s in symbols if s in self.data}


def quote(sym, ltp, source, ts="2026-11-09T11:00:00+05:30", prev=None):
    return {"symbol": sym, "ltp": ltp, "prev_close": prev, "day_high": ltp + 1, "day_low": ltp - 1,
            "volume": 100, "quote_ts": ts, "source": source}


class QuoteServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "c.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_permission_error_disables_provider_and_falls_back(self):
        kite = FakeProvider("kite", error=qt.ProviderUnavailable("no permission"))
        yahoo = FakeProvider("yahoo", {"AAA": quote("AAA", 100.0, "yahoo")})
        svc = qt.QuoteService(self.cm, providers=[kite, yahoo])
        r1 = svc.refresh(["AAA"])
        self.assertEqual(r1["sources"], ["yahoo"])
        self.assertIn("kite", svc.disabled)
        svc.refresh(["AAA"])
        self.assertEqual(len(kite.calls), 1, "a disabled provider must not be retried every poll")
        self.assertEqual(self.cm.get_all_quotes()["AAA"]["source"], "yahoo")

    def test_transient_error_keeps_provider_enabled(self):
        flaky = FakeProvider("kite", error=qt.QuoteProviderError("timeout"))
        yahoo = FakeProvider("yahoo", {"AAA": quote("AAA", 100.0, "yahoo")})
        svc = qt.QuoteService(self.cm, providers=[flaky, yahoo])
        svc.refresh(["AAA"])
        svc.refresh(["AAA"])
        self.assertEqual(len(flaky.calls), 2)
        self.assertEqual(svc.disabled, {})

    def test_second_provider_only_asked_for_missing_symbols(self):
        kite = FakeProvider("kite", {"AAA": quote("AAA", 10.0, "kite")})
        yahoo = FakeProvider("yahoo", {"AAA": quote("AAA", 11.0, "yahoo"), "BBB": quote("BBB", 20.0, "yahoo")})
        svc = qt.QuoteService(self.cm, providers=[kite, yahoo])
        summary = svc.refresh(["AAA", "BBB"])
        self.assertEqual(yahoo.calls, [["BBB"]])
        self.assertEqual(summary["quoted"], 2)
        stored = self.cm.get_all_quotes()
        self.assertEqual((stored["AAA"]["source"], stored["BBB"]["source"]), ("kite", "yahoo"))

    def test_all_providers_failing_does_not_raise_and_keeps_old_quotes(self):
        self.cm.save_quotes([quote("AAA", 50.0, "yahoo")])
        svc = qt.QuoteService(self.cm, providers=[FakeProvider("yahoo", error=qt.QuoteProviderError("rate limited"))])
        summary = svc.refresh(["AAA"])
        self.assertEqual(summary["quoted"], 0)
        self.assertIn("rate limited", svc.last_error)
        self.assertEqual(self.cm.get_all_quotes()["AAA"]["ltp"], 50.0)

    def test_buggy_provider_cannot_kill_the_poller(self):
        class Boom:
            name = "boom"

            def fetch(self, symbols):
                raise ZeroDivisionError("bug")
        yahoo = FakeProvider("yahoo", {"AAA": quote("AAA", 1.0, "yahoo")})
        self.assertEqual(qt.QuoteService(self.cm, providers=[Boom(), yahoo]).refresh(["AAA"])["quoted"], 1)

    def test_prev_close_comes_from_stored_candles_before_the_quote_day(self):
        self.cm.save_historical_candles([
            {"symbol": "AAA", "date": "2026-11-05", "open": 1, "high": 1, "low": 1, "close": 90.0, "volume": 1},
            {"symbol": "AAA", "date": "2026-11-06", "open": 1, "high": 1, "low": 1, "close": 95.0, "volume": 1},
            {"symbol": "AAA", "date": "2026-11-09", "open": 1, "high": 1, "low": 1, "close": 99.0, "volume": 1},  # same day
        ])
        yahoo = FakeProvider("yahoo", {"AAA": quote("AAA", 100.0, "yahoo", ts="2026-11-09T11:00:00+05:30")})
        qt.QuoteService(self.cm, providers=[yahoo]).refresh(["AAA"])
        self.assertEqual(self.cm.get_all_quotes()["AAA"]["prev_close"], 95.0)

    def test_provider_given_prev_close_is_kept(self):
        kite = FakeProvider("kite", {"AAA": quote("AAA", 100.0, "kite", prev=97.0)})
        qt.QuoteService(self.cm, providers=[kite]).refresh(["AAA"])
        self.assertEqual(self.cm.get_all_quotes()["AAA"]["prev_close"], 97.0)

    def test_quotes_with_no_price_are_not_stored(self):
        bad = quote("AAA", 1.0, "yahoo")
        bad["ltp"] = None
        qt.QuoteService(self.cm, providers=[FakeProvider("yahoo", {"AAA": bad})]).refresh(["AAA"])
        self.assertEqual(self.cm.get_all_quotes(), {})

    def test_default_providers_always_end_with_yahoo(self):
        self.assertEqual([p.name for p in qt.default_providers("kite")], ["kite", "yahoo"])
        self.assertEqual([p.name for p in qt.default_providers("")], ["yahoo"])
        self.assertEqual([p.name for p in qt.default_providers("bogus, yahoo")], ["yahoo"])

    def test_kite_without_setup_is_unavailable_not_a_crash(self):
        kite = qt.KiteQuoteProvider(api_key="", token_path=os.path.join(self.tmp.name, "none.json"))
        with self.assertRaises(qt.ProviderUnavailable):
            kite.fetch(["AAA"])

    def test_kite_new_token_file_reenables_provider(self):
        token = os.path.join(self.tmp.name, "tok.json")
        kite = qt.KiteQuoteProvider(api_key="k", token_path=token)
        svc = qt.QuoteService(self.cm, providers=[kite, FakeProvider("yahoo", {"AAA": quote("AAA", 1.0, "yahoo")})])
        svc.refresh(["AAA"])
        self.assertIn("kite", svc.disabled)
        with open(token, "w", encoding="utf-8") as f:
            f.write('{"access_token": "x"}')
        svc._maybe_reenable(kite)
        self.assertNotIn("kite", svc.disabled)


class QuoteResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "c.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_stale_flag_only_during_market_hours(self):
        self.cm.save_quotes([quote("AAA", 100.0, "yahoo", ts="2026-11-09T10:00:00+05:30", prev=98.0)])
        live = qt.build_quotes_response(self.cm, now=at(*MON, 11, 0))      # 60 min old, market open
        self.assertTrue(live["quotes"]["AAA"]["stale"])
        self.assertTrue(live["market_open"])
        fresh = qt.build_quotes_response(self.cm, now=at(*MON, 10, 5))     # 5 min old
        self.assertFalse(fresh["quotes"]["AAA"]["stale"])
        closed = qt.build_quotes_response(self.cm, now=at(*MON, 17, 0))    # closed: age is expected
        self.assertFalse(closed["quotes"]["AAA"]["stale"])
        self.assertFalse(closed["market_open"])
        self.assertEqual(live["quotes"]["AAA"]["change_pct"], round((100 - 98) / 98 * 100, 2))

    def test_unlisted_holiday_is_detected_from_quote_timestamps(self):
        # "open" per the calendar at 11:00 but every quote is from the previous session
        self.cm.save_quotes([quote("AAA", 100.0, "yahoo", ts="2026-11-06T15:29:00+05:30")])
        r = qt.build_quotes_response(self.cm, now=at(*MON, 11, 0))
        self.assertEqual(r["market_state"], "holiday")
        self.assertFalse(r["market_open"])

    def test_prev_close_filled_at_read_time_when_candles_arrive_after_the_quote(self):
        self.cm.save_quotes([quote("AAA", 100.0, "yahoo", ts="2026-11-09T15:25:00+05:30")])      # no prev_close stored
        self.assertIsNone(qt.build_quotes_response(self.cm, now=at(*MON, 20, 0))["quotes"]["AAA"]["change_pct"])
        self.cm.save_historical_candles([candle("2026-11-06", 1, 2, 1, 95.0)])
        r = qt.build_quotes_response(self.cm, now=at(*MON, 20, 0))["quotes"]["AAA"]
        self.assertEqual(r["prev_close"], 95.0)
        self.assertEqual(r["change_pct"], round((100 - 95) / 95 * 100, 2))

    def test_not_flagged_as_holiday_in_the_first_minutes(self):
        self.cm.save_quotes([quote("AAA", 100.0, "yahoo", ts="2026-11-06T15:29:00+05:30")])
        r = qt.build_quotes_response(self.cm, now=at(*MON, 9, 20))
        self.assertEqual(r["market_state"], "open")

    def test_price_info_prefers_quote_then_close_then_analysis(self):
        q = {"ltp": 105.0, "prev_close": 100.0, "quote_ts": "2026-11-09T11:00:00+05:30"}
        info = qt.build_price_info(q, 99.0, "2026-11-06", 98.0, "2026-11-06")
        self.assertEqual((info["kind"], info["price"], info["change_pct"]), ("quote", 105.0, 5.0))
        self.assertEqual(info["drift_pct"], round((105 - 98) / 98 * 100, 2))
        stale_quote = {"ltp": 90.0, "prev_close": 91.0, "quote_ts": "2026-11-03T15:00:00+05:30"}   # older than newest close
        self.assertEqual(qt.build_price_info(stale_quote, 99.0, "2026-11-06", 98.0, None)["kind"], "close")
        self.assertEqual(qt.build_price_info(None, None, None, 98.0, None)["kind"], "analysis")
        nothing = qt.build_price_info(None, None, None, None, None)
        self.assertIsNone(nothing["price"])
        self.assertIsNone(nothing["drift_pct"])


class QuotePollerTests(unittest.TestCase):
    class Svc:
        def __init__(self, quoted=1, errors=None):
            self.calls, self.quoted, self.errors = 0, quoted, errors or []
            self.disabled, self.last_error = {}, None

        def refresh(self, symbols):
            self.calls += 1
            return {"quoted": self.quoted, "missing": 0, "sources": ["yahoo"], "errors": self.errors}

    def make(self, svc, clock):
        return qt.QuotePoller(svc, lambda: ["AAA"], poll_seconds=300, clock=clock)

    def test_polls_on_interval_only_while_open(self):
        now = {"t": at(*MON, 10, 0)}
        svc = self.Svc()
        poller = self.make(svc, lambda: now["t"])
        poller.poll_once(0)                                   # catch-up at start
        self.assertFalse(poller.tick(100))                    # open, but next poll not due yet
        self.assertTrue(poller.tick(301))                     # due
        self.assertEqual(svc.calls, 2)
        now["t"] = at(*MON, 15, 31)                           # market just closed -> exactly one closing poll
        self.assertTrue(poller.tick(1000))
        self.assertFalse(poller.tick(1400))
        self.assertEqual(svc.calls, 3)

    def test_idle_when_closed(self):
        svc = self.Svc()
        poller = self.make(svc, lambda: at(*SAT, 12, 0))
        self.assertFalse(poller.tick(10_000))
        self.assertEqual(svc.calls, 0)

    def test_backoff_grows_and_resets(self):
        svc = self.Svc(quoted=0, errors=["down"])
        poller = self.make(svc, lambda: at(*MON, 10, 0))
        poller.poll_once(0)
        first = poller._next_poll_at
        poller.poll_once(first)
        second = poller._next_poll_at - first
        self.assertGreater(second, first)                    # exponential
        for _ in range(10):
            poller.poll_once(0)
        self.assertLessEqual(poller._next_poll_at, 1800)     # capped at 30 minutes
        svc.quoted, svc.errors = 1, []
        poller.poll_once(0)
        self.assertEqual(poller._next_poll_at, 300)


# ----------------------------------------------------------------------------------------------- scheduler
class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "c.db"))
        self.sched = Scheduler(self.cm, workflow_getter=lambda: None, symbols_loader=lambda: [])
        self.ran = []
        self.sched.run_premarket = lambda: self.ran.append("premarket")
        self.sched.run_postclose = lambda: self.ran.append("postclose")

    def tearDown(self):
        self.tmp.cleanup()

    def test_premarket_due_from_0845_on_trading_days_only(self):
        self.assertEqual(self.sched.due_jobs(at(*SAT, 10, 0)), ["postclose"])   # weekend: only Friday's catch-up
        self.cm.set_state("sched.postclose.2026-11-06", "x")      # Friday done
        self.assertEqual(self.sched.due_jobs(at(*SAT, 10, 0)), [])
        self.assertEqual(self.sched.due_jobs(at(*MON, 8, 30)), [])
        self.assertEqual(self.sched.due_jobs(at(*MON, 8, 45)), ["premarket"])

    def test_postclose_waits_for_1600_then_runs_once(self):
        self.cm.set_state("sched.premarket.2026-11-09", "x")
        self.cm.set_state("sched.postclose.2026-11-06", "x")
        self.assertEqual(self.sched.due_jobs(at(*MON, 15, 50)), [])        # complete but before 16:00
        self.assertEqual(self.sched.due_jobs(at(*MON, 16, 0)), ["postclose"])
        self.assertEqual(self.sched.tick(at(*MON, 16, 1)), ["postclose"])
        self.assertEqual(self.sched.due_jobs(at(*MON, 16, 2)), [])         # recorded -> never repeated
        self.assertEqual(self.ran, ["postclose"])

    def test_missed_session_is_caught_up_next_day(self):
        self.cm.set_state("sched.premarket.2026-11-10", "x")
        # Monday's post-close never ran (PC off). Tuesday 10:00 -> catch up Monday
        self.assertEqual(self.sched.due_jobs(at(*TUE, 10, 0)), ["postclose"])

    def test_restart_does_not_repeat_finished_jobs(self):
        self.sched.tick(at(*MON, 17, 0))
        again = Scheduler(self.cm, workflow_getter=lambda: None, symbols_loader=lambda: [])
        self.assertEqual(again.due_jobs(at(*MON, 17, 30)), [])

    def test_failed_job_is_retried_not_recorded(self):
        def boom():
            raise RuntimeError("network down")
        self.sched.run_postclose = boom
        self.cm.set_state("sched.premarket.2026-11-09", "x")
        self.cm.set_state("sched.postclose.2026-11-06", "x")
        self.assertEqual(self.sched.tick(at(*MON, 17, 0)), [])
        self.assertEqual(self.sched.due_jobs(at(*MON, 17, 1)), ["postclose"])

    def test_premarket_not_due_after_close(self):
        self.cm.set_state("sched.postclose.2026-11-06", "x")
        self.assertNotIn("premarket", self.sched.due_jobs(at(*MON, 17, 0)))


# ----------------------------------------------------------------------------------------------- predictions
def candle(day, o, h, l, c):
    return {"symbol": "AAA", "date": day, "open": o, "high": h, "low": l, "close": c, "volume": 1}


class OutcomeTrackerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cm = CacheManager(db_path=os.path.join(self.tmp.name, "c.db"))

    def tearDown(self):
        self.tmp.cleanup()

    def predict(self, price=100.0, target=110.0, stop=95.0, as_of="2026-11-02", verdict="BUY", conf=80):
        self.cm.log_prediction({"symbol": "AAA", "as_of_date": as_of, "verdict": verdict, "confidence_pct": conf,
                                "price_at_signal": price, "target": target, "stop": stop, "horizon_days": 3})

    def resolve(self, candles):
        self.cm.save_historical_candles(candles)
        counts = ot.resolve_open_predictions(self.cm)
        return counts, self.cm.get_predictions()[0]

    def test_target_hit_long(self):
        self.predict()
        counts, row = self.resolve([candle("2026-11-03", 100, 104, 99, 103), candle("2026-11-04", 103, 111, 102, 109)])
        self.assertEqual(row["status"], "HIT_TARGET")
        self.assertEqual(row["outcome_price"], 110.0)
        self.assertEqual(row["return_pct"], 10.0)
        self.assertEqual(counts["HIT_TARGET"], 1)

    def test_stop_hit_long(self):
        self.predict()
        _, row = self.resolve([candle("2026-11-03", 100, 101, 94, 96)])
        self.assertEqual((row["status"], row["outcome_price"], row["return_pct"]), ("HIT_STOP", 95.0, -5.0))

    def test_same_candle_touching_both_counts_as_stop(self):
        self.predict()
        _, row = self.resolve([candle("2026-11-03", 100, 112, 94, 100)])
        self.assertEqual(row["status"], "HIT_STOP")

    def test_gap_down_through_stop_fills_at_the_open(self):
        self.predict()
        _, row = self.resolve([candle("2026-11-03", 90, 92, 88, 91)])
        self.assertEqual((row["status"], row["outcome_price"]), ("HIT_STOP", 90.0))
        self.assertEqual(row["return_pct"], -10.0)

    def test_expires_after_horizon_at_that_days_close(self):
        self.predict()
        counts, row = self.resolve([candle("2026-11-03", 100, 103, 98, 101), candle("2026-11-04", 101, 104, 99, 102),
                                    candle("2026-11-05", 102, 105, 100, 104)])
        self.assertEqual((row["status"], row["outcome_price"], row["return_pct"]), ("EXPIRED", 104.0, 4.0))

    def test_stays_open_until_enough_data(self):
        self.predict()
        counts, row = self.resolve([candle("2026-11-03", 100, 103, 98, 101)])
        self.assertEqual(row["status"], "OPEN")
        self.assertEqual(counts["still_open"], 1)

    def test_candles_on_or_before_signal_date_are_ignored(self):
        self.predict(as_of="2026-11-03")
        _, row = self.resolve([candle("2026-11-03", 100, 200, 1, 100), candle("2026-11-02", 100, 200, 1, 100)])
        self.assertEqual(row["status"], "OPEN")

    def test_short_side_mirrors(self):
        self.predict(price=100.0, target=90.0, stop=105.0, verdict="SELL")
        _, row = self.resolve([candle("2026-11-03", 100, 101, 89, 91)])
        self.assertEqual((row["status"], row["outcome_price"], row["return_pct"]), ("HIT_TARGET", 90.0, 10.0))
        self.predict(price=100.0, target=90.0, stop=105.0, verdict="SELL", as_of="2026-11-09")
        short_stop = [r for r in self.cm.get_predictions("OPEN")][0]
        res = ot._score(short_stop, [{"OPEN_PRICE": 100, "HIGH_PRICE": 106, "LOW_PRICE": 99, "CLOSE_PRICE": 104}])
        self.assertEqual((res[0], res[1], res[2]), ("HIT_STOP", 105.0, -5.0))

    def test_resolved_prediction_is_never_rewritten(self):
        self.predict()
        self.resolve([candle("2026-11-03", 100, 101, 94, 96)])
        self.predict(target=150.0, stop=50.0)                       # re-analysis of the same as_of date
        row = self.cm.get_predictions()[0]
        self.assertEqual((row["status"], row["target"]), ("HIT_STOP", 110.0))

    def test_open_prediction_is_refreshed_by_same_day_reanalysis(self):
        self.predict()
        self.predict(target=120.0)
        rows = self.cm.get_predictions()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["target"], 120.0)

    def test_build_record_parses_synth_output_and_rejects_unusable(self):
        synth = {"last_price": 100.0, "structured_signal": {
            "action_verdict": "BUY", "confidence_percentage": 82, "when_to_sell_target": "Rs. 1,110.50",
            "stop_loss": "Rs. 95.25", "when_to_buy_entry": "Rs. 99.00 - 101.50", "evidence_score": 0.5}}
        rec = ot.build_prediction_record("AAA", synth, "2026-11-06")
        self.assertEqual((rec["target"], rec["stop"], rec["entry_lo"], rec["entry_hi"]), (1110.5, 95.25, 99.0, 101.5))
        for bad in ({"last_price": "N/A", "structured_signal": synth["structured_signal"]},
                    {"last_price": 100.0, "structured_signal": {**synth["structured_signal"], "when_to_sell_target": "N/A"}},
                    {"last_price": 100.0, "structured_signal": {**synth["structured_signal"], "stop_loss": "N/A"}}):
            self.assertIsNone(ot.build_prediction_record("AAA", bad, "2026-11-06"))
        self.assertIsNone(ot.build_prediction_record("AAA", synth, None))

    def test_parse_price(self):
        self.assertEqual(ot.parse_price("Rs. 1,234.50"), 1234.5)
        self.assertEqual(ot.parse_price(99), 99.0)
        for junk in ("N/A", "", None, float("nan"), True):
            self.assertIsNone(ot.parse_price(junk), junk)

    def test_accuracy_report(self):
        self.predict(as_of="2026-11-02", conf=80)
        self.predict(as_of="2026-11-03", conf=60)
        self.cm.save_historical_candles([candle("2026-11-04", 100, 111, 99, 108)])
        ot.resolve_open_predictions(self.cm)
        self.predict(as_of="2026-11-05", conf=50)                   # stays open
        acc = ot.compute_accuracy(self.cm)
        self.assertEqual((acc["logged"], acc["resolved"], acc["open"]), (3, 2, 1))
        self.assertEqual(acc["by_verdict"]["BUY"]["n"], 2)
        self.assertEqual(acc["by_verdict"]["BUY"]["target_rate_pct"], 100.0)
        self.assertFalse(acc["by_verdict"]["BUY"]["reliable"], "2 samples must not be called reliable")
        self.assertEqual(set(acc["by_confidence"]), {"75+", "55-74"})
        empty = ot.compute_accuracy(CacheManager(db_path=os.path.join(self.tmp.name, "e.db")))
        self.assertEqual(empty["resolved"], 0)


# ----------------------------------------------------------------------------------------------- web security
class WebSecurityTests(unittest.TestCase):
    def test_symbol_validation(self):
        for ok in ("RELIANCE", "M&M", "BAJAJ-AUTO", "20MICRONS"):
            self.assertTrue(valid_symbol(ok), ok)
        for bad in ("", "a", "reliance", "X" * 21, "A B", "A'B", 'A"B', "<script>", "A;B", "../x", "A.NS", None, 5, "A\n"):
            self.assertFalse(valid_symbol(bad), repr(bad))

    def test_host_header(self):
        for ok in ("localhost:8765", "127.0.0.1:8765", "localhost", "[::1]:8765"):
            self.assertTrue(host_header_ok(ok), ok)
        for bad in ("evil.com", "evil.com:8765", "localhost.evil.com:8765", "192.168.1.5:8765", "", None, "127.0.0.1.evil.com"):
            self.assertFalse(host_header_ok(bad), bad)
        self.assertTrue(host_header_ok("anything", enforce=False))

    def test_post_guard(self):
        good = {"Content-Type": "application/json", "X-Stox-Request": "1", "Host": "localhost:8765"}
        self.assertIsNone(post_guard_error(good))
        self.assertIsNone(post_guard_error({**good, "Content-Type": "application/json; charset=utf-8"}))
        self.assertIsNone(post_guard_error({**good, "Origin": "http://localhost:8765"}))
        self.assertEqual(post_guard_error({**good, "Content-Type": "text/plain"})[0], 415)       # classic CSRF form post
        self.assertEqual(post_guard_error({**good, "Content-Type": "application/x-www-form-urlencoded"})[0], 415)
        no_header = {k: v for k, v in good.items() if k != "X-Stox-Request"}
        self.assertEqual(post_guard_error(no_header)[0], 403)
        self.assertEqual(post_guard_error({**good, "X-Stox-Request": "0"})[0], 403)
        self.assertEqual(post_guard_error({**good, "Origin": "http://evil.com"})[0], 403)
        self.assertEqual(post_guard_error({**good, "Origin": "http://localhost:9999"})[0], 403)

    def test_resolve_within_blocks_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            static = os.path.join(d, "static")
            os.makedirs(os.path.join(static, "sub"))
            for path, text in (("static/index.html", "ok"), ("static/sub/app.js", "js"), ("secret.txt", "TOKEN")):
                with open(os.path.join(d, path), "w", encoding="utf-8") as f:
                    f.write(text)
            self.assertIsNotNone(resolve_within(static, "index.html"))
            self.assertIsNotNone(resolve_within(static, "/sub/app.js"))
            for attack in ("../secret.txt", "/../secret.txt", "sub/../../secret.txt", "..\\secret.txt",
                           os.path.join(d, "secret.txt"), "sub", "missing.js", ""):
                self.assertIsNone(resolve_within(static, attack), attack)
            # sibling directory whose name merely starts with the base name must not pass a prefix check
            os.makedirs(os.path.join(d, "static_evil"))
            with open(os.path.join(d, "static_evil", "x.txt"), "w", encoding="utf-8") as f:
                f.write("x")
            self.assertIsNone(resolve_within(static, "../static_evil/x.txt"))


# ----------------------------------------------------------------------------------------------- indicators & history
try:
    import pandas as pd
    from tools.tech_tools import wilder_rsi
    from tools.historical_data_tools import HistoricalDataEngine
    HAVE_PANDAS = True
except ImportError:
    HAVE_PANDAS = False


@unittest.skipUnless(HAVE_PANDAS, "pandas not installed")
class RsiTests(unittest.TestCase):
    CLOSES = [44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
              45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439]

    def test_matches_published_wilder_reference_values(self):
        # StockCharts "RSI" worked example (Wilder smoothing)
        got = [round(x, 2) for x in wilder_rsi(pd.Series(self.CLOSES), 14).dropna()]
        self.assertEqual(got, [70.53, 66.32, 66.55, 69.41, 66.36, 57.97])

    def test_nan_until_enough_history_and_bounded(self):
        r = wilder_rsi(pd.Series(self.CLOSES), 14)
        self.assertTrue(r.iloc[:14].isna().all())
        self.assertTrue(wilder_rsi(pd.Series([1.0, 2.0, 3.0]), 14).isna().all())
        self.assertTrue(((r.dropna() >= 0) & (r.dropna() <= 100)).all())

    def test_edge_cases(self):
        self.assertEqual(wilder_rsi(pd.Series(range(1, 40), dtype=float), 14).iloc[-1], 100.0)   # only gains
        self.assertEqual(wilder_rsi(pd.Series([5.0] * 30), 14).iloc[-1], 50.0)                   # flat
        self.assertLess(wilder_rsi(pd.Series(range(40, 1, -1), dtype=float), 14).iloc[-1], 1.0)  # only losses


@unittest.skipUnless(HAVE_PANDAS, "pandas not installed")
class ProvisionalBarTests(unittest.TestCase):
    def frame(self, days):
        return pd.DataFrame({"DATE": pd.to_datetime(days), "CLOSE_PRICE": range(len(days))})

    def drop(self, df, now):
        with unittest.mock.patch.object(mc, "now_ist", return_value=now):
            return HistoricalDataEngine._drop_provisional_bar(df)

    def test_todays_bar_dropped_while_session_is_not_final(self):
        df = self.frame(["2026-11-05", "2026-11-06", "2026-11-09"])
        for t in (at(*MON, 10, 0), at(*MON, 15, 35), at(*MON, 15, 44)):
            self.assertEqual(len(self.drop(df, t)), 2, t)

    def test_todays_bar_kept_once_final(self):
        df = self.frame(["2026-11-05", "2026-11-06", "2026-11-09"])
        self.assertEqual(len(self.drop(df, at(*MON, 15, 46))), 3)
        self.assertEqual(len(self.drop(df, at(*MON, 20, 0))), 3)

    def test_earlier_days_never_dropped(self):
        df = self.frame(["2026-11-04", "2026-11-05", "2026-11-06"])
        self.assertEqual(len(self.drop(df, at(*MON, 10, 0))), 3)

    def test_empty_frame(self):
        self.assertTrue(self.drop(pd.DataFrame(), at(*MON, 10, 0)).empty)

    def test_stored_partial_bar_from_older_versions_is_hidden_on_load(self):
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "c.db"))
            cm.save_historical_candles([candle("2026-11-06", 1, 2, 1, 2), candle("2026-11-09", 1, 2, 1, 2)])
            engine = HistoricalDataEngine(cache_manager=cm)
            with unittest.mock.patch.object(mc, "now_ist", return_value=at(*MON, 11, 0)):
                self.assertEqual(len(engine._load_cached_df("AAA")), 1)
            with unittest.mock.patch.object(mc, "now_ist", return_value=at(*MON, 18, 0)):
                self.assertEqual(len(engine._load_cached_df("AAA")), 2)

    def test_freshness_follows_last_completed_session(self):
        with tempfile.TemporaryDirectory() as d:
            engine = HistoricalDataEngine(cache_manager=CacheManager(db_path=os.path.join(d, "c.db")))
            friday = datetime(2026, 11, 6)
            with unittest.mock.patch.object(mc, "now_ist", return_value=at(*MON, 11, 0)):      # Monday mid-session
                self.assertTrue(engine._is_up_to_date("AAA", friday))
            with unittest.mock.patch.object(mc, "now_ist", return_value=at(*MON, 18, 0)):      # Monday evening
                self.assertFalse(engine._is_up_to_date("AAA", friday))                         # Monday's candle is due
                engine._last_sync_attempt["AAA"] = __import__("time").time()
                self.assertTrue(engine._is_up_to_date("AAA", friday), "recently asked -> don't hammer the vendor")


if __name__ == "__main__":
    unittest.main()
