"""
Macro Risk Shield
=================
Converts the existing macro sentiment score into an actionable,
multi-tier RISK LEVEL and generates portfolio protection playbook.

Risk levels:
  🟢 LOW       macro_score >= +0.15   → Markets supportive; stay invested.
  🟡 ELEVATED  macro_score in (-0.15, +0.15) → Neutral; monitor key levels.
  🟠 HIGH      macro_score in (-0.50, -0.15)  → Defensive rotation recommended.
  🔴 DANGER    macro_score <= -0.50   → Raise cash, tighten all stops urgently.

The shield also:
  - Identifies which sectors are most exposed to the current macro headwinds
  - Recommends defensive safe-haven sectors to rotate into
  - Generates per-holding protection actions (tighten SL, reduce size, hold, exit)
  - Flags scheduled upcoming macro risk events

All logic is deterministic — no LLM needed.
"""

from __future__ import annotations
import re
from typing import Any

from tools.macro_tools import BULLISH_THRESHOLD, BEARISH_THRESHOLD, DANGER_THRESHOLD


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RISK_LEVELS = {
    "LOW":         {"label": "🟢 LOW",         "colour": "#10b981", "action": "Stay Invested",                         "threshold_lo": BULLISH_THRESHOLD},
    "ELEVATED":    {"label": "🟡 ELEVATED",    "colour": "#f59e0b", "action": "Monitor & Partial Hedge",               "threshold_lo": BEARISH_THRESHOLD},
    "HIGH":        {"label": "🟠 HIGH",        "colour": "#f97316", "action": "Defensive Rotation",                    "threshold_lo": DANGER_THRESHOLD},
    "DANGER":      {"label": "🔴 DANGER",      "colour": "#ef4444", "action": "Raise Cash / Exit Risk",                "threshold_lo": -1.00},
    "UNAVAILABLE": {"label": "⚪ UNAVAILABLE", "colour": "#94a3b8", "action": "Macro Feed Unavailable — Hold & Monitor", "threshold_lo":  0.00},
}

# Sector sensitivity to common macro shocks
# (sector → risk_weight): higher = drops more in a macro shock
SECTOR_SENSITIVITY = {
    "Banking & Finance":    0.90,
    "Financial Services":   0.90,
    "Metals & Mining":      0.85,
    "Real Estate":          0.85,
    "Capital Goods":        0.80,
    "Automobiles":          0.75,
    "Consumer Discretionary": 0.75,
    "Oil & Gas":            0.70,
    "Infrastructure":       0.70,
    "Chemicals":            0.65,
    "Technology":           0.55,
    "IT Services":          0.50,
    "FMCG":                 0.20,   # defensive
    "Healthcare":           0.20,   # defensive
    "Pharma":               0.20,   # defensive
    "Utilities":            0.25,   # defensive
    "Defence":              0.35,
    "Telecom":              0.40,
}

# Defensive safe-haven sectors & why
DEFENSIVE_SECTORS = {
    "FMCG": "Staples — revenue barely drops in recession; people still buy soap & biscuits.",
    "Pharma / Healthcare": "Counter-cyclical — healthcare spending is non-discretionary.",
    "IT Exports (USD-earning)": "USD revenues benefit when INR weakens during risk-off episodes.",
    "Utilities": "Regulated revenues; dividend yield acts as cushion.",
    "Gold ETF (GOLDBEES / SGB)": "Classic safe haven; rallies when equities and INR fall.",
    "Defence PSUs": "Government capex-backed order books; insulated from private credit cycles.",
}

# Specific stocks known as defensives (for display only — no price/recommendation)
DEFENSIVE_EXAMPLES = {
    "FMCG":        ["HINDUNILVR", "ITC", "NESTLEIND", "DABUR"],
    "Pharma":      ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB"],
    "IT Exports":  ["INFY", "TCS", "WIPRO", "HCLTECH"],
    "Utilities":   ["NTPC", "POWERGRID", "CESC"],
    "Gold":        ["GOLDBEES (ETF)", "Sovereign Gold Bond"],
    "Defence":     ["BEL", "HAL", "MAZDOCK", "COCHINSHIP"],
}

