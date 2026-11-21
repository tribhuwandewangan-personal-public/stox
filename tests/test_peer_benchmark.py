"""
Unit tests for PeerBenchmarkEngine.
Verifies:
  - Sector peer resolution and mapping
  - Deterministic sector median computations (P/E, P/B, ROE, Margin)
  - Comparison labels (CHEAPER, EXPENSIVE, IN_LINE, SUPERIOR, LAGGING)
  - Deterministic peer verdict generation
Strictly read-only test with no network dependency.
"""

import unittest
from unittest.mock import MagicMock
from tools.peer_benchmark_engine import PeerBenchmarkEngine, _resolve_sector


class TestPeerBenchmarkEngine(unittest.TestCase):
    def setUp(self):
        self.engine = PeerBenchmarkEngine()

    def test_sector_resolution(self):
        """Test canonical mapping of various sector inputs."""
        self.assertEqual(_resolve_sector("IT"), "IT")
        self.assertEqual(_resolve_sector("Information Technology"), "IT")
        self.assertEqual(_resolve_sector("auto"), "AUTO")
        self.assertEqual(_resolve_sector("Automobile"), "AUTO")
        self.assertEqual(_resolve_sector("Banking"), "BANKING")
        self.assertEqual(_resolve_sector("Non-Existent-Sector-1234"), None)

    def test_get_peer_group_excludes_subject(self):
        """Test that peer group excludes the subject symbol and stays <= 5."""
        peers = self.engine.get_peer_group("TCS", "IT")
        self.assertNotIn("TCS", peers)
        self.assertLessEqual(len(peers), 5)
        self.assertIn("INFY", peers)

    def test_compute_peer_benchmarks_deterministic(self):
        """Test benchmark calculation with mock fundamental data."""
        mock_fund_engine = MagicMock()

        # Subject company INFY: P/E 20.0, ROE 30.0%, Margin 18.0%
        # Peers:
        # TCS: P/E 30.0, ROE 25.0%, Margin 20.0%
        # WIPRO: P/E 24.0, ROE 15.0%, Margin 12.0%
        # HCLTECH: P/E 26.0, ROE 22.0%, Margin 15.0%
        metrics_map = {
            "INFY": {
                "pe_ratio": 20.0,
                "pb_ratio": 6.0,
                "roe_pct": 30.0,
                "profit_margin_pct": 18.0,
                "debt_to_equity": 0.0,
            },
            "TCS": {
                "pe_ratio": 30.0,
                "pb_ratio": 12.0,
                "roe_pct": 25.0,
                "profit_margin_pct": 20.0,
                "debt_to_equity": 0.0,
            },
            "WIPRO": {
                "pe_ratio": 24.0,
                "pb_ratio": 3.0,
                "roe_pct": 15.0,
                "profit_margin_pct": 12.0,
                "debt_to_equity": 10.0,
            },
            "HCLTECH": {
                "pe_ratio": 26.0,
                "pb_ratio": 5.0,
                "roe_pct": 22.0,
                "profit_margin_pct": 15.0,
                "debt_to_equity": 5.0,
            },
            "TECHM": {
                "pe_ratio": "N/A",
                "pb_ratio": "N/A",
                "roe_pct": "N/A",
                "profit_margin_pct": "N/A",
                "debt_to_equity": "N/A",
            },
            "LTIM": {
                "pe_ratio": None,
                "pb_ratio": None,
                "roe_pct": None,
                "profit_margin_pct": None,
                "debt_to_equity": None,
            }
        }

        mock_fund_engine.get_fundamental_metrics.side_effect = lambda sym: metrics_map.get(sym, {})

        result = self.engine.compute_peer_benchmarks("INFY", "IT", mock_fund_engine)

        self.assertEqual(len(result["peers_analyzed"]), 3)
        # Peers considered with numeric P/E: [30.0, 24.0, 26.0] -> median is 26.0
        self.assertEqual(result["sector_median_pe"], 26.0)
        # INFY P/E is 20.0 vs median 26.0 -> 23% discount -> CHEAPER
        self.assertEqual(result["peer_comparison"]["pe_vs_peers"], "CHEAPER")
        # INFY ROE is 30.0 vs peers median 22.0 -> >20% better -> SUPERIOR
        self.assertEqual(result["peer_comparison"]["roe_vs_peers"], "SUPERIOR")
        self.assertIn("discount to sector median P/E", result["peer_verdict"])


if __name__ == "__main__":
    unittest.main()
