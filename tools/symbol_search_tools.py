"""
Symbol Search & Management Tools for NSE Stock Predictor.
Enables searching the internet (Yahoo Finance / NSE search) for company tickers,
validating Indian equity symbols, and dynamically adding/removing symbols in symbols.json
and the persistent SQLite task queue.
"""

import os
import json
import sqlite3
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from config import SYMBOLS_FILE_PATH, CACHE_DB_PATH


def search_internet_symbols(query: str, symbols_file: str = SYMBOLS_FILE_PATH) -> List[Dict[str, Any]]:
    """
    Searches the internet for Indian (NSE/BSE) equity symbols matching the user's query.
    Extracts clean ticker, company name, sector, and checks if already present in symbols.json.
    """
    clean_query = (query or "").strip()
    if not clean_query:
        return []

    # Get set of already tracked symbols
    existing_symbols = set()
    if os.path.exists(symbols_file):
        try:
            with open(symbols_file, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                existing_symbols = {s.get("symbol", "").upper() for s in s_data.get("symbols", [])}
        except Exception:
            pass

    results: List[Dict[str, Any]] = []
    seen_tickers = set()

    # 1. Query Yahoo Finance live search API
    encoded = urllib.parse.quote(clean_query)
    search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={encoded}&quotesCount=15&newsCount=0"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=4.5) as response:
            raw_data = json.loads(response.read().decode("utf-8"))
            quotes = raw_data.get("quotes", [])
            for q in quotes:
                full_sym = q.get("symbol", "")
                exch = (q.get("exchange") or "").upper()
                qtype = (q.get("quoteType") or "").upper()

                # Prioritize Indian equities (.NS, .BO, or Indian exchange tags)
                is_indian = (
                    full_sym.endswith(".NS")
                    or full_sym.endswith(".BO")
                    or exch in ("NSI", "NSE", "BSE")
                )
                if not is_indian and qtype != "EQUITY":
                    continue

                clean_sym = full_sym.replace(".NS", "").replace(".BO", "").upper().strip()
                if not clean_sym or clean_sym in seen_tickers:
                    continue
                seen_tickers.add(clean_sym)

                name = q.get("shortname") or q.get("longname") or clean_sym
                sector = q.get("sector") or q.get("industry") or "Indian Equities"
                exchange = "NSE" if (full_sym.endswith(".NS") or exch in ("NSI", "NSE")) else ("BSE" if full_sym.endswith(".BO") or exch == "BSE" else "NSE")

                results.append({
                    "symbol": clean_sym,
                    "name": name,
                    "sector": sector,
                    "exchange": exchange,
                    "yahoo_ticker": full_sym,
                    "is_added": clean_sym in existing_symbols,
                    "source": "Yahoo Finance Live Feed"
                })
    except Exception as e:
        # Fallback for network timeouts or DNS resolution
        pass

    # 2. If the user typed an exact symbol directly (e.g. TATAPOWER, SUZLON, ZOMATO)
    # Ensure it's included as a top candidate even if search returned other items
    direct_sym = clean_query.upper().replace(".NS", "").replace(".BO", "").strip()
    if direct_sym and direct_sym not in seen_tickers and len(direct_sym) >= 2 and direct_sym.isalnum():
        results.insert(0, {
            "symbol": direct_sym,
            "name": f"{direct_sym} Limited",
            "sector": "Indian Equities",
            "exchange": "NSE",
            "yahoo_ticker": f"{direct_sym}.NS",
            "is_added": direct_sym in existing_symbols,
            "source": "Direct Symbol Entry"
        })

    return results


def add_symbol_to_json(
    symbol: str,
    name: str = "",
    sector: str = "",
    exchange: str = "NSE",
    symbols_file: str = SYMBOLS_FILE_PATH,
    db_path: str = CACHE_DB_PATH
) -> Dict[str, Any]:
    """
    Appends a new verified stock symbol into symbols.json and registers it in the SQLite queue.
    """
    clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    if not clean_sym:
        return {"status": "error", "message": "Symbol cannot be empty."}

    symbols_data: Dict[str, Any] = {"symbols": []}
    if os.path.exists(symbols_file):
        with open(symbols_file, "r", encoding="utf-8") as f:
            try:
                symbols_data = json.load(f)
            except Exception:
                symbols_data = {"symbols": []}

    existing_list = symbols_data.get("symbols", [])
    for item in existing_list:
        if item.get("symbol", "").upper() == clean_sym:
            return {
                "status": "exists",
                "symbol": clean_sym,
                "name": item.get("name", clean_sym),
                "sector": item.get("sector", "Equities"),
                "message": f"Symbol {clean_sym} is already in symbols.json."
            }

    clean_name = name.strip() if name and name.strip() else f"{clean_sym} Limited"
    clean_sector = sector.strip() if sector and sector.strip() else "Equities"
    clean_exchange = exchange.strip().upper() if exchange and exchange.strip() else "NSE"

    new_stock = {
        "symbol": clean_sym,
        "name": clean_name,
        "sector": clean_sector,
        "exchange": clean_exchange
    }

    existing_list.append(new_stock)
    symbols_data["symbols"] = existing_list
    symbols_data["updated_at"] = datetime.now().strftime("%Y-%m-%d")

    # Atomic write to symbols.json
    temp_file = f"{symbols_file}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(symbols_data, f, indent=2, ensure_ascii=False)
    os.replace(temp_file, symbols_file)

    # Insert into persistent SQLite queue
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        with sqlite3.connect(db_path) as conn:
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
            cursor.execute("""
                INSERT OR IGNORE INTO persistent_stock_queue (symbol, company_name, sector, status)
                VALUES (?, ?, ?, 'pending')
            """, (clean_sym, clean_name, clean_sector))
            conn.commit()
    except Exception as e:
        print(f"Notice: Could not insert {clean_sym} into persistent queue: {e}")

    return {
        "status": "added",
        "symbol": clean_sym,
        "name": clean_name,
        "sector": clean_sector,
        "exchange": clean_exchange,
        "total_symbols": len(existing_list),
        "message": f"Successfully added {clean_sym} ({clean_name}) to symbols.json!"
    }


def remove_symbol_from_json(
    symbol: str,
    symbols_file: str = SYMBOLS_FILE_PATH,
    db_path: str = CACHE_DB_PATH
) -> Dict[str, Any]:
    """
    Removes a symbol from symbols.json and persistent queue.
    """
    clean_sym = symbol.upper().replace(".NS", "").replace(".BO", "").strip()
    if not os.path.exists(symbols_file):
        return {"status": "error", "message": "symbols.json not found."}

    with open(symbols_file, "r", encoding="utf-8") as f:
        symbols_data = json.load(f)

    existing_list = symbols_data.get("symbols", [])
    filtered_list = [s for s in existing_list if s.get("symbol", "").upper() != clean_sym]

    if len(filtered_list) == len(existing_list):
        return {"status": "not_found", "message": f"Symbol {clean_sym} not found in symbols.json."}

    symbols_data["symbols"] = filtered_list
    symbols_data["updated_at"] = datetime.now().strftime("%Y-%m-%d")

    temp_file = f"{symbols_file}.tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(symbols_data, f, indent=2, ensure_ascii=False)
    os.replace(temp_file, symbols_file)

    # Clean from queue
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM persistent_stock_queue WHERE symbol = ?", (clean_sym,))
            conn.commit()
    except Exception:
        pass

    return {
        "status": "removed",
        "symbol": clean_sym,
        "total_symbols": len(filtered_list),
        "message": f"Successfully removed {clean_sym} from symbols.json."
    }
