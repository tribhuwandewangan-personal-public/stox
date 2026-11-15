"""
Fundamental Picks Scoring Engine
=================================
Pure rule-based, deterministic multi-criteria scoring for
"Top 10 Fundamental Stocks — Right Time to Buy".

Scoring rubric (0–100 pts, can go negative):
  PEG ratio quality   : up to +25 pts
  Balance sheet       : up to +15 pts
  Valuation           : up to +12 pts  (gate: Overvalued = disqualified)
  52W timing window   : up to +15 pts  (sweet spot –5% to –20% from peak)
  Institutional flow  : up to +10 pts
  LT Verdict moat     : up to +10 pts
  Liquidity / coverage: up to  +5 pts
  Catalyst bonus      : up to  +3 pts

Eligibility gate (ALL must pass):
  - Has synthesizer output (any age; prefer < 7 days for scoring bonus)
  - valuation_assessment must NOT be "Overvalued" or "High Premium"
    (unless PEG < 1.0 — cheap enough to override valuation label)
  - pct_from_52w_high < –3%  (not at all-time high — can't be right entry)
  - action_verdict is NOT "SELL"
"""

from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def score_fundamental_pick(sym: str, synth_res: dict, tech_res: dict | None) -> dict | None:
    """
    Score one stock for the Fundamental Picks table.

    Parameters
    ----------
    sym       : ticker symbol (e.g. "RELIANCE")
    synth_res : result dict from Master Prediction Synthesizer Agent
    tech_res  : result dict from Technical Analysis Agent (may be None)

    Returns
    -------
    dict with scoring details, or None if ineligible.
    """

    sig       = synth_res.get("structured_signal", {})
    fund_out  = synth_res.get("agent_outputs", {}).get("fundamental", {}) or {}
    tech_out  = (tech_res or {}).get("raw_indicators", {}) or {}

    verdict = str(sig.get("action_verdict", "HOLD")).upper()
    if verdict == "SELL":
        return None                               # hard gate

    peg_raw       = _safe_float(synth_res.get("peg_ratio") or fund_out.get("peg_ratio"))
    pe_raw        = _safe_float(synth_res.get("pe_ratio")  or fund_out.get("pe_ratio"))
    de_raw        = _safe_float(synth_res.get("debt_to_equity") or fund_out.get("debt_to_equity"))
    cr_raw        = _safe_float(synth_res.get("current_ratio")  or fund_out.get("current_ratio"))
    net_cash_flag = str(synth_res.get("net_cash_status") or fund_out.get("net_cash_status") or "").lower()
    val_text      = str(synth_res.get("valuation_assessment") or fund_out.get("valuation_assessment") or "").lower()
    lt_verdict    = str(sig.get("long_term_verdict") or "").upper()
    # pct from 52W high (negative = below high)
    pct52w        = _safe_float(tech_out.get("pct_from_52w_high"))
    ud_ratio      = _safe_float(tech_out.get("up_down_vol_ratio"))
    swing_low20   = _safe_float(tech_out.get("swing_low_20"))
    last_price    = _safe_float(synth_res.get("last_price") or tech_out.get("last_price"))
    upcoming_ev   = str(sig.get("upcoming_events_note") or "").lower()

    # ── Eligibility gates ────────────────────────────────────────────────────
    is_overvalued = any(x in val_text for x in ("overvalued", "high premium", "expensive"))
    if is_overvalued and (peg_raw is None or peg_raw >= 1.0):
        return None                               # overvalued without compelling PEG

    if pct52w is not None and pct52w >= -3.0:
        return None                               # too close to 52W high — not a right-time entry

    # ── Score ─────────────────────────────────────────────────────────────────
    score = 0
    reasons = []

    # 1. PEG ratio (primary value quality signal)
    if peg_raw is not None:
        if peg_raw <= 0.8:
            score += 25; reasons.append("Exceptional PEG ≤0.8")
        elif peg_raw <= 1.0:
            score += 22; reasons.append("Excellent PEG ≤1.0")
        elif peg_raw <= 1.5:
            score += 18; reasons.append("Good PEG ≤1.5")
        elif peg_raw <= 2.0:
            score += 10; reasons.append("Acceptable PEG ≤2.0")
        elif peg_raw <= 2.5:
            score += 3
        else:
            score -= 10; reasons.append(f"Pricey PEG {peg_raw:.1f}")
    elif pe_raw is not None:
        # Fallback: use P/E heuristics when PEG unavailable
        if pe_raw <= 15:
            score += 12; reasons.append(f"Low P/E {pe_raw:.0f}x")
        elif pe_raw <= 25:
            score += 6
        elif pe_raw > 50:
            score -= 8

    # 2. Balance sheet quality
    if "net cash" in net_cash_flag or "positive" in net_cash_flag or "debt-free" in net_cash_flag:
        score += 15; reasons.append("Net Cash / Debt-Free")
    elif "low" in net_cash_flag or "minimal" in net_cash_flag:
        score += 8; reasons.append("Low Debt")
    elif de_raw is not None:
        if de_raw <= 0.3:
            score += 12; reasons.append("Strong B/S (D/E ≤0.3)")
        elif de_raw <= 0.8:
            score += 6
        elif de_raw <= 1.5:
            score += 0
        elif de_raw <= 2.0:
            score -= 5
        else:
            score -= 15; reasons.append(f"High D/E {de_raw:.1f}x")

    # 3. Valuation label
    if any(x in val_text for x in ("undervalued", "deeply undervalued")):
        score += 12; reasons.append("Undervalued")
    elif any(x in val_text for x in ("fairly valued", "fair value", "reasonably")):
        score += 6; reasons.append("Fairly Valued")
    elif is_overvalued:
        score -= 15                               # rare — only reaches here if PEG < 1.0 overrode gate

    # 4. 52W timing window  (sweet spot: −5% to −25% below peak)
    if pct52w is not None:
        if -20.0 <= pct52w <= -5.0:
            score += 15; reasons.append(f"Sweet Timing ({pct52w:.1f}% off peak)")
        elif -35.0 <= pct52w < -20.0:
            score += 8;  reasons.append(f"Moderate Dip ({pct52w:.1f}% off peak)")
        elif pct52w < -35.0:
            score -= 5                            # too far down may be a falling knife

        # Bonus: also near 20D swing low support (within 4%)
        if swing_low20 is not None and last_price is not None and last_price > 0:
            pct_from_low = (last_price - swing_low20) / swing_low20 * 100
            if 0 <= pct_from_low <= 4.0:
                score += 5; reasons.append("Near 20D Support Floor")

    # 5. Institutional volume flow
    if ud_ratio is not None:
        if ud_ratio >= 1.5:
            score += 10; reasons.append(f"Strong Accumulation ({ud_ratio:.1f}x)")
        elif ud_ratio >= 1.1:
            score += 6;  reasons.append(f"Mild Accumulation ({ud_ratio:.1f}x)")
        elif ud_ratio <= 0.6:
            score -= 10; reasons.append(f"Distribution ({ud_ratio:.1f}x)")
        elif ud_ratio <= 0.85:
            score -= 4

    # 6. Long-term moat / verdict
    if "STRONG BUY" in lt_verdict or "STRONG HOLD" in lt_verdict:
        score += 10; reasons.append("LT: STRONG BUY")
    elif any(x in lt_verdict for x in ("BUY", "ACCUMULATE")):
        score += 5;  reasons.append(f"LT: {lt_verdict.split()[0]}")
    elif "SELL" in lt_verdict:
        score -= 10

    # 7. Liquidity coverage ratio
    if cr_raw is not None:
        if cr_raw >= 2.0:
            score += 5; reasons.append(f"Strong Liquidity (CR {cr_raw:.1f})")
        elif cr_raw >= 1.5:
            score += 3
        elif cr_raw < 1.0:
            score -= 5; reasons.append(f"Weak Liquidity (CR {cr_raw:.1f})")

    # 8. Catalyst bonus (earnings, results, order, deal)
    catalyst_keywords = ("result", "earnings", "order", "deal", "contract", "export", "win", "capex", "launch")
    if any(kw in upcoming_ev for kw in catalyst_keywords):
        score += 3; reasons.append("Near Catalyst")

    # Build timing reason tag (most informative single reason)
    timing_reason = _pick_primary_reason(reasons, pct52w, ud_ratio, val_text, swing_low20, last_price)

    return {
        "sym":          sym,
        "score":        score,
        "peg":          peg_raw,
        "valuation":    _capitalise(val_text) if val_text else "N/A",
        "pct52w":       round(pct52w, 1) if pct52w is not None else None,
        "ud_ratio":     ud_ratio,
        "lt_verdict":   lt_verdict or verdict,
        "lt_target":    sig.get("long_term_target") or sig.get("when_to_sell_target") or "N/A",
        "last_price":   last_price,
        "reasons":      reasons,
        "timing_tag":   timing_reason,
        "action":       verdict,
    }


