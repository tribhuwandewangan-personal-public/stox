"""
Local Financial Statement Ingestion & Parser Engine.
Allows direct ingestion and offline cached loading of local/Ind-AS quarterly and annual
financial statement feeds (e.g. Screener.in / Trendlyne / BSE / NSE formats) without network reliance.

Deterministic, rule-based, read-only advisory module.
No broker order placement.
"""

import os
import json
from typing import Dict, Any, Optional
import math


def _num(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely converts any input into a float or returns default."""
    if val is None or isinstance(val, bool):
        return default
    try:
        f = float(str(val).replace(",", "").strip())
        return f if math.isfinite(f) else default
    except (ValueError, TypeError):
        return default


class LocalFinancialsParser:
    """
    Parses and loads standardized Ind-AS and Indian financial statements
    from local cache or provided dictionaries/files.
    """
    def __init__(self, data_dir: Optional[str] = None):
        self.data_dir = data_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "financials"
        )
        os.makedirs(self.data_dir, exist_ok=True)

    def get_statement_path(self, symbol: str) -> str:
        """Returns the expected JSON file path for a given ticker's cached statement."""
        sym_clean = symbol.upper().strip().replace(".NS", "").replace(".BO", "")
        return os.path.join(self.data_dir, f"{sym_clean}.json")

    def has_local_statement(self, symbol: str) -> bool:
        """Checks if a local statement file exists for the symbol."""
        return os.path.exists(self.get_statement_path(symbol))

    def load_local_statement(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Loads and standardizes local financial statements from the local JSON file if present.
        """
        path = self.get_statement_path(symbol)
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            return self.standardize_statement(raw_data)
        except Exception:
            return None

    def save_local_statement(self, symbol: str, data: Dict[str, Any]) -> str:
        """
        Saves a financial statement dataset to local JSON cache for offline ingestion.
        """
        path = self.get_statement_path(symbol)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return path

    def standardize_statement(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Standardizes varying Screener.in, Trendlyne, or BSE/NSE schema variations
        into the uniform statement dict required by ForensicFinancialEngine.
        """
        data: Dict[str, Any] = {
            "source": raw_data.get("source", "Local Indian Filing Feed"),
            "company_name": raw_data.get("company_name", raw_data.get("name", "")),
            "sector": raw_data.get("sector", ""),
            "revenue": _num(raw_data.get("revenue") or raw_data.get("sales") or raw_data.get("total_revenue"), 0.0),
            "revenue_prior": _num(raw_data.get("revenue_prior") or raw_data.get("sales_prior"), 0.0),
            "reported_pat": _num(raw_data.get("reported_pat") or raw_data.get("pat") or raw_data.get("net_profit"), 0.0),
            "other_income": _num(raw_data.get("other_income") or raw_data.get("non_operating_income"), 0.0),
            "exceptional_items": _num(raw_data.get("exceptional_items") or raw_data.get("special_items"), 0.0),
            "cfo": _num(raw_data.get("cfo") or raw_data.get("cash_from_operations") or raw_data.get("operating_cash_flow"), 0.0),
            "capex": abs(_num(raw_data.get("capex") or raw_data.get("capital_expenditure"), 0.0)),
            "minority_interest": abs(_num(raw_data.get("minority_interest") or raw_data.get("non_controlling_interest"), 0.0)),
            "trade_receivables": _num(raw_data.get("trade_receivables") or raw_data.get("debtors") or raw_data.get("receivables"), 0.0),
            "receivables_prior": _num(raw_data.get("receivables_prior") or raw_data.get("debtors_prior"), 0.0),
            "total_debt": _num(raw_data.get("total_debt") or raw_data.get("borrowings"), 0.0),
            "total_cash": _num(raw_data.get("total_cash") or raw_data.get("cash_equivalents"), 0.0),
            "contingent_liabilities": _num(raw_data.get("contingent_liabilities"), 0.0),
            "promoter_holding_pct": _num(raw_data.get("promoter_holding_pct") or raw_data.get("promoter_holding")),
            "promoter_pledge_pct": _num(raw_data.get("promoter_pledge_pct") or raw_data.get("pledge_pct"), 0.0),
        }

        # Calculate free cash flow if cfo is provided
        fcf = raw_data.get("free_cashflow")
        if fcf is not None:
            data["free_cashflow"] = _num(fcf, 0.0)
        else:
            data["free_cashflow"] = data["cfo"] - data["capex"]

        return data
