"""
Events & Catalyst Engine for NSE Equities.
Aggregates upcoming corporate events (NSE Reg 29/30 corporate actions, earnings dates, dividends,
splits, bonuses, buybacks, F&O expiries) and macroeconomic catalysts (RBI MPC decisions, US Fed FOMC,
Union Budget, CPI/GDP releases) plus pre-event swing risk guardrails.
"""

import os
import re
import sys
import json
import calendar
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import CACHE_DB_PATH
from storage.cache_manager import CacheManager
from tools.market_calendar import load_holidays
from tools.yf_quiet import silence_yfinance_logging

silence_yfinance_logging()


def _parse_nse_date(raw: Any) -> Optional[str]:
    """Parses NSE / ISO corporate action dates into 'YYYY-MM-DD'."""
    if not raw:
        return None
    txt = str(raw).strip()
    if txt in ("-", "N/A", "null", "None"):
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt[:11].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    if re.match(r"^\d{4}-\d{2}-\d{2}", txt):
        return txt[:10]
    return None


def compute_nse_fo_expiry_dates(
    start_date: Optional[date] = None, months_ahead: int = 3
) -> List[Dict[str, Any]]:
    """
    Computes upcoming NSE Monthly F&O Expiry dates (last Tuesday of the month, rolling
    backward past weekends and listed NSE holidays in data/nse_holidays.json).
    """
    ref = start_date or date.today()
    holidays = load_holidays()
    results: List[Dict[str, Any]] = []

    y, m = ref.year, ref.month
    for offset in range(max(1, months_ahead) + 1):
        mm = ((m - 1 + offset) % 12) + 1
        yy = y + ((m - 1 + offset) // 12)
        last_dom = calendar.monthrange(yy, mm)[1]
        d = date(yy, mm, last_dom)
        # Step back to Tuesday (weekday() == 1)
        while d.weekday() != 1:
            d -= timedelta(days=1)
        # Step back if exchange holiday or weekend
        while d.weekday() >= 5 or d.isoformat() in holidays:
            d -= timedelta(days=1)
        if d >= ref and len(results) < months_ahead:
            results.append({
                "event_name": f"NSE Monthly F&O Expiry ({d.strftime('%b %Y')})",
                "date": d.isoformat(),
                "impact": "Elevated",
                "affected_sectors": ["All F&O Stocks", "Nifty 50", "Bank Nifty"],
                "note": "Monthly derivatives rollover & settlement volatility session.",
            })
    return results


def parse_nse_corporate_actions(
    rows: Any, symbol: str, as_of_date: Optional[date] = None
) -> Dict[str, Any]:
    """
    Pure parser for NSE `/api/corporates-corporateActions` Reg 30 payload rows.
    Extracts exact per-event dividends (Rs/share), splits, bonuses, buybacks, and demergers.
    """
    sym_u = str(symbol or "").upper().strip()
    ref_str = (as_of_date or date.today()).isoformat()
    actions: List[Dict[str, Any]] = []

    if isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            row_sym = str(r.get("symbol") or sym_u).upper().strip()
            if sym_u and row_sym != sym_u:
                continue
            ex_date = _parse_nse_date(r.get("exDate") or r.get("ex_date"))
            if not ex_date or ex_date < ref_str:
                continue
            subj = str(r.get("subject") or r.get("purpose") or "").strip()
            if not subj:
                continue
            subj_l = subj.lower()

            act_type = "OTHER"
            div_ps: Optional[float] = None
            ratio: Optional[str] = None

            if "dividend" in subj_l:
                act_type = "DIVIDEND"
                m_div = re.search(r"(?:rs\.?|inr|₹)\s*([0-9]+(?:\.[0-9]+)?)", subj, re.I)
                if m_div:
                    div_ps = round(float(m_div.group(1)), 2)
            elif "split" in subj_l or "sub-division" in subj_l or "face value" in subj_l:
                act_type = "SPLIT"
                m_ratio = re.search(r"from\s+(?:rs\.?\s*)?(\d+)[^0-9]+to\s+(?:rs\.?\s*)?(\d+)", subj, re.I)
                if m_ratio:
                    ratio = f"{m_ratio.group(1)}:{m_ratio.group(2)}"
            elif "bonus" in subj_l:
                act_type = "BONUS"
                m_ratio = re.search(r"(\d+\s*:\s*\d+)", subj)
                if m_ratio:
                    ratio = m_ratio.group(1).replace(" ", "")
            elif "buyback" in subj_l or "buy-back" in subj_l:
                act_type = "BUYBACK"
            elif "demerger" in subj_l or "amalgamation" in subj_l or "rights" in subj_l:
                act_type = "RESTRUCTURING"

            actions.append({
                "type": act_type,
                "ex_date": ex_date,
                "subject": subj,
                "dividend_per_share": div_ps,
                "ratio": ratio,
                "record_date": _parse_nse_date(r.get("recDate") or r.get("recordDate")),
            })

    actions.sort(key=lambda a: a["ex_date"])
    div_events = [a for a in actions if a["type"] == "DIVIDEND"]
    split_events = [a for a in actions if a["type"] == "SPLIT"]
    bonus_events = [a for a in actions if a["type"] == "BONUS"]

    first_div = div_events[0] if div_events else None
    div_ps_top = first_div["dividend_per_share"] if first_div else None
    div_amt_str = (
        f"Rs. {div_ps_top:.2f} / share"
        if div_ps_top is not None
        else (first_div["subject"] if first_div else None)
    )

    return {
        "corporate_actions": actions,
        "dividend_ex_date": first_div["ex_date"] if first_div else None,
        "dividend_per_share": div_ps_top,
        "dividend_amount": div_amt_str,
        "split_ex_date": split_events[0]["ex_date"] if split_events else None,
        "split_ratio": split_events[0]["ratio"] if split_events else None,
        "bonus_ex_date": bonus_events[0]["ex_date"] if bonus_events else None,
        "bonus_ratio": bonus_events[0]["ratio"] if bonus_events else None,
    }


def parse_nse_board_meetings(
    rows: Any, symbol: str, as_of_date: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """
    Pure parser for NSE `/api/corporates-board-meetings` Reg 29 payload rows.
    Detects earliest upcoming quarterly/annual financial results meeting.
    """
    sym_u = str(symbol or "").upper().strip()
    ref_str = (as_of_date or date.today()).isoformat()
    if not isinstance(rows, list):
        return None

    hits = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        row_sym = str(r.get("symbol") or r.get("sm_symbol") or sym_u).upper().strip()
        if sym_u and row_sym != sym_u:
            continue
        m_date = _parse_nse_date(r.get("meetingDate") or r.get("bm_date"))
        if not m_date or m_date < ref_str:
            continue
        purpose = str(r.get("purpose") or r.get("bm_purpose") or "").strip()
        if re.search(r"\b(?:financial\s+results?|quarterly|audited|unaudited|annual\s+results?|half[\s-]+yearly)\b", purpose, re.I):
            hits.append((m_date, purpose))

    if not hits:
        return None
    hits.sort(key=lambda t: t[0])
    return {
        "earnings_date": hits[0][0],
        "earnings_purpose": hits[0][1],
        "source": "NSE Reg 29 Board Meeting",
    }


def fetch_nse_corporate_actions(symbol: str, timeout: float = 6.0) -> Optional[Dict[str, Any]]:
    """
    Fetches official NSE Reg 29 (board meetings) & Reg 30 (corporate actions) JSON feeds.
    Returns None cleanly if NSE blocks requests or network is offline.
    """
    sym_u = str(symbol or "").upper().strip()
    if not sym_u:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nseindia.com/companies-listing/corporate-filings-actions",
    }
    try:
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
        with opener.open(urllib.request.Request("https://www.nseindia.com", headers=headers), timeout=timeout):
            pass

        sym_q = urllib.parse.quote(sym_u)
        ca_parsed: Dict[str, Any] = {}
        try:
            ca_url = f"https://www.nseindia.com/api/corporates-corporateActions?index=equities&symbol={sym_q}"
            with opener.open(urllib.request.Request(ca_url, headers=headers), timeout=timeout) as resp:
                ca_rows = json.loads(resp.read().decode("utf-8", errors="ignore"))
            ca_parsed = parse_nse_corporate_actions(ca_rows, sym_u)
        except Exception:
            ca_parsed = {}

        bm_parsed: Optional[Dict[str, Any]] = None
        try:
            bm_url = f"https://www.nseindia.com/api/corporates-board-meetings?index=equities&symbol={sym_q}"
            with opener.open(urllib.request.Request(bm_url, headers=headers), timeout=timeout) as resp:
                bm_rows = json.loads(resp.read().decode("utf-8", errors="ignore"))
            bm_parsed = parse_nse_board_meetings(bm_rows, sym_u)
        except Exception:
            bm_parsed = None

        has_actions = bool(ca_parsed.get("corporate_actions"))
        if not has_actions and not bm_parsed:
            return None

        return {
            "earnings_date": (bm_parsed or {}).get("earnings_date"),
            "earnings_quarter": (bm_parsed or {}).get("earnings_purpose") or ("Quarterly Results" if bm_parsed else None),
            "dividend_ex_date": ca_parsed.get("dividend_ex_date"),
            "dividend_per_share": ca_parsed.get("dividend_per_share"),
            "dividend_amount": ca_parsed.get("dividend_amount"),
            "split_ex_date": ca_parsed.get("split_ex_date"),
            "split_ratio": ca_parsed.get("split_ratio"),
            "bonus_ex_date": ca_parsed.get("bonus_ex_date"),
            "bonus_ratio": ca_parsed.get("bonus_ratio"),
            "corporate_actions": ca_parsed.get("corporate_actions", []),
            "source": "NSE Reg 29/30 Official Filing",
        }
    except Exception:
        return None


def evaluate_pre_event_guardrail(
    events_data: Optional[Dict[str, Any]],
    as_of_date: Optional[date] = None,
    window_days: int = 3,
) -> Dict[str, Any]:
    """
    Evaluates T-3 pre-event swing guardrails around binary corporate catalysts:
    - T-3 Earnings blackout: flags binary gap risk ahead of results (verdict downgrade/confidence cap).
    - T-3 Ex-Dividend / Split / Bonus: returns exact per-event dividend_per_share for SL adjustment.
    """
    ev = events_data or {}
    ref = as_of_date
    if ref is None and ev.get("_as_of_date"):
        try:
            ref = datetime.strptime(str(ev["_as_of_date"])[:10], "%Y-%m-%d").date()
        except ValueError:
            ref = None
    ref = ref or date.today()

    def _days_until(raw_d: Any) -> Optional[int]:
        iso = _parse_nse_date(raw_d)
        if not iso:
            return None
        try:
            d_obj = datetime.strptime(iso, "%Y-%m-%d").date()
            return (d_obj - ref).days
        except ValueError:
            return None

    days_earn = _days_until(ev.get("earnings_date"))
    days_div = _days_until(ev.get("dividend_ex_date"))
    days_split = _days_until(ev.get("split_ex_date"))
    days_bonus = _days_until(ev.get("bonus_ex_date"))

    earnings_active = days_earn is not None and 0 <= days_earn <= window_days
    ex_div_active = days_div is not None and 0 <= days_div <= window_days
    corp_active = (
        (days_split is not None and 0 <= days_split <= window_days)
        or (days_bonus is not None and 0 <= days_bonus <= window_days)
    )

    div_ps: Optional[float] = None
    if ev.get("dividend_per_share") is not None:
        try:
            val = float(ev["dividend_per_share"])
            if val > 0:
                div_ps = round(val, 2)
        except (TypeError, ValueError):
            div_ps = None
    elif ev.get("dividend_amount") and "(Annual)" not in str(ev.get("dividend_amount")):
        m_ps = re.search(r"([0-9]+(?:\.[0-9]+)?)", str(ev["dividend_amount"]))
        if m_ps:
            div_ps = round(float(m_ps.group(1)), 2)

    warnings: List[str] = []
    if earnings_active:
        warnings.append(
            f"T-{days_earn} Earnings Guardrail ({ev.get('earnings_date')}): binary gap risk; avoid aggressive fresh swing breakout chases."
        )
    if ex_div_active:
        ps_txt = f" (Rs. {div_ps:.2f}/sh adjustment)" if div_ps else ""
        warnings.append(
            f"T-{days_div} Ex-Dividend ({ev.get('dividend_ex_date')}){ps_txt}: price drops mechanically on ex-date."
        )
    if corp_active:
        warnings.append("T-3 Split/Bonus corporate action imminent: exercise caution on level comparisons.")

    return {
        "earnings_guardrail_active": earnings_active,
        "ex_div_guardrail_active": ex_div_active,
        "corp_action_guardrail_active": corp_active,
        "days_to_earnings": days_earn,
        "days_to_ex_div": days_div,
        "dividend_per_share": div_ps,
        "warnings": warnings,
    }


class EventsEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.db_path = self.cache_manager.db_path
        self._init_events_table()

    def _init_events_table(self):
        if getattr(self.cache_manager, "use_valkey", False):
            return
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
        Returns scheduled high-impact macroeconomic events and policy meetings on valid trading weekdays.
        Provides date, impact level, and affected sectors. Past events are dropped.
        """
        events = [
            {
                "event_name": "India Q2 FY27 GDP Growth Data Release",
                "date": "2026-11-27",
                "impact": "High",
                "affected_sectors": ["All Sectors", "Capital Goods", "Infra"],
                "note": "Broad macro barometer for corporate CAPEX and earnings expansion."
            },
            {
                "event_name": "RBI MPC Monetary Policy & Rate Decision",
                "date": "2026-12-04",
                "impact": "Critical",
                "affected_sectors": ["Banking", "Real Estate", "Auto", "NBFCs"],
                "note": "Repo rate decision, stance, and liquidity commentary."
            },
            {
                "event_name": "US Federal Reserve FOMC Rate Decision",
                "date": "2026-12-09",
                "impact": "Critical",
                "affected_sectors": ["IT & Tech", "Pharma", "FII Inflows"],
                "note": "Key driver of global liquidity, dollar index (DXY), and FII flows."
            },
            {
                "event_name": "India CPI Inflation Release (MoM/YoY)",
                "date": "2026-12-14",
                "impact": "High",
                "affected_sectors": ["Banking", "FMCG", "Automobile"],
                "note": "Determines interest rate path and household consumption sentiment."
            },
            {
                "event_name": "India Union Budget (FY28)",
                "date": "2027-02-01",
                "impact": "Critical",
                "affected_sectors": ["Capital Goods", "Defence", "Infra", "PSUs", "Banking"],
                "note": "Annual fiscal deficit target, capex outlay, and sectoral tax policy."
            },
            {
                "event_name": "RBI MPC Monetary Policy & Rate Decision",
                "date": "2027-02-05",
                "impact": "Critical",
                "affected_sectors": ["Banking", "Real Estate", "Auto", "NBFCs"],
                "note": "Post-Budget repo rate decision, stance, and liquidity commentary."
            }
        ]
        today = datetime.now().strftime("%Y-%m-%d")
        fo_expiries = compute_nse_fo_expiry_dates(start_date=date.today(), months_ahead=2)
        combined = [e for e in (events + fo_expiries) if e["date"] >= today]
        combined.sort(key=lambda e: e["date"])
        return combined

    def _get_curated_corporate_calendar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Deprecated hardcoded 2026 corporate calendar removed to prevent fabricated weekend dates
        or spurious orderbook text from polluting signal synthesis. Live feeds drive corporate events.
        """
        return None

    def get_cached_events(self, symbol: str) -> Dict[str, Any]:
        """Read-only: last stored events for a symbol with expired dates stripped ({} if none)."""
        try:
            sym_u = symbol.upper().strip()
            if getattr(self.cache_manager, "use_valkey", False) and hasattr(self.cache_manager, "get_cached_event_record"):
                rec = self.cache_manager.get_cached_event_record(sym_u)
                if not rec:
                    return {}
                data = rec.get("events_data") or {}
            else:
                with self.cache_manager._get_connection() as conn:
                    row = conn.execute(
                        "SELECT events_data FROM events_cache WHERE symbol = ?", (sym_u,)
                    ).fetchone()
                if not row:
                    return {}
                data = json.loads(row[0])
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("earnings_date") and data["earnings_date"] < today:
                data["earnings_date"] = None
            if data.get("dividend_ex_date") and data["dividend_ex_date"] < today:
                data["dividend_ex_date"] = None
                data["dividend_amount"] = None
            if isinstance(data.get("upcoming_macro_catalysts"), list):
                data["upcoming_macro_catalysts"] = [
                    m for m in data["upcoming_macro_catalysts"] if (m.get("date") or "") >= today
                ]
            return data
        except Exception:
            return {}

    def fetch_stock_events(self, symbol: str) -> Dict[str, Any]:
        """
        Fetches upcoming corporate events for a symbol.
        Checks cache (<48h), queries yfinance if online, then falls back to verified calendar.
        """
        symbol_clean = symbol.upper().strip()

        # Check Valkey / SQLite cache first
        if getattr(self.cache_manager, "use_valkey", False) and hasattr(self.cache_manager, "get_cached_event_record"):
            rec = self.cache_manager.get_cached_event_record(symbol_clean)
            if rec:
                try:
                    updated_dt = datetime.fromisoformat(rec["updated_at"])
                    cached_events = rec["events_data"]
                    ttl = 3600 if cached_events.get("source") == "unavailable" else 48 * 3600
                    if (datetime.now() - updated_dt).total_seconds() < ttl:
                        return cached_events
                except Exception:
                    pass
        else:
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

        # Try official NSE Reg 29/30 corporate actions & board meetings first
        nse_found = fetch_nse_corporate_actions(symbol_clean)
        events_found = None
        if nse_found:
            today_str = datetime.now().strftime("%Y-%m-%d")
            e_date = nse_found.get("earnings_date")
            days_to_results = None
            if e_date and e_date >= today_str:
                try:
                    days_to_results = (datetime.strptime(e_date, "%Y-%m-%d").date() - datetime.now().date()).days
                except ValueError:
                    days_to_results = None
            events_found = {
                "symbol": symbol_clean,
                "earnings_date": e_date,
                "earnings_quarter": nse_found.get("earnings_quarter"),
                "dividend_ex_date": nse_found.get("dividend_ex_date"),
                "dividend_per_share": nse_found.get("dividend_per_share"),
                "dividend_amount": nse_found.get("dividend_amount"),
                "split_ex_date": nse_found.get("split_ex_date"),
                "split_ratio": nse_found.get("split_ratio"),
                "bonus_ex_date": nse_found.get("bonus_ex_date"),
                "bonus_ratio": nse_found.get("bonus_ratio"),
                "corporate_actions": nse_found.get("corporate_actions", []),
                "corporate_action": nse_found.get("earnings_quarter") or (
                    nse_found["corporate_actions"][0]["subject"] if nse_found.get("corporate_actions") else None
                ),
                "impact": "High (results within 7 days)" if (days_to_results is not None and 0 <= days_to_results <= 7) else "Normal",
                "source": nse_found.get("source", "NSE Reg 29/30 Official Filing"),
            }

        # Fall back or fill gaps dynamically via yfinance
        alias_map = {
            "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS", "TATAMOTORS.BO"],
            "ZOMATO": ["ETERNAL.NS", "ZOMATO.NS"],
            "LTIM": ["LTM.NS", "LTIM.NS"],
            "NSE": ["NSE.BO", "NSE.NS"],
        }
        candidates = alias_map.get(symbol_clean, [f"{symbol_clean}.NS", f"{symbol_clean}.BO"])

        if not events_found or not events_found.get("earnings_date"):
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
                        ex_div_val = info.get("exDividendDate")
                        ex_div_str = (
                            datetime.fromtimestamp(int(ex_div_val), tz=timezone.utc).strftime("%Y-%m-%d")
                            if ex_div_val
                            else None
                        )
                        if ex_div_str and ex_div_str < today_str:
                            ex_div_str = None

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
                                    days_to_results = (
                                        datetime.strptime(earnings_str, "%Y-%m-%d").date() - datetime.now().date()
                                    ).days
                                except ValueError:
                                    days_to_results = None
                            div_rate = info.get("dividendRate")
                            if events_found:
                                if not events_found.get("earnings_date") and earnings_str:
                                    events_found["earnings_date"] = earnings_str
                                    events_found["earnings_quarter"] = "Quarterly Results"
                                    if days_to_results is not None and 0 <= days_to_results <= 7:
                                        events_found["impact"] = "High (results within 7 days)"
                                if not events_found.get("dividend_ex_date") and ex_div_str:
                                    events_found["dividend_ex_date"] = ex_div_str
                                    events_found["dividend_amount"] = (
                                        f"Rs. {float(div_rate):.2f} / share (Annual)" if div_rate else None
                                    )
                            else:
                                events_found = {
                                    "symbol": symbol_clean,
                                    "earnings_date": earnings_str,
                                    "earnings_quarter": "Quarterly Results" if earnings_str else None,
                                    "dividend_ex_date": ex_div_str,
                                    "dividend_amount": f"Rs. {float(div_rate):.2f} / share (Annual)" if (ex_div_str and div_rate) else None,
                                    "corporate_action": "Board Meeting & Results Disclosure" if earnings_str else None,
                                    "impact": "High (results within 7 days)" if (days_to_results is not None and 0 <= days_to_results <= 7) else "Normal",
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

        # Save to Valkey or SQLite events_cache
        try:
            if getattr(self.cache_manager, "use_valkey", False) and hasattr(self.cache_manager, "save_cached_event_record"):
                self.cache_manager.save_cached_event_record(symbol_clean, events_found)
            else:
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

