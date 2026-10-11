"""
SQLite Cache Manager for Incremental Data Storage & Retrieval.
Stores historical Bhavcopy stats, web news, macro indicators, technical calculations,
and past agent analysis outputs to avoid redundant queries and reduce execution time.
"""

import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from config import CACHE_DB_PATH

class CacheManager:
    def __init__(self, db_path: str = CACHE_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes tables for incremental storage."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Historical Bhavcopy summary per stock
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bhavcopy_cache (
                    symbol TEXT,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    prev_close REAL,
                    volume INTEGER,
                    deliv_qty INTEGER,
                    deliv_per REAL,
                    PRIMARY KEY (symbol, date)
                )
            """)

            # Online News & Sentiment Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS news_cache (
                    symbol TEXT,
                    url TEXT PRIMARY KEY,
                    title TEXT,
                    snippet TEXT,
                    source TEXT,
                    fetch_date TEXT,
                    sentiment_score REAL,
                    sentiment_label TEXT
                )
            """)

            # Global Macro Metrics Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS macro_cache (
                    indicator_name TEXT,
                    fetch_date TEXT,
                    value REAL,
                    unit TEXT,
                    summary TEXT,
                    PRIMARY KEY (indicator_name, fetch_date)
                )
            """)

            # Technical Analysis Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tech_cache (
                    symbol TEXT,
                    date TEXT,
                    sma_20 REAL,
                    sma_50 REAL,
                    sma_200 REAL,
                    rsi_14 REAL,
                    macd REAL,
                    macd_signal REAL,
                    bollinger_upper REAL,
                    bollinger_lower REAL,
                    support REAL,
                    resistance REAL,
                    PRIMARY KEY (symbol, date)
                )
            """)

            # Shared Common Market Context Bulletin Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS shared_market_bulletin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT,
                    sentiment_label TEXT,
                    macro_summary TEXT,
                    raw_indicators TEXT
                )
            """)

            # Agent Runs & Predictions Storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS agent_runs_cache (
                    run_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    timestamp TEXT,
                    agent_name TEXT,
                    output_data TEXT
                )
            """)
            conn.commit()

    # --- Shared Market Bulletin API ---
    def get_latest_market_bulletin(self) -> Optional[Dict[str, Any]]:
        """Retrieves the latest common market context bulletin."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, sentiment_label, macro_summary, raw_indicators
                FROM shared_market_bulletin
                ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return {
                    "timestamp": row[0],
                    "sentiment_label": row[1],
                    "summary": row[2],
                    "raw_indicators": json.loads(row[3]) if row[3] else {}
                }
            return None

    def save_market_bulletin(self, sentiment_label: str, macro_summary: str, raw_indicators: Dict[str, Any]):
        """Saves a newly generated common market context bulletin."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            cursor.execute("""
                INSERT INTO shared_market_bulletin (timestamp, sentiment_label, macro_summary, raw_indicators)
                VALUES (?, ?, ?, ?)
            """, (now_str, sentiment_label, macro_summary, json.dumps(raw_indicators)))
            conn.commit()

    # --- Bhavcopy Historical Cache API ---
    def get_cached_bhavcopy_history(self, symbol: str, limit_days: int = 500) -> List[Dict[str, Any]]:
        """Retrieves cached Bhavcopy history from SQLite database for a symbol."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT date, open, high, low, close, prev_close, volume, deliv_qty, deliv_per
                FROM bhavcopy_cache
                WHERE symbol = ?
                ORDER BY date ASC
            """, (symbol.upper(),))
            rows = cursor.fetchall()
            if not rows:
                return []
            
            result = [
                {
                    "SYMBOL": symbol.upper(),
                    "DATE": r[0],
                    "OPEN_PRICE": r[1],
                    "HIGH_PRICE": r[2],
                    "LOW_PRICE": r[3],
                    "CLOSE_PRICE": r[4],
                    "PREV_CLOSE": r[5],
                    "TTL_TRD_QNTY": r[6],
                    "DELIV_QTY": r[7],
                    "DELIV_PER": r[8]
                }
                for r in rows
            ]
            return result[-limit_days:]

    def save_bhavcopy_records(self, records: List[Dict[str, Any]]):
        """Batch inserts parsed Bhavcopy daily records into SQLite database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT OR REPLACE INTO bhavcopy_cache
                (symbol, date, open, high, low, close, prev_close, volume, deliv_qty, deliv_per)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r["symbol"].upper(),
                    str(r["date"]),
                    float(r.get("open", 0.0)),
                    float(r.get("high", 0.0)),
                    float(r.get("low", 0.0)),
                    float(r.get("close", 0.0)),
                    float(r.get("prev_close", 0.0)),
                    int(r.get("volume", 0)),
                    int(r.get("deliv_qty", 0)),
                    float(r.get("deliv_per", 0.0))
                )
                for r in records
            ])
            conn.commit()

    # --- News Cache API ---
    def get_cached_news(self, symbol: str, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """Retrieves cached news for a stock symbol if fetched within max_age_hours."""
        cutoff_date = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT title, snippet, source, fetch_date, sentiment_score, sentiment_label
                FROM news_cache
                WHERE symbol = ? AND fetch_date >= ?
                ORDER BY fetch_date DESC
            """, (symbol.upper(), cutoff_date))
            rows = cursor.fetchall()
            return [
                {
                    "title": r[0], "snippet": r[1], "source": r[2],
                    "fetch_date": r[3], "sentiment_score": r[4], "sentiment_label": r[5]
                }
                for r in rows
            ]

    def save_news(self, symbol: str, news_items: List[Dict[str, Any]]):
        """Saves scraped news items into cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            for item in news_items:
                url = item.get("url") or f"{symbol}_{hash(item.get('title', ''))}"
                cursor.execute("""
                    INSERT OR REPLACE INTO news_cache 
                    (symbol, url, title, snippet, source, fetch_date, sentiment_score, sentiment_label)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol.upper(),
                    url,
                    item.get("title", ""),
                    item.get("snippet", ""),
                    item.get("source", "Web"),
                    now_str,
                    item.get("sentiment_score", 0.0),
                    item.get("sentiment_label", "Neutral")
                ))
            conn.commit()

    # --- Macro Cache API ---
    def get_cached_macro(self, max_age_hours: int = 12) -> List[Dict[str, Any]]:
        cutoff_date = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT indicator_name, fetch_date, value, unit, summary
                FROM macro_cache
                WHERE fetch_date >= ?
            """, (cutoff_date,))
            rows = cursor.fetchall()
            return [
                {"indicator": r[0], "fetch_date": r[1], "value": r[2], "unit": r[3], "summary": r[4]}
                for r in rows
            ]

    def save_macro(self, macro_data: List[Dict[str, Any]]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            for m in macro_data:
                cursor.execute("""
                    INSERT OR REPLACE INTO macro_cache (indicator_name, fetch_date, value, unit, summary)
                    VALUES (?, ?, ?, ?, ?)
                """, (m["indicator"], now_str, m.get("value", 0.0), m.get("unit", ""), m.get("summary", "")))
            conn.commit()

    # --- Agent Runs Cache ---
    def save_agent_output(self, symbol: str, agent_name: str, output_data: Dict[str, Any]):
        run_id = f"{symbol.upper()}_{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_runs_cache (run_id, symbol, timestamp, agent_name, output_data)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, symbol.upper(), datetime.now().isoformat(), agent_name, json.dumps(output_data)))
            conn.commit()

    def get_latest_agent_output(self, symbol: str, agent_name: str, max_age_hours: int = 12) -> Optional[Dict[str, Any]]:
        cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT output_data FROM agent_runs_cache
                WHERE symbol = ? AND agent_name = ? AND timestamp >= ?
                ORDER BY timestamp DESC LIMIT 1
            """, (symbol.upper(), agent_name, cutoff))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
