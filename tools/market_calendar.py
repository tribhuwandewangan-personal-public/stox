"""
NSE market calendar (IST). Dependency-free (fixed UTC+05:30 offset; India has no DST).

  * Regular session: 09:15-15:30 IST, Monday-Friday, except exchange holidays.
  * Holidays come from data/nse_holidays.json, which YOU maintain (copy the yearly list from NSE's website).
    No free official holiday API could be verified, so none is called. An unlisted holiday is also caught at
    runtime: the quote poller sees that no fresh trade timestamps arrive and reports "no session today".

All functions accept an optional `now` (tz-aware or naive IST) so they are deterministic in tests.
"""

import json
import os
import threading
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional, Set

IST = timezone(timedelta(hours=5, minutes=30), name="IST")

OPEN_TIME = time(9, 15)
CLOSE_TIME = time(15, 30)
# Daily candles from data vendors are not final the second the bell rings; wait this long.
EOD_DATA_BUFFER = timedelta(minutes=15)

HOLIDAYS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "nse_holidays.json")

_holiday_lock = threading.Lock()
_holiday_cache = {"mtime": None, "path": None, "dates": set()}


def now_ist() -> datetime:
    return datetime.now(IST)


def _as_ist(now: Optional[datetime]) -> datetime:
    if now is None:
        return now_ist()
    if now.tzinfo is None:
        return now.replace(tzinfo=IST)
    return now.astimezone(IST)


def load_holidays(path: Optional[str] = None) -> Set[str]:
    """Set of 'YYYY-MM-DD' strings from the holidays file (re-read when the file changes)."""
    path = path or HOLIDAYS_PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return set()
    with _holiday_lock:
        if _holiday_cache["path"] == path and _holiday_cache["mtime"] == mtime:
            return _holiday_cache["dates"]
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f).get("holidays", [])
            dates = {str(d)[:10] for d in raw if isinstance(d, str)}
        except (OSError, ValueError, AttributeError):
            dates = set()
        _holiday_cache.update({"path": path, "mtime": mtime, "dates": dates})
        return dates


def is_trading_day(d: date, holidays: Optional[Set[str]] = None) -> bool:
    holidays = load_holidays() if holidays is None else holidays
    return d.weekday() < 5 and d.isoformat() not in holidays


def is_market_open(now: Optional[datetime] = None) -> bool:
    n = _as_ist(now)
    return is_trading_day(n.date()) and OPEN_TIME <= n.time() < CLOSE_TIME


def session_state(now: Optional[datetime] = None) -> str:
    """'open' | 'pre_open' | 'closed' (after the bell) | 'holiday' (weekend or listed holiday)."""
    n = _as_ist(now)
    if not is_trading_day(n.date()):
        return "holiday"
    if n.time() < OPEN_TIME:
        return "pre_open"
    if n.time() < CLOSE_TIME:
        return "open"
    return "closed"


def is_session_complete(d: date, now: Optional[datetime] = None) -> bool:
    """True when the daily candle for trading day `d` is final (past close + vendor buffer)."""
    n = _as_ist(now)
    if not is_trading_day(d):
        return False
    if d < n.date():
        return True
    if d > n.date():
        return False
    final_at = datetime.combine(d, CLOSE_TIME, tzinfo=IST) + EOD_DATA_BUFFER
    return n >= final_at


def previous_trading_day(d: date) -> date:
    """Latest trading day strictly before `d`."""
    holidays = load_holidays()
    cur = d - timedelta(days=1)
    while not is_trading_day(cur, holidays):
        cur -= timedelta(days=1)
    return cur


def last_completed_session(now: Optional[datetime] = None) -> date:
    """Most recent trading day whose daily candle is final."""
    n = _as_ist(now)
    today = n.date()
    if is_session_complete(today, n):
        return today
    return previous_trading_day(today)


def next_open(now: Optional[datetime] = None) -> datetime:
    """Start of the next regular session strictly after `now`."""
    n = _as_ist(now)
    holidays = load_holidays()
    d = n.date()
    if is_trading_day(d, holidays) and n.time() < OPEN_TIME:
        return datetime.combine(d, OPEN_TIME, tzinfo=IST)
    d += timedelta(days=1)
    while not is_trading_day(d, holidays):
        d += timedelta(days=1)
    return datetime.combine(d, OPEN_TIME, tzinfo=IST)


def trading_days_after(start: date, end: date) -> int:
    """Number of trading days in (start, end] -- i.e. sessions elapsed after `start` up to and including `end`."""
    if end <= start:
        return 0
    holidays = load_holidays()
    count, cur = 0, start + timedelta(days=1)
    while cur <= end:
        if is_trading_day(cur, holidays):
            count += 1
        cur += timedelta(days=1)
    return count
