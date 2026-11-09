"""
Master Prediction Synthesizer Agent (deterministic -- no LLM).

Combines chart patterns, trend (SMA 50/200), momentum (RSI), news sentiment, global macro backdrop,
fundamental valuation and 30-day price history into ONE weighted evidence score in [-1, +1], then maps it to a
verdict, confidence, entry range, target, stop loss and a templated rationale.

Design rules:
  * Inputs that are missing (no news, macro feed down, fundamentals unavailable, ...) are EXCLUDED from the
    score -- never replaced with invented defaults. Coverage is reported alongside the verdict.
  * Target / stop / entry are always directionally consistent with the verdict (BUY: target > price > stop).
  * Confidence is a rule-based measure of signal agreement and data coverage. It is NOT a calibrated
    probability of the trade working out.
"""

import math
from typing import Dict, Any, List, Optional, Tuple

from storage.cache_manager import CacheManager

# --------------------------------------------------------------------------------------------------
# Tunable model parameters (single place, documented)
# --------------------------------------------------------------------------------------------------
EVIDENCE_WEIGHTS = {
    "pattern": 3.0,      # confirmed chart pattern direction x quality score
    "trend": 2.0,        # price vs SMA-50 and SMA-200
    "momentum": 1.0,     # RSI-14 regime
    "news": 1.0,         # net headline sentiment
    "macro": 1.0,        # global backdrop for Indian equities
    "fundamental": 1.0,  # P/E valuation label + ROE
    "historical": 0.5,   # 30-day price momentum
}
BUY_THRESHOLD = 0.45
ACCUMULATE_THRESHOLD = 0.20
SELL_THRESHOLD = -0.30
DEFENSIVE_HOLD_THRESHOLD = -0.10   # HOLD below this (or with a bearish pattern) is "no fresh entry"
SIGNIFICANT_SIGNAL = 0.15          # |value| needed to count a signal as agreeing / disagreeing
MIN_SUPPORT_POINTS = 2             # a BUY/ACCUMULATE/SELL call needs this many supporting points
STRONG_PATTERN_QUALITY = 0.80      # a pattern this strong (quality >= 80/100) counts as two supporting points
MAX_CONFIDENCE = 92
TOTAL_WEIGHT = sum(EVIDENCE_WEIGHTS.values())


