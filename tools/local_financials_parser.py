"""
Local Financial Statement Ingestion & Parser Engine.
Allows direct ingestion and offline cached loading of local/Ind-AS quarterly and annual
financial statement feeds (e.g. Screener.in / Trendlyne / BSE / NSE formats) without network reliance,
along with filing freshness checks and NSE shareholding/pledge parsing.

Deterministic, rule-based, read-only advisory module.
No broker order placement.
"""

import os
import re
import json
import math
import urllib.request
from datetime import datetime, date
from typing import Dict, Any, Optional


def _num(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely converts any input into a float or returns default."""
    if val is None or isinstance(val, bool):
        return default
    try:
        f = float(str(val).replace(",", "").replace("%", "").strip())
        return f if math.isfinite(f) else default
    except (ValueError, TypeError):
        return default


def _parse_iso_date(val: Any) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val).strip()[:20]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:11].strip(), fmt).date()
        except ValueError:
            continue
    return None


def compute_filing_freshness(
    raw_data: Dict[str, Any],
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Evaluates staleness of a local/Ind-AS filing based on `period_end_date` / `filing_date`
    or `fiscal_year` (e.g. "FY2025" -> 2025-03-31).
    Returns {"status": "FRESH"|"AGING"|"STALE"|"UNKNOWN", "filing_age_days": int|None, "is_stale": bool, ...}.
    """
    ref_day = _parse_iso_date(as_of_date) if as_of_date is not None else datetime.now().date()
    fy_raw = str(raw_data.get("fiscal_year") or "").strip()
    p_date = (
        _parse_iso_date(raw_data.get("filing_date"))
        or _parse_iso_date(raw_data.get("period_end_date"))
        or _parse_iso_date(raw_data.get("as_of"))
    )

    if p_date is None and fy_raw:
        m = re.match(r"^(?:FY)?\s*(\d{2}|\d{4})(?:\s*[-/]\s*(\d{2}|\d{4}))?$", fy_raw, re.I)
        if m:
            y1 = int(m.group(1))
            y2 = m.group(2)
            end_yr = int(y2) if y2 else y1
            if end_yr < 100:
                end_yr += 2000
            p_date = date(end_yr, 3, 31)

    if p_date is None:
        return {
            "fiscal_year": fy_raw or None,
            "period_end_date": None,
            "filing_age_days": None,
            "is_stale": False,
            "status": "UNKNOWN",
        }

    age_days = max(0, (ref_day - p_date).days)
    if age_days <= 180:
        status = "FRESH"
    elif age_days <= 420:
        status = "AGING"
    else:
        status = "STALE"

    return {
        "fiscal_year": fy_raw or None,
        "period_end_date": p_date.isoformat(),
        "filing_age_days": age_days,
        "is_stale": age_days > 420,
        "status": status,
    }


def parse_nse_shareholding_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parses NSE/BSE shareholding & pledge JSON shapes (nested or flat keys) into normalized floats.
    Never invents missing percentages.
    """
    if not isinstance(payload, dict):
        return {
            "promoter_holding_pct": None,
            "promoter_pledge_pct": None,
            "fii_holding_pct": None,
            "dii_holding_pct": None,
            "quarter_end_date": None,
        }

    prom_node = payload.get("promoterAndPromoterGroup")
    prom_raw = (
        prom_node.get("totalPct") or prom_node.get("shareholdingPct") or prom_node.get("pct")
        if isinstance(prom_node, dict)
        else prom_node
    )
    if prom_raw is None:
        prom_raw = (
            payload.get("promoter_holding_pct")
            if payload.get("promoter_holding_pct") is not None
            else payload.get("promoter_holding", payload.get("promoterPct"))
        )

    pledge_node = payload.get("pledgedOrEncumbered") or (
        prom_node.get("pledgedOrEncumbered") if isinstance(prom_node, dict) else None
    )
    pledge_raw = (
        pledge_node.get("pct") or pledge_node.get("pledgedPct") or pledge_node.get("shareholdingPct")
        if isinstance(pledge_node, dict)
        else pledge_node
    )
    if pledge_raw is None:
        pledge_raw = (
            payload.get("promoter_pledge_pct")
            if payload.get("promoter_pledge_pct") is not None
            else payload.get("pledge_pct", payload.get("pledgedPct"))
        )

    pub_node = payload.get("publicShareholding") if isinstance(payload.get("publicShareholding"), dict) else {}
    inst_node = payload.get("institutions") if isinstance(payload.get("institutions"), dict) else {}
    fii_raw = (
        payload.get("fii_holding_pct")
        if payload.get("fii_holding_pct") is not None
        else payload.get("fiiPct", pub_node.get("fiiPct", inst_node.get("fiiPct")))
    )
    dii_raw = (
        payload.get("dii_holding_pct")
        if payload.get("dii_holding_pct") is not None
        else payload.get("diiPct", pub_node.get("diiPct", inst_node.get("diiPct")))
    )

    q_date = (
        payload.get("quarter_end_date")
        or payload.get("shareholding_quarter")
        or payload.get("periodEndDate")
        or payload.get("asOfDate")
        or payload.get("date")
    )

    return {
        "promoter_holding_pct": _num(prom_raw),
        "promoter_pledge_pct": _num(pledge_raw),
        "fii_holding_pct": _num(fii_raw),
        "dii_holding_pct": _num(dii_raw),
        "quarter_end_date": str(q_date).strip() if q_date else None,
    }


def fetch_nse_shareholding(symbol: str, timeout: int = 6) -> Optional[Dict[str, Any]]:
    """
    Best-effort fetch of latest NSE quarterly shareholding disclosures.
    Degrades gracefully returning None if NSE API blocks or network is unavailable.
    """
    sym = str(symbol or "").upper().strip()
    if not sym:
        return None
    url = f"https://www.nseindia.com/api/corporate-share-holdings-master?index=equities&symbol={sym}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json,*/*",
        "Referer": "https://www.nseindia.com/",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode("utf-8", errors="replace"))
        if isinstance(raw, list) and raw:
            raw = raw[0]
        if isinstance(raw, dict) and raw:
            parsed = parse_nse_shareholding_payload(raw)
            if parsed.get("promoter_holding_pct") is not None or parsed.get("promoter_pledge_pct") is not None:
                return parsed
    except Exception:
        pass
    return None


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
        Missing prior-year or optional items remain None (never fabricated).
        """
        freshness = compute_filing_freshness(raw_data)
        sh_parsed = parse_nse_shareholding_payload(raw_data)

        shares_cr = _num(raw_data.get("shares_outstanding_cr"))
        if shares_cr is None:
            raw_shares = _num(raw_data.get("shares_outstanding"))
            if raw_shares is not None and raw_shares > 0:
                shares_cr = round(raw_shares / 1e7, 4)

        shares_prior_cr = _num(raw_data.get("shares_prior_cr"))
        if shares_prior_cr is None:
            raw_shares_p = _num(raw_data.get("shares_prior"))
            if raw_shares_p is not None and raw_shares_p > 0:
                shares_prior_cr = round(raw_shares_p / 1e7, 4)

        ca = _num(raw_data.get("current_assets"))
        cl = _num(raw_data.get("current_liabilities"))
        cr_cur = _num(raw_data.get("current_ratio"))
        if cr_cur is None and ca is not None and cl is not None and cl > 0:
            cr_cur = round(ca / cl, 4)

        ca_p = _num(raw_data.get("current_assets_prior"))
        cl_p = _num(raw_data.get("current_liabilities_prior"))
        cr_prior = _num(raw_data.get("current_ratio_prior"))
        if cr_prior is None and ca_p is not None and cl_p is not None and cl_p > 0:
            cr_prior = round(ca_p / cl_p, 4)

        data: Dict[str, Any] = {
            "source": raw_data.get("source", "Local Indian Filing Feed"),
            "company_name": raw_data.get("company_name", raw_data.get("name", "")),
            "sector": raw_data.get("sector", ""),
            "fiscal_year": freshness["fiscal_year"],
            "period_end_date": freshness["period_end_date"],
            "filing_freshness": freshness,
            "revenue": _num(raw_data.get("revenue") or raw_data.get("sales") or raw_data.get("total_revenue"), 0.0),
            "revenue_prior": _num(raw_data.get("revenue_prior") or raw_data.get("sales_prior"), 0.0),
            "reported_pat": _num(raw_data.get("reported_pat") or raw_data.get("pat") or raw_data.get("net_profit"), 0.0),
            "reported_pat_prior": _num(raw_data.get("reported_pat_prior") or raw_data.get("pat_prior") or raw_data.get("net_profit_prior")),
            "other_income": _num(raw_data.get("other_income") or raw_data.get("non_operating_income"), 0.0),
            "exceptional_items": _num(raw_data.get("exceptional_items") or raw_data.get("special_items"), 0.0),
            "cfo": _num(raw_data.get("cfo") or raw_data.get("cash_from_operations") or raw_data.get("operating_cash_flow"), 0.0),
            "capex": abs(_num(raw_data.get("capex") or raw_data.get("capital_expenditure"), 0.0)),
            "minority_interest": abs(_num(raw_data.get("minority_interest") or raw_data.get("non_controlling_interest"), 0.0)),
            "trade_receivables": _num(raw_data.get("trade_receivables") or raw_data.get("debtors") or raw_data.get("receivables"), 0.0),
            "receivables_prior": _num(raw_data.get("receivables_prior") or raw_data.get("debtors_prior"), 0.0),
            "total_debt": _num(raw_data.get("total_debt") or raw_data.get("borrowings"), 0.0),
            "total_debt_prior": _num(raw_data.get("total_debt_prior") or raw_data.get("borrowings_prior")),
            "long_term_debt": _num(raw_data.get("long_term_debt")),
            "long_term_debt_prior": _num(raw_data.get("long_term_debt_prior")),
            "total_cash": _num(raw_data.get("total_cash") or raw_data.get("cash_equivalents"), 0.0),
            "contingent_liabilities": _num(raw_data.get("contingent_liabilities"), 0.0),
            "total_assets": _num(raw_data.get("total_assets")),
            "total_assets_prior": _num(raw_data.get("total_assets_prior")),
            "current_assets": ca,
            "current_assets_prior": ca_p,
            "current_liabilities": cl,
            "current_liabilities_prior": cl_p,
            "current_ratio": cr_cur,
            "current_ratio_prior": cr_prior,
            "shares_outstanding_cr": shares_cr,
            "shares_prior_cr": shares_prior_cr,
            "gross_profit": _num(raw_data.get("gross_profit")),
            "gross_profit_prior": _num(raw_data.get("gross_profit_prior")),
            "gross_margin_pct": _num(raw_data.get("gross_margin_pct")),
            "gross_margin_prior_pct": _num(raw_data.get("gross_margin_prior_pct")),
            "ebitda": _num(raw_data.get("ebitda")),
            "ebitda_prior": _num(raw_data.get("ebitda_prior")),
            "depreciation": _num(raw_data.get("depreciation")),
            "depreciation_prior": _num(raw_data.get("depreciation_prior")),
            "ppe": _num(raw_data.get("ppe")),
            "ppe_prior": _num(raw_data.get("ppe_prior")),
            "sga_expense": _num(raw_data.get("sga_expense")),
            "sga_expense_prior": _num(raw_data.get("sga_expense_prior")),
            "book_value_per_share": _num(raw_data.get("book_value_per_share") or raw_data.get("book_value")),
            # BFSI-specific banking/NBFC health ratios
            "roa_pct": _num(raw_data.get("roa_pct")),
            "roe_pct": _num(raw_data.get("roe_pct")),
            "nim_pct": _num(raw_data.get("nim_pct")),
            "gnpa_pct": _num(raw_data.get("gnpa_pct")),
            "nnpa_pct": _num(raw_data.get("nnpa_pct")),
            "casa_pct": _num(raw_data.get("casa_pct")),
            "crar_pct": _num(raw_data.get("crar_pct")),
            "pb_ratio": _num(raw_data.get("pb_ratio")),
            # Governance & Shareholding telemetry
            "promoter_holding_pct": sh_parsed["promoter_holding_pct"],
            "promoter_pledge_pct": _num(raw_data.get("promoter_pledge_pct") if raw_data.get("promoter_pledge_pct") is not None else raw_data.get("pledge_pct"), 0.0),
            "promoter_holding_prior_pct": _num(raw_data.get("promoter_holding_prior_pct")),
            "fii_holding_pct": sh_parsed["fii_holding_pct"],
            "dii_holding_pct": sh_parsed["dii_holding_pct"],
            "shareholding_quarter": sh_parsed["quarter_end_date"],
        }

        fcf = raw_data.get("free_cashflow")
        if fcf is not None:
            data["free_cashflow"] = _num(fcf, 0.0)
        else:
            data["free_cashflow"] = data["cfo"] - data["capex"]

        return data
