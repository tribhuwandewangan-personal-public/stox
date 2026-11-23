"""
Persistent Background Queue Manager using Valkey / Redis with SQLite Fallback.
When Valkey is available, all queue state (pending list, in-progress set, completed set,
and per-symbol statuses) is stored exclusively in Valkey without touching SQLite cache.db.
Falls back to SQLite (cache.db) only when Valkey is unreachable.
"""

import json
import os
from typing import Dict, Any, Optional, List

from config import CACHE_DB_PATH
from storage.cache_manager import open_db

VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))


class ValkeyQueueManager:
    def __init__(
        self,
        host: str = VALKEY_HOST,
        port: int = VALKEY_PORT,
        db_path: str = CACHE_DB_PATH,
        prefer_valkey: Optional[bool] = None,
    ):
        self.host = host
        self.port = port
        self.db_path = db_path
        self.client = None
        self.use_valkey = False
        # Connect to Valkey by default when using the primary cache DB path (or when explicitly requested)
        should_try_valkey = prefer_valkey if prefer_valkey is not None else (
            os.path.abspath(db_path) == os.path.abspath(CACHE_DB_PATH)
        )
        if should_try_valkey:
            self._connect_valkey()
        if not self.use_valkey:
            self._init_sqlite_queue()

    def _connect_valkey(self):
        """Attempts connection to local Valkey / Redis server and displays status/warnings."""
        try:
            import redis
            client = redis.Redis(host=self.host, port=self.port, socket_timeout=2.0)
            client.ping()
            self.client = client
            self.use_valkey = True
            print(f"✅ [Valkey Queue Engine] Connected to Valkey server on {self.host}:{self.port} (SQLite cache.db bypassed)")
        except Exception:
            self.use_valkey = False
            print("=" * 80)
            print(f"⚠️  VALKEY WARNING: Valkey queue server is NOT running on {self.host}:{self.port}")
            print("   To run with Valkey queue, start your Valkey service: valkey-server (or docker start stox-valkey).")
            print(f"   Falling back to persistent SQLite queue storage ({self.db_path})")
            print("=" * 80 + "\n")

    def _init_sqlite_queue(self):
        """Initializes SQLite fallback persistent queue table ONLY when Valkey is unavailable."""
        if self.use_valkey:
            return
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with open_db(self.db_path) as conn:
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
            cursor.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE status = 'in_progress'")
            conn.commit()

    def reset_queue(self, symbols_list: Optional[List[Dict[str, Any]]] = None):
        """Resets the queue so target symbols are pending again for a new run."""
        if self.use_valkey and self.client:
            try:
                pipe = self.client.pipeline(transaction=False)
                pipe.delete("nse_stock_queue", "nse_completed_symbols", "nse_in_progress_symbols")
                if symbols_list:
                    status_map = {}
                    for item in symbols_list:
                        sym = str(item.get("symbol", "")).upper().strip()
                        if not sym:
                            continue
                        pipe.rpush("nse_stock_queue", json.dumps(item))
                        status_map[sym] = "pending"
                    if status_map:
                        pipe.hset("nse_symbol_statuses", mapping=status_map)
                else:
                    existing = self.client.hkeys("nse_symbol_statuses")
                    if existing:
                        status_map = {
                            (k.decode("utf-8") if isinstance(k, bytes) else str(k)): "pending"
                            for k in existing
                        }
                        pipe.hset("nse_symbol_statuses", mapping=status_map)
                pipe.execute()
                return
            except Exception as e:
                print(f"⚠️ [Valkey Reset Notice]: {e}")
                return

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
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
                    symbol = str(item.get("symbol", "")).upper().strip()
                    if not symbol:
                        continue
                    if not force and self.client.sismember("nse_completed_symbols", symbol):
                        continue
                    self.client.rpush("nse_stock_queue", json.dumps(item))
                    self.client.hset("nse_symbol_statuses", symbol, "pending")
                return
            except Exception as e:
                print(f"⚠️ [Valkey Queue Error]: {e}")
                return

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
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
                q_len = int(self.client.llen("nse_stock_queue") or 0)
                if q_len <= 0:
                    return None
                allowed = {s.upper() for s in symbols_filter} if symbols_filter else None
                for _ in range(q_len):
                    raw_item = self.client.lpop("nse_stock_queue")
                    if not raw_item:
                        return None
                    item_str = raw_item.decode("utf-8") if isinstance(raw_item, bytes) else raw_item
                    item_data = json.loads(item_str)
                    sym = str(item_data.get("symbol", "")).upper().strip()
                    if allowed is not None and sym not in allowed:
                        self.client.rpush("nse_stock_queue", item_str)
                    else:
                        if sym:
                            self.client.sadd("nse_in_progress_symbols", sym)
                            self.client.hset("nse_symbol_statuses", sym, "in_progress")
                        return item_data
                return None
            except Exception:
                return None

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
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
        symbol = symbol.upper().strip()
        if self.use_valkey and self.client:
            try:
                pipe = self.client.pipeline(transaction=False)
                pipe.srem("nse_in_progress_symbols", symbol)
                pipe.sadd("nse_completed_symbols", symbol)
                pipe.hset("nse_symbol_statuses", symbol, "completed")
                pipe.execute()
            except Exception:
                pass
            return

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE persistent_stock_queue SET status = 'completed' WHERE symbol = ?", (symbol,))
            conn.commit()

    def remove_symbol(self, symbol: str):
        """Removes a symbol from queue tracking."""
        symbol = symbol.upper().strip()
        if self.use_valkey and self.client:
            try:
                self.client.srem("nse_completed_symbols", symbol)
                self.client.srem("nse_in_progress_symbols", symbol)
                self.client.hdel("nse_symbol_statuses", symbol)
            except Exception:
                pass
            return

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM persistent_stock_queue WHERE symbol = ?", (symbol,))
            conn.commit()

    def get_symbol_statuses(self) -> Dict[str, str]:
        """Returns a mapping of symbol -> queue status ('pending', 'in_progress', 'completed')."""
        if self.use_valkey and self.client:
            statuses: Dict[str, str] = {}
            try:
                raw_map = self.client.hgetall("nse_symbol_statuses") or {}
                for k, v in raw_map.items():
                    ks = (k.decode("utf-8") if isinstance(k, bytes) else str(k)).upper()
                    vs = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                    statuses[ks] = vs
                for c in (self.client.smembers("nse_completed_symbols") or set()):
                    cs = (c.decode("utf-8") if isinstance(c, bytes) else str(c)).upper()
                    statuses[cs] = "completed"
                for ip in (self.client.smembers("nse_in_progress_symbols") or set()):
                    ips = (ip.decode("utf-8") if isinstance(ip, bytes) else str(ip)).upper()
                    statuses[ips] = "in_progress"
            except Exception:
                pass
            return statuses

        statuses = {}
        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT symbol, status FROM persistent_stock_queue")
            for sym, stat in cursor.fetchall():
                statuses[sym.upper()] = stat
        return statuses

    def get_queue_status(self) -> Dict[str, Any]:
        """Returns statistics on pending and completed queue items."""
        if self.use_valkey and self.client:
            try:
                pending_count = int(self.client.llen("nse_stock_queue") or 0)
                in_prog_count = int(self.client.scard("nse_in_progress_symbols") or 0)
                completed_count = int(self.client.scard("nse_completed_symbols") or 0)
                return {
                    "engine": "Valkey / Redis",
                    "pending": pending_count,
                    "in_progress": in_prog_count,
                    "completed": completed_count,
                }
            except Exception:
                return {"engine": "Valkey / Redis", "pending": 0, "in_progress": 0, "completed": 0}

        self._init_sqlite_queue()
        with open_db(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status, COUNT(*) FROM persistent_stock_queue GROUP BY status")
            counts = dict(cursor.fetchall())
            return {
                "engine": "SQLite Persistent Queue",
                "pending": counts.get("pending", 0),
                "in_progress": counts.get("in_progress", 0),
                "completed": counts.get("completed", 0),
            }
