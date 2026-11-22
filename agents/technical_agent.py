"""
Technical Analysis Agent.
Fast quantitative computation of moving averages (20, 50, 200), RSI, MACD crossovers,
Bollinger Bands, and advanced chart patterns:
- Head and Shoulders (and Inverse Head & Shoulders)
- Bollinger Band Squeeze, Band Walk, and Mean Reversion
- Saucer Pattern (Rounding Bottom / Accumulation Bowl)
- Double Bottom (W) / Double Top (M) formations.
"""

from typing import Dict, Any
from tools.tech_tools import TechnicalAnalysisEngine


class TechnicalAnalysisAgent:
    def __init__(self, tech_engine: TechnicalAnalysisEngine = None):
        self.tech_engine = tech_engine or TechnicalAnalysisEngine()

    def run(self, symbol: str) -> Dict[str, Any]:
        tech_data = self.tech_engine.analyze_symbol(symbol)
        
        rsi = tech_data.get("rsi_14", 50)
        sma50 = tech_data.get("sma_50", 0)
        sma200 = tech_data.get("sma_200", 0)
        last_price = tech_data.get("last_price", 0)
        bb_upper = tech_data.get("bollinger_upper", 0)
        bb_lower = tech_data.get("bollinger_lower", 0)
        pct_b = tech_data.get("bollinger_pct_b", 0.5)
        signals = ", ".join(tech_data.get("technical_signals", []))
        patterns = tech_data.get("detected_patterns", [])

        # Institutional volume flow footprint (20D Up/Down Volume Ratio)
        ud_ratio = tech_data.get("up_down_vol_ratio")
        ud_str = ""
        if ud_ratio is not None:
            if ud_ratio >= 1.25:
                ud_str = f" | Inst. Volume: Accumulation ({ud_ratio:.2f}x U/D)"
            elif ud_ratio <= 0.75:
                ud_str = f" | Inst. Volume: Distribution ({ud_ratio:.2f}x U/D)"
            else:
                ud_str = f" | Inst. Volume: Neutral ({ud_ratio:.2f}x U/D)"

        # Multi-week structural swing levels
        sh20 = tech_data.get("swing_high_20")
        sl20 = tech_data.get("swing_low_20")
        swing_str = ""
        if sh20 and sl20:
            swing_str = f" | 20D Swing Range: [Rs.{sl20:.2f} - Rs.{sh20:.2f}]"

        pct_52w = tech_data.get("pct_from_52w_high")
        pct_52w_str = f" | 52W High Gap: {pct_52w:.1f}%" if pct_52w is not None else ""

        extra_parts = []
        adx_14 = tech_data.get("adx_14")
        if adx_14 is not None:
            t_str = tech_data.get("trend_strength") or ""
            extra_parts.append(f"ADX(14): {adx_14:.1f}" + (f" ({t_str})" if t_str else ""))
        weekly_trend = tech_data.get("weekly_trend")
        if weekly_trend:
            extra_parts.append(f"Weekly Trend: {weekly_trend}")
        mrs = tech_data.get("mansfield_rs")
        if mrs is not None:
            rs_r = tech_data.get("rs_rating") or ""
            extra_parts.append(f"RS vs Nifty: {mrs:+.2f}" + (f" ({rs_r})" if rs_r else ""))
        deliv_pct = tech_data.get("delivery_pct")
        if deliv_pct is not None:
            d_conv = tech_data.get("delivery_conviction") or ""
            extra_parts.append(f"Delivery %: {deliv_pct:.1f}%" + (f" ({d_conv})" if d_conv else ""))
        extras_str = (" | " + " | ".join(extra_parts)) if extra_parts else ""

        if patterns:
            p_summary = "; ".join([f"{p['name']} [Score: {p.get('quality_score', 'N/A')}/100, Status: {p.get('status', 'Active')}, Target: Rs.{p.get('target_price', 'N/A')}]: {p['description']}" for p in patterns])
            patterns_line = f"Detected Chart Patterns: {p_summary}"
        else:
            patterns_line = "Detected Chart Patterns: No major reversal/continuation patterns confirmed (Consolidation)."

        analysis_text = (
            f"Last Price: Rs.{last_price} | RSI(14): {rsi} | SMA50: Rs.{sma50} | SMA200: Rs.{sma200} | "
            f"Bollinger Bands: [{bb_lower} - {bb_upper}] (%B: {pct_b}){ud_str}{swing_str}{pct_52w_str}{extras_str} | "
            f"{patterns_line} | "
            f"Key Technical Signals: {signals}"
        )

        return {
            "agent_name": "Technical Analysis Agent",
            "symbol": symbol,
            "raw_indicators": tech_data,
            "detected_patterns": patterns,
            "analysis": analysis_text
        }
