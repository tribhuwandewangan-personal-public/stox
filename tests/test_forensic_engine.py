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

    def test_governance_high_pledge_flag(self):
        """High pledge % should produce governance red flags and force AVOID verdict."""
        # Financials are otherwise clean — governance alone must trigger the flag
        clean_stmts = {
            "company_name": "PledgeRisk Corp Ltd",
            "sector": "Real Estate",
            "revenue": 500.0,
            "revenue_prior": 460.0,
            "reported_pat": 60.0,
            "exceptional_items": 0.0,
            "other_income": 1.0,
            "minority_interest": 0.0,
            "cfo": 58.0,
            "capex": 12.0,
            "trade_receivables": 40.0,
            "receivables_prior": 38.0,
            "total_debt": 0.0,
            "total_cash": 50.0,
        }

        # Directly inject a HIGH_RISK governance payload by patching
        # _audit_governance_telemetry so no network calls are needed.
        import unittest.mock as mock
        high_risk_gov = {
            "promoter_holding_pct": 22.5,
            "promoter_holding_flag": True,
            "pledge_risk": "HIGH",
            "audit_risk_score": 8.0,
            "board_risk_score": 7.0,
            "compensation_risk_score": None,
            "governance_grade": "HIGH_RISK",
            "governance_flags": [
                "Low promoter/insider holding: 22.5% (<30% threshold).",
                "High promoter pledge risk: ~35.0% of insider shares estimated as pledged.",
                "High audit risk score: 8/10 (Refinitiv ESG).",
            ],
        }

        with mock.patch.object(
            self.engine,
            "_audit_governance_telemetry",
            return_value=high_risk_gov,
        ):
            result = self.engine.analyze_company(
                symbol="PLEDGERISK",
                price_override=200.0,
                financial_statement_override=clean_stmts,
            )

        gov = result["governance_telemetry"]
        # Governance grade must be HIGH_RISK
        self.assertEqual(gov["governance_grade"], "HIGH_RISK")
        # Pledge risk must be flagged
        self.assertEqual(gov["pledge_risk"], "HIGH")
        # Promoter holding flag must be set
        self.assertTrue(gov["promoter_holding_flag"])
        # Must have at least 2 governance flags in the list
        self.assertGreaterEqual(len(gov["governance_flags"]), 2)

        # Governance flags must surface in top-level red_flags
        flag_text = " ".join(result["red_flags"])
        self.assertIn("Governance", flag_text)

        # HIGH_RISK governance must force AVOID verdict
        self.assertIn("AVOID", result["verdict"])
        self.assertIn("🔴", result["verdict_badge"])

    def test_piotroski_f_score_and_working_capital(self):
        """Test authentic multi-period Piotroski F-Score (0-9) and working capital DSO metrics."""
        strong_stmts = {
            "company_name": "Titanium Financials Ltd",
            "sector": "Industrial Goods",
            "revenue": 1000.0,
            "revenue_prior": 850.0,
            "reported_pat": 120.0,
            "reported_pat_prior": 90.0,
            "exceptional_items": 0.0,
            "other_income": 5.0,
            "minority_interest": 0.0,
            "cfo": 140.0,  # CFO > PAT
            "capex": 30.0,
            "trade_receivables": 100.0,  # DSO = (100 / 1000) * 365 = 36.5 days
            "receivables_prior": 90.0,
            "total_debt": 0.0,
            "total_debt_prior": 10.0,
            "total_cash": 150.0,
            "total_assets": 900.0,
            "total_assets_prior": 880.0,
            "current_ratio": 2.4,
            "current_ratio_prior": 1.9,
            "gross_profit": 420.0,
            "gross_profit_prior": 330.0,
            "shares_outstanding_cr": 10.0,
            "shares_prior_cr": 10.0,
        }

        result = self.engine.analyze_company(
            symbol="TITANIUM",
            price_override=500.0,
            financial_statement_override=strong_stmts,
        )

        f_score = result.get("piotroski_f_score")
        f_score_rating = result.get("piotroski_rating")
        self.assertIsNotNone(f_score)
        self.assertGreaterEqual(f_score, 7)
        self.assertEqual(f_score_rating, "STRONG")

        dso = result.get("debtor_days")
        self.assertIsNotNone(dso)
        self.assertAlmostEqual(dso, 36.5, places=1)


if __name__ == "__main__":
    unittest.main()