def _to_float(value) -> Optional[float]:
    """Finite float or None (handles None, 'N/A', NaN, strings with commas)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        f = float(str(value).replace(",", "")) if isinstance(value, str) else float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# --------------------------------------------------------------------------------------------------
# Evidence scoring
# --------------------------------------------------------------------------------------------------
def _pattern_signal(top_pattern: Optional[dict]) -> Tuple[float, str]:
    if not top_pattern:
        return 0.0, "no confirmed chart pattern"
    name = top_pattern.get("name", "pattern")
    direction = top_pattern.get("direction", "Neutral")
    quality = _to_float(top_pattern.get("quality_score"))
    quality = _clamp((quality if quality is not None else 70.0) / 100.0, 0.0, 1.0)
    if direction == "Bullish":
        return quality, f"bullish {name} ({quality * 100:.0f}/100)"
    if direction == "Bearish":
        return -quality, f"bearish {name} ({quality * 100:.0f}/100)"
    return 0.0, f"neutral {name}"


def _trend_signal(lp: float, sma50: Optional[float], sma200: Optional[float]) -> Optional[Tuple[float, str]]:
    parts = []
    if sma50 is not None and sma50 > 0:
        parts.append(("SMA-50", 1.0 if lp > sma50 else -1.0))
    if sma200 is not None and sma200 > 0:
        parts.append(("SMA-200", 1.0 if lp > sma200 else -1.0))
    if not parts:
        return None
    value = sum(v for _, v in parts) / len(parts)
    above = [n for n, v in parts if v > 0]
    below = [n for n, v in parts if v < 0]
    text = []
    if above:
        text.append("above " + "/".join(above))
    if below:
        text.append("below " + "/".join(below))
    return value, "price " + " and ".join(text)


def _momentum_signal(rsi: Optional[float]) -> Optional[Tuple[float, str]]:
    if rsi is None:
        return None
    if rsi < 30:
        return 0.5, f"RSI {rsi:.0f} oversold (reversal setup)"
    if rsi < 45:
        return 0.0, f"RSI {rsi:.0f} soft momentum"
    if rsi <= 65:
        return 0.3, f"RSI {rsi:.0f} healthy momentum"
    if rsi <= 70:
        return 0.0, f"RSI {rsi:.0f} stretched"
    return -0.5, f"RSI {rsi:.0f} overbought"


def _news_signal(news: Optional[dict]) -> Optional[Tuple[float, str]]:
    if not news:
        return None
    total = int(news.get("total") or 0)
    if total <= 0:
        return None
    bull, bear = int(news.get("bullish") or 0), int(news.get("bearish") or 0)
    net = (bull - bear) / total
    # Few headlines are weak evidence: full weight only from 3 headlines up
    value = _clamp(net * min(1.0, total / 3.0))
    return value, f"news {bull} bullish vs {bear} bearish of {total}"


def _macro_signal(macro: Optional[dict]) -> Optional[Tuple[float, str]]:
    if not macro or not macro.get("available"):
        return None
    score = _to_float(macro.get("score"))
    if score is None:
        return None
    return _clamp(score), f"macro backdrop {macro.get('label', 'Neutral')} ({score:+.2f})"


def _fundamental_signal(fund: Optional[dict]) -> Optional[Tuple[float, str]]:
    if not fund or not fund.get("available", False):
        return None
    val = str(fund.get("valuation_assessment", ""))
    value, notes = 0.0, []
    if val.startswith("Undervalued"):
        value += 0.6
        notes.append("undervalued on P/E")
    elif val.startswith("High Growth"):
        value -= 0.3
        notes.append("premium P/E")
    elif val.startswith("Fairly"):
        notes.append("fair P/E")
    roe = _to_float(fund.get("roe_pct"))
    if roe is not None:
        if roe >= 15:
            value += 0.2
            notes.append(f"ROE {roe:.0f}%")
        elif roe < 8:
            value -= 0.2
            notes.append(f"weak ROE {roe:.0f}%")
    if not notes:
        return None
    return _clamp(value), "valuation: " + ", ".join(notes)


def _historical_signal(hist: Optional[dict]) -> Optional[Tuple[float, str]]:
    ret30 = _to_float((hist or {}).get("pct_change_30d"))
    if ret30 is None:
        return None
    return _clamp(ret30 / 10.0, -0.5, 0.5), f"30-day return {ret30:+.1f}%"


def score_evidence(
    lp: float,
    raw_tech: dict,
    top_pattern: Optional[dict],
    context: Optional[dict] = None,
) -> Dict[str, Any]:
    """Weighted evidence score. Returns score, per-signal breakdown, agreement and coverage."""
    ctx = context or {}
    signals: Dict[str, Optional[Tuple[float, str]]] = {
        "pattern": _pattern_signal(top_pattern),
        "trend": _trend_signal(lp, _to_float(raw_tech.get("sma_50")), _to_float(raw_tech.get("sma_200"))),
        "momentum": _momentum_signal(_to_float(raw_tech.get("rsi_14"))),
        "news": _news_signal(ctx.get("news")),
        "macro": _macro_signal(ctx.get("macro")),
        "fundamental": _fundamental_signal(ctx.get("fundamental")),
        "historical": _historical_signal(ctx.get("historical")),
    }

    breakdown: List[Dict[str, Any]] = []
    weighted_sum = 0.0
    used_weight = 0.0
    for name, sig in signals.items():
        if sig is None:
            continue
        value, note = sig
        weight = EVIDENCE_WEIGHTS[name]
        weighted_sum += value * weight
        used_weight += weight
        breakdown.append({"signal": name, "value": round(value, 3), "weight": weight, "note": note})

    score = round(weighted_sum / used_weight, 3) if used_weight > 0 else 0.0
    coverage = used_weight / TOTAL_WEIGHT

    sign = 1 if score > 0 else -1 if score < 0 else 0
    significant = [b for b in breakdown if abs(b["value"]) >= SIGNIFICANT_SIGNAL]
    agreeing = [b for b in significant if sign != 0 and (b["value"] > 0) == (sign > 0)]
    agreement = (len(agreeing) / len(significant)) if (significant and sign != 0) else 0.0
    # One point per agreeing signal; a strong confirmed chart pattern is worth two on its own
    support_points = len(agreeing) + sum(
        1 for b in agreeing if b["signal"] == "pattern" and abs(b["value"]) >= STRONG_PATTERN_QUALITY
    )

    # Confidence: conviction (|score|), breadth of agreement and data coverage. Rule-based, not a probability.
    conf_pct = int(round(40 + 35 * min(1.0, abs(score) / 0.6) + 15 * agreement + 10 * coverage))
    conf_pct = max(0, min(MAX_CONFIDENCE, conf_pct))

    return {
        "score": score,
        "breakdown": breakdown,
        "agreeing": len(agreeing),
        "support_points": support_points,
        "significant": len(significant),
        "coverage": round(coverage, 3),
        "confidence_pct": conf_pct,
    }


def _explain_evidence(ev: Dict[str, Any], verdict: str) -> str:
    """Deterministic one-sentence explanation: strongest supporting signals plus the main contrary signal."""
    ranked = sorted(ev["breakdown"], key=lambda b: abs(b["value"] * b["weight"]), reverse=True)
    if not ranked:
        return f"Evidence score {ev['score']:+.2f}: limited evidence available."
    if verdict == "HOLD":
        drivers = "; ".join(b["note"] for b in ranked[:3])
        return f"Evidence score {ev['score']:+.2f} (mixed or weak signals): {drivers}."
    bullish_call = verdict in ("BUY", "ACCUMULATE")
    supports = [b for b in ranked if (b["value"] > 0) == bullish_call and abs(b["value"]) >= SIGNIFICANT_SIGNAL][:3]
    caveats = [b for b in ranked if (b["value"] > 0) != bullish_call and abs(b["value"]) >= SIGNIFICANT_SIGNAL][:1]
    text = f"Evidence score {ev['score']:+.2f} ({ev['agreeing']}/{ev['significant']} signals agree): " + "; ".join(b["note"] for b in supports)
    if caveats:
        text += f". Caveat: {caveats[0]['note']}"
    return text + "."


def _confidence_label(pct: int) -> str:
    if pct >= 75:
        return f"HIGH ({pct}%)"
    if pct >= 55:
        return f"MEDIUM ({pct}%)"
    return f"LOW ({pct}%)"


def _verdict_from_score(score: float) -> str:
    if score >= BUY_THRESHOLD:
        return "BUY"
    if score >= ACCUMULATE_THRESHOLD:
        return "ACCUMULATE"
    if score <= SELL_THRESHOLD:
        return "SELL"
    return "HOLD"


class MasterPredictionSynthesizerAgent:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()

    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _insufficient_data_signal(symbol: str, company_name: str) -> dict:
        from tools.long_term_strategy import long_term_engine
        lt_eval = long_term_engine.evaluate_long_term_stock(symbol, company_name, last_price=None, short_verdict="HOLD")
        return {
            "action_verdict": "HOLD",
            "confidence_rating": "LOW (0%)",
            "confidence_percentage": 0,
            "when_to_buy_entry": "N/A",
            "when_to_sell_target": "N/A",
            "short_term_target": "N/A",
            "short_term_horizon": "N/A",
            "stop_loss": "N/A",
            "holding_horizon": "N/A",
            "long_term_signal": lt_eval,
            "long_term_target": lt_eval["long_term_target"],
            "long_term_verdict": lt_eval["long_term_verdict"],
            "long_term_horizon": lt_eval["long_term_horizon"],
            "suggested_long_term_peers": lt_eval["suggested_long_term_peers"],
            "chart_patterns": "N/A",
            "upcoming_events_note": "",
            "key_rationale": f"No reliable price history is available for {symbol}, so no trading levels are produced.",
            "actionable_recommendation": "Wait for price data to load, then re-run the analysis.",
            "evidence_score": 0.0,
            "evidence_breakdown": [],
            "data_coverage_pct": 0,
        }

    @staticmethod
    def compute_quantitative_verdict(
        symbol: str,
        company_name: str,
        last_price: Any,
        raw_tech: dict,
        raw_risk: dict,
        detected_patterns: list,
        events_data: dict,
        context: Optional[dict] = None,
    ) -> dict:
        """
        Deterministic verdict engine (sub-millisecond). `context` optionally carries
        {"news": {...}, "macro": {...}, "fundamental": {...}, "historical": {...}} from the other agents.
        """
        raw_tech = raw_tech or {}
        raw_risk = raw_risk or {}
        lp = _to_float(last_price)
        if lp is None:
            lp = _to_float(raw_tech.get("last_price"))
        if lp is None or lp <= 0:
            return MasterPredictionSynthesizerAgent._insufficient_data_signal(symbol, company_name)

        # Risk-tool bounds (volatility based). Only used when directionally valid for the verdict.
        risk_tp = _to_float(raw_risk.get("suggested_target_price"))
        risk_sl = _to_float(raw_risk.get("suggested_stop_loss"))
        suggested_tp = round(risk_tp, 2) if (risk_tp is not None and risk_tp > lp) else round(lp * 1.08, 2)
        suggested_sl = round(risk_sl, 2) if (risk_sl is not None and 0 < risk_sl < lp) else round(lp * 0.95, 2)

        top_pattern = detected_patterns[0] if detected_patterns else None
        p_name = top_pattern.get("name", "Consolidation Range") if top_pattern else "Consolidation Range"
        p_dir = top_pattern.get("direction", "Neutral") if top_pattern else "Neutral"

        raw_p_target = _to_float(top_pattern.get("target_price")) if top_pattern else None
        raw_p_sl = _to_float(top_pattern.get("stop_loss")) if top_pattern else None
        raw_p_entry = _to_float(top_pattern.get("entry_trigger")) if top_pattern else None

        earnings_date = (events_data or {}).get("earnings_date")
        earnings_str = f"Next results: {earnings_date}" if earnings_date else ""
        earnings_clause = f" {earnings_str}." if earnings_str else ""

        # Step 1: weighted evidence -> verdict + confidence
        ev = score_evidence(lp, raw_tech, top_pattern, context)
        verdict = _verdict_from_score(ev["score"])
        if verdict != "HOLD" and ev["support_points"] < MIN_SUPPORT_POINTS:
            verdict = "HOLD"   # a single weak signal (e.g. trend alone) is not enough to act on
        conf_pct = ev["confidence_pct"]
        conf = _confidence_label(conf_pct)

        basis = _explain_evidence(ev, verdict)

        # Step 2: levels strictly aligned with the verdict
        if verdict in ("BUY", "ACCUMULATE"):
            # Bullish: target MUST be above price, stop MUST be below price
            if raw_p_target and lp < raw_p_target <= lp * 1.6:
                target = round(raw_p_target, 2)
            else:
                target = suggested_tp
            if raw_p_sl and lp * 0.75 <= raw_p_sl < lp:
                sl = round(raw_p_sl, 2)
            else:
                sl = suggested_sl

            # Tight, realistic entry range near current market price
            if raw_p_entry and 0.95 * lp <= raw_p_entry <= 1.04 * lp:
                if raw_p_entry > lp:
                    entry_floor = round(lp * 0.99, 2)
                    entry_ceiling = round(raw_p_entry * 1.01, 2)
                else:
                    entry_floor = round(max(raw_p_entry * 0.99, lp * 0.98), 2)
                    entry_ceiling = round(lp * 1.015, 2)
            else:
                entry_floor = round(lp * 0.985, 2)
                entry_ceiling = round(lp * 1.015, 2)

            # Entry ceiling must never reach the target; floor strictly below ceiling
            entry_ceiling = min(entry_ceiling, round(target * 0.96, 2))
            entry_floor = min(entry_floor, round(entry_ceiling * 0.985, 2))
            entry = f"Rs. {entry_floor:.2f} - {entry_ceiling:.2f}"

            rationale = f"{verdict} bias for {symbol}. {basis} Upside target near Rs. {target}.{earnings_clause}"
            action = f"Initiate position in {entry} range targeting Rs. {target} with risk stop at Rs. {sl}."

        elif verdict == "SELL":
            # Bearish: target is downside support (below price), stop is above price
            if raw_p_target and lp * 0.5 <= raw_p_target < lp:
                target = round(raw_p_target, 2)
            else:
                target = round(lp * 0.92, 2)
            sl = round(raw_p_sl, 2) if (raw_p_sl and raw_p_sl > lp) else round(lp * 1.05, 2)

            entry = "Defensive / Avoid fresh entry"
            rationale = f"SELL bias for {symbol}. {basis} Downside target near Rs. {target}.{earnings_clause}"
            action = f"Protect capital: maintain strict trailing stop at Rs. {sl}. Avoid fresh long positions until reversal is confirmed."

        else:
            if p_dir == "Bearish" or ev["score"] <= DEFENSIVE_HOLD_THRESHOLD:
                target = round(lp * 0.94, 2)
                sl = round(lp * 1.04, 2)
                entry = "Hold existing / No fresh entry"
                rationale = f"HOLD (defensive) for {symbol}. {basis}{earnings_clause}"
                action = f"Hold existing exposure with trailing stop at Rs. {sl}. Wait for a clear directional breakout before fresh allocation."
            else:
                target = suggested_tp
                sl = suggested_sl
                entry_ceiling = min(round(lp * 1.015, 2), round(target * 0.96, 2))
                entry_floor = min(round(lp * 0.98, 2), round(entry_ceiling * 0.985, 2))
                entry = f"Rs. {entry_floor:.2f} - {entry_ceiling:.2f}"
                rationale = f"HOLD (range-bound) for {symbol}. {basis}{earnings_clause}"
                action = f"Accumulate on dips in {entry} with protective stop loss at Rs. {sl} targeting Rs. {target}."

        from tools.long_term_strategy import long_term_engine
        lt_eval = long_term_engine.evaluate_long_term_stock(symbol, company_name, last_price=lp, short_verdict=verdict)

        return {
            "action_verdict": verdict,
            "confidence_rating": conf,
            "confidence_percentage": conf_pct,
            "when_to_buy_entry": entry,
            "when_to_sell_target": f"Rs. {target}",
            "short_term_target": f"Rs. {target}",
            "short_term_horizon": "1-3 Weeks (Swing/Momentum)",
            "stop_loss": f"Rs. {sl}",
            "holding_horizon": "Medium-Term (1-3 Months)" if verdict in ("BUY", "ACCUMULATE") else "Short-Term (1-3 Weeks)",
            "long_term_signal": lt_eval,
            "long_term_target": lt_eval["long_term_target"],
            "long_term_verdict": lt_eval["long_term_verdict"],
            "long_term_horizon": lt_eval["long_term_horizon"],
            "suggested_long_term_peers": lt_eval["suggested_long_term_peers"],
            "chart_patterns": p_name,
            "upcoming_events_note": earnings_str,
            "key_rationale": rationale,
            "actionable_recommendation": action,
            "evidence_score": ev["score"],
            "evidence_breakdown": ev["breakdown"],
            "data_coverage_pct": round(ev["coverage"] * 100),
        }

    # ----------------------------------------------------------------------------------------------
    @staticmethod
    def _news_context(news_out: dict) -> Optional[dict]:
        if not news_out:
            return None
        if news_out.get("news_score"):
            return news_out["news_score"]
        items = news_out.get("news_items") or []   # outputs saved before news_score existed
        if not items:
            return None
        bull = sum(1 for i in items if "Bullish" in (i.get("sentiment_label") or ""))
        bear = sum(1 for i in items if "Bearish" in (i.get("sentiment_label") or ""))
        return {"bullish": bull, "bearish": bear, "total": len(items)}

    def run(self, symbol: str, company_name: str, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        raw_tech = agent_outputs.get("technical", {}).get("raw_indicators", {})
        raw_risk = agent_outputs.get("risk", {}).get("raw_risk", {})
        raw_hist = agent_outputs.get("historical_rag", {}).get("raw_stats", {})
        events_data = agent_outputs.get("fundamental", {}).get("upcoming_events", {})
        detected_patterns = agent_outputs.get("technical", {}).get("detected_patterns") or raw_tech.get("detected_patterns", [])

        last_price = _to_float(raw_tech.get("last_price")) or _to_float(raw_risk.get("last_price")) or _to_float(raw_hist.get("last_close"))
        if last_price is None:
            candles = self.cache_manager.get_cached_candles(symbol, limit_days=1)
            if candles:
                last_price = _to_float(candles[-1].get("CLOSE_PRICE"))
        if last_price is not None:
            last_price = round(last_price, 2)

        context = {
            "news": self._news_context(agent_outputs.get("news_sentiment", {})),
            "macro": agent_outputs.get("macro", {}).get("macro_sentiment"),
            "fundamental": agent_outputs.get("fundamental", {}).get("raw_fundamentals"),
            "historical": raw_hist,
        }

        parsed = self.compute_quantitative_verdict(
            symbol, company_name, last_price, raw_tech, raw_risk, detected_patterns, events_data, context
        )

        # Format patterns / events summaries for the report
        if detected_patterns:
            patterns_text = "; ".join([
                f"{p['name']} [Score: {p.get('quality_score', 'N/A')}/100, Target: Rs.{p.get('target_price', 'N/A')}, Stop: Rs.{p.get('stop_loss', 'N/A')}]: {p.get('description', '')}"
                for p in detected_patterns[:3]
            ])
        else:
            patterns_text = "No strong reversal/continuation pattern confirmed. Trading in standard range."

        if events_data and (events_data.get("earnings_date") or events_data.get("dividend_ex_date")):
            events_text = (
                f"Next Earnings: {events_data.get('earnings_date') or 'TBD'} ({events_data.get('earnings_quarter') or 'n/a'}) | "
                f"Dividend: {events_data.get('dividend_amount') or 'N/A'} (Ex: {events_data.get('dividend_ex_date') or 'N/A'}) | "
                f"Impact: {events_data.get('impact') or 'Normal'}"
            )
        else:
            events_text = "No upcoming corporate event data available."

        # Long-term evaluation
        lt = parsed.get("long_term_signal", {})
        lt_verdict = lt.get("long_term_verdict", "HOLD")
        lt_horizon = lt.get("long_term_horizon", "1-3 Years")
        lt_target = lt.get("long_term_target", "N/A")
        lt_upside = lt.get("long_term_upside_pct") or "N/A"
        lt_moat = lt.get("long_term_moat", "N/A")
        lt_thesis = lt.get("long_term_thesis", "")
        lt_peers = lt.get("suggested_long_term_peers", [])
        lt_peers_str = ", ".join(lt_peers) if lt_peers else "N/A"

        entry_display = parsed.get("when_to_buy_entry", "N/A")
        target_display = parsed.get("when_to_sell_target", "N/A")
        sl_display = parsed.get("stop_loss", "N/A")

        # Reward-to-risk (short-term), long-biased verdicts only
        rr_ratio, upside_pct_st = "N/A", "N/A"
        tgt = _to_float(str(target_display).replace("Rs.", "").strip())
        stp = _to_float(str(sl_display).replace("Rs.", "").strip())
        if last_price and tgt is not None and stp is not None:
            risk_amt = last_price - stp
            reward_amt = tgt - last_price
            if risk_amt > 0 and reward_amt > 0:
                rr_ratio = f"{reward_amt / risk_amt:.1f}x"
            upside_pct_st = f"{(tgt - last_price) / last_price * 100:+.1f}%"

        report_text = f"""### 🎯 SHORT-TERM VERDICT: {parsed.get('action_verdict', 'HOLD')} | Confidence: {parsed.get('confidence_rating', 'LOW (0%)')}
