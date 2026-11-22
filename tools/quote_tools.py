"""
Near-real-time quotes (polled, not tick-by-tick) with a provider fallback chain.

  QUOTE_SOURCES (default "kite,yahoo") is tried left to right for every poll:
    * kite  - Zerodha Kite Connect. Used only if you completed tools/kite_probe.py AND your plan allows quote
              calls. A permission/auth error disables it (logged once) and the chain falls through to Yahoo.
    * yahoo - Yahoo Finance via yfinance, one batched 5-minute-bar download for all symbols. Yahoo lists NSE
              (.NS) as real-time. Unofficial endpoint, personal use only -> may rate-limit or break; the service
              backs off and keeps serving the last stored quote flagged as stale.

Quotes are written to the SQLite `quotes` table. The dashboard reads them from there.
"""

import json
import os
import threading
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from tools import market_calendar
from tools.yf_quiet import silence_yfinance_logging
from tools import events_bus

silence_yfinance_logging()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KITE_TOKEN_PATH = os.path.join(PROJECT_ROOT, "storage", "kite_token.json")

YF_TIMEOUT_SECONDS = 20
STALE_AFTER_MINUTES = 15          # a quote older than this during market hours is flagged stale (3 five-minute bars)
KITE_CHUNK = 400                  # Kite allows up to 500 instruments per /quote call
YAHOO_CHUNK = 50                  # Chunk batch yfinance downloads so 250+ midcap lists don't timeout or throttle

# Same ticker special cases as the history/fundamental tools
_YAHOO_ALIAS = {"TATAMOTORS": "TMPV.NS", "NSE": "NSE.BO"}


class QuoteProviderError(Exception):
    """Transient failure (network, rate limit, no data). The provider stays enabled."""


class ProviderUnavailable(QuoteProviderError):
    """Permanent for this session (no permission, not logged in, library missing). Provider is disabled."""


def yahoo_symbol(symbol: str) -> str:
    sym = symbol.upper().strip()
    return _YAHOO_ALIAS.get(sym, f"{sym}.NS")


