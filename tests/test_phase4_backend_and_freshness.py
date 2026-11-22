"""
Deterministic offline tests for Phase 4 Wave 4A (Tasks 4.7 & 4.8):
- Special weekend/Budget sessions (2026-02-01) and 16:15 IST EOD data buffer
- Chunked Yahoo provider, IST conversion before date slicing, auto_adjust=True,
  finalized EOD close precedence over earlier intraday quotes, Kite VWAP/circuit persistence
- Bulk SQLite queries (get_candles_bulk_summary, get_cached_events_bulk), no tech_cache table,
  macro_cache & shared_market_bulletin pruning
- Market-hours window throttling on BackgroundMacroSentinel
- Starlette NaN-safe _json_response & consistent HTTP 400/500 error codes across dashboard_server & routes
- Monitored universe coverage & orphan file removal (stox.db, tools/patch_html.py).
"""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from datetime import date, datetime
from unittest.mock import MagicMock

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from storage.cache_manager import CacheManager
from tools import market_calendar as mc
from tools import quote_tools as qt

IST = mc.IST


class Phase4BackendAndFreshnessTests(unittest.TestCase):
    def test_market_calendar_special_session_and_1615_buffer(self):
        # 2026-02-01 is Sunday (Union Budget special NSE trading session)
        self.assertTrue(mc.is_trading_day(date(2026, 2, 1)))
        # 16:15 IST EOD vendor buffer
        mon = date(2026, 11, 9)
        self.assertFalse(mc.is_session_complete(mon, datetime(2026, 11, 9, 16, 14, tzinfo=IST)))
        self.assertTrue(mc.is_session_complete(mon, datetime(2026, 11, 9, 16, 16, tzinfo=IST)))

    def test_yahoo_chunking_ist_slicing_eod_precedence_and_kite_fields(self):
        # 1. Yahoo chunks > 50 symbols and converts UTC -> IST before slicing session date
        calls = []

        def fake_download(tickers, **kwargs):
            calls.append((list(tickers), kwargs.get("auto_adjust")))
            # UTC 2026-11-09 19:00 UTC == 2026-11-10 00:30 IST (and next bar 04:00 UTC == 09:30 IST)
            idx = pd.to_datetime([
                "2026-11-09 09:00:00+00:00",  # 14:30 IST on 2026-11-09
                "2026-11-09 19:00:00+00:00",  # 00:30 IST on 2026-11-10!
                "2026-11-10 04:00:00+00:00",  # 09:30 IST on 2026-11-10
            ])
            if len(tickers) == 1:
                return pd.DataFrame({
                    "Open": [100.0, 102.0, 104.0],
                    "High": [101.0, 103.0, 106.0],
                    "Low": [99.0, 101.0, 103.0],
                    "Close": [100.5, 102.5, 105.0],
                    "Volume": [1000, 2000, 3000],
                }, index=idx)
            cols = {}
            for t in tickers:
                for col, vals in (("Open", [100.0, 102.0, 104.0]), ("High", [101.0, 103.0, 106.0]),
                                  ("Low", [99.0, 101.0, 103.0]), ("Close", [100.5, 102.5, 105.0]),
                                  ("Volume", [1000, 2000, 3000])):
                    cols[(t, col)] = vals
            df = pd.DataFrame(cols, index=idx)
            df.columns = pd.MultiIndex.from_tuples(df.columns)
            return df

        syms = [f"SYM{i:03d}" for i in range(65)]
        with unittest.mock.patch("yfinance.download", side_effect=fake_download):
            out = qt.YahooQuoteProvider().fetch(syms)

        self.assertEqual(len(calls), 2)
        self.assertEqual(len(calls[0][0]), qt.YAHOO_CHUNK)
        self.assertEqual(len(calls[1][0]), 15)
        self.assertTrue(calls[0][1])  # auto_adjust=True
        # IST slicing combined 19:00 UTC (00:30 IST Nov 10) + 04:00 UTC (09:30 IST Nov 10) -> Vol 5000, Low 101.0
        self.assertEqual(out["SYM000"]["volume"], 5000)
        self.assertEqual(out["SYM000"]["day_low"], 101.0)
        self.assertTrue(out["SYM000"]["quote_ts"].startswith("2026-11-10T"))

        # 2. Kite VWAP + circuit limits persist in quotes table and API response
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "q.db"))
            cm.save_quotes([{
                "symbol": "INFY",
                "ltp": 1520.0,
                "prev_close": 1500.0,
                "day_high": 1530.0,
                "day_low": 1495.0,
                "volume": 500000,
                "vwap": 1512.4,
                "upper_circuit": 1650.0,
                "lower_circuit": 1350.0,
                "quote_ts": "2026-11-10T11:00:00+05:30",
                "source": "kite",
            }])
            resp = qt.build_quotes_response(cm, now=datetime(2026, 11, 10, 11, 5, tzinfo=IST))
            self.assertEqual(resp["quotes"]["INFY"]["vwap"], 1512.4)
            self.assertEqual(resp["quotes"]["INFY"]["upper_circuit"], 1650.0)
            self.assertEqual(resp["quotes"]["INFY"]["lower_circuit"], 1350.0)

        # 3. Finalized EOD close (1535.0 on 2026-11-10) overrides an earlier same-day 11:00 IST quote (1520.0)
        intraday_q = {"ltp": 1520.0, "prev_close": 1500.0, "quote_ts": "2026-11-10T11:00:00+05:30", "source": "yahoo"}
        p_info = qt.build_price_info(intraday_q, 1535.0, "2026-11-10", 1500.0, "2026-11-09", prev_close_from_candle=1500.0)
        self.assertEqual(p_info["kind"], "close")
        self.assertEqual(p_info["price"], 1535.0)
        # Whereas post-close or next-day quote wins cleanly
        post_close_q = {"ltp": 1540.0, "prev_close": 1500.0, "quote_ts": "2026-11-10T15:30:00+05:30", "source": "kite"}
        p_info2 = qt.build_price_info(post_close_q, 1535.0, "2026-11-10", 1500.0, "2026-11-09")
        self.assertEqual(p_info2["kind"], "quote")
        self.assertEqual(p_info2["price"], 1540.0)

    def test_bulk_queries_no_tech_cache_and_macro_pruning(self):
        with tempfile.TemporaryDirectory() as d:
            cm = CacheManager(db_path=os.path.join(d, "bulk.db"))
            with cm._get_connection() as conn:
                self.assertIsNone(
                    conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='tech_cache'").fetchone()
                )

            cm.save_historical_candles([
                {"symbol": "AAA", "date": f"2026-10-{i+1:02d}", "open": 100 + i, "high": 105 + i,
                 "low": 95 + i, "close": 100 + i, "adj_close": 100 + i, "volume": 1000}
                for i in range(30)
            ])
            bulk = cm.get_candles_bulk_summary(["AAA"])
            self.assertEqual(len(bulk["AAA"]["sparkline"]), 25)
            self.assertEqual(bulk["AAA"]["latest_close"], 129.0)
            self.assertEqual(bulk["AAA"]["prev_close"], 128.0)
            self.assertEqual(bulk["AAA"]["high_52w"], 134.0)
            self.assertEqual(bulk["AAA"]["low_52w"], 95.0)

            for i in range(15):
                cm.save_market_bulletin("Bullish", f"summary {i}", {})
            cm.save_macro([{"indicator": "S&P 500", "value": 6000.0, "unit": "pts", "summary": "now"}])
            res = cm.prune_macro_history(keep_bulletins=5, keep_days=7)
            self.assertEqual(res["bulletins_pruned"], 10)
            with cm._get_connection() as conn:
                cnt = conn.execute("SELECT COUNT(*) FROM shared_market_bulletin").fetchone()[0]
            self.assertEqual(cnt, 5)

    def test_sentinel_market_hours_starlette_nan_safe_and_consistent_errors(self):
        from agents.macro_sentinel import BackgroundMacroSentinel
        from api.services import safe_json_dumps

        # Sentinel market window check
        self.assertTrue(BackgroundMacroSentinel.is_active_window(datetime(2026, 11, 9, 10, 0, tzinfo=IST)))
        self.assertFalse(BackgroundMacroSentinel.is_active_window(datetime(2026, 11, 9, 22, 0, tzinfo=IST)))
        self.assertFalse(BackgroundMacroSentinel.is_active_window(datetime(2026, 11, 7, 11, 0, tzinfo=IST)))  # Saturday

        # safe_json_dumps converts NaN/Inf to JSON null (used by Starlette _json_response & dashboard_server)
        parsed = json.loads(safe_json_dumps({"x": float("nan"), "y": float("inf"), "z": 12.5}).decode("utf-8"))
        self.assertEqual(parsed, {"x": None, "y": None, "z": 12.5})

        # Optional Starlette test if installed in environment
        try:
            from starlette.testclient import TestClient
            from starlette.applications import Starlette
            from api import routes

            resp = routes._json_response({"x": float("nan"), "y": float("inf"), "z": 12.5})
            self.assertEqual(json.loads(resp.body.decode("utf-8")), {"x": None, "y": None, "z": 12.5})
            with tempfile.TemporaryDirectory() as d:
                cm = CacheManager(db_path=os.path.join(d, "rt.db"))
                routes.set_managers(cm, MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), MagicMock(), lambda: None)
                client = TestClient(Starlette(routes=routes.routes))
                self.assertEqual(client.get("/api/history?days=30").status_code, 400)
        except ImportError:
            pass

        # HTTP 400 consistency on missing symbol in dashboard_server
        from dashboard_server import DashboardHandler
        handler = DashboardHandler.__new__(DashboardHandler)
        handler.headers = {"Host": "localhost:8765"}
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()
        handler.rfile = MagicMock()
        handler.path = "/api/history?days=30"
        handler.do_GET()
        handler.send_response.assert_called_with(400)

        handler.send_response.reset_mock()
        handler.path = "/api/recommendation"
        handler.do_GET()
        handler.send_response.assert_called_with(400)

    def test_monitored_universe_coverage_and_housekeeping(self):
        from api.services import load_active_monitored_symbols
        from tools.long_term_strategy import _load_curated_symbols_cached

        monitored = load_active_monitored_symbols()
        syms = [m["symbol"] for m in monitored]
        self.assertGreater(len(syms), 20)
        self.assertEqual(len(syms), len(set(syms)))  # strictly deduplicated

        # Cached curated loader works cleanly
        self.assertGreater(len(_load_curated_symbols_cached()), 10)

        # Orphan files removed
        self.assertFalse(os.path.exists(os.path.join(ROOT, "stox.db")))
        self.assertFalse(os.path.exists(os.path.join(ROOT, "tools", "patch_html.py")))


if __name__ == "__main__":
    unittest.main()