def build_fundamental_picks_section(symbols_list: list, results_dict: dict, cache_mgr: Any) -> str:
    """
    Entry point called from main.py — builds the markdown section for the
    "Top 10 Fundamental Stocks: Right Time to Buy" block of the daily report.
    """
    scored = []

    for item in symbols_list:
        sym   = item.get("symbol", "").upper()
        cname = item.get("name", "")
        sec   = item.get("sector", "")

        # Resolve synthesizer output (same cascade as Quick Picks)
        synth_res = None
        if sym in results_dict:
            synth_res = results_dict[sym]["result"]
        if not synth_res and cache_mgr:
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=168)
        if not synth_res and cache_mgr:
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=None)
        if not synth_res:
            continue

        # Resolve technical output for 52W + flow signals
        tech_res = None
        if sym in results_dict:
            tech_res = results_dict[sym]["result"].get("agent_outputs", {}).get("technical")
        if not tech_res and cache_mgr:
            tech_res = cache_mgr.get_latest_agent_output(sym, "Technical Analysis Agent", max_age_hours=168)

        pick = score_fundamental_pick(sym, synth_res, tech_res)
        if pick is None:
            continue

        pick["cname"] = cname
        pick["sec"]   = sec
        scored.append(pick)

    if not scored:
        return (
            "\n## 🏛️ Top 10 Fundamental Picks — Right Time to Buy\n"
            "> No qualifying fundamentally-sound stocks found in the current universe.\n\n---\n"
        )

    # Rank by score descending, cap at 10
    scored.sort(key=lambda x: x["score"], reverse=True)
    top10 = scored[:10]

    lines = []
    lines.append("\n## 🏛️ Top 10 Fundamental Picks — Right Time to Buy")
    lines.append("> **For long-term wealth** — Fundamentally sound stocks at the right valuation & technical entry point.")
    lines.append("> Scored across 8 dimensions: PEG, Balance Sheet, Valuation, 52W Timing, Institutional Flow, LT Moat, Liquidity, Catalysts.\n")
    lines.append("| # | Symbol | Company | Sector | LTP | PEG | Valuation | % from 52W High | Inst. Flow | LT Rating | LT Target | Why Now | Action |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")

    for i, p in enumerate(top10, 1):
        peg_disp   = f"{p['peg']:.2f}x" if p['peg'] is not None else "N/A"
        pct52_disp = f"{p['pct52w']:.1f}%" if p['pct52w'] is not None else "N/A"
        ud_disp    = _ud_label(p['ud_ratio'])
        ltp_disp   = f"Rs. {p['last_price']:.0f}" if p['last_price'] else "N/A"
        lines.append(
            f"| {i} | **{p['sym']}** | {p['cname']} | {p['sec']} "
            f"| {ltp_disp} | {peg_disp} | {p['valuation']} "
            f"| {pct52_disp} | {ud_disp} | {p['lt_verdict']} "
            f"| {p['lt_target']} | {p['timing_tag']} | {p['action']} |"
        )

    lines.append("")
    lines.append("> [!TIP]")
    lines.append("> **How to use**: These are long-term compounders. Accumulate in tranches over 2–4 weeks.")
    lines.append("> Stocks scored highest on value *and* technical timing — the rare convergence of quality + right price.\n")
    lines.append("---\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(str(val).replace(",", "").strip())
        return f if f == f else None   # NaN check
    except (ValueError, TypeError):
        return None


def _capitalise(text: str) -> str:
    if not text:
        return text
    return text.strip().capitalize()


def _ud_label(ud: float | None) -> str:
    if ud is None:
        return "N/A"
    if ud >= 1.5:
        return f"Strong Accum. ({ud:.1f}x)"
    if ud >= 1.1:
        return f"Mild Accum. ({ud:.1f}x)"
    if ud <= 0.6:
        return f"Distribution ({ud:.1f}x)"
    if ud <= 0.85:
        return f"Mild Dist. ({ud:.1f}x)"
    return f"Neutral ({ud:.1f}x)"


def _pick_primary_reason(reasons, pct52w, ud_ratio, val_text, swing_low20, last_price) -> str:
    """Return the single most investor-relevant timing tag for the 'Why Now' column."""
    # Prioritise near support
    if swing_low20 is not None and last_price is not None and last_price > 0:
        pct_from_low = (last_price - swing_low20) / swing_low20 * 100
        if 0 <= pct_from_low <= 4.0:
            return "Near Support Floor"
    if pct52w is not None and -20.0 <= pct52w <= -5.0:
        return f"Attractive Dip ({pct52w:.1f}%)"
    if ud_ratio is not None and ud_ratio >= 1.25:
        return "Inst. Accumulation"
    if any(x in val_text for x in ("undervalued", "deeply")):
        return "Undervalued Entry"
    if pct52w is not None and pct52w < -20.0:
        return f"Deep Correction ({pct52w:.1f}%)"
    if reasons:
        return reasons[0]
    return "Multi-Factor Entry"