| Field | Details |
|---|---|
| **Entry Range** | {entry_display} |
| **Target Price** | {target_display} |
| **Stop Loss** | {sl_display} |
| **Upside Potential** | {upside_pct_st} |
| **Reward : Risk** | {rr_ratio} |
| **Holding Horizon** | {parsed.get('holding_horizon', 'Short-Term (1-3 Weeks)')} |
| **Chart Patterns** | {parsed.get('chart_patterns') or patterns_text} |
| **Upcoming Events** | {parsed.get('upcoming_events_note') or events_text} |
| **Data Coverage** | {parsed.get('data_coverage_pct', 0)}% of evidence inputs available |

**📌 Key Rationale**: {parsed.get('key_rationale', '')}
**⚡ Action Plan**: {parsed.get('actionable_recommendation', '')}
*Confidence is a rule-based measure of signal agreement and data coverage, not a calibrated probability.*

---
### 📈 LONG-TERM OUTLOOK ({lt_horizon})
| Field | Details |
|---|---|
| **Long-Term Signal** | {lt_verdict} |
| **Long-Term Target** | {lt_target} |
| **Expected Upside** | {lt_upside} |
| **Competitive Moat** | {lt_moat} |
| **Sector Peers** | {lt_peers_str} |

**💡 Investment Thesis**: {lt_thesis}
"""

        return {
            "agent_name": "Master Prediction Synthesizer Agent",
            "symbol": symbol,
            "last_price": last_price if last_price is not None else "N/A",
            "structured_signal": parsed,
            "final_report": report_text,
            "detected_patterns": detected_patterns,
            "upcoming_events": events_data
        }