def _to_float(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


# ------------------------------------------------------------------------------------------------ Yahoo
class YahooQuoteProvider:
    name = "yahoo"

    def fetch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        try:
            import yfinance as yf
        except ImportError as e:
            raise ProviderUnavailable(f"yfinance not installed: {e}")

        pairs = [(yahoo_symbol(s), s.upper().strip()) for s in symbols]
        out: Dict[str, Dict[str, Any]] = {}
        chunk_errors: List[str] = []

        for start in range(0, len(pairs), YAHOO_CHUNK):
            chunk = pairs[start:start + YAHOO_CHUNK]
            mapping = {y: s for y, s in chunk}
            try:
                # auto_adjust=True matches HistoricalDataEngine candles; convert index to IST BEFORE date slicing
                df = yf.download(
                    tickers=list(mapping), period="5d", interval="5m", group_by="ticker",
                    threads=True, progress=False, auto_adjust=True, timeout=YF_TIMEOUT_SECONDS,
                )
            except Exception as e:
                chunk_errors.append(f"{type(e).__name__}: {e}")
                continue
            if df is None or df.empty:
                continue

            multi = getattr(df.columns, "nlevels", 1) > 1
            for ysym, sym in mapping.items():
                try:
                    sub = df[ysym] if multi else df
                    sub = sub.dropna(subset=["Close"])
                    if sub.empty:
                        continue
                    idx_ist = (
                        sub.index.tz_convert(market_calendar.IST)
                        if sub.index.tzinfo is not None
                        else sub.index.tz_localize(market_calendar.IST)
                    )
                    last_ts = idx_ist[-1]
                    session = sub[idx_ist.date == last_ts.date()]
                    out[sym] = {
                        "symbol": sym,
                        "ltp": _to_float(session["Close"].iloc[-1]),
                        "prev_close": None,                       # filled from stored daily candles
                        "day_high": _to_float(session["High"].max()),
                        "day_low": _to_float(session["Low"].min()),
                        "volume": int(session["Volume"].fillna(0).sum()),
                        "vwap": None,
                        "upper_circuit": None,
                        "lower_circuit": None,
                        "quote_ts": last_ts.isoformat(),
                        "source": self.name,
                    }
                except Exception:
                    continue

        if not out:
            err_msg = chunk_errors[0] if chunk_errors else "yahoo returned no usable rows (rate limited or offline)"
            raise QuoteProviderError(f"yahoo download failed: {err_msg}")
        return out


# ------------------------------------------------------------------------------------------------ Kite
class KiteQuoteProvider:
    """Zerodha Kite Connect. Optional: needs `pip install kiteconnect`, KITE_API_KEY and a token from kite_probe."""
    name = "kite"

    def __init__(self, api_key: Optional[str] = None, token_path: str = KITE_TOKEN_PATH):
        self.api_key = api_key or os.getenv("KITE_API_KEY", "")
        self.token_path = token_path

    def token_mtime(self) -> float:
        try:
            return os.path.getmtime(self.token_path)
        except OSError:
            return 0.0

    def _access_token(self) -> str:
        try:
            with open(self.token_path, "r", encoding="utf-8") as f:
                return json.load(f).get("access_token", "")
        except (OSError, ValueError):
            return ""

    def fetch(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        if not symbols:
            return {}
        token = self._access_token()
        if not self.api_key or not token:
            raise ProviderUnavailable("Kite not set up: set KITE_API_KEY and run tools/kite_probe.py")
        try:
            from kiteconnect import KiteConnect
        except Exception as e:
            raise ProviderUnavailable(f"kiteconnect unavailable: {e}")

        kite = KiteConnect(api_key=self.api_key)
        kite.set_access_token(token)
        keys = {f"NSE:{s.upper().strip()}": s.upper().strip() for s in symbols}
        out: Dict[str, Dict[str, Any]] = {}
        names = list(keys)
        for i in range(0, len(names), KITE_CHUNK):
            chunk = names[i:i + KITE_CHUNK]
            try:
                data = kite.quote(chunk)
            except Exception as e:
                kind = type(e).__name__
                # Kite exceptions are matched by class name so a missing/renamed class can't crash the poller
                if kind in ("PermissionException", "TokenException"):
                    raise ProviderUnavailable(f"Kite refused the quote call ({kind}): {e}")
                raise QuoteProviderError(f"kite quote failed: {kind}: {e}")
            for key, q in (data or {}).items():
                sym = keys.get(key)
                if not sym:
                    continue
                ohlc = q.get("ohlc") or {}
                ts = q.get("last_trade_time") or q.get("timestamp")
                if isinstance(ts, datetime):
                    ts = (ts.replace(tzinfo=market_calendar.IST) if ts.tzinfo is None else ts).isoformat()
                out[sym] = {
                    "symbol": sym,
                    "ltp": _to_float(q.get("last_price")),
                    "prev_close": _to_float(ohlc.get("close")),   # Kite: ohlc.close is the previous close
                    "day_high": _to_float(ohlc.get("high")),
                    "day_low": _to_float(ohlc.get("low")),
                    "volume": int(q.get("volume") or 0),
                    "vwap": _to_float(q.get("average_price")),
                    "upper_circuit": _to_float(q.get("upper_circuit_limit")),
                    "lower_circuit": _to_float(q.get("lower_circuit_limit")),
                    "quote_ts": ts,
                    "source": self.name,
                }
        if not out:
            raise QuoteProviderError("kite returned no quotes")
        return out


def default_providers(sources: str) -> List[Any]:
    registry = {"kite": KiteQuoteProvider, "yahoo": YahooQuoteProvider}
    providers = []
    for name in [s.strip().lower() for s in (sources or "").split(",") if s.strip()]:
        if name in registry:
            providers.append(registry[name]())
    if not any(p.name == "yahoo" for p in providers):
        providers.append(YahooQuoteProvider())     # Yahoo is always the last resort
    return providers


def prev_close_from_candles(cache_manager, symbol: str, quote_ts: Optional[str]) -> Optional[float]:
    """Close of the last stored daily candle dated before the quote's day (None if no candles are stored)."""
    try:
        quote_day = str(quote_ts or "")[:10]
        candles = cache_manager.get_cached_candles(symbol, limit_days=5)
        prior = [c for c in candles if str(c["DATE"])[:10] < quote_day] or candles[:-1]
        return prior[-1]["CLOSE_PRICE"] if prior else None
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------ service
class QuoteService:
    """Runs the provider chain and stores the result."""

    def __init__(self, cache_manager, providers: Optional[List[Any]] = None, sources: str = "kite,yahoo"):
        self.cache = cache_manager
        self.providers = providers if providers is not None else default_providers(sources)
        self._disabled: Dict[str, str] = {}              # provider name -> reason
        self._kite_token_seen: Dict[str, float] = {}
        self.last_error: Optional[str] = None

    @property
    def disabled(self) -> Dict[str, str]:
        return dict(self._disabled)

    def _maybe_reenable(self, provider) -> None:
        """A new Kite token file (user logged in again) re-enables a provider disabled for an expired token."""
        mtime = getattr(provider, "token_mtime", None)
        if mtime and provider.name in self._disabled and mtime() > self._kite_token_seen.get(provider.name, 0.0):
            del self._disabled[provider.name]

    def _fill_prev_close(self, quote: Dict[str, Any]) -> None:
        if quote.get("prev_close") is None:
            quote["prev_close"] = prev_close_from_candles(self.cache, quote["symbol"], quote.get("quote_ts"))

    def refresh(self, symbols: List[str]) -> Dict[str, Any]:
        """Fetch quotes for `symbols`; returns a summary. Stores whatever was obtained."""
        remaining = [s.upper().strip() for s in symbols]
        got: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []
        used: List[str] = []

        for provider in self.providers:
            if not remaining:
                break
            self._maybe_reenable(provider)
            if provider.name in self._disabled:
                continue
            try:
                res = provider.fetch(remaining)
            except ProviderUnavailable as e:
                self._disabled[provider.name] = str(e)
                self._kite_token_seen[provider.name] = getattr(provider, "token_mtime", lambda: 0.0)()
                errors.append(f"{provider.name}: {e}")
                print(f"⚠️ [Quotes] {provider.name} disabled: {e}", flush=True)
                continue
            except QuoteProviderError as e:
                errors.append(f"{provider.name}: {e}")
                continue
            except Exception as e:                       # a buggy provider must never kill the poller
                errors.append(f"{provider.name}: unexpected {type(e).__name__}: {e}")
                continue
            if res:
                used.append(provider.name)
                got.update(res)
                remaining = [s for s in remaining if s not in res]

        quotes = [q for q in got.values() if q.get("ltp") is not None]
        for q in quotes:
            self._fill_prev_close(q)
        if quotes:
            self.cache.save_quotes(quotes)
            # Publish quotes event for WebSocket broadcast
            events_bus.publish(events_bus.QUOTES, {
                "quotes": {q["symbol"]: q for q in quotes},
                "count": len(quotes),
                "timestamp": datetime.now().isoformat()
            })
        self.last_error = "; ".join(errors) if errors and not quotes else (None if quotes else "no providers available")
        return {"quoted": len(quotes), "missing": len(remaining), "sources": used, "errors": errors}


# ------------------------------------------------------------------------------------------------ poller
class QuotePoller:
    """
    Background thread: poll every `poll_seconds` while the market is open, once at start (catch-up) and once
    right after the close. Idle otherwise. Exponential back-off (max 30 min) when every provider fails.
    """

    TICK_SECONDS = 20

    def __init__(self, service: QuoteService, symbols_loader: Callable[[], List[str]], poll_seconds: int = 300,
                 clock: Callable[[], datetime] = market_calendar.now_ist):
        self.service = service
        self.symbols_loader = symbols_loader
        self.poll_seconds = max(30, int(poll_seconds))
        self.clock = clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._was_open = False
        self._next_poll_at = 0.0
        self._failures = 0
        self.last_poll_at: Optional[str] = None
        self.last_summary: Dict[str, Any] = {}

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="QuotePollerThread")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        self.poll_once()                                  # catch-up poll at start (also off-hours: last session)
        while not self._stop.wait(self.TICK_SECONDS):
            self.tick()

    def tick(self, now_monotonic: Optional[float] = None) -> bool:
        """One scheduling decision. Returns True if a poll was made. (Separate from the loop for testing.)"""
        t = time.monotonic() if now_monotonic is None else now_monotonic
        now = self.clock()
        open_now = market_calendar.is_market_open(now)
        closing_poll = self._was_open and not open_now
        self._was_open = open_now
        if closing_poll or (open_now and t >= self._next_poll_at):
            self.poll_once(t)
            return True
        return False

    def poll_once(self, now_monotonic: Optional[float] = None) -> Dict[str, Any]:
        t = time.monotonic() if now_monotonic is None else now_monotonic
        try:
            symbols = self.symbols_loader()
            summary = self.service.refresh(symbols) if symbols else {"quoted": 0, "missing": 0, "sources": [], "errors": []}
        except Exception as e:
            summary = {"quoted": 0, "missing": 0, "sources": [], "errors": [f"poller: {type(e).__name__}: {e}"]}
        self.last_summary = summary
        self.last_poll_at = self.clock().isoformat()
        if summary["quoted"] == 0 and summary.get("errors"):
            self._failures += 1
            delay = min(1800, self.poll_seconds * (2 ** self._failures))
        else:
            self._failures = 0
            delay = self.poll_seconds
        self._next_poll_at = t + delay
        return summary


# ------------------------------------------------------------------------------------------------ read side
def quote_age_minutes(quote_ts: Optional[str], now: Optional[datetime] = None) -> Optional[float]:
    if not quote_ts:
        return None
    try:
        ts = datetime.fromisoformat(quote_ts)
    except ValueError:
        return None
    n = now or market_calendar.now_ist()
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=market_calendar.IST)
    return max(0.0, (n - ts).total_seconds() / 60.0)


