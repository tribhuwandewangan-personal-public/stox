"""
Zerodha Kite Portfolio Integration & Multi-Agent Action Engine.

Provides secure, strictly READ-ONLY portfolio telemetry from Zerodha Kite Connect:
- Fetches equity delivery holdings and open positions
- Evaluates each holding through both Long-Term Compounder & Short-Term Swing lenses
- Delivers direct actionable advice (Hold Core, Accumulate, Trail Stop, Book Partial Profits)
- Calculates portfolio-level diversification, sector concentration, and risk exposure
- Operates safely in advisory-only mode (ZERO real-capital order placement)
- Keeps all user tokens and holding records private and gitignored.
"""

import os
import re
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH, MIDCAP_250_SYMBOLS_FILE_PATH, ALL_NSE_SYMBOLS_FILE_PATH
from storage.cache_manager import CacheManager
from tools.long_term_strategy import long_term_engine
from tools.portfolio_analytics import (
    classify_sebi_cap_tier,
    compute_atr_position_sizing,
    compute_correlation_matrix,
    compute_hhi_concentration,
    compute_portfolio_var_cvar,
    compute_stock_beta,
    estimate_indian_tax_and_cost_impact,
    extract_daily_returns,
    run_macro_stress_tests,
)
from tools.quote_tools import KITE_TOKEN_PATH

_BFSI_RE = re.compile(
    r"\b(bank|banking|nbfc|financial services|insurance|housing finance|microfinance|capital markets|fintech)\b",
    re.I,
)

LOCAL_HOLDINGS_PATH = os.path.join(PROJECT_ROOT, "storage", "my_holdings.json")


def _safe_float(val, default: float = 0.0) -> float:
    try:
        if val is None or val == "N/A" or val == "":
            return default
        f = float(str(val).replace("Rs.", "").replace(",", "").strip())
        return f if f == f and f not in (float("inf"), float("-inf")) else default
    except Exception:
        return default


def _extract_request_token(text: str) -> str:
    """Accepts the bare token or the full redirect URL containing ?request_token=..."""
    text = (text or "").strip()
    if "request_token=" in text:
        qs = parse_qs(urlparse(text).query)
        return (qs.get("request_token") or [""])[0]
    return text


