"""
Reliable Historical Data Engine & Excel Export Utility.
Replaces legacy scraping with split/dividend-adjusted historical data (via yfinance),
persists into SQLite (historical_candles table), and exports to Excel (.xlsx).
"""

import os
import sys
import csv
import io
import json
import time
import threading
import urllib.request
import concurrent.futures
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Try to import optional modules, but don't fail if missing
try:
    from config import CACHE_DB_PATH, SYMBOLS_FILE_PATH, HISTORICAL_EXCEL_PATH, REPORTS_DIR
except ImportError:
    CACHE_DB_PATH = "stox.db"
    SYMBOLS_FILE_PATH = "symbols.json"
    HISTORICAL_EXCEL_PATH = "reports/NSE_Historical_Data.xlsx"
    REPORTS_DIR = "reports"

try:
    from storage.cache_manager import CacheManager
except ImportError:
    # Create a simple fallback CacheManager if module missing
    class CacheManager:
        def __init__(self):
            import sqlite3
            self.db_path = CACHE_DB_PATH

        def get_cached_candles(self, symbol, limit_days=1500):
            import sqlite3
            try:
                conn = sqlite3.connect(self.db_path)
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                c.execute(f"""
                    SELECT * FROM historical_data
                    WHERE symbol = ?
                    ORDER BY DATE DESC LIMIT ?
                """, (symbol.upper(), limit_days))
                rows = [dict(row) for row in c.fetchall()]
                conn.close()
                return rows
            except:
                return []

        def save_historical_candles(self, records, replace_symbol=None):
            import sqlite3
            try:
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                if replace_symbol:
                    c.execute("DELETE FROM historical_data WHERE symbol = ?", (replace_symbol.upper(),))
                for record in records:
                    c.execute("""
                        INSERT OR REPLACE INTO historical_data
                        (symbol, date, open, high, low, close, adj_close, volume, dividends, splits)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        record['symbol'].upper(),
                        record['date'],
                        record['open'],
                        record['high'],
                        record['low'],
                        record['close'],
                        record['adj_close'],
                        record['volume'],
                        record.get('dividends', 0),
                        record.get('splits', 0)
                    ))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Warning: Could not save to database: {e}")

try:
    from tools import market_calendar
except ImportError:
    # Create fallback market_calendar
    class market_calendar:
        @staticmethod
        def now_ist():
            from datetime import datetime, timezone, timedelta
            ist = timezone(timedelta(hours=5, minutes=30))
            return datetime.now(ist)

        @staticmethod
        def last_completed_session():
            from datetime import datetime, timedelta
            today = datetime.now().date()
            # Assume previous business day
            if today.weekday() == 0:  # Monday
                return (today - timedelta(days=3)).date()
            elif today.weekday() == 6:  # Sunday
                return (today - timedelta(days=2)).date()
            else:
                return (today - timedelta(days=1)).date()

        @staticmethod
        def is_session_complete(date):
            from datetime import datetime, time
            now = datetime.now().time()
            return now > time(15, 30)  # NSE closes at 3:30 PM

try:
    from tools.yf_quiet import silence_yfinance_logging
    silence_yfinance_logging()
except ImportError:
    # Fallback: silence yfinance manually
    import logging
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    logging.getLogger('urllib3').setLevel(logging.CRITICAL)

HISTORY_WINDOW = 1500          # candles kept in memory per symbol (~6 years)
INCREMENTAL_OVERLAP_DAYS = 7   # re-fetched on every refresh to detect split/dividend re-adjustment
ADJUSTMENT_TOLERANCE = 0.001   # >0.1% change in an overlapping close => history was re-adjusted
RECHECK_SECONDS = 1800         # don't re-ask the vendor for a symbol more often than this (unlisted holidays)
DF_CACHE_TTL_SECONDS = 900     # in-memory frames are reloaded from SQLite after this (long-running dashboard)
BENCHMARK_NIFTY50 = "^NSEI"
BENCHMARK_MIDCAP150 = "^CRSMID"
BENCHMARK_SYMBOLS = (BENCHMARK_NIFTY50, BENCHMARK_MIDCAP150)
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/csv,text/plain,*/*",
    "Referer": "https://www.nseindia.com/",
}


def parse_nse_delivery_csv(csv_text: str) -> List[Dict[str, Any]]:
    """
    Parses NSE `sec_bhavdata_full_DDMMYYYY.csv` text into standardized delivery records:
      [{"symbol", "date", "delivery_qty", "delivery_pct"}].
    Keeps SERIES == "EQ" rows and safely skips "-" or non-numeric delivery fields.
    """
    if not csv_text or not csv_text.strip():
        return []
    reader = csv.DictReader(io.StringIO(csv_text.strip()))
    if not reader.fieldnames:
        return []

    records: List[Dict[str, Any]] = []
    for raw_row in reader:
        row = {str(k).strip().upper(): (v.strip() if isinstance(v, str) else "") for k, v in raw_row.items() if k is not None}
        if row.get("SERIES", "").upper() != "EQ":
            continue
        sym = row.get("SYMBOL", "").upper().strip()
        if not sym:
            continue

        date_raw = row.get("DATE1") or row.get("TIMESTAMP") or row.get("DATE") or ""
        iso_date = None
        for fmt in ("%d-%b-%Y", "%d-%b-%y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                iso_date = datetime.strptime(date_raw.strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue
        if not iso_date:
            continue

        dqty_raw = row.get("DELIV_QTY", "").replace(",", "").strip()
        dpct_raw = row.get("DELIV_PER", "").replace(",", "").replace("%", "").strip()

        delivery_qty: Optional[int] = None
        delivery_pct: Optional[float] = None
        if dqty_raw and dqty_raw != "-":
            try:
                q_val = int(float(dqty_raw))
                if q_val >= 0:
                    delivery_qty = q_val
            except ValueError:
                pass
        if dpct_raw and dpct_raw != "-":
            try:
                p_val = float(dpct_raw)
                if np.isfinite(p_val) and 0.0 <= p_val <= 100.0:
                    delivery_pct = round(p_val, 2)
            except ValueError:
                pass

        if delivery_qty is None and delivery_pct is None:
            continue

        records.append({
            "symbol": sym,
            "date": iso_date,
            "delivery_qty": delivery_qty,
            "delivery_pct": delivery_pct,
        })
    return records


class HistoricalDataEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self._cache_lock = threading.Lock()
        self.df_cache: Dict[str, pd.DataFrame] = {}
        self._df_loaded_at: Dict[str, float] = {}
        self._last_sync_attempt: Dict[str, float] = {}
        self._intraday_cache: Dict[tuple, tuple] = {}

    def _resolve_yf_candidates(self, symbol_clean: str):
        """Resolves yfinance ticker candidates and failure tracker for a symbol."""
        is_index = symbol_clean.startswith("^")
        if is_index:
            return [symbol_clean], None
        try:
            from tools.ticker_validator import build_yf_candidates, get_tracker, _is_sme_or_derivative
            if _is_sme_or_derivative(symbol_clean):
                return [], None
            tracker = get_tracker()
            if tracker.is_unavailable(symbol_clean):
                return [], tracker
            return build_yf_candidates(symbol_clean), tracker
        except ImportError:
            return [f"{symbol_clean}.NS", f"{symbol_clean}.BO"], None

    def fetch_from_source(self, symbol: str, period: str = "5y", start: Optional[str] = None) -> pd.DataFrame:
        """
        Fetches corporate-action adjusted daily OHLCV candles from reliable market feeds.
        Primary: <SYMBOL>.NS (NSE)
        Fallback: <SYMBOL>.BO (BSE)
        Uses ticker_validator for smart candidate list + failure tracking.
        If `start` (YYYY-MM-DD) is given only candles from that date are downloaded, otherwise `period`.
        """
        import yfinance as yf

        symbol_clean = symbol.upper().strip()
        candidates, tracker = self._resolve_yf_candidates(symbol_clean)
        if not candidates:
            return pd.DataFrame()

        df_history = pd.DataFrame()

        for candidate in candidates:
            try:
                ticker = yf.Ticker(candidate)
                if start:
                    df = ticker.history(start=start, auto_adjust=True)
                else:
                    df = ticker.history(period=period, auto_adjust=True)

                if df is not None and not df.empty:
                    df_history = df.copy()
                    if tracker:
                        tracker.record_success(symbol_clean)
                    break
            except Exception:
                continue

        if df_history.empty:
            if tracker:
                tracker.record_failure(symbol_clean)
            return pd.DataFrame()

        # Never store candles without a close price
        df_history = df_history.dropna(subset=['Close'])
        if df_history.empty:
            return pd.DataFrame()

        # Format dataframe into standardized schema
        df_history = df_history.reset_index()

        # Standardize date column
        date_col = 'Date' if 'Date' in df_history.columns else df_history.columns[0]
        df_history['DATE'] = pd.to_datetime(df_history[date_col]).dt.tz_localize(None).dt.normalize()

        df_history['SYMBOL'] = symbol_clean
        df_history['OPEN_PRICE'] = df_history['Open'].astype(float)
        df_history['HIGH_PRICE'] = df_history['High'].astype(float)
        df_history['LOW_PRICE'] = df_history['Low'].astype(float)
        df_history['CLOSE_PRICE'] = df_history['Close'].astype(float)
        df_history['ADJ_CLOSE'] = df_history['Close'].astype(float)
        df_history['TTL_TRD_QNTY'] = df_history['Volume'].fillna(0).astype(int)
        df_history['VOLUME'] = df_history['TTL_TRD_QNTY']

        div_col = 'Dividends' if 'Dividends' in df_history.columns else None
        split_col = 'Stock Splits' if 'Stock Splits' in df_history.columns else None
        df_history['DIVIDENDS'] = df_history[div_col].fillna(0.0).astype(float) if div_col else 0.0
        df_history['SPLITS'] = df_history[split_col].fillna(0.0).astype(float) if split_col else 0.0

        # Compute Previous Close
        df_history['PREV_CLOSE'] = df_history['CLOSE_PRICE'].shift(1).fillna(df_history['OPEN_PRICE'])

        # Keep ordered and sorted
        df_history = df_history.sort_values('DATE').reset_index(drop=True)
        return self._drop_provisional_bar(df_history)

    def fetch_intraday_history(self, symbol: str, interval: str = "1h", days: int = 365) -> pd.DataFrame:
        """
        Fetches intraday OHLCV candles (15m, 30m, 1h) from yfinance with a 5-minute in-memory TTL cache.
        yfinance supports up to 60d for 15m/30m and up to 730d for 1h.
        """
        if interval not in ("15m", "30m", "1h"):
            return pd.DataFrame()

        symbol_clean = symbol.upper().strip()
        if interval in ("15m", "30m"):
            period = "60d"
        else:
            period = "730d" if days > 365 else "400d"

        cache_key = (symbol_clean, interval, period)
        now = time.time()
        with self._cache_lock:
            cached = self._intraday_cache.get(cache_key)
            if cached and (now - cached[0]) < 300:
                return cached[1].copy()

        import yfinance as yf

        candidates, tracker = self._resolve_yf_candidates(symbol_clean)
        if not candidates:
            return pd.DataFrame()

        df_history = pd.DataFrame()
        for candidate in candidates:
            try:
                df = yf.Ticker(candidate).history(period=period, interval=interval, auto_adjust=True)
                if df is not None and not df.empty:
                    df_history = df.copy()
                    if tracker:
                        tracker.record_success(symbol_clean)
                    break
            except Exception:
                continue

        if df_history.empty:
            return pd.DataFrame()

        df_history = df_history.dropna(subset=['Close']).reset_index()
        if df_history.empty:
            return pd.DataFrame()

        date_col = 'Datetime' if 'Datetime' in df_history.columns else ('Date' if 'Date' in df_history.columns else df_history.columns[0])
        dt_series = pd.to_datetime(df_history[date_col])
        if dt_series.dt.tz is not None:
            dt_series = dt_series.dt.tz_convert('Asia/Kolkata').dt.tz_localize(None)

        df_out = pd.DataFrame({
            'DATE': dt_series,
            'SYMBOL': symbol_clean,
            'OPEN_PRICE': df_history['Open'].astype(float),
            'HIGH_PRICE': df_history['High'].astype(float),
            'LOW_PRICE': df_history['Low'].astype(float),
            'CLOSE_PRICE': df_history['Close'].astype(float),
            'VOLUME': df_history['Volume'].fillna(0).astype(int),
        })
        df_out = df_out.sort_values('DATE').drop_duplicates(subset=['DATE']).reset_index(drop=True)

        with self._cache_lock:
            self._intraday_cache[cache_key] = (now, df_out.copy())
        return df_out

    @staticmethod
    def _drop_provisional_bar(df: pd.DataFrame) -> pd.DataFrame:
        """
        Yahoo returns today's in-progress bar while the session runs. Storing it would freeze an intraday price
        in as that day's close, so a bar for a not-yet-final session is dropped (live prices come from the
        quote layer instead).
        If the newly listed stock only has 1 bar, retain it so it is not dropped to empty.
        """
        if df is None or len(df) <= 1:
            return df
        today = market_calendar.now_ist().date()
        if df['DATE'].iloc[-1].date() == today and not market_calendar.is_session_complete(today):
            return df.iloc[:-1].reset_index(drop=True)
        return df

    # ---- helpers -------------------------------------------------------------------------------
    def _load_cached_df(self, symbol: str) -> pd.DataFrame:
        """Full cached window (HISTORY_WINDOW candles) for a symbol straight from SQLite."""
        records = self.cache_manager.get_cached_candles(symbol, limit_days=HISTORY_WINDOW)
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        df['DATE'] = pd.to_datetime(df['DATE'])
        df = df.sort_values('DATE').reset_index(drop=True)
        # Also hides a provisional bar stored by older versions
        return self._drop_provisional_bar(df)

    def _is_up_to_date(self, symbol: str, latest_dt: datetime) -> bool:
        """Stored candles reach the last completed session, or the vendor was asked very recently."""
        if latest_dt.date() >= market_calendar.last_completed_session():
            return True
        with self._cache_lock:
            last_try = self._last_sync_attempt.get(symbol, 0.0)
        return (time.time() - last_try) < RECHECK_SECONDS

    def _remember(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        with self._cache_lock:
            self.df_cache[symbol] = df
            self._df_loaded_at[symbol] = time.time()
        return df

    @staticmethod
    def _df_to_records(symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        dates = df['DATE'].dt.strftime('%Y-%m-%d')
        has_dqty = 'DELIVERY_QTY' in df.columns
        has_dpct = 'DELIVERY_PCT' in df.columns
        dqtys = df['DELIVERY_QTY'] if has_dqty else [None] * len(df)
        dpcts = df['DELIVERY_PCT'] if has_dpct else [None] * len(df)
        return [
            {
                "symbol": symbol, "date": d,
                "open": float(o), "high": float(h), "low": float(l), "close": float(c),
                "adj_close": float(a), "volume": int(v), "dividends": float(dv), "splits": float(sp),
                "delivery_qty": (int(dq) if dq is not None and pd.notna(dq) else None),
                "delivery_pct": (float(dp) if dp is not None and pd.notna(dp) else None),
            }
            for d, o, h, l, c, a, v, dv, sp, dq, dp in zip(
                dates, df['OPEN_PRICE'], df['HIGH_PRICE'], df['LOW_PRICE'], df['CLOSE_PRICE'],
                df['ADJ_CLOSE'], df['VOLUME'], df['DIVIDENDS'], df['SPLITS'], dqtys, dpcts
            )
        ]

    @staticmethod
    def _history_readjusted(cached_df: pd.DataFrame, df_new: pd.DataFrame) -> bool:
        """
        True when appending df_new onto the stored history would mix price bases: a split in the new window,
        no overlapping dates to compare, or overlapping closes that moved (dividend/split re-adjustment of the
        whole series by auto_adjust).
        """
        if (df_new['SPLITS'] != 0).any():
            return True
        old = cached_df.set_index(cached_df['DATE'].dt.strftime('%Y-%m-%d'))['CLOSE_PRICE']
        new = df_new.set_index(df_new['DATE'].dt.strftime('%Y-%m-%d'))['CLOSE_PRICE']
        common = old.index.intersection(new.index)
        if len(common) == 0:
            return True
        old_c, new_c = old[common], new[common]
        rel = (new_c - old_c).abs() / old_c.abs().clip(lower=1e-9)
        return bool((rel > ADJUSTMENT_TOLERANCE).any())

    @staticmethod
    def _compute_rebaseline_factor(cached_df: pd.DataFrame, df_new: pd.DataFrame) -> Optional[float]:
        """Computes median price adjustment factor (new / old) across overlapping dates when history is re-adjusted."""
        if cached_df is None or cached_df.empty or df_new is None or df_new.empty:
            return None
        try:
            old = cached_df.set_index(cached_df['DATE'].dt.strftime('%Y-%m-%d'))['CLOSE_PRICE']
            new = df_new.set_index(df_new['DATE'].dt.strftime('%Y-%m-%d'))['CLOSE_PRICE']
            common = old.index.intersection(new.index)
            if len(common) == 0:
                return None
            old_c = old[common].astype(float)
            new_c = new[common].astype(float)
            valid = (old_c > 0) & (new_c > 0)
            if not valid.any():
                return None
            ratios = new_c[valid] / old_c[valid]
            rel = (new_c[valid] - old_c[valid]).abs() / old_c[valid]
            if not (rel > ADJUSTMENT_TOLERANCE).any():
                return None
            med = float(ratios.median())
            if abs(med - 1.0) > ADJUSTMENT_TOLERANCE and 0.01 <= med <= 100.0:
                return round(med, 6)
        except Exception:
            return None
        return None

    def _full_refresh(self, symbol: str, period: str, fallback: pd.DataFrame) -> pd.DataFrame:
        df_fresh = self.fetch_from_source(symbol, period=period)
        if df_fresh.empty:
            if not fallback.empty:
                return self._remember(symbol, fallback)
            return pd.DataFrame()
        rebase_factor = self._compute_rebaseline_factor(fallback, df_fresh) if not fallback.empty else None
        cutoff_date = (
            fallback['DATE'].iloc[-1].strftime('%Y-%m-%d')
            if (rebase_factor is not None and not fallback.empty)
            else None
        )
        # replace_symbol: drop old rows so every stored candle shares one adjustment basis
        self.cache_manager.save_historical_candles(self._df_to_records(symbol, df_fresh), replace_symbol=symbol)
        if rebase_factor is not None and hasattr(self.cache_manager, "rebase_open_predictions"):
            try:
                self.cache_manager.rebase_open_predictions(symbol, rebase_factor, as_of_cutoff=cutoff_date)
            except Exception:
                pass
        return self._remember(symbol, self._load_cached_df(symbol))

    def sync_benchmarks(
        self, benchmarks: tuple = BENCHMARK_SYMBOLS, force: bool = False
    ) -> Dict[str, bool]:
        """Synchronizes index benchmarks (^NSEI Nifty 50, ^CRSMID Nifty Midcap 150) into SQLite."""
        results: Dict[str, bool] = {}
        for bm in benchmarks:
            sym = str(bm or "").upper().strip()
            if not sym:
                continue
            try:
                df = self.sync_symbol_data(sym, period="5y", force=force)
                results[sym] = df is not None and not df.empty
            except Exception:
                results[sym] = False
        return results

    # ---- public API ----------------------------------------------------------------------------
    def sync_symbol_data(self, symbol: str, period: str = "5y", force: bool = False) -> pd.DataFrame:
        """
        Syncs symbol candles:
        - Cached and up to date (reaches the last completed NSE session): no network, returns cached DataFrame.
        - Cached but behind: downloads only the missing days (plus a 7-day overlap) and appends them. If the
          overlap shows the history was re-adjusted (split/dividend) it falls back to a full re-download.
        - Not cached (or force): downloads the full period.
        """
        symbol = symbol.upper().strip()
        cached_df = self._load_cached_df(symbol)

        if not force and not cached_df.empty:
            latest_dt = cached_df['DATE'].iloc[-1].to_pydatetime()
            if self._is_up_to_date(symbol, latest_dt):
                return self._remember(symbol, cached_df)

            with self._cache_lock:
                self._last_sync_attempt[symbol] = time.time()
            start = (latest_dt - timedelta(days=INCREMENTAL_OVERLAP_DAYS)).strftime('%Y-%m-%d')
            df_new = self.fetch_from_source(symbol, start=start)
            if df_new.empty:
                # Source unavailable: serve what we have rather than nothing
                return self._remember(symbol, cached_df)
            if self._history_readjusted(cached_df, df_new):
                return self._full_refresh(symbol, period, fallback=cached_df)
            self.cache_manager.save_historical_candles(self._df_to_records(symbol, df_new))
            return self._remember(symbol, self._load_cached_df(symbol))

        return self._full_refresh(symbol, period, fallback=cached_df)

    def load_symbol_history(self, symbol: str, limit_days: int = 500) -> pd.DataFrame:
        """
        Loads symbol history (most recent `limit_days` candles):
        1. In-memory frame (reloaded from SQLite after 15 min so a long-running dashboard sees new candles).
        2. SQLite database.
        3. If missing, fetches from source, saves to SQLite, and returns.
        The in-memory frame always holds the full window, never just the last request's slice.
        """
        symbol = symbol.upper().strip()
        with self._cache_lock:
            df = self.df_cache.get(symbol)
            loaded_at = self._df_loaded_at.get(symbol, 0.0)
        if df is None or (time.time() - loaded_at) > DF_CACHE_TTL_SECONDS:
            loaded = self._load_cached_df(symbol)
            if not loaded.empty:
                df = self._remember(symbol, loaded)
            elif df is None:
                df = self.sync_symbol_data(symbol, period="5y")
                if df.empty:
                    return pd.DataFrame()
        return df.tail(limit_days).reset_index(drop=True)

    def load_benchmark_history(
        self,
        benchmark: str = BENCHMARK_NIFTY50,
        limit_days: int = 500,
        allow_fetch: bool = False,
    ) -> pd.DataFrame:
        """
        Returns historical candles for benchmark index (default ^NSEI Nifty 50).
        When allow_fetch=False (default), serves cached SQLite data cleanly with zero network calls.
        """
        bench_sym = str(benchmark or BENCHMARK_NIFTY50).upper().strip()
        try:
            with self._cache_lock:
                df = self.df_cache.get(bench_sym)
                loaded_at = self._df_loaded_at.get(bench_sym, 0.0)
            if df is None or (time.time() - loaded_at) > DF_CACHE_TTL_SECONDS:
                loaded = self._load_cached_df(bench_sym)
                if not loaded.empty:
                    df = self._remember(bench_sym, loaded)
                elif allow_fetch:
                    df = self.sync_symbol_data(bench_sym, period="5y")
                else:
                    return pd.DataFrame()
            elif allow_fetch and not df.empty:
                latest_dt = df['DATE'].iloc[-1].to_pydatetime()
                if not self._is_up_to_date(bench_sym, latest_dt):
                    df = self.sync_symbol_data(bench_sym, period="5y")
            if df is None or df.empty:
                return pd.DataFrame()
            return df.tail(limit_days).reset_index(drop=True)
        except Exception:
            return pd.DataFrame()

    def sync_nse_delivery_data(
        self,
        dates: Optional[List[str]] = None,
        lookback_days: int = 5,
    ) -> int:
        """
        Downloads official NSE security-wise full bhavdata CSVs for recent trading days and updates
        delivery_qty & delivery_pct in SQLite historical_candles. Degrades gracefully returning 0 offline.
        """
        target_dates: List[datetime] = []
        if dates:
            for d_str in dates:
                try:
                    target_dates.append(datetime.strptime(str(d_str)[:10], "%Y-%m-%d"))
                except ValueError:
                    continue
        else:
            try:
                cur_d = market_calendar.last_completed_session()
            except Exception:
                cur_d = datetime.now().date() - timedelta(days=1)
            attempts = 0
            while len(target_dates) < max(1, lookback_days) and attempts < max(5, lookback_days * 4):
                is_td = (
                    market_calendar.is_trading_day(cur_d)
                    if hasattr(market_calendar, "is_trading_day")
                    else (cur_d.weekday() < 5)
                )
                if is_td:
                    target_dates.append(datetime.combine(cur_d, datetime.min.time()))
                cur_d = cur_d - timedelta(days=1)
                attempts += 1

        total_updated = 0
        for dt in target_dates:
            ddmmyyyy = dt.strftime("%d%m%Y")
            url = f"https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{ddmmyyyy}.csv"
            try:
                req = urllib.request.Request(url, headers=NSE_HEADERS)
                with urllib.request.urlopen(req, timeout=8) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                recs = parse_nse_delivery_csv(text)
                if recs:
                    total_updated += self.cache_manager.update_delivery_data(recs)
            except Exception:
                continue

        if total_updated > 0:
            with self._cache_lock:
                self.df_cache.clear()
                self._df_loaded_at.clear()
        return total_updated

    def get_historical_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Generates statistical insights and RAG context for the Historical Analyst Agent.
        """
        df = self.load_symbol_history(symbol, limit_days=500)
        if df.empty:
            return {"symbol": symbol, "status": "No historical data found."}

        latest = df.iloc[-1]
        prev_5d = df.tail(5)
        prev_30d = df.tail(30)
        prev_1y = df.tail(252)

        # Volume Analysis
        avg_vol_30 = float(prev_30d['VOLUME'].mean()) if len(prev_30d) > 0 else float(latest['VOLUME'])
        latest_vol = int(latest['VOLUME'])
        vol_surge_ratio = round(latest_vol / (avg_vol_30 + 1e-5), 2)

        # Price Performance
        close_latest = float(latest['CLOSE_PRICE'])
        p5d_first = float(prev_5d.iloc[0]['CLOSE_PRICE']) if len(prev_5d) > 0 else close_latest
        p30d_first = float(prev_30d.iloc[0]['CLOSE_PRICE']) if len(prev_30d) > 0 else close_latest
        p1y_first = float(prev_1y.iloc[0]['CLOSE_PRICE']) if len(prev_1y) > 0 else close_latest

        return_5d = round(((close_latest - p5d_first) / (p5d_first + 1e-5)) * 100, 2)
        return_30d = round(((close_latest - p30d_first) / (p30d_first + 1e-5)) * 100, 2)
        return_1y = round(((close_latest - p1y_first) / (p1y_first + 1e-5)) * 100, 2)

        high_52w = float(prev_1y['HIGH_PRICE'].max()) if len(prev_1y) > 0 else float(latest['HIGH_PRICE'])
        low_52w = float(prev_1y['LOW_PRICE'].min()) if len(prev_1y) > 0 else float(latest['LOW_PRICE'])

        return {
            "symbol": symbol,
            "latest_date": str(latest['DATE'].date()) if pd.notnull(latest['DATE']) else "N/A",
            "last_close": round(close_latest, 2),
            "prev_close": round(float(latest['PREV_CLOSE']), 2),
            "day_high": round(float(latest['HIGH_PRICE']), 2),
            "day_low": round(float(latest['LOW_PRICE']), 2),
            "52w_high": round(high_52w, 2),
            "52w_low": round(low_52w, 2),
            "pct_change_5d": return_5d,
            "pct_change_30d": return_30d,
            "pct_change_1y": return_1y,
            "latest_volume": latest_vol,
            "avg_volume_30d": int(avg_vol_30),
            "volume_surge_ratio": vol_surge_ratio,
            "data_points": len(df)
        }

    def sync_all_symbols(self, symbols: List[Dict[str, Any]], force: bool = False, max_workers: int = 6) -> Dict[str, bool]:
        """
        Synchronizes historical data for all symbols and caches to SQLite (parallel, incremental).
        Pre-filters SME/derivative/persistently-unavailable symbols to avoid wasting fetch time.
        """
        # Pre-filter: separate fetchable from skip-worthy symbols
        try:
            from tools.ticker_validator import filter_fetchable_symbols, get_tracker
            fetchable, skipped = filter_fetchable_symbols(symbols)
            tracker = get_tracker()
            # Also skip symbols that have hit the persistent-unavailable threshold
            unavail_set = set(tracker.get_unavailable_symbols())
            prev_len = len(fetchable)
            fetchable = [s for s in fetchable if s.get("symbol", "").upper() not in unavail_set]
            perm_skipped = prev_len - len(fetchable)
            if skipped or perm_skipped:
                print(f"⚡ Pre-filter: {len(fetchable)} fetchable | "
                      f"{len(skipped)} SME/derivative | "
                      f"{perm_skipped} persistently unavailable (skipped)")
        except ImportError:
            fetchable = symbols
            skipped = []

        results: Dict[str, bool] = {}
        # Mark skipped as False immediately
        for s in skipped:
            sym = s.get("symbol", "").upper()
            if sym:
                results[sym] = False

        total = len(fetchable)
        print(f"📥 Syncing reliable historical data for {total} symbols...")

        def _sync(item):
            sym = item.get("symbol", "").upper().strip()
            t0 = time.time()
            try:
                df = self.sync_symbol_data(sym, period="5y", force=force)
                return sym, df, time.time() - t0, None
            except Exception as e:
                return sym, None, time.time() - t0, e

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(max_workers, total or 1))) as pool:
            futures = [pool.submit(_sync, item) for item in fetchable]
            for idx, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                sym, df, elapsed, err = fut.result()
                if err is not None:
                    print(f"  [{idx:4d}/{total}] ❌ {sym:<14} | Error: {err}")
                    results[sym] = False
                elif df is not None and len(df) > 0:
                    latest_d = df.iloc[-1]['DATE'].strftime('%Y-%m-%d')
                    print(f"  [{idx:4d}/{total}] ✅ {sym:<14} | {len(df):4d} candles | Latest: {latest_d} ({elapsed:.1f}s)")
                    results[sym] = True
                else:
                    print(f"  [{idx:4d}/{total}] ⚠️  {sym:<14} | No candles returned ({elapsed:.1f}s)")
                    results[sym] = False

        return results

    def export_to_excel(self, symbols: List[Dict[str, Any]], excel_path: str = HISTORICAL_EXCEL_PATH, max_individual_sheets: int = 50) -> str:
        """
        Exports synchronized historical data to an Excel workbook (.xlsx).
        - Sheet 1: Master Summary (All stocks with 52W H/L, Returns, Surge, Volume)
        - Dedicated Sheets: Per stock OHLCV history with indicators only for smaller watchlists
          (or up to `max_individual_sheets` symbols). For large universes (e.g. 2,400 NSE stocks),
          individual 500-day candle sheets are omitted to keep the file lightweight (~1 MB)
          and generation fast, while SQLite preserves the complete candle database.
        """
        os.makedirs(os.path.dirname(excel_path), exist_ok=True)
        total_syms = len(symbols)
        include_detail_sheets = total_syms <= max_individual_sheets
        print(f"\n📊 Exporting historical market data for {total_syms} stocks to Excel: {excel_path}...")
        if not include_detail_sheets:
            print(f"ℹ️ Large universe detected ({total_syms} stocks > {max_individual_sheets}). "
                  f"Writing comprehensive Master Summary sheet. Full OHLCV history preserved in SQLite.")

        summary_rows = []
        stock_dfs = {}

        for item in symbols:
            sym = item.get("symbol", "").upper().strip()
            name = item.get("name", sym)
            sector = item.get("sector", "")
            
            summary = self.get_historical_summary(sym)
            
            if include_detail_sheets:
                df = self.load_symbol_history(sym, limit_days=500)
                if not df.empty:
                    df_export = df.copy()
                    df_export['Date'] = df_export['DATE'].dt.strftime('%Y-%m-%d')
                    df_export['Open'] = df_export['OPEN_PRICE'].round(2)
                    df_export['High'] = df_export['HIGH_PRICE'].round(2)
                    df_export['Low'] = df_export['LOW_PRICE'].round(2)
                    df_export['Close'] = df_export['CLOSE_PRICE'].round(2)
                    df_export['Volume'] = df_export['VOLUME']
                    df_export['Daily_Return_Pct'] = (df_export['Close'].pct_change() * 100).round(2)
                    df_export['SMA_50'] = df_export['Close'].rolling(50).mean().round(2)
                    df_export['SMA_200'] = df_export['Close'].rolling(200).mean().round(2)
                    
                    export_cols = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume', 'Daily_Return_Pct', 'SMA_50', 'SMA_200']
                    stock_dfs[sym] = df_export[export_cols].sort_values('Date', ascending=False)

            summary_rows.append({
                "Symbol": sym,
                "Company Name": name,
                "Sector": sector,
                "Latest Date": summary.get("latest_date", "N/A"),
                "Close (Rs)": summary.get("last_close", 0.0),
                "Prev Close (Rs)": summary.get("prev_close", 0.0),
                "52W High (Rs)": summary.get("52w_high", 0.0),
                "52W Low (Rs)": summary.get("52w_low", 0.0),
                "5-Day Return (%)": summary.get("pct_change_5d", 0.0),
                "30-Day Return (%)": summary.get("pct_change_30d", 0.0),
                "1-Year Return (%)": summary.get("pct_change_1y", 0.0),
                "Volume Surge": summary.get("volume_surge_ratio", 1.0),
                "Latest Volume": summary.get("latest_volume", 0),
                "30D Avg Volume": summary.get("avg_volume_30d", 0)
            })

        df_summary = pd.DataFrame(summary_rows)

        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            # 1. Master Summary Sheet
            df_summary.to_excel(writer, sheet_name="Market_Summary", index=False)
            
            # 2. Individual Stock Sheets (if applicable)
            for sym, df_stock in stock_dfs.items():
                sheet_name = sym[:31]
                df_stock.to_excel(writer, sheet_name=sheet_name, index=False)

        if include_detail_sheets:
            print(f"✅ Excel export successfully created with Market_Summary + {len(stock_dfs)} stock detail worksheets!")
        else:
            print(f"✅ Excel summary successfully created: {excel_path} ({len(df_summary)} stocks, 1 sheet)")
        return excel_path


