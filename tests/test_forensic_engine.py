"""
Unit tests for ForensicFinancialEngine.
Verifies the detection of:
  - Exceptional income distortion
  - Minority interest leakage
  - Negative / poor cash conversion (CFO < PAT)
  - Working capital divergence
  - Deterministic recommendation verdict (AVOID_OR_VALUE_TRAP, BUY, etc.)
Strictly read-only test.
"""

import unittest
from tools.forensic_financial_engine import ForensicFinancialEngine


class TestForensicFinancialEngine(unittest.TestCase):
    def setUp(self):
        self.engine = ForensicFinancialEngine()

    def test_aeroenter_case_study(self):
        """
        Simulate the exact AEROENTER scenario:
        - Reported PAT: 38.24 Cr
        - Minority Interest: 12.58 Cr (32.9% belonging to subsidiary minority shareholders)
        - Exceptional Income: 8.50 Cr
        - CFO: 14.50 Cr (only 38% conversion vs reported profit)
        - Receivables grew +48% while revenue only grew +12%
        - Current Price: Rs. 210
        """
        aeroenter_stmts = {
            "company_name": "Aeroflex / AeroEnter Enterprises",
            "sector": "Industrial Engineering",
            "revenue": 180.0,
            "revenue_prior": 160.0,  # +12.5% revenue growth
            "reported_pat": 38.24,
            "exceptional_items": 8.50,
            "other_income": 4.20,
            "minority_interest": 12.58,  # > 30% minority leak
            "cfo": 14.50,  # CFO/PAT = 38%
            "capex": 8.00,
            "trade_receivables": 52.0,
            "receivables_prior": 35.0,  # +48.5% receivables growth (massive working capital trap)
            "total_debt": 45.0,
            "total_cash": 12.0
        }

        result = self.engine.analyze_company(
            symbol="AEROENTER",
            price_override=210.0,
            financial_statement_override=aeroenter_stmts
        )

        # 1. Earnings Quality verification
        eq = result["earnings_quality"]
        self.assertEqual(eq["reported_pat"], 38.24)
        self.assertEqual(eq["adjusted_pat"], 29.74)
        # Sustainable PAT must be significantly lower than reported PAT
        self.assertLess(eq["sustainable_pat"], 20.0)
        self.assertGreater(eq["distortion_pct"], 40.0)
        self.assertEqual(eq["quality_grade"], "SEVERELY_DISTORTED")

        # 2. Cash Conversion verification
        cf = result["cash_conversion"]
        self.assertLess(cf["cfo_to_pat_ratio"], 0.45)
        self.assertTrue(cf["working_capital_divergence"])

        # 3. Subsidiary verification
        sub = result["subsidiary_attribution"]
        self.assertGreater(sub["minority_share_pct"], 30.0)
        self.assertTrue(sub["subsidiary_leakage_flag"])

        # 4. Red flags detection
        flags = result["red_flags"]
        self.assertGreaterEqual(len(flags), 3)
        flag_text = " ".join(flags)
        self.assertIn("distortion", flag_text.lower())
        self.assertIn("cash conversion", flag_text.lower())
        self.assertIn("minority", flag_text.lower())

        # 5. Recommendation Verdict: Must NOT be BUY! Must be flagged as AVOID / VALUE TRAP
        self.assertIn("AVOID", result["verdict"])
        self.assertIn("🔴", result["verdict_badge"])
        self.assertLess(result["margin_of_safety_pct"], 0)

    def test_clean_compounder_case(self):
        """
        Simulate a clean, high-quality compounding business:
        - Reported PAT: 50.0 Cr (100% core operating, 0 exceptional, 0 minority interest)
        - CFO: 55.0 Cr (CFO/PAT = 110%, pristine cash conversion)
        - Net cash positive balance sheet
        - Receivables in line with revenue
        - Trading at a 25% discount to fair value
        """
        clean_stmts = {
            "company_name": "Quality Compounder Ltd",
            "sector": "Consumer Goods",
            "revenue": 300.0,
            "revenue_prior": 250.0,
            "reported_pat": 50.0,
            "exceptional_items": 0.0,
            "other_income": 2.0,
            "minority_interest": 0.0,
            "cfo": 55.0,
            "capex": 10.0,
            "trade_receivables": 25.0,
            "receivables_prior": 22.0,
            "total_debt": 0.0,
            "total_cash": 40.0
        }

        result = self.engine.analyze_company(
            symbol="CLEANCO",
            price_override=100.0,
            financial_statement_override=clean_stmts
        )

        eq = result["earnings_quality"]
        self.assertLess(eq["distortion_pct"], 10.0)
        self.assertEqual(eq["quality_grade"], "HIGH_QUALITY")

        cf = result["cash_conversion"]
        self.assertGreaterEqual(cf["cfo_to_pat_ratio"], 1.0)
        self.assertFalse(cf["working_capital_divergence"])

        self.assertEqual(len(result["red_flags"]), 0)
        self.assertIn(result["verdict"], ["BUY", "STRONG_BUY", "HOLD"])


if __name__ == "__main__":
    unittest.main()