# Scheduled macro event types (approximate calendar — user should check RBI/MPC calendar)
SCHEDULED_RISK_EVENTS = [
    {"event": "RBI MPC Policy Decision",           "frequency": "Bi-monthly",   "risk": "HIGH",     "impact": "INR, Banking, NBFCs"},
    {"event": "US Federal Reserve FOMC Meeting",   "frequency": "8× per year",  "risk": "HIGH",     "impact": "All sectors — FII flow"},
    {"event": "India Union Budget",                "frequency": "Annual (Feb)", "risk": "VERY HIGH","impact": "Capital Goods, Defence, Infra, PSUs"},
    {"event": "US CPI Inflation Data",             "frequency": "Monthly",      "risk": "ELEVATED", "impact": "Banking, NBFC, USD/INR"},
    {"event": "US Non-Farm Payrolls (NFP)",        "frequency": "Monthly",      "risk": "ELEVATED", "impact": "Global risk appetite, FII flow"},
    {"event": "India GDP / IIP Data",              "frequency": "Quarterly",    "risk": "ELEVATED", "impact": "Broad market"},
    {"event": "Oil Supply Shock (OPEC+ meetings)", "frequency": "Variable",     "risk": "HIGH",     "impact": "Airlines, Paints, Chemicals, Tyres"},
    {"event": "US Earnings Season (Big Tech)",     "frequency": "Quarterly",    "risk": "ELEVATED", "impact": "IT Services, ADR-listed Indian cos"},
    {"event": "China PMI / Economic Data",         "frequency": "Monthly",      "risk": "ELEVATED", "impact": "Metals, Chemicals, Export plays"},
]


# ---------------------------------------------------------------------------
# Core risk computation
# ---------------------------------------------------------------------------

def compute_risk_level(macro_score: float) -> dict:
    """
    Given a macro_score in [-1, +1] (from compute_macro_sentiment),
    return a full risk-level dict with label, colour, action, advice.
    Uses unified thresholds from tools.macro_tools.
    """
    if macro_score >= BULLISH_THRESHOLD:
        key = "LOW"
    elif macro_score >= BEARISH_THRESHOLD:
        key = "ELEVATED"
    elif macro_score >= DANGER_THRESHOLD:
        key = "HIGH"
    else:
        key = "DANGER"

    meta = RISK_LEVELS[key]
    score_pct = int(abs(macro_score) * 100)

    playbook = _build_playbook(key, macro_score)

    return {
        "risk_key":       key,
        "risk_label":     meta["label"],
        "risk_colour":    meta["colour"],
        "macro_score":    round(macro_score, 3),
        "action_header":  meta["action"],
        "playbook":       playbook,
        "defensive_sectors": list(DEFENSIVE_SECTORS.items()),
        "defensive_examples": DEFENSIVE_EXAMPLES,
        "scheduled_events":  SCHEDULED_RISK_EVENTS,
    }


