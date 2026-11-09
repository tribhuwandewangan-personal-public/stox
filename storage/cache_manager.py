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

class _ClosingConnection(sqlite3.Connection):
    """`with conn:` commits/rolls back like stock sqlite3 AND closes the connection afterwards.
    (Stock sqlite3 leaves it open, leaking handles and keeping the DB file locked on Windows.)"""

    def __exit__(self, exc_type, exc, tb):
        try:
            return super().__exit__(exc_type, exc, tb)
        finally:
            self.close()


def open_db(db_path: str) -> sqlite3.Connection:
    """Connection for the shared cache DB: 30s busy timeout, and `with open_db(p) as conn:` closes it on exit."""
    return sqlite3.connect(db_path, timeout=30, factory=_ClosingConnection)


class CacheManager:
    def __init__(self, db_path: str = CACHE_DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        # 30s busy timeout: many agent threads + the dashboard share this file.
        return open_db(self.db_path)

    def _init_db(self):
        """Initializes tables for incremental storage."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # WAL lets the dashboard read while analysis workers write (persistent DB setting)
            cursor.execute("PRAGMA journal_mode=WAL")

            # Drop legacy bhavcopy table if present (check first: DROP takes a write lock every start)
            cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='bhavcopy_cache'")
            if cursor.fetchone():
                cursor.execute("DROP TABLE bhavcopy_cache")

            # Reliable historical adjusted candles per stock
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS historical_candles (
                    symbol TEXT,
                    date TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    adj_close REAL,
                    volume INTEGER,
                    dividends REAL DEFAULT 0.0,
                    splits REAL DEFAULT 0.0,
                    PRIMARY KEY (symbol, date)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_hist_candles_sym_date 
                ON historical_candles(symbol, date)
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
                    sentiment_label TEXT,
                    pub_date TEXT
                )
            """)
            try:
                cursor.execute("ALTER TABLE news_cache ADD COLUMN pub_date TEXT")
            except sqlite3.OperationalError:
                pass


            # Global Macro Metrics Cache
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS macro_cache (
                    indicator_name TEXT,
                    fetch_date TEXT,
                    value REAL,
                    unit TEXT,
                    summary TEXT,
                    pct_change REAL,
                    PRIMARY KEY (indicator_name, fetch_date)
                )
            """)
            try:
                cursor.execute("ALTER TABLE macro_cache ADD COLUMN pct_change REAL")
            except sqlite3.OperationalError:
                pass

            # Fundamentals Cache (yfinance .info is slow and flaky)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS fundamentals_cache (
                    symbol TEXT PRIMARY KEY,
                    fetched_at TEXT,
                    data TEXT
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
            # Latest live/near-real-time quote per symbol (written by the quote poller)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    symbol TEXT PRIMARY KEY,
                    ltp REAL,
                    prev_close REAL,
                    day_high REAL,
                    day_low REAL,
                    volume INTEGER,
                    quote_ts TEXT,
                    fetched_at TEXT,
                    source TEXT
                )
            """)

            # Every verdict ever produced, later scored against actual prices (see tools/outcome_tracker.py)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS prediction_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    made_at TEXT,
                    as_of_date TEXT NOT NULL,
                    verdict TEXT,
                    confidence_pct INTEGER,
                    price_at_signal REAL,
                    entry_lo REAL,
                    entry_hi REAL,
                    target REAL,
                    stop REAL,
                    evidence_score REAL,
                    breakdown TEXT,
                    horizon_days INTEGER,
                    status TEXT DEFAULT 'OPEN',
                    resolved_at TEXT,
                    outcome_price REAL,
                    return_pct REAL,
                    UNIQUE(symbol, as_of_date)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_prediction_status ON prediction_log(status)
            """)

            # Tiny key/value store (scheduler bookkeeping)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS kv_state (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_runs_sym_agent_ts
                ON agent_runs_cache(symbol, agent_name, timestamp)
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
            """, (now_str, sentiment_label, macro_summary, self._safe_json_dumps(raw_indicators)))
            conn.commit()

    # --- Reliable Historical Candles SQLite API ---
    def get_cached_candles(self, symbol: str, limit_days: int = 500) -> List[Dict[str, Any]]:
        """Retrieves split-adjusted historical candles (oldest first) for a symbol; at most limit_days."""
        limit_days = max(1, int(limit_days))
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Newest limit_days rows (+1 context row so the first returned row has a true PREV_CLOSE)
            cursor.execute("""
                SELECT date, open, high, low, close, adj_close, volume, dividends, splits
                FROM historical_candles
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
            """, (symbol.upper(), limit_days + 1))
            rows = cursor.fetchall()
        if not rows:
            return []
        rows.reverse()
        if len(rows) > limit_days:
            prev_close = float(rows[0][4] or 0.0)
            rows = rows[1:]
        else:
            prev_close = rows[0][4]

        result = []
        for r in rows:
            close_val = float(r[4] or 0.0)
            result.append({
                "SYMBOL": symbol.upper(),
                "DATE": r[0],
                "OPEN_PRICE": float(r[1] or 0.0),
                "HIGH_PRICE": float(r[2] or 0.0),
                "LOW_PRICE": float(r[3] or 0.0),
                "CLOSE_PRICE": close_val,
                "ADJ_CLOSE": float(r[5] or close_val),
                "PREV_CLOSE": prev_close,
                "TTL_TRD_QNTY": int(r[6] or 0),
                "VOLUME": int(r[6] or 0),
                "DIVIDENDS": float(r[7] or 0.0),
                "SPLITS": float(r[8] or 0.0)
            })
            prev_close = close_val

        return result

    def save_historical_candles(self, records: List[Dict[str, Any]], replace_symbol: Optional[str] = None):
        """
        Batch inserts parsed corporate-action adjusted daily candles into SQLite database.
        With replace_symbol, that symbol's existing candles are deleted in the same transaction first, so the
        stored series never mixes price-adjustment bases.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if replace_symbol:
                cursor.execute("DELETE FROM historical_candles WHERE symbol = ?", (replace_symbol.upper(),))
            cursor.executemany("""
                INSERT OR REPLACE INTO historical_candles
                (symbol, date, open, high, low, close, adj_close, volume, dividends, splits)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    r["symbol"].upper(),
                    str(r["date"]),
                    float(r.get("open", 0.0)),
                    float(r.get("high", 0.0)),
                    float(r.get("low", 0.0)),
                    float(r.get("close", 0.0)),
                    float(r.get("adj_close", r.get("close", 0.0))),
                    int(r.get("volume", 0)),
                    float(r.get("dividends", 0.0)),
                    float(r.get("splits", 0.0))
                )
                for r in records
            ])
            conn.commit()

    def get_latest_candle_date(self, symbol: str) -> Optional[str]:
        """Date (YYYY-MM-DD) of the newest stored candle for a symbol, or None. Cheap (index lookup)."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM historical_candles WHERE symbol = ?", (symbol.upper(),)
            ).fetchone()
        return row[0] if row and row[0] else None

    # Backwards compatibility shims
    def get_cached_bhavcopy_history(self, symbol: str, limit_days: int = 500) -> List[Dict[str, Any]]:
        return self.get_cached_candles(symbol, limit_days=limit_days)

    def save_bhavcopy_records(self, records: List[Dict[str, Any]]):
        return self.save_historical_candles(records)

    # --- News Cache API ---
    def get_cached_news(self, symbol: str, max_age_hours: int = 24) -> List[Dict[str, Any]]:
        """Retrieves cached news for a stock symbol if fetched within max_age_hours."""
        cutoff_date = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, COALESCE(pub_date, fetch_date)
                FROM news_cache
                WHERE symbol = ? AND fetch_date >= ?
                ORDER BY fetch_date DESC
            """, (symbol.upper(), cutoff_date))
            rows = cursor.fetchall()
            return [
                {
                    "url": r[0], "title": r[1], "snippet": r[2], "source": r[3],
                    "fetch_date": r[4], "sentiment_score": r[5], "sentiment_label": r[6],
                    "pub_date": r[7]
                }
                for r in rows
            ]

    def get_all_cached_news(self, max_age_hours: int = 48) -> Dict[str, List[Dict[str, Any]]]:
        """Retrieves all cached news grouped by symbol within max_age_hours."""
        cutoff_date = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, COALESCE(pub_date, fetch_date)
                FROM news_cache
                WHERE fetch_date >= ?
                ORDER BY symbol ASC, fetch_date DESC
            """, (cutoff_date,))
            rows = cursor.fetchall()
            result: Dict[str, List[Dict[str, Any]]] = {}
            for r in rows:
                sym = r[0]
                item = {
                    "symbol": sym, "url": r[1], "title": r[2], "snippet": r[3], "source": r[4],
                    "fetch_date": r[5], "sentiment_score": r[6], "sentiment_label": r[7],
                    "pub_date": r[8]
                }
                if sym not in result:
                    result[sym] = []
                result[sym].append(item)
            return result

    def save_news(self, symbol: str, news_items: List[Dict[str, Any]]):
        """Saves scraped news items into cache."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            for item in news_items:
                url = item.get("url") or f"{symbol}_{hash(item.get('title', ''))}"
                pub_date = item.get("pub_date") or now_str
                cursor.execute("""
                    INSERT OR REPLACE INTO news_cache 
                    (symbol, url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, pub_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    symbol.upper(),
                    url,
                    item.get("title", ""),
                    item.get("snippet", ""),
                    item.get("source", "Web"),
                    now_str,
                    item.get("sentiment_score", 0.0),
                    item.get("sentiment_label", "Neutral"),
                    pub_date
                ))
            conn.commit()

    # --- Macro Cache API ---
    def get_cached_macro(self, max_age_hours: int = 12) -> List[Dict[str, Any]]:
        """Latest cached reading per indicator fetched within max_age_hours (no duplicates)."""
        cutoff_date = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.indicator_name, m.fetch_date, m.value, m.unit, m.summary, m.pct_change
                FROM macro_cache m
                JOIN (
                    SELECT indicator_name, MAX(fetch_date) AS fd
                    FROM macro_cache
                    WHERE fetch_date >= ?
                    GROUP BY indicator_name
                ) latest ON latest.indicator_name = m.indicator_name AND latest.fd = m.fetch_date
            """, (cutoff_date,))
            rows = cursor.fetchall()
        return [
            {"indicator": r[0], "fetch_date": r[1], "value": r[2], "unit": r[3], "summary": r[4], "pct_change": r[5]}
            for r in rows
        ]

    def save_macro(self, macro_data: List[Dict[str, Any]]):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now_str = datetime.now().isoformat()
            cursor.executemany("""
                INSERT OR REPLACE INTO macro_cache (indicator_name, fetch_date, value, unit, summary, pct_change)
                VALUES (?, ?, ?, ?, ?, ?)
            """, [
                (m["indicator"], now_str, m.get("value", 0.0), m.get("unit", ""), m.get("summary", ""), m.get("pct_change"))
                for m in macro_data
            ])
            conn.commit()

    # --- Fundamentals Cache API ---
    def get_cached_fundamentals(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Returns {'fetched_at': datetime, 'data': dict} or None. Caller decides freshness."""
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT fetched_at, data FROM fundamentals_cache WHERE symbol = ?", (symbol.upper(),)
            ).fetchone()
        if not row:
            return None
        try:
            return {"fetched_at": datetime.fromisoformat(row[0]), "data": json.loads(row[1])}
        except Exception:
            return None

    def save_fundamentals(self, symbol: str, data: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_cache (symbol, fetched_at, data) VALUES (?, ?, ?)",
                (symbol.upper(), datetime.now().isoformat(), self._safe_json_dumps(data))
            )
            conn.commit()

    # --- Agent Runs Cache ---
    @staticmethod
    def _safe_json_dumps(data) -> str:
        """JSON-serialize data: NaN/Infinity ? null, bool ? int, other non-serializable ? str."""
        import math

        def _sanitize(obj):
            if isinstance(obj, float):
                return None if (math.isnan(obj) or math.isinf(obj)) else obj
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            return obj

        def _default(obj):
            if isinstance(obj, bool):
                return int(obj)
            try:
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            except Exception:
                pass
            return str(obj)

        return json.dumps(_sanitize(data), default=_default)

    def save_agent_output(self, symbol: str, agent_name: str, output_data: Dict[str, Any]):
        run_id = f"{symbol.upper()}_{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_runs_cache (run_id, symbol, timestamp, agent_name, output_data)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, symbol.upper(), datetime.now().isoformat(), agent_name, self._safe_json_dumps(output_data)))
            conn.commit()

    def get_latest_agent_output(self, symbol: str, agent_name: str, max_age_hours: Optional[int] = 12) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if max_age_hours is not None:
                cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                cursor.execute("""
                    SELECT output_data FROM agent_runs_cache
                    WHERE symbol = ? AND agent_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (symbol.upper(), agent_name, cutoff))
            else:
                cursor.execute("""
                    SELECT output_data FROM agent_runs_cache
                    WHERE symbol = ? AND agent_name = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (symbol.upper(), agent_name))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    def get_latest_agent_outputs_bulk(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Latest output of every agent for every symbol in ONE query.
        Returns {symbol: {agent_name: {"timestamp": iso, "output": dict}}}.
        """
        with self._get_connection() as conn:
            rows = conn.execute("""
                SELECT a.symbol, a.agent_name, a.timestamp, a.output_data
                FROM agent_runs_cache a
                JOIN (
                    SELECT symbol, agent_name, MAX(timestamp) AS ts
                    FROM agent_runs_cache
                    GROUP BY symbol, agent_name
                ) m ON m.symbol = a.symbol AND m.agent_name = a.agent_name AND m.ts = a.timestamp
            """).fetchall()
        result: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for sym, agent, ts, blob in rows:
            try:
                result.setdefault(sym, {})[agent] = {"timestamp": ts, "output": json.loads(blob)}
            except Exception:
                continue
        return result

    def get_agent_runs_marker(self) -> str:
        """Newest agent-output timestamp; changes whenever any analysis is written (response-cache key)."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT MAX(timestamp) FROM agent_runs_cache").fetchone()
        return row[0] or ""

    # --- Live quotes API ---
    def save_quotes(self, quotes: List[Dict[str, Any]]):
        """Upsert latest quotes. Each dict: symbol, ltp, prev_close, day_high, day_low, volume, quote_ts, source."""
        if not quotes:
            return
        now_str = datetime.now().isoformat()
        with self._get_connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO quotes
                (symbol, ltp, prev_close, day_high, day_low, volume, quote_ts, fetched_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (q["symbol"].upper(), q.get("ltp"), q.get("prev_close"), q.get("day_high"), q.get("day_low"),
                 q.get("volume"), q.get("quote_ts"), now_str, q.get("source"))
                for q in quotes
            ])
            conn.commit()

    def get_all_quotes(self) -> Dict[str, Dict[str, Any]]:
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT symbol, ltp, prev_close, day_high, day_low, volume, quote_ts, fetched_at, source FROM quotes"
            ).fetchall()
        keys = ("symbol", "ltp", "prev_close", "day_high", "day_low", "volume", "quote_ts", "fetched_at", "source")
        return {r[0]: dict(zip(keys, r)) for r in rows}

    # --- Prediction log API ---
    def log_prediction(self, rec: Dict[str, Any]):
        """
        Record a verdict. One row per (symbol, as_of_date): re-analysing the same day refreshes the row while it
        is still OPEN, but never rewrites an already-resolved prediction.
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO prediction_log
                (symbol, made_at, as_of_date, verdict, confidence_pct, price_at_signal, entry_lo, entry_hi,
                 target, stop, evidence_score, breakdown, horizon_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                    made_at=excluded.made_at, verdict=excluded.verdict, confidence_pct=excluded.confidence_pct,
                    price_at_signal=excluded.price_at_signal, entry_lo=excluded.entry_lo, entry_hi=excluded.entry_hi,
                    target=excluded.target, stop=excluded.stop, evidence_score=excluded.evidence_score,
                    breakdown=excluded.breakdown, horizon_days=excluded.horizon_days
                WHERE prediction_log.status = 'OPEN'
            """, (
                rec["symbol"].upper(), rec.get("made_at") or datetime.now().isoformat(), rec["as_of_date"],
                rec.get("verdict"), rec.get("confidence_pct"), rec.get("price_at_signal"), rec.get("entry_lo"),
                rec.get("entry_hi"), rec.get("target"), rec.get("stop"), rec.get("evidence_score"),
                self._safe_json_dumps(rec.get("breakdown") or []), rec.get("horizon_days"),
            ))
            conn.commit()

    def get_predictions(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = ("SELECT id, symbol, made_at, as_of_date, verdict, confidence_pct, price_at_signal, entry_lo, entry_hi, "
               "target, stop, evidence_score, horizon_days, status, resolved_at, outcome_price, return_pct "
               "FROM prediction_log")
        params: tuple = ()
        if status == "RESOLVED":
            sql += " WHERE status != 'OPEN'"
        elif status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY as_of_date, id"
        keys = ("id", "symbol", "made_at", "as_of_date", "verdict", "confidence_pct", "price_at_signal", "entry_lo",
                "entry_hi", "target", "stop", "evidence_score", "horizon_days", "status", "resolved_at",
                "outcome_price", "return_pct")
        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(zip(keys, r)) for r in rows]

    def resolve_prediction(self, prediction_id: int, status: str, outcome_price: Optional[float],
                           return_pct: Optional[float], resolved_at: Optional[str] = None):
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE prediction_log SET status = ?, resolved_at = ?, outcome_price = ?, return_pct = ? "
                "WHERE id = ? AND status = 'OPEN'",
                (status, resolved_at or datetime.now().isoformat(), outcome_price, return_pct, prediction_id)
            )
            conn.commit()

    # --- Scheduler bookkeeping ---
    def get_state(self, key: str) -> Optional[str]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat())
            )
            conn.commit()

    # --- Housekeeping ---
    def prune_agent_runs(self, keep_days: int = 30) -> int:
        """Delete agent outputs older than keep_days, always keeping the newest one per (symbol, agent)."""
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._get_connection() as conn:
            cur = conn.execute("""
                DELETE FROM agent_runs_cache
                WHERE timestamp < ?
                  AND run_id NOT IN (
                    SELECT a.run_id FROM agent_runs_cache a
                    JOIN (SELECT symbol, agent_name, MAX(timestamp) AS ts FROM agent_runs_cache
                          GROUP BY symbol, agent_name) m
                      ON m.symbol = a.symbol AND m.agent_name = a.agent_name AND m.ts = a.timestamp
                  )
            """, (cutoff,))
            conn.commit()
            return cur.rowcount
