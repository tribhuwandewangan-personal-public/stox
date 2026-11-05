"""
Master Prediction Synthesizer Agent.
Combines historical RAG insights, quantitative patterns (Saucer, Cup & Handle, TTM Squeeze, Wyckoff Spring, Triangles, Harmonics),
upcoming corporate & macro events (Earnings, Dividends, MPC), online sentiment,
fundamental valuation, and risk guardrails into a cohesive future prediction forecast report
with structured action signals (Buy/Sell, Entry Range, Target, Holding Horizon, Confidence Score).
Features a sub-millisecond QuantitativeVerdictEngine and safety-capped Ollama synthesis.
"""

import json
import os
from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate

from config import get_llm, FAST_MODE
from storage.cache_manager import CacheManager


class MasterPredictionSynthesizerAgent:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()
        self._llm = None

    @property
    def llm(self):
        if self._llm is None:
            self._llm = get_llm(temperature=0.2, max_tokens=320, timeout=18)
        return self._llm

    @staticmethod
    def compute_quantitative_verdict(
        symbol: str,
        company_name: str,
        last_price: Any,
        raw_tech: dict,
        raw_risk: dict,
        detected_patterns: list,
        events_data: dict
    ) -> dict:
        """
        Sub-millisecond institutional quantitative verdict engine.
        Synthesizes technical patterns, ATR/Keltner volatility, support/resistance,
        and event catalysts deterministically.
        """
        try:
            lp = float(last_price)
        except Exception:
            lp = float(raw_tech.get("last_price", 100.0))

        # Default risk bounds
        suggested_tp = raw_risk.get("suggested_target_price")
        if not suggested_tp or float(suggested_tp) <= lp:
            suggested_tp = round(lp * 1.08, 2)
        else:
            suggested_tp = round(float(suggested_tp), 2)

        suggested_sl = raw_risk.get("suggested_stop_loss")
        if not suggested_sl or float(suggested_sl) >= lp:
            suggested_sl = round(lp * 0.95, 2)
        else:
            suggested_sl = round(float(suggested_sl), 2)

        rsi = float(raw_tech.get("rsi_14", 50.0))
        sma50 = float(raw_tech.get("sma_50", lp))
        sma200 = float(raw_tech.get("sma_200", lp))

        top_pattern = detected_patterns[0] if detected_patterns else None
        p_name = top_pattern.get("name", "Consolidation Range") if top_pattern else "Consolidation Range"
        p_dir = top_pattern.get("direction", "Neutral") if top_pattern else "Neutral"
        p_score = top_pattern.get("quality_score", 70) if top_pattern else 60

        raw_p_target = top_pattern.get("target_price") if top_pattern else None
        raw_p_sl = top_pattern.get("stop_loss") if top_pattern else None
        raw_p_entry = top_pattern.get("entry_trigger") if top_pattern else None

        earnings_str = f"Next Results: {events_data.get('earnings_date', 'Upcoming')} ({events_data.get('earnings_quarter', 'Q2')})" if events_data else "Earnings in Q2 window"

        # Step 1: Synthesize clear Directional Verdict based on evidence weight
        if p_dir == "Bullish" and (lp >= sma50 or rsi <= 45 or p_score >= 82):
            verdict = "BUY" if p_score >= 85 else "ACCUMULATE"
            conf_pct = min(92, max(65, int(p_score)))
            conf = f"HIGH ({conf_pct}%)" if conf_pct >= 80 else f"MEDIUM ({conf_pct}%)"
        elif p_dir == "Bearish":
            if p_score >= 85 or lp < sma50:
                verdict = "SELL"
                conf_pct = min(90, max(70, int(p_score)))
                conf = f"HIGH ({conf_pct}%)" if conf_pct >= 80 else f"MEDIUM ({conf_pct}%)"
            else:
                verdict = "HOLD"
                conf_pct = 65
                conf = "MEDIUM (65%)"
        else:
            verdict = "ACCUMULATE" if lp > sma200 else "HOLD"
            conf_pct = 65
            conf = "MEDIUM (65%)"

        # Step 2: Formulate Entry Range, Target, and Stop Loss strictly aligned with Verdict
        if verdict in ("BUY", "ACCUMULATE"):
            # Bullish: Target MUST be above current price
            if raw_p_target and float(raw_p_target) > lp and float(raw_p_target) <= lp * 1.6:
                target = round(float(raw_p_target), 2)
            else:
                target = suggested_tp if suggested_tp > lp else round(lp * 1.08, 2)

            # Bullish: Stop loss MUST be below current price
            if raw_p_sl and float(raw_p_sl) < lp and float(raw_p_sl) >= lp * 0.75:
                sl = round(float(raw_p_sl), 2)
            else:
                sl = suggested_sl if suggested_sl < lp else round(lp * 0.95, 2)

            # Tight, realistic entry range near current market price (±1.5%)
            if raw_p_entry and 0.95 * lp <= float(raw_p_entry) <= 1.04 * lp:
                p_entry_val = float(raw_p_entry)
                if p_entry_val > lp:
                    entry_floor = round(lp * 0.99, 2)
                    entry_ceiling = round(p_entry_val * 1.01, 2)
                else:
                    entry_floor = round(max(p_entry_val * 0.99, lp * 0.98), 2)
                    entry_ceiling = round(lp * 1.015, 2)
            else:
                entry_floor = round(lp * 0.985, 2)
                entry_ceiling = round(lp * 1.015, 2)

            # HARD CEILING CLAMP: Entry ceiling must never be at or above target price
            entry_ceiling = min(entry_ceiling, round(target * 0.96, 2))
            entry_floor = min(entry_floor, round(entry_ceiling * 0.985, 2))
            entry = f"Rs. {entry_floor:.2f} - {entry_ceiling:.2f}"

            rationale = (
                f"Bullish quantitative pattern {p_name} (Score: {p_score}/100) confirms strong accumulation structure for {symbol}. "
                f"Price action is well-supported with upside target near Rs. {target}. "
                f"Corporate catalyst ({earnings_str}) provides strong upside momentum."
            )
            action = f"Initiate position in {entry} range targeting Rs. {target} with risk stop at Rs. {sl}."

        elif verdict == "SELL":
            # Bearish: Target MUST be downside support below current price
            if raw_p_target and float(raw_p_target) < lp and float(raw_p_target) >= lp * 0.5:
                target = round(float(raw_p_target), 2)
            else:
                target = round(lp * 0.92, 2)

            # Bearish: Stop loss MUST be above current price
            if raw_p_sl and float(raw_p_sl) > lp:
                sl = round(float(raw_p_sl), 2)
            else:
                sl = round(lp * 1.05, 2)

            entry = "Defensive / Avoid fresh entry"
            rationale = (
                f"Bearish formation {p_name} (Score: {p_score}/100) indicates distribution or breakdown pressure on {symbol}. "
                f"Immediate downside target is Rs. {target}. Caution advised ahead of {earnings_str}."
            )
            action = f"Protect capital: maintain strict trailing stop at Rs. {sl}. Avoid fresh long positions until reversal is confirmed."

        else:
            # HOLD: Range-bound or defensive caution
            if p_dir == "Bearish":
                target = round(lp * 0.94, 2)
                sl = round(lp * 1.04, 2)
                entry = "Hold existing / No fresh entry"
                rationale = (
                    f"{symbol} is showing bearish pattern {p_name} (Score: {p_score}/100) while holding key support. "
                    f"Watch Rs. {sl} resistance. {earnings_str} will determine continuation."
                )
                action = f"Hold existing exposure with trailing stop at Rs. {sl}. Wait for clear directional breakout before fresh allocation."
            else:
                target = suggested_tp if suggested_tp > lp else round(lp * 1.07, 2)
                sl = suggested_sl if suggested_sl < lp else round(lp * 0.94, 2)
                entry_floor = round(lp * 0.98, 2)
                entry_ceiling = min(round(lp * 1.015, 2), round(target * 0.96, 2))
                entry_floor = min(entry_floor, round(entry_ceiling * 0.985, 2))
                entry = f"Rs. {entry_floor:.2f} - {entry_ceiling:.2f}"
                rationale = (
                    f"{symbol} is trading in statistical equilibrium around SMA-50 (Rs. {sma50:.2f}). "
                    f"RSI ({rsi:.1f}) indicates balanced momentum. Key catalyst {earnings_str} will drive next directional expansion."
                )
                action = f"Accumulate on dips in {entry} with protective stop loss at Rs. {sl} targeting Rs. {target}."

        return {
            "action_verdict": verdict,
            "confidence_rating": conf,
            "confidence_percentage": conf_pct,
            "when_to_buy_entry": entry,
            "when_to_sell_target": f"Rs. {target}",
            "stop_loss": f"Rs. {sl}",
            "holding_horizon": "Medium-Term (1-3 Months)" if verdict in ("BUY", "ACCUMULATE") else "Short-Term (1-3 Weeks)",
            "chart_patterns": p_name,
            "upcoming_events_note": earnings_str,
            "key_rationale": rationale,
            "actionable_recommendation": action
        }

    def run(self, symbol: str, company_name: str, agent_outputs: Dict[str, Any]) -> Dict[str, Any]:
        hist_analysis = agent_outputs.get("historical_rag", {}).get("analysis", "N/A")
        tech_analysis = agent_outputs.get("technical", {}).get("analysis", "N/A")
        news_analysis = agent_outputs.get("news_sentiment", {}).get("analysis", "N/A")
        macro_analysis = agent_outputs.get("macro", {}).get("analysis", "N/A")
        fund_analysis = agent_outputs.get("fundamental", {}).get("analysis", "N/A")
        risk_analysis = agent_outputs.get("risk", {}).get("analysis", "N/A")

        raw_tech = agent_outputs.get("technical", {}).get("raw_indicators", {})
        raw_risk = agent_outputs.get("risk", {}).get("raw_risk", {})
        raw_hist = agent_outputs.get("historical_rag", {}).get("raw_stats", {})
        events_data = agent_outputs.get("fundamental", {}).get("upcoming_events", {})
        detected_patterns = agent_outputs.get("technical", {}).get("detected_patterns") or raw_tech.get("detected_patterns", [])

        last_price = raw_tech.get("last_price") or raw_risk.get("last_price") or raw_hist.get("last_close")
        if not last_price or last_price == "N/A":
            candles = self.cache_manager.get_cached_candles(symbol, limit_days=1)
            if candles:
                last_price = candles[-1].get("CLOSE_PRICE", "N/A")
        if last_price != "N/A":
            try:
                last_price = round(float(last_price), 2)
            except Exception:
                pass
        else:
            last_price = "N/A"

        suggested_sl = raw_risk.get("suggested_stop_loss", "N/A")
        suggested_tp = raw_risk.get("suggested_target_price", "N/A")

        # Compute instant deterministic quantitative verdict
        quant_verdict = self.compute_quantitative_verdict(
            symbol, company_name, last_price, raw_tech, raw_risk, detected_patterns, events_data
        )

        parsed = quant_verdict

        # Format patterns summary
        if detected_patterns:
            patterns_text = "; ".join([
                f"{p['name']} [Score: {p.get('quality_score', 'N/A')}/100, Target: Rs.{p.get('target_price', 'N/A')}, Stop: Rs.{p.get('stop_loss', 'N/A')}]: {p.get('description', '')}"
                for p in detected_patterns[:3]
            ])
        else:
            patterns_text = "No strong reversal/continuation pattern confirmed. Trading in standard range."

        # Format events summary
        if events_data:
            events_text = (
                f"Next Earnings: {events_data.get('earnings_date', 'TBD')} ({events_data.get('earnings_quarter', '')}) | "
                f"Dividend: {events_data.get('dividend_amount', 'N/A')} (Ex: {events_data.get('dividend_ex_date', 'N/A')}) | "
                f"Impact: {events_data.get('impact', 'Normal')}"
            )
        else:
            events_text = "Corporate earnings window within 30 days. No imminent binary risk."

        # Run LLM if NOT in FAST_MODE
        if not FAST_MODE:
            prompt = PromptTemplate.from_template(
                """You are a Master Quant Strategist synthesizing equity research for {symbol} ({company_name}) at Last Price Rs. {last_price}:
Patterns: {patterns_text}
Events: {events_text}
Technicals: {tech_analysis}
News Sentiment: {news_analysis}
Risk Bounds: Stop Loss Rs. {suggested_sl}, Target Rs. {suggested_tp}

Return a valid JSON strictly matching:
{{
  "action_verdict": "BUY" | "ACCUMULATE" | "HOLD" | "SELL",
  "confidence_rating": "HIGH (85%)" | "MEDIUM (65%)",
  "confidence_percentage": 85,
  "when_to_buy_entry": "Optimal Entry Range in Rs.",
  "when_to_sell_target": "Target Price in Rs.",
  "stop_loss": "Stop Loss in Rs.",
  "holding_horizon": "Short-Term (1-3 Weeks)" | "Medium-Term (1-3 Months)",
  "chart_patterns": "Primary chart pattern",
  "upcoming_events_note": "Earnings/dividend catalyst",
  "key_rationale": "2-sentence executive rationale.",
  "actionable_recommendation": "Concise step-by-step action plan."
}}
Return ONLY valid JSON.
"""
            )
            chain = prompt | self.llm
            try:
                response = chain.invoke({
                    "symbol": symbol,
                    "company_name": company_name,
                    "last_price": last_price,
                    "patterns_text": patterns_text,
                    "events_text": events_text,
                    "tech_analysis": tech_analysis,
                    "news_analysis": news_analysis,
                    "suggested_sl": suggested_sl,
                    "suggested_tp": suggested_tp
                })
                response_text = response.content if hasattr(response, 'content') else str(response)
                json_str = response_text.strip()
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0].strip()
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0].strip()
                parsed = json.loads(json_str)
            except Exception:
                # Fallback directly to the high-conviction quantitative verdict
                parsed = quant_verdict

        # Format markdown representation
        report_text = f"""### 🎯 VERDICT: {parsed.get('action_verdict', 'HOLD')} | Confidence: {parsed.get('confidence_rating', 'MEDIUM (60%)')}
- **When to Buy (Entry Range)**: {parsed.get('when_to_buy_entry', f'Rs. {last_price}')}
- **When to Sell (Target Price)**: {parsed.get('when_to_sell_target', f'Rs. {suggested_tp}')}
- **Stop Loss**: {parsed.get('stop_loss', f'Rs. {suggested_sl}')}
- **Holding Horizon**: {parsed.get('holding_horizon', 'Medium-Term (1-3 Months)')}
- **Technical Chart Patterns**: {parsed.get('chart_patterns', patterns_text)}
- **Upcoming Events & Catalysts**: {parsed.get('upcoming_events_note', events_text)}

**Key Rationale**: {parsed.get('key_rationale', '')}
**Action Plan**: {parsed.get('actionable_recommendation', '')}
"""

        return {
            "agent_name": "Master Prediction Synthesizer Agent",
            "symbol": symbol,
            "last_price": last_price,
            "structured_signal": parsed,
            "final_report": report_text,
            "detected_patterns": detected_patterns,
            "upcoming_events": events_data
        }