def _build_playbook(key: str, score: float) -> list[dict]:
    """Return ordered list of protection steps for the given risk level."""
    if key == "LOW":
        return [
            {"step": 1, "icon": "✅", "action": "Stay Invested",
             "detail": "Macro tailwinds are supportive. Continue running your strategy. No defensive action needed."},
            {"step": 2, "icon": "📋", "action": "Review Stop-Losses Quarterly",
             "detail": "Use trailing stops (5–8% below highs) so profits are protected if sentiment turns."},
            {"step": 3, "icon": "💡", "action": "Pre-plan Your Exits",
             "detail": "Know at what price you would exit each holding. Write it down before emotion kicks in."},
        ]
    elif key == "ELEVATED":
        return [
            {"step": 1, "icon": "⚡", "action": "Tighten Trailing Stop-Losses",
             "detail": "Bring trailing stops from 8% to 5% below the recent high for all holdings. Protects gains."},
            {"step": 2, "icon": "⚖️",  "action": "Reduce Position in High-Sensitivity Sectors",
             "detail": "Trim 20–30% of positions in Banking, Metals, Real Estate. These fall hardest in a correction."},
            {"step": 3, "icon": "🏛️", "action": "Increase Defensive Exposure",
             "detail": "Rotate trimmed capital into FMCG, Pharma, or IT export stocks. These hold up better."},
            {"step": 4, "icon": "💰", "action": "Build a Cash Buffer (10–15%)",
             "detail": "Keep cash ready. A further drop is a buying opportunity — but only if you have cash on hand."},
        ]
    elif key == "HIGH":
        return [
            {"step": 1, "icon": "🛑", "action": "Trigger All Stop-Losses Immediately",
             "detail": "Any stock below its pre-defined stop-loss must be exited NOW. No exceptions, no hope-based holding."},
            {"step": 2, "icon": "✂️", "action": "Reduce Overall Equity Exposure by 30–40%",
             "detail": "Sell your highest-risk, highest-sensitivity positions first (cyclicals, leveraged names, small caps)."},
            {"step": 3, "icon": "🔄", "action": "Rotate to Defensive Sectors",
             "detail": "FMCG, Pharma, Utilities, and Gold. These are not just safe — they can outperform in risk-off."},
            {"step": 4, "icon": "🚫", "action": "No New Cyclical Positions",
             "detail": "Do not deploy fresh money into Banking, Auto, Metals, Real Estate until macro stabilises."},
            {"step": 5, "icon": "💰", "action": "Raise Cash to 20–30%",
             "detail": "Capital preservation is the priority. Cash earns nothing but loses nothing. Opportunity will return."},
        ]
    elif key == "DANGER":
        return [
            {"step": 1, "icon": "🚨", "action": "EXIT ALL STOP-LOSS BREACHED POSITIONS NOW",
             "detail": "Every position below its stop-loss must be closed immediately. Market gaps will get worse."},
            {"step": 2, "icon": "🏃", "action": "Raise Cash to 40–60%",
             "detail": "Severe macro headwind active. The priority is capital preservation, not returns."},
            {"step": 3, "icon": "⬇️",  "action": "Avoid Averaging Down",
             "detail": "Do NOT buy dips yet. Wait for macro score to improve to ELEVATED before re-entering."},
            {"step": 4, "icon": "🏅", "action": "Only Hold Gold / Defensive Quality",
             "detail": "GOLDBEES ETF, HINDUNILVR, SUNPHARMA type names. Even these may dip — but recover fastest."},
            {"step": 5, "icon": "📰", "action": "Watch the Key Reversal Signals",
             "detail": "Re-entry signal: US 10Y yield stabilises, DXY stops rising, FII flow turns net positive for 3 days."},
            {"step": 6, "icon": "🧘", "action": "Do Not Panic-Sell at the Bottom",
             "detail": "The worst sale is at the absolute bottom. Use staged re-entry once signals stabilise."},
        ]
    else:  # UNAVAILABLE
        return [
            {"step": 1, "icon": "⚪", "action": "Macro Feed Temporarily Unavailable",
             "detail": "Global macro telemetry is offline or incomplete; no macro-driven trims or cash-raising actions are triggered."},
            {"step": 2, "icon": "📋", "action": "Rely on Stock-Level Stops",
             "detail": "Continue enforcing individual technical stop-losses and fundamental risk rules until macro feeds recover."},
        ]


# ---------------------------------------------------------------------------
# Per-holding shield actions
# ---------------------------------------------------------------------------

