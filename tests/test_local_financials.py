"""
Unit tests for LocalFinancialsParser and offline Ind-AS financials ingestion.
Strictly read-only / mock-based, zero network requests.
"""

import os
import shutil
import tempfile
import unittest
from tools.local_financials_parser import LocalFinancialsParser
from tools.forensic_financial_engine import ForensicFinancialEngine


class TestLocalFinancialsParser(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.parser = LocalFinancialsParser(data_dir=self.test_dir)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_save_and_load_local_statement(self):
        """Verify saving and standardizing Screener.in / BSE / NSE financial statements."""
        raw_feed = {
            "source": "Screener.in Feed",
            "name": "Tata Motors Ltd",
            "sector": "Automobile",
            "sales": "105000.50",
            "sales_prior": "95000.00",
            "net_profit": "7500.00",
            "special_items": "250.00",
            "other_income": "450.00",
            "cash_from_operations": "12000.00",
            "capex": "4000.00",
            "debtors": "15000.00",
            "debtors_prior": "14000.00",
            "borrowings": "18000.00",
            "cash_equivalents": "8000.00",
            "contingent_liabilities": "120.00",
            "promoter_holding": "46.4",
            "pledge_pct": "0.0"
        }

        self.parser.save_local_statement("TATAMOTORS", raw_feed)
        self.assertTrue(self.parser.has_local_statement("TATAMOTORS"))

        loaded = self.parser.load_local_statement("TATAMOTORS")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["revenue"], 105000.50)
        self.assertEqual(loaded["reported_pat"], 7500.00)
        self.assertEqual(loaded["cfo"], 12000.00)
        self.assertEqual(loaded["free_cashflow"], 8000.00)
        self.assertEqual(loaded["trade_receivables"], 15000.00)
        self.assertEqual(loaded["total_debt"], 18000.00)
        self.assertEqual(loaded["source"], "Screener.in Feed")

    def test_engine_uses_local_feed_when_available(self):
        """Forensic engine should prioritize offline cached Indian filings."""
        engine = ForensicFinancialEngine()
        engine.local_parser = self.parser

        raw_feed = {
            "source": "BSE/NSE Filing Feed",
            "company_name": "Local Indian Enterprise",
            "sector": "Industrial",
            "sales": 500.0,
            "sales_prior": 450.0,
            "net_profit": 60.0,
            "cash_from_operations": 65.0,
            "capex": 10.0,
            "trade_receivables": 30.0,
            "receivables_prior": 28.0,
            "total_debt": 0.0,
            "total_cash": 50.0
        }
        self.parser.save_local_statement("LOCALTEST", raw_feed)

        result = engine.analyze_company("LOCALTEST", price_override=150.0)
        self.assertEqual(result["statement_source"], "BSE/NSE Filing Feed")
        self.assertEqual(result["earnings_quality"]["reported_pat"], 60.0)
        self.assertGreaterEqual(result["cash_conversion"]["cfo_to_pat_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
