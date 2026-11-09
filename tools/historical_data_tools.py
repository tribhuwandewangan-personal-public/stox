"""
Reliable Historical Data Engine & Excel Export Utility.
Replaces legacy scraping with split/dividend-adjusted historical data (via yfinance),
persists into SQLite (historical_candles table), and exports to Excel (.xlsx).
"""

import os
import sys
import json
import time
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


class HistoricalDataEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.df_cache: Dict[str, pd.DataFrame] = {}
        self._df_loaded_at: Dict[str, float] = {}
        self._last_sync_attempt: Dict[str, float] = {}

    def fetch_from_source(self, symbol: str, period: str = "5y", start: Optional[str] = None) -> pd.DataFrame:
        """
        Fetches corporate-action adjusted daily OHLCV candles from reliable market feeds.
        Primary: <SYMBOL>.NS (NSE)
        Fallback: <SYMBOL>.BO (BSE)
        If `start` (YYYY-MM-DD) is given only candles from that date are downloaded, otherwise `period`.
        """
        import yfinance as yf

        symbol_clean = symbol.upper().strip()
        alias_map = {
            "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS", "TATAMOTORS.BO"],
            "NSE": ["NSE.BO", "NSE.NS"]
        }
        candidates = alias_map.get(symbol_clean, [f"{symbol_clean}.NS", f"{symbol_clean}.BO"])

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
                    break
            except Exception:
                continue

        if df_history.empty:
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

    @staticmethod
    def _drop_provisional_bar(df: pd.DataFrame) -> pd.DataFrame:
        """
        Yahoo returns today's in-progress bar while the session runs. Storing it would freeze an intraday price
        in as that day's close, so a bar for a not-yet-final session is dropped (live prices come from the
        quote layer instead).
        """
        if df is None or df.empty:
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
        return (time.time() - self._last_sync_attempt.get(symbol, 0.0)) < RECHECK_SECONDS

    def _remember(self, symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        self.df_cache[symbol] = df
        self._df_loaded_at[symbol] = time.time()
        return df

    @staticmethod
    def _df_to_records(symbol: str, df: pd.DataFrame) -> List[Dict[str, Any]]:
        dates = df['DATE'].dt.strftime('%Y-%m-%d')
        return [
            {
                "symbol": symbol, "date": d,
                "open": float(o), "high": float(h), "low": float(l), "close": float(c),
                "adj_close": float(a), "volume": int(v), "dividends": float(dv), "splits": float(sp),
            }
            for d, o, h, l, c, a, v, dv, sp in zip(
                dates, df['OPEN_PRICE'], df['HIGH_PRICE'], df['LOW_PRICE'], df['CLOSE_PRICE'],
                df['ADJ_CLOSE'], df['VOLUME'], df['DIVIDENDS'], df['SPLITS']
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

    def _full_refresh(self, symbol: str, period: str, fallback: pd.DataFrame) -> pd.DataFrame:
        df_fresh = self.fetch_from_source(symbol, period=period)
        if df_fresh.empty:
            if not fallback.empty:
                return self._remember(symbol, fallback)
            return pd.DataFrame()
        # replace_symbol: drop old rows so every stored candle shares one adjustment basis
        self.cache_manager.save_historical_candles(self._df_to_records(symbol, df_fresh), replace_symbol=symbol)
        return self._remember(symbol, self._load_cached_df(symbol))

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
        df = self.df_cache.get(symbol)
        if df is None or (time.time() - self._df_loaded_at.get(symbol, 0.0)) > DF_CACHE_TTL_SECONDS:
            loaded = self._load_cached_df(symbol)
            if not loaded.empty:
                df = self._remember(symbol, loaded)
            elif df is None:
                df = self.sync_symbol_data(symbol, period="5y")
                if df.empty:
                    return pd.DataFrame()
        return df.tail(limit_days).reset_index(drop=True)

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
        """
        results: Dict[str, bool] = {}
        total = len(symbols)
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
            futures = [pool.submit(_sync, item) for item in symbols]
            for idx, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                sym, df, elapsed, err = fut.result()
                if err is not None:
                    print(f"  [{idx:2d}/{total:2d}] ❌ {sym:<10} | Error: {err}")
                    results[sym] = False
                elif df is not None and len(df) > 0:
                    latest_d = df.iloc[-1]['DATE'].strftime('%Y-%m-%d')
                    print(f"  [{idx:2d}/{total:2d}] ✅ {sym:<10} | {len(df):4d} candles synced | Latest: {latest_d} ({elapsed:.2f}s)")
                    results[sym] = True
                else:
                    print(f"  [{idx:2d}/{total:2d}] ⚠️ {sym:<10} | No candles returned ({elapsed:.2f}s)")
                    results[sym] = False

        return results

    def export_to_excel(self, symbols: List[Dict[str, Any]], excel_path: str = HISTORICAL_EXCEL_PATH) -> str:
        """
        Exports the synchronized historical data to a rich Excel workbook (.xlsx).
        - Sheet 1: Master Summary (All stocks with 52W H/L, Returns, Surge, Volume)
        - Dedicated Sheets: Per stock OHLCV history with indicators
        """
        os.makedirs(os.path.dirname(excel_path), exist_ok=True)
        print(f"\n📊 Exporting historical market data to Excel: {excel_path}...")

        summary_rows = []
        stock_dfs = {}

        for item in symbols:
            sym = item.get("symbol", "").upper().strip()
            name = item.get("name", sym)
            sector = item.get("sector", "")
            
            summary = self.get_historical_summary(sym)
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
            
            # 2. Individual Stock Sheets (truncated sheet names if >31 chars)
            for sym, df_stock in stock_dfs.items():
                sheet_name = sym[:31]
                df_stock.to_excel(writer, sheet_name=sheet_name, index=False)

        print(f"✅ Excel export successfully created with {len(stock_dfs)} stock worksheets!")
        return excel_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Reliable Historical Data Sync & Excel Export")
    parser.add_argument("--sync", action="store_true", help="Download/update historical candles from reliable source")
    parser.add_argument("--excel", action="store_true", help="Export historical database to Excel (.xlsx)")
    parser.add_argument("--force", action="store_true", help="Force re-download even if cache is fresh")
    args = parser.parse_args()

    engine = HistoricalDataEngine()

    if not os.path.exists(SYMBOLS_FILE_PATH):
        print(f"Error: {SYMBOLS_FILE_PATH} not found.")
        return

    with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
        symbols_data = json.load(f)
        symbols = symbols_data.get("symbols", [])

    # Default action: sync and export if no flags provided
    do_sync = args.sync or (not args.sync and not args.excel)
    do_excel = args.excel or (not args.sync and not args.excel)

    if do_sync:
        engine.sync_all_symbols(symbols, force=args.force)

    if do_excel:
        engine.export_to_excel(symbols)


if __name__ == "__main__":
    main()