def evaluate_holding_shield(holding: dict, risk_key: str) -> dict:
    """
    Given one holding from kite_portfolio and the current risk key,
    return a recommended protective action for that specific holding.

    holding dict expected keys: symbol, sector, pnl_pct, current_value, long_term_action
    """
    sym    = holding.get("symbol", "")
    sector = str(holding.get("sector", "Unknown"))
    pnl    = float(holding.get("pnl_pct", 0) or 0)
    lt_act = str(holding.get("long_term_action", "HOLD")).upper()

    sensitivity = _sector_sensitivity(sector)

    if risk_key == "UNAVAILABLE":
        shield_action = "⚪ HOLD — Macro feed unavailable; rely on stock-level stops."
        urgency = "none"

    elif risk_key == "LOW":
        shield_action = "🟢 HOLD — Macro supportive. Maintain position."
        urgency = "none"

    elif risk_key == "ELEVATED":
        if sensitivity >= 0.80:
            shield_action = f"🟡 TRIM 25% — {sector} is high-sensitivity. Book partial profit / reduce exposure."
            urgency = "medium"
        elif pnl < -8:
            shield_action = f"🟡 REVIEW SL — Stock is already {pnl:.1f}% in loss during elevated risk. Consider cutting."
            urgency = "medium"
        else:
            shield_action = "🟡 TIGHTEN SL — Move stop-loss to 5% below recent high. Keep monitoring."
            urgency = "low"

    elif risk_key == "HIGH":
        if sensitivity >= 0.80 or pnl < -5:
            shield_action = f"🟠 REDUCE 40% — {sector} highly exposed to macro shock. Protect capital."
            urgency = "high"
        elif sensitivity >= 0.60:
            shield_action = f"🟠 TRIM 20% — Moderate exposure sector. Reduce risk."
            urgency = "medium"
        elif sensitivity <= 0.30:
            shield_action = "🟠 HOLD — Defensive sector. Likely to outperform in correction."
            urgency = "none"
        else:
            shield_action = "🟠 TIGHTEN SL to 5% — Monitor daily."
            urgency = "medium"

    else:  # DANGER
        if sensitivity <= 0.25:
            shield_action = "🔴 HOLD (Defensive) — Safe haven. May dip but recovers fastest."
            urgency = "low"
        elif pnl < 0:
            shield_action = f"🔴 EXIT — Losing position in a DANGER macro environment. Cut loss now."
            urgency = "critical"
        elif sensitivity >= 0.60:
            shield_action = f"🔴 EXIT 50-60% — {sector} will be heavily sold in macro shock. Preserve gains."
            urgency = "critical"
        else:
            shield_action = "🔴 TRIM 30-40% — Raise cash. Re-enter when macro stabilises."
            urgency = "high"

    return {
        "symbol":        sym,
        "sector":        sector,
        "sensitivity":   round(sensitivity, 2),
        "pnl_pct":       round(pnl, 1),
        "shield_action": shield_action,
        "urgency":       urgency,
    }


_SECTOR_SENSITIVITY_RULES: list[tuple[re.Pattern, float]] = [
    # Defensives FIRST so compound labels like "Fast Moving Consumer Goods", "Healthcare & Pharmaceuticals",
    # "Consumer Defensive", and "FMCG & Agri" are never hijacked by "&" or "goods" or "consumer".
    (re.compile(r"\b(?:fmcg|fast moving consumer goods|consumer staples|consumer defensive|packaged foods?|beverages?|agri)\b", re.I), 0.20),
    (re.compile(r"\b(?:pharma|pharmaceuticals?|healthcare|hospitals?|diagnostics?)\b", re.I), 0.20),
    (re.compile(r"\b(?:utilities|power transmission|power generation)\b", re.I), 0.25),
    # High-beta / rate-sensitive financials & cyclicals
    (re.compile(r"\b(?:banking|bank|banks|nbfc|financial services|finance|housing finance|microfinance|capital markets|fintech|insurance)\b", re.I), 0.90),
    (re.compile(r"\b(?:metals?|mining|steel|aluminium|aluminum|copper|basic materials)\b", re.I), 0.85),
    (re.compile(r"\b(?:real estate|realty)\b", re.I), 0.85),
    (re.compile(r"\b(?:capital goods|electricals?|electrical equipment|machinery|industrials?|industrial engineering)\b", re.I), 0.80),
    (re.compile(r"\b(?:automobiles?|automotive|auto ancillar(?:y|ies)|auto components?|tyres?)\b", re.I), 0.75),
    (re.compile(r"\b(?:consumer discretionary|consumer cyclical|consumer durables|consumer services|retail|luxury|paints?)\b", re.I), 0.75),
    (re.compile(r"\b(?:oil|gas|petroleum|energy|refining)\b", re.I), 0.70),
    (re.compile(r"\b(?:infrastructure|infra|construction|ports?|airports?|logistics|cement|building materials)\b", re.I), 0.70),
    (re.compile(r"\b(?:chemicals?|specialty chemicals?|agro\s*chemicals?|fertilizers?)\b", re.I), 0.65),
    (re.compile(r"\b(?:defence|defense|aerospace|shipbuilding|maritime)\b", re.I), 0.60),
    (re.compile(r"\b(?:semiconductors?|electronics?)\b", re.I), 0.60),
    (re.compile(r"\b(?:information technology|it services|it|software|technology|cpaas)\b", re.I), 0.50),
    (re.compile(r"\b(?:telecom|telecommunications?|media|entertainment)\b", re.I), 0.40),
]


