"""
Market Scanner & Outside Stock Discovery Engine
================================================
Scans a wide universe of institutional-grade NSE stocks OUTSIDE of `symbols.json`
to discover top-tier relative strength leaders, institutional accumulation targets,
and fundamentally superior growth compounders.

Key Features:
- Filtered Universe: Automatically excludes symbols already in `symbols.json`.
- Deterministic 5-Pillar Strength Scoring (0 - 100):
    1. Trend & Stage 2 Alignment (Max 25 pts)
    2. Proximity to 52-Week High / Relative Strength (Max 20 pts)
    3. Institutional Volume Footprint (20D Up/Down Ratio & RVOL) (Max 20 pts)
    4. Momentum Quality (Wilder RSI & Velocity) (Max 15 pts)
    5. Fundamental Quality (GARP / PEG, ROE, Leverage) (Max 20 pts)
- Actions: Inspect top candidates, export markdown report, and add directly to watchlist.
- Strictly Read-Only / Advisory Mode (Zero order placement).
"""

import os
import sys
import json
import argparse
import datetime
from typing import List, Dict, Any, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH, CACHE_DB_PATH
from tools.symbol_search_tools import add_symbol_to_json

# Curated institutional universe of ~120 high-liquidity NSE candidates across sectors
DEFAULT_SCANNER_UNIVERSE: List[Dict[str, str]] = [
    # Mega-Cap & Technology
    {"symbol": "TCS", "name": "Tata Consultancy Services Ltd", "sector": "Information Technology"},
    {"symbol": "INFY", "name": "Infosys Ltd", "sector": "Information Technology"},
    {"symbol": "HCLTECH", "name": "HCL Technologies Ltd", "sector": "Information Technology"},
    {"symbol": "WIPRO", "name": "Wipro Ltd", "sector": "Information Technology"},
    {"symbol": "LTM", "name": "LTIMindtree / LTM Ltd", "sector": "Information Technology"},
    {"symbol": "PERSISTENT", "name": "Persistent Systems Ltd", "sector": "Information Technology"},
    {"symbol": "OFSS", "name": "Oracle Financial Services Software", "sector": "Information Technology"},
    {"symbol": "TATACOMM", "name": "Tata Communications Ltd", "sector": "Telecom & Cloud"},
    # Banking & Financial Services
    {"symbol": "AXISBANK", "name": "Axis Bank Ltd", "sector": "Banking & Financial Services"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance Ltd", "sector": "Banking & Financial Services"},
    {"symbol": "BAJAJFINSV", "name": "Bajaj Finserv Ltd", "sector": "Banking & Financial Services"},
    {"symbol": "CHOLAFIN", "name": "Cholamandalam Investment & Finance", "sector": "Banking & Financial Services"},
    {"symbol": "SHRIRAMFIN", "name": "Shriram Finance Ltd", "sector": "Banking & Financial Services"},
    {"symbol": "INDUSINDBK", "name": "IndusInd Bank Ltd", "sector": "Banking & Financial Services"},
    {"symbol": "BANKBARODA", "name": "Bank of Baroda", "sector": "Banking & Financial Services"},
    {"symbol": "CANBK", "name": "Canara Bank", "sector": "Banking & Financial Services"},
    {"symbol": "PFC", "name": "Power Finance Corporation", "sector": "Banking & Financial Services"},
    {"symbol": "RECLTD", "name": "REC Ltd", "sector": "Banking & Financial Services"},
    # Capital Goods, Engineering, Defence & Aerospace
    {"symbol": "HAL", "name": "Hindustan Aeronautics Ltd", "sector": "Aerospace & Defence"},
    {"symbol": "BDL", "name": "Bharat Dynamics Ltd", "sector": "Aerospace & Defence"},
    {"symbol": "COCHINSHIP", "name": "Cochin Shipyard Ltd", "sector": "Defence & Maritime"},
    {"symbol": "GRSE", "name": "Garden Reach Shipbuilders & Engineers", "sector": "Defence & Maritime"},
    {"symbol": "BEML", "name": "BEML Ltd", "sector": "Defence & Heavy Engineering"},
    {"symbol": "SIEMENS", "name": "Siemens Ltd", "sector": "Capital Goods & Electricals"},
    {"symbol": "BHEL", "name": "Bharat Heavy Electricals Ltd", "sector": "Capital Goods & Heavy Electricals"},
    {"symbol": "CUMMINSIND", "name": "Cummins India Ltd", "sector": "Capital Goods & Machinery"},
    {"symbol": "HAVELLS", "name": "Havells India Ltd", "sector": "Consumer Electricals & Cap Goods"},
    {"symbol": "KEI", "name": "KEI Industries Ltd", "sector": "Cables & Electricals"},
    {"symbol": "THERMAX", "name": "Thermax Ltd", "sector": "Energy & Capital Goods"},
    {"symbol": "AIAENG", "name": "AIA Engineering Ltd", "sector": "Industrial Engineering"},
    # Consumer, FMCG & Retail Leaders
    {"symbol": "TITAN", "name": "Titan Company Ltd", "sector": "Consumer & Luxury Retail"},
    {"symbol": "TRENT", "name": "Trent Ltd", "sector": "Consumer & Retail"},
    {"symbol": "VBL", "name": "Varun Beverages Ltd", "sector": "FMCG & Beverages"},
    {"symbol": "DMART", "name": "Avenue Supermarts Ltd (DMart)", "sector": "Consumer & Retail"},
    {"symbol": "ITC", "name": "ITC Ltd", "sector": "FMCG & Diversified"},
    {"symbol": "NESTLEIND", "name": "Nestle India Ltd", "sector": "FMCG & Food Products"},
    {"symbol": "BRITANNIA", "name": "Britannia Industries Ltd", "sector": "FMCG & Food Products"},
    {"symbol": "COLPAL", "name": "Colgate-Palmolive (India) Ltd", "sector": "FMCG & Personal Care"},
    {"symbol": "DABUR", "name": "Dabur India Ltd", "sector": "FMCG & Ayurvedic Care"},
    {"symbol": "MARICO", "name": "Marico Ltd", "sector": "FMCG & Consumer Goods"},
    {"symbol": "TATACONSUM", "name": "Tata Consumer Products Ltd", "sector": "FMCG & Beverages"},
    {"symbol": "ETERNAL", "name": "Eternal Ltd (Zomato)", "sector": "Consumer Tech & Quick Commerce"},
    # Auto & Auto Components
    {"symbol": "MARUTI", "name": "Maruti Suzuki India Ltd", "sector": "Automobiles & Mobility"},
    {"symbol": "M&M", "name": "Mahindra & Mahindra Ltd", "sector": "Automobiles & Mobility"},
    {"symbol": "BAJAJ-AUTO", "name": "Bajaj Auto Ltd", "sector": "Automobiles & Mobility"},
    {"symbol": "HEROMOTOCO", "name": "Hero MotoCorp Ltd", "sector": "Automobiles & Mobility"},
    {"symbol": "TVSMOTOR", "name": "TVS Motor Company Ltd", "sector": "Automobiles & Mobility"},
    {"symbol": "BHARATFORG", "name": "Bharat Forge Ltd", "sector": "Auto Components & Defence"},
    {"symbol": "ENDURANCE", "name": "Endurance Technologies Ltd", "sector": "Auto Components"},
    {"symbol": "TIINDIA", "name": "Tube Investments of India Ltd", "sector": "Auto Components & Engg"},
    {"symbol": "SONACOMS", "name": "Sona BLW Precision Forgings", "sector": "Auto Components & EV"},
    # Energy, Power & Natural Resources
    {"symbol": "NTPC", "name": "NTPC Ltd", "sector": "Power Generation & Utilities"},
    {"symbol": "POWERGRID", "name": "Power Grid Corporation of India", "sector": "Power Transmission"},
    {"symbol": "TATAPOWER", "name": "Tata Power Company Ltd", "sector": "Power & Renewable Energy"},
    {"symbol": "COALINDIA", "name": "Coal India Ltd", "sector": "Mining & Natural Resources"},
    {"symbol": "ONGC", "name": "Oil & Natural Gas Corporation", "sector": "Oil & Gas Exploration"},
    {"symbol": "BPCL", "name": "Bharat Petroleum Corporation Ltd", "sector": "Oil Refining & Marketing"},
    {"symbol": "IOC", "name": "Indian Oil Corporation Ltd", "sector": "Oil Refining & Marketing"},
    {"symbol": "GAIL", "name": "GAIL (India) Ltd", "sector": "Gas Transmission & Distribution"},
    {"symbol": "IGL", "name": "Indraprastha Gas Ltd", "sector": "City Gas Distribution"},
    {"symbol": "MGL", "name": "Mahanagar Gas Ltd", "sector": "City Gas Distribution"},
    # Healthcare, Pharmaceuticals & Diagnostics
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical Industries", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "CIPLA", "name": "Cipla Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "DRREDDY", "name": "Dr. Reddy's Laboratories Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "DIVISLAB", "name": "Divi's Laboratories Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "APOLLOHOSP", "name": "Apollo Hospitals Enterprise Ltd", "sector": "Healthcare & Hospitals"},
    {"symbol": "LUPIN", "name": "Lupin Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "TORNTPHARM", "name": "Torrent Pharmaceuticals Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "MANKIND", "name": "Mankind Pharma Ltd", "sector": "Pharmaceuticals & Healthcare"},
    {"symbol": "MAXHEALTH", "name": "Max Healthcare Institute Ltd", "sector": "Healthcare & Hospitals"},
    {"symbol": "FORTIS", "name": "Fortis Healthcare Ltd", "sector": "Healthcare & Hospitals"},
    # Metals, Mining & Building Materials
    {"symbol": "JSWSTEEL", "name": "JSW Steel Ltd", "sector": "Metals & Mining"},
    {"symbol": "HINDALCO", "name": "Hindalco Industries Ltd", "sector": "Metals & Mining"},
    {"symbol": "JINDALSTEL", "name": "Jindal Steel & Power Ltd", "sector": "Metals & Mining"},
    {"symbol": "VEDL", "name": "Vedanta Ltd", "sector": "Metals & Natural Resources"},
    {"symbol": "ULTRACEMCO", "name": "UltraTech Cement Ltd", "sector": "Cement & Building Materials"},
    {"symbol": "SHREECEM", "name": "Shree Cement Ltd", "sector": "Cement & Building Materials"},
    {"symbol": "DALBHARAT", "name": "Dalmia Bharat Ltd", "sector": "Cement & Building Materials"},
    {"symbol": "PIDILITIND", "name": "Pidilite Industries Ltd", "sector": "Specialty Chemicals & Adhesives"},
    {"symbol": "SRF", "name": "SRF Ltd", "sector": "Specialty Chemicals & Packaging"},
    {"symbol": "ASTRAL", "name": "Astral Ltd", "sector": "Building Materials & Pipes"},
    {"symbol": "DEEPAKNTR", "name": "Deepak Nitrite Ltd", "sector": "Chemicals & Intermediates"},
    {"symbol": "PIIND", "name": "PI Industries Ltd", "sector": "Agro Chemicals & Specialty"},
    {"symbol": "NAVINFLUOR", "name": "Navin Fluorine International", "sector": "Specialty Fluorochemicals"},
    # Telecom, Logistics & Infrastructure
    {"symbol": "INDIGO", "name": "InterGlobe Aviation Ltd (IndiGo)", "sector": "Aviation & Logistics"},
    {"symbol": "CONCOR", "name": "Container Corporation of India", "sector": "Logistics & Transport"},
    {"symbol": "DELHIVERY", "name": "Delhivery Ltd", "sector": "Logistics & Supply Chain"},
    {"symbol": "GMRAIRPORT", "name": "GMR Airports Ltd", "sector": "Airports & Infrastructure"},
    {"symbol": "IRCTC", "name": "Indian Railway Catering & Tourism", "sector": "Railways & Travel Services"},
]


def load_existing_symbols() -> set:
    """Reads symbols.json to find what is already tracked."""
    if not os.path.exists(SYMBOLS_FILE_PATH):
        return set()
    try:
        with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            syms = data.get("symbols", []) if isinstance(data, dict) else data
            return {s["symbol"].upper() for s in syms if isinstance(s, dict) and "symbol" in s}
    except Exception:
        return set()


def get_scan_candidates(custom_symbols: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """
    Returns candidate stocks strictly OUTSIDE of symbols.json.
    """
    existing = load_existing_symbols()
    candidates = []

    if custom_symbols:
        for s in custom_symbols:
            s_clean = s.strip().upper()
            if s_clean and s_clean not in existing:
                candidates.append({"symbol": s_clean, "name": s_clean, "sector": "General"})
        return candidates

    for item in DEFAULT_SCANNER_UNIVERSE:
        sym = item["symbol"].upper()
        if sym not in existing:
            candidates.append(item)
    return candidates


def evaluate_stock_strength(sym: str, meta: Dict[str, str], yf_ticker) -> Optional[Dict[str, Any]]:
    """
    Quantitative 5-pillar relative strength evaluation for an individual stock.
    """
    try:
        import numpy as np
        import pandas as pd

        hist = yf_ticker.history(period="1y", interval="1d")
        if hist.empty or len(hist) < 50:
            return None

        # Clean columns
        close = hist["Close"]
        vol = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]

        last_p = float(close.iloc[-1])
        if last_p <= 0:
            return None

        # 1. Moving Averages & Trend
        sma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else last_p
        sma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else last_p
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50

        # SMA50 slope over last 10 days
        sma50_series = close.rolling(50).mean().dropna()
        sma50_slope = 0.0
        if len(sma50_series) >= 10:
            sma50_slope = float((sma50_series.iloc[-1] - sma50_series.iloc[-10]) / sma50_series.iloc[-10] * 100)

        # 2. 52-Week High & Low
        high_52w = float(high.max())
        low_52w = float(low.min())
        pct_52w = round((last_p - high_52w) / high_52w * 100, 2) if high_52w > 0 else 0.0

        # 3. Institutional Volume Footprint (20D Up/Down Volume Ratio)
        diff = close.diff()
        up_v = vol.where(diff > 0, 0.0).tail(20).sum()
        dn_v = vol.where(diff < 0, 0.0).tail(20).sum()
        ud_ratio = round(float(up_v / (dn_v + 1e-5)), 2) if dn_v > 0 else 1.0

        # Relative Volume (RVOL)
        vol_ma20 = float(vol.rolling(20).mean().iloc[-1]) if len(vol) >= 20 else float(vol.iloc[-1])
        rvol = round(float(vol.iloc[-1] / (vol_ma20 + 1e-5)), 2)

        # 4. Wilder RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / (loss + 1e-9)
        rsi_14 = round(float(100 - (100 / (1 + rs.iloc[-1]))), 1)

        # 5. Fundamental Metrics (Read-only via ticker.info)
        info = {}
        try:
            info = yf_ticker.info or {}
        except Exception:
            info = {}

        pe_val = info.get("trailingPE") or info.get("forwardPE")
        raw_peg = info.get("pegRatio") or info.get("trailingPegRatio")
        eg_val = info.get("earningsGrowth")
        rg_val = info.get("revenueGrowth")
        roe_val = info.get("returnOnEquity")
        de_val = info.get("debtToEquity")

        # Normalize PEG
        peg = None
        if raw_peg is not None and isinstance(raw_peg, (int, float)) and raw_peg > 0:
            peg = round(float(raw_peg), 2)
        elif pe_val and isinstance(pe_val, (int, float)) and pe_val > 0:
            if eg_val and isinstance(eg_val, (int, float)) and eg_val > 0.02:
                eg_pct = min(eg_val * 100.0, 100.0)
                peg = round(pe_val / eg_pct, 2)
            elif rg_val and isinstance(rg_val, (int, float)) and rg_val > 0.05:
                rg_pct = min(rg_val * 100.0, 100.0)
                peg = round(pe_val / rg_pct, 2)

        # ── Quantitative Strength Score Calculation (0 - 100) ─────────────────
        score = 0
        signals = []

        # Pillar 1: Trend Alignment (Max 25 pts)
        if last_p > sma50 > sma200:
            score += 20
            signals.append("Stage 2 Bullish Trend (P > SMA50 > SMA200)")
        elif last_p > sma50:
            score += 10
            signals.append("Above 50-day SMA")
        elif last_p > sma200:
            score += 5

        if sma50_slope > 0.2:
            score += 5
            signals.append(f"Rising 50D Moving Average (+{sma50_slope:.1f}%)")

        # Pillar 2: 52-Week High Proximity (Max 20 pts)
        if -10.0 <= pct_52w <= -2.0:
            score += 20
            signals.append(f"Prime Leader High Proximity ({pct_52w:+.1f}%)")
        elif -20.0 <= pct_52w < -10.0:
            score += 14
            signals.append(f"Constructive Dip ({pct_52w:+.1f}%)")
        elif -30.0 <= pct_52w < -20.0:
            score += 6
        elif pct_52w < -35.0:
            score -= 5

        # Pillar 3: Institutional Volume Footprint (Max 20 pts)
        if ud_ratio >= 1.30:
            score += 15
            signals.append(f"Institutional Accumulation ({ud_ratio:.2f}x 20D U/D)")
        elif ud_ratio >= 1.10:
            score += 8
            signals.append(f"Positive Money Flow ({ud_ratio:.2f}x U/D)")
        elif ud_ratio <= 0.75:
            score -= 5
            signals.append(f"Institutional Distribution ({ud_ratio:.2f}x U/D)")

        if rvol >= 1.25:
            score += 5
            signals.append(f"Volume Surge (RVOL {rvol:.1f}x)")

        # Pillar 4: Momentum Quality (Max 15 pts)
        if 55.0 <= rsi_14 <= 70.0:
            score += 15
            signals.append(f"Strong Bullish Momentum (RSI {rsi_14:.1f})")
        elif 48.0 <= rsi_14 < 55.0:
            score += 8
            signals.append(f"Neutral-Positive Momentum (RSI {rsi_14:.1f})")
        elif rsi_14 > 75.0:
            score += 4
            signals.append(f"Overextended / Extended RSI ({rsi_14:.1f})")

        # Pillar 5: Fundamental Quality (Max 20 pts)
        if peg is not None:
            if 0 < peg <= 1.2:
                score += 10
                signals.append(f"Superior PEG ({peg:.2f}x)")
            elif 0 < peg <= 1.8:
                score += 7
                signals.append(f"Reasonable PEG ({peg:.2f}x)")
            elif peg > 2.5:
                score -= 3
        elif pe_val and isinstance(pe_val, (int, float)) and 0 < pe_val <= 30:
            score += 6

        if roe_val and isinstance(roe_val, (int, float)) and roe_val >= 0.15:
            score += 5
            signals.append(f"High Capital Efficiency (ROE {roe_val*100:.1f}%)")

        if de_val is not None and isinstance(de_val, (int, float)):
            if de_val <= 50.0:   # <= 0.5x D/E (yfinance returns % often)
                score += 5
                signals.append("Low Debt / Strong Balance Sheet")
            elif de_val > 150.0:
                score -= 5

        # Forensic Due Diligence & Governance Quality Overlay
        forensic_grade = "SOUND"
        forensic_verdict = "UNAUDITED"
        intrinsic_fair_val = "N/A"
        mos_pct_val = None
        try:
            from tools.forensic_financial_engine import ForensicFinancialEngine
            forensic_engine = ForensicFinancialEngine()
            f_res = forensic_engine.analyze_company(sym, price_override=last_p)
            gov = f_res.get("governance_telemetry", {})
            forensic_grade = gov.get("governance_grade", "SOUND")
            forensic_verdict = f_res.get("verdict", "N/A")
            v_met = f_res.get("valuation_metrics", {})
            fair_v = v_met.get("intrinsic_fair_value") or f_res.get("fair_value")
            if fair_v is not None and isinstance(fair_v, (int, float)):
                intrinsic_fair_val = round(float(fair_v), 2)
            mos_pct_val = v_met.get("margin_of_safety_pct") or f_res.get("margin_of_safety_pct")

            # Intrinsic Valuation bonus / penalty
            if mos_pct_val is not None and isinstance(mos_pct_val, (int, float)):
                if mos_pct_val >= 15.0:
                    score += 8
                    signals.append(f"Deep Margin of Safety (+{mos_pct_val:.0f}% vs Intrinsic Value)")
                elif mos_pct_val <= -20.0:
                    score -= 8
                    signals.append(f"Price Stretched vs Intrinsic ({mos_pct_val:.0f}% Overvalued)")

            # Governance penalty / reward
            if forensic_grade == "HIGH_RISK":
                score -= 20
                signals.append("⚠️ HIGH RISK Governance / Promoter Pledge Warning")
            elif forensic_grade == "SOUND":
                score += 3
                signals.append("Clean Governance & Promoter Integrity")

            # Peer Relative Valuation context
            peers = f_res.get("peer_benchmarks", {})
            peer_comp = peers.get("peer_comparison", {})
            if peer_comp.get("pe_vs_peers") == "CHEAPER" and peer_comp.get("roe_vs_peers") == "SUPERIOR":
                score += 5
                signals.append("Undervalued vs Sector Peers with Superior ROE")
        except Exception:
            pass

        # Clamp score between 0 and 100
        score = max(0, min(100, score))

        # Strength Tier
        if score >= 80:
            tier = "⭐ TOP LEADER"
        elif score >= 70:
            tier = "🟢 STRONG ACCUMULATION"
        elif score >= 60:
            tier = "🟡 WATCHLIST CANDIDATE"
        else:
            tier = "⚪ CONSOLIDATING"

        return {
            "symbol": sym,
            "name": meta.get("name", sym),
            "sector": meta.get("sector", "General"),
            "strength_score": score,
            "tier": tier,
            "last_price": round(last_p, 2),
            "high_52w": round(high_52w, 2),
            "low_52w": round(low_52w, 2),
            "pct_from_52w_high": pct_52w,
            "rsi_14": rsi_14,
            "up_down_vol_ratio": ud_ratio,
            "rvol": rvol,
            "pe_ratio": round(pe_val, 2) if isinstance(pe_val, (int, float)) else "N/A",
            "peg_ratio": peg if peg is not None else "N/A",
            "intrinsic_fair_value": intrinsic_fair_val,
            "margin_of_safety_pct": mos_pct_val,
            "roe_pct": round(roe_val * 100, 1) if isinstance(roe_val, (int, float)) else "N/A",
            "forensic_verdict": forensic_verdict,
            "governance_grade": forensic_grade,
            "signals": signals,
            "evaluated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    except Exception as e:
        return None


def run_market_scan(
    custom_symbols: Optional[List[str]] = None,
    min_score: int = 60,
    top_n: int = 15,
    max_scan_count: int = 60
) -> List[Dict[str, Any]]:
    """
    Scans candidates outside symbols.json and returns ranked leaders.
    """
    import yfinance as yf

    candidates = get_scan_candidates(custom_symbols)
    if not candidates:
        return []

    # Limit scan count to avoid long timeouts on free feeds
    to_scan = candidates[:max_scan_count]
    results = []

    print(f"🔍 Market Scanner starting: Evaluating {len(to_scan)} stocks outside symbols.json...")

    from tools.ticker_validator import build_yf_candidates
    for item in to_scan:
        sym = item["symbol"]
        ticker_str = build_yf_candidates(sym)[0]
        try:
            t = yf.Ticker(ticker_str)
            res = evaluate_stock_strength(sym, item, t)
            if res and res["strength_score"] >= min_score:
                results.append(res)
                print(f"  ✨ Discovered: {sym:12} | Score: {res['strength_score']:2d}/100 | {res['tier']} | Gap: {res['pct_from_52w_high']:+.1f}%")
        except Exception:
            continue

    # Sort descending by composite strength score
    results.sort(key=lambda x: (x["strength_score"], -abs(x["pct_from_52w_high"])), reverse=True)
    top_results = results[:top_n]

    # Cache scan results in SQLite kv_state
    _cache_scan_results(top_results)

    # Generate Markdown Report
    _generate_markdown_report(top_results, scanned_count=len(to_scan))

    return top_results


def _cache_scan_results(results: List[Dict[str, Any]]):
    """Saves scanner results into storage/cache.db kv_state."""
    import sqlite3
    from contextlib import closing
    try:
        os.makedirs(os.path.dirname(CACHE_DB_PATH), exist_ok=True)
        with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
            with conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS kv_state (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMP)"
                )
                payload = json.dumps({
                    "timestamp": datetime.datetime.now().isoformat(),
                    "count": len(results),
                    "stocks": results
                })
                conn.execute(
                    "INSERT OR REPLACE INTO kv_state (key, value, updated_at) VALUES (?, ?, ?)",
                    ("market_scanner_latest", payload, datetime.datetime.now().isoformat())
                )
    except Exception as e:
        print(f"⚠️ Failed to cache market scanner results: {e}")


def get_latest_cached_scan() -> Dict[str, Any]:
    """Retrieves the most recent market scanner results from SQLite."""
    import sqlite3
    from contextlib import closing
    try:
        if not os.path.exists(CACHE_DB_PATH):
            return {"stocks": [], "timestamp": None}
        with closing(sqlite3.connect(CACHE_DB_PATH)) as conn:
            row = conn.execute(
                "SELECT value FROM kv_state WHERE key = 'market_scanner_latest'"
            ).fetchone()
            if row and row[0]:
                return json.loads(row[0])
    except Exception:
        pass
    return {"stocks": [], "timestamp": None}


def _generate_markdown_report(results: List[Dict[str, Any]], scanned_count: int):
    """Creates a comprehensive markdown report in reports/."""
    reports_dir = os.path.join(PROJECT_ROOT, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    report_path = os.path.join(reports_dir, "Daily_Market_Scan_latest.md")

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    md = [
        f"# 🔭 Daily Market Scanner — Outside Universe Discovery",
        f"> **Generated at:** {now_str} | **Universe Scanned:** {scanned_count} institutional non-watchlist stocks",
        f"> **Filter Criterion:** Minimum Strength Score ≥ 60/100 | Stage 2 Uptrend + Volume Footprint + Relative Strength",
        "",
        "---",
        "",
        "| Rank | Symbol | Company | Sector | LTP | Strength Score | Tier | % from 52W High | 20D Inst Flow | RSI | PEG | Intrinsic Value | Top Signals |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|"
    ]

    for idx, r in enumerate(results, 1):
        top_sigs = "; ".join(r["signals"][:2]) if r["signals"] else "Strong alignment"
        peg_disp = f"{r['peg_ratio']}x" if r['peg_ratio'] != "N/A" else "N/A"
        iv_disp = f"Rs. {r['intrinsic_fair_value']}" if r.get("intrinsic_fair_value") not in ("N/A", None) else "N/A"
        if r.get("margin_of_safety_pct") is not None:
            m = r["margin_of_safety_pct"]
            iv_disp += f" ({'+' if m > 0 else ''}{m:.0f}%)"
        md.append(
            f"| {idx} | **{r['symbol']}** | {r['name']} | {r['sector']} | Rs. {r['last_price']:,.2f} | "
            f"**{r['strength_score']}/100** | {r['tier']} | {r['pct_from_52w_high']:+.1f}% | "
            f"{r['up_down_vol_ratio']:.2f}x | {r['rsi_14']:.1f} | {peg_disp} | {iv_disp} | {top_sigs} |"
        )

    md.append("")
    md.append("---")
    md.append("### 💡 Recommended Next Actions")
    md.append("1. **Add high-conviction leaders** to your active watchlist using the Dashboard **Market Scanner** or CLI:")
    md.append("   ```powershell")
    md.append("   python -m tools.market_scanner --add-to-watchlist <SYMBOL>")
    md.append("   ```")
    md.append("2. Running complete multi-agent analysis on newly added stocks will queue them for deep RAG synthesis and hedge calculations.")
    md.append("")
    md.append("*Strictly Advisory & Read-Only Engine. No order placement or real-money execution.*")

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        print(f"📄 Scan report written to: {report_path}")
    except Exception as e:
        print(f"⚠️ Could not write report: {e}")


def main():
    parser = argparse.ArgumentParser(description="Market Scanner & Stock Discovery Engine (NSE)")
    parser.add_argument("--top", type=int, default=10, help="Number of top candidates to report (default: 10)")
    parser.add_argument("--min-score", type=int, default=60, help="Minimum strength score (default: 60)")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated custom symbols to scan")
    parser.add_argument("--max-scan", type=int, default=40, help="Max candidates to scan in one batch (default: 40)")
    parser.add_argument("--add-to-watchlist", type=str, default=None, help="Add a discovered symbol to symbols.json")
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    # Direct Watchlist Addition
    if args.add_to_watchlist:
        sym = args.add_to_watchlist.strip().upper()
        # Find meta from default universe
        meta = next((item for item in DEFAULT_SCANNER_UNIVERSE if item["symbol"] == sym), None)
        cname = meta["name"] if meta else sym
        csec = meta["sector"] if meta else "General"
        res = add_symbol_to_json(symbol=sym, name=cname, sector=csec, exchange="NSE")
        print(f"✅ Watchlist Update: {res}")
        return

    custom_syms = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    results = run_market_scan(
        custom_symbols=custom_syms,
        min_score=args.min_score,
        top_n=args.top,
        max_scan_count=args.max_scan
    )

    if args.json:
        print(json.dumps(results, indent=2))
        return

    print("\n" + "="*80)
    print(f"🏆 TOP {len(results)} MARKET LEADERS DISCOVERED (Outside symbols.json)")
    print("="*80)
    for idx, r in enumerate(results, 1):
        print(f"{idx:2d}. {r['symbol']:12} | Score: {r['strength_score']:2d}/100 | {r['tier']}")
        print(f"    LTP: Rs.{r['last_price']:,.2f} | 52W Gap: {r['pct_from_52w_high']:+.1f}% | 20D Inst Flow: {r['up_down_vol_ratio']:.2f}x | RSI: {r['rsi_14']}")
        print(f"    Signals: {', '.join(r['signals'][:3])}")
        print("-" * 80)


if __name__ == "__main__":
    main()
