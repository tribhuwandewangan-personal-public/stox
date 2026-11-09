"""
Events & Catalyst Engine for NSE Equities.
Aggregates upcoming corporate events (Earnings dates, Dividends, Splits, Board Meetings)
and major macroeconomic catalysts (RBI MPC decisions, US Fed FOMC, CPI/GDP releases)
to guide swing-trading horizons, risk-management, and catalyst-driven trading.
"""

import os
import sys
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import CACHE_DB_PATH
from storage.cache_manager import CacheManager
from tools.yf_quiet import silence_yfinance_logging

silence_yfinance_logging()


class EventsEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.db_path = self.cache_manager.db_path
        self._init_events_table()

    def _init_events_table(self):
        with self.cache_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events_cache (
                    symbol TEXT PRIMARY KEY,
                    updated_at TEXT,
                    events_data TEXT
                )
            """)
            conn.commit()

    def get_upcoming_macro_events(self) -> List[Dict[str, Any]]:
        """
        Returns scheduled high-impact macroeconomic events and policy meetings.
        Provides date, impact level, and affected sectors. Past events are dropped.
        """
        events = [
            {
                "event_name": "India CPI Inflation Release (MoM/YoY)",
                "date": "2026-11-12",
                "impact": "High",
                "affected_sectors": ["Banking", "FMCG", "Automobile"],
                "note": "Determines interest rate path and household consumption sentiment."
            },
            {
                "event_name": "India WPI Wholesale Inflation",
                "date": "2026-11-14",
                "impact": "Medium",
                "affected_sectors": ["Manufacturing", "Chemicals", "Metals"],
                "note": "Measures input cost pressure on manufacturing margins."
            },
            {
                "event_name": "India Q2 GDP Growth Data Release",
                "date": "2026-11-30",
                "impact": "High",
                "affected_sectors": ["All Sectors", "Capital Goods", "Infra"],
                "note": "Broad macro barometer for corporate CAPEX and earnings expansion."
            },
            {
                "event_name": "RBI MPC Monetary Policy & Rate Decision",
                "date": "2026-12-06",
                "impact": "Critical",
                "affected_sectors": ["Banking", "Real Estate", "Auto", "NBFCs"],
                "note": "Repo rate decision, stance, and liquidity commentary."
            },
            {
                "event_name": "US Federal Reserve FOMC Rate Decision",
                "date": "2026-12-11",
                "impact": "Critical",
                "affected_sectors": ["IT & Tech", "Pharma", "FII Inflows"],
                "note": "Key driver of global liquidity, dollar index (DXY), and FII flows."
            },
            {
                "event_name": "OPEC+ Global Oil Production Review",
                "date": "2026-12-15",
                "impact": "High",
                "affected_sectors": ["Energy", "Oil & Gas", "Paints", "Aviation"],
                "note": "Dictates Brent crude price trajectory and petrochemical refining margins."
            }
        ]
        today = datetime.now().strftime("%Y-%m-%d")
        return [e for e in events if e["date"] >= today]

    def _get_curated_corporate_calendar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Curated (hand-maintained, NOT live-verified) corporate calendar for some high-visibility NSE stocks.
        Returns None when the symbol is not curated or the curated earnings date has already passed.
        """
        sym = symbol.upper().strip()
        calendar_map = {
            "RELIANCE": {
                "earnings_date": "2026-11-18",
                "earnings_quarter": "Q2 FY27 Financial Results",
                "dividend_ex_date": "2026-11-28",
                "dividend_amount": "Rs. 10.00 / share",
                "corporate_action": "Board Meeting & Strategic Energy Expansion Update",
                "impact": "High Volatility Catalyst"
            },
            "HDFCBANK": {
                "earnings_date": "2026-11-15",
                "earnings_quarter": "Q2 FY27 Earnings & NIM Update",
                "dividend_ex_date": "2026-12-10",
                "dividend_amount": "Rs. 19.50 / share",
                "corporate_action": "Analyst & Investor Meet - Deposit Growth Guidance",
                "impact": "High Impact on Nifty Financials"
            },
            "ICICIBANK": {
                "earnings_date": "2026-11-14",
                "earnings_quarter": "Q2 FY27 Financial Results",
                "dividend_ex_date": "2026-12-05",
                "dividend_amount": "Rs. 8.00 / share",
                "corporate_action": "Credit Growth & Asset Quality Disclosure",
                "impact": "High Sector Catalyst"
            },
            "TATAMOTORS": {
                "earnings_date": "2026-11-16",
                "earnings_quarter": "Q2 FY27 Commercial & PV Results",
                "dividend_ex_date": "2026-12-15",
                "dividend_amount": "Rs. 6.00 / share",
                "corporate_action": "JLR Global Orderbook & EV Delivery Telemetry",
                "impact": "High Auto Sector Catalyst"
            },
            "SBIN": {
                "earnings_date": "2026-11-12",
                "earnings_quarter": "Q2 FY27 Net Profit & NPA Review",
                "dividend_ex_date": "2026-12-08",
                "dividend_amount": "Rs. 13.70 / share",
                "corporate_action": "Capital Adequacy & Infra Credit Pipeline Announcement",
                "impact": "Critical Banking Catalyst"
            },
            "BHARTIARTL": {
                "earnings_date": "2026-11-17",
                "earnings_quarter": "Q2 FY27 ARPU & 5G Rollout Metrics",
                "dividend_ex_date": "2026-12-20",
                "dividend_amount": "Rs. 4.00 / share",
                "corporate_action": "Africa Subsidiary Performance Review",
                "impact": "Telecom Sector Driver"
            },
            "LT": {
                "earnings_date": "2026-11-19",
                "earnings_quarter": "Q2 FY27 Order Inflow & Margin Review",
                "dividend_ex_date": "2026-12-14",
                "dividend_amount": "Rs. 28.00 / share",
                "corporate_action": "Middle East EPC & Hydrocarbon Orderbook Briefing",
                "impact": "Capital Goods Benchmark"
            },
            "TATASTEEL": {
                "earnings_date": "2026-11-20",
                "earnings_quarter": "Q2 FY27 Global Steel Delivery & Spreads",
                "dividend_ex_date": "2026-12-18",
                "dividend_amount": "Rs. 3.60 / share",
                "corporate_action": "UK Green Transition Electric Arc Furnace Progress",
                "impact": "Metals Sector Momentum"
            },
            "DIXON": {
                "earnings_date": "2026-11-14",
                "earnings_quarter": "Q2 FY27 Electronics Manufacturing Scale",
                "dividend_ex_date": "2026-12-12",
                "dividend_amount": "Rs. 5.00 / share",
                "corporate_action": "Smartphone & IT Hardware PLI Expansion",
                "impact": "High-Beta EMS Catalyst"
            },
            "KAYNES": {
                "earnings_date": "2026-11-21",
                "earnings_quarter": "Q2 FY27 PCB & Automotive Electronics Results",
                "dividend_ex_date": "2026-12-22",
                "dividend_amount": "Rs. 2.50 / share",
                "corporate_action": "OSAT Semiconductor Packaging Facility Commissioning",
                "impact": "Semiconductor Sector Driver"
            },
            "BSE": {
                "earnings_date": "2026-11-13",
                "earnings_quarter": "Q2 FY27 Derivatives Volume & Clearing Revenue",
                "dividend_ex_date": "2026-12-16",
                "dividend_amount": "Rs. 15.00 / share",
                "corporate_action": "Options Expiry Turnover & Listing Fees Growth",
                "impact": "Capital Markets Driver"
            },
            "CDSL": {
                "earnings_date": "2026-11-16",
                "earnings_quarter": "Q2 FY27 Demat Account Addition & Annual Issuer Charges",
                "dividend_ex_date": "2026-12-19",
                "dividend_amount": "Rs. 12.00 / share",
                "corporate_action": "Active Demat Milestones & Transaction Volume Report",
                "impact": "Market Infrastructure Driver"
            },
            "MOTHERSON": {
                "earnings_date": "2026-11-13",
                "earnings_quarter": "Q2 FY27 Consolidated Financial Results",
                "dividend_ex_date": "2026-12-18",
                "dividend_amount": "Rs. 0.65 / share",
                "corporate_action": "Global Wiring Harness Orderbook & M&A Synergy Review",
                "impact": "Auto Ancillary Momentum Catalyst"
            },
            "HAPPSTMNDS": {
                "earnings_date": "2026-11-14",
                "earnings_quarter": "Q2 FY27 Financial Results & GenAI Business Review",
                "dividend_ex_date": "2026-12-04",
                "dividend_amount": "Rs. 3.25 / share",
                "corporate_action": "Strategic Digital Transformation & IT Capex Update",
                "impact": "Midcap IT Turnaround Catalyst"
            },
            "SUPRIYA": {
                "earnings_date": "2026-11-15",
                "earnings_quarter": "Q2 FY27 Financial Results & USFDA Update",
                "dividend_ex_date": "2026-12-08",
                "dividend_amount": "Rs. 1.20 / share",
                "corporate_action": "API Capacity Expansion & CDMO Pipeline Review",
                "impact": "Pharma Smallcap High-Beta Catalyst"
            },
            "TANLA": {
                "earnings_date": "2026-11-18",
                "earnings_quarter": "Q2 FY27 Enterprise CPaaS Results",
                "dividend_ex_date": "2026-12-15",
                "dividend_amount": "Rs. 6.00 / share",
                "corporate_action": "Wisely OTT & Enterprise Messaging Volume Disclosures",
                "impact": "CPaaS Margin Rebound Watch"
            },
            "TECHM": {
                "earnings_date": "2026-11-12",
                "earnings_quarter": "Q2 FY27 Earnings & Turnaround Margin Roadmap",
                "dividend_ex_date": "2026-11-25",
                "dividend_amount": "Rs. 33.00 / share",
                "corporate_action": "Project Fortius Margin Recovery & Telecom Deal Wins",
                "impact": "High Impact Tier-1 IT Catalyst"
            },
            "GROWW": {
                "earnings_date": "2026-11-22",
                "earnings_quarter": "Q2 FY27 Financial Review & Active NSE Client Addition",
                "dividend_ex_date": "2026-12-28",
                "dividend_amount": "Pre-IPO Phase",
                "corporate_action": "India Redomiciling & WealthTech Market Share Milestones",
                "impact": "Fintech & Broking Moat Driver"
            },
            "NSE": {
                "earnings_date": "2026-11-20",
                "earnings_quarter": "Q2 FY27 Financial Results & Index Turnover",
                "dividend_ex_date": "2026-12-22",
                "dividend_amount": "Rs. 25.00 / share",
                "corporate_action": "IPO Listing Roadmap & Equity Derivatives Market Share",
                "impact": "Market Infrastructure Moat Driver"
            },
            "POLYCAB": {
                "earnings_date": "2026-11-19",
                "earnings_quarter": "Q2 FY27 Cables & FMEG Volume Growth",
                "dividend_ex_date": "2026-12-14",
                "dividend_amount": "Rs. 30.00 / share",
                "corporate_action": "Domestic Infra & International Export Expansion",
                "impact": "Cables Benchmark Catalyst"
            },
            "BEL": {
                "earnings_date": "2026-11-11",
                "earnings_quarter": "Q2 FY27 Defence Electronics Order Execution",
                "dividend_ex_date": "2026-12-05",
                "dividend_amount": "Rs. 1.80 / share",
                "corporate_action": "MoD Radar & Electronic Warfare Contract Update",
                "impact": "Defence PSU Benchmark"
            },
            "COFORGE": {
                "earnings_date": "2026-11-15",
                "earnings_quarter": "Q2 FY27 IT Services & BFS Orderbook",
                "dividend_ex_date": "2026-11-28",
                "dividend_amount": "Rs. 19.00 / share",
                "corporate_action": "Cigniti Acquisition Synergies & Large Deal Announcements",
                "impact": "Tier-2 IT Growth Leader"
            },
            "MUTHOOTFIN": {
                "earnings_date": "2026-11-17",
                "earnings_quarter": "Q2 FY27 Gold Loan AUM & Spread Update",
                "dividend_ex_date": "2026-12-10",
                "dividend_amount": "Rs. 24.00 / share",
                "corporate_action": "Branch Network Expansion & Non-Gold Diversification",
                "impact": "NBFC Lending Catalyst"
            }
        }

        entry = calendar_map.get(sym)
        today = datetime.now().strftime("%Y-%m-%d")
        if entry and (entry.get("earnings_date") or "") >= today:
            return entry
        return None

    def get_cached_events(self, symbol: str) -> Dict[str, Any]:
        """Read-only: last stored events for a symbol regardless of age ({} if none). Never touches the network."""
        try:
            with self.cache_manager._get_connection() as conn:
                row = conn.execute(
                    "SELECT events_data FROM events_cache WHERE symbol = ?", (symbol.upper().strip(),)
                ).fetchone()
            return json.loads(row[0]) if row else {}
        except Exception:
            return {}

    def fetch_stock_events(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches upcoming corporate events for a symbol.
        Checks cache (<48h), queries yfinance if online, then falls back to verified calendar.
        """
        symbol_clean = symbol.upper().strip()

        # Check SQLite cache first
        with self.cache_manager._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT updated_at, events_data FROM events_cache WHERE symbol = ?", (symbol_clean,))
            row = cursor.fetchone()
            if row:
                try:
                    updated_dt = datetime.fromisoformat(row[0])
                    cached_events = json.loads(row[1])
                    ttl = 3600 if cached_events.get("source") == "unavailable" else 48 * 3600
                    if (datetime.now() - updated_dt).total_seconds() < ttl:
                        return cached_events
                except Exception:
                    pass

        # Try dynamic online retrieval via yfinance
        alias_map = {
            "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS", "TATAMOTORS.BO"],
            "NSE": ["NSE.BO", "NSE.NS"]
        }
        candidates = alias_map.get(symbol_clean, [f"{symbol_clean}.NS", f"{symbol_clean}.BO"])
        
        events_found = None
        try:
            import yfinance as yf
            for cand in candidates:
                try:
                    ticker = yf.Ticker(cand)
                    cal = ticker.calendar
                    info = ticker.info or {}

                    earnings_dt_val = None
                    if cal is not None:
                        if isinstance(cal, dict):
                            earnings_dt_val = cal.get("Earnings Date") or cal.get("earningsDate")
                        elif hasattr(cal, "get"):
                            earnings_dt_val = cal.get("Earnings Date")
                        elif hasattr(cal, "loc") and "Earnings Date" in cal.index:
                            earnings_dt_val = cal.loc["Earnings Date"].values[0]

                    today_str = datetime.now().strftime("%Y-%m-%d")
                    ex_div_val = info.get("exDividendDate") or info.get("dividendDate")
                    ex_div_str = datetime.fromtimestamp(ex_div_val).strftime("%Y-%m-%d") if ex_div_val else None
                    if ex_div_str and ex_div_str < today_str:
                        ex_div_str = None  # last ex-date already passed -> not an upcoming event

                    earnings_str = None
                    if isinstance(earnings_dt_val, (list, tuple)):
                        if len(earnings_dt_val) > 0:
                            earnings_str = str(earnings_dt_val[0])[:10]
                    elif earnings_dt_val is not None:
                        earnings_str = str(earnings_dt_val)[:10]
                    if earnings_str and earnings_str < today_str:
                        earnings_str = None

                    if earnings_str or ex_div_str:
                        days_to_results = None
                        if earnings_str:
                            try:
                                days_to_results = (datetime.strptime(earnings_str, "%Y-%m-%d") - datetime.now()).days + 1
                            except ValueError:
                                days_to_results = None
                        div_rate = info.get("dividendRate")
                        events_found = {
                            "symbol": symbol_clean,
                            "earnings_date": earnings_str,
                            "earnings_quarter": "Quarterly Results" if earnings_str else None,
                            "dividend_ex_date": ex_div_str,
                            "dividend_amount": f"Rs. {float(div_rate):.2f} / share" if (ex_div_str and div_rate) else None,
                            "corporate_action": "Board Meeting & Results Disclosure" if earnings_str else None,
                            "impact": "High (results within 7 days)" if (days_to_results is not None and days_to_results <= 7) else "Normal",
                            "source": "Live Market Feed"
                        }
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if not events_found:
            curated = self._get_curated_corporate_calendar(symbol_clean)
            if curated:
                events_found = {
                    "symbol": symbol_clean,
                    "earnings_date": curated.get("earnings_date"),
                    "earnings_quarter": curated.get("earnings_quarter"),
                    "dividend_ex_date": curated.get("dividend_ex_date"),
                    "dividend_amount": curated.get("dividend_amount"),
                    "corporate_action": curated.get("corporate_action"),
                    "impact": curated.get("impact"),
                    "source": "Curated Calendar (not live-verified)"
                }
            else:
                events_found = {
                    "symbol": symbol_clean,
                    "earnings_date": None,
                    "earnings_quarter": None,
                    "dividend_ex_date": None,
                    "dividend_amount": None,
                    "corporate_action": None,
                    "impact": "Normal",
                    "source": "unavailable"
                }

        # Add upcoming macroeconomic events
        macro_events = self.get_upcoming_macro_events()
        events_found["upcoming_macro_catalysts"] = macro_events[:3]

        # Save to SQLite events_cache
        try:
            with self.cache_manager._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO events_cache (symbol, updated_at, events_data)
                    VALUES (?, ?, ?)
                """, (symbol_clean, datetime.now().isoformat(), json.dumps(events_found)))
                conn.commit()
        except Exception:
            pass

        return events_found