def build_quotes_response(cache_manager, poller: Optional[QuotePoller] = None, now: Optional[datetime] = None) -> Dict[str, Any]:
    """Payload for /api/quotes: per-symbol quote + stale flag, plus market state metadata."""
    n = now or market_calendar.now_ist()
    state = market_calendar.session_state(n)
    market_open = state == "open"
    raw = cache_manager.get_all_quotes()
    quotes: Dict[str, Any] = {}
    todays_stamps = 0
    for sym, q in raw.items():
        age = quote_age_minutes(q.get("quote_ts"), n)
        ltp, prev = q.get("ltp"), q.get("prev_close")
        if prev is None:   # candles may have been stored after this quote was fetched (e.g. first start)
            prev = prev_close_from_candles(cache_manager, sym, q.get("quote_ts"))
        if str(q.get("quote_ts") or "")[:10] == n.date().isoformat():
            todays_stamps += 1
        quotes[sym] = {
            "ltp": ltp,
            "prev_close": prev,
            "change_pct": round((ltp - prev) / prev * 100, 2) if (ltp is not None and prev) else None,
            "day_high": q.get("day_high"),
            "day_low": q.get("day_low"),
            "volume": q.get("volume"),
            "vwap": q.get("vwap"),
            "upper_circuit": q.get("upper_circuit"),
            "lower_circuit": q.get("lower_circuit"),
            "quote_ts": q.get("quote_ts"),
            "age_min": round(age, 1) if age is not None else None,
            "stale": bool(market_open and (age is None or age > STALE_AFTER_MINUTES)),
            "source": q.get("source"),
        }
    # Open per the calendar, but nothing has traded today (after the first minutes): unlisted holiday
    no_session_today = bool(market_open and quotes and todays_stamps == 0 and n.time() > market_calendar.OPEN_TIME.replace(minute=45))
    return {
        "market_state": "holiday" if no_session_today else state,
        "market_open": market_open and not no_session_today,
        "server_time": n.isoformat(),
        "quotes": quotes,
        "poller": {
            "last_poll_at": poller.last_poll_at if poller else None,
            "last_summary": poller.last_summary if poller else {},
            "disabled_providers": poller.service.disabled if poller else {},
            "last_error": poller.service.last_error if poller else None,
        },
    }


