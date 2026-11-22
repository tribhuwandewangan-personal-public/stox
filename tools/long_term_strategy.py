"""
Long-Term Wealth & Compounder Analysis Engine for NSE Equities.
Provides quantitative multi-pillar 1-3 year compounder scoring (Growth, Quality,
Moat, Valuation), decoupled from short-term swing verdicts.
"""

import json
import math
import os
import re
import threading
from typing import Dict, Any, Optional, List

_SYMBOLS_CACHE_LOCK = threading.Lock()
_SYMBOLS_CACHE = {"path": None, "mtime": None, "data": []}


def _load_curated_symbols_cached() -> List[Dict[str, Any]]:
    try:
        from config import SYMBOLS_FILE_PATH
        path = SYMBOLS_FILE_PATH
        mtime = os.path.getmtime(path)
    except Exception:
        return []
    with _SYMBOLS_CACHE_LOCK:
        if _SYMBOLS_CACHE["path"] == path and _SYMBOLS_CACHE["mtime"] == mtime:
            return _SYMBOLS_CACHE["data"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                sdata = json.load(f)
            sym_list = sdata.get("symbols", []) if isinstance(sdata, dict) else sdata
        except Exception:
            sym_list = []
        _SYMBOLS_CACHE.update({"path": path, "mtime": mtime, "data": sym_list})
        return sym_list

_BFSI_RE = re.compile(
    r"\b(bank|banking|nbfc|financial services|insurance|housing finance|microfinance|capital markets|fintech)\b",
    re.I,
)


def _num(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(str(val).replace(",", "").replace("%", "").strip())
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


class LongTermStrategyEngine:
    def __init__(self):
        self.sector_profiles = {
            "Capital Markets": {
                "base_cagr": "18-24% p.a.",
                "moat_type": "Wide Moat (Financialization Duopoly)",
                "catalyst_theme": "Demat account surge, equity penetration & options trading turnover",
                "top_long_term_peers": ["BSE", "CDSL", "MCX", "ANGELONE"],
            },
            "Capital Goods & Construction": {
                "base_cagr": "15-20% p.a.",
                "moat_type": "Wide Moat (Domestic & GCC Capex Leader)",
                "catalyst_theme": "Mega infra, high-speed rail, defence & green hydrogen EPC",
                "top_long_term_peers": ["LT", "ABB", "POLYCAB", "CUMMINSIND"],
            },
            "Aerospace & Defence": {
                "base_cagr": "18-22% p.a.",
                "moat_type": "Wide Moat (Sovereign Defence Electronics)",
                "catalyst_theme": "Atmanirbhar Bharat defence indigenization & export orders",
                "top_long_term_peers": ["BEL", "HAL", "MAZDOCK", "DATAPATTNS"],
            },
            "Auto Ancillaries": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Wide Moat (Global Tier-1 Consolidator)",
                "catalyst_theme": "EV wiring harness content expansion & international M&A synergies",
                "top_long_term_peers": ["MOTHERSON", "BHARATFORG", "BOSCHLTD", "SONACOMS"],
            },
            "Information Technology": {
                "base_cagr": "12-16% p.a.",
                "moat_type": "Narrow to Wide Moat (Enterprise Digital Transformation)",
                "catalyst_theme": "Enterprise AI modernization, cloud migration & global outsourcing",
                "top_long_term_peers": ["TCS", "INFY", "HCLTECH", "COFORGE"],
            },
            "Semiconductors & Electronics": {
                "base_cagr": "20-28% p.a.",
                "moat_type": "Emerging Moat (India Electronics & EMS Scale)",
                "catalyst_theme": "EMS localization, OSAT packaging plants & industrial electronics",
                "top_long_term_peers": ["DIXON", "KAYNES", "PGEL", "SYRMA"],
            },
            "Healthcare & Pharmaceuticals": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Narrow to Wide Moat (Regulated Market Formulations & APIs)",
                "catalyst_theme": "Specialty generics, CDMO China+1 de-risking & hospital scale",
                "top_long_term_peers": ["SUNPHARMA", "CIPLA", "DIVISLAB", "APOLLOHOSP"],
            },
            "Metals & Mining": {
                "base_cagr": "10-14% p.a.",
                "moat_type": "Narrow Moat (Capital Intensive Cyclical)",
                "catalyst_theme": "Domestic infra steel demand & raw material integration",
                "top_long_term_peers": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "COALINDIA"],
            },
            "Banking & Financial Services": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Wide Moat (Retail CASA & Credit Expansion)",
                "catalyst_theme": "Granular deposit franchise, credit discipline & rising RoA",
                "top_long_term_peers": ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],
            },
            "FMCG & Consumer": {
                "base_cagr": "12-16% p.a.",
                "moat_type": "Wide Moat (Brand Equity & Distribution Reach)",
                "catalyst_theme": "Rural demand recovery, premiumization & category leadership",
                "top_long_term_peers": ["HINDUNILVR", "ITC", "NESTLEIND", "TITAN"],
            },
            "Energy, Oil & Power": {
                "base_cagr": "13-17% p.a.",
                "moat_type": "Wide Moat (Integrated Energy & Grid Infrastructure)",
                "catalyst_theme": "Power transmission capex, refining integration & renewables",
                "top_long_term_peers": ["RELIANCE", "NTPC", "POWERGRID", "TATAPOWER"],
            },
            "Chemicals & Materials": {
                "base_cagr": "15-20% p.a.",
                "moat_type": "Narrow to Wide Moat (Specialty Chem Complex Synthesis)",
                "catalyst_theme": "Import substitution, fluorochemicals & global supply diversification",
                "top_long_term_peers": ["PIDILITIND", "SRF", "PIIND", "NAVINFLUOR"],
            },
            "Telecommunications & Media": {
                "base_cagr": "14-18% p.a.",
                "moat_type": "Duopoly Moat (Spectrum & Digital Infrastructure)",
                "catalyst_theme": "ARPU expansion, 5G enterprise monetization & fiber connectivity",
                "top_long_term_peers": ["BHARTIARTL", "INDUSTOWER", "TATACOMM"],
            },
            "Packaging & Industrials": {
                "base_cagr": "13-17% p.a.",
                "moat_type": "Moderate Moat (Contract Manufacturing & Industrial Supply)",
                "catalyst_theme": "FMCG/pharma packaging consolidation & industrial automation",
                "top_long_term_peers": ["SIEMENS", "CUMMINSIND", "CARBORUNIV"],
            },
        }

    def _match_sector_profile(self, sym: str, sector: str) -> Dict[str, Any]:
        sector_clean = sector or ""
        matched_sec = None

        if sector_clean:
            for sec_key, prof in self.sector_profiles.items():
                if sec_key.lower() in sector_clean.lower() or sector_clean.lower() in sec_key.lower():
                    matched_sec = dict(prof)
                    break

        if not matched_sec and sector_clean:
            try:
                from tools.peer_benchmark_engine import _resolve_sector, SECTOR_PEER_MAP
                canon_key = _resolve_sector(sector_clean)
                if canon_key and canon_key in SECTOR_PEER_MAP:
                    canon_peers = [p for p in SECTOR_PEER_MAP[canon_key] if p != sym]
                    sec_map_name = {
                        "IT": "Information Technology",
                        "BANKING": "Banking & Financial Services",
                        "PHARMA": "Healthcare & Pharmaceuticals",
                        "AUTO": "Auto Ancillaries",
                        "FMCG": "FMCG & Consumer",
                        "ENERGY": "Energy, Oil & Power",
                        "METALS": "Metals & Mining",
                        "INFRA": "Capital Goods & Construction",
                        "CAPITAL_GOODS": "Capital Goods & Construction",
                        "DEFENCE": "Aerospace & Defence",
                        "CHEMICALS": "Chemicals & Materials",
                        "CAPITAL_MARKETS": "Capital Markets",
                        "TELECOM": "Telecommunications & Media",
                        "CONSUMER": "FMCG & Consumer",
                        "NBFC": "Banking & Financial Services",
                    }.get(canon_key)
                    if sec_map_name and sec_map_name in self.sector_profiles:
                        matched_sec = dict(self.sector_profiles[sec_map_name])
                        if canon_peers:
                            matched_sec["top_long_term_peers"] = canon_peers
            except Exception:
                pass

        if not matched_sec:
            matched_sec = {
                "base_cagr": "12-16% p.a.",
                "moat_type": "Moderate Moat (Established Market Presence)",
                "catalyst_theme": "Domestic GDP expansion, operating leverage & margin efficiency",
                "top_long_term_peers": ["RELIANCE", "LT", "HDFCBANK"],
            }
        return matched_sec

    def _discover_peers(self, sym: str, sector_clean: str, base_peers: List[str]) -> List[str]:
        dyn_peers = list(base_peers)
        if sector_clean:
            for s in _load_curated_symbols_cached():
                if not isinstance(s, dict) or not s.get("symbol"):
                    continue
                s_sym = str(s["symbol"]).upper()
                s_sec = str(s.get("sector", ""))
                if s_sym != sym and s_sec and (s_sec.lower() in sector_clean.lower() or sector_clean.lower() in s_sec.lower()):
                    if s_sym not in dyn_peers:
                        dyn_peers.append(s_sym)
        peers = [p for p in dyn_peers if p != sym]
        return peers[:4] if peers else ["LT", "RELIANCE"]

    def evaluate_long_term_stock(
        self,
        symbol: str,
        name: str = "",
        sector: str = "",
        last_price: Optional[float] = None,
        short_verdict: str = "HOLD",
        fund_data: Optional[Dict[str, Any]] = None,
        forensic_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generates a 1-3 year quantitative fundamental compounder rating completely decoupled
        from `short_verdict`. Evaluates 4 pillars (Growth, Quality, Moat, Valuation -> 0-100).
        Without fundamental/forensic telemetry, returns a neutral HOLD / UNAUDITED FUNDAMENTALS
        rating with an indicative baseline scenario.
        """
        sym = symbol.upper().strip()
        try:
            lp = float(last_price)
        except (TypeError, ValueError):
            lp = 0.0
        has_price = lp > 0 and math.isfinite(lp)

        fund = dict((fund_data or {}).get("raw_fundamentals") or (fund_data or {}))
        forensic = dict(forensic_data or {})
        eff_sector = sector or str(fund.get("sector") or forensic.get("sector") or "")
        matched_sec = self._match_sector_profile(sym, eff_sector)
        peers = self._discover_peers(sym, eff_sector, matched_sec.get("top_long_term_peers", []))
        is_bfsi = bool(_BFSI_RE.search(eff_sector))

        # Extract quantitative signals
        eg = _num(fund.get("earnings_growth_pct"))
        rg = _num(fund.get("revenue_growth_pct")) or _num((forensic.get("cash_conversion") or {}).get("revenue_growth_pct"))
        bfsi_h = forensic.get("bfsi_health") or {}
        roe = _num(fund.get("roe_pct")) or _num(bfsi_h.get("roe_pct"))
        roa = _num(fund.get("roa_pct")) or _num(bfsi_h.get("roa_pct"))
        pm = _num(fund.get("profit_margin_pct"))
        pe = _num(fund.get("pe_ratio"))
        peg = _num(fund.get("peg_ratio"))
        de_raw = _num(fund.get("debt_to_equity"))
        net_cash_str = str(fund.get("net_cash_status") or "").lower()

        cfo_pat = _num((forensic.get("cash_conversion") or {}).get("cfo_to_pat_ratio"))
        distortion = _num((forensic.get("earnings_quality") or {}).get("distortion_pct"))
        f_score = _num(forensic.get("piotroski_f_score"))
        f_verdict = str(forensic.get("verdict") or "").upper()
        gov_grade = str((forensic.get("governance_telemetry") or {}).get("governance_grade") or "").upper()
        beneish_status = str((forensic.get("beneish_m_score") or {}).get("status") or "").upper()
        fair_val = _num(forensic.get("fair_value") or (forensic.get("valuation_metrics") or {}).get("intrinsic_fair_value"))
        mos_pct = _num(forensic.get("margin_of_safety_pct") or (forensic.get("valuation_metrics") or {}).get("margin_of_safety_pct"))
        val_method = str((forensic.get("valuation_metrics") or {}).get("valuation_method") or "")

        has_quant = any(
            v is not None for v in (eg, rg, roe, roa, pe, peg, f_score, cfo_pat, mos_pct, fair_val)
        ) or (bool(fund.get("available")) and f_verdict not in ("", "UNAUDITED"))

        if not has_quant:
            compounder_score = 50
            pillar_scores = {"growth": 12, "quality": 15, "moat": 11, "valuation": 12}
            projected_cagr_pct = 8.0
            verdict = "HOLD / UNAUDITED FUNDAMENTALS"
            is_pick = False
            horizon = "1-3 Years (Awaiting Fundamental Telemetry)"
            target_basis = "indicative_scenario"
            lt_target_num = round(lp * ((1.0 + projected_cagr_pct / 100.0) ** 3), 2) if has_price else None
            lt_target_str = f"Rs. {lt_target_num:,.2f}" if lt_target_num is not None else "N/A"
            thesis = (
                f"{matched_sec['catalyst_theme'].capitalize()}. Unaudited / awaiting fundamental telemetry; "
                f"target reflects an indicative scenario (~{projected_cagr_pct:.1f}% CAGR), not a model forecast."
            )
        else:
            # Pillar 1: Growth (0 - 25)
            growth = 10.0
            if eg is not None:
                if eg >= 20.0:
                    growth += 9.0
                elif eg >= 12.0:
                    growth += 6.0
                elif eg >= 5.0:
                    growth += 3.0
                elif eg < 0.0:
                    growth -= 5.0
            if rg is not None:
                if rg >= 15.0:
                    growth += 6.0
                elif rg >= 8.0:
                    growth += 4.0
                elif rg < 0.0:
                    growth -= 4.0
            growth = max(0.0, min(25.0, growth))

            # Pillar 2: Quality (0 - 30)
            quality = 8.0
            if roe is not None:
                if roe >= 20.0:
                    quality += 10.0
                elif roe >= 14.0:
                    quality += 7.0
                elif roe >= 10.0:
                    quality += 3.0
                elif roe < 6.0:
                    quality -= 5.0
            elif is_bfsi and roa is not None:
                if roa >= 1.5:
                    quality += 9.0
                elif roa >= 1.0:
                    quality += 5.0
            elif is_bfsi:
                quality += 4.0

            if not is_bfsi and cfo_pat is not None:
                if cfo_pat >= 0.90:
                    quality += 6.0
                elif cfo_pat >= 0.70:
                    quality += 3.0
                elif cfo_pat < 0.45:
                    quality -= 6.0
            elif is_bfsi:
                quality += 3.0

            if distortion is not None:
                if distortion < 10.0:
                    quality += 3.0
                elif distortion >= 25.0:
                    quality -= 6.0
            if f_score is not None:
                if f_score >= 7:
                    quality += 5.0
                elif f_score <= 3:
                    quality -= 5.0
            quality = max(0.0, min(30.0, quality))

            # Pillar 3: Moat & Financial Strength (0 - 20)
            moat = 6.0
            if is_bfsi:
                gnpa = _num(bfsi_h.get("gnpa_pct"))
                casa = _num(bfsi_h.get("casa_pct"))
                crar = _num(bfsi_h.get("crar_pct"))
                if gnpa is not None:
                    moat += 5.0 if gnpa <= 2.0 else (-4.0 if gnpa > 4.5 else 2.0)
                if casa is not None and casa >= 40.0:
                    moat += 4.0
                if crar is not None and crar >= 16.0:
                    moat += 3.0
            else:
                de_ratio = (de_raw / 100.0) if (de_raw is not None and de_raw > 5.0) else de_raw
                if "net cash" in net_cash_str or "debt-free" in net_cash_str or (de_ratio is not None and 0 <= de_ratio <= 0.35):
                    moat += 7.0
                elif de_ratio is not None and de_ratio <= 0.9:
                    moat += 3.0
                elif de_ratio is not None and de_ratio > 1.8:
                    moat -= 5.0
                if pm is not None:
                    if pm >= 15.0:
                        moat += 4.0
                    elif pm >= 8.0:
                        moat += 2.0
            if "wide" in matched_sec["moat_type"].lower() or "duopoly" in matched_sec["moat_type"].lower():
                moat += 3.0
            moat = max(0.0, min(20.0, moat))

            # Pillar 4: Valuation (0 - 25)
            valuation = 8.0
            if mos_pct is not None:
                if mos_pct >= 25.0:
                    valuation += 12.0
                elif mos_pct >= 10.0:
                    valuation += 8.0
                elif mos_pct >= 0.0:
                    valuation += 4.0
                elif mos_pct <= -25.0:
                    valuation -= 7.0
                elif mos_pct <= -15.0:
                    valuation -= 4.0
            if peg is not None:
                if 0 < peg <= 1.0:
                    valuation += 6.0
                elif 1.0 < peg <= 1.5:
                    valuation += 4.0
                elif peg > 2.5:
                    valuation -= 5.0
                elif peg <= 0:
                    valuation -= 4.0
            elif pe is not None:
                if 0 < pe <= 18.0:
                    valuation += 5.0
                elif pe <= 28.0:
                    valuation += 2.0
                elif pe > 55.0:
                    valuation -= 5.0
            valuation = max(0.0, min(25.0, valuation))

            compounder_score = int(round(growth + quality + moat + valuation))
            pillar_scores = {
                "growth": int(round(growth)),
                "quality": int(round(quality)),
                "moat": int(round(moat)),
                "valuation": int(round(valuation)),
            }

            if (
                gov_grade == "HIGH_RISK"
                or f_verdict in ("AVOID_OR_VALUE_TRAP", "HIGH_RISK_DISTRESSED")
                or beneish_status == "HIGH_MANIPULATION_RISK"
            ):
                compounder_score = min(compounder_score, 35)

            cagr_raw = 8.0 + (compounder_score - 50) * 0.22
            if rg is not None:
                cagr_raw = (cagr_raw * 0.7) + (max(2.0, min(25.0, rg)) * 0.3)
            projected_cagr_pct = round(max(4.0, min(24.0, cagr_raw)), 1)

            if compounder_score >= 78:
                verdict = "STRONG BUY (High-Quality Compounder)"
                is_pick = True
            elif compounder_score >= 64:
                verdict = "BUY / ACCUMULATE (Quality Compounder)"
                is_pick = True
            elif compounder_score >= 46:
                verdict = "HOLD (Monitor Fundamentals)"
                is_pick = False
            else:
                verdict = "AVOID / UNDERWEIGHT (Fundamental Risk)"
                is_pick = False

            horizon = "1-3 Years (Wealth Compounder)"
            if not has_price:
                lt_target_num = None
                lt_target_str = "N/A"
                target_basis = "indicative_scenario"
            elif fair_val is not None and fair_val > 0 and val_method in ("MULTI_METHOD_INTRINSIC", "BFSI_JUSTIFIED_PB"):
                lt_target_num = round(fair_val * ((1.0 + projected_cagr_pct / 100.0) ** 3), 2)
                lt_target_str = f"Rs. {lt_target_num:,.2f}"
                target_basis = "quantitative_fundamental_model"
            else:
                lt_target_num = round(lp * ((1.0 + projected_cagr_pct / 100.0) ** 3), 2)
                lt_target_str = f"Rs. {lt_target_num:,.2f}"
                target_basis = "indicative_scenario"

            thesis = (
                f"4-Pillar Compounder Score {compounder_score}/100 (G:{pillar_scores['growth']}/25, "
                f"Q:{pillar_scores['quality']}/30, M:{pillar_scores['moat']}/20, V:{pillar_scores['valuation']}/25). "
                f"{matched_sec['catalyst_theme'].capitalize()} (Projected CAGR ~{projected_cagr_pct:.1f}% p.a., "
                f"basis: {target_basis.replace('_', ' ')})."
            )

        if has_price and lt_target_num is not None:
            upside = round(((lt_target_num - lp) / lp) * 100.0, 1)
            lt_upside_pct = f"{'+' if upside >= 0 else ''}{upside}%"
        else:
            lt_upside_pct = ""

        return {
            "symbol": sym,
            "long_term_verdict": verdict,
            "long_term_horizon": horizon,
            "long_term_target": lt_target_str,
            "long_term_target_num": lt_target_num,
            "long_term_upside_pct": lt_upside_pct,
            "target_basis": target_basis,
            "long_term_moat": matched_sec["moat_type"],
            "long_term_thesis": thesis,
            "suggested_long_term_peers": peers,
            "is_top_wealth_pick": is_pick,
            "compounder_score": compounder_score,
            "pillar_scores": pillar_scores,
            "projected_cagr_pct": projected_cagr_pct,
        }


# Global singleton instance
long_term_engine = LongTermStrategyEngine()
