import os
import tempfile
import unittest
from datetime import datetime, timedelta

import pandas as pd

from storage.cache_manager import CacheManager
from tools.catalyst_backtest import run_catalyst_backtest
from tools.catalyst_scanner import CatalystScannerEngine
from tools.catalyst_scorer import (
    classify_catalyst_category,
    extract_deal_value_cr,
    score_catalyst,
)


class TestCatalystEarlyWarningSystem(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "cat_test.db")
        self.cache = CacheManager(db_path=self.db_path, prefer_valkey=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_revenue_scaled_financial_impact(self):
        # Same Rs 500 Cr order on Rs 500 Cr revenue vs Rs 10,000 Cr revenue
        small_co = score_catalyst(
            title="Bagged Rs 500 Cr railway wagon order",
            source="NSE",
            annual_revenue_cr=500.0,
            market_ctx={"rvol": 2.1, "delivery_pct": 58.0, "pct_change": 3.5},
        )
        large_co = score_catalyst(
            title="Bagged Rs 500 Cr railway wagon order",
            source="NSE",
            annual_revenue_cr=10000.0,
            market_ctx={"rvol": 2.1, "delivery_pct": 58.0, "pct_change": 3.5},
        )
        self.assertEqual(small_co["category"], "LARGE_ORDER_WIN")
        self.assertEqual(small_co["deal_value_cr"], 500.0)
        self.assertGreater(
            small_co["score_breakdown"]["financial_impact"],
            large_co["score_breakdown"]["financial_impact"],
        )
        self.assertGreaterEqual(small_co["total_score"], 80.0)
        self.assertEqual(small_co["tier"], "A")

    def test_jv_tech_transfer_classification_and_novelty_penalty(self):
        cat = classify_catalyst_category(
            "Strategic partnership and technology transfer with Woojin for railway manufacturing"
        )
        self.assertEqual(cat, "STRATEGIC_JV_TECH_TRANSFER")
        self.assertEqual(extract_deal_value_cr("Contract worth ₹ 1,250 crore"), 1250.0)

        fresh = score_catalyst("Strategic JV", recent_count_30d=0)
        repeat = score_catalyst("Strategic JV", recent_count_30d=2)
        self.assertGreater(fresh["score_breakdown"]["news_novelty"], repeat["score_breakdown"]["news_novelty"])

    def test_scanner_persistence_and_historical_backtest(self):
        # Seed 80 trading days of candles where price rallies +18% after 2026-09-01
        dates = pd.bdate_range(start="2026-08-01", periods=80)
        records = []
        for i, dt in enumerate(dates):
            px = 100.0 + (i * 0.4 if i >= 22 else 0.0)
            records.append({
                "symbol": "JWL",
                "date": dt.strftime("%Y-%m-%d"),
                "open": px,
                "high": px + 2.0,
                "low": px - 1.0,
                "close": px,
                "adj_close": px,
                "volume": 500000 if i == 79 else 100000,
                "dividends": 0.0,
                "splits": 0.0,
                "delivery_pct": 58.0,
            })
        self.cache.save_historical_candles(records)

        scanner = CatalystScannerEngine(cache_manager=self.cache)
        ev = scanner.analyze_and_save_event(
            symbol="JWL",
            title="Bagged Rs 600 Cr multi-year railway wagon order",
            source="NSE",
            announced_at="2026-09-01",
            annual_revenue_cr=1200.0,
        )
        self.assertIn(ev["tier"], ("A", "B"))
        stored = self.cache.get_catalyst_events(symbol="JWL")
        self.assertEqual(len(stored), 1)

        bt = run_catalyst_backtest(cache_manager=self.cache)
        self.assertEqual(bt["total_evaluated"], 1)
        self.assertGreater(bt["summary"]["avg_ret_20d_pct"], 0.0)
        self.assertEqual(bt["summary"]["breakout_hit_rate_pct"], 100.0)


if __name__ == "__main__":
    unittest.main()
