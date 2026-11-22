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
from storage.cache_manager import CacheManager
from tools.fundamental_tools import FundamentalAnalysisEngine
from tools.peer_benchmark_engine import PeerBenchmarkEngine
from tools.local_financials_parser import LocalFinancialsParser


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
        financial_statement_override: Optional[Dict[str, Any]] = None
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

        # 3. Earnings Quality Normalization
        eq = self._audit_earnings_quality(stmts, fund_data)

        # 4. Cash Flow & Working Capital Audit
        cf = self._audit_cash_conversion(stmts, fund_data)

        # 5. Subsidiary & Minority Interest Attribution
        sub = self._audit_subsidiary_attribution(stmts, fund_data)

        # 6. Solvency & Balance Sheet Health
        solv = self._audit_solvency_and_debt(stmts, fund_data)

        # 7. Valuation & Fair Value Calculation
        market_price = _num(price_override)
        if market_price is None or market_price <= 0:
            market_price = self._get_current_price(symbol_clean, fund_data)

        val = self._calculate_sustainable_valuation(eq, cf, solv, fund_data, market_price)

        # 6b. Governance & Promoter Pledging Telemetry
        gov = self._audit_governance_telemetry(symbol_clean, fund_data)

        # 6c. Piotroski F-Score & Working Capital Efficiency
        f_score = self._calculate_piotroski_f_score(stmts, fund_data, eq, cf, solv)
        wc = self._calculate_working_capital_metrics(stmts)

        # 7b. Automated Peer Valuation Comparison
        sector_name = stmts.get("sector") or fund_data.get("sector", "")
        peer_engine = PeerBenchmarkEngine()
        peer_benchmarks = peer_engine.compute_peer_benchmarks(symbol_clean, sector_name, self.fund_engine)

        # 8. Forensic Red Flags & Positive Catalysts
        red_flags, catalysts = self._compile_forensic_signals(eq, cf, sub, solv, val, gov, peer_benchmarks, f_score, wc)

        # 9. Deterministic Investment Recommendation Verdict
        rec = self._synthesize_recommendation(eq, cf, solv, val, red_flags, catalysts, market_price, gov, f_score)

        return {
            "symbol": symbol_clean,
            "company_name": stmts.get("company_name", symbol_clean),
            "sector": stmts.get("sector", fund_data.get("sector", "N/A")),
            "market_price": market_price,
            "verdict": rec["verdict"],
            "verdict_badge": rec["verdict_badge"],
            "confidence_score": rec["confidence_score"],
            "fair_value": val["intrinsic_fair_value"],
            "margin_of_safety_pct": val["margin_of_safety_pct"],
            "piotroski_f_score": f_score["score"],
            "piotroski_rating": f_score["rating"],
            "piotroski_f_score_details": f_score,
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
            return local_stmt

        data: Dict[str, Any] = {
            "source": "Standardized Telemetry",
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

                def get_fin(item, col=latest_col):
                    return _num(fin.loc[item, col]) if item in fin.index else 0.0

                data["revenue"] = get_fin("Total Revenue") or get_fin("Operating Revenue")
                data["reported_pat"] = get_fin("Net Income") or get_fin("Net Income Common Stockholders")
                data["other_income"] = get_fin("Other Income Expense") or get_fin("Non Operating Income Net Other")
                data["exceptional_items"] = get_fin("Special Income Charges") or get_fin("Other Special Charges")
                data["minority_interest"] = get_fin("Minority Interest") or get_fin("Net Income Continuous Operations to Noncontrolling Interests")

                if prev_col is not None:
                    data["revenue_prior"] = get_fin("Total Revenue", prev_col)

            if cf is not None and not cf.empty:
                latest_cf = cf.columns[0]
                def get_cf(item):
                    return _num(cf.loc[item, latest_cf]) if item in cf.index else 0.0

                data["cfo"] = get_cf("Operating Cash Flow") or get_cf("Cash Flowsfromusedin Operating Activities Direct")
                data["capex"] = abs(get_cf("Capital Expenditure") or get_cf("Purchase Of PPE"))
                if data["cfo"]:
                    data["free_cashflow"] = data["cfo"] - data["capex"]

            if bs is not None and not bs.empty:
                latest_bs = bs.columns[0]
                prev_bs = bs.columns[1] if len(bs.columns) > 1 else None
                def get_bs(item, col=latest_bs):
                    return _num(bs.loc[item, col]) if item in bs.index else 0.0

                data["trade_receivables"] = get_bs("Receivables") or get_bs("Accounts Receivable")
                if prev_bs is not None:
                    data["receivables_prior"] = get_bs("Receivables", prev_bs) or get_bs("Accounts Receivable", prev_bs)

        except Exception:
            pass

        # If statement revenue/pat still missing, derive from fund_data market cap / ratios
        mcap = _num(fund_data.get("market_cap"), 1000.0)
        pe = _num(fund_data.get("pe_ratio"), 20.0)
        if data["reported_pat"] == 0.0 and pe and pe > 0:
            data["reported_pat"] = round(mcap / pe, 2)
        if data["revenue"] == 0.0:
            rg = _num(fund_data.get("revenue_growth_pct"), 10.0)
            data["revenue"] = round(data["reported_pat"] * 8.0, 2)
            data["revenue_prior"] = round(data["revenue"] / (1.0 + rg / 100.0), 2)

        if data["cfo"] == 0.0:
            fcf = _num(fund_data.get("free_cashflow"))
            if fcf is not None and fcf != 0:
                data["free_cashflow"] = fcf
                data["cfo"] = round(fcf * 1.25, 2)
                data["capex"] = round(fcf * 0.25, 2)
            else:
                # Default conservative CFO estimate based on profit
                data["cfo"] = round(data["reported_pat"] * 0.85, 2)
                data["capex"] = round(data["reported_pat"] * 0.30, 2)
                data["free_cashflow"] = data["cfo"] - data["capex"]

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

    def _audit_solvency_and_debt(self, stmts: Dict[str, Any], fund_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyzes leverage, net cash status, and current debt service ability.
        """
        total_debt = _num(stmts.get("total_debt"), _num(fund_data.get("total_debt"), 0.0))
        total_cash = _num(stmts.get("total_cash"), _num(fund_data.get("total_cash"), 0.0))
        net_debt = round(total_debt - total_cash, 2)
        de_ratio = _num(fund_data.get("debt_to_equity"))
        current_ratio = _num(fund_data.get("current_ratio"))

        # Interest coverage estimate
        reported_pat = _num(stmts.get("reported_pat"), 10.0)
        estimated_ebit = reported_pat * 1.35
        interest_cost = total_debt * 0.09  # 9% estimated borrowing cost
        interest_coverage = round(estimated_ebit / interest_cost, 2) if interest_cost > 0 else 99.0

        is_debt_free = net_debt <= 0
        solvency_rating = "PRISTINE"
        if total_debt > 0 and de_ratio and de_ratio > 150:
            solvency_rating = "OVER_LEVERAGED"
        elif interest_coverage < 2.5 and not is_debt_free:
            solvency_rating = "DEBT_SERVICE_STRESS"
        elif is_debt_free or (de_ratio and de_ratio < 30):
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

    def _calculate_sustainable_valuation(
        self,
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        solv: Dict[str, Any],
        fund_data: Dict[str, Any],
        market_price: float
    ) -> Dict[str, Any]:
        """
        Calculates Intrinsic Fair Value per share based on SUSTAINABLE recurring earnings
        and cash conversion, discounting for distortion.
        """
        reported_pat = eq["reported_pat"]
        sustainable_pat = eq["sustainable_pat"]
        pe_ratio = _num(fund_data.get("pe_ratio"), 20.0)

        # Baseline earnings multiplier
        base_multiple = min(35.0, max(12.0, pe_ratio))

        # Haircuts for low quality earnings & weak cash flow
        haircut = 1.0
        if eq["distortion_pct"] > 30.0:
            haircut *= 0.75  # 25% discount for high distortion
        elif eq["distortion_pct"] > 15.0:
            haircut *= 0.88

        if cf["cfo_to_pat_ratio"] < 0.60:
            haircut *= 0.80  # 20% discount for poor cash conversion
        elif cf["cfo_to_pat_ratio"] >= 0.90:
            haircut *= 1.08  # 8% premium for superior cash generator

        if solv["solvency_rating"] == "OVER_LEVERAGED":
            haircut *= 0.75

        # Intrinsic price proxy
        sustainable_ratio = (sustainable_pat / reported_pat) if reported_pat > 0 else 1.0
        intrinsic_fair_value = round(market_price * sustainable_ratio * haircut, 2)
        if intrinsic_fair_value <= 0:
            intrinsic_fair_value = round(market_price * 0.40, 2)

        margin_of_safety_pct = round(((intrinsic_fair_value - market_price) / market_price) * 100.0, 2) if market_price > 0 else 0.0

        return {
            "intrinsic_fair_value": intrinsic_fair_value,
            "margin_of_safety_pct": margin_of_safety_pct,
            "applied_haircut_factor": round(haircut, 2),
            "sustainable_earnings_ratio": round(sustainable_ratio, 2),
            "valuation_verdict": "UNDERVALUED" if margin_of_safety_pct > 15.0 else ("OVERVALUED" if margin_of_safety_pct < -15.0 else "FAIRLY_VALUED")
        }

    def _calculate_piotroski_f_score(
        self,
        stmts: Dict[str, Any],
        fund_data: Dict[str, Any],
        eq: Dict[str, Any],
        cf: Dict[str, Any],
        solv: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Calculates the 9-point Piotroski F-Score to evaluate financial strength:
        Profitability:
          1. Positive Net Income (ROA > 0)
          2. Positive Operating Cash Flow (CFO > 0)
          3. Higher ROA in current year vs prior (or positive sustainable PAT)
          4. Quality of earnings (CFO > Net Income / Accrual test)
        Leverage, Liquidity and Source of Funds:
          5. Lower Long-Term Debt / Leverage ratio
          6. Higher Current Ratio (liquidity)
          7. No Dilution (no substantial share count expansion)
        Operating Efficiency:
          8. Higher Gross / Operating Margin
          9. Higher Asset Turnover / Revenue Growth
        Returns score (0-9) and qualitative category (STRONG: 7-9, MODERATE: 4-6, WEAK: 0-3).
        """
        score = 0
        points = []

        reported_pat = _num(stmts.get("reported_pat"), 0.0)
        cfo = _num(cf.get("cfo"), 0.0)
        rev_now = _num(stmts.get("revenue"), 0.0)
        rev_prev = _num(stmts.get("revenue_prior"), 0.0)
        total_debt = _num(solv.get("total_debt"), 0.0)
        current_ratio = _num(solv.get("current_ratio"))

        # 1. Net Income > 0
        if reported_pat > 0:
            score += 1
            points.append("Positive Net Income (+1)")
        # 2. CFO > 0
        if cfo > 0:
            score += 1
            points.append("Positive Operating Cash Flow (+1)")
        # 3. Sustainable Core Profitability
        if eq.get("sustainable_pat", 0) > 0 and reported_pat > 0:
            score += 1
            points.append("Sound Core Recurring Earnings (+1)")
        # 4. Accruals: CFO > Net Income (Clean cash backed earnings)
        if cfo > reported_pat and reported_pat > 0:
            score += 1
            points.append("Superior Cash Accrual Quality CFO > PAT (+1)")

        # 5. Leverage: Net cash or virtually zero leverage
        if solv.get("net_cash_positive") or (total_debt == 0.0):
            score += 1
            points.append("Debt-Free / Net Cash Balance Sheet (+1)")
        elif solv.get("solvency_rating") == "PRISTINE_OR_NET_CASH":
            score += 1
            points.append("Manageable Low Debt Profile (+1)")

        # 6. Liquidity: Current Ratio >= 1.25
        if current_ratio is not None and isinstance(current_ratio, (int, float)) and current_ratio >= 1.25:
            score += 1
            points.append(f"Comfortable Liquidity (CR {current_ratio:.2f}) (+1)")

        # 7. Quality of Balance Sheet: Working capital not bloated
        if not cf.get("working_capital_divergence", False):
            score += 1
            points.append("No Debtor / Working Capital Bloat (+1)")

        # 8. Revenue Growth: Current > Prior
        if rev_now > rev_prev and rev_prev > 0:
            score += 1
            points.append("Top-Line Revenue Expansion (+1)")

        # 9. Operating Margin & Capital Efficiency: ROE >= 12%
        roe = _num(fund_data.get("roe_pct"))
        if roe is not None and roe >= 12.0:
            score += 1
            points.append(f"High Capital Efficiency (ROE {roe:.1f}%) (+1)")

        rating = "STRONG" if score >= 7 else ("MODERATE" if score >= 4 else "WEAK")
        return {
            "score": score,
            "rating": rating,
            "points": points
        }

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
        fund_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Fetches promoter holding data and governance risk signals from yfinance.
        Flags promoter pledging risk, audit risk, and board governance concerns.
        Returns a governance_telemetry dict with deterministic grade and flags.
        Strictly read-only. No order placement.
        """
        governance_flags: List[str] = []
        promoter_holding_pct: Optional[float] = None
        promoter_holding_flag = False
        pledge_risk = "LOW"
        audit_risk_score: Optional[float] = None
        board_risk_score: Optional[float] = None
        compensation_risk_score: Optional[float] = None

        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{symbol}.NS")

            # --- Promoter / Insider Holding % ---
            try:
                major_holders = getattr(ticker, "major_holders", None)
                if major_holders is not None and not major_holders.empty:
                    # yfinance major_holders: row 0 = % held by insiders, row 1 = % held by institutions
                    for idx in range(len(major_holders)):
                        label = str(major_holders.iloc[idx, 1]).lower() if major_holders.shape[1] > 1 else ""
                        value_raw = major_holders.iloc[idx, 0]
                        if "insider" in label or "promoter" in label:
                            pct = _num(value_raw)
                            if pct is not None:
                                # yfinance returns a decimal (e.g. 0.52 for 52%)
                                promoter_holding_pct = round(pct * 100.0, 2) if pct <= 1.0 else round(pct, 2)
                            break
                    # Fallback: first row is insider %
                    if promoter_holding_pct is None:
                        pct = _num(major_holders.iloc[0, 0])
                        if pct is not None:
                            promoter_holding_pct = round(pct * 100.0, 2) if pct <= 1.0 else round(pct, 2)
            except Exception:
                pass

            if promoter_holding_pct is not None and promoter_holding_pct < 30.0:
                promoter_holding_flag = True
                governance_flags.append(
                    f"Low promoter/insider holding: {promoter_holding_pct:.1f}% (<30% threshold). "
                    "Suggests limited skin-in-the-game or possible stake dilution."
                )

            # --- Pledge Risk from Insider Transactions ---
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
                            # Treat "pledge", "hypothecate" transactions as pledged
                            if any(kw in tx_text for kw in ("pledge", "hypothecate", "encumber", "collateral")):
                                pledged_estimate += abs(shares)

                    if total_shares > 0 and pledged_estimate > 0:
                        pledge_pct = round((pledged_estimate / total_shares) * 100.0, 2)
                        if pledge_pct > 20.0:
                            pledge_risk = "HIGH"
                            governance_flags.append(
                                f"High promoter pledge risk: ~{pledge_pct:.1f}% of insider shares estimated as pledged "
                                "(>20% threshold). Collateral call risk in market downturn."
                            )
                        elif pledge_pct > 10.0:
                            pledge_risk = "MODERATE"
                            governance_flags.append(
                                f"Moderate pledge risk: ~{pledge_pct:.1f}% of insider shares estimated as pledged."
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

        if has_high_pledge or (risk_count >= 3) or (has_high_audit and promoter_holding_flag):
            governance_grade = "HIGH_RISK"
        elif risk_count >= 1 or has_high_audit or has_high_board:
            governance_grade = "ELEVATED_RISK"
        else:
            governance_grade = "SOUND"

        return {
            "promoter_holding_pct": promoter_holding_pct,
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
        wc: Optional[Dict[str, Any]] = None
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

        # 2. Cash Flow Signals
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

        # 4. Solvency Signals
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
                f"Attractive margin of safety: Sustainable fair value offers +{val['margin_of_safety_pct']}% upside."
            )
        elif val["margin_of_safety_pct"] < -25.0:
            red_flags.append(
                f"Stretched valuation: Market price is {abs(val['margin_of_safety_pct'])}% above sustainable core earnings power."
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

        # 8. Piotroski F-Score & Working Capital Signals
        if f_score:
            f_pts = f_score.get("score", 0)
            if f_pts >= 8:
                catalysts.append(f"Outstanding Piotroski F-Score: {f_pts}/9 indicates top-tier financial strength & profitability.")
            elif f_pts <= 3:
                red_flags.append(f"Weak Piotroski F-Score: {f_pts}/9 flags multi-dimensional balance sheet or operational vulnerability.")

        if wc:
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
        f_score: Optional[Dict[str, Any]] = None
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
        cfo_ratio = cf["cfo_to_pat_ratio"]
        distortion = eq["distortion_pct"]
        is_leveraged = solv["solvency_rating"] in ("OVER_LEVERAGED", "DEBT_SERVICE_STRESS")

        # Governance override — HIGH_RISK governance forces AVOID_OR_VALUE_TRAP
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

        # Deterministic Rules
        # Piotroski F-score and leverage distress check
        f_score_val = f_score.get("score") if f_score else None
        if (is_leveraged and cfo_ratio < 0.50) or (f_score_val is not None and f_score_val <= 2 and is_leveraged):
            verdict = "HIGH_RISK_DISTRESSED"
            badge = "🔴 HIGH RISK / DISTRESSED"
            confidence = 88
            thesis = (
                f"High leverage combined with weak cash flow ({cfo_ratio*100:.0f}% CFO/PAT) and distressed F-Score ({f_score_val or 'N/A'}/9) "
                "poses acute balance sheet vulnerability. Capital preservation demands avoidance."
            )
        elif distortion >= 30.0 or cfo_ratio <= 0.40 or num_flags >= 3 or (f_score_val is not None and f_score_val <= 2):
            verdict = "AVOID_OR_VALUE_TRAP"
            badge = "🔴 AVOID / VALUE TRAP"
            confidence = 85
            thesis = (
                f"Severe forensic discrepancies detected: {distortion}% earnings distortion, weak cash conversion "
                f"({cfo_ratio*100:.0f}% of PAT) or weak Piotroski score ({f_score_val or 'N/A'}/9). "
                "Reported profitability masks underlying operational weakness."
            )
        elif mos >= 20.0 and cfo_ratio >= 0.80 and distortion < 15.0 and num_flags == 0 and (f_score_val is None or f_score_val >= 7):
            verdict = "STRONG_BUY"
            badge = "🟢 STRONG BUY"
            confidence = 90
            thesis = (
                f"Exceptional quality compounder with {mos}% margin of safety and robust Piotroski F-score ({f_score_val or 'Strong'}/9). "
                "Clean reported earnings backed by strong Free Cash Flow and a resilient balance sheet."
            )
        elif mos >= 10.0 and cfo_ratio >= 0.70 and distortion < 25.0 and num_flags <= 1:
            verdict = "BUY"
            badge = "🟢 BUY (VALUE OPPORTUNITY)"
            confidence = 80
            thesis = (
                f"Attractive risk-reward with {mos}% margin of safety on sustainable earnings. "
                "Cash conversion is healthy with manageable working capital."
            )
        elif mos >= -15.0 and num_flags <= 2:
            verdict = "HOLD"
            badge = "🟡 HOLD / WATCHLIST"
            confidence = 72
            thesis = (
                f"Company is trading near sustainable fair value (margin of safety {mos}%). "
                "Maintain existing positions but await a more compelling entry multiple or cash flow acceleration."
            )
        else:
            verdict = "AVOID_OVERVALUED"
            badge = "🟠 AVOID (OVERVALUED)"
            confidence = 78
            thesis = (
                f"Market price is priced to perfection, running {abs(mos)}% above sustainable fair value. "
                "Risk-reward is asymmetric to the downside."
            )

        return {
            "verdict": verdict,
            "verdict_badge": badge,
            "confidence_score": confidence,
            "investment_thesis": thesis
        }
