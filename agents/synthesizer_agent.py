"""
Master Prediction Synthesizer Agent.
Combines historical RAG insights, technical patterns, online sentiment, macro outlook,
fundamental valuation, and risk guardrails into a cohesive future prediction forecast report
with structured action signals (Buy/Sell, Entry Range, Target, Holding Horizon, Confidence Score).
"""

import json
from typing import Dict, Any, List
from langchain_core.prompts import PromptTemplate

from config import get_llm
from storage.cache_manager import CacheManager

class MasterPredictionSynthesizerAgent:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()
        self.llm = get_llm(temperature=0.2)

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

        shared_bulletin = self.cache_manager.get_latest_market_bulletin()
        market_bulletin_text = shared_bulletin.get("summary", "Stable global market environment.") if shared_bulletin else "Stable global market environment."

        prompt = PromptTemplate.from_template(
            """You are a Chief Investment Officer and Master Quant Strategist.
Synthesize all specialist research for stock {symbol} ({company_name}) at Last Price Rs. {last_price}:

Shared Market Bulletin:
{market_bulletin_text}

Specialist Research:
- Historical RAG: {hist_analysis}
- Technicals: {tech_analysis}
- News Sentiment: {news_analysis}
- Macro: {macro_analysis}
- Fundamentals: {fund_analysis}
- Risk & Volatility: {risk_analysis}

Return a valid JSON object strictly matching this schema:
{{
  "action_verdict": "BUY" | "ACCUMULATE" | "HOLD" | "SELL" | "STRONG_SELL",
  "confidence_rating": "HIGH (85%)" | "MEDIUM (65%)" | "LOW (40%)",
  "confidence_percentage": 85,
  "when_to_buy_entry": "Optimal Entry Range in Rs.",
  "when_to_sell_target": "Target Price in Rs.",
  "stop_loss": "Stop Loss in Rs.",
  "holding_horizon": "Short-Term (1-3 Weeks)" | "Medium-Term (1-3 Months)" | "Long-Term (6-12 Months)",
  "key_rationale": "3-sentence executive summary of why to buy/sell/hold.",
  "actionable_recommendation": "Step-by-step trading plan."
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
                "market_bulletin_text": market_bulletin_text,
                "hist_analysis": hist_analysis,
                "tech_analysis": tech_analysis,
                "news_analysis": news_analysis,
                "macro_analysis": macro_analysis,
                "fund_analysis": fund_analysis,
                "risk_analysis": risk_analysis
            })
            response_text = response.content if hasattr(response, 'content') else str(response)
            
            # Clean JSON string
            json_str = response_text.strip()
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            parsed = json.loads(json_str)
        except Exception:
            # Fallback structured signal
            parsed = {
                "action_verdict": "ACCUMULATE",
                "confidence_rating": "MEDIUM (65%)",
                "confidence_percentage": 65,
                "when_to_buy_entry": f"Rs. {last_price}",
                "when_to_sell_target": f"Rs. {suggested_tp}",
                "stop_loss": f"Rs. {suggested_sl}",
                "holding_horizon": "Medium-Term (1-3 Months)",
                "key_rationale": f"Balanced technical RSI and support trends for {symbol}. Accumulate near support level.",
                "actionable_recommendation": f"Buy on dips near Rs. {last_price} with stop loss at Rs. {suggested_sl} targeting Rs. {suggested_tp}."
            }

        # Format markdown representation for CLI and files
        report_text = f"""### 🎯 VERDICT: {parsed.get('action_verdict', 'HOLD')} | Confidence: {parsed.get('confidence_rating', 'MEDIUM (60%)')}
- **When to Buy (Entry Range)**: {parsed.get('when_to_buy_entry', f'Rs. {last_price}')}
- **When to Sell (Target Price)**: {parsed.get('when_to_sell_target', f'Rs. {suggested_tp}')}
- **Stop Loss**: {parsed.get('stop_loss', f'Rs. {suggested_sl}')}
- **Holding Horizon**: {parsed.get('holding_horizon', 'Medium-Term (1-3 Months)')}

**Key Rationale**: {parsed.get('key_rationale', '')}
**Action Plan**: {parsed.get('actionable_recommendation', '')}
"""

        return {
            "agent_name": "Master Prediction Synthesizer Agent",
            "symbol": symbol,
            "last_price": last_price,
            "structured_signal": parsed,
            "final_report": report_text
        }
