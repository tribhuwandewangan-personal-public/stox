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
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, Any, List, Optional
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH
from storage.cache_manager import CacheManager
from tools.long_term_strategy import long_term_engine
from tools.quote_tools import KITE_TOKEN_PATH

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
        self._load_saved_credentials()

    def _load_saved_credentials(self):
        """Loads API key and token from storage/kite_token.json if not present in env."""
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if not self.api_key and data.get("api_key"):
                        self.api_key = data.get("api_key", "").strip()
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
                    qty = int(h.get("quantity", 0)) + int(h.get("t1_quantity", 0))
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
                        "average_price": avg_p,
                        "last_price": ltp,
                        "invested_value": invested,
                        "current_value": cur_val,
                        "pnl": pnl,
                        "pnl_pct": pnl_pct,
                        "product": h.get("product", "CNC"),
                        "collateral_quantity": int(h.get("collateral_quantity", 0)),
                        "last_updated": datetime.now().isoformat()
                    })

                # Cache to local snapshot file for offline access
                if normalized:
                    self._save_local_snapshot(normalized)
                    return normalized
            except Exception as e:
                print(f"⚠️ [Kite Notice] Live holdings fetch failed ({type(e).__name__}: {e}). Checking local snapshot...")

        # Fallback to local snapshot
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
                "diversification_flags": ["No portfolio holdings detected."]
            }

        # Sector mapping from symbols.json
        sector_map = {}
        name_map = {}
        if os.path.exists(SYMBOLS_FILE_PATH):
            try:
                with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
                    sdata = json.load(f)
                    for item in sdata.get("symbols", []):
                        sym_u = item.get("symbol", "").upper()
                        sector_map[sym_u] = item.get("sector", "Other")
                        name_map[sym_u] = item.get("name", sym_u)
            except Exception:
                pass

        bulk_outputs = self.cache_manager.get_latest_agent_outputs_bulk()
        live_quotes = self.cache_manager.get_all_quotes()

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

            sector = sector_map.get(sym, "Diversified")
            c_name = name_map.get(sym, sym)
            sector_weights[sector] = sector_weights.get(sector, 0.0) + cur_val

            # Retrieve agent outputs
            agents = bulk_outputs.get(sym, {})
            synth_res = agents.get("Master Prediction Synthesizer Agent", {}).get("output", {})
            tech_res = agents.get("Technical Analysis Agent", {}).get("output", {})
            fund_res = agents.get("Fundamental Analyst Agent", {}).get("output", {})

            sig = synth_res.get("structured_signal", {})
            short_verdict = sig.get("action_verdict", "HOLD")
            short_conf = sig.get("confidence_rating", "MEDIUM")
            st_target = sig.get("when_to_sell_target", "N/A")
            st_sl = sig.get("stop_loss", "N/A")

            # Fundamental valuation & solvency
            raw_fund = fund_res.get("raw_fundamentals", {})
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

            # Evaluate Long-Term Horizon (1-3 Years)
            lt_eval = long_term_engine.evaluate_long_term_stock(
                symbol=sym,
                name=c_name,
                sector=sector,
                last_price=ltp,
                short_verdict=short_verdict
            )

            # Generate Specific Direct Actions for User
            # 1. Long-Term Compounder Action:
            lt_action = "CORE HOLD (Maintain long-term allocation)"
            if lt_eval.get("is_top_wealth_pick") or "STRONG BUY" in lt_eval.get("long_term_verdict", ""):
                if peg != "N/A" and _safe_float(peg) <= 1.5:
                    lt_action = "💎 TOP COMPOUNDER — ACCUMULATE ON DIPS (Favorable PEG & High CAGR)"
                else:
                    lt_action = "💎 TOP COMPOUNDER — HOLD CORE (Compounding trajectory on track)"
            elif peg != "N/A" and _safe_float(peg) > 2.5:
                lt_action = "⚠️ EXPENSIVE GROWTH (PEG > 2.5) — Avoid fresh buying; consider trimming on rallies"
            elif "LEVERAGE" in str(net_cash).upper() or _safe_float(raw_fund.get("debt_to_equity")) > 150:
                lt_action = "⚡ HIGH LEVERAGE — Review debt profile; cap exposure"

            # 2. Short-Term Swing Action:
            st_target_f = _safe_float(st_target)
            st_sl_f = _safe_float(st_sl)
            swing_action = f"HOLD with trailing stop at {st_sl}"

            if st_target_f and ltp >= st_target_f * 0.985:
                swing_action = f"🎯 TARGET ACHIEVED (Rs. {st_target_f:.2f}) — Book partial profits (30-50%) or tighten stop loss"
            elif st_sl_f and ltp <= st_sl_f:
                swing_action = f"🛑 STOP LOSS BREACHED (Rs. {st_sl_f:.2f}) — Protect capital; trim or exit swing exposure"
            elif swing_h20 and ltp >= swing_h20 * 0.988:
                swing_action = f"🚧 NEAR OVERHEAD RESISTANCE (Rs. {swing_h20:.2f}) — Lock partial gains or wait for breakout confirmation"
            elif any("Bearish RSI" in str(p.get("name", "")) for p in tech_res.get("detected_patterns", [])):
                swing_action = f"⚠️ BEARISH RSI DIVERGENCE — Momentum fading; tighten stop loss to Rs. {st_sl_f:.2f}"
            elif ud_ratio >= 1.25 and short_verdict in ("BUY", "ACCUMULATE"):
                swing_action = f"🟢 INSTITUTIONAL ACCUMULATION ({ud_ratio:.2f}x) — Add on dips near entry floor"

            evaluated_holdings.append({
                "symbol": sym,
                "company_name": c_name,
                "sector": sector,
                "quantity": qty,
                "average_price": avg_p,
                "last_price": ltp,
                "invested_value": inv_val,
                "current_value": cur_val,
                "pnl": pnl,
                "pnl_pct": pnl_pct,
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
            })

        # Calculate Sector Percentages
        sector_breakdown = {}
        for sec, val in sorted(sector_weights.items(), key=lambda x: -x[1]):
            pct = round((val / current_value * 100), 1) if current_value > 0 else 0.0
            sector_breakdown[sec] = {"value": round(val, 2), "weight_pct": pct}

        # Diversification & Concentration Checks
        flags = []
        for h in evaluated_holdings:
            w_pct = (h["current_value"] / current_value * 100) if current_value > 0 else 0
            if w_pct > 25.0:
                flags.append(f"⚠️ High Stock Concentration: **{h['symbol']}** represents {w_pct:.1f}% of total portfolio value.")
        for sec, data in sector_breakdown.items():
            if data["weight_pct"] > 35.0:
                flags.append(f"⚠️ High Sector Concentration: **{sec}** represents {data['weight_pct']:.1f}% of portfolio.")

        if not flags:
            flags.append("✅ Well diversified: No single stock >25% and no sector >35%.")

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
                "data_source": conn_status["data_source"],
                "connection_status": conn_status["status"],
                "as_of": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            },
            "holdings": evaluated_holdings,
            "sector_breakdown": sector_breakdown,
            "diversification_flags": flags
        }

    def generate_portfolio_report(self) -> str:
        """
        Generates a comprehensive Markdown report of portfolio holdings,
        diagnostics, long-term compounder status, and swing trading actions.
        """
        eval_data = self.evaluate_portfolio()
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

        # Save to reports directory
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
