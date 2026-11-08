"""
Long-Term Wealth & Compounder Analysis Engine for NSE Equities.
Provides institutional 1-3 year multi-year fundamental horizons, compounder ratings,
business moat scores, and sectoral long-term stock recommendations to accompany
short-term swing and technical indicators.
"""

from typing import Dict, Any, List, Optional


class LongTermStrategyEngine:
    def __init__(self):
        # Curated sector profiles with institutional growth CAGR, moat benchmarks, and top compounders
        self.sector_profiles = {
            "Capital Markets": {
                "base_cagr": "18-24% p.a.",
                "moat_type": "Wide Moat (Financialization Duopoly)",
                "catalyst_theme": "Demat account surge, equity penetration & options trading turnover",
                "top_long_term_peers": ["NSE", "BSE", "CDSL"]
            },
            "Capital Goods & Construction": {
                "base_cagr": "15-20% p.a.",
                "moat_type": "Wide Moat (Domestic & GCC Capex Leader)",
                "catalyst_theme": "Mega infra, high-speed rail, defence & green hydrogen EPC",
                "top_long_term_peers": ["LT", "POLYCAB", "LLOYDSENGG"]
            },
            "Aerospace & Defence": {
                "base_cagr": "18-22% p.a.",
                "moat_type": "Wide Moat (Sovereign Defence Electronics)",
                "catalyst_theme": "Atmanirbhar Bharat defence indigenization & export orders",
                "top_long_term_peers": ["BEL", "MAZDOCK", "DATAPATTNS", "ZENTEC"]
            },
            "Auto Ancillaries": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Wide Moat (Global Tier-1 Consolidator)",
                "catalyst_theme": "EV wiring harness content expansion & international M&A synergies",
                "top_long_term_peers": ["MOTHERSON", "GABRIEL", "RML"]
            },
            "Information Technology": {
                "base_cagr": "12-16% p.a.",
                "moat_type": "Narrow to Wide Moat (Enterprise Digital Transformation)",
                "catalyst_theme": "GenAI adoption, cloud migration & telecom 5G monetization",
                "top_long_term_peers": ["TECHM", "COFORGE", "TATATECH"]
            },
            "Semiconductors & Electronics": {
                "base_cagr": "22-30% p.a.",
                "moat_type": "Emerging Moat (India Semiconductor Mission)",
                "catalyst_theme": "OSAT packaging plants, SiC power semis & fab ecosystem buildout",
                "top_long_term_peers": ["DIXON", "KAYNES", "MOSCHIP", "RIR"]
            },
            "Healthcare & Pharmaceuticals": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Narrow Moat (Regulated Market APIs)",
                "catalyst_theme": "China+1 active pharmaceutical ingredient de-risking & CDMO scale",
                "top_long_term_peers": ["SUPRIYA", "AETHER", "LINDEINDIA"]
            },
            "Metals & Mining": {
                "base_cagr": "10-14% p.a.",
                "moat_type": "Narrow Moat (Capital Intensive Cyclical)",
                "catalyst_theme": "Domestic infra steel demand & green hydrogen transition",
                "top_long_term_peers": ["TATASTEEL", "AMBUJACEM"]
            },
            "Banking & Financial Services": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Wide Moat (Retail CASA & Credit Expansion)",
                "catalyst_theme": "Double-digit credit growth, pristine asset quality & gold loan AUM",
                "top_long_term_peers": ["HDFCBANK", "ICICIBANK", "SBIN", "MUTHOOTFIN"]
            }
        }

        # Specific institutional multi-year ratings for key tracked symbols
        self.curated_profiles = {
            "ABB": {
                "multiplier": 1.48,
                "verdict": "STRONG BUY (Industrial Automation Leader)",
                "moat": "Wide Moat (Electrification & Motion MNC Duopoly)",
                "horizon": "1-3 Years (Capex & Automation Wave)",
                "thesis": "Dominant global MNC player in industrial robotics, drives, energy-efficient motors, and electrification equipment.",
                "peers": ["POWERINDIA", "CGPOWER", "LT", "TARIL"]
            },
            "GROWW": {
                "multiplier": 1.60,
                "verdict": "STRONG BUY (Fintech & WealthTech Leader)",
                "moat": "Wide Moat (India's Largest Active Client Broker)",
                "horizon": "1-3 Years (Pre-IPO / Retail Expansion)",
                "thesis": "Over 1.2 crore active NSE clients, fast-growing mutual fund and margin trading facility (MTF) book.",
                "peers": ["BSE", "CDSL", "NSE"]
            },
            "NSE": {
                "multiplier": 1.55,
                "verdict": "STRONG BUY (Core Monopoly Compounder)",
                "moat": "Monopoly Moat (National Exchange Infrastructure)",
                "horizon": "1-3 Years (Pre-IPO / Post-Listing Anchor)",
                "thesis": "Dominant exchange handling 90%+ of Indian derivatives with superior ROE and operating leverage.",
                "peers": ["BSE", "CDSL"]
            },
            "LT": {
                "multiplier": 1.48,
                "verdict": "STRONG BUY (Infra & EPC Anchor)",
                "moat": "Wide Moat (India & Middle East Orderbook)",
                "horizon": "1-3 Years (Capex Supercycle)",
                "thesis": "Unmatched scale in infrastructure, defence manufacturing, hydrocarbon, and green energy EPC.",
                "peers": ["POLYCAB", "BEL", "LLOYDSENGG"]
            },
            "MOTHERSON": {
                "multiplier": 1.52,
                "verdict": "BUY (Global Auto Ancillary Compounder)",
                "moat": "Wide Moat (Global Wiring Harness Leader)",
                "horizon": "1-3 Years (Multi-Year Auto Recovery)",
                "thesis": "Tier-1 supplier to global OEMs; rising content per vehicle from electrification and electronics.",
                "peers": ["GABRIEL", "TMPV", "RML"]
            },
            "BEL": {
                "multiplier": 1.55,
                "verdict": "STRONG BUY (Defence Monopolist)",
                "moat": "Wide Moat (Sovereign Defence Electronics)",
                "horizon": "1-3 Years (Atmanirbhar Growth)",
                "thesis": "Virtually zero debt, robust 20%+ ROE, and multi-year order backlog with Indian Armed Forces.",
                "peers": ["MAZDOCK", "DATAPATTNS", "ZENTEC"]
            },
            "POLYCAB": {
                "multiplier": 1.45,
                "verdict": "ACCUMULATE (Capex & Electrification Proxy)",
                "moat": "Wide Moat (Wires & Cables Market Leader)",
                "horizon": "1-3 Years (Infra & Real Estate Wave)",
                "thesis": "25%+ market share in organized cables, strong FMEG brand expansion, and heavy institutional backing.",
                "peers": ["LT", "TARIL"]
            },
            "HDFCBANK": {
                "multiplier": 1.42,
                "verdict": "STRONG BUY (Private Banking Anchor)",
                "moat": "Wide Moat (CASA & Granular Branch Franchise)",
                "horizon": "1-3 Years (Deposit Normalization)",
                "thesis": "Post-merger loan-to-deposit ratio is normalizing; superior long-term wealth compounder.",
                "peers": ["ICICIBANK", "SBIN", "MUTHOOTFIN"]
            },
            "ICICIBANK": {
                "multiplier": 1.45,
                "verdict": "STRONG BUY (Credit Outperformer)",
                "moat": "Wide Moat (Tech-First Retail & Corporate Banking)",
                "horizon": "1-3 Years (Core Portfolio Compounder)",
                "thesis": "Consistently industry-best NIMs, Return on Assets (>2.2%), and digital retail moat.",
                "peers": ["HDFCBANK", "SBIN"]
            },
            "TATASTEEL": {
                "multiplier": 1.32,
                "verdict": "HOLD / ACCUMULATE ON DIPS (Cyclical)",
                "moat": "Narrow Moat (Integrated Raw Material Advantage)",
                "horizon": "1-2 Years (Global Commodity Cycle)",
                "thesis": "Domestic steel demand is robust, but UK green transition and European spreads moderate multi-year CAGR.",
                "peers": ["LT", "AMBUJACEM"]
            },
            "TECHM": {
                "multiplier": 1.38,
                "verdict": "ACCUMULATE (Turnaround & Telecom 5G)",
                "moat": "Wide Moat (Tier-1 IT Global Telecom Leader)",
                "horizon": "1-3 Years (Project Fortius Turnaround)",
                "thesis": "Under new CEO leadership, margin expansion program is executing well alongside high dividend yield.",
                "peers": ["COFORGE", "TATATECH"]
            },
            "SUPRIYA": {
                "multiplier": 1.46,
                "verdict": "ACCUMULATE (Specialty API Compounder)",
                "moat": "Narrow to Wide Moat (Regulated Market Certifications)",
                "horizon": "1-3 Years (CDMO Capacity Expansion)",
                "thesis": "High EBITDA margin profile (28-32%), FDA compliance, and continuous new DMF filings.",
                "peers": ["AETHER", "LINDEINDIA"]
            },
            "HAPPSTMNDS": {
                "multiplier": 1.30,
                "verdict": "HOLD / NEUTRAL (Turnaround Watch)",
                "moat": "Narrow Moat (Midcap IT Valuation Compression)",
                "horizon": "1-3 Years (Rebound Watch)",
                "thesis": "GenAI narrative is promising, but recent acquisitions diluted margins. Await operational margin stability.",
                "peers": ["TECHM", "COFORGE", "TATATECH"]
            },
            "TANLA": {
                "multiplier": 1.20,
                "verdict": "NEUTRAL / HARVEST ON BOUNCES (Margin Pressure)",
                "moat": "Narrow Moat (CPaaS Price Competition)",
                "horizon": "1-2 Years (Transformation Watch)",
                "thesis": "Commercial SMS pricing pressure remains a headwind; Wisely platform requires sustained enterprise ramp.",
                "peers": ["TECHM", "COFORGE", "BHARTIARTL"]
            },
            "CDSL": {
                "multiplier": 1.50,
                "verdict": "STRONG BUY (Demat Monopoly)",
                "moat": "Wide Moat (India's Largest Depository)",
                "horizon": "1-3 Years (Capital Market Democratization)",
                "thesis": "Asset-light, debt-free monopoly benefiting from exponential retail equity and mutual fund participation.",
                "peers": ["BSE", "NSE"]
            },
            "BSE": {
                "multiplier": 1.48,
                "verdict": "BUY (Derivatives Volume Expander)",
                "moat": "Wide Moat (Oldest Exchange with Rising Share)",
                "horizon": "1-3 Years (Market Share Expansion)",
                "thesis": "Staggering growth in index options turnover (Sensex/Bankex) and Star MF transaction fee revenues.",
                "peers": ["NSE", "CDSL"]
            },
            "DIXON": {
                "multiplier": 1.55,
                "verdict": "STRONG BUY (Electronics Manufacturing Giant)",
                "moat": "Wide Moat (India Electronics PLI Champion)",
                "horizon": "1-3 Years (Mobile & IT Hardware Scale)",
                "thesis": "Largest domestic EMS provider scaling global smartphone manufacturing, backward integration, and display tech.",
                "peers": ["KAYNES", "SYRMA"]
            },
            "KAYNES": {
                "multiplier": 1.52,
                "verdict": "ACCUMULATE (OSAT Semiconductor Player)",
                "moat": "Wide Moat (High-Mix High-Complexity Electronics)",
                "horizon": "1-3 Years (Semiconductor OSAT Commercialization)",
                "thesis": "First-mover in Indian OSAT packaging facilities with soaring automotive and aerospace orderbook.",
                "peers": ["DIXON", "MOSCHIP"]
            }
        }

    def evaluate_long_term_stock(
        self,
        symbol: str,
        name: str = "",
        sector: str = "",
        last_price: float = 100.0,
        short_verdict: str = "BUY"
    ) -> Dict[str, Any]:
        """
        Generates institutional 1-3 year wealth compounder outlook for any stock.
        """
        sym = symbol.upper().strip()
        lp = max(1.0, float(last_price or 100.0))

        # Check curated profile first
        if sym in self.curated_profiles:
            cp = self.curated_profiles[sym]
            mult = cp["multiplier"]
            lt_target = round(lp * mult, 2)
            upside_pct = round((mult - 1.0) * 100, 1)
            return {
                "symbol": sym,
                "long_term_verdict": cp["verdict"],
                "long_term_horizon": cp["horizon"],
                "long_term_target": f"Rs. {lt_target:,.2f}",
                "long_term_target_num": lt_target,
                "long_term_upside_pct": f"+{upside_pct}%",
                "long_term_moat": cp["moat"],
                "long_term_thesis": cp["thesis"],
                "suggested_long_term_peers": cp["peers"],
                "is_top_wealth_pick": any(w in cp["verdict"].upper() for w in ["STRONG BUY", "BUY", "ACCUMULATE"]) and not any(w in cp["verdict"].upper() for w in ["AVOID", "NEUTRAL", "HARVEST"])
            }

        # Dynamic heuristic based on sector and short-term verdict
        sector_clean = sector or "Equities"
        matched_sec = None
        for sec_key in self.sector_profiles:
            if sec_key.lower() in sector_clean.lower() or sector_clean.lower() in sec_key.lower():
                matched_sec = self.sector_profiles[sec_key]
                break

        if not matched_sec:
            # Fallback profile
            matched_sec = {
                "base_cagr": "12-16% p.a.",
                "moat_type": "Moderate Moat (Established Market Presence)",
                "catalyst_theme": "Domestic GDP expansion, operating leverage & margin efficiency",
                "top_long_term_peers": ["RELIANCE", "LT", "HDFCBANK"]
            }

        short_v = (short_verdict or "HOLD").upper()
        if "BUY" in short_v or "ACCUMULATE" in short_v:
            mult = 1.42
            verdict = "ACCUMULATE (Quality Compounder)"
            is_pick = True
        elif "SELL" in short_v:
            mult = 1.15
            verdict = "HOLD / DEFENSIVE (Cyclical Watch)"
            is_pick = False
        else:
            mult = 1.30
            verdict = "ACCUMULATE ON DIPS (Long-Term Horizon)"
            is_pick = False

        lt_target = round(lp * mult, 2)
        upside_pct = round((mult - 1.0) * 100, 1)

        # Remove self from peers
        peers = [p for p in matched_sec["top_long_term_peers"] if p != sym]
        if not peers:
            peers = ["LT", "RELIANCE"]

        return {
            "symbol": sym,
            "long_term_verdict": verdict,
            "long_term_horizon": "1-3 Years (Wealth Compounder)",
            "long_term_target": f"Rs. {lt_target:,.2f}",
            "long_term_target_num": lt_target,
            "long_term_upside_pct": f"+{upside_pct}%",
            "long_term_moat": matched_sec["moat_type"],
            "long_term_thesis": f"Beneficiary of {matched_sec['catalyst_theme']}. Expected earnings CAGR: {matched_sec['base_cagr']}.",
            "suggested_long_term_peers": peers[:3],
            "is_top_wealth_pick": is_pick
        }


# Global singleton instance
long_term_engine = LongTermStrategyEngine()

