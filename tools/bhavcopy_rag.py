"""
Historical NSE Bhavcopy RAG & Statistical Analysis Engine (SQLite Optimized).
Parses local daily Bhavcopy CSV files (sec_bhavdata_full_*.csv) from data/
and indexes them into SQLite storage/cache.db for ultra-fast instant lookups.
"""

import os
import glob
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional
from datetime import datetime

from config import DATA_DIR
from storage.cache_manager import CacheManager

class BhavcopyRAGEngine:
    def __init__(self, data_dir: str = DATA_DIR, cache_manager: CacheManager = None):
        self.data_dir = data_dir
        self.cache_manager = cache_manager or CacheManager()
        self.df_cache = {}

    def load_symbol_history(self, symbol: str, limit_days: int = 500) -> pd.DataFrame:
        """
        Loads symbol history:
        1. Checks in-memory cache.
        2. Checks SQLite database (bhavcopy_cache) for ultra-fast ~1ms retrieval.
        3. If not in SQLite, parses disk CSV files, indexes into SQLite, and returns.
        """
        symbol = symbol.upper()
        if symbol in self.df_cache:
            return self.df_cache[symbol]

        # Step 1: Check SQLite Cache
        db_records = self.cache_manager.get_cached_bhavcopy_history(symbol, limit_days=limit_days)
        if db_records:
            df_sqlite = pd.DataFrame(db_records)
            df_sqlite['DATE'] = pd.to_datetime(df_sqlite['DATE'])
            df_sqlite = df_sqlite.sort_values('DATE').reset_index(drop=True)
            self.df_cache[symbol] = df_sqlite
            return df_sqlite

        # Step 2: Fallback to parsing raw CSV files in data/
        csv_files = glob.glob(os.path.join(self.data_dir, "sec_bhavdata_full_*.csv"))
        if not csv_files:
            return pd.DataFrame()

        records = []
        records_to_sqlite = []

        for file_path in csv_files:
            try:
                df = pd.read_csv(file_path, skipinitialspace=True)
                df.columns = [c.strip() for c in df.columns]
                
                symbol_match = df[(df['SYMBOL'] == symbol) & (df['SERIES'].isin(['EQ', 'BE']))]
                if not symbol_match.empty:
                    row = symbol_match.iloc[0].to_dict()
                    records.append(row)
                    
                    # Prepare record for SQLite persistence
                    date_str = str(row.get('DATE1', '')).strip()
                    try:
                        dt = pd.to_datetime(date_str, format='%d-%b-%Y').strftime('%Y-%m-%d')
                    except Exception:
                        dt = date_str

                    records_to_sqlite.append({
                        "symbol": symbol,
                        "date": dt,
                        "open": row.get("OPEN_PRICE", 0),
                        "high": row.get("HIGH_PRICE", 0),
                        "low": row.get("LOW_PRICE", 0),
                        "close": row.get("CLOSE_PRICE", 0),
                        "prev_close": row.get("PREV_CLOSE", 0),
                        "volume": row.get("TTL_TRD_QNTY", 0),
                        "deliv_qty": row.get("DELIV_QTY", 0),
                        "deliv_per": row.get("DELIV_PER", 0)
                    })
            except Exception:
                continue

        if not records:
            return pd.DataFrame()

        df_symbol = pd.DataFrame(records)
        if 'DATE1' in df_symbol.columns:
            df_symbol['DATE'] = pd.to_datetime(df_symbol['DATE1'].astype(str).str.strip(), format='%d-%b-%Y', errors='coerce')
        
        df_symbol = df_symbol.sort_values('DATE').dropna(subset=['DATE'])
        
        numeric_cols = ['PREV_CLOSE', 'OPEN_PRICE', 'HIGH_PRICE', 'LOW_PRICE', 'LAST_PRICE', 'CLOSE_PRICE', 'AVG_PRICE', 'TTL_TRD_QNTY', 'NO_OF_TRADES', 'DELIV_QTY', 'DELIV_PER']
        for col in numeric_cols:
            if col in df_symbol.columns:
                df_symbol[col] = pd.to_numeric(df_symbol[col].astype(str).str.replace('-', '0').str.strip(), errors='coerce').fillna(0)

        df_symbol = df_symbol.tail(limit_days).reset_index(drop=True)
        self.df_cache[symbol] = df_symbol

        # Save to SQLite database for future 1ms lookups
        if records_to_sqlite:
            try:
                self.cache_manager.save_bhavcopy_records(records_to_sqlite)
            except Exception:
                pass

        return df_symbol

    def get_historical_summary(self, symbol: str) -> Dict[str, Any]:
        """
        Generates statistical insights and RAG context for the Historical RAG Agent.
        """
        df = self.load_symbol_history(symbol)
        if df.empty:
            return {"symbol": symbol, "status": "No historical Bhavcopy data found."}

        latest = df.iloc[-1]
        prev_5d = df.tail(5)
        prev_30d = df.tail(30)
        prev_1y = df.tail(252)

        # Delivery & Volume Analysis
        avg_vol_30 = prev_30d['TTL_TRD_QNTY'].mean()
        latest_vol = latest['TTL_TRD_QNTY']
        vol_surge_ratio = round(latest_vol / (avg_vol_30 + 1e-5), 2)

        avg_deliv_per_30 = prev_30d['DELIV_PER'].mean()
        latest_deliv_per = latest['DELIV_PER']

        # Price Performance
        close_latest = latest['CLOSE_PRICE']
        return_5d = round(((close_latest - prev_5d.iloc[0]['CLOSE_PRICE']) / (prev_5d.iloc[0]['CLOSE_PRICE'] + 1e-5)) * 100, 2)
        return_30d = round(((close_latest - prev_30d.iloc[0]['CLOSE_PRICE']) / (prev_30d.iloc[0]['CLOSE_PRICE'] + 1e-5)) * 100, 2)
        return_1y = round(((close_latest - prev_1y.iloc[0]['CLOSE_PRICE']) / (prev_1y.iloc[0]['CLOSE_PRICE'] + 1e-5)) * 100, 2) if len(prev_1y) > 0 else 0.0

        high_52w = prev_1y['HIGH_PRICE'].max() if len(prev_1y) > 0 else latest['HIGH_PRICE']
        low_52w = prev_1y['LOW_PRICE'].min() if len(prev_1y) > 0 else latest['LOW_PRICE']

        return {
            "symbol": symbol,
            "latest_date": str(latest['DATE'].date()) if pd.notnull(latest['DATE']) else "N/A",
            "last_close": float(latest['CLOSE_PRICE']),
            "prev_close": float(latest['PREV_CLOSE']),
            "day_high": float(latest['HIGH_PRICE']),
            "day_low": float(latest['LOW_PRICE']),
            "52w_high": float(high_52w),
            "52w_low": float(low_52w),
            "pct_change_5d": return_5d,
            "pct_change_30d": return_30d,
            "pct_change_1y": return_1y,
            "latest_volume": int(latest_vol),
            "volume_surge_ratio": vol_surge_ratio,
            "latest_deliv_per": float(latest_deliv_per),
            "avg_deliv_per_30d": round(float(avg_deliv_per_30), 2),
            "data_points": len(df)
        }
