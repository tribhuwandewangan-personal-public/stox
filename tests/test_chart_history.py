import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd

from api.services import get_history_response_body
from tools.tech_tools import TechnicalAnalysisEngine


def _make_daily_df(days: int = 600) -> pd.DataFrame:
    end = datetime(2026, 11, 25)
    dates = pd.bdate_range(end=end, periods=days)
    base = 100.0 + pd.Series(range(len(dates)), dtype=float) * 0.2
    return pd.DataFrame({
        "DATE": dates,
        "SYMBOL": "TESTSYM",
        "OPEN_PRICE": base,
        "HIGH_PRICE": base + 2.0,
        "LOW_PRICE": base - 1.5,
        "CLOSE_PRICE": base + 0.5,
        "VOLUME": [10000] * len(dates),
    })


def _make_intraday_df(interval: str = "1h", periods: int = 120) -> pd.DataFrame:
    freq = {"15m": "15min", "30m": "30min", "1h": "1h"}[interval]
    dates = pd.date_range(end=datetime(2026, 11, 25, 15, 15), periods=periods, freq=freq)
    base = 200.0 + pd.Series(range(len(dates)), dtype=float) * 0.1
    return pd.DataFrame({
        "DATE": dates,
        "SYMBOL": "TESTSYM",
        "OPEN_PRICE": base,
        "HIGH_PRICE": base + 1.0,
        "LOW_PRICE": base - 1.0,
        "CLOSE_PRICE": base + 0.25,
        "VOLUME": [5000] * len(dates),
    })


class TestChartHistoryIntervals(unittest.TestCase):
    def setUp(self):
        self.rag = MagicMock()
        self.rag.load_symbol_history.return_value = _make_daily_df(600)
        self.rag.fetch_intraday_history.side_effect = lambda sym, interval="1h", days=365: _make_intraday_df(interval, 120)
        self.engine = TechnicalAnalysisEngine(rag_engine=self.rag)

    def test_normalize_chart_interval(self):
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("15m"), "15m")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("30m"), "30m")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("60m"), "1h")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1h"), "1h")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1d"), "1d")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1w"), "1wk")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1wk"), "1wk")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1M"), "1mo")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("1mo"), "1mo")
        self.assertEqual(TechnicalAnalysisEngine.normalize_chart_interval("invalid"), "1d")

    def test_default_1y_daily_candles(self):
        res = self.engine.get_chart_data("TESTSYM")
        self.assertEqual(res["interval"], "1d")
        self.assertEqual(res["days"], 365)
        self.assertGreater(len(res["candles"]), 200)
        self.assertLessEqual(len(res["candles"]), 270)
        self.assertEqual(len(res["candles"][0]["date"]), 10)  # YYYY-MM-DD

    def test_weekly_and_monthly_resampling(self):
        res_wk = self.engine.get_chart_data("TESTSYM", limit_days=365, interval="1wk")
        self.assertEqual(res_wk["interval"], "1wk")
        self.assertGreaterEqual(len(res_wk["candles"]), 50)
        self.assertLessEqual(len(res_wk["candles"]), 55)

        res_mo = self.engine.get_chart_data("TESTSYM", limit_days=365, interval="1mo")
        self.assertEqual(res_mo["interval"], "1mo")
        self.assertGreaterEqual(len(res_mo["candles"]), 12)
        self.assertLessEqual(len(res_mo["candles"]), 14)

    def test_intraday_intervals_and_60d_note(self):
        res_15m = self.engine.get_chart_data("TESTSYM", limit_days=365, interval="15m")
        self.assertEqual(res_15m["interval"], "15m")
        self.assertIn("60 days", res_15m.get("note", ""))
        self.assertIn(":", res_15m["candles"][0]["date"])  # YYYY-MM-DD HH:MM

        res_1h = self.engine.get_chart_data("TESTSYM", limit_days=365, interval="1h")
        self.assertEqual(res_1h["interval"], "1h")
        self.assertNotIn("note", res_1h)
        self.assertIn(":", res_1h["candles"][0]["date"])

    def test_history_memo_separates_intervals(self):
        cache_mgr = MagicMock()
        cache_mgr.get_latest_candle_date.return_value = "2026-11-25"
        body_1d = json.loads(get_history_response_body("TESTSYM", 365, cache_mgr, self.engine, interval="1d"))
        body_1wk = json.loads(get_history_response_body("TESTSYM", 365, cache_mgr, self.engine, interval="1wk"))
        self.assertEqual(body_1d["interval"], "1d")
        self.assertEqual(body_1wk["interval"], "1wk")
        self.assertGreater(len(body_1d["candles"]), len(body_1wk["candles"]))

    def test_intraday_sqlite_incremental_ticks(self):
        import os, tempfile
        from storage.cache_manager import CacheManager
        from tools.historical_data_tools import HistoricalDataEngine

        with tempfile.TemporaryDirectory() as tmpdir:
            cm = CacheManager(db_path=os.path.join(tmpdir, "t.db"), prefer_valkey=False)
            cm.save_intraday_candles("TESTSYM", "1h", [
                {"dt": "2026-11-24 10:15:00", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
                {"dt": "2026-11-25 15:15:00", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1200},
            ])
            eng = HistoricalDataEngine(cache_manager=cm)
            # Mock _intraday_is_up_to_date=True to verify zero network fetch when ticks are current
            eng._intraday_is_up_to_date = lambda sym, iv, dt: True
            df = eng.fetch_intraday_history("TESTSYM", interval="1h", days=365)
            self.assertEqual(len(df), 2)
            self.assertEqual(float(df["CLOSE_PRICE"].iloc[-1]), 102.0)


if __name__ == "__main__":
    unittest.main()
