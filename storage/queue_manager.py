"""
Persistent Background Queue Manager using Valkey / Redis with SQLite Fallback.
Provides resilient, interruptible background task queueing for stock analysis.
If power or internet is interrupted, resuming execution picks up pending stock items without restarting from scratch.
"""

import json
import os
import sqlite3
from typing import Dict, Any, Optional, List

from config import CACHE_DB_PATH, VERBOSE_LOGGING

VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))

class ValkeyQueueManager:
    def __init__(self, host: str = VALKEY_HOST, port: int = VALKEY_PORT, db_path: str = CACHE_DB_PATH):
        self.host = host
        self.port = port
        self.db_path = db_path
        self.client = None
        self.use_valkey = False
        self._connect_valkey()
        self._init_sqlite_queue()

    def _connect_valkey(self):
        """Attempts connection to local Valkey / Redis server and displays status/warnings."""
        try:
            import redis
            client = redis.Redis(host=self.host, port=self.port, socket_timeout=2.0)
            client.ping()
            self.client = client
            self.use_valkey = True
            print(f"✅ [Valkey Queue Engine] Connected to Valkey server on {self.host}:{self.port}")
        except Exception as e:
            self.use_valkey = False
            print("=" * 80)
            print(f"⚠️  VALKEY WARNING: Valkey queue server is NOT running on {self.host}:{self.port}")
            print(f"   To run with Valkey queue, start your Valkey service: valkey-server (or redis-server).")
            print(f"   Falling back to persistent SQLite queue storage ({CACHE_DB_PATH})")
            print("=" * 80 + "\n")

    def _init_sqlite_queue(self):
        """Initializes SQLite fallback persistent queue table."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS persistent_stock_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT UNIQUE,
                    company_name TEXT,
                    sector TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Reset any tasks stuck in 'in_progress' from a previous interrupted run
            cursor.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE status = 'in_progress'")
            conn.commit()

    def reset_queue(self, symbols_list: Optional[List[Dict[str, Any]]] = None):
        """Resets the queue so target symbols are pending again for a new run."""
        if self.use_valkey and self.client:
            try:
                self.client.delete("nse_stock_queue")
                self.client.delete("nse_completed_symbols")
                if symbols_list:
                    for item in symbols_list:
                        self.client.rpush("nse_stock_queue", json.dumps(item))
            except Exception as e:
                print(f"⚠️ [Valkey Reset Notice]: {e}")

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if symbols_list:
                for item in symbols_list:
                    symbol = item.get("symbol", "").upper()
                    company_name = item.get("name", "")
                    sector = item.get("sector", "")
                    cursor.execute("""
                        INSERT INTO persistent_stock_queue (symbol, company_name, sector, status)
                        VALUES (?, ?, ?, 'pending')
                        ON CONFLICT(symbol) DO UPDATE SET status = 'pending', company_name = excluded.company_name, sector = excluded.sector
                    """, (symbol, company_name, sector))
            else:
                cursor.execute("UPDATE persistent_stock_queue SET status = 'pending'")
            conn.commit()

    def enqueue_symbols(self, symbols_list: List[Dict[str, Any]], force: bool = False):
        """Pushes target symbols into queue, skipping already completed items unless forced."""
        if force:
            self.reset_queue(symbols_list)
            return

        if self.use_valkey and self.client:
            try:
                for item in symbols_list:
                    symbol = item.get("symbol", "").upper()
                    # Check if already completed in Valkey set
                    if not force and self.client.sismember("nse_completed_symbols", symbol):
                        continue
                    item_json = json.dumps(item)
                    # Push to Valkey list
                    self.client.rpush("nse_stock_queue", item_json)
                return
            except Exception as e:
                print(f"⚠️ [Valkey Queue Error] Switching to SQLite queue: {e}")

        # SQLite Persistent Queue Fallback
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for item in symbols_list:
                symbol = item.get("symbol", "").upper()
                company_name = item.get("name", "")
                sector = item.get("sector", "")
                
                cursor.execute("""
                    INSERT OR IGNORE INTO persistent_stock_queue (symbol, company_name, sector, status)
                    VALUES (?, ?, ?, 'pending')
                """, (symbol, company_name, sector))
            conn.commit()

    def dequeue_symbol(self, symbols_filter: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Pops the next pending stock symbol task from queue (optionally filtered by symbol names)."""
        if self.use_valkey and self.client:
            try:
                raw_item = self.client.lpop("nse_stock_queue")
                if raw_item:
                    item_str = raw_item.decode("utf-8") if isinstance(raw_item, bytes) else raw_item
                    item_data = json.loads(item_str)
                    if symbols_filter and item_data.get("symbol", "").upper() not in [s.upper() for s in symbols_filter]:
                        # Put back at end if not in filter
                        self.client.rpush("nse_stock_queue", item_str)
                    else:
                        return item_data
            except Exception:
                pass

        # SQLite Fallback Dequeue
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if symbols_filter:
                placeholders = ",".join("?" * len(symbols_filter))
                cursor.execute(f"""
                    SELECT id, symbol, company_name, sector FROM persistent_stock_queue
                    WHERE status = 'pending' AND UPPER(symbol) IN ({placeholders})
                    ORDER BY id ASC LIMIT 1
                """, [s.upper() for s in symbols_filter])
            else:
                cursor.execute("""
                    SELECT id, symbol, company_name, sector FROM persistent_stock_queue
                    WHERE status = 'pending'
                    ORDER BY id ASC LIMIT 1
                """)
            row = cursor.fetchone()
            if row:
                task_id, symbol, company_name, sector = row
                cursor.execute("UPDATE persistent_stock_queue SET status = 'in_progress' WHERE id = ?", (task_id,))
                conn.commit()
                return {"symbol": symbol, "name": company_name, "sector": sector, "_task_id": task_id}
            return None

    def mark_completed(self, symbol: str, task_id: Optional[int] = None):
        """Marks a stock symbol analysis task as completed."""
        symbol = symbol.upper()
        if self.use_valkey and self.client:
            try:
                self.client.sadd("nse_completed_symbols", symbol)
            except Exception:
                pass

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE persistent_stock_queue SET status = 'completed' WHERE symbol = ?", (symbol,))
            conn.commit()

    def get_symbol_statuses(self) -> Dict[str, str]:
        """Returns a mapping of symbol -> queue status ('pending', 'in_progress', 'completed')."""
        statuses = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, status FROM persistent_stock_queue")
            for sym, stat in cursor.fetchall():
                statuses[sym.upper()] = stat
        return statuses

    def get_queue_status(self) -> Dict[str, Any]:
        """Returns statistics on pending and completed queue items."""
        if self.use_valkey and self.client:
            try:
                pending_count = self.client.llen("nse_stock_queue")
                completed_count = self.client.scard("nse_completed_symbols")
                return {
                    "engine": "Valkey / Redis",
                    "pending": pending_count,
                    "completed": completed_count
                }
            except Exception:
                pass

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM persistent_stock_queue GROUP BY status")
            counts = dict(cursor.fetchall())
            return {
                "engine": "SQLite Persistent Queue",
                "pending": counts.get("pending", 0),
                "in_progress": counts.get("in_progress", 0),
                "completed": counts.get("completed", 0)
            }