class KitePortfolioEngine:
    """
    Connects to Zerodha Kite Connect in strictly READ-ONLY advisory mode.
    Reads token from storage/kite_token.json, environment, or .env.
    """
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.api_key = os.getenv("KITE_API_KEY", "").strip()
        self.api_secret = os.getenv("KITE_API_SECRET", "").strip()
        self.token_path = KITE_TOKEN_PATH
        self.local_holdings_path = LOCAL_HOLDINGS_PATH
        self._last_fetch_source: Optional[str] = None
        self._load_saved_credentials()

    def _load_saved_credentials(self):
        """Loads API key from storage/kite_token.json so token and api_key stay paired."""
        if not os.getenv("KITE_ACCESS_TOKEN", "").strip() and os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("api_key"):
                        self.api_key = str(data.get("api_key", "")).strip()
            except Exception:
                pass

    def get_access_token(self) -> str:
        """Retrieves stored access token."""
        env_token = os.getenv("KITE_ACCESS_TOKEN", "").strip()
        if env_token:
            return env_token
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    return json.load(f).get("access_token", "").strip()
            except Exception:
                return ""
        return ""

    def get_connection_status(self) -> Dict[str, Any]:
        """Returns the authentication and data source status for the user."""
        token = self.get_access_token()
        has_local_snapshot = os.path.exists(self.local_holdings_path)

        if not self.api_key:
            return {
                "connected": False,
                "status": "No API Key configured",
                "message": "Set KITE_API_KEY and KITE_API_SECRET in environment or run 'python tools/kite_portfolio.py --login'",
                "has_local_snapshot": has_local_snapshot,
                "data_source": "Local Snapshot" if has_local_snapshot else "None"
            }
        if not token:
            return {
                "connected": False,
                "status": "Token Missing or Expired",
                "message": "Zerodha access tokens expire daily. Run 'python tools/kite_portfolio.py --login' to refresh.",
                "has_local_snapshot": has_local_snapshot,
                "data_source": "Local Snapshot" if has_local_snapshot else "None"
            }

        # Zerodha Kite tokens expire daily (~06:00 IST); verify created_at matches today if sourced from token file
        if not os.getenv("KITE_ACCESS_TOKEN", "").strip() and os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    tok_data = json.load(f)
                    created_raw = tok_data.get("created_at") or tok_data.get("created") or ""
                if created_raw:
                    created_dt = datetime.fromisoformat(str(created_raw)).date()
                    if created_dt != datetime.now().date():
                        return {
                            "connected": False,
                            "status": "Token Expired (Daily Reset)",
                            "message": f"Saved Kite token is from {created_dt}. Run 'python tools/kite_portfolio.py --login' to refresh.",
                            "has_local_snapshot": has_local_snapshot,
                            "data_source": "Local Snapshot" if has_local_snapshot else "None"
                        }
            except Exception:
                pass

        return {
            "connected": True,
            "status": "Ready",
            "message": "Kite Connect access token configured and active.",
            "has_local_snapshot": has_local_snapshot,
            "data_source": "Live Kite API"
        }

    def login_interactive(self) -> bool:
        """Interactive CLI helper to log in to Kite and save access token."""
        print("\n" + "=" * 70)
        print("  🔑 ZERODHA KITE CONNECT — SECURE LOGIN HELPER")
        print("  (Advisory Read-Only Mode: strictly no order placement)")
        print("=" * 70 + "\n")

        api_key = self.api_key or input("Enter Kite API Key: ").strip()
        api_secret = self.api_secret or input("Enter Kite API Secret: ").strip()

        if not api_key or not api_secret:
            print("❌ Error: API Key and API Secret are required.")
            return False

        try:
            from kiteconnect import KiteConnect
        except ImportError:
            print("❌ Error: kiteconnect library not installed. Run: uv pip install kiteconnect")
            return False

        kite = KiteConnect(api_key=api_key)
        login_url = kite.login_url()

        print("1) Open the following URL in your browser and approve the session:\n")
        print(f"   {login_url}\n")
        redirect_input = input("2) After login, paste the full redirected URL (or request_token) here:\n> ").strip()

        request_token = _extract_request_token(redirect_input)
        if not request_token:
            print("❌ Error: No request_token detected.")
            return False

        try:
            session = kite.generate_session(request_token, api_secret=api_secret)
            access_token = session["access_token"]
            user_id = session.get("user_id", "Zerodha User")

            os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
            with open(self.token_path, "w", encoding="utf-8") as f:
                json.dump({
                    "api_key": api_key,
                    "access_token": access_token,
                    "user_id": user_id,
                    "created_at": datetime.now().isoformat()
                }, f, indent=2)

            print(f"\n✅ SUCCESS! Logged in as: {user_id}")
            print(f"🔒 Access token securely stored at: {self.token_path} (gitignored)")
            self.api_key = api_key
            self.api_secret = api_secret
            return True
        except Exception as e:
            print(f"❌ Login failed ({type(e).__name__}): {e}")
            return False

    def fetch_holdings(self, force_live: bool = False) -> List[Dict[str, Any]]:
        """
        Fetches user's equity delivery holdings from Kite Connect.
        Falls back to storage/my_holdings.json if live connection is offline or expired.
        """
        token = self.get_access_token()
        if token and self.api_key:
            try:
                from kiteconnect import KiteConnect
                kite = KiteConnect(api_key=self.api_key)
                kite.set_access_token(token)

                raw_holdings = kite.holdings()
                normalized = []
                for h in raw_holdings:
                    sym = str(h.get("tradingsymbol", "")).upper().strip()
                    if not sym:
                        continue
                    collateral_qty = int(h.get("collateral_quantity", 0) or 0)
                    used_qty = int(h.get("used_quantity", 0) or 0)
                    qty = max(
                        0,
                        int(h.get("quantity", 0) or 0)
                        + int(h.get("t1_quantity", 0) or 0)
                        + collateral_qty
                        - used_qty,
                    )
                    if qty <= 0:
                        continue

                    avg_price = _safe_float(h.get("average_price", 0))
                    ltp = _safe_float(h.get("last_price", 0)) or avg_price
                    invested = round(qty * avg_price, 2)
                    cur_val = round(qty * ltp, 2)
                    pnl = round(cur_val - invested, 2)
                    pnl_pct = round((pnl / invested * 100), 2) if invested > 0 else 0.0

                    normalized.append({
                        "symbol": sym,
                        "exchange": h.get("exchange", "NSE"),
                        "isin": h.get("isin", ""),
                        "quantity": qty,
                        "average_price": avg_price,
                        "last_price": ltp,
                        "invested_value": invested,
                        "current_value": cur_val,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "product": h.get("product", "CNC"),
                        "collateral_quantity": int(h.get("collateral_quantity", 0)),
                        "last_updated": datetime.now().isoformat()
                    })

                # Cache to local snapshot file for offline access (even if empty, so old account holdings are cleared)
                self._last_fetch_source = "Live Kite API"
                self._save_local_snapshot(normalized)
                return normalized
            except Exception as e:
                print(f"⚠️ [Kite Notice] Live holdings fetch failed ({type(e).__name__}: {e}). Checking local snapshot...")

        # Fallback to local snapshot
        self._last_fetch_source = "Local Snapshot" if os.path.exists(self.local_holdings_path) else "None"
        return self._load_local_snapshot()

    def _save_local_snapshot(self, holdings: List[Dict[str, Any]]):
        try:
            os.makedirs(os.path.dirname(self.local_holdings_path), exist_ok=True)
            with open(self.local_holdings_path, "w", encoding="utf-8") as f:
                json.dump({"updated_at": datetime.now().isoformat(), "holdings": holdings}, f, indent=2)
        except Exception:
            pass

    def _load_local_snapshot(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.local_holdings_path):
            return []
        try:
            with open(self.local_holdings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("holdings", [])
        except Exception:
            return []

    def create_sample_holdings_file(self) -> str:
        """Creates a sample my_holdings.json for demonstration / testing."""
        sample = {
            "updated_at": datetime.now().isoformat(),
            "note": "Sample portfolio snapshot for testing and demonstration.",
            "holdings": [
                {
                    "symbol": "RELIANCE",
                    "quantity": 25,
                    "average_price": 2420.50,
                    "last_price": 2540.00,
                    "invested_value": 60512.50,
                    "current_value": 63500.00,
                    "pnl": 2987.50,
                    "pnl_pct": 4.94
                },
                {
                    "symbol": "TCS",
                    "quantity": 15,
                    "average_price": 3850.00,
                    "last_price": 3720.00,
                    "invested_value": 57750.00,
                    "current_value": 55800.00,
                    "pnl": -1950.00,
                    "pnl_pct": -3.38
                },
                {
                    "symbol": "BEL",
                    "quantity": 100,
                    "average_price": 280.00,
                    "last_price": 305.00,
                    "invested_value": 28000.00,
                    "current_value": 30500.00,
                    "pnl": 2500.00,
                    "pnl_pct": 8.93
                },
                {
                    "symbol": "LT",
                    "quantity": 12,
                    "average_price": 3450.00,
                    "last_price": 3610.00,
                    "invested_value": 41400.00,
                    "current_value": 43320.00,
                    "pnl": 1920.00,
                    "pnl_pct": 4.64
                },
                {
                    "symbol": "HDFCBANK",
                    "quantity": 40,
                    "average_price": 1640.00,
                    "last_price": 1710.00,
                    "invested_value": 65600.00,
                    "current_value": 68400.00,
                    "pnl": 2800.00,
                    "pnl_pct": 4.27
                }
            ]
        }
        os.makedirs(os.path.dirname(self.local_holdings_path), exist_ok=True)
        with open(self.local_holdings_path, "w", encoding="utf-8") as f:
            json.dump(sample, f, indent=2)
        return self.local_holdings_path

    def evaluate_portfolio(self, holdings: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Runs multi-agent portfolio diagnostics across all held stocks.
        Synthesizes Long-Term Compounder status with Short-Term Swing actions.
        """
        if holdings is None:
            holdings = self.fetch_holdings()

        if not holdings:
            return {
                "summary": {
                    "total_holdings": 0,
                    "total_invested": 0.0,
                    "current_value": 0.0,
                    "total_pnl": 0.0,
                    "total_pnl_pct": 0.0,
                    "profitable_count": 0,
                    "losing_count": 0,
                    "data_source": "No Holdings Found"
                },
                "holdings": [],
                "sector_breakdown": {},
                "diversification_flags": ["No portfolio holdings detected."],
                "portfolio_analytics": {},
            }

        # Layered sector & name mapping across all NSE -> Midcap 250 -> Curated symbols
        sector_map = {}
        name_map = {}
        midcap_symbols = set()
        from config import NSE_CATALOG_FILE_PATH
        for sym_file in (NSE_CATALOG_FILE_PATH, ALL_NSE_SYMBOLS_FILE_PATH, MIDCAP_250_SYMBOLS_FILE_PATH, SYMBOLS_FILE_PATH):
            if os.path.exists(sym_file):
                try:
                    with open(sym_file, "r", encoding="utf-8") as f:
                        sdata = json.load(f)
                        items = sdata.get("symbols", []) if isinstance(sdata, dict) else sdata
                        is_midcap_file = (sym_file == MIDCAP_250_SYMBOLS_FILE_PATH)
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            sym_u = str(item.get("symbol", "")).upper().strip()
                            if not sym_u:
                                continue
                            if is_midcap_file:
                                midcap_symbols.add(sym_u)
                            sec_val = str(item.get("sector", "")).strip()
                            if sec_val and (sec_val != "Indian Equities" or sym_u not in sector_map):
                                sector_map[sym_u] = sec_val
                            nm_val = str(item.get("name", "")).strip()
                            if nm_val:
                                name_map[sym_u] = nm_val
                except Exception:
                    pass

        bulk_outputs = self.cache_manager.get_latest_agent_outputs_bulk()
        live_quotes = self.cache_manager.get_all_quotes()
        bench_candles = self.cache_manager.get_cached_candles("^NSEI", limit_days=260)
        bench_returns = extract_daily_returns(bench_candles)
        returns_by_symbol: Dict[str, Dict[str, float]] = {}
        try:
            from tools.forensic_financial_engine import ForensicFinancialEngine
            f_engine = ForensicFinancialEngine(cache_manager=self.cache_manager)
        except Exception:
            f_engine = None

        evaluated_holdings = []
        total_invested = 0.0
        current_value = 0.0
        sector_weights = {}

        for h in holdings:
            sym = h.get("symbol", "").upper().strip()
            qty = h.get("quantity", 0)
            avg_p = _safe_float(h.get("average_price", 0))

            # Prefer live quote if available
            q = live_quotes.get(sym, {})
            ltp = _safe_float(q.get("ltp")) or _safe_float(h.get("last_price")) or avg_p

            inv_val = round(qty * avg_p, 2)
            cur_val = round(qty * ltp, 2)
            pnl = round(cur_val - inv_val, 2)
            pnl_pct = round((pnl / inv_val * 100), 2) if inv_val > 0 else 0.0

            total_invested += inv_val
            current_value += cur_val

            # Retrieve agent outputs
            agents = bulk_outputs.get(sym, {})
            synth_res = agents.get("Master Prediction Synthesizer Agent", {}).get("output", {})
            tech_res = agents.get("Technical Analysis Agent", {}).get("output", {})
            fund_res = agents.get("Fundamental Analyst Agent", {}).get("output", {})

            sig = synth_res.get("structured_signal", {})
            short_verdict = str(sig.get("action_verdict", "HOLD")).upper()
            short_conf = sig.get("confidence_rating", "MEDIUM")
            st_target = sig.get("when_to_sell_target", "N/A")
            st_sl = sig.get("stop_loss", "N/A")

            # Fundamental valuation & solvency
            raw_fund = fund_res.get("raw_fundamentals", {})
            sector = sector_map.get(sym) or raw_fund.get("sector") or "Diversified"
            c_name = name_map.get(sym, sym)
            sector_weights[sector] = sector_weights.get(sector, 0.0) + cur_val
            is_bfsi = bool(_BFSI_RE.search(str(sector)))

            pe = raw_fund.get("pe_ratio", "N/A")
            peg = raw_fund.get("peg_ratio", "N/A")
            net_cash = raw_fund.get("net_cash_status", "N/A")
            order_catalyst = raw_fund.get("order_book_catalyst")
            val_assessment = raw_fund.get("valuation_assessment", "Standard")

            # Technical swing & volume telemetry
            raw_tech = tech_res.get("raw_indicators", {})
            ud_ratio = _safe_float(raw_tech.get("up_down_vol_ratio"), 1.0)
            swing_h20 = _safe_float(raw_tech.get("swing_high_20"))
            swing_l20 = _safe_float(raw_tech.get("swing_low_20"))

            # Forensic Governance & Peer Benchmarks (feed into long-term quantitative compounder scoring)
            forensic_grade = "UNAUDITED"
            forensic_flags = []
            peer_verdict = ""
            f_data = None
            if f_engine is not None:
                try:
                    f_data = f_engine.analyze_company(sym, price_override=ltp, sector_override=sector)
                    gov = f_data.get("governance_telemetry", {})
                    forensic_grade = gov.get("governance_grade", "UNAUDITED")
                    forensic_flags = gov.get("governance_flags", [])
                    peer_verdict = f_data.get("peer_benchmarks", {}).get("peer_verdict", "")
                except Exception:
                    f_data = None

            # Evaluate Long-Term Horizon (1-3 Years, quantitative multi-pillar model)
            lt_eval = long_term_engine.evaluate_long_term_stock(
                symbol=sym,
                name=c_name,
                sector=sector,
                last_price=ltp,
                short_verdict=short_verdict,
                fund_data=raw_fund,
                forensic_data=f_data,
            )

            # Generate Specific Direct Actions for User
            # 1. Long-Term Compounder Action:
            lt_action = "CORE HOLD (Maintain long-term allocation)"
            peg_f = _safe_float(peg, -1.0)
            if lt_eval.get("is_top_wealth_pick") or "STRONG BUY" in lt_eval.get("long_term_verdict", ""):
                if 0 < peg_f <= 1.5:
                    lt_action = "💎 TOP COMPOUNDER — ACCUMULATE ON DIPS (Favorable PEG & High CAGR)"
                else:
                    lt_action = "💎 TOP COMPOUNDER — HOLD CORE (Compounding trajectory on track)"
            elif peg_f > 2.5:
                lt_action = "⚠️ EXPENSIVE GROWTH (PEG > 2.5) — Avoid fresh buying; consider trimming on rallies"
            elif (not is_bfsi) and ("LEVERAGE" in str(net_cash).upper() or _safe_float(raw_fund.get("debt_to_equity")) > 150):
                lt_action = "⚡ HIGH LEVERAGE — Review debt profile; cap exposure"

            # 2. Short-Term Swing Action (strictly direction-aware; never celebrate SELL downside targets as profit targets):
            st_target_f = _safe_float(st_target)
            st_sl_f = _safe_float(st_sl)
            swing_action = f"HOLD with trailing stop at {st_sl}"

            if short_verdict == "SELL":
                tgt_txt = f" (downside target Rs. {st_target_f:.2f})" if st_target_f > 0 else ""
                swing_action = f"🔴 SELL SIGNAL ACTIVE{tgt_txt} — Protect capital; review exit or hedge"
            elif short_verdict == "HOLD" and st_target_f > 0 and st_target_f < ltp:
                swing_action = f"🟡 DEFENSIVE HOLD (downside support Rs. {st_target_f:.2f}) — Avoid fresh adds; monitor closely"
            elif st_target_f > ltp and ltp >= st_target_f * 0.985:
                swing_action = f"🎯 TARGET ACHIEVED (Rs. {st_target_f:.2f}) — Book partial profits (30-50%) or tighten stop loss"
            elif 0 < st_sl_f < ltp and ltp <= st_sl_f:
                swing_action = f"🛑 STOP LOSS BREACHED (Rs. {st_sl_f:.2f}) — Protect capital; trim or exit swing exposure"
            elif swing_h20 and ltp >= swing_h20 * 0.988:
                swing_action = f"🚧 NEAR OVERHEAD RESISTANCE (Rs. {swing_h20:.2f}) — Lock partial gains or wait for breakout confirmation"
            elif any("Bearish RSI" in str(p.get("name", "")) for p in tech_res.get("detected_patterns", [])):
                sl_txt = f"Rs. {st_sl_f:.2f}" if st_sl_f > 0 else "defined support"
                swing_action = f"⚠️ BEARISH RSI DIVERGENCE — Momentum fading; tighten stop loss to {sl_txt}"
            elif ud_ratio >= 1.25 and short_verdict in ("BUY", "ACCUMULATE"):
                swing_action = f"🟢 INSTITUTIONAL ACCUMULATION ({ud_ratio:.2f}x) — Add on dips near entry floor"

            if forensic_grade == "HIGH_RISK":
                lt_action = "🚨 HIGH GOVERNANCE / PLEDGE RISK — Trim position; forensic red flags detected"

            # Historical returns, Beta vs Nifty 50, 20D ADV, SEBI Cap Tier & Indian Tax/Cost Impact
            sym_candles = self.cache_manager.get_cached_candles(sym, limit_days=260)
            sym_rets = extract_daily_returns(sym_candles)
            if sym_rets:
                returns_by_symbol[sym] = sym_rets
            vols_20 = [
                float(c.get("VOLUME") or 0)
                for c in sym_candles[-20:]
                if float(c.get("VOLUME") or 0) > 0
            ]
            adv_20d = round(sum(vols_20) / len(vols_20), 1) if vols_20 else None
            beta_vs_nifty = compute_stock_beta(sym_rets, bench_returns)

            mkt_cap_cr = _safe_float(raw_fund.get("market_cap_cr"), -1.0)
            if mkt_cap_cr <= 0:
                raw_mc = _safe_float(raw_fund.get("market_cap"), -1.0)
                mkt_cap_cr = (raw_mc / 1e7) if raw_mc > 1e8 else (raw_mc if raw_mc > 0 else None)
            else:
                mkt_cap_cr = mkt_cap_cr
            cap_tier = classify_sebi_cap_tier(sym, market_cap_cr=mkt_cap_cr, midcap_symbols=midcap_symbols)

            tax_impact = estimate_indian_tax_and_cost_impact(
                quantity=qty,
                avg_price=avg_p,
                sell_price=ltp,
                holding_days=h.get("holding_days"),
            )

            evaluated_holdings.append({
                "symbol": sym,
                "company_name": c_name,
                "sector": sector,
                "cap_tier": cap_tier,
                "quantity": qty,
                "average_price": avg_p,
                "last_price": ltp,
                "invested_value": inv_val,
                "current_value": cur_val,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
                "beta_vs_nifty": beta_vs_nifty,
                "adv_20d": adv_20d,
                "tax_and_cost_impact": tax_impact,
                # Long-Term Strategy Dimensions
                "long_term_verdict": lt_eval.get("long_term_verdict", "HOLD"),
                "long_term_target": lt_eval.get("long_term_target", "N/A"),
                "long_term_upside": lt_eval.get("long_term_upside_pct", "N/A"),
                "economic_moat": lt_eval.get("long_term_moat", "Industry Standard"),
                "long_term_action": lt_action,
                "suggested_peers": lt_eval.get("suggested_long_term_peers", []),
                # Short-Term Swing Dimensions
                "short_term_verdict": short_verdict,
                "short_term_confidence": short_conf,
                "short_term_target": st_target,
                "short_term_stop_loss": st_sl,
                "swing_action": swing_action,
                "institutional_volume_ratio": ud_ratio,
                # Valuation & Solvency
                "pe_ratio": pe,
                "peg_ratio": peg,
                "net_cash_status": net_cash,
                "order_catalyst": order_catalyst,
                # Forensic Governance & Peer Telemetry
                "governance_grade": forensic_grade,
                "governance_flags": forensic_flags,
                "peer_verdict": peer_verdict,
            })

        # Calculate Sector Percentages
        sector_breakdown = {}
        for sec, val in sorted(sector_weights.items(), key=lambda x: -x[1]):
            pct = round((val / current_value * 100), 1) if current_value > 0 else 0.0
            sector_breakdown[sec] = {"value": round(val, 2), "weight_pct": pct}

        # Portfolio-level Quantitative Risk Analytics, Position Sizing & Tax Summary
        weights = {
            h["symbol"]: (h["current_value"] / current_value)
            for h in evaluated_holdings
            if current_value > 0
        }
        for h in evaluated_holdings:
            st_sl_num = _safe_float(h.get("short_term_stop_loss"))
            stop_for_sz = st_sl_num if (0 < st_sl_num < h["last_price"]) else round(h["last_price"] * 0.94, 2)
            h["position_sizing"] = compute_atr_position_sizing(
                portfolio_capital=current_value,
                entry_price=h["last_price"],
                stop_loss=stop_for_sz,
                risk_per_trade_pct=1.0,
                avg_daily_volume=h.get("adv_20d"),
            )

        weighted_betas = [
            (h["beta_vs_nifty"], h["current_value"])
            for h in evaluated_holdings
            if h.get("beta_vs_nifty") is not None and h["current_value"] > 0
        ]
        portfolio_beta = (
            round(sum(b * v for b, v in weighted_betas) / sum(v for _, v in weighted_betas), 2)
            if weighted_betas
            else None
        )
        corr_data = compute_correlation_matrix(returns_by_symbol)
        var_cvar = compute_portfolio_var_cvar(returns_by_symbol, weights, current_value)
        hhi_data = compute_hhi_concentration(weights)

        cap_totals: Dict[str, float] = {"Large Cap": 0.0, "Mid Cap": 0.0, "Small Cap": 0.0}
        for h in evaluated_holdings:
            tier = h.get("cap_tier") or "Small Cap"
            cap_totals[tier] = cap_totals.get(tier, 0.0) + float(h.get("current_value") or 0.0)
        cap_mix = {
            tier: {
                "value": round(val, 2),
                "weight_pct": round(val / current_value * 100.0, 1) if current_value > 0 else 0.0,
            }
            for tier, val in cap_totals.items()
        }
        stress_tests = run_macro_stress_tests(
            evaluated_holdings,
            portfolio_beta,
            {sec: d["weight_pct"] for sec, d in sector_breakdown.items()},
            current_value,
        )

        # Diversification & Concentration Checks
        flags = []
        for h in evaluated_holdings:
            w_pct = (h["current_value"] / current_value * 100) if current_value > 0 else 0
            if w_pct > 25.0:
                flags.append(f"⚠️ High Stock Concentration: **{h['symbol']}** represents {w_pct:.1f}% of total portfolio value.")
        for sec, data in sector_breakdown.items():
            if data["weight_pct"] > 35.0:
                flags.append(f"⚠️ High Sector Concentration: **{sec}** represents {data['weight_pct']:.1f}% of portfolio.")
        for hp in corr_data.get("high_correlation_pairs", [])[:3]:
            flags.append(
                f"🔗 Hidden Correlation Risk: **{hp['pair']}** exhibit {hp['correlation']:.2f} daily return correlation (>= 0.75)."
            )
        if hhi_data.get("hhi", 0.0) > 2500.0 and len(evaluated_holdings) >= 2:
            flags.append(
                f"⚠️ High HHI Concentration: Herfindahl index {hhi_data['hhi']:.0f} (effective {hhi_data['effective_num_stocks']:.1f} equal-weight stocks)."
            )

        if not flags:
            flags.append("✅ Well diversified: No single stock >25%, no sector >35%, and low HHI concentration.")

        portfolio_analytics = {
            "portfolio_beta_vs_nifty": portfolio_beta,
            "hhi_concentration": hhi_data,
            "cap_tier_mix": cap_mix,
            "correlation": corr_data,
            "var_cvar": var_cvar,
            "stress_tests": stress_tests,
            "estimated_liquidation_tax_rs": round(sum(h["tax_and_cost_impact"]["estimated_tax"] for h in evaluated_holdings), 2),
            "estimated_liquidation_costs_rs": round(sum(h["tax_and_cost_impact"]["statutory_costs"] for h in evaluated_holdings), 2),
        }

        total_pnl = round(current_value - total_invested, 2)
        total_pnl_pct = round((total_pnl / total_invested * 100), 2) if total_invested > 0 else 0.0

        profitable_count = sum(1 for h in evaluated_holdings if h["pnl"] > 0)
        losing_count = sum(1 for h in evaluated_holdings if h["pnl"] < 0)

        conn_status = self.get_connection_status()

        return {
            "summary": {
                "total_holdings": len(evaluated_holdings),
                "total_invested": round(total_invested, 2),
                "current_value": round(current_value, 2),
                "total_pnl": total_pnl,
                "total_pnl_pct": total_pnl_pct,
                "profitable_count": profitable_count,
                "losing_count": losing_count,
                "win_rate_pct": round((profitable_count / len(evaluated_holdings) * 100), 1) if evaluated_holdings else 0.0,
                "data_source": self._last_fetch_source or conn_status["data_source"],
                "connection_status": conn_status["status"],
                "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "holdings": evaluated_holdings,
            "sector_breakdown": sector_breakdown,
            "diversification_flags": flags,
            "portfolio_analytics": portfolio_analytics,
        }

    def generate_portfolio_report(
        self,
        output_path: Optional[str] = None,
        holdings: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Generates a comprehensive Markdown report of portfolio holdings,
        diagnostics, long-term compounder status, and swing trading actions.
        """
        eval_data = self.evaluate_portfolio(holdings=holdings)
        summary = eval_data["summary"]
        holdings = eval_data["holdings"]
        sec_bd = eval_data["sector_breakdown"]
        flags = eval_data["diversification_flags"]

        pnl_sign = "+" if summary["total_pnl"] >= 0 else ""
        pnl_badge = "🟢" if summary["total_pnl"] >= 0 else "🔴"

        md = []
        md.append("# 💼 Zerodha Kite Portfolio Diagnostics & Strategic Action Report")
        md.append(f"**As Of**: {summary['as_of']} | **Data Source**: {summary['data_source']} | **Advisory Mode**: Strictly Read-Only  ")
        md.append(f"**Total Holdings**: {summary['total_holdings']} | **Capital Invested**: Rs. {summary['total_invested']:,.2f} | **Current Value**: Rs. {summary['current_value']:,.2f}  ")
        md.append(f"**Unrealized P&L**: {pnl_badge} {pnl_sign}Rs. {summary['total_pnl']:,.2f} ({pnl_sign}{summary['total_pnl_pct']}%) | **Win Rate**: {summary.get('win_rate_pct', 0)}% ({summary['profitable_count']} Winning / {summary['losing_count']} Losing)\n")
        md.append("---")

        # Portfolio Health & Sector Concentration
        md.append("\n## 📊 Portfolio Asset & Sector Allocation")
        md.append("| Sector | Allocation Value | Weight (%) | Diversification Health |")
        md.append("| :--- | :--- | :---: | :--- |")
        for sec, s_info in sec_bd.items():
            health = "🟢 Balanced" if s_info["weight_pct"] <= 30 else ("🟡 Moderate Concentration" if s_info["weight_pct"] <= 40 else "🔴 Heavy Concentration")
            md.append(f"| **{sec}** | Rs. {s_info['value']:,.2f} | {s_info['weight_pct']}% | {health} |")

        md.append("\n**Diversification Diagnostics**:")
        for fl in flags:
            md.append(f"- {fl}")

        pa = eval_data.get("portfolio_analytics") or {}
        if pa:
            md.append("\n## 📈 Portfolio Quantitative Risk, Stress Tests & Tax Impact")
            hhi = pa.get("hhi_concentration", {})
            beta_str = f"{pa['portfolio_beta_vs_nifty']:.2f}x" if pa.get("portfolio_beta_vs_nifty") is not None else "N/A"
            md.append(
                f"- **Portfolio Beta vs Nifty 50**: `{beta_str}` | **HHI Concentration**: `{hhi.get('hhi', 0):.0f}` ({hhi.get('regime', 'N/A')}; effective `{hhi.get('effective_num_stocks', 0):.1f}` equal stocks)"
            )
            var_d = pa.get("var_cvar", {})
            if var_d.get("available"):
                md.append(
                    f"- **1-Day Historical VaR (95% / 99%)**: `{var_d['var_95_pct']:.2f}%` (Rs. {var_d['var_95_rs']:,.0f}) / `{var_d['var_99_pct']:.2f}%` (Rs. {var_d['var_99_rs']:,.0f}) | "
                    f"**CVaR (95%)**: `{var_d['cvar_95_pct']:.2f}%` (Rs. {var_d['cvar_95_rs']:,.0f}) | **Ann. Vol**: `{var_d['annualized_volatility_pct']:.1f}%`"
                )
            cap_mix = pa.get("cap_tier_mix", {})
            cap_str = " | ".join(f"{t}: {d['weight_pct']}%" for t, d in cap_mix.items() if d.get("weight_pct", 0) > 0)
            if cap_str:
                md.append(f"- **SEBI/AMFI Market-Cap Mix**: {cap_str}")
            md.append(
                f"- **Estimated Exit Tax & Statutory Cost Exposure**: Est. Tax Rs. {pa.get('estimated_liquidation_tax_rs', 0):,.0f} + "
                f"NSE CNC Fees Rs. {pa.get('estimated_liquidation_costs_rs', 0):,.0f} *(Finance Act 2024: STCG 20% <12m / LTCG 12.5% >Rs.1.25L >=12m)*"
            )
            if pa.get("stress_tests"):
                md.append("\n| Macro Stress Scenario | Est. Impact (%) | Est. Impact (Rs.) | Channel |")
                md.append("| :--- | :---: | :---: | :--- |")
                for st in pa["stress_tests"]:
                    md.append(
                        f"| {st['scenario']} | `{st['estimated_impact_pct']:+.2f}%` | Rs. {st['estimated_impact_rs']:+,.0f} | {st['note']} |"
                    )

        md.append("\n---\n")

        # Actionable Holdings Master Table
        md.append("## 🎯 Holdings Action Matrix (Long-Term Wealth vs. Short-Term Swing)")
        md.append("| Symbol | Qty | Avg Price | LTP | P&L (%) | Long-Term Rating | 3Y Target | Long-Term Action | Swing Verdict | Swing Action Plan |")
        md.append("| :--- | :---: | :---: | :---: | :---: | :--- | :---: | :--- | :---: | :--- |")

        for h in holdings:
            p_sign = "+" if h["pnl"] >= 0 else ""
            p_badge = "🟢" if h["pnl"] >= 0 else "🔴"
            pnl_str = f"{p_badge} {p_sign}{h['pnl_pct']:.1f}%"

            md.append(
                f"| **{h['symbol']}** | {h['quantity']} | Rs.{h['average_price']:.1f} | Rs.{h['last_price']:.1f} | {pnl_str} "
                f"| {h['long_term_verdict']} | {h['long_term_target']} | {h['long_term_action']} "
                f"| {h['short_term_verdict']} | {h['swing_action']} |"
            )

        md.append("\n---\n")

        # Detailed Stock-by-Stock Strategic Dossier
        md.append("## 🏢 Individual Holdings Deep Dive & Next Steps\n")
        for idx, h in enumerate(holdings, 1):
            md.append(f"### {idx}. {h['symbol']} — {h['company_name']} ({h['sector']})")
            md.append(f"- **Current Position**: {h['quantity']} shares @ Rs. {h['average_price']:.2f} (Inv: Rs. {h['invested_value']:,.2f} | Current: Rs. {h['current_value']:,.2f})")
            md.append(f"- **Unrealized Return**: {h['pnl']:+,.2f} ({h['pnl_pct']:+.2f}%)")
            md.append(f"- **🏛️ Long-Term Wealth Thesis (1-3Y)**: {h['economic_moat']} | 3Y Target: **{h['long_term_target']}** ({h['long_term_upside']})")
            md.append(f"  * **Long-Term Recommendation**: {h['long_term_action']}")
            if h.get("suggested_peers"):
                md.append(f"  * *Top Sector Compounders to compare*: {', '.join(h['suggested_peers'])}")
            md.append(f"- **⚡ Short-Term Swing Setup**: Verdict: **{h['short_term_verdict']}** | Target: {h['short_term_target']} | Protective Stop: {h['short_term_stop_loss']}")
            md.append(f"  * **Immediate Swing Action**: **{h['swing_action']}**")
            md.append(f"- **⚖️ Fundamentals & Solvency**: P/E: {h['pe_ratio']} | PEG: {h['peg_ratio']} | Solvency: {h['net_cash_status']}")
            if h.get("order_catalyst"):
                md.append(f"  * *Order Book / Project Win*: 📦 {h['order_catalyst']}")
            md.append("")

        md.append("---\n")
        md.append("> [!IMPORTANT]\n")
        md.append("> **Risk Disclaimer & Real Capital Notice**: This application operates in strictly advisory, read-only mode. No automated real money transactions are ever placed. Always verify with your own risk tolerance and investment advisor before executing trades.")

        report_content = "\n".join(md)

        # Save to explicit output path (used by tests) or default reports directory
        if output_path:
            out_dir = os.path.dirname(os.path.abspath(output_path))
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            return output_path

        reports_dir = os.path.join(PROJECT_ROOT, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        today_str = datetime.now().strftime("%Y%m%d")
        daily_path = os.path.join(reports_dir, f"Portfolio_Holdings_Analysis_{today_str}.md")
        latest_path = os.path.join(reports_dir, "Portfolio_Holdings_Analysis_latest.md")

        with open(daily_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        with open(latest_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        return latest_path


def main():
    parser = argparse.ArgumentParser(description="Zerodha Kite Portfolio Integration & Multi-Agent Advisory Engine")
    parser.add_argument("--login", action="store_true", help="Interactive helper to log in to Zerodha Kite and store daily token")
    parser.add_argument("--sync", action="store_true", help="Sync live holdings from Kite and print portfolio summary")
    parser.add_argument("--report", action="store_true", help="Generate complete Markdown Portfolio Action Report")
    parser.add_argument("--sample", action="store_true", help="Create a sample my_holdings.json snapshot for demonstration")
    args = parser.parse_args()

    engine = KitePortfolioEngine()

    if args.login:
        engine.login_interactive()
        return

    if args.sample:
        p = engine.create_sample_holdings_file()
        print(f"✅ Created sample holdings file at: {p}")
        return

    eval_data = engine.evaluate_portfolio()
    summary = eval_data["summary"]

    if summary["total_holdings"] == 0:
        print("\nNotice: No holdings found from Kite or storage/my_holdings.json.")
        print("To connect live Kite: run 'python tools/kite_portfolio.py --login'")
        print("To create sample holdings: run 'python tools/kite_portfolio.py --sample'")
        return

    print("\n" + "=" * 80)
    print("  💼 PORTFOLIO DIAGNOSTICS & STRATEGIC ACTIONS")
    print(f"  Data Source: {summary['data_source']} | Mode: Advisory Only")
    print("=" * 80)
    print(f"  Holdings Count: {summary['total_holdings']}")
    print(f"  Total Invested: Rs. {summary['total_invested']:,.2f}")
    print(f"  Current Value:  Rs. {summary['current_value']:,.2f}")
    pnl_sign = "+" if summary["total_pnl"] >= 0 else ""
    print(f"  Unrealized P&L: {pnl_sign}Rs. {summary['total_pnl']:,.2f} ({pnl_sign}{summary['total_pnl_pct']}%)")
    print("=" * 80)

    for h in eval_data["holdings"]:
        print(f"\n[{h['symbol']}] ({h['company_name']}) | Qty: {h['quantity']} | P&L: {h['pnl_pct']:+.1f}%")
        print(f"  🏛️ Long-Term: {h['long_term_action']}")
        print(f"  ⚡ Swing:     {h['swing_action']}")

    rep_path = engine.generate_portfolio_report()
    print(f"\n📄 Full Portfolio Strategy Report generated: {rep_path}\n")


if __name__ == "__main__":
    main()