def _is_intraday_before_close(quote_ts: Optional[str]) -> bool:
    if not quote_ts or len(str(quote_ts).strip()) <= 10:
        return False
    try:
        dt = datetime.fromisoformat(str(quote_ts).strip())
        dt_ist = (
            dt.astimezone(market_calendar.IST)
            if dt.tzinfo is not None
            else dt.replace(tzinfo=market_calendar.IST)
        )
        return dt_ist.time() < market_calendar.CLOSE_TIME
    except ValueError:
        return False


def build_price_info(
    quote,
    latest_close,
    latest_close_date,
    analysis_price,
    analysis_as_of,
    prev_close_from_candle: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Best-known price for a stock: live quote -> newest stored daily close -> price at analysis time.
    - Quotes older than newest stored candle are ignored.
    - Finalized EOD close beats an earlier same-day intraday quote (quote_day == latest_close_date and time < 15:30 IST).
    """
    price, kind, as_of, change_pct, source, age_min = None, None, None, None, None, None
    quote_day = str((quote or {}).get("quote_ts") or "")[:10]
    quote_is_current = bool(
        quote
        and quote.get("ltp")
        and (
            not latest_close_date
            or quote_day > latest_close_date
            or (quote_day == latest_close_date and not _is_intraday_before_close(quote.get("quote_ts")))
        )
    )
    if quote_is_current:
        price, kind, as_of = float(quote["ltp"]), "quote", quote.get("quote_ts")
        source = quote.get("source")
        age = quote_age_minutes(quote.get("quote_ts"))
        age_min = round(age, 1) if age is not None else None
        prev = quote.get("prev_close") or prev_close_from_candle
        if prev:
            change_pct = round((price - prev) / prev * 100, 2)
    elif latest_close:
        price, kind, as_of = float(latest_close), "close", latest_close_date
        source = "eod_candle"
        if prev_close_from_candle:
            change_pct = round((price - prev_close_from_candle) / prev_close_from_candle * 100, 2)
    elif analysis_price:
        price, kind = float(analysis_price), "analysis"
    drift_pct = None
    if price and analysis_price:
        drift_pct = round((price - analysis_price) / analysis_price * 100, 2)
    return {
        "price": price,
        "kind": kind,
        "as_of": as_of,
        "change_pct": change_pct,
        "analysis_price": analysis_price,
        "analysis_as_of": analysis_as_of,
        "drift_pct": drift_pct,
        "source": source,
        "age_min": age_min,
    }
