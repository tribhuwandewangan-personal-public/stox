"""
Forensic Financial Analysis & Due-Diligence Recommendation Engine.
Deterministic, rule-based quantitative auditor designed to catch:
  1. Exceptional / one-off income distorting reported profitability.
  2. Subsidiary & minority profits not attributable to parent shareholders.
  3. Divergence between reported PAT and Cash Flow from Operations (CFO).
  4. Working capital deterioration (receivables / inventory swelling faster than sales).
  5. Solvency and debt-service vulnerability (Debt/EBITDA, Interest Coverage).
  6. Normalized valuation and true Margin of Safety.

Strictly Read-Only & Advisory Mode (No broker order placement).
"""

from typing import Dict, Any, List, Optional
import math
import re
from storage.cache_manager import CacheManager
from tools.fundamental_tools import FundamentalAnalysisEngine
from tools.peer_benchmark_engine import PeerBenchmarkEngine
from tools.local_financials_parser import LocalFinancialsParser, compute_filing_freshness

_CAPITAL_MARKETS_RE = re.compile(
    r"\b(capital markets|fintech|exchange|exchanges|depository|broking|brokerage|wealth|asset management|amc|credit rating)\b",
    re.I,
)
_CAPITAL_MARKETS_SYMBOLS = {
    "BSE", "NSE", "CDSL", "MCX", "IEX", "ANGELONE", "GROWW", "360ONE", "5PAISA",
    "CAMS", "KFINTECH", "MOTILALOFS", "NUVAMA", "ANANDRATHI", "PRUDENT",
    "HDFCAMC", "NAM-INDIA", "UTIAMC", "ABSLAMC", "CRISIL", "ICRA", "CAREERP",
}
_BFSI_RE = re.compile(
    r"\b(bank|banking|nbfc|financial services|insurance|housing finance|microfinance)\b",
    re.I,
)


def _is_capital_markets(sector: str, symbol: str = "") -> bool:
    if symbol and symbol.upper().strip() in _CAPITAL_MARKETS_SYMBOLS:
        return True
    return bool(sector and _CAPITAL_MARKETS_RE.search(sector))


def _is_bfsi_sector(sector: str, symbol: str = "") -> bool:
    if _is_capital_markets(sector, symbol):
        return False
    return bool(sector and _BFSI_RE.search(sector))


_SECTOR_VALUATION_BENCHMARKS: Dict[str, Dict[str, float]] = {
    "CAPITAL_MARKETS": {"norm_pe": 38.0, "norm_ev_ebitda": 24.0, "norm_margin_pct": 30.0},
    "DEFENCE": {"norm_pe": 35.0, "norm_ev_ebitda": 22.0, "norm_margin_pct": 14.0},
    "EMS": {"norm_pe": 40.0, "norm_ev_ebitda": 23.0, "norm_margin_pct": 3.5},
    "FMCG": {"norm_pe": 36.0, "norm_ev_ebitda": 22.0, "norm_margin_pct": 11.0},
    "CONSUMER": {"norm_pe": 35.0, "norm_ev_ebitda": 21.0, "norm_margin_pct": 10.0},
    "CAPITAL_GOODS": {"norm_pe": 33.0, "norm_ev_ebitda": 20.0, "norm_margin_pct": 9.0},
    "IT": {"norm_pe": 26.0, "norm_ev_ebitda": 16.5, "norm_margin_pct": 14.5},
    "PHARMA": {"norm_pe": 27.0, "norm_ev_ebitda": 17.0, "norm_margin_pct": 14.0},
    "CHEMICALS": {"norm_pe": 30.0, "norm_ev_ebitda": 18.0, "norm_margin_pct": 11.5},
    "AUTO": {"norm_pe": 24.0, "norm_ev_ebitda": 14.5, "norm_margin_pct": 7.0},
    "TELECOM": {"norm_pe": 28.0, "norm_ev_ebitda": 13.0, "norm_margin_pct": 10.0},
    "INFRA": {"norm_pe": 24.0, "norm_ev_ebitda": 13.5, "norm_margin_pct": 9.0},
    "ENERGY": {"norm_pe": 18.0, "norm_ev_ebitda": 10.0, "norm_margin_pct": 8.0},
    "METALS": {"norm_pe": 15.0, "norm_ev_ebitda": 8.5, "norm_margin_pct": 7.5},
    "DEFAULT": {"norm_pe": 24.0, "norm_ev_ebitda": 14.5, "norm_margin_pct": 10.0},
}


def _get_sector_valuation_benchmark(sector: str, symbol: str = "") -> Dict[str, float]:
    if _is_capital_markets(sector, symbol):
        return _SECTOR_VALUATION_BENCHMARKS["CAPITAL_MARKETS"]
    sec_l = str(sector or "").lower()
    if any(k in sec_l for k in ("electronics manufacturing", "ems", "semiconductor")):
        return _SECTOR_VALUATION_BENCHMARKS["EMS"]
    if any(k in sec_l for k in ("defence", "aerospace", "shipbuilding")):
        return _SECTOR_VALUATION_BENCHMARKS["DEFENCE"]
    if any(k in sec_l for k in ("fmcg", "staples", "food", "beverage", "agri")):
        return _SECTOR_VALUATION_BENCHMARKS["FMCG"]
    if any(k in sec_l for k in ("consumer", "retail", "jewel", "paint")):
        return _SECTOR_VALUATION_BENCHMARKS["CONSUMER"]
    if any(k in sec_l for k in ("capital goods", "electrical", "engineering", "industrial", "machinery")):
        return _SECTOR_VALUATION_BENCHMARKS["CAPITAL_GOODS"]
    if any(k in sec_l for k in ("information technology", "technology", "software", "it services")):
        return _SECTOR_VALUATION_BENCHMARKS["IT"]
    if any(k in sec_l for k in ("pharma", "healthcare", "hospital", "drug")):
        return _SECTOR_VALUATION_BENCHMARKS["PHARMA"]
    if any(k in sec_l for k in ("chemical", "fertilizer", "agrochem")):
        return _SECTOR_VALUATION_BENCHMARKS["CHEMICALS"]
    if any(k in sec_l for k in ("auto", "vehicle", "tyre", "ancillar")):
        return _SECTOR_VALUATION_BENCHMARKS["AUTO"]
    if any(k in sec_l for k in ("telecom", "communication", "media")):
        return _SECTOR_VALUATION_BENCHMARKS["TELECOM"]
    if any(k in sec_l for k in ("infra", "construction", "logistics", "port", "cement", "realty", "real estate", "packaging")):
        return _SECTOR_VALUATION_BENCHMARKS["INFRA"]
    if any(k in sec_l for k in ("energy", "oil", "gas", "petrol", "power")):
        return _SECTOR_VALUATION_BENCHMARKS["ENERGY"]
    if any(k in sec_l for k in ("metal", "mining", "steel", "aluminium")):
        return _SECTOR_VALUATION_BENCHMARKS["METALS"]
    return _SECTOR_VALUATION_BENCHMARKS["DEFAULT"]


