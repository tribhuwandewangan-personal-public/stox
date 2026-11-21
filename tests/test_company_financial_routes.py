"""
Integration tests for company, earnings, and financial API endpoints in dashboard_server.
Tests handle_get directly or via local server invocation.
"""

import unittest
import json
from unittest.mock import MagicMock
from dashboard_server import DashboardHandler


class DummyRequest:
    def makefile(self, *args, **kwargs):
        import io
        return io.BytesIO(b"")


class TestDashboardCompanyFinancialEndpoints(unittest.TestCase):
    def setUp(self):
        # Instantiate a handler with mock socket
        self.handler = DashboardHandler.__new__(DashboardHandler)
        self.handler.headers = {"Host": "localhost:8000"}
        self.handler.send_response = MagicMock()
        self.handler.send_header = MagicMock()
        self.handler.end_headers = MagicMock()
        self.handler.wfile = MagicMock()
        self.handler.rfile = MagicMock()

    def _get_json_response(self, path):
        self.handler.path = path
        written_bytes = bytearray()
        self.handler.wfile.write.side_effect = lambda b: written_bytes.extend(b)
        self.handler.do_GET()
        return json.loads(written_bytes.decode("utf-8"))

    def test_company_profile_endpoint(self):
        """GET /api/company/INFY returns company profile and governance."""
        data = self._get_json_response("/api/company/INFY")
        self.assertEqual(data.get("ticker"), "INFY")
        self.assertIn("governanceGrade", data)
        self.assertIn("earningsQuality", data)

    def test_earnings_endpoint(self):
        """GET /api/earnings/TCS returns earnings quality structure."""
        data = self._get_json_response("/api/earnings/TCS")
        self.assertIn("reportedPAT", data)
        self.assertIn("sustainablePAT", data)
        self.assertIn("exceptionalItems", data)

    def test_financial_endpoints(self):
        """GET /api/financial/INFY/income, balance, cashflow returns statements."""
        inc = self._get_json_response("/api/financial/INFY/income")
        self.assertIsInstance(inc, list)
        self.assertIn("reportedPAT", inc[0])

        bal = self._get_json_response("/api/financial/INFY/balance")
        self.assertIsInstance(bal, list)
        self.assertIn("totalDebt", bal[0])

        cf = self._get_json_response("/api/financial/INFY/cashflow")
        self.assertIsInstance(cf, list)
        self.assertIn("cashFromOperations", cf[0])


if __name__ == "__main__":
    unittest.main()