def _sector_sensitivity(sector: str) -> float:
    """Return sector sensitivity score (0–1) using word-boundary rules (never matches '&')."""
    if not sector:
        return 0.55
    for pat, weight in _SECTOR_SENSITIVITY_RULES:
        if pat.search(sector):
            return weight
    return 0.55   # default: moderate


# ---------------------------------------------------------------------------
# Full shield report (for API and report generation)
# ---------------------------------------------------------------------------

def build_macro_risk_shield(macro_result: dict, holdings: list[dict] | None = None) -> dict:
    """
    Master entry point. Given macro_result from compute_macro_sentiment()
    and optional holdings list from KitePortfolioEngine, returns the
    full shield analysis.
    """
    available = macro_result.get("available")
    score = float(macro_result.get("score", 0.0) or 0.0)
    if available is False:
        meta = RISK_LEVELS["UNAVAILABLE"]
        risk = {
            "risk_key":          "UNAVAILABLE",
            "risk_label":        meta["label"],
            "risk_colour":       meta["colour"],
            "macro_score":       round(score, 3),
            "action_header":     meta["action"],
            "playbook":          _build_playbook("UNAVAILABLE", score),
            "defensive_sectors": list(DEFENSIVE_SECTORS.items()),
            "defensive_examples": DEFENSIVE_EXAMPLES,
            "scheduled_events":  SCHEDULED_RISK_EVENTS,
        }
    else:
        risk = compute_risk_level(score)

    # Per-holding shield actions
    holding_shields = []
    if holdings:
        for h in holdings:
            sh = evaluate_holding_shield(h, risk["risk_key"])
            holding_shields.append(sh)
        # Sort: critical first
        urgency_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4}
        holding_shields.sort(key=lambda x: urgency_order.get(x["urgency"], 5))

    risk["holding_shields"] = holding_shields
    risk["macro_drivers"]   = macro_result.get("drivers", [])
    risk["macro_label"]     = macro_result.get("label", "Neutral")
    risk["macro_available"] = macro_result.get("available", False)

    return risk


def build_macro_risk_shield_markdown(risk_data: dict) -> str:
    """Generate a markdown section for the daily report."""
    lines = []
    lines.append(f"\n## {risk_data['risk_label']} Macro Risk Shield — Portfolio Protection Playbook")
    lines.append(f"> **Global Macro Score**: {risk_data['macro_score']:+.2f} | "
                 f"**Sentiment**: {risk_data['macro_label']} | "
                 f"**Recommended Action**: {risk_data['action_header']}\n")

    if risk_data.get("macro_drivers"):
        lines.append("**Key Macro Drivers Today:**")
        for d in risk_data["macro_drivers"]:
            lines.append(f"- {d}")
        lines.append("")

    lines.append("### 🛡️ Protection Playbook")
    for step in risk_data.get("playbook", []):
        lines.append(f"**Step {step['step']}** {step['icon']} **{step['action']}**")
        lines.append(f"> {step['detail']}\n")

    lines.append("### 🏛️ Safe-Haven Sectors to Rotate Into")
    lines.append("| Sector | Why It Holds Up |")
    lines.append("|---|---|")
    for sec, why in risk_data.get("defensive_sectors", []):
        lines.append(f"| {sec} | {why} |")

    lines.append("")
    lines.append("### 📅 High-Risk Scheduled Events to Watch")
    lines.append("| Event | Frequency | Risk Level | Sectors Affected |")
    lines.append("|---|---|---|---|")
    for ev in risk_data.get("scheduled_events", []):
        lines.append(f"| {ev['event']} | {ev['frequency']} | {ev['risk']} | {ev['impact']} |")

    if risk_data.get("holding_shields"):
        lines.append("")
        lines.append("### 💼 Portfolio Shield Actions (Your Holdings)")
        lines.append("| Symbol | Sector | Sensitivity | P&L% | Recommended Action |")
        lines.append("|---|---|---|---|---|")
        for h in risk_data["holding_shields"]:
            lines.append(f"| **{h['symbol']}** | {h['sector']} | {h['sensitivity']:.0%} "
                         f"| {h['pnl_pct']:+.1f}% | {h['shield_action']} |")

    lines.append("")
    lines.append("> [!WARNING]")
    lines.append("> This is an advisory system only. No action is taken automatically.")
    lines.append("> All stop-loss and exit decisions must be executed by you in your broker platform.\n")
    lines.append("---\n")

    return "\n".join(lines)