def _num(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Safely converts any input into a float or returns default."""
    if val is None or isinstance(val, bool):
        return default
    try:
        f = float(str(val).replace(",", "").strip())
        return f if math.isfinite(f) else default
    except (ValueError, TypeError):
        return default


class ForensicFinancialEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.fund_engine = FundamentalAnalysisEngine(cache_manager=self.cache_manager)
        self.local_parser = LocalFinancialsParser()

    def analyze_company(
        self,
        symbol: str,
        price_override: Optional[float] = None,
        financial_statement_override: Optional[Dict[str, Any]] = None,
        sector_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Runs comprehensive forensic audit on the company's financial statements,
        computes normalized sustainable earnings, evaluates cash conversion,
        uncovers red flags, and generates a deterministic investment recommendation.
        """
        symbol_clean = symbol.upper().strip()

        # 1. Fetch market fundamentals (P/E, Market Cap, Debt, Cash, etc.)
        fund_data = self.fund_engine.get_fundamental_metrics(symbol_clean)

        # 2. Extract or construct financial statements
        stmts = financial_statement_override or self._extract_statement_data(symbol_clean, fund_data)

        has_statements = bool(
            stmts.get("statements_available")
            or (_num(stmts.get("reported_pat"), 0.0) != 0.0)
            or (_num(stmts.get("revenue"), 0.0) != 0.0)
        )
        sector_name = sector_override or stmts.get("sector") or fund_data.get("sector", "")
        is_bfsi = _is_bfsi_sector(sector_name, symbol_clean)

        market_price = _num(price_override)
        if market_price is None or market_price <= 0:
            market_price = self._get_current_price(symbol_clean, fund_data)

        # Governance & Peer Benchmarking (always grounded in real telemetry)
        gov = self._audit_governance_telemetry(symbol_clean, fund_data, stmts=stmts)
        peer_engine = PeerBenchmarkEngine()
        peer_benchmarks = peer_engine.compute_peer_benchmarks(symbol_clean, sector_name, self.fund_engine)
        freshness = stmts.get("filing_freshness") or compute_filing_freshness(stmts)

        if not has_statements:
            return {
                "symbol": symbol_clean,
                "company_name": stmts.get("company_name") or symbol_clean,
                "sector": sector_name or "N/A",
                "market_price": market_price,
                "verdict": "UNAUDITED",
                "verdict_badge": "⚪ UNAUDITED",
                "confidence_score": 0,
                "fair_value": None,
                "margin_of_safety_pct": None,
                "piotroski_f_score": None,
                "piotroski_rating": "UNAUDITED",
                "piotroski_f_score_details": {"score": None, "rating": "UNAUDITED", "evaluable_criteria": 0, "missing_criteria": [], "points": []},
                "beneish_m_score": {"m_score": None, "status": "UNAUDITED", "components": {}},
                "bfsi_health": None,
                "filing_freshness": freshness,
                "debtor_days": None,
                "earnings_quality": {
                    "reported_pat": None,
                    "adjusted_pat": None,
                    "sustainable_pat": None,
                    "revenue": None,
                    "exceptional_items": None,
                    "other_income": None,
                    "minority_deduction": None,
                    "distortion_pct": None,
                    "quality_grade": "UNAUDITED",
                },
                "cash_conversion": {
                    "cfo": None,
                    "capex": None,
                    "fcf": None,
                    "cfo_to_pat_ratio": None,
                    "fcf_to_pat_ratio": None,
                    "receivables_growth_pct": None,
                    "revenue_growth_pct": None,
                    "working_capital_divergence": False,
                    "conversion_status": "UNAUDITED",
                },
                "subsidiary_attribution": {
                    "minority_interest_amount": None,
                    "minority_share_pct": None,
                    "parent_attributable_pct": None,
                    "subsidiary_leakage_flag": False,
                },
                "solvency_health": {
                    "total_debt": _num(fund_data.get("total_debt")),
                    "total_cash": _num(fund_data.get("total_cash")),
                    "net_debt": _num(fund_data.get("net_debt")),
                    "net_cash_positive": None,
                    "debt_to_equity": _num(fund_data.get("debt_to_equity"), "N/A"),
                    "current_ratio": _num(fund_data.get("current_ratio"), "N/A"),
                    "estimated_interest_coverage": None,
                    "solvency_rating": "UNAUDITED",
                },
                "valuation_metrics": {
                    "intrinsic_fair_value": None,
                    "margin_of_safety_pct": None,
                    "applied_haircut_factor": None,
                    "sustainable_earnings_ratio": None,
                    "valuation_verdict": "UNAUDITED",
                    "valuation_method": "UNAUDITED",
                    "method_breakdown": {},
                },
                "governance_telemetry": gov,
                "peer_benchmarks": peer_benchmarks,
                "red_flags": list(gov.get("governance_flags", [])),
                "positive_catalysts": [],
                "investment_thesis": "Audited financial statements unavailable from data feed.",
                "statement_source": "Unavailable",
                "timestamp": fund_data.get("fetched_at", ""),
            }

        # 3. Earnings Quality Normalization
        eq = self._audit_earnings_quality(stmts, fund_data)

        # 4. Cash Flow & Working Capital Audit
        cf = self._audit_cash_conversion(stmts, fund_data)

        # 5. Subsidiary & Minority Interest Attribution
        sub = self._audit_subsidiary_attribution(stmts, fund_data)

        # 6. Solvency & Balance Sheet Health (BFSI deposits/borrowings handled appropriately)
        solv = self._audit_solvency_and_debt(stmts, fund_data, is_bfsi=is_bfsi)
        bfsi_health = self._audit_bfsi_health(stmts, fund_data, market_price) if is_bfsi else None

        # 7. Sector-Specific Non-Circular Intrinsic Valuation
        val = self._calculate_sustainable_valuation(
            eq, cf, solv, fund_data, market_price, stmts=stmts, sector=sector_name, bfsi_health=bfsi_health
        )

        # 8. Authentic Multi-Period Piotroski F-Score, Beneish M-Score & Working Capital Efficiency
        f_score = self._calculate_piotroski_f_score(stmts, fund_data, eq, cf, solv)
        beneish = self._calculate_beneish_m_score(stmts, cf, is_bfsi=is_bfsi)
        wc = self._calculate_working_capital_metrics(stmts)

        # 9. Forensic Red Flags & Positive Catalysts
        red_flags, catalysts = self._compile_forensic_signals(
            eq, cf, sub, solv, val, gov, peer_benchmarks, f_score, wc,
            is_bfsi=is_bfsi, bfsi_health=bfsi_health, beneish=beneish, filing_freshness=freshness,
        )

        # 10. Deterministic Investment Recommendation Verdict
        rec = self._synthesize_recommendation(
            eq, cf, solv, val, red_flags, catalysts, market_price, gov, f_score,
            is_bfsi=is_bfsi, bfsi_health=bfsi_health, beneish=beneish,
        )

        return {
            "symbol": symbol_clean,
            "company_name": stmts.get("company_name", symbol_clean),
            "sector": sector_name or "N/A",
            "market_price": market_price,
            "verdict": rec["verdict"],
            "verdict_badge": rec["verdict_badge"],
            "confidence_score": rec["confidence_score"],
            "fair_value": val["intrinsic_fair_value"],
            "margin_of_safety_pct": val["margin_of_safety_pct"],
            "piotroski_f_score": f_score["score"],
            "piotroski_rating": f_score["rating"],
            "piotroski_f_score_details": f_score,
            "beneish_m_score": beneish,
            "bfsi_health": bfsi_health,
            "filing_freshness": freshness,
            "debtor_days": wc["debtor_days"],
            "earnings_quality": eq,
            "cash_conversion": cf,
            "subsidiary_attribution": sub,
            "solvency_health": solv,
            "valuation_metrics": val,
            "governance_telemetry": gov,
            "peer_benchmarks": peer_benchmarks,
            "red_flags": red_flags,
            "positive_catalysts": catalysts,
            "investment_thesis": rec["investment_thesis"],
            "statement_source": stmts.get("source", "Market Feed & Filings"),
            "timestamp": fund_data.get("fetched_at", "")
        }

    def _get_current_price(self, symbol: str, fund_data: Dict[str, Any]) -> float:
        """Looks up the most current price from SQLite quotes or fundamentals."""
        try:
            with self.cache_manager._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT ltp FROM quotes WHERE symbol = ?", (symbol,))
                row = cur.fetchone()
                if row and row[0] and float(row[0]) > 0:
                    return float(row[0])

                # Fallback to recent candle
                cur.execute("SELECT close FROM historical_candles WHERE symbol = ? ORDER BY date DESC LIMIT 1", (symbol,))
                c_row = cur.fetchone()
                if c_row and c_row[0] and float(c_row[0]) > 0:
                    return float(c_row[0])
        except Exception:
            pass

        # Estimate from market cap and shares if available
        pe = _num(fund_data.get("pe_ratio"))
        mcap = _num(fund_data.get("market_cap"))
        if pe and pe > 0:
            return round(pe * 10.0, 2)  # Normalized proxy when no ticker quote is available
        return 100.0

    def _extract_statement_data(self, symbol: str, fund_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gathers statement items from local Indian financials cache (Screener/BSE/NSE feed)
        or falls back to yfinance and stored telemetry.
        Provides robust defaults if certain line items are missing.
        """
        # 1. Check local Indian statements feed first (offline resilience)
        local_stmt = self.local_parser.load_local_statement(symbol)
        if local_stmt:
            local_stmt["statements_available"] = True
            return local_stmt

        data: Dict[str, Any] = {
            "source": "Unavailable",
            "statements_available": False,
            "revenue": 0.0,
            "reported_pat": 0.0,
            "other_income": 0.0,
            "exceptional_items": 0.0,
            "cfo": 0.0,
            "capex": 0.0,
            "minority_interest": 0.0,
            "trade_receivables": 0.0,
            "receivables_prior": 0.0,
            "revenue_prior": 0.0,
            "total_debt": _num(fund_data.get("total_debt"), 0.0),
            "total_cash": _num(fund_data.get("total_cash"), 0.0),
            "free_cashflow": _num(fund_data.get("free_cashflow"), 0.0),
        }

        # Try online/cached yfinance financials if accessible
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}.NS")
            fin = getattr(ticker, "financials", None)
            cf = getattr(ticker, "cashflow", None)
            bs = getattr(ticker, "balance_sheet", None)

            if fin is not None and not fin.empty:
                data["source"] = "Audited Statements"
                latest_col = fin.columns[0]
                prev_col = fin.columns[1] if len(fin.columns) > 1 else None
                data["period_end_date"] = str(latest_col)[:10]

                def get_fin_cr(items, col=latest_col):
                    for item in (items if isinstance(items, (list, tuple)) else (items,)):
                        if item in fin.index:
                            v = _num(fin.loc[item, col])
                            if v is not None:
                                return round(v / 1e7, 2)
                    return None

                data["revenue"] = get_fin_cr(["Total Revenue", "Operating Revenue"]) or 0.0
                data["reported_pat"] = get_fin_cr(["Net Income", "Net Income Common Stockholders"]) or 0.0
                data["other_income"] = get_fin_cr(["Other Income Expense", "Non Operating Income Net Other"]) or 0.0
                data["exceptional_items"] = get_fin_cr(["Special Income Charges", "Other Special Charges"]) or 0.0
                data["minority_interest"] = abs(get_fin_cr(["Minority Interest", "Net Income Continuous Operations to Noncontrolling Interests"]) or 0.0)
                data["gross_profit"] = get_fin_cr(["Gross Profit"])
                data["ebitda"] = get_fin_cr(["EBITDA", "Normalized EBITDA"])
                data["depreciation"] = get_fin_cr(["Reconciled Depreciation", "Depreciation And Amortization"])
                data["sga_expense"] = get_fin_cr(["Selling General And Administration", "General And Administrative Expense"])

                if prev_col is not None:
                    data["revenue_prior"] = get_fin_cr(["Total Revenue", "Operating Revenue"], prev_col) or 0.0
                    data["reported_pat_prior"] = get_fin_cr(["Net Income", "Net Income Common Stockholders"], prev_col)
                    data["gross_profit_prior"] = get_fin_cr(["Gross Profit"], prev_col)
                    data["ebitda_prior"] = get_fin_cr(["EBITDA", "Normalized EBITDA"], prev_col)
                    data["depreciation_prior"] = get_fin_cr(["Reconciled Depreciation", "Depreciation And Amortization"], prev_col)
                    data["sga_expense_prior"] = get_fin_cr(["Selling General And Administration", "General And Administrative Expense"], prev_col)
                if data["revenue"] != 0.0 or data["reported_pat"] != 0.0:
                    data["statements_available"] = True

            if cf is not None and not cf.empty:
                latest_cf = cf.columns[0]
                def get_cf_cr(items):
                    for item in (items if isinstance(items, (list, tuple)) else (items,)):
                        if item in cf.index:
                            v = _num(cf.loc[item, latest_cf])
                            if v is not None:
                                return round(v / 1e7, 2)
                    return 0.0

                data["cfo"] = get_cf_cr(["Operating Cash Flow", "Cash Flowsfromusedin Operating Activities Direct"])
                data["capex"] = abs(get_cf_cr(["Capital Expenditure", "Purchase Of PPE"]))
                if data["cfo"]:
                    data["free_cashflow"] = round(data["cfo"] - data["capex"], 2)

            if bs is not None and not bs.empty:
                latest_bs = bs.columns[0]
                prev_bs = bs.columns[1] if len(bs.columns) > 1 else None
                def get_bs_cr(items, col=latest_bs):
                    for item in (items if isinstance(items, (list, tuple)) else (items,)):
                        if item in bs.index:
                            v = _num(bs.loc[item, col])
                            if v is not None:
                                return round(v / 1e7, 2)
                    return None

                data["trade_receivables"] = get_bs_cr(["Receivables", "Accounts Receivable"]) or 0.0
                data["total_assets"] = get_bs_cr(["Total Assets"])
                data["current_assets"] = get_bs_cr(["Current Assets", "Total Current Assets"])
                data["current_liabilities"] = get_bs_cr(["Current Liabilities", "Total Current Liabilities"])
                data["total_debt"] = get_bs_cr(["Total Debt"]) if get_bs_cr(["Total Debt"]) is not None else data.get("total_debt", 0.0)
                data["long_term_debt"] = get_bs_cr(["Long Term Debt"])
                bs_cash = get_bs_cr(["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents"])
                fd_cash_raw = _num(data.get("total_cash"), 0.0) or 0.0
                fd_cash_cr = round(fd_cash_raw / 1e7, 2) if fd_cash_raw > 1e6 else fd_cash_raw
                if bs_cash is not None:
                    data["total_cash"] = max(bs_cash, fd_cash_cr)
                else:
                    data["total_cash"] = fd_cash_cr
                data["ppe"] = get_bs_cr(["Net PPE", "Properties"])
                data["shares_outstanding_cr"] = get_bs_cr(["Ordinary Shares Number", "Share Issued"])
                if data["current_assets"] and data["current_liabilities"] and data["current_liabilities"] > 0:
                    data["current_ratio"] = round(data["current_assets"] / data["current_liabilities"], 4)

                if prev_bs is not None:
                    data["receivables_prior"] = get_bs_cr(["Receivables", "Accounts Receivable"], prev_bs) or 0.0
                    data["total_assets_prior"] = get_bs_cr(["Total Assets"], prev_bs)
                    data["current_assets_prior"] = get_bs_cr(["Current Assets", "Total Current Assets"], prev_bs)
                    data["current_liabilities_prior"] = get_bs_cr(["Current Liabilities", "Total Current Liabilities"], prev_bs)
                    data["total_debt_prior"] = get_bs_cr(["Total Debt"], prev_bs)
                    data["long_term_debt_prior"] = get_bs_cr(["Long Term Debt"], prev_bs)
                    data["ppe_prior"] = get_bs_cr(["Net PPE", "Properties"], prev_bs)
                    data["shares_prior_cr"] = get_bs_cr(["Ordinary Shares Number", "Share Issued"], prev_bs)
                    if data["current_assets_prior"] and data["current_liabilities_prior"] and data["current_liabilities_prior"] > 0:
                        data["current_ratio_prior"] = round(data["current_assets_prior"] / data["current_liabilities_prior"], 4)

            if data.get("period_end_date"):
                data["filing_freshness"] = compute_filing_freshness(data)

        except Exception:
            pass

        return data

    def _audit_earnings_quality(self, stmts: Dict[str, Any], fund_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes earnings by stripping exceptional items, non-operating income,
        and minority interest leakage.
        Calculates:
          - Reported PAT
          - Adjusted PAT (Reported PAT - Exceptional Income + Exceptional Expense)
          - Sustainable PAT (Core operating earnings attributable to parent shareholders)
          - Distortion Percentage
        """
        reported_pat = _num(stmts.get("reported_pat"), 0.0)
        other_income = _num(stmts.get("other_income"), 0.0)
        exceptional_items = _num(stmts.get("exceptional_items"), 0.0)
        minority_interest = abs(_num(stmts.get("minority_interest"), 0.0))

        # Adjusted PAT excludes one-off extraordinary items
        adjusted_pat = reported_pat - exceptional_items

        # Sustainable PAT strips excessive non-operating windfalls and deducts minority share
        # Core operating filter: allow up to 10% of profit as recurring treasury/other income, hair-cut excess
        excess_other_income = max(0.0, other_income - (reported_pat * 0.10)) if reported_pat > 0 else 0.0

        sustainable_pat = adjusted_pat - excess_other_income - minority_interest
        # Floor sustainable PAT appropriately
        if reported_pat > 0 and sustainable_pat < 0:
            sustainable_pat = 0.0

        # Calculate distortion %
        if reported_pat > 0:
            distortion_pct = round(((reported_pat - sustainable_pat) / reported_pat) * 100.0, 2)
        else:
            distortion_pct = 0.0

        quality_grade = "HIGH_QUALITY"
        if distortion_pct > 35.0:
            quality_grade = "SEVERELY_DISTORTED"
        elif distortion_pct > 18.0:
            quality_grade = "MODERATELY_DISTORTED"

        return {
            "reported_pat": round(reported_pat, 2),
            "adjusted_pat": round(adjusted_pat, 2),
            "sustainable_pat": round(sustainable_pat, 2),
            "revenue": round(_num(stmts.get("revenue"), 0.0), 2),
            "exceptional_items": round(exceptional_items, 2),
            "other_income": round(other_income, 2),
            "minority_deduction": round(minority_interest, 2),
            "distortion_pct": distortion_pct,
            "quality_grade": quality_grade
        }

    def _audit_cash_conversion(self, stmts: Dict[str, Any], fund_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates CFO/PAT, FCF, and working capital expansion.
        Detects paper-profit traps where profits rise while operating cash dwindles.
        """
        cfo = _num(stmts.get("cfo"), 0.0)
        reported_pat = _num(stmts.get("reported_pat"), 1.0)
        capex = _num(stmts.get("capex"), 0.0)
        fcf = stmts.get("free_cashflow", cfo - capex)

        cfo_to_pat = round(cfo / reported_pat, 2) if reported_pat > 0 else 0.0
        fcf_to_pat = round(fcf / reported_pat, 2) if reported_pat > 0 else 0.0

        # Working Capital Drag Analysis
        rec_now = _num(stmts.get("trade_receivables"), 0.0)
        rec_prev = _num(stmts.get("receivables_prior"), 0.0)
        rev_now = _num(stmts.get("revenue"), 1.0)
        rev_prev = _num(stmts.get("revenue_prior"), 1.0)

        receivables_growth_pct = 0.0
        revenue_growth_pct = 0.0
        wc_divergence = False

        if rec_prev > 0 and rec_now > 0:
            receivables_growth_pct = round(((rec_now - rec_prev) / rec_prev) * 100.0, 2)
        if rev_prev > 0 and rev_now > 0:
            revenue_growth_pct = round(((rev_now - rev_prev) / rev_prev) * 100.0, 2)

        # Flag if receivables ballooned > 15% faster than revenue
        if receivables_growth_pct > (revenue_growth_pct + 15.0) and receivables_growth_pct > 15.0:
            wc_divergence = True

        status = "HEALTHY_CASH_FLOW"
        if cfo <= 0 and reported_pat > 0:
            status = "NEGATIVE_OPERATING_CASH_FLOW"
        elif cfo_to_pat < 0.65:
            status = "WEAK_CASH_CONVERSION"
        elif cfo_to_pat >= 0.85:
            status = "EXCELLENT_CASH_GENERATOR"

        return {
            "cfo": round(cfo, 2),
            "capex": round(capex, 2),
            "fcf": round(fcf, 2),
            "cfo_to_pat_ratio": cfo_to_pat,
            "fcf_to_pat_ratio": fcf_to_pat,
            "receivables_growth_pct": receivables_growth_pct,
            "revenue_growth_pct": revenue_growth_pct,
            "working_capital_divergence": wc_divergence,
            "conversion_status": status
        }

    def _audit_subsidiary_attribution(self, stmts: Dict[str, Any], fund_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates how much consolidated PAT is leaked to minority partners.
        """
        reported_pat = _num(stmts.get("reported_pat"), 1.0)
        minority = abs(_num(stmts.get("minority_interest"), 0.0))

        minority_share_pct = round((minority / reported_pat) * 100.0, 2) if reported_pat > 0 else 0.0
        parent_attributable_pct = max(0.0, 100.0 - minority_share_pct)

        subsidiary_leakage_flag = minority_share_pct >= 25.0

        return {
            "minority_interest_amount": round(minority, 2),
            "minority_share_pct": minority_share_pct,
            "parent_attributable_pct": parent_attributable_pct,
            "subsidiary_leakage_flag": subsidiary_leakage_flag
        }

    def _audit_solvency_and_debt(self, stmts: Dict[str, Any], fund_data: Dict[str, Any], is_bfsi: bool = False) -> Dict[str, Any]:
        """
        Analyzes leverage, net cash status, and current debt service ability.
        Exempts BFSI (banks/NBFCs) from industrial debt/leverage classifications.
        """
        raw_fd_debt = _num(fund_data.get("total_debt"), 0.0)
        raw_fd_cash = _num(fund_data.get("total_cash"), 0.0)
        # Convert raw INR fund_data fallback (>1e6) into Cr when stmts didn't supply borrowings
        if raw_fd_debt > 1e6:
            raw_fd_debt = round(raw_fd_debt / 1e7, 2)
        if raw_fd_cash > 1e6:
            raw_fd_cash = round(raw_fd_cash / 1e7, 2)

        total_debt = _num(stmts.get("total_debt"))
        if total_debt is None:
            total_debt = raw_fd_debt
        total_cash = _num(stmts.get("total_cash"))
        if total_cash is None:
            total_cash = raw_fd_cash

        net_debt = round(total_debt - total_cash, 2)
        de_ratio = _num(fund_data.get("debt_to_equity"))
        current_ratio = _num(stmts.get("current_ratio"))
        if current_ratio is None:
            current_ratio = _num(fund_data.get("current_ratio"))

        reported_pat = _num(stmts.get("reported_pat"), 10.0)
        estimated_ebit = reported_pat * 1.35
        interest_cost = total_debt * 0.09
        interest_coverage = round(estimated_ebit / interest_cost, 2) if interest_cost > 0 else 99.0

        is_debt_free = net_debt <= 0
        if is_bfsi:
            solvency_rating = "BFSI_REGULATED"
        else:
            solvency_rating = "PRISTINE"
            de_norm = (de_ratio / 100.0) if (de_ratio is not None and de_ratio > 5.0) else de_ratio
            if total_debt > 0 and de_norm is not None and de_norm > 1.5 and interest_coverage < 4.0:
                solvency_rating = "OVER_LEVERAGED"
            elif interest_coverage < 2.5 and not is_debt_free:
                solvency_rating = "DEBT_SERVICE_STRESS"
            elif is_debt_free or (de_norm is not None and de_norm < 0.30):
                solvency_rating = "PRISTINE_OR_NET_CASH"

        return {
            "total_debt": total_debt,
            "total_cash": total_cash,
            "net_debt": net_debt,
            "net_cash_positive": is_debt_free,
            "debt_to_equity": de_ratio if de_ratio is not None else "N/A",
            "current_ratio": current_ratio if current_ratio is not None else "N/A",
            "estimated_interest_coverage": interest_coverage,
            "solvency_rating": solvency_rating
        }

    def _audit_bfsi_health(
        self,
        stmts: Dict[str, Any],
        fund_data: Dict[str, Any],
        market_price: float,
    ) -> Dict[str, Any]:
        """
        Dedicated banking & NBFC health scorecard evaluating RoA, RoE, NIM, GNPA/NNPA,
        CASA, CRAR, and P/B valuation.
        """
        pat = _num(stmts.get("reported_pat"))
        assets = _num(stmts.get("total_assets"))
        roe_pct = _num(stmts.get("roe_pct")) if _num(stmts.get("roe_pct")) is not None else _num(fund_data.get("roe_pct"))
        roa_pct = _num(stmts.get("roa_pct")) if _num(stmts.get("roa_pct")) is not None else _num(fund_data.get("roa_pct"))
        if roa_pct is None and pat is not None and assets and assets > 0:
            roa_pct = round((pat / assets) * 100.0, 2)

        nim_pct = _num(stmts.get("nim_pct"))
        gnpa_pct = _num(stmts.get("gnpa_pct"))
        nnpa_pct = _num(stmts.get("nnpa_pct"))
        casa_pct = _num(stmts.get("casa_pct"))
        crar_pct = _num(stmts.get("crar_pct"))
        pb_ratio = _num(stmts.get("pb_ratio")) if _num(stmts.get("pb_ratio")) is not None else _num(fund_data.get("pb_ratio"))
        bvps = _num(stmts.get("book_value_per_share")) or _num(fund_data.get("book_value"))
        if bvps is None and pb_ratio and pb_ratio > 0 and market_price > 0:
            bvps = round(market_price / pb_ratio, 2)
        if pb_ratio is None and bvps and bvps > 0 and market_price > 0:
            pb_ratio = round(market_price / bvps, 2)

        bfsi_flags: List[str] = []
        bfsi_strengths: List[str] = []

        if gnpa_pct is not None:
            if gnpa_pct > 5.0:
                bfsi_flags.append(f"[BFSI Asset Quality] Elevated GNPA at {gnpa_pct:.2f}% (>5% threshold).")
            elif gnpa_pct <= 2.0:
                bfsi_strengths.append(f"Clean BFSI asset quality with GNPA at {gnpa_pct:.2f}%.")
        if nnpa_pct is not None and nnpa_pct > 2.0:
            bfsi_flags.append(f"[BFSI Asset Quality] Elevated Net NPA at {nnpa_pct:.2f}% (>2% threshold).")
        if crar_pct is not None:
            if crar_pct < 12.0:
                bfsi_flags.append(f"[BFSI Capital] Tight capital adequacy CRAR at {crar_pct:.1f}%.")
            elif crar_pct >= 16.0:
                bfsi_strengths.append(f"Strong Tier capital buffer with CRAR at {crar_pct:.1f}%.")
        if roa_pct is not None:
            if roa_pct < 0.7:
                bfsi_flags.append(f"[BFSI Profitability] Weak Return on Assets at {roa_pct:.2f}%.")
            elif roa_pct >= 1.5:
                bfsi_strengths.append(f"Superior banking Return on Assets (RoA {roa_pct:.2f}%).")
        if roe_pct is not None:
            if roe_pct < 10.0:
                bfsi_flags.append(f"[BFSI Profitability] Sub-hurdle RoE at {roe_pct:.1f}%.")
            elif roe_pct >= 15.0:
                bfsi_strengths.append(f"Healthy BFSI Return on Equity (RoE {roe_pct:.1f}%).")
        if casa_pct is not None and casa_pct >= 42.0:
            bfsi_strengths.append(f"Strong low-cost CASA deposit franchise ({casa_pct:.1f}%).")

        has_any = any(v is not None for v in (roe_pct, roa_pct, gnpa_pct, crar_pct, bvps, pb_ratio))
        if not has_any:
            grade = "UNAUDITED"
        elif (
            (gnpa_pct is not None and gnpa_pct > 5.0)
            or (nnpa_pct is not None and nnpa_pct > 2.0)
            or (crar_pct is not None and crar_pct < 12.0)
            or (roa_pct is not None and roa_pct < 0.6)
            or len(bfsi_flags) >= 2
        ):
            grade = "STRESSED_BFSI"
        elif len(bfsi_flags) >= 1:
            grade = "WATCH_ASSET_QUALITY"
        elif len(bfsi_strengths) >= 2 and (roa_pct is None or roa_pct >= 1.5):
            grade = "FORTRESS_BANK"
        else:
            grade = "HEALTHY_BFSI"

        return {
            "bfsi_grade": grade,
            "roe_pct": roe_pct,
            "roa_pct": roa_pct,
            "nim_pct": nim_pct,
            "gnpa_pct": gnpa_pct,
            "nnpa_pct": nnpa_pct,
            "casa_pct": casa_pct,
            "crar_pct": crar_pct,
            "pb_ratio": pb_ratio,
            "book_value_per_share": bvps,
            "bfsi_flags": bfsi_flags,
            "bfsi_strengths": bfsi_strengths,
        }

    def _calculate_sustainable_valuation(
        self,
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        solv: Dict[str, Any],
        fund_data: Dict[str, Any],
        market_price: float,
        stmts: Optional[Dict[str, Any]] = None,
        sector: str = "",
        bfsi_health: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Non-circular sector-specific intrinsic valuation:
          - BFSI: Justified P/B Gordon excess-return model on Book Value Per Share
          - Non-BFSI (when shares_cr available): Multi-method blend of EPV + 2-Stage FCF DCF + EV/EBITDA (independent of market_price)
          - Fallback (minimal statements lacking share count/BVPS): Earnings quality / net-debt adjusted proxy
        """
        stmts = stmts or {}
        reported_pat = _num(eq.get("reported_pat"), 0.0)
        sustainable_pat = _num(eq.get("sustainable_pat"), 0.0)
        sustainable_ratio = round((sustainable_pat / reported_pat), 2) if reported_pat > 0 else 1.0
        sym_for_bfsi = str(stmts.get("symbol") or fund_data.get("symbol") or "")
        is_bfsi = _is_bfsi_sector(sector, sym_for_bfsi) or (bfsi_health is not None)

        # Quality haircut factor (non-price operational discipline)
        haircut = 1.0
        if (eq.get("distortion_pct") or 0.0) > 30.0:
            haircut *= 0.80
        elif (eq.get("distortion_pct") or 0.0) > 15.0:
            haircut *= 0.90
        if not is_bfsi:
            cfo_r = _num(cf.get("cfo_to_pat_ratio"), 1.0)
            if cfo_r < 0.60:
                haircut *= 0.80
            elif cfo_r >= 0.90:
                haircut *= 1.05
            if solv.get("solvency_rating") == "OVER_LEVERAGED":
                haircut *= 0.80

        method_breakdown: Dict[str, Any] = {}
        valuation_method = "EARNINGS_QUALITY_PROXY"
        intrinsic_fair_value: Optional[float] = None

        # --- Case A: BFSI Justified P/B (2-Stage Excess Return & Earnings Power Blend) ---
        if is_bfsi:
            bvps = (bfsi_health or {}).get("book_value_per_share") or _num(stmts.get("book_value_per_share")) or _num(fund_data.get("book_value"))
            if bvps is not None and bvps > 0:
                roe_pct = (bfsi_health or {}).get("roe_pct") or _num(stmts.get("roe_pct")) or _num(fund_data.get("roe_pct"))
                roe = (roe_pct if roe_pct is not None else 14.0) / 100.0
                eg_pct = _num(fund_data.get("earnings_growth_pct"))
                rg_pct = _num(fund_data.get("revenue_growth_pct")) or _num(cf.get("revenue_growth_pct"))
                fd_pe_bfsi = _num(fund_data.get("pe_ratio"))
                fd_pb_bfsi = _num(fund_data.get("pb_ratio")) or (bfsi_health or {}).get("pb_ratio")

                # Mean-revert cyclical peak ROE (>18%) over a full credit cycle so temporary commodity/gold windfalls don't double P/B
                sust_roe = min(0.22, roe if roe <= 0.18 else (0.18 + (roe - 0.18) * 0.35))
                eff_roe = max(sust_roe, 0.145 if (eg_pct is not None and eg_pct >= 18.0 and roe >= 0.10) else sust_roe)

                coe = 0.118
                g_term = min(0.072, max(0.045, eff_roe * 0.45))
                terminal_pb = max(0.5, min(3.4, (eff_roe - g_term) / max(0.03, coe - g_term)))

                # 5-year franchise compounding before terminal stage
                g_5y = min(0.18, max(eff_roe * 0.70, ((eg_pct or rg_pct or 12.0) / 100.0) * 0.55))
                compound_mult = max(1.0, min(1.32, ((1.0 + g_5y) / (1.0 + coe)) ** 5)) if eff_roe >= 0.11 else 1.0
                justified_pb = terminal_pb * compound_mult

                gnpa = (bfsi_health or {}).get("gnpa_pct")
                roa = (bfsi_health or {}).get("roa_pct")
                casa = (bfsi_health or {}).get("casa_pct")
                if gnpa is not None and gnpa > 5.0:
                    justified_pb *= 0.65
                elif gnpa is not None and gnpa > 3.5:
                    justified_pb *= 0.85
                if roa is not None and roa >= 1.7:
                    justified_pb *= 1.08
                elif roa is not None and roa < 0.8:
                    justified_pb *= 0.75
                if casa is not None and casa >= 45.0:
                    justified_pb *= 1.05

                # Blend with BFSI Earnings Power when TTM EPS is available and asset quality is healthy
                eps_bfsi = _num(fund_data.get("eps"))
                if eps_bfsi and eps_bfsi > 0 and (gnpa is None or gnpa <= 3.5):
                    fair_bank_pe = 14.0 + min(6.5, max(0.0, (eff_roe * 100.0 - 11.0) * 0.42 + max(0.0, min(25.0, eg_pct or 0.0)) * 0.12))
                    if fd_pe_bfsi is not None and 0 < fd_pe_bfsi < 15.0 and fair_bank_pe > fd_pe_bfsi * 1.22:
                        fair_bank_pe = min(fd_pe_bfsi * 1.22, (fd_pe_bfsi * 1.15) * 0.65 + fair_bank_pe * 0.35)
                    implied_pb = (eps_bfsi * fair_bank_pe) / bvps
                    if 0.5 <= implied_pb <= 4.5:
                        justified_pb = (justified_pb * 0.55) + (implied_pb * 0.45)

                # Structural P/B discipline: prevent NBFCs/banks priced at low multiples from assuming a +80-100% P/B jump
                if fd_pb_bfsi is not None and fd_pb_bfsi > 0 and justified_pb > fd_pb_bfsi * 1.25:
                    justified_pb = min(fd_pb_bfsi * 1.24, (fd_pb_bfsi * 1.15) * 0.65 + justified_pb * 0.35)

                justified_pb = round(max(0.4, min(4.2, justified_pb)), 2)
                intrinsic_fair_value = round(bvps * justified_pb, 2)
                valuation_method = "BFSI_JUSTIFIED_PB"
                method_breakdown = {"bvps": round(bvps, 2), "justified_pb": justified_pb, "roe_pct": round(roe * 100.0, 2)}

        # --- Case B: Non-BFSI Market-Price-Independent Per-Share Intrinsic Value ---
        if intrinsic_fair_value is None and not is_bfsi:
            shares_cr = _num(stmts.get("shares_outstanding_cr"))
            if not shares_cr:
                raw_sh = _num(stmts.get("shares_outstanding")) or _num(fund_data.get("shares_outstanding"))
                if raw_sh and raw_sh > 0:
                    shares_cr = round(raw_sh / 1e7, 4)
            if not shares_cr:
                mcap = _num(fund_data.get("market_cap"))
                if mcap and mcap > 0 and market_price > 0:
                    shares_cr = round((mcap / market_price) / 1e7, 4)
            if not shares_cr:
                eps_v = _num(fund_data.get("eps"))
                if reported_pat > 0 and eps_v and eps_v > 0:
                    shares_cr = round(reported_pat / eps_v, 4)

            if shares_cr and shares_cr > 0:
                rep_eps = (reported_pat / shares_cr) if reported_pat > 0 else 0.0
                stmt_sust_eps = (sustainable_pat / shares_cr) if sustainable_pat > 0 else 0.0
                fd_eps = _num(fund_data.get("eps"))

                # Reconcile annual statement basis with TTM per-share basis (handles demergers/splits and TTM growth)
                scale_factor = 1.0
                if fd_eps is not None and fd_eps <= 0:
                    # Negative TTM earnings (e.g. post-demerger operating loss): do not project stale positive annual PAT
                    scale_factor = 0.0
                elif fd_eps and fd_eps > 0 and rep_eps > fd_eps * 2.0:
                    scale_factor = fd_eps / rep_eps
                elif fd_eps and fd_eps > 0 and rep_eps > 0 and fd_eps > rep_eps:
                    scale_factor = min(1.25, fd_eps / rep_eps)

                sust_eps = stmt_sust_eps * scale_factor
                if sust_eps <= 0 and fd_eps and fd_eps > 0:
                    sust_eps = fd_eps * min(1.1, max(0.6, sustainable_ratio))

                stmt_ebitda = _num(stmts.get("ebitda"))
                fd_ebitda = _num(fund_data.get("ebitda"))
                if fd_ebitda and fd_ebitda > 1e6:
                    fd_ebitda = round(fd_ebitda / 1e7, 2)
                if 0 < scale_factor < 1.0:
                    eff_ebitda = (stmt_ebitda or fd_ebitda or 0.0) * scale_factor
                elif scale_factor == 0.0:
                    eff_ebitda = fd_ebitda or ((stmt_ebitda or 0.0) * 0.25)
                else:
                    eff_ebitda = max(stmt_ebitda or 0.0, fd_ebitda or 0.0)

                total_cash = _num(solv.get("total_cash"), 0.0) or 0.0
                total_debt = _num(solv.get("total_debt"), 0.0) or 0.0
                net_cash_cr = (total_cash - total_debt) * (scale_factor if 0 < scale_factor < 1.0 else 1.0)
                if net_cash_cr < 0 and eff_ebitda > 0:
                    adj_net_cash_cr = max(net_cash_cr, -1.5 * eff_ebitda)
                else:
                    adj_net_cash_cr = net_cash_cr
                adj_net_cash_ps = adj_net_cash_cr / shares_cr

                rev_g = _num(cf.get("revenue_growth_pct"))
                fd_rg = _num(fund_data.get("revenue_growth_pct"))
                fd_eg = _num(fund_data.get("earnings_growth_pct"))
                pm_pct = _num(fund_data.get("profit_margin_pct"))
                fd_pe = _num(fund_data.get("pe_ratio"))
                fd_ev_ebitda = _num(fund_data.get("ev_to_ebitda"))

                if rev_g is not None and fd_rg is not None and rev_g > 0 and fd_rg > 0:
                    # Blend audited annual revenue growth with TTM/quarterly growth so a single quarter spike doesn't over-inflate
                    top_g = min(45.0, (rev_g * 0.55) + (fd_rg * 0.45))
                else:
                    pos_rgs = [g for g in (rev_g, fd_rg) if g is not None and g > 0]
                    top_g = min(45.0, max(pos_rgs)) if pos_rgs else (rev_g if rev_g is not None else fd_rg)
                if fd_eg is not None:
                    if fd_eg < -15.0:
                        g_pct = max(0.0, (top_g if (top_g is not None and top_g > 0) else 6.0) * 0.35)
                    elif fd_eg > 120.0:
                        # Extreme low-base earnings jump: anchor on top-line revenue growth
                        g_pct = top_g if (top_g is not None and top_g > 0) else 15.0
                    elif fd_eg > 0:
                        cap_eg = min(45.0, fd_eg)
                        base_rg = top_g if (top_g is not None and top_g > 0) else cap_eg
                        g_pct = (base_rg * 0.60) + (cap_eg * 0.40)
                    else:
                        g_pct = top_g if top_g is not None else 10.0
                else:
                    g_pct = top_g if top_g is not None else 10.0
                g_pct = max(0.0, min(45.0, g_pct))

                roe_v = _num(stmts.get("roe_pct")) or _num(fund_data.get("roe_pct")) or 15.0
                sec_l = str(sector or "").lower()
                is_cap_mkt = _is_capital_markets(sector, sym_for_bfsi)
                sec_bench = _get_sector_valuation_benchmark(sector, sym_for_bfsi)
                sec_norm_pe = sec_bench["norm_pe"]
                sec_norm_ev = sec_bench["norm_ev_ebitda"]
                sec_norm_margin = sec_bench["norm_margin_pct"]

                methods: Dict[str, float] = {}
                weights = {"dcf": 0.40, "epv": 0.35, "ev_ebitda": 0.25}

                # 1. Sector-Anchored Growth-Adjusted Earnings Power Value (GARP EPV)
                if sust_eps > 0:
                    # Anchor base P/E on the sector's structural norm, then adjust for growth, ROE, and sector-relative margin
                    fair_pe = (sec_norm_pe * 0.62) + min(20.0, g_pct * 0.50)
                    if roe_v >= 30.0:
                        fair_pe += 6.0
                    elif roe_v >= 22.0:
                        fair_pe += 4.0
                    elif roe_v >= 15.0:
                        fair_pe += 2.0
                    elif roe_v < 9.0:
                        fair_pe -= 3.5

                    # Sector-relative profit margin comparison (e.g. 4% is normal in EMS, while 11% is below norm in IT)
                    if pm_pct is not None and sec_norm_margin > 0:
                        if pm_pct < sec_norm_margin * 0.82:
                            fair_pe -= 3.5
                        elif pm_pct >= sec_norm_margin * 1.25:
                            fair_pe += 2.0

                    if net_cash_cr > 0:
                        fair_pe += 1.5
                    if fd_eg is not None and fd_eg < -20.0:
                        fair_pe = min(fair_pe, sec_norm_pe * 0.72)

                    # Sectorial multiple discipline: when a stock trades at a deep structural discount to its own sector norm P/E,
                    # bound how far theoretical fair_pe can re-rate above its actual market multiple
                    if fd_pe is not None and 0 < fd_pe < sec_norm_pe * 0.85 and fair_pe > fd_pe * 1.22:
                        fair_pe = min(fd_pe * 1.22, (fd_pe * 1.15) * 0.65 + fair_pe * 0.35)

                    fair_pe = max(10.0, min(45.0, fair_pe))
                    epv_ps = max(0.0, sust_eps * fair_pe + adj_net_cash_ps)
                    if epv_ps > 0:
                        methods["epv"] = round(epv_ps, 2)

                # 2. 10-Year 2-Stage Owner-Earnings / Free Cash Flow DCF (Cr)
                raw_fcf = _num(cf.get("fcf"))
                fd_fcf = _num(fund_data.get("free_cashflow"))
                if fd_fcf and abs(fd_fcf) > 1e6:
                    fd_fcf = round(fd_fcf / 1e7, 2)
                if 0 < scale_factor < 1.0:
                    eff_fcf = (raw_fcf or fd_fcf or 0.0) * scale_factor
                elif scale_factor == 0.0:
                    eff_fcf = min(raw_fcf or 0.0, fd_fcf or 0.0)
                else:
                    eff_fcf = max(raw_fcf or 0.0, fd_fcf or 0.0)

                norm_sust_pat = sust_eps * shares_cr
                cfo_now = _num(cf.get("cfo"), 0.0) or 0.0
                if eff_fcf > 0 and norm_sust_pat > 0 and cfo_now > 0:
                    if eff_fcf < norm_sust_pat * 0.75:
                        eff_fcf = round((eff_fcf * 0.35) + ((norm_sust_pat * 0.80) * 0.65), 2)
                    elif eff_fcf > norm_sust_pat * 1.05:
                        # Prevent single-year working-capital inventory release from inflating 10Y perpetuity
                        eff_fcf = round((eff_fcf * 0.35) + (norm_sust_pat * 0.65), 2)

                if eff_fcf is not None and eff_fcf > 0:
                    g_stage1 = min(0.24, max(0.04, (g_pct / 100.0) * 0.78))
                    g_term = 0.055
                    r_wacc = 0.115 if (net_cash_cr >= 0 and roe_v >= 18.0) else (0.12 if net_cash_cr >= 0 else 0.125)
                    if fd_pe is not None and 0 < fd_pe < sec_norm_pe * 0.75:
                        r_wacc = max(r_wacc, 0.132)
                        g_stage1 = min(g_stage1, 0.12)

                    pv_cf = 0.0
                    cf_t = eff_fcf
                    for t in range(1, 6):
                        cf_t = cf_t * (1.0 + g_stage1)
                        pv_cf += cf_t / ((1.0 + r_wacc) ** t)
                    for t in range(6, 11):
                        fade = (t - 5) / 5.0
                        g_t = g_stage1 * (1.0 - fade) + g_term * fade
                        cf_t = cf_t * (1.0 + g_t)
                        pv_cf += cf_t / ((1.0 + r_wacc) ** t)

                    tv = (cf_t * (1.0 + g_term)) / max(0.03, r_wacc - g_term)
                    pv_tv = tv / ((1.0 + r_wacc) ** 10)
                    dcf_ps = max(0.0, (pv_cf + pv_tv + adj_net_cash_cr) / shares_cr)
                    if fd_pe is not None and 0 < fd_pe < sec_norm_pe * 0.80 and "epv" in methods:
                        dcf_ps = min(dcf_ps, methods["epv"] * 1.12)
                    if dcf_ps > 0:
                        methods["dcf"] = round(dcf_ps, 2)

                # 3. Sector-Anchored EV / EBITDA
                if eff_ebitda is not None and eff_ebitda > 0:
                    ev_mult = (sec_norm_ev * 0.78) + min(10.0, max(-3.0, g_pct * 0.30))
                    if roe_v >= 25.0:
                        ev_mult += 3.5
                    elif roe_v >= 16.0:
                        ev_mult += 1.8
                    elif roe_v < 9.0:
                        ev_mult -= 2.0

                    if pm_pct is not None and sec_norm_margin > 0:
                        if pm_pct < sec_norm_margin * 0.82:
                            ev_mult -= 2.5
                        elif pm_pct >= sec_norm_margin * 1.25:
                            ev_mult += 1.5
                    if fd_eg is not None and fd_eg < -20.0:
                        ev_mult = min(ev_mult, sec_norm_ev * 0.70)
                    if fd_ev_ebitda is not None and 0 < fd_ev_ebitda < sec_norm_ev * 0.80 and ev_mult > fd_ev_ebitda * 1.22:
                        ev_mult = min(fd_ev_ebitda * 1.22, (fd_ev_ebitda * 1.15) * 0.65 + ev_mult * 0.35)
                    ev_mult = max(6.5, min(30.0, ev_mult))

                    ev_ps = max(0.0, (eff_ebitda * ev_mult + adj_net_cash_cr) / shares_cr)
                    if ev_ps > 0:
                        methods["ev_ebitda"] = round(ev_ps, 2)

                if methods:
                    tot_w = sum(weights[k] for k in methods)
                    blended = sum(methods[k] * weights[k] for k in methods) / max(tot_w, 1e-6)
                    q_disc = 1.0
                    if (eq.get("distortion_pct") or 0.0) > 30.0:
                        q_disc *= 0.85
                    if (_num(cf.get("cfo_to_pat_ratio"), 1.0)) < 0.60 and not (norm_sust_pat > 0 and (eq.get("distortion_pct") or 0.0) < 10.0 and net_cash_cr >= 0):
                        q_disc *= 0.85
                    intrinsic_fair_value = round(blended * q_disc, 2)
                    valuation_method = "MULTI_METHOD_INTRINSIC"
                    method_breakdown = {**methods, "shares_cr": round(shares_cr, 2), "quality_factor": round(q_disc, 2)}

        # --- Case C: Statement-Only Quality Proxy Fallback (no share count or BVPS supplied) ---
        if intrinsic_fair_value is None:
            intrinsic_fair_value = round(market_price * sustainable_ratio * haircut, 2)
            if intrinsic_fair_value <= 0:
                intrinsic_fair_value = round(market_price * 0.40, 2)
            valuation_method = "EARNINGS_QUALITY_PROXY"

        margin_of_safety_pct = (
            round(((intrinsic_fair_value - market_price) / market_price) * 100.0, 2)
            if market_price > 0 else 0.0
        )

        return {
            "intrinsic_fair_value": intrinsic_fair_value,
            "margin_of_safety_pct": margin_of_safety_pct,
            "applied_haircut_factor": round(haircut, 2),
            "sustainable_earnings_ratio": sustainable_ratio,
            "valuation_verdict": "UNDERVALUED" if margin_of_safety_pct > 15.0 else ("OVERVALUED" if margin_of_safety_pct < -15.0 else "FAIRLY_VALUED"),
            "valuation_method": valuation_method,
            "method_breakdown": method_breakdown,
        }

    def _calculate_piotroski_f_score(
        self,
        stmts: Dict[str, Any],
        fund_data: Dict[str, Any],
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        solv: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Authentic 9-point Piotroski (2000) F-Score using multi-period statements.
        Never awards free points when prior-year or balance-sheet line items are missing;
        tracks `evaluable_criteria` (0-9) and `missing_criteria`.
        """
        score = 0
        evaluable = 0
        points: List[str] = []
        missing_criteria: List[str] = []

        pat = _num(stmts.get("reported_pat"))
        pat_prior = _num(stmts.get("reported_pat_prior"))
        cfo = _num(cf.get("cfo"))
        assets = _num(stmts.get("total_assets"))
        assets_prior = _num(stmts.get("total_assets_prior"))
        rev_now = _num(stmts.get("revenue"))
        rev_prev = _num(stmts.get("revenue_prior"))

        # 1. F_ROA: Positive Net Income / ROA
        if pat is not None:
            evaluable += 1
            if pat > 0:
                score += 1
                points.append("Positive Net Income (+1)")
        else:
            missing_criteria.append("F_ROA")

        # 2. F_CFO: Positive Operating Cash Flow
        if cfo is not None:
            evaluable += 1
            if cfo > 0:
                score += 1
                points.append("Positive Operating Cash Flow (+1)")
        else:
            missing_criteria.append("F_CFO")

        # 3. F_DELTA_ROA: YoY increase in Return on Assets (pat / assets vs pat_prior / assets_prior)
        if pat is not None and pat_prior is not None and assets and assets > 0 and assets_prior and assets_prior > 0:
            evaluable += 1
            roa_now = pat / assets
            roa_prev = pat_prior / assets_prior
            if roa_now > roa_prev:
                score += 1
                points.append(f"Rising ROA {roa_prev*100:.1f}% -> {roa_now*100:.1f}% (+1)")
        else:
            missing_criteria.append("F_DELTA_ROA")

        # 4. F_ACCRUAL: Operating Cash Flow > Net Income
        if cfo is not None and pat is not None and pat > 0:
            evaluable += 1
            if cfo > pat:
                score += 1
                points.append("Superior Cash Accrual Quality CFO > PAT (+1)")
        else:
            missing_criteria.append("F_ACCRUAL")

        # 5. F_DELTA_LEVER: YoY reduction in leverage ratio (lt_debt or total_debt / assets)
        lt_d = _num(stmts.get("long_term_debt"))
        lt_dp = _num(stmts.get("long_term_debt_prior"))
        d_now = lt_d if (lt_d is not None and lt_dp is not None) else _num(stmts.get("total_debt"))
        d_prev = lt_dp if (lt_d is not None and lt_dp is not None) else _num(stmts.get("total_debt_prior"))
        if d_now is not None and d_prev is not None and assets and assets > 0 and assets_prior and assets_prior > 0:
            evaluable += 1
            if (d_now / assets) <= (d_prev / assets_prior):
                score += 1
                points.append("De-leveraging / Stable Debt-to-Assets (+1)")
        else:
            missing_criteria.append("F_DELTA_LEVER")

        # 6. F_DELTA_LIQUID: YoY improvement in Current Ratio
        cr_now = _num(stmts.get("current_ratio"))
        cr_prev = _num(stmts.get("current_ratio_prior"))
        if cr_now is not None and cr_prev is not None:
            evaluable += 1
            if cr_now > cr_prev:
                score += 1
                points.append(f"Improving Liquidity CR {cr_prev:.2f} -> {cr_now:.2f} (+1)")
        else:
            missing_criteria.append("F_DELTA_LIQUID")

        # 7. F_EQ_OFFER: No net equity dilution (shares_outstanding_cr <= shares_prior_cr)
        sh_now = _num(stmts.get("shares_outstanding_cr"))
        sh_prev = _num(stmts.get("shares_prior_cr"))
        if sh_now and sh_now > 0 and sh_prev and sh_prev > 0:
            evaluable += 1
            if sh_now <= sh_prev * 1.005:
                score += 1
                points.append("Zero Equity Dilution / Buybacks (+1)")
        else:
            missing_criteria.append("F_EQ_OFFER")

        # 8. F_DELTA_MARGIN: YoY expansion in Gross Margin (or Operating/EBITDA Margin)
        gm_now = _num(stmts.get("gross_margin_pct"))
        gm_prev = _num(stmts.get("gross_margin_prior_pct"))
        if gm_now is None and gm_prev is None and rev_now and rev_now > 0 and rev_prev and rev_prev > 0:
            gp_now = _num(stmts.get("gross_profit"))
            gp_prev = _num(stmts.get("gross_profit_prior"))
            if gp_now is not None and gp_prev is not None:
                gm_now = (gp_now / rev_now) * 100.0
                gm_prev = (gp_prev / rev_prev) * 100.0
            else:
                eb_now = _num(stmts.get("ebitda"))
                eb_prev = _num(stmts.get("ebitda_prior"))
                if eb_now is not None and eb_prev is not None:
                    gm_now = (eb_now / rev_now) * 100.0
                    gm_prev = (eb_prev / rev_prev) * 100.0
        if gm_now is not None and gm_prev is not None:
            evaluable += 1
            if gm_now > gm_prev:
                score += 1
                points.append(f"Expanding Operating/Gross Margin {gm_prev:.1f}% -> {gm_now:.1f}% (+1)")
        else:
            missing_criteria.append("F_DELTA_MARGIN")

        # 9. F_DELTA_TURN: YoY increase in Asset Turnover (revenue / total_assets)
        if rev_now and rev_now > 0 and rev_prev and rev_prev > 0 and assets and assets > 0 and assets_prior and assets_prior > 0:
            evaluable += 1
            at_now = rev_now / assets
            at_prev = rev_prev / assets_prior
            if at_now > at_prev:
                score += 1
                points.append("Improving Asset Turnover Efficiency (+1)")
        else:
            missing_criteria.append("F_DELTA_TURN")

        if evaluable < 5:
            rating = "INSUFFICIENT_HISTORY"
        else:
            ratio = score / float(evaluable)
            if score >= 7 or ratio >= 0.78:
                rating = "STRONG"
            elif ratio >= 0.45:
                rating = "MODERATE"
            else:
                rating = "WEAK"

        return {
            "score": score,
            "rating": rating,
            "evaluable_criteria": evaluable,
            "missing_criteria": missing_criteria,
            "points": points,
        }

    def _calculate_beneish_m_score(
        self,
        stmts: Dict[str, Any],
        cf: Dict[str, Any],
        is_bfsi: bool = False,
    ) -> Dict[str, Any]:
        """
        Computes Beneish 8-variable M-Score to detect earnings manipulation.
        Not applicable to BFSI institutions. Requires TATA, SGI, and >= 5 real ratios.
        Threshold: M > -1.78 indicates HIGH_MANIPULATION_RISK.
        """
        if is_bfsi:
            return {"m_score": None, "status": "NOT_APPLICABLE_BFSI", "components": {}}

        rev = _num(stmts.get("revenue"))
        rev_p = _num(stmts.get("revenue_prior"))
        rec = _num(stmts.get("trade_receivables"))
        rec_p = _num(stmts.get("receivables_prior"))
        pat = _num(stmts.get("reported_pat"))
        cfo_v = _num(cf.get("cfo"))
        assets = _num(stmts.get("total_assets"))
        assets_p = _num(stmts.get("total_assets_prior"))
        ca = _num(stmts.get("current_assets"))
        ca_p = _num(stmts.get("current_assets_prior"))
        ppe = _num(stmts.get("ppe"))
        ppe_p = _num(stmts.get("ppe_prior"))
        dep = _num(stmts.get("depreciation"))
        dep_p = _num(stmts.get("depreciation_prior"))
        sga = _num(stmts.get("sga_expense"))
        sga_p = _num(stmts.get("sga_expense_prior"))
        debt = _num(stmts.get("long_term_debt")) if _num(stmts.get("long_term_debt")) is not None else _num(stmts.get("total_debt"))
        debt_p = _num(stmts.get("long_term_debt_prior")) if _num(stmts.get("long_term_debt_prior")) is not None else _num(stmts.get("total_debt_prior"))
        cl = _num(stmts.get("current_liabilities"))
        cl_p = _num(stmts.get("current_liabilities_prior"))
        gp = _num(stmts.get("gross_profit"))
        gp_p = _num(stmts.get("gross_profit_prior"))

        comp: Dict[str, float] = {}
        if rev and rev > 0 and rev_p and rev_p > 0:
            comp["SGI"] = rev / rev_p
        if pat is not None and cfo_v is not None and assets and assets > 0:
            comp["TATA"] = (pat - cfo_v) / assets
        if rec is not None and rec >= 0 and rev and rev > 0 and rec_p and rec_p > 0 and rev_p and rev_p > 0:
            comp["DSRI"] = (rec / rev) / (rec_p / rev_p)
        if gp and gp > 0 and gp_p and gp_p > 0 and rev and rev > 0 and rev_p and rev_p > 0:
            comp["GMI"] = (gp_p / rev_p) / (gp / rev)
        if ca is not None and ppe is not None and assets and assets > 0 and ca_p is not None and ppe_p is not None and assets_p and assets_p > 0:
            soft_p = 1.0 - ((ca_p + ppe_p) / assets_p)
            soft_c = 1.0 - ((ca + ppe) / assets)
            if soft_p > 0.001:
                comp["AQI"] = max(0.0, soft_c) / soft_p
        if dep and dep > 0 and ppe is not None and dep_p and dep_p > 0 and ppe_p is not None and (dep + ppe) > 0 and (dep_p + ppe_p) > 0:
            comp["DEPI"] = (dep_p / (dep_p + ppe_p)) / (dep / (dep + ppe))
        if sga and sga > 0 and sga_p and sga_p > 0 and rev and rev > 0 and rev_p and rev_p > 0:
            comp["SGAI"] = (sga / rev) / (sga_p / rev_p)
        if cl is not None and debt is not None and assets and assets > 0 and cl_p is not None and debt_p is not None and assets_p and assets_p > 0:
            lev_p = (cl_p + debt_p) / assets_p
            if lev_p > 0.001:
                comp["LVGI"] = ((cl + debt) / assets) / lev_p

        rounded_comp = {k: round(v, 3) for k, v in comp.items()}
        if "TATA" not in comp or "SGI" not in comp or len(comp) < 5:
            return {"m_score": None, "status": "INSUFFICIENT_DATA", "components": rounded_comp}

        m = (
            -4.84
            + 0.920 * comp.get("DSRI", 1.0)
            + 0.528 * comp.get("GMI", 1.0)
            + 0.404 * comp.get("AQI", 1.0)
            + 0.892 * comp.get("SGI", 1.0)
            + 0.115 * comp.get("DEPI", 1.0)
            - 0.172 * comp.get("SGAI", 1.0)
            + 4.679 * comp.get("TATA", 0.0)
            - 0.327 * comp.get("LVGI", 1.0)
        )
        m_val = round(m, 3)
        if m_val > -1.78:
            status = "HIGH_MANIPULATION_RISK"
        elif m_val >= -2.22:
            status = "BORDERLINE_WATCH"
        else:
            status = "UNLIKELY_MANIPULATOR"

        return {"m_score": m_val, "status": status, "components": rounded_comp}

    def _calculate_working_capital_metrics(self, stmts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates working capital efficiency and Debtor Days (DSO):
          - Debtor Days = (Trade Receivables / Revenue) * 365
        """
        rev = _num(stmts.get("revenue"), 0.0)
        rec = _num(stmts.get("trade_receivables"), 0.0)
        debtor_days = round((rec / rev) * 365.0, 1) if (rev > 0 and rec > 0) else None

        status = "HEALTHY"
        if debtor_days is not None:
            if debtor_days > 120:
                status = "STRETCHED_COLLECTIONS"
            elif debtor_days < 60:
                status = "LEAN_CASH_COLLECTIONS"

        return {
            "debtor_days": debtor_days,
            "collection_status": status
        }

    def _audit_governance_telemetry(
        self,
        symbol: str,
        fund_data: Dict[str, Any],
        stmts: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Evaluates promoter holding & pledge data from local filings first, then yfinance.
        Flags promoter pledging risk, audit risk, and board governance concerns.
        Returns a governance_telemetry dict with deterministic grade and flags.
        Strictly read-only. No order placement.
        """
        governance_flags: List[str] = []
        stmts = stmts or {}
        promoter_holding_pct: Optional[float] = _num(stmts.get("promoter_holding_pct"))
        promoter_pledge_pct: Optional[float] = _num(stmts.get("promoter_pledge_pct"))
        promoter_holding_flag = False
        pledge_risk = "LOW"
        audit_risk_score: Optional[float] = None
        board_risk_score: Optional[float] = None
        compensation_risk_score: Optional[float] = None

        professionally_managed = {
            "HDFCBANK", "ICICIBANK", "LT", "ITC", "AXISBANK", "INFY", "LTM", "LTIM",
            "FEDERALBNK", "IDFCFIRSTB", "RBLBANK", "CDSL", "BSE", "IEX",
        }

        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}.NS")

            # --- Promoter / Insider Holding % (skip network if local filing already supplied it) ---
            if promoter_holding_pct is None:
                try:
                    major_holders = getattr(ticker, "major_holders", None)
                    if major_holders is not None and not major_holders.empty:
                        for idx in range(len(major_holders)):
                            label = str(major_holders.iloc[idx, 1]).lower() if major_holders.shape[1] > 1 else ""
                            value_raw = major_holders.iloc[idx, 0]
                            if "insider" in label or "promoter" in label:
                                pct = _num(value_raw)
                                if pct is not None:
                                    promoter_holding_pct = round(pct * 100.0, 2) if pct <= 1.0 else round(pct, 2)
                                break
                        if promoter_holding_pct is None:
                            pct = _num(major_holders.iloc[0, 0])
                            if pct is not None:
                                promoter_holding_pct = round(pct * 100.0, 2) if pct <= 1.0 else round(pct, 2)
                except Exception:
                    pass

            if (
                promoter_holding_pct is not None
                and promoter_holding_pct > 0.0
                and promoter_holding_pct < 30.0
                and symbol.upper() not in professionally_managed
            ):
                promoter_holding_flag = True
                governance_flags.append(
                    f"Low promoter/insider holding: {promoter_holding_pct:.1f}% (<30% threshold). "
                    "Suggests limited skin-in-the-game or possible stake dilution."
                )

            # --- Pledge Risk from Local Filings or Insider Transactions ---
            if promoter_pledge_pct is not None:
                if promoter_pledge_pct > 20.0:
                    pledge_risk = "HIGH"
                    governance_flags.append(
                        f"High promoter pledge risk: {promoter_pledge_pct:.1f}% of promoter shares pledged (>20% threshold)."
                    )
                elif promoter_pledge_pct > 10.0:
                    pledge_risk = "MODERATE"
                    governance_flags.append(
                        f"Moderate promoter pledge risk: {promoter_pledge_pct:.1f}% of promoter shares pledged."
                    )
            else:
                try:
                    insider_tx = getattr(ticker, "insider_transactions", None)
                    if insider_tx is not None and not insider_tx.empty:
                        total_shares = 0.0
                        pledged_estimate = 0.0
                        for _, row in insider_tx.iterrows():
                            shares = _num(row.get("Shares", row.get("shares", 0)))
                            tx_text = str(row.get("Transaction", row.get("transaction", ""))).lower()
                            if shares and shares > 0:
                                total_shares += abs(shares)
                                if any(kw in tx_text for kw in ("pledge", "hypothecate", "encumber", "collateral")):
                                    pledged_estimate += abs(shares)

                        if total_shares > 0 and pledged_estimate > 0:
                            promoter_pledge_pct = round((pledged_estimate / total_shares) * 100.0, 2)
                            if promoter_pledge_pct > 20.0:
                                pledge_risk = "HIGH"
                                governance_flags.append(
                                    f"High promoter pledge risk: ~{promoter_pledge_pct:.1f}% of insider shares estimated as pledged "
                                    "(>20% threshold). Collateral call risk in market downturn."
                                )
                            elif promoter_pledge_pct > 10.0:
                                pledge_risk = "MODERATE"
                                governance_flags.append(
                                    f"Moderate pledge risk: ~{promoter_pledge_pct:.1f}% of insider shares estimated as pledged."
                                )
                except Exception:
                    pass

            # --- Audit & Board Risk from ticker.info ---
            try:
                info = getattr(ticker, "info", {}) or {}
                audit_raw = _num(info.get("auditRisk"))
                board_raw = _num(info.get("boardRisk"))
                comp_raw = _num(info.get("compensationRisk"))

                if audit_raw is not None:
                    audit_risk_score = audit_raw
                    if audit_raw >= 7:
                        governance_flags.append(
                            f"High audit risk score: {audit_raw:.0f}/10 (Refinitiv ESG). "
                            "Elevated accounting opacity or auditor concerns."
                        )
                    elif audit_raw >= 5:
                        governance_flags.append(
                            f"Moderate audit risk score: {audit_raw:.0f}/10."
                        )

                if board_raw is not None:
                    board_risk_score = board_raw
                    if board_raw >= 7:
                        governance_flags.append(
                            f"High board governance risk: {board_raw:.0f}/10. "
                            "Board independence or oversight concerns flagged."
                        )

                if comp_raw is not None:
                    compensation_risk_score = comp_raw
                    if comp_raw >= 7:
                        governance_flags.append(
                            f"High compensation risk: {comp_raw:.0f}/10. "
                            "Excessive executive pay relative to performance."
                        )
            except Exception:
                pass

        except Exception:
            pass

        # --- Governance Grade ---
        risk_count = len(governance_flags)
        has_high_pledge = pledge_risk == "HIGH"
        has_high_audit = audit_risk_score is not None and audit_risk_score >= 7
        has_high_board = board_risk_score is not None and board_risk_score >= 7
        has_any_telemetry = any(
            v is not None for v in (promoter_holding_pct, promoter_pledge_pct, audit_risk_score, board_risk_score, compensation_risk_score)
        )

        if has_high_pledge or (risk_count >= 3) or (has_high_audit and promoter_holding_flag):
            governance_grade = "HIGH_RISK"
        elif risk_count >= 1 or has_high_audit or has_high_board:
            governance_grade = "ELEVATED_RISK"
        elif not has_any_telemetry:
            governance_grade = "UNAUDITED"
        else:
            governance_grade = "SOUND"

        return {
            "promoter_holding_pct": promoter_holding_pct,
            "promoter_pledge_pct": promoter_pledge_pct,
            "promoter_holding_flag": promoter_holding_flag,
            "pledge_risk": pledge_risk,
            "audit_risk_score": audit_risk_score,
            "board_risk_score": board_risk_score,
            "compensation_risk_score": compensation_risk_score,
            "governance_grade": governance_grade,
            "governance_flags": governance_flags,
        }

    def _compile_forensic_signals(
        self,
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        sub: Dict[str, Any],
        solv: Dict[str, Any],
        val: Dict[str, Any],
        gov: Optional[Dict[str, Any]] = None,
        peer_benchmarks: Optional[Dict[str, Any]] = None,
        f_score: Optional[Dict[str, Any]] = None,
        wc: Optional[Dict[str, Any]] = None,
        is_bfsi: bool = False,
        bfsi_health: Optional[Dict[str, Any]] = None,
        beneish: Optional[Dict[str, Any]] = None,
        filing_freshness: Optional[Dict[str, Any]] = None,
    ) -> tuple[List[str], List[str]]:
        """Compiles rule-based red flags and positive fundamental catalysts."""
        red_flags: List[str] = []
        catalysts: List[str] = []

        # 1. Earnings Quality Signals
        if eq["distortion_pct"] >= 30.0:
            red_flags.append(
                f"Severe earnings distortion: Reported PAT is inflated by {eq['distortion_pct']}% via non-operating items or minority claims."
            )
        elif eq["distortion_pct"] >= 15.0:
            red_flags.append(
                f"Moderate earnings distortion: {eq['distortion_pct']}% of PAT is non-core or non-attributable."
            )
        else:
            catalysts.append("High-quality clean earnings: Minimal distortion from non-operating or one-off items.")

        if eq["exceptional_items"] > 0:
            red_flags.append(
                f"Significant exceptional income of Rs. {eq['exceptional_items']:,.0f} Cr distorting reported profitability."
            )

        # 2. Cash Flow Signals (skip industrial CFO/WC rules for BFSI institutions)
        if not is_bfsi:
            if cf["conversion_status"] == "NEGATIVE_OPERATING_CASH_FLOW":
                red_flags.append(
                    "Critical red flag: Cash Flow from Operations (CFO) is NEGATIVE despite positive reported profit."
                )
            elif cf["cfo_to_pat_ratio"] < 0.65 and cf["cfo_to_pat_ratio"] > 0:
                red_flags.append(
                    f"Weak cash conversion: CFO is only {cf['cfo_to_pat_ratio']*100:.0f}% of reported PAT (profits are largely on paper)."
                )
            elif cf["cfo_to_pat_ratio"] >= 0.85:
                catalysts.append(
                    f"Superb cash conversion: CFO covers {cf['cfo_to_pat_ratio']*100:.0f}% of PAT with strong Free Cash Flow."
                )

            if cf["working_capital_divergence"]:
                red_flags.append(
                    f"Working capital drag: Trade receivables expanded +{cf['receivables_growth_pct']}% vs revenue growth of +{cf['revenue_growth_pct']}%."
                )

        # 3. Subsidiary Signals
        if sub["subsidiary_leakage_flag"]:
            red_flags.append(
                f"Subsidiary profit leakage: {sub['minority_share_pct']}% of consolidated PAT belongs to minority partners, not parent shareholders."
            )

        # 4. Solvency / BFSI Health Signals
        if is_bfsi and bfsi_health:
            red_flags.extend(bfsi_health.get("bfsi_flags", []))
            catalysts.extend(bfsi_health.get("bfsi_strengths", []))
        else:
            if solv["solvency_rating"] == "OVER_LEVERAGED":
                red_flags.append(
                    f"High balance sheet leverage: Debt-to-Equity is elevated at {solv['debt_to_equity']}."
                )
            elif solv["solvency_rating"] == "PRISTINE_OR_NET_CASH":
                catalysts.append(
                    "Fortress balance sheet: Company is net cash positive or virtually debt-free."
                )

        # 5. Valuation Signals
        if val["margin_of_safety_pct"] > 20.0:
            catalysts.append(
                f"Attractive margin of safety: Intrinsic valuation offers +{val['margin_of_safety_pct']}% upside."
            )
        elif val["margin_of_safety_pct"] < -25.0:
            red_flags.append(
                f"Stretched valuation: Market price is {abs(val['margin_of_safety_pct'])}% above intrinsic fair value."
            )

        # 6. Governance Signals
        if gov:
            for flag in gov.get("governance_flags", []):
                red_flags.append(f"[Governance] {flag}")
            if gov.get("governance_grade") == "SOUND" and not gov.get("promoter_holding_flag"):
                catalysts.append("Sound governance: Promoter holding healthy, low pledge and audit risk.")

        # 7. Peer Benchmarking Signals
        if peer_benchmarks:
            peer_comp = peer_benchmarks.get("peer_comparison", {})
            pe_vs = peer_comp.get("pe_vs_peers")
            roe_vs = peer_comp.get("roe_vs_peers")
            if pe_vs == "EXPENSIVE" and eq.get("distortion_pct", 0) >= 15.0:
                red_flags.append("[Peer Valuation] Premium valuation commanded despite non-trivial earnings distortion relative to peers.")
            elif pe_vs == "CHEAPER" and roe_vs == "SUPERIOR":
                catalysts.append(f"[Peer Valuation] Favorable relative value: {peer_benchmarks.get('peer_verdict')}")

        # 8. Piotroski F-Score (only assert F-Score flags/catalysts when >= 6 criteria evaluable)
        if f_score and f_score.get("evaluable_criteria", 0) >= 6:
            f_pts = f_score.get("score", 0)
            if f_pts >= 7:
                catalysts.append(f"Outstanding Piotroski F-Score: {f_pts}/9 indicates top-tier multi-period financial strength.")
            elif f_pts <= 3:
                red_flags.append(f"Weak Piotroski F-Score: {f_pts}/9 flags multi-period balance sheet or operational vulnerability.")

        # 9. Beneish M-Score & Filing Freshness
        if beneish and beneish.get("status") == "HIGH_MANIPULATION_RISK":
            red_flags.append(
                f"[Beneish M-Score] Elevated accounting manipulation risk (M-Score {beneish['m_score']} > -1.78 threshold)."
            )
        if filing_freshness and filing_freshness.get("is_stale"):
            red_flags.append(
                f"[Filing Staleness] Financial statements dated {filing_freshness.get('period_end_date')} are {filing_freshness.get('filing_age_days')} days old; verify latest exchange filings."
            )

        if wc and not is_bfsi:
            dso = wc.get("debtor_days")
            if dso is not None and dso > 120:
                red_flags.append(f"Extended Debtor Days: {dso:.0f} days required to collect cash receivables (working capital drag).")
            elif dso is not None and dso < 45:
                catalysts.append(f"Lean working capital: Rapid cash realization with Debtor Days at {dso:.0f} days.")

        return red_flags, catalysts

    def _synthesize_recommendation(
        self,
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        solv: Dict[str, Any],
        val: Dict[str, Any],
        red_flags: List[str],
        catalysts: List[str],
        market_price: float,
        gov: Optional[Dict[str, Any]] = None,
        f_score: Optional[Dict[str, Any]] = None,
        is_bfsi: bool = False,
        bfsi_health: Optional[Dict[str, Any]] = None,
        beneish: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Synthesizes all findings into a deterministic decision:
          - STRONG_BUY
          - BUY
          - HOLD
          - AVOID_OR_VALUE_TRAP
          - HIGH_RISK_DISTRESSED
        If governance_grade == HIGH_RISK, verdict is forced to AVOID_OR_VALUE_TRAP.
        """
        mos = val["margin_of_safety_pct"]
        num_flags = len(red_flags)
        cfo_ratio = 1.0 if is_bfsi else cf["cfo_to_pat_ratio"]
        distortion = eq["distortion_pct"]
        is_leveraged = (not is_bfsi) and (solv["solvency_rating"] in ("OVER_LEVERAGED", "DEBT_SERVICE_STRESS"))

        governance_grade = gov.get("governance_grade", "SOUND") if gov else "SOUND"
        if governance_grade == "HIGH_RISK":
            return {
                "verdict": "AVOID_OR_VALUE_TRAP",
                "verdict_badge": "🔴 AVOID / VALUE TRAP",
                "confidence_score": 87,
                "investment_thesis": (
                    "Governance red flags override quantitative merit: HIGH_RISK governance grade detected "
                    "(elevated promoter pledge, audit risk, or critically low promoter holding). "
                    "Capital preservation demands avoidance until governance concerns are resolved."
                )
            }

        f_evaluable = (f_score or {}).get("evaluable_criteria", 0)
        f_score_val = f_score.get("score") if (f_score and f_evaluable >= 6) else None
        beneish_high = bool(beneish and beneish.get("status") == "HIGH_MANIPULATION_RISK")
        bfsi_stressed = bool(is_bfsi and bfsi_health and bfsi_health.get("bfsi_grade") == "STRESSED_BFSI")

        if bfsi_stressed:
            return {
                "verdict": "HIGH_RISK_DISTRESSED",
                "verdict_badge": "🔴 HIGH RISK / BFSI STRESS",
                "confidence_score": 85,
                "investment_thesis": (
                    "BFSI asset quality / capital adequacy stress detected "
                    "(elevated NPA, weak RoA, or tight CRAR). Capital preservation demands avoidance."
                ),
            }

        if (is_leveraged and cfo_ratio < 0.50) or (f_score_val is not None and f_score_val <= 2 and is_leveraged):
            verdict = "HIGH_RISK_DISTRESSED"
            badge = "🔴 HIGH RISK / DISTRESSED"
            confidence = 88
            thesis = (
                f"High leverage combined with weak cash flow ({cfo_ratio*100:.0f}% CFO/PAT) and distressed F-Score ({f_score_val or 'N/A'}/9) "
                "poses acute balance sheet vulnerability. Capital preservation demands avoidance."
            )
        elif beneish_high or distortion >= 30.0 or (not is_bfsi and cfo_ratio <= 0.40) or num_flags >= 3 or (f_score_val is not None and f_score_val <= 2):
            verdict = "AVOID_OR_VALUE_TRAP"
            badge = "🔴 AVOID / VALUE TRAP"
            confidence = 85
            thesis = (
                f"Forensic discrepancies detected: {distortion}% earnings distortion, CFO/PAT "
                f"{cfo_ratio*100:.0f}%, Piotroski {f_score_val or 'N/A'}/9, Beneish {beneish.get('m_score') if beneish else 'N/A'}. "
                "Reported profitability masks underlying operational or accounting risk."
            )
        elif mos >= 20.0 and (is_bfsi or cfo_ratio >= 0.80) and distortion < 15.0 and num_flags == 0 and (f_score_val is None or f_score_val >= 7):
            verdict = "STRONG_BUY"
            badge = "🟢 STRONG BUY"
            confidence = 90
            thesis = (
                f"Exceptional quality compounder with {mos}% margin of safety and robust Piotroski F-score ({f_score_val or 'Strong'}/9). "
                "Clean reported earnings backed by strong fundamentals and a resilient balance sheet."
            )
        elif mos >= 10.0 and (is_bfsi or cfo_ratio >= 0.70) and distortion < 25.0 and num_flags <= 1:
            verdict = "BUY"
            badge = "🟢 BUY (VALUE OPPORTUNITY)"
            confidence = 80
            thesis = (
                f"Attractive risk-reward with {mos}% margin of safety on intrinsic fair value. "
                "Cash conversion and earnings quality remain healthy."
            )
        elif mos >= -25.0 and num_flags <= 2:
            verdict = "HOLD"
            badge = "🟡 HOLD / WATCHLIST"
            confidence = 72
            thesis = (
                f"Company is trading near intrinsic fair value (margin of safety {mos}%). "
                "Maintain existing positions and await a wider margin of safety."
            )
        else:
            verdict = "AVOID_OVERVALUED"
            badge = "🟠 AVOID (OVERVALUED)"
            confidence = 78
            thesis = (
                f"Market price is running {abs(mos)}% above intrinsic fair value ({val.get('valuation_method', 'model')}). "
                "Risk-reward is asymmetric to the downside."
            )

        return {
            "verdict": verdict,
            "verdict_badge": badge,
            "confidence_score": confidence,
            "investment_thesis": thesis
        }