def main():
    import argparse
    from tools.nse_universe import ensure_nse_universe
    try:
        from config import ALL_NSE_SYMBOLS_FILE_PATH
    except ImportError:
        ALL_NSE_SYMBOLS_FILE_PATH = "symbols_nse_all.json"

    parser = argparse.ArgumentParser(description="Reliable Historical Data Sync & Excel Export")
    parser.add_argument("--sync", action="store_true", help="Download/update historical candles from reliable source")
    parser.add_argument("--excel", action="store_true", help="Export historical database to Excel (.xlsx)")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cache is fresh")
    parser.add_argument("--all-nse", action="store_true", help="Sync all NSE stocks from symbols_nse_all.json")
    parser.add_argument("--symbols-file", type=str, default="", help="Path to custom symbols JSON file")
    parser.add_argument("--report-failures", action="store_true", help="Show ticker failure tracker summary + unavailable symbols")
    parser.add_argument("--max-sheets", type=int, default=50, help="Max individual stock sheets in Excel export (default: 50)")
    args = parser.parse_args()

    engine = HistoricalDataEngine()

    # Optional: show failure tracker report
    if args.report_failures:
        try:
            from tools.ticker_validator import TickerFailureTracker
            tracker = TickerFailureTracker()
            summary = tracker.get_summary()
            unavail = tracker.get_unavailable_symbols()
            print("\n📊 Ticker Failure Tracker Summary:")
            for k, v in summary.items():
                print(f"   {k}: {v}")
            if unavail:
                print(f"\n🚫 Symbols marked unavailable ({len(unavail)}):")
                for s in sorted(unavail):
                    print(f"   • {s}")
        except Exception as e:
            print(f"Could not load failure tracker: {e}")
        return

    if args.all_nse:
        sym_file = ALL_NSE_SYMBOLS_FILE_PATH
        if not os.path.exists(sym_file):
            ensure_nse_universe()
    elif args.symbols_file:
        sym_file = args.symbols_file
    else:
        sym_file = SYMBOLS_FILE_PATH

    if not os.path.exists(sym_file):
        print(f"Error: {sym_file} not found.")
        return

    with open(sym_file, "r", encoding="utf-8") as f:
        symbols_data = json.load(f)
        symbols = symbols_data.get("symbols", []) if isinstance(symbols_data, dict) else symbols_data

    # Default action: sync and export if no flags provided
    do_sync = args.sync or (not args.sync and not args.excel)
    do_excel = args.excel or (not args.sync and not args.excel)

    if do_sync:
        engine.sync_all_symbols(symbols, force=args.force)

    if do_excel:
        engine.export_to_excel(symbols, max_individual_sheets=args.max_sheets)


if __name__ == "__main__":
    main()
