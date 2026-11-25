"""
Deterministic 100-Point Stock Catalyst Scorer.

Scores corporate announcements out of 100 across 6 weighted pillars:
  1. Financial Impact (0-25)     - scaled against TTM annual revenue (never raw hype)
  2. Business Growth (0-20)      - category structural impact (JV/tech transfer, order win, etc.)
  3. News Novelty (0-15)         - penalizes repeat disclosures within 30 days
  4. Revenue Visibility (0-15)   - multi-year / recurring / order-book visibility
  5. Source Credibility (0-10)   - NSE/BSE/SEBI/PIB primary filings vs secondary news
  6. Market Reaction (0-15)      - RVOL, NSE delivery %, and early price confirmation
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

CATEGORY_GROWTH_SCORES = {
    "STRATEGIC_JV_TECH_TRANSFER": 19.0,
    "LARGE_ORDER_WIN": 17.0,
    "ACQUISITION_NEW_BUSINESS": 16.0,
    "GOVT_POLICY_BENEFICIARY": 15.0,
    "CAPACITY_EXPANSION": 14.0,
    "ROUTINE": 4.0,
}

SOURCE_CREDIBILITY_SCORES = {
    "NSE": 10.0,
    "BSE": 10.0,
    "SEBI": 10.0,
    "PIB": 10.0,
    "TENDER": 9.0,
    "IR": 8.0,
    "EARNINGS_CALL": 8.0,
    "NEWS": 5.0,
}


def extract_deal_value_cr(text: str) -> Optional[float]:
    """
    Extracts monetary deal/order/capex value in INR Crores from announcement text.
    Supports patterns like 'Rs 500 Cr', '₹ 1,250 crore', 'INR 450.5 Cr', '5000 Lakhs'.
    """
    if not text:
        return None
    s = str(text).replace(",", "")
    # Crore patterns
    m_cr = re.search(
        r"(?:rs\.?|inr|₹)\s*([0-9]+(?:\.[0-9]+)?)\s*(?:crores?|crs?|cr\b)",
        s,
        flags=re.IGNORECASE,
    )
    if not m_cr:
        m_cr = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:crores?|cr\b)", s, flags=re.IGNORECASE)
    if m_cr:
        val = float(m_cr.group(1))
        return round(val, 2) if val > 0 else None

    # Lakh patterns -> convert to Cr
    m_lk = re.search(
        r"(?:rs\.?|inr|₹)?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:lakhs?|lacs?)",
        s,
        flags=re.IGNORECASE,
    )
    if m_lk:
        val = float(m_lk.group(1)) / 100.0
        return round(val, 2) if val > 0 else None
    return None


def classify_catalyst_category(title: str, summary: str = "") -> str:
    """Classifies announcement text into one of 6 deterministic catalyst categories."""
    blob = f"{title} {summary}".lower()

    if any(k in blob for k in (
        "joint venture", "jv ", "strategic partnership", "technology transfer",
        "tech transfer", "collaboration agreement", "licensing agreement", "mou ", "memorandum of understanding"
    )):
        return "STRATEGIC_JV_TECH_TRANSFER"

    if any(k in blob for k in (
        "order win", "bagged order", "received order", "letter of award", "loa ",
        "work order", "contract worth", "supply order", "purchase order", "l1 bidder", "awarded contract"
    )) or (
        any(v in blob for v in ("bagged", "won ", "wins ", "received", "secures", "secured", "awarded"))
        and any(n in blob for n in ("order", "contract", "tender"))
    ):
        return "LARGE_ORDER_WIN"

    if any(k in blob for k in (
        "acquisition", "acquired ", "acquire ", "stake buy", "new business",
        "foray into", "subsidiary incorporation", "amalgamation", "merger"
    )):
        return "ACQUISITION_NEW_BUSINESS"

    if any(k in blob for k in (
        "government policy", "pli scheme", "production linked", "ministry",
        "cabinet approval", "import duty", "customs duty", "tender", "railways", "defence"
    )):
        return "GOVT_POLICY_BENEFICIARY"

    if any(k in blob for k in (
        "capacity expansion", "capex", "greenfield", "brownfield",
        "commissioning", "new plant", "new facility", "manufacturing unit"
    )):
        return "CAPACITY_EXPANSION"

    return "ROUTINE"


def _score_financial_impact(
    deal_value_cr: Optional[float],
    annual_revenue_cr: Optional[float],
    category: str,
) -> float:
    """
    0-25 points. Scales deal value against TTM annual revenue so a Rs 500 Cr order
    for a Rs 500 Cr company scores far higher than for a Rs 10,000 Cr company.
    """
    if deal_value_cr and deal_value_cr > 0:
        if annual_revenue_cr and annual_revenue_cr > 0:
            ratio = deal_value_cr / annual_revenue_cr
            if ratio >= 0.50:
                return 25.0
            if ratio >= 0.25:
                return 22.0
            if ratio >= 0.10:
                return 18.0
            if ratio >= 0.05:
                return 14.0
            if ratio >= 0.02:
                return 10.0
            if ratio >= 0.005:
                return 6.0
            return 3.0
        # Revenue unknown: conservative size-based fallback
        if deal_value_cr >= 1000:
            return 18.0
        if deal_value_cr >= 300:
            return 15.0
        if deal_value_cr >= 100:
            return 12.0
        return 8.0

    # No explicit deal value stated
    if category == "STRATEGIC_JV_TECH_TRANSFER":
        return 14.0
    if category in ("GOVT_POLICY_BENEFICIARY", "ACQUISITION_NEW_BUSINESS", "CAPACITY_EXPANSION"):
        return 12.0
    if category == "LARGE_ORDER_WIN":
        return 11.0
    return 4.0


def _score_revenue_visibility(text: str, category: str) -> float:
    """0-15 points for multi-year, recurring, or clear execution-horizon visibility."""
    blob = text.lower()
    score = 6.0 if category != "ROUTINE" else 2.0
    if any(k in blob for k in ("multi-year", "years", "months", "long-term", "annuity", "recurring", "o&m")):
        score += 5.0
    if any(k in blob for k in ("export", "global", "order book", "backlog", "execution")):
        score += 4.0
    return min(15.0, score)


def _score_market_reaction(market_ctx: Optional[Dict[str, Any]]) -> float:
    """0-15 points from RVOL, delivery %, and early price action."""
    if not market_ctx:
        return 0.0
    pts = 0.0
    rvol = float(market_ctx.get("rvol") or 0.0)
    delivery = float(market_ctx.get("delivery_pct") or 0.0)
    pct_chg = float(market_ctx.get("pct_change") or 0.0)

    if rvol >= 2.0:
        pts += 6.0
    elif rvol >= 1.4:
        pts += 4.5
    elif rvol >= 1.15:
        pts += 2.5

    if delivery >= 55.0:
        pts += 5.0
    elif delivery >= 45.0:
        pts += 3.5
    elif delivery >= 35.0:
        pts += 1.5

    if 0.5 <= pct_chg <= 6.0:
        pts += 4.0
    elif pct_chg > 6.0:
        pts += 2.5  # Already extended
    elif pct_chg > 0:
        pts += 1.5

    return min(15.0, round(pts, 2))


def score_catalyst(
    title: str,
    summary: str = "",
    source: str = "NSE",
    category: Optional[str] = None,
    deal_value_cr: Optional[float] = None,
    annual_revenue_cr: Optional[float] = None,
    recent_count_30d: int = 0,
    market_ctx: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Computes the deterministic 100-point Catalyst Assessment and Alert Tier (A/B/C).
    """
    eff_cat = category or classify_catalyst_category(title, summary)
    eff_deal = deal_value_cr if deal_value_cr is not None else extract_deal_value_cr(f"{title} {summary}")

    fin_pts = _score_financial_impact(eff_deal, annual_revenue_cr, eff_cat)
    growth_pts = CATEGORY_GROWTH_SCORES.get(eff_cat, 4.0)
    novelty_pts = 15.0 if recent_count_30d <= 0 else (10.0 if recent_count_30d == 1 else 5.0)
    vis_pts = _score_revenue_visibility(f"{title} {summary}", eff_cat)
    cred_pts = SOURCE_CREDIBILITY_SCORES.get(source.upper().strip(), 5.0)
    mkt_pts = _score_market_reaction(market_ctx)

    total = round(fin_pts + growth_pts + novelty_pts + vis_pts + cred_pts + mkt_pts, 1)
    tier = "A" if total >= 80.0 else ("B" if total >= 65.0 else "C")

    return {
        "category": eff_cat,
        "deal_value_cr": eff_deal,
        "annual_revenue_cr": annual_revenue_cr,
        "total_score": total,
        "tier": tier,
        "score_breakdown": {
            "financial_impact": round(fin_pts, 1),
            "business_growth": round(growth_pts, 1),
            "news_novelty": round(novelty_pts, 1),
            "revenue_visibility": round(vis_pts, 1),
            "source_credibility": round(cred_pts, 1),
            "market_reaction": round(mkt_pts, 1),
        },
    }
