import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from storage.cache_manager import CacheManager
from tools.sector_research_engine import SectorResearchEngine


MOCK_GEMINI_RESPONSE = {
    "normalized_sector": "Indian Power Transmission & Grid",
    "overview": {
        "thesis": "Grid expansion for renewables and data centers drives multi-year transformer demand.",
        "tam_and_growth": "INR 2.5L Cr capex over FY25-30 (~18% CAGR)",
        "unit_economics": "High operating leverage and CRGO pass-through clauses",
        "policy_and_regulatory_tailwinds": ["National Electricity Plan", "ISTS Waiver"],
        "bottleneck_summary": "765kV/400kV power transformers have 18-24 month lead times.",
        "demand_drivers": ["Renewable integration", "Data center load", "HVDC corridors"],
        "capex_cycle_stage": "Expansion",
        "key_risks": ["Execution delays", "CRGO steel supply"],
        "bear_case_triggers": ["Grid capex slowdown"],
    },
    "components": [
        {
            "name": "High-Voltage Transformers",
            "description": "Critical bottleneck equipment for substations.",
            "is_bottleneck_layer": True,
            "pricing_power": "High",
            "entry_barriers": "PGCIL type-testing & 24-month qualification",
            "capacity_bottleneck_reason": "Global shortage of CRGO steel & winding capacity",
            "value_capture_score": 9,
            "companies": [
                {
                    "symbol": "CGPOWER",
                    "company_name": "CG Power and Industrial Solutions",
                    "role_tag": "bottleneck",
                    "moat_type": "Capacity Scarcity",
                    "revenue_purity": "Pure-Play (>70%)",
                    "bottleneck_exposure": "Direct Chokepoint",
                    "rationale": "Severe global transformer capacity shortage gives strong pricing power.",
                },
                {
                    "symbol": "POWERGRID",
                    "company_name": "Power Grid Corporation of India",
                    "role_tag": "market_leader",
                    "moat_type": "Scale & Distribution",
                    "revenue_purity": "Pure-Play (>70%)",
                    "bottleneck_exposure": "Downstream",
                    "rationale": "Dominant central transmission utility.",
                },
            ],
        }
    ],
}


class TestSectorResearchEngine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_cache.db")
        self.cache = CacheManager(db_path=self.db_path, prefer_valkey=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _mock_workflow(self):
        wf = MagicMock()
        wf.hist_engine.load_symbol_history.return_value = pd.DataFrame({
            "DATE": pd.date_range("2026-10-01", periods=30),
            "CLOSE_PRICE": [100.0 + i for i in range(30)],
        })

        def fake_run_analysis(symbol, company_name="", sector="", force_refresh=False):
            score = 78.0 if symbol == "CGPOWER" else 64.0
            self.cache.save_agent_output(symbol, "Fundamental Analyst Agent", {"fundamental_score": score})
            self.cache.save_agent_output(symbol, "Technical Analysis Agent", {"technical_score": score - 2.0})
            return {
                "symbol": symbol,
                "last_price": 500.0,
                "structured_signal": {
                    "action_verdict": "BUY" if symbol == "CGPOWER" else "HOLD",
                    "evidence_score": score,
                    "confidence_rating": "HIGH (80%)",
                    "key_rationale": "Deterministic test rationale",
                },
            }

        wf.run_analysis.side_effect = fake_run_analysis
        return wf

    def test_missing_api_key_degrades_gracefully(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False), \
             patch("tools.sector_research_engine._load_gemini_api_key", return_value=""):
            engine = SectorResearchEngine(cache_manager=self.cache)
            res = engine.run_research("Indian Defence Electronics")
            self.assertEqual(res["status"], "missing_api_key")
            self.assertIn("GEMINI_API_KEY", res["error_message"])
            runs = self.cache.list_sector_research_runs()
            self.assertEqual(len(runs), 1)

    def test_gemini_discovery_plus_existing_quant_and_sqlite_persistence(self):
        wf = self._mock_workflow()
        gemini_mock = MagicMock(return_value=MOCK_GEMINI_RESPONSE)
        engine = SectorResearchEngine(
            cache_manager=self.cache,
            workflow_factory=lambda: wf,
            gemini_caller=gemini_mock,
        )

        res = engine.run_research("Power Grid")
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["normalized_sector"], "Indian Power Transmission & Grid")
        self.assertEqual(len(res["components"]), 1)
        self.assertEqual(len(res["stocks"]), 2)

        # Ranked highest composite_score first (CGPOWER bottleneck > POWERGRID leader)
        top = res["stocks"][0]
        self.assertEqual(top["symbol"], "CGPOWER")
        self.assertEqual(top["role_tag"], "bottleneck")
        self.assertEqual(top["verdict"], "BUY")
        self.assertEqual(top["quant_snapshot"]["moat_type"], "Capacity Scarcity")
        self.assertEqual(top["quant_snapshot"]["revenue_purity"], "Pure-Play (>70%)")
        self.assertIn("bottleneck_summary", res["overview"])
        self.assertEqual(res["components"][0]["pricing_power"], "High")
        self.assertGreater(top["composite_score"], res["stocks"][1]["composite_score"])

        # Rescore re-uses existing Stox workflow without calling Gemini again
        gemini_mock.reset_mock()
        rescored = engine.rescore_run(res["id"])
        gemini_mock.assert_not_called()
        self.assertEqual(len(rescored["stocks"]), 2)

        # Delete run from SQLite
        self.assertTrue(self.cache.delete_sector_research_run(res["id"]))
        self.assertIsNone(self.cache.get_sector_research_run(res["id"]))


if __name__ == "__main__":
    unittest.main()
