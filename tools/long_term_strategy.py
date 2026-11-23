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

_PRICE_PERF_LOCK = threading.Lock()
_PRICE_PERF_CACHE: Dict[str, Any] = {"ts": 0, "data": {}}
_SYMBOLS_CACHE_LOCK = threading.Lock()
_SYMBOLS_CACHE = {"path": None, "mtime": None, "data": []}


def _get_cached_multi_year_perf(symbol: str, current_price: float = 0.0, sector: str = "") -> Dict[str, Optional[float]]:
    """
    Computes 1Y return %, 3Y return %, 3Y peak drawdown %, and Sector-Relative 1Y/3Y Alpha %
    by comparing each stock against its canonical sector peers' median 1Y and 3Y price performance.
    Cached in memory for 5 minutes across all symbols to avoid repeated DB queries.
    """
    import time
    import statistics
    from tools.peer_benchmark_engine import _resolve_sector, SECTOR_PEER_MAP

    now_bucket = int(time.time() // 300)
    with _PRICE_PERF_LOCK:
        if _PRICE_PERF_CACHE["ts"] != now_bucket:
            try:
                from config import CACHE_DB_PATH, SYMBOLS_FILE_PATH, MIDCAP_250_SYMBOLS_FILE_PATH
                from storage.cache_manager import open_db
                perf_map: Dict[str, Dict[str, Optional[float]]] = {}
                sym_sec_map: Dict[str, str] = {}
                for spath in (MIDCAP_250_SYMBOLS_FILE_PATH, SYMBOLS_FILE_PATH):
                    if spath and os.path.exists(spath):
                        try:
                            with open(spath, "r", encoding="utf-8") as f:
                                sdata = json.load(f)
                            for s_it in (sdata.get("symbols", []) if isinstance(sdata, dict) else []):
                                k = str(s_it.get("symbol") or "").upper().strip()
                                sc = _resolve_sector(str(s_it.get("sector") or ""))
                                if k and sc:
                                    sym_sec_map[k] = sc
                        except Exception:
                            pass
                for canon_sec, peer_list in SECTOR_PEER_MAP.items():
                    for p_sym in peer_list:
                        sym_sec_map.setdefault(p_sym.upper(), canon_sec)

                if os.path.exists(CACHE_DB_PATH):
                    with open_db(CACHE_DB_PATH) as conn:
                        rows = conn.execute(
                            "SELECT symbol, high, close FROM historical_candles ORDER BY symbol, date DESC"
                        ).fetchall()
                    grouped: Dict[str, List[tuple]] = {}
                    for sym, h, c in rows:
                        b = grouped.setdefault(sym, [])
                        if len(b) < 760:
                            b.append((float(h or c or 0.0), float(c or 0.0)))
                    sec_1y_buckets: Dict[str, List[float]] = {}
                    sec_3y_buckets: Dict[str, List[float]] = {}
                    for sym, desc in grouped.items():
                        if len(desc) < 200:
                            continue
                        p0 = desc[0][1]
                        if p0 <= 0:
                            continue
                        c_1y = desc[min(251, len(desc) - 1)][1]
                        ret_1y = round(((p0 - c_1y) / c_1y) * 100.0, 2) if c_1y > 0 else None
                        ret_3y = None
                        if len(desc) >= 480:
                            c_3y = desc[min(755, len(desc) - 1)][1]
                            if c_3y > 0:
                                ret_3y = round(((p0 - c_3y) / c_3y) * 100.0, 2)
                        h_3y = max(r[0] for r in desc)
                        dd_3y = round(((p0 - h_3y) / h_3y) * 100.0, 2) if h_3y > 0 else None
                        c_sec = sym_sec_map.get(sym)
                        if c_sec:
                            if ret_1y is not None:
                                sec_1y_buckets.setdefault(c_sec, []).append(ret_1y)
                            if ret_3y is not None:
                                sec_3y_buckets.setdefault(c_sec, []).append(ret_3y)
                        perf_map[sym] = {
                            "ret_1y_pct": ret_1y,
                            "ret_3y_pct": ret_3y,
                            "drawdown_3y_pct": dd_3y,
                            "high_3y": h_3y,
                            "canon_sector": c_sec,
                        }
                    sec_med_1y = {k: round(statistics.median(v), 2) for k, v in sec_1y_buckets.items() if v}
                    sec_med_3y = {k: round(statistics.median(v), 2) for k, v in sec_3y_buckets.items() if v}
                    for sym, p_entry in perf_map.items():
                        cs = p_entry.get("canon_sector")
                        m1 = sec_med_1y.get(cs) if cs else None
                        m3 = sec_med_3y.get(cs) if cs else None
                        p_entry["sector_median_1y_pct"] = m1
                        p_entry["sector_median_3y_pct"] = m3
                        p_entry["alpha_1y_vs_sector_pct"] = round(p_entry["ret_1y_pct"] - m1, 2) if (p_entry.get("ret_1y_pct") is not None and m1 is not None) else None
                        p_entry["alpha_3y_vs_sector_pct"] = round(p_entry["ret_3y_pct"] - m3, 2) if (p_entry.get("ret_3y_pct") is not None and m3 is not None) else None
                _PRICE_PERF_CACHE["ts"] = now_bucket
                _PRICE_PERF_CACHE["data"] = perf_map
                _PRICE_PERF_CACHE["sec_med_1y"] = sec_med_1y if os.path.exists(CACHE_DB_PATH) else {}
                _PRICE_PERF_CACHE["sec_med_3y"] = sec_med_3y if os.path.exists(CACHE_DB_PATH) else {}
            except Exception:
                _PRICE_PERF_CACHE["ts"] = now_bucket
                _PRICE_PERF_CACHE["data"] = {}
                _PRICE_PERF_CACHE["sec_med_1y"] = {}
                _PRICE_PERF_CACHE["sec_med_3y"] = {}
        hit = dict(_PRICE_PERF_CACHE["data"].get(symbol.upper().strip()) or {})
        if hit and not hit.get("canon_sector") and sector:
            cs = _resolve_sector(sector)
            if cs:
                m1 = (_PRICE_PERF_CACHE.get("sec_med_1y") or {}).get(cs)
                m3 = (_PRICE_PERF_CACHE.get("sec_med_3y") or {}).get(cs)
                hit["sector_median_1y_pct"] = m1
                hit["sector_median_3y_pct"] = m3
                if hit.get("ret_1y_pct") is not None and m1 is not None:
                    hit["alpha_1y_vs_sector_pct"] = round(hit["ret_1y_pct"] - m1, 2)
                if hit.get("ret_3y_pct") is not None and m3 is not None:
                    hit["alpha_3y_vs_sector_pct"] = round(hit["ret_3y_pct"] - m3, 2)
    if hit and current_price and current_price > 0 and hit.get("high_3y"):
        h3 = max(float(hit["high_3y"]), float(current_price))
        hit["drawdown_3y_pct"] = round(((current_price - h3) / h3) * 100.0, 2)
    return hit


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

_CAPITAL_MARKETS_RE = re.compile(
    r"\b(capital markets|fintech|exchange|exchanges|depository|broking|brokerage|wealth|asset management|amc|credit rating)\b",
    re.I,
)
_CAPITAL_MARKETS_SYMBOLS = {
    "BSE", "NSE", "CDSL", "MCX", "IEX", "ANGELONE", "GROWW", "360ONE", "5PAISA",
    "CAMS", "KFINTECH", "MOTILALOFS", "NUVAMA", "ANANDRATHI", "PRUDENT",
    "HDFCAMC", "NAM-INDIA", "UTIAMC", "ABSLAMC", "CRISIL", "ICRA", "CAREERP",
}
_BFSI_RE = re.compile(
    r"\b(bank|banking|nbfc|financial services|insurance|housing finance|microfinance)\b",
    re.I,
)


def _is_capital_markets(sector: str, symbol: str = "") -> bool:
    if symbol and symbol.upper().strip() in _CAPITAL_MARKETS_SYMBOLS:
        return True
    return bool(sector and _CAPITAL_MARKETS_RE.search(sector))


def _is_bfsi_sector(sector: str, symbol: str = "") -> bool:
    if _is_capital_markets(sector, symbol):
        return False
    return bool(sector and _BFSI_RE.search(sector))


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
        eff_sector = sector or str(forensic.get("sector") or fund.get("sector") or "")
        if _is_capital_markets(eff_sector, sym) and "capital market" not in eff_sector.lower():
            eff_sector = "Capital Markets"
        matched_sec = self._match_sector_profile(sym, eff_sector)
        peers = self._discover_peers(sym, eff_sector, matched_sec.get("top_long_term_peers", []))
        is_bfsi = _is_bfsi_sector(eff_sector, sym)

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

            # Sector-Relative Multi-Year Price Wealth Creation Audit:
            # Compares 1Y/3Y price performance against the stock's own sector median (Sector Alpha)
            perf = _get_cached_multi_year_perf(sym, lp, eff_sector)
            ret_1y = _num(fund.get("ret_1y_pct")) if _num(fund.get("ret_1y_pct")) is not None else perf.get("ret_1y_pct")
            ret_3y = _num(fund.get("ret_3y_pct")) if _num(fund.get("ret_3y_pct")) is not None else perf.get("ret_3y_pct")
            dd_3y = _num(fund.get("drawdown_3y_pct")) if _num(fund.get("drawdown_3y_pct")) is not None else perf.get("drawdown_3y_pct")
            sec_med_3y = perf.get("sector_median_3y_pct")
            alpha_3y = perf.get("alpha_3y_vs_sector_pct")
            alpha_1y = perf.get("alpha_1y_vs_sector_pct")

            is_multi_year_laggard = False
            laggard_note = ""
            # Flag as laggard only when the stock underperformed both absolutely AND relative to its sector peers
            if ret_3y is not None and ret_3y < 0.0 and (alpha_3y is None or alpha_3y < -10.0):
                is_multi_year_laggard = True
                sec_cmp = f" vs Sector 3Y median {sec_med_3y:+.1f}% (Sector Alpha {alpha_3y:+.1f}%)" if (sec_med_3y is not None and alpha_3y is not None) else ""
                dd_clause = f", {dd_3y:.1f}% off 3Y peak" if (dd_3y is not None and dd_3y <= -25.0) else ""
                laggard_note = f" Sectorial multi-year laggard (3Y return {ret_3y:+.1f}%{sec_cmp}{dd_clause}) — requires sustained sector-relative turnaround."
                penalty = 20 if (ret_3y <= -20.0 or (alpha_3y is not None and alpha_3y <= -35.0)) else 14
                compounder_score = max(25, min(58, compounder_score - penalty))
            elif dd_3y is not None and dd_3y <= -42.0 and (ret_1y is None or ret_1y < 15.0) and (alpha_1y is None or alpha_1y < -10.0):
                is_multi_year_laggard = True
                sec_cmp = f", 1Y Sector Alpha {alpha_1y:+.1f}%" if alpha_1y is not None else ""
                laggard_note = f" Deep sector-relative drawdown ({dd_3y:.1f}% off 3Y peak, 1Y return {ret_1y or 0.0:+.1f}%{sec_cmp}) — structural de-rating caution."
                compounder_score = max(25, min(58, compounder_score - 15))
            elif ret_1y is not None and ret_1y <= -20.0 and (alpha_1y is None or alpha_1y <= -20.0):
                # Steep 1-year sector-relative pullback (e.g. -31% over 1Y while sector peers are positive): cap below STRONG BUY
                sec_cmp = f" vs Sector 1Y median {perf.get('sector_median_1y_pct'):+.1f}% (1Y Sector Alpha {alpha_1y:+.1f}%)" if (perf.get("sector_median_1y_pct") is not None and alpha_1y is not None) else ""
                laggard_note = f" Steep 1-year cyclical correction (1Y return {ret_1y:+.1f}%{sec_cmp}) — await trend stabilization."
                compounder_score = max(35, min(68, compounder_score - 12))

            cagr_raw = 8.0 + (compounder_score - 50) * 0.22
            if rg is not None:
                cagr_raw = (cagr_raw * 0.7) + (max(2.0, min(25.0, rg)) * 0.3)
            if is_multi_year_laggard:
                cagr_raw = min(cagr_raw, 10.5)
            projected_cagr_pct = round(max(4.0, min(24.0, cagr_raw)), 1)

            if is_multi_year_laggard:
                if compounder_score >= 46:
                    verdict = "HOLD / TURNAROUND WATCH (Multi-Year Laggard)"
                else:
                    verdict = "AVOID / UNDERWEIGHT (Structural Underperformer)"
                is_pick = False
            elif compounder_score >= 78:
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
                # 3-Year forward wealth target combines fundamental earnings/BV compounding with partial valuation convergence
                val_gap_pct = ((fair_val - lp) / lp) * 100.0
                if val_gap_pct >= 0:
                    # Undervalued: business CAGR + partial re-rating upside towards intrinsic value
                    rerating_pa = min(6.5, (val_gap_pct / 100.0) * 12.0)
                    effective_cagr_pct = min(28.0, projected_cagr_pct + rerating_pa)
                else:
                    # Trading above static intrinsic value: business CAGR tempered by modest multiple compression
                    compression_pa = min(projected_cagr_pct * 0.55, (abs(val_gap_pct) / 100.0) * 9.0)
                    effective_cagr_pct = max(4.5, projected_cagr_pct - compression_pa)
                lt_target_num = round(lp * ((1.0 + effective_cagr_pct / 100.0) ** 3), 2)
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
                f"basis: {target_basis.replace('_', ' ')}).{laggard_note}"
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
