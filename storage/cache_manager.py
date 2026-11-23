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

from config import CACHE_DB_PATH, MODEL_VERSION

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


VALKEY_HOST = os.getenv("VALKEY_HOST", "localhost")
VALKEY_PORT = int(os.getenv("VALKEY_PORT", "6379"))


class CacheManager:
    def __init__(
        self,
        db_path: str = CACHE_DB_PATH,
        prefer_valkey: Optional[bool] = None,
        valkey_host: str = VALKEY_HOST,
        valkey_port: int = VALKEY_PORT,
    ):
        self.db_path = db_path
        self.valkey_host = valkey_host
        self.valkey_port = valkey_port
        self.valkey = None
        self.use_valkey = False

        should_try_valkey = prefer_valkey if prefer_valkey is not None else (
            os.path.abspath(db_path) == os.path.abspath(CACHE_DB_PATH)
        )
        if should_try_valkey:
            self._connect_valkey()

        if self.use_valkey:
            self._bootstrap_valkey_if_needed()
        else:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            self._init_db()

    def _connect_valkey(self):
        """Connects to Valkey / Redis so CacheManager serves and writes exclusively in Valkey."""
        try:
            import redis
            client = redis.Redis(host=self.valkey_host, port=self.valkey_port, socket_timeout=2.0)
            client.ping()
            self.valkey = client
            self.use_valkey = True
        except Exception:
            self.valkey = None
            self.use_valkey = False

    @staticmethod
    def _dec(val: Any) -> str:
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="replace")
        return str(val) if val is not None else ""

    def _bootstrap_valkey_if_needed(self):
        """
        One-time migration of existing SQLite cache.db data into Valkey if Valkey is freshly started.
        Once `stox:cache:bootstrapped_v1` is set in Valkey, SQLite cache.db is never queried again.
        """
        if not self.use_valkey or not self.valkey:
            return
        try:
            if self.valkey.get("stox:cache:bootstrapped_v1"):
                return
            if not os.path.exists(self.db_path):
                self.valkey.set("stox:cache:bootstrapped_v1", "1")
                return
            with open_db(self.db_path) as conn:
                cur = conn.cursor()
                pipe = self.valkey.pipeline(transaction=False)

                # 1. Shared market bulletin
                try:
                    row = cur.execute(
                        "SELECT timestamp, sentiment_label, macro_summary, raw_indicators FROM shared_market_bulletin ORDER BY id DESC LIMIT 1"
                    ).fetchone()
                    if row:
                        pipe.set("stox:bulletin:latest", self._safe_json_dumps({
                            "timestamp": row[0],
                            "sentiment_label": row[1],
                            "summary": row[2],
                            "raw_indicators": json.loads(row[3]) if row[3] else {},
                        }))
                except Exception:
                    pass

                # 2. Macro cache
                try:
                    m_rows = cur.execute("""
                        SELECT m.indicator_name, m.fetch_date, m.value, m.unit, m.summary, m.pct_change
                        FROM macro_cache m
                        JOIN (SELECT indicator_name, MAX(fetch_date) AS fd FROM macro_cache GROUP BY indicator_name) l
                          ON l.indicator_name = m.indicator_name AND l.fd = m.fetch_date
                    """).fetchall()
                    if m_rows:
                        m_map = {
                            r[0]: self._safe_json_dumps({
                                "indicator": r[0], "fetch_date": r[1], "value": r[2],
                                "unit": r[3], "summary": r[4], "pct_change": r[5],
                            })
                            for r in m_rows
                        }
                        pipe.hset("stox:macro", mapping=m_map)
                except Exception:
                    pass

                # 3. Fundamentals cache
                try:
                    f_rows = cur.execute("SELECT symbol, fetched_at, data FROM fundamentals_cache").fetchall()
                    if f_rows:
                        f_map = {
                            str(sym).upper(): self._safe_json_dumps({"fetched_at": fat, "data": json.loads(d)})
                            for sym, fat, d in f_rows if sym and d
                        }
                        if f_map:
                            pipe.hset("stox:fundamentals", mapping=f_map)
                except Exception:
                    pass

                # 4. Agent runs cache (latest per symbol + agent_name)
                try:
                    a_rows = cur.execute("""
                        SELECT a.symbol, a.agent_name, a.timestamp, a.output_data
                        FROM agent_runs_cache a
                        JOIN (
                            SELECT symbol, agent_name, MAX(timestamp) AS ts
                            FROM agent_runs_cache
                            GROUP BY symbol, agent_name
                        ) m ON m.symbol = a.symbol AND m.agent_name = a.agent_name AND m.ts = a.timestamp
                    """).fetchall()
                    a_map = {}
                    max_ts = ""
                    for sym, ag, ts, blob in a_rows:
                        if not sym or not ag or not blob:
                            continue
                        ts_str = str(ts or "")
                        if ts_str > max_ts:
                            max_ts = ts_str
                        a_map[f"{str(sym).upper()}::{ag}"] = self._safe_json_dumps({
                            "symbol": str(sym).upper(),
                            "agent_name": ag,
                            "timestamp": ts_str,
                            "output": json.loads(blob),
                        })
                    if a_map:
                        for items_chunk in [dict(list(a_map.items())[i:i + 500]) for i in range(0, len(a_map), 500)]:
                            pipe.hset("stox:agent_runs", mapping=items_chunk)
                    if max_ts:
                        pipe.set("stox:agent_runs:marker", max_ts)
                except Exception:
                    pass

                # 5. Quotes
                try:
                    q_rows = cur.execute(
                        "SELECT symbol, ltp, prev_close, day_high, day_low, volume, vwap, upper_circuit, lower_circuit, quote_ts, fetched_at, source FROM quotes"
                    ).fetchall()
                    q_keys = ("symbol", "ltp", "prev_close", "day_high", "day_low", "volume", "vwap", "upper_circuit", "lower_circuit", "quote_ts", "fetched_at", "source")
                    if q_rows:
                        q_map = {str(r[0]).upper(): self._safe_json_dumps(dict(zip(q_keys, r))) for r in q_rows if r[0]}
                        if q_map:
                            pipe.hset("stox:quotes", mapping=q_map)
                except Exception:
                    pass

                # 6. Events cache
                try:
                    e_rows = cur.execute("SELECT symbol, updated_at, events_data FROM events_cache").fetchall()
                    if e_rows:
                        e_map = {
                            str(sym).upper(): self._safe_json_dumps({"updated_at": uat, "events_data": json.loads(ed)})
                            for sym, uat, ed in e_rows if sym and ed
                        }
                        if e_map:
                            pipe.hset("stox:events", mapping=e_map)
                except Exception:
                    pass

                # 7. News cache
                try:
                    n_rows = cur.execute(
                        "SELECT symbol, url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, COALESCE(pub_date, fetch_date) FROM news_cache ORDER BY symbol ASC, fetch_date DESC"
                    ).fetchall()
                    n_grouped: Dict[str, List[Dict[str, Any]]] = {}
                    for r in n_rows:
                        sym_u = str(r[0]).upper()
                        bucket = n_grouped.setdefault(sym_u, [])
                        if len(bucket) < 30:
                            bucket.append({
                                "symbol": sym_u, "url": r[1], "title": r[2], "snippet": r[3], "source": r[4],
                                "fetch_date": r[5], "sentiment_score": r[6], "sentiment_label": r[7], "pub_date": r[8],
                            })
                    if n_grouped:
                        pipe.hset("stox:news", mapping={k: self._safe_json_dumps(v) for k, v in n_grouped.items()})
                except Exception:
                    pass

                # 8. KV State & Prediction Log
                try:
                    kv_rows = cur.execute("SELECT key, value FROM kv_state").fetchall()
                    if kv_rows:
                        pipe.hset("stox:kv_state", mapping={str(k): str(v) for k, v in kv_rows if k})
                except Exception:
                    pass

                try:
                    p_rows = cur.execute(
                        "SELECT id, symbol, made_at, as_of_date, verdict, confidence_pct, price_at_signal, entry_lo, entry_hi, "
                        "target, stop, evidence_score, horizon_days, status, resolved_at, outcome_price, return_pct, "
                        "COALESCE(model_version, 'legacy'), COALESCE(split_adjusted_factor, 1.0) FROM prediction_log"
                    ).fetchall()
                    p_keys = (
                        "id", "symbol", "made_at", "as_of_date", "verdict", "confidence_pct", "price_at_signal", "entry_lo",
                        "entry_hi", "target", "stop", "evidence_score", "horizon_days", "status", "resolved_at",
                        "outcome_price", "return_pct", "model_version", "split_adjusted_factor",
                    )
                    if p_rows:
                        p_map = {
                            f"{str(r[1]).upper()}::{r[3]}": self._safe_json_dumps(dict(zip(p_keys, r)))
                            for r in p_rows if r[1] and r[3]
                        }
                        if p_map:
                            pipe.hset("stox:predictions", mapping=p_map)
                except Exception:
                    pass

                # 9. Precompute historical candle summaries into Valkey (stox:candles:summary)
                try:
                    c_rows = cur.execute(
                        "SELECT symbol, date, high, low, close FROM historical_candles ORDER BY symbol, date DESC"
                    ).fetchall()
                    c_summaries = self._aggregate_bulk_candle_rows(c_rows, 760, 25)
                    if c_summaries:
                        c_map = {sym: self._safe_json_dumps(s) for sym, s in c_summaries.items()}
                        for chunk in [dict(list(c_map.items())[i:i + 500]) for i in range(0, len(c_map), 500)]:
                            pipe.hset("stox:candles:summary", mapping=chunk)
                except Exception:
                    pass

                pipe.set("stox:cache:bootstrapped_v1", "1")
                pipe.execute()
        except Exception as e:
            print(f"⚠️ [Valkey Cache Bootstrap Notice]: {e}")

    def _get_connection(self):
        # 30s busy timeout: many agent threads + the dashboard share this file.
        return open_db(self.db_path)

    def _init_db(self):
        """Initializes tables for incremental storage."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # WAL lets the dashboard read while analysis workers write (persistent DB setting)
            cursor.execute("PRAGMA journal_mode=WAL")

            # Drop legacy/unused tables if present (check first: DROP takes a write lock every start)
            for obsolete_tbl in ("bhavcopy_cache", "tech_cache"):
                cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (obsolete_tbl,))
                if cursor.fetchone():
                    cursor.execute(f"DROP TABLE {obsolete_tbl}")

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
                    delivery_qty INTEGER DEFAULT NULL,
                    delivery_pct REAL DEFAULT NULL,
                    adj_factor REAL DEFAULT 1.0,
                    PRIMARY KEY (symbol, date)
                )
            """)
            for col_ddl in (
                "ALTER TABLE historical_candles ADD COLUMN delivery_qty INTEGER DEFAULT NULL",
                "ALTER TABLE historical_candles ADD COLUMN delivery_pct REAL DEFAULT NULL",
                "ALTER TABLE historical_candles ADD COLUMN adj_factor REAL DEFAULT 1.0",
            ):
                try:
                    cursor.execute(col_ddl)
                except sqlite3.OperationalError:
                    pass
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
                    vwap REAL DEFAULT NULL,
                    upper_circuit REAL DEFAULT NULL,
                    lower_circuit REAL DEFAULT NULL,
                    quote_ts TEXT,
                    fetched_at TEXT,
                    source TEXT
                )
            """)
            for col_ddl in (
                "ALTER TABLE quotes ADD COLUMN vwap REAL DEFAULT NULL",
                "ALTER TABLE quotes ADD COLUMN upper_circuit REAL DEFAULT NULL",
                "ALTER TABLE quotes ADD COLUMN lower_circuit REAL DEFAULT NULL",
            ):
                try:
                    cursor.execute(col_ddl)
                except sqlite3.OperationalError:
                    pass

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
                    model_version TEXT DEFAULT 'legacy',
                    split_adjusted_factor REAL DEFAULT 1.0,
                    UNIQUE(symbol, as_of_date)
                )
            """)
            for col_ddl in (
                "ALTER TABLE prediction_log ADD COLUMN model_version TEXT DEFAULT 'legacy'",
                "ALTER TABLE prediction_log ADD COLUMN split_adjusted_factor REAL DEFAULT 1.0",
            ):
                try:
                    cursor.execute(col_ddl)
                except sqlite3.OperationalError:
                    pass
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
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.get("stox:bulletin:latest")
                return json.loads(self._dec(raw)) if raw else None
            except Exception:
                return None
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
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                self.valkey.set("stox:bulletin:latest", self._safe_json_dumps({
                    "timestamp": now_str,
                    "sentiment_label": sentiment_label,
                    "summary": macro_summary,
                    "raw_indicators": raw_indicators or {},
                }))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO shared_market_bulletin (timestamp, sentiment_label, macro_summary, raw_indicators)
                VALUES (?, ?, ?, ?)
            """, (now_str, sentiment_label, macro_summary, self._safe_json_dumps(raw_indicators)))
            conn.commit()

    # --- Reliable Historical Candles Valkey / SQLite API ---
    def _load_symbol_candles_from_sqlite_once(self, sym_u: str) -> List[Dict[str, Any]]:
        """Lazy one-time hydration of a symbol's full candle history into Valkey if not yet cached in `stox:candles`."""
        if not os.path.exists(self.db_path):
            return []
        try:
            with open_db(self.db_path) as conn:
                rows = conn.execute("""
                    SELECT date, open, high, low, close, adj_close, volume, dividends, splits, delivery_qty, delivery_pct
                    FROM historical_candles
                    WHERE symbol = ?
                    ORDER BY date ASC
                """, (sym_u,)).fetchall()
            if not rows:
                return []
            prev_close = float(rows[0][4] or 0.0)
            result = []
            for r in rows:
                close_val = float(r[4] or 0.0)
                result.append({
                    "SYMBOL": sym_u,
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
                    "SPLITS": float(r[8] or 0.0),
                    "DELIVERY_QTY": int(r[9]) if r[9] is not None else None,
                    "DELIVERY_PCT": float(r[10]) if r[10] is not None else None,
                })
                prev_close = close_val
            if self.valkey:
                self.valkey.hset("stox:candles", sym_u, self._safe_json_dumps(result))
            return result
        except Exception:
            return []

    def get_cached_candles(self, symbol: str, limit_days: int = 500) -> List[Dict[str, Any]]:
        """Retrieves split-adjusted historical candles (oldest first) for a symbol; at most limit_days."""
        limit_days = max(1, int(limit_days))
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:candles", sym_u)
                if raw:
                    candles = json.loads(self._dec(raw))
                else:
                    candles = self._load_symbol_candles_from_sqlite_once(sym_u)
                return candles[-limit_days:] if candles else []
            except Exception:
                return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Newest limit_days rows (+1 context row so the first returned row has a true PREV_CLOSE)
            cursor.execute("""
                SELECT date, open, high, low, close, adj_close, volume, dividends, splits, delivery_qty, delivery_pct
                FROM historical_candles
                WHERE symbol = ?
                ORDER BY date DESC
                LIMIT ?
            """, (sym_u, limit_days + 1))
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
                "SYMBOL": sym_u,
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
                "SPLITS": float(r[8] or 0.0),
                "DELIVERY_QTY": int(r[9]) if r[9] is not None else None,
                "DELIVERY_PCT": float(r[10]) if r[10] is not None else None,
            })
            prev_close = close_val

        return result

    def save_historical_candles(self, records: List[Dict[str, Any]], replace_symbol: Optional[str] = None):
        """
        Batch inserts parsed corporate-action adjusted daily candles into Valkey (or SQLite fallback).
        With replace_symbol, that symbol's existing candles are replaced so the series never mixes bases.
        """
        if self.use_valkey and self.valkey:
            try:
                grouped: Dict[str, List[Dict[str, Any]]] = {}
                for r in records or []:
                    sym_u = str(r.get("symbol", "")).upper().strip()
                    if sym_u:
                        grouped.setdefault(sym_u, []).append(r)
                if replace_symbol and replace_symbol.upper().strip() not in grouped:
                    grouped[replace_symbol.upper().strip()] = []

                for sym_u, recs in grouped.items():
                    if replace_symbol and sym_u == replace_symbol.upper().strip():
                        by_date: Dict[str, Dict[str, Any]] = {}
                    else:
                        existing = self.get_cached_candles(sym_u, limit_days=5000)
                        by_date = {str(c["DATE"])[:10]: c for c in existing}
                    for r in recs:
                        dt = str(r["date"])[:10]
                        prev_entry = by_date.get(dt, {})
                        c_val = float(r.get("close", 0.0))
                        by_date[dt] = {
                            "SYMBOL": sym_u,
                            "DATE": dt,
                            "OPEN_PRICE": float(r.get("open", 0.0)),
                            "HIGH_PRICE": float(r.get("high", 0.0)),
                            "LOW_PRICE": float(r.get("low", 0.0)),
                            "CLOSE_PRICE": c_val,
                            "ADJ_CLOSE": float(r.get("adj_close", c_val)),
                            "PREV_CLOSE": c_val,
                            "TTL_TRD_QNTY": int(r.get("volume", 0)),
                            "VOLUME": int(r.get("volume", 0)),
                            "DIVIDENDS": float(r.get("dividends", 0.0)),
                            "SPLITS": float(r.get("splits", 0.0)),
                            "DELIVERY_QTY": int(r["delivery_qty"]) if r.get("delivery_qty") is not None else prev_entry.get("DELIVERY_QTY"),
                            "DELIVERY_PCT": float(r["delivery_pct"]) if r.get("delivery_pct") is not None else prev_entry.get("DELIVERY_PCT"),
                        }
                    sorted_candles = [by_date[d] for d in sorted(by_date.keys())]
                    prev_c = sorted_candles[0]["CLOSE_PRICE"] if sorted_candles else 0.0
                    for c in sorted_candles:
                        c["PREV_CLOSE"] = prev_c
                        prev_c = c["CLOSE_PRICE"]
                    self.valkey.hset("stox:candles", sym_u, self._safe_json_dumps(sorted_candles))
                    desc_rows = [
                        (sym_u, c["DATE"], c["HIGH_PRICE"], c["LOW_PRICE"], c["CLOSE_PRICE"])
                        for c in reversed(sorted_candles[-760:])
                    ]
                    agg = self._aggregate_bulk_candle_rows(desc_rows, 760, 25).get(sym_u)
                    if agg:
                        self.valkey.hset("stox:candles:summary", sym_u, self._safe_json_dumps(agg))
            except Exception:
                pass
            return

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if replace_symbol:
                cursor.execute("DELETE FROM historical_candles WHERE symbol = ?", (replace_symbol.upper(),))
            cursor.executemany("""
                INSERT INTO historical_candles
                (symbol, date, open, high, low, close, adj_close, volume, dividends, splits, delivery_qty, delivery_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    adj_close = excluded.adj_close,
                    volume = excluded.volume,
                    dividends = excluded.dividends,
                    splits = excluded.splits,
                    delivery_qty = COALESCE(excluded.delivery_qty, historical_candles.delivery_qty),
                    delivery_pct = COALESCE(excluded.delivery_pct, historical_candles.delivery_pct)
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
                    float(r.get("splits", 0.0)),
                    int(r["delivery_qty"]) if r.get("delivery_qty") is not None else None,
                    float(r["delivery_pct"]) if r.get("delivery_pct") is not None else None,
                )
                for r in records
            ])
            conn.commit()

    def update_delivery_data(self, records: List[Dict[str, Any]]) -> int:
        """
        Updates delivery_qty and delivery_pct on existing (symbol, date) rows.
        Returns the total count of matched rows updated.
        """
        if not records:
            return 0
        if self.use_valkey and self.valkey:
            updated_count = 0
            by_sym: Dict[str, List[Dict[str, Any]]] = {}
            for r in records:
                sym = str(r.get("symbol", "")).upper().strip()
                dt = str(r.get("date", "")).strip()
                if sym and dt:
                    by_sym.setdefault(sym, []).append(r)
            for sym, recs in by_sym.items():
                candles = self.get_cached_candles(sym, limit_days=5000)
                if not candles:
                    continue
                c_map = {str(c["DATE"])[:10]: c for c in candles}
                changed = False
                for r in recs:
                    dt = str(r.get("date", ""))[:10]
                    if dt in c_map:
                        if r.get("delivery_qty") is not None:
                            c_map[dt]["DELIVERY_QTY"] = int(r["delivery_qty"])
                        if r.get("delivery_pct") is not None:
                            c_map[dt]["DELIVERY_PCT"] = float(r["delivery_pct"])
                        updated_count += 1
                        changed = True
                if changed:
                    self.valkey.hset("stox:candles", sym, self._safe_json_dumps(candles))
            return updated_count

        rows_to_update = []
        for r in records:
            sym = str(r.get("symbol", "")).upper().strip()
            dt = str(r.get("date", "")).strip()
            if not sym or not dt:
                continue
            dqty = int(r["delivery_qty"]) if r.get("delivery_qty") is not None else None
            dpct = float(r["delivery_pct"]) if r.get("delivery_pct") is not None else None
            rows_to_update.append((dqty, dpct, sym, dt))
        if not rows_to_update:
            return 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany("""
                UPDATE historical_candles
                SET delivery_qty = COALESCE(?, delivery_qty),
                    delivery_pct = COALESCE(?, delivery_pct)
                WHERE symbol = ? AND date = ?
            """, rows_to_update)
            updated = max(0, cursor.rowcount)
            conn.commit()
        return updated

    def get_latest_candle_date(self, symbol: str) -> Optional[str]:
        """Date (YYYY-MM-DD) of the newest stored candle for a symbol, or None. Cheap lookup."""
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw_sum = self.valkey.hget("stox:candles:summary", sym_u)
                if raw_sum:
                    return json.loads(self._dec(raw_sum)).get("latest_date")
                candles = self.get_cached_candles(sym_u, limit_days=1)
                return str(candles[-1]["DATE"])[:10] if candles else None
            except Exception:
                return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(date) FROM historical_candles WHERE symbol = ?", (sym_u,)
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
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:news", sym_u)
                if not raw:
                    return []
                items = json.loads(self._dec(raw))
                return [i for i in items if str(i.get("fetch_date", "")) >= cutoff_date]
            except Exception:
                return []
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, COALESCE(pub_date, fetch_date)
                FROM news_cache
                WHERE symbol = ? AND fetch_date >= ?
                ORDER BY fetch_date DESC
            """, (sym_u, cutoff_date))
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
        if self.use_valkey and self.valkey:
            result: Dict[str, List[Dict[str, Any]]] = {}
            try:
                raw_all = self.valkey.hgetall("stox:news") or {}
                for k, v in raw_all.items():
                    sym = self._dec(k).upper()
                    items = [i for i in json.loads(self._dec(v)) if str(i.get("fetch_date", "")) >= cutoff_date]
                    if items:
                        result[sym] = items
            except Exception:
                pass
            return result
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
        sym_u = symbol.upper().strip()
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:news", sym_u)
                existing = json.loads(self._dec(raw)) if raw else []
                by_url = {i.get("url"): i for i in existing if i.get("url")}
                for item in news_items or []:
                    url = item.get("url") or f"{sym_u}_{hash(item.get('title', ''))}"
                    by_url[url] = {
                        "symbol": sym_u,
                        "url": url,
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "source": item.get("source", "Web"),
                        "fetch_date": now_str,
                        "sentiment_score": item.get("sentiment_score", 0.0),
                        "sentiment_label": item.get("sentiment_label", "Neutral"),
                        "pub_date": item.get("pub_date") or now_str,
                    }
                merged = sorted(by_url.values(), key=lambda x: str(x.get("fetch_date", "")), reverse=True)[:40]
                self.valkey.hset("stox:news", sym_u, self._safe_json_dumps(merged))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for item in news_items:
                url = item.get("url") or f"{symbol}_{hash(item.get('title', ''))}"
                pub_date = item.get("pub_date") or now_str
                cursor.execute("""
                    INSERT OR REPLACE INTO news_cache 
                    (symbol, url, title, snippet, source, fetch_date, sentiment_score, sentiment_label, pub_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sym_u,
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
        if self.use_valkey and self.valkey:
            out: List[Dict[str, Any]] = []
            try:
                raw_all = self.valkey.hgetall("stox:macro") or {}
                for _, v in raw_all.items():
                    rec = json.loads(self._dec(v))
                    if str(rec.get("fetch_date", "")) >= cutoff_date:
                        out.append(rec)
            except Exception:
                pass
            return out
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
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                m_map = {
                    m["indicator"]: self._safe_json_dumps({
                        "indicator": m["indicator"],
                        "fetch_date": now_str,
                        "value": m.get("value", 0.0),
                        "unit": m.get("unit", ""),
                        "summary": m.get("summary", ""),
                        "pct_change": m.get("pct_change"),
                    })
                    for m in (macro_data or []) if m.get("indicator")
                }
                if m_map:
                    self.valkey.hset("stox:macro", mapping=m_map)
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            cursor = conn.cursor()
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
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:fundamentals", sym_u)
                if not raw:
                    return None
                obj = json.loads(self._dec(raw))
                return {"fetched_at": datetime.fromisoformat(obj["fetched_at"]), "data": obj["data"]}
            except Exception:
                return None
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT fetched_at, data FROM fundamentals_cache WHERE symbol = ?", (sym_u,)
            ).fetchone()
        if not row:
            return None
        try:
            return {"fetched_at": datetime.fromisoformat(row[0]), "data": json.loads(row[1])}
        except Exception:
            return None

    def save_fundamentals(self, symbol: str, data: Dict[str, Any]):
        sym_u = symbol.upper().strip()
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                self.valkey.hset("stox:fundamentals", sym_u, self._safe_json_dumps({"fetched_at": now_str, "data": data}))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO fundamentals_cache (symbol, fetched_at, data) VALUES (?, ?, ?)",
                (sym_u, now_str, self._safe_json_dumps(data))
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
        sym_u = symbol.upper().strip()
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                pipe = self.valkey.pipeline(transaction=False)
                pipe.hset("stox:agent_runs", f"{sym_u}::{agent_name}", self._safe_json_dumps({
                    "symbol": sym_u,
                    "agent_name": agent_name,
                    "timestamp": now_str,
                    "output": output_data,
                }))
                pipe.set("stox:agent_runs:marker", now_str)
                pipe.execute()
            except Exception:
                pass
            return
        run_id = f"{sym_u}_{agent_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO agent_runs_cache (run_id, symbol, timestamp, agent_name, output_data)
                VALUES (?, ?, ?, ?, ?)
            """, (run_id, sym_u, now_str, agent_name, self._safe_json_dumps(output_data)))
            conn.commit()

    def get_latest_agent_output(self, symbol: str, agent_name: str, max_age_hours: Optional[int] = 12) -> Optional[Dict[str, Any]]:
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:agent_runs", f"{sym_u}::{agent_name}")
                if not raw:
                    return None
                rec = json.loads(self._dec(raw))
                if max_age_hours is not None:
                    cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                    if str(rec.get("timestamp", "")) < cutoff:
                        return None
                return rec.get("output")
            except Exception:
                return None
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if max_age_hours is not None:
                cutoff = (datetime.now() - timedelta(hours=max_age_hours)).isoformat()
                cursor.execute("""
                    SELECT output_data FROM agent_runs_cache
                    WHERE symbol = ? AND agent_name = ? AND timestamp >= ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (sym_u, agent_name, cutoff))
            else:
                cursor.execute("""
                    SELECT output_data FROM agent_runs_cache
                    WHERE symbol = ? AND agent_name = ?
                    ORDER BY timestamp DESC LIMIT 1
                """, (sym_u, agent_name))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    def get_latest_agent_outputs_bulk(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        """
        Latest output of every agent for every symbol in ONE query.
        Returns {symbol: {agent_name: {"timestamp": iso, "output": dict}}}.
        """
        if self.use_valkey and self.valkey:
            result: Dict[str, Dict[str, Dict[str, Any]]] = {}
            try:
                raw_all = self.valkey.hgetall("stox:agent_runs") or {}
                for k, v in raw_all.items():
                    key_str = self._dec(k)
                    if "::" not in key_str:
                        continue
                    sym, agent = key_str.split("::", 1)
                    rec = json.loads(self._dec(v))
                    result.setdefault(sym, {})[agent] = {
                        "timestamp": rec.get("timestamp", ""),
                        "output": rec.get("output", {}),
                    }
            except Exception:
                pass
            return result
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
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.get("stox:agent_runs:marker")
                return self._dec(raw) if raw else ""
            except Exception:
                return ""
        with self._get_connection() as conn:
            row = conn.execute("SELECT MAX(timestamp) FROM agent_runs_cache").fetchone()
        return row[0] or ""

    # --- Live quotes API ---
    def save_quotes(self, quotes: List[Dict[str, Any]]):
        """Upsert latest quotes including Kite VWAP & circuit limits."""
        if not quotes:
            return
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                q_map = {}
                for q in quotes:
                    sym_u = str(q.get("symbol", "")).upper().strip()
                    if not sym_u:
                        continue
                    q_map[sym_u] = self._safe_json_dumps({
                        "symbol": sym_u,
                        "ltp": q.get("ltp"),
                        "prev_close": q.get("prev_close"),
                        "day_high": q.get("day_high"),
                        "day_low": q.get("day_low"),
                        "volume": q.get("volume"),
                        "vwap": q.get("vwap"),
                        "upper_circuit": q.get("upper_circuit"),
                        "lower_circuit": q.get("lower_circuit"),
                        "quote_ts": q.get("quote_ts"),
                        "fetched_at": now_str,
                        "source": q.get("source"),
                    })
                if q_map:
                    self.valkey.hset("stox:quotes", mapping=q_map)
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO quotes
                (symbol, ltp, prev_close, day_high, day_low, volume, vwap, upper_circuit, lower_circuit, quote_ts, fetched_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (
                    q["symbol"].upper(), q.get("ltp"), q.get("prev_close"), q.get("day_high"), q.get("day_low"),
                    q.get("volume"), q.get("vwap"), q.get("upper_circuit"), q.get("lower_circuit"),
                    q.get("quote_ts"), now_str, q.get("source"),
                )
                for q in quotes
            ])
            conn.commit()

    def get_all_quotes(self) -> Dict[str, Dict[str, Any]]:
        if self.use_valkey and self.valkey:
            out: Dict[str, Dict[str, Any]] = {}
            try:
                raw_all = self.valkey.hgetall("stox:quotes") or {}
                for k, v in raw_all.items():
                    out[self._dec(k).upper()] = json.loads(self._dec(v))
            except Exception:
                pass
            return out
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT symbol, ltp, prev_close, day_high, day_low, volume, vwap, upper_circuit, lower_circuit, quote_ts, fetched_at, source FROM quotes"
            ).fetchall()
        keys = ("symbol", "ltp", "prev_close", "day_high", "day_low", "volume", "vwap", "upper_circuit", "lower_circuit", "quote_ts", "fetched_at", "source")
        return {r[0]: dict(zip(keys, r)) for r in rows}

    def get_candles_bulk_summary(
        self,
        symbols: Optional[List[str]] = None,
        limit_days: int = 260,
        sparkline_days: int = 25,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Reads candle summaries (25-bar sparkline, 52W high/low, latest close/date, prev_close) for all
        or selected symbols in a single Valkey/SQLite query instead of N per-symbol queries.
        """
        if self.use_valkey and self.valkey:
            out: Dict[str, Dict[str, Any]] = {}
            try:
                if symbols:
                    clean_syms = sorted({str(s).upper().strip() for s in symbols if str(s).strip()})
                    if not clean_syms:
                        return {}
                    vals = self.valkey.hmget("stox:candles:summary", clean_syms)
                    for sym, v in zip(clean_syms, vals):
                        if v:
                            item = json.loads(self._dec(v))
                            if sparkline_days < len(item.get("sparkline", [])):
                                item["sparkline"] = item["sparkline"][-sparkline_days:]
                            out[sym] = item
                    return out
                raw_all = self.valkey.hgetall("stox:candles:summary") or {}
                for k, v in raw_all.items():
                    item = json.loads(self._dec(v))
                    if sparkline_days < len(item.get("sparkline", [])):
                        item["sparkline"] = item["sparkline"][-sparkline_days:]
                    out[self._dec(k).upper()] = item
            except Exception:
                pass
            return out
        lim = max(25, int(limit_days))
        with self._get_connection() as conn:
            if symbols:
                clean_syms = sorted({str(s).upper().strip() for s in symbols if str(s).strip()})
                if not clean_syms:
                    return {}
                out: Dict[str, Dict[str, Any]] = {}
                # SQLite host-parameter limit is 999 -> query in batches of 400
                for start in range(0, len(clean_syms), 400):
                    batch = clean_syms[start:start + 400]
                    placeholders = ",".join("?" for _ in batch)
                    rows = conn.execute(
                        f"SELECT symbol, date, high, low, close FROM historical_candles "
                        f"WHERE symbol IN ({placeholders}) ORDER BY symbol, date DESC",
                        tuple(batch),
                    ).fetchall()
                    out.update(self._aggregate_bulk_candle_rows(rows, lim, sparkline_days))
                return out
            rows = conn.execute(
                "SELECT symbol, date, high, low, close FROM historical_candles ORDER BY symbol, date DESC"
            ).fetchall()
        return self._aggregate_bulk_candle_rows(rows, lim, sparkline_days)

    @staticmethod
    def _aggregate_bulk_candle_rows(rows, limit_days: int, sparkline_days: int) -> Dict[str, Dict[str, Any]]:
        summary: Dict[str, Dict[str, Any]] = {}
        grouped: Dict[str, List[tuple]] = {}
        for sym, d, h, l, c in rows:
            bucket = grouped.setdefault(sym, [])
            if len(bucket) < limit_days:
                bucket.append((d, h, l, c))

        for sym, desc_rows in grouped.items():
            # desc_rows is newest-first
            if not desc_rows:
                continue
            closes_desc = [float(r[3] or 0.0) for r in desc_rows]
            highs_52w = [float(r[1] or r[3] or 0.0) for r in desc_rows[:260]]
            lows_52w = [float(r[2] or r[3] or 0.0) for r in desc_rows[:260] if (r[2] or r[3])]
            highs_all = [float(r[1] or r[3] or 0.0) for r in desc_rows]
            spark = [round(x, 2) for x in reversed(closes_desc[:sparkline_days])]
            latest_c = round(closes_desc[0], 2) if closes_desc else None
            latest_d = str(desc_rows[0][0])[:10]
            prev_c = round(closes_desc[1], 2) if len(closes_desc) > 1 else latest_c

            ret_1y_pct = None
            ret_3y_pct = None
            drawdown_3y_pct = None
            if latest_c and latest_c > 0:
                if len(closes_desc) >= 200:
                    c_1y = closes_desc[min(251, len(closes_desc) - 1)]
                    if c_1y > 0:
                        ret_1y_pct = round(((latest_c - c_1y) / c_1y) * 100.0, 2)
                if len(closes_desc) >= 480:
                    c_3y = closes_desc[min(755, len(closes_desc) - 1)]
                    if c_3y > 0:
                        ret_3y_pct = round(((latest_c - c_3y) / c_3y) * 100.0, 2)
                if len(highs_all) >= 200:
                    h_3y = max(highs_all)
                    if h_3y > 0:
                        drawdown_3y_pct = round(((latest_c - h_3y) / h_3y) * 100.0, 2)

            summary[sym] = {
                "sparkline": spark,
                "latest_close": latest_c,
                "latest_date": latest_d,
                "prev_close": prev_c,
                "high_52w": round(max(highs_52w), 2) if highs_52w else None,
                "low_52w": round(min(lows_52w), 2) if lows_52w else None,
                "ret_1y_pct": ret_1y_pct,
                "ret_3y_pct": ret_3y_pct,
                "drawdown_3y_pct": drawdown_3y_pct,
            }
        return summary

    def get_cached_event_record(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Retrieves {'updated_at': iso, 'events_data': dict} for a symbol from Valkey or SQLite."""
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            try:
                raw = self.valkey.hget("stox:events", sym_u)
                return json.loads(self._dec(raw)) if raw else None
            except Exception:
                return None
        with self._get_connection() as conn:
            has_tbl = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events_cache'"
            ).fetchone()
            if not has_tbl:
                return None
            row = conn.execute("SELECT updated_at, events_data FROM events_cache WHERE symbol = ?", (sym_u,)).fetchone()
            if not row:
                return None
            return {"updated_at": row[0], "events_data": json.loads(row[1])}

    def save_cached_event_record(self, symbol: str, events_data: Dict[str, Any]):
        """Stores corporate events for a symbol into Valkey or SQLite."""
        sym_u = symbol.upper().strip()
        now_str = datetime.now().isoformat()
        if self.use_valkey and self.valkey:
            try:
                self.valkey.hset("stox:events", sym_u, self._safe_json_dumps({
                    "updated_at": now_str,
                    "events_data": events_data,
                }))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS events_cache (
                    symbol TEXT PRIMARY KEY,
                    updated_at TEXT,
                    events_data TEXT
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO events_cache (symbol, updated_at, events_data) VALUES (?, ?, ?)",
                (sym_u, now_str, self._safe_json_dumps(events_data)),
            )
            conn.commit()

    def get_cached_events_bulk(self) -> Dict[str, Dict[str, Any]]:
        """Reads all cached corporate events in ONE query and strips expired event dates."""
        today = datetime.now().strftime("%Y-%m-%d")
        if self.use_valkey and self.valkey:
            result: Dict[str, Dict[str, Any]] = {}
            try:
                raw_all = self.valkey.hgetall("stox:events") or {}
                for k, v in raw_all.items():
                    rec = json.loads(self._dec(v))
                    data = rec.get("events_data") or {}
                    if data.get("earnings_date") and str(data["earnings_date"]) < today:
                        data["earnings_date"] = None
                    if data.get("dividend_ex_date") and str(data["dividend_ex_date"]) < today:
                        data["dividend_ex_date"] = None
                        data["dividend_amount"] = None
                        data["dividend_per_share"] = None
                    if isinstance(data.get("upcoming_macro_catalysts"), list):
                        data["upcoming_macro_catalysts"] = [
                            m for m in data["upcoming_macro_catalysts"] if str(m.get("date") or "") >= today
                        ]
                    result[self._dec(k).upper()] = data
            except Exception:
                pass
            return result
        with self._get_connection() as conn:
            has_tbl = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='events_cache'"
            ).fetchone()
            if not has_tbl:
                return {}
            rows = conn.execute("SELECT symbol, events_data FROM events_cache").fetchall()

        result: Dict[str, Dict[str, Any]] = {}
        for sym, blob in rows:
            try:
                data = json.loads(blob)
            except Exception:
                continue
            if data.get("earnings_date") and str(data["earnings_date"]) < today:
                data["earnings_date"] = None
            if data.get("dividend_ex_date") and str(data["dividend_ex_date"]) < today:
                data["dividend_ex_date"] = None
                data["dividend_amount"] = None
                data["dividend_per_share"] = None
            if isinstance(data.get("upcoming_macro_catalysts"), list):
                data["upcoming_macro_catalysts"] = [
                    m for m in data["upcoming_macro_catalysts"] if str(m.get("date") or "") >= today
                ]
            result[str(sym).upper()] = data
        return result

    def prune_macro_history(self, keep_bulletins: int = 200, keep_days: int = 14) -> Dict[str, int]:
        """Bounds shared_market_bulletin and macro_cache table growth."""
        if self.use_valkey and self.valkey:
            return {"bulletins_pruned": 0, "macro_rows_pruned": 0}
        cutoff = (datetime.now() - timedelta(days=max(1, int(keep_days)))).isoformat()
        with self._get_connection() as conn:
            c1 = conn.execute(
                """
                DELETE FROM shared_market_bulletin
                WHERE id NOT IN (
                    SELECT id FROM shared_market_bulletin ORDER BY id DESC LIMIT ?
                )
                """,
                (max(1, int(keep_bulletins)),),
            )
            c2 = conn.execute(
                """
                DELETE FROM macro_cache
                WHERE fetch_date < ?
                  AND fetch_date NOT IN (
                    SELECT MAX(fetch_date) FROM macro_cache m2 WHERE m2.indicator_name = macro_cache.indicator_name
                  )
                """,
                (cutoff,),
            )
            conn.commit()
            return {"bulletins_pruned": max(0, c1.rowcount), "macro_rows_pruned": max(0, c2.rowcount)}

    # --- Prediction log API ---
    def log_prediction(self, rec: Dict[str, Any]):
        """
        Record a verdict. One row per (symbol, as_of_date): re-analysing the same day refreshes the row while it
        is still OPEN, but never rewrites an already-resolved prediction.
        """
        from tools import market_calendar
        made_at_val = rec.get("made_at") or market_calendar.now_ist().isoformat()
        model_ver = str(rec.get("model_version") or MODEL_VERSION)
        split_fac = float(rec.get("split_adjusted_factor") or 1.0)
        sym_u = rec["symbol"].upper().strip()
        as_of = str(rec["as_of_date"])
        if self.use_valkey and self.valkey:
            try:
                pkey = f"{sym_u}::{as_of}"
                raw_prev = self.valkey.hget("stox:predictions", pkey)
                if raw_prev:
                    prev_obj = json.loads(self._dec(raw_prev))
                    if prev_obj.get("status", "OPEN") != "OPEN":
                        return
                    pred_id = prev_obj.get("id") or int(self.valkey.incr("stox:predictions:seq"))
                else:
                    pred_id = int(self.valkey.incr("stox:predictions:seq"))
                self.valkey.hset("stox:predictions", pkey, self._safe_json_dumps({
                    "id": pred_id,
                    "symbol": sym_u,
                    "made_at": made_at_val,
                    "as_of_date": as_of,
                    "verdict": rec.get("verdict"),
                    "confidence_pct": rec.get("confidence_pct"),
                    "price_at_signal": rec.get("price_at_signal"),
                    "entry_lo": rec.get("entry_lo"),
                    "entry_hi": rec.get("entry_hi"),
                    "target": rec.get("target"),
                    "stop": rec.get("stop"),
                    "evidence_score": rec.get("evidence_score"),
                    "horizon_days": rec.get("horizon_days"),
                    "status": "OPEN",
                    "resolved_at": None,
                    "outcome_price": None,
                    "return_pct": None,
                    "model_version": model_ver,
                    "split_adjusted_factor": split_fac,
                }))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO prediction_log
                (symbol, made_at, as_of_date, verdict, confidence_pct, price_at_signal, entry_lo, entry_hi,
                 target, stop, evidence_score, breakdown, horizon_days, model_version, split_adjusted_factor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, as_of_date) DO UPDATE SET
                    made_at=excluded.made_at, verdict=excluded.verdict, confidence_pct=excluded.confidence_pct,
                    price_at_signal=excluded.price_at_signal, entry_lo=excluded.entry_lo, entry_hi=excluded.entry_hi,
                    target=excluded.target, stop=excluded.stop, evidence_score=excluded.evidence_score,
                    breakdown=excluded.breakdown, horizon_days=excluded.horizon_days,
                    model_version=excluded.model_version, split_adjusted_factor=excluded.split_adjusted_factor
                WHERE prediction_log.status = 'OPEN'
            """, (
                sym_u, made_at_val, as_of,
                rec.get("verdict"), rec.get("confidence_pct"), rec.get("price_at_signal"), rec.get("entry_lo"),
                rec.get("entry_hi"), rec.get("target"), rec.get("stop"), rec.get("evidence_score"),
                self._safe_json_dumps(rec.get("breakdown") or []), rec.get("horizon_days"),
                model_ver, split_fac,
            ))
            conn.commit()

    def get_predictions(
        self,
        status: Optional[str] = None,
        model_version: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if self.use_valkey and self.valkey:
            out: List[Dict[str, Any]] = []
            try:
                raw_all = self.valkey.hgetall("stox:predictions") or {}
                for _, v in raw_all.items():
                    rec = json.loads(self._dec(v))
                    st = rec.get("status", "OPEN")
                    mv = rec.get("model_version") or "legacy"
                    if status == "RESOLVED" and st == "OPEN":
                        continue
                    if status and status != "RESOLVED" and st != status:
                        continue
                    if model_version and mv != model_version:
                        continue
                    out.append(rec)
                out.sort(key=lambda r: (str(r.get("as_of_date", "")), int(r.get("id") or 0)))
            except Exception:
                pass
            return out
        sql = (
            "SELECT id, symbol, made_at, as_of_date, verdict, confidence_pct, price_at_signal, entry_lo, entry_hi, "
            "target, stop, evidence_score, horizon_days, status, resolved_at, outcome_price, return_pct, "
            "COALESCE(model_version, 'legacy'), COALESCE(split_adjusted_factor, 1.0) "
            "FROM prediction_log"
        )
        clauses: List[str] = []
        params_list: List[Any] = []
        if status == "RESOLVED":
            clauses.append("status != 'OPEN'")
        elif status:
            clauses.append("status = ?")
            params_list.append(status)
        if model_version:
            clauses.append("COALESCE(model_version, 'legacy') = ?")
            params_list.append(model_version)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY as_of_date, id"
        keys = (
            "id", "symbol", "made_at", "as_of_date", "verdict", "confidence_pct", "price_at_signal", "entry_lo",
            "entry_hi", "target", "stop", "evidence_score", "horizon_days", "status", "resolved_at",
            "outcome_price", "return_pct", "model_version", "split_adjusted_factor",
        )
        with self._get_connection() as conn:
            rows = conn.execute(sql, tuple(params_list)).fetchall()
        return [dict(zip(keys, r)) for r in rows]

    def rebase_open_predictions(
        self,
        symbol: str,
        factor: float,
        as_of_cutoff: Optional[str] = None,
    ) -> int:
        """
        Re-baselines price levels on OPEN predictions when corporate actions (splits/bonuses) rescale historical candles.
        """
        if factor is None or factor <= 0 or abs(factor - 1.0) <= 1e-4:
            return 0
        sym_u = symbol.upper().strip()
        if self.use_valkey and self.valkey:
            updated = 0
            try:
                raw_all = self.valkey.hgetall("stox:predictions") or {}
                for k, v in raw_all.items():
                    key_str = self._dec(k)
                    if not key_str.startswith(f"{sym_u}::"):
                        continue
                    rec = json.loads(self._dec(v))
                    if rec.get("status", "OPEN") != "OPEN":
                        continue
                    if as_of_cutoff and str(rec.get("as_of_date", "")) > as_of_cutoff:
                        continue
                    for fld in ("price_at_signal", "entry_lo", "entry_hi", "target", "stop"):
                        if rec.get(fld) is not None:
                            rec[fld] = round(float(rec[fld]) * factor, 2)
                    rec["split_adjusted_factor"] = float(rec.get("split_adjusted_factor") or 1.0) * factor
                    self.valkey.hset("stox:predictions", key_str, self._safe_json_dumps(rec))
                    updated += 1
            except Exception:
                pass
            return updated
        sql = """
            UPDATE prediction_log
            SET price_at_signal = ROUND(price_at_signal * ?, 2),
                entry_lo = CASE WHEN entry_lo IS NOT NULL THEN ROUND(entry_lo * ?, 2) ELSE NULL END,
                entry_hi = CASE WHEN entry_hi IS NOT NULL THEN ROUND(entry_hi * ?, 2) ELSE NULL END,
                target = ROUND(target * ?, 2),
                stop = ROUND(stop * ?, 2),
                split_adjusted_factor = COALESCE(split_adjusted_factor, 1.0) * ?
            WHERE symbol = ? AND status = 'OPEN'
        """
        params: List[Any] = [factor, factor, factor, factor, factor, factor, sym_u]
        if as_of_cutoff:
            sql += " AND as_of_date <= ?"
            params.append(as_of_cutoff)
        with self._get_connection() as conn:
            cur = conn.execute(sql, tuple(params))
            conn.commit()
            return max(0, cur.rowcount)

    def resolve_prediction(self, prediction_id: int, status: str, outcome_price: Optional[float],
                           return_pct: Optional[float], resolved_at: Optional[str] = None):
        if self.use_valkey and self.valkey:
            try:
                raw_all = self.valkey.hgetall("stox:predictions") or {}
                for k, v in raw_all.items():
                    rec = json.loads(self._dec(v))
                    if int(rec.get("id") or -1) == int(prediction_id) and rec.get("status", "OPEN") == "OPEN":
                        rec["status"] = status
                        rec["resolved_at"] = resolved_at or datetime.now().isoformat()
                        rec["outcome_price"] = outcome_price
                        rec["return_pct"] = return_pct
                        self.valkey.hset("stox:predictions", self._dec(k), self._safe_json_dumps(rec))
                        break
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE prediction_log SET status = ?, resolved_at = ?, outcome_price = ?, return_pct = ? "
                "WHERE id = ? AND status = 'OPEN'",
                (status, resolved_at or datetime.now().isoformat(), outcome_price, return_pct, prediction_id)
            )
            conn.commit()

    # --- Scheduler bookkeeping ---
    def get_state(self, key: str) -> Optional[str]:
        if self.use_valkey and self.valkey:
            try:
                val = self.valkey.hget("stox:kv_state", key)
                return self._dec(val) if val is not None else None
            except Exception:
                return None
        with self._get_connection() as conn:
            row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_state(self, key: str, value: str):
        if self.use_valkey and self.valkey:
            try:
                self.valkey.hset("stox:kv_state", key, str(value))
            except Exception:
                pass
            return
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO kv_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat())
            )
            conn.commit()

    # --- Housekeeping ---
    def prune_agent_runs(self, keep_days: int = 30) -> int:
        """Delete agent outputs older than keep_days, always keeping the newest one per (symbol, agent)."""
        if self.use_valkey and self.valkey:
            return 0
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
