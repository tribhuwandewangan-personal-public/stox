"""
Reliable Historical Data Engine & Excel Export Utility.
Replaces legacy scraping with split/dividend-adjusted historical data (via yfinance),
persists into SQLite (historical_candles table), and exports to Excel (.xlsx).
"""

import os
import sys
import json
import time
import contextlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import CACHE_DB_PATH, SYMBOLS_FILE_PATH, HISTORICAL_EXCEL_PATH, REPORTS_DIR
from storage.cache_manager import CacheManager


class HistoricalDataEngine:
    def __init__(self, cache_manager: Optional[CacheManager] = None):
        self.cache_manager = cache_manager or CacheManager()
        self.df_cache: Dict[str, pd.DataFrame] = {}

    def fetch_from_source(self, symbol: str, period: str = "5y") -> pd.DataFrame:
        """
        Fetches corporate-action adjusted daily OHLCV candles from reliable market feeds.
        Primary: <SYMBOL>.NS (NSE)
        Fallback: <SYMBOL>.BO (BSE)
        """
        import yfinance as yf

        symbol_clean = symbol.upper().strip()
        alias_map = {
            "TATAMOTORS": ["TMPV.NS", "TMCV.NS", "TATAMOTORS.NS", "TATAMOTORS.BO"]
        }
        candidates = alias_map.get(symbol_clean, [f"{symbol_clean}.NS", f"{symbol_clean}.BO"])
        
        df_history = pd.DataFrame()
        
        for candidate in candidates:
            try:
                # Suppress noisy yfinance stderr output
                with open(os.devnull, 'w', encoding='utf-8', errors='replace') as devnull:
                    with contextlib.redirect_stderr(devnull), contextlib.redirect_stdout(devnull):
                        ticker = yf.Ticker(candidate)
                        df = ticker.history(period=period, auto_adjust=True)
                
                if df is not None and not df.empty:
                    df_history = df.copy()
                    break
            except Exception:
                continue

        if df_history.empty:
            return pd.DataFrame()

        # Format dataframe into standardized schema
        df_history = df_history.reset_index()
        
        # Standardize date column
        date_col = 'Date' if 'Date' in df_history.columns else df_history.columns[0]
        df_history['DATE'] = pd.to_datetime(df_history[date_col]).dt.tz_localize(None)
        
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
        return df_history

    def sync_symbol_data(self, symbol: str, period: str = "5y", force: bool = False) -> pd.DataFrame:
        """
        Syncs symbol candles:
        - If cached in SQLite and fresh (<24h), returns cached DataFrame.
        - Otherwise, downloads adjusted data and writes to SQLite database.
        """
        symbol = symbol.upper().strip()
        
        if not force:
            cached_records = self.cache_manager.get_cached_candles(symbol, limit_days=1500)
            if cached_records:
                latest_date_str = cached_records[-1].get("DATE", "")
                try:
                    latest_dt = datetime.strptime(latest_date_str[:10], "%Y-%m-%d")
                    # If latest candle is within 3 days (accounting for weekends), consider fresh
                    if (datetime.now() - latest_dt).days <= 3:
                        df_cached = pd.DataFrame(cached_records)
                        df_cached['DATE'] = pd.to_datetime(df_cached['DATE'])
                        self.df_cache[symbol] = df_cached
                        return df_cached
                except Exception:
                    pass

        # Fetch fresh data from reliable source
        df_fresh = self.fetch_from_source(symbol, period=period)
        if df_fresh.empty:
            # Fallback to existing cache if available
            cached_records = self.cache_manager.get_cached_candles(symbol, limit_days=1500)
            if cached_records:
                df_cached = pd.DataFrame(cached_records)
                df_cached['DATE'] = pd.to_datetime(df_cached['DATE'])
                self.df_cache[symbol] = df_cached
                return df_cached
            return pd.DataFrame()

        # Prepare records for SQLite
        records = []
        for _, row in df_fresh.iterrows():
            dt_str = row['DATE'].strftime('%Y-%m-%d')
            records.append({
                "symbol": symbol,
                "date": dt_str,
                "open": float(row['OPEN_PRICE']),
                "high": float(row['HIGH_PRICE']),
                "low": float(row['LOW_PRICE']),
                "close": float(row['CLOSE_PRICE']),
                "adj_close": float(row['ADJ_CLOSE']),
                "volume": int(row['VOLUME']),
                "dividends": float(row.get('DIVIDENDS', 0.0)),
                "splits": float(row.get('SPLITS', 0.0))
            })

        self.cache_manager.save_historical_candles(records)
        self.df_cache[symbol] = df_fresh
        return df_fresh

    def load_symbol_history(self, symbol: str, limit_days: int = 500) -> pd.DataFrame:
        """
        Loads symbol history:
        1. Checks in-memory cache.
        2. Checks SQLite database.
        3. If missing, fetches from source, saves to SQLite, and returns.
        """
        symbol = symbol.upper().strip()
        if symbol in self.df_cache:
            df = self.df_cache[symbol]
            return df.tail(limit_days).reset_index(drop=True)

        # Check SQLite
        cached_records = self.cache_manager.get_cached_candles(symbol, limit_days=limit_days)
        if cached_records:
            df = pd.DataFrame(cached_records)
            df['DATE'] = pd.to_datetime(df['DATE'])
            df = df.sort_values('DATE').reset_index(drop=True)
            self.df_cache[symbol] = df
            return df

        # Fallback to fetching fresh
        df = self.sync_symbol_data(symbol, period="5y")
        if not df.empty:
            return df.tail(limit_days).reset_index(drop=True)
        return pd.DataFrame()

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

    def sync_all_symbols(self, symbols: List[Dict[str, Any]], force: bool = False) -> Dict[str, bool]:
        """
        Synchronizes historical data for all symbols and caches to SQLite.
        """
        results = {}
        total = len(symbols)
        print(f"📥 Syncing reliable historical data for {total} symbols...")
        
        for idx, item in enumerate(symbols, 1):
            sym = item.get("symbol", "").upper().strip()
            name = item.get("name", sym)
            t0 = time.time()
            try:
                df = self.sync_symbol_data(sym, period="5y", force=force)
                rows = len(df)
                elapsed = time.time() - t0
                if rows > 0:
                    latest_d = df.iloc[-1]['DATE'].strftime('%Y-%m-%d')
                    print(f"  [{idx:2d}/{total:2d}] ✅ {sym:<10} | {rows:4d} candles synced | Latest: {latest_d} ({elapsed:.2f}s)")
                    results[sym] = True
                else:
                    print(f"  [{idx:2d}/{total:2d}] ⚠️ {sym:<10} | No candles returned ({elapsed:.2f}s)")
                    results[sym] = False
            except Exception as e:
                print(f"  [{idx:2d}/{total:2d}] ❌ {sym:<10} | Error: {e}")
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
