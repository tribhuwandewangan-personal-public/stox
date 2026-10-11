"""
Risk & Volatility Management Agent.
Fast quantitative calculation of volatility, 95% VaR, Max Drawdown, Stop Loss, and Risk-Reward.
"""

from typing import Dict, Any
from tools.risk_tools import RiskManagementEngine

class RiskAgent:
    def __init__(self, risk_engine: RiskManagementEngine = None):
        self.risk_engine = risk_engine or RiskManagementEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        risk_data = self.risk_engine.evaluate_risk(symbol)
        
        sl = risk_data.get("suggested_stop_loss", 0)
        tp = risk_data.get("suggested_target_price", 0)
        rr = risk_data.get("risk_reward_ratio", "1:2")
        vol = risk_data.get("annualized_volatility_pct", 0)

        analysis_text = f"Volatility: {vol}% | Stop Loss: Rs.{sl} | Target Price: Rs.{tp} | Risk-Reward: {rr}"

        return {
            "agent_name": "Risk & Volatility Agent",
            "symbol": symbol,
            "raw_risk": risk_data,
            "analysis": analysis_text
        }
