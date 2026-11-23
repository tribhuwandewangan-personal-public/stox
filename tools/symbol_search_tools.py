"""
Symbol Search & Management Tools for NSE Stock Predictor.
Enables searching the internet (Yahoo Finance / NSE search) for company tickers,
validating Indian equity symbols, and dynamically adding/removing symbols in symbols.json
and the persistent SQLite task queue.
"""

import os
import json
import sqlite3
import threading
from storage.cache_manager import open_db
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Dict, Any, List, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
from config import SYMBOLS_FILE_PATH, CACHE_DB_PATH, MIDCAP_250_SYMBOLS_FILE_PATH, ALL_NSE_SYMBOLS_FILE_PATH, NSE_CATALOG_FILE_PATH

_CATALOG_LOCK = threading.Lock()
_CATALOG_CACHE: Dict[str, Any] = {"loaded": False, "items": []}


def _load_local_nse_catalog() -> List[Dict[str, Any]]:
    """
    Loads and caches the unified local NSE stock catalog (Curated + Midcap 250 + All NSE ~2,200+ equities)
    for sub-millisecond partial search by symbol, company name, or sector.
    """
    with _CATALOG_LOCK:
        if _CATALOG_CACHE["loaded"] and _CATALOG_CACHE["items"]:
            return _CATALOG_CACHE["items"]

        catalog_map: Dict[str, Dict[str, Any]] = {}
        sources = [
            (NSE_CATALOG_FILE_PATH, "NSE Master Catalog", 2),
            (ALL_NSE_SYMBOLS_FILE_PATH, "Nifty 100", 1),
            (MIDCAP_250_SYMBOLS_FILE_PATH, "Nifty Midcap 100", 1),
            (SYMBOLS_FILE_PATH, "Curated Watchlist", 0),
        ]
        for path, src_label, priority in sources:
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                sym_list = data.get("symbols", []) if isinstance(data, dict) else []
                for item in sym_list:
                    sym = str(item.get("symbol") or "").upper().strip()
                    if not sym:
                        continue
                    name = str(item.get("name") or sym).strip()
                    sector = str(item.get("sector") or "Indian Equities").strip()
                    exchange = str(item.get("exchange") or "NSE").upper().strip()
                    prev = catalog_map.get(sym)
                    if not prev:
                        catalog_map[sym] = {
                            "symbol": sym,
                            "name": name,
                            "sector": sector,
                            "exchange": exchange,
                            "source": src_label,
                            "priority": priority,
                        }
                    else:
                        if name and (prev["name"] == sym or len(name) > len(prev["name"])):
                            prev["name"] = name
                        if sector and sector != "Indian Equities":
                            prev["sector"] = sector
                        prev["priority"] = min(prev["priority"], priority)
                        if priority <= 1:
                            prev["source"] = src_label
            except Exception:
                continue

        items = sorted(catalog_map.values(), key=lambda x: (x["priority"], x["symbol"]))
        _CATALOG_CACHE["items"] = items
        _CATALOG_CACHE["loaded"] = True
        return items


def search_internet_symbols(
    query: str,
    symbols_file: str = SYMBOLS_FILE_PATH,
    limit: int = 30,
    allow_remote: bool = True,
) -> List[Dict[str, Any]]:
    """
    Performs instant partial search across the local NSE equity catalog (~2,200+ stocks)
    by symbol, company name, or sector, supplemented by Yahoo Finance live search when needed.
    When query is empty, returns popular NSE stocks (prioritizing those not yet in symbols.json).
    """
    clean_query = (query or "").strip()

    # Get set of already tracked symbols in symbols.json
    existing_symbols = set()
    if os.path.exists(symbols_file):
        try:
            with open(symbols_file, "r", encoding="utf-8") as f:
                s_data = json.load(f)
                existing_symbols = {str(s.get("symbol") or "").upper().strip() for s in s_data.get("symbols", [])}
        except Exception:
            pass

    catalog = _load_local_nse_catalog()

    # Empty query: return popular Midcap 250 / NSE stocks so the modal immediately shows selectable stocks
    if not clean_query:
        not_added = []
        added = []
        for item in catalog:
            sym = item["symbol"]
            is_in = sym in existing_symbols
            entry = {
                "symbol": sym,
                "name": item["name"],
                "sector": item["sector"],
                "exchange": item["exchange"],
                "yahoo_ticker": f"{sym}.NS",
                "is_added": is_in,
                "source": item["source"],
            }
            if not is_in:
                not_added.append(entry)
            else:
                added.append(entry)
            if len(not_added) >= limit:
                break
        return (not_added + added)[:limit]

    q_upper = clean_query.upper().replace(".NS", "").replace(".BO", "").strip()
    q_lower = clean_query.lower().strip()
    tokens = [t for t in q_lower.split() if t]

    scored_matches: List[Tuple[Tuple[int, int, int, str], Dict[str, Any]]] = []
    seen_tickers = set()

    for item in catalog:
        sym = item["symbol"]
        name = item["name"]
        sector = item["sector"]
        sym_l = sym.lower()
        name_l = name.lower()
        sec_l = sector.lower()
        combined = f"{sym_l} {name_l} {sec_l}"

        # All search tokens must partially match somewhere in symbol, name, or sector
        if not all(tok in combined for tok in tokens):
            continue

        # Rank relevance: lower rank tuple is better
        if sym == q_upper:
            rank_tier = 0
        elif sym.startswith(q_upper):
            rank_tier = 1
        elif name_l.startswith(q_lower):
            rank_tier = 2
        elif any(w.startswith(q_lower) for w in name_l.replace("(", " ").replace(")", " ").split()):
            rank_tier = 3
        elif q_upper in sym:
            rank_tier = 4
        elif q_lower in name_l:
            rank_tier = 5
        else:
            rank_tier = 6

        is_in = sym in existing_symbols
        seen_tickers.add(sym)
        scored_matches.append((
            (rank_tier, item["priority"], len(sym), sym),
            {
                "symbol": sym,
                "name": name,
                "sector": sector,
                "exchange": item["exchange"],
                "yahoo_ticker": f"{sym}.NS",
                "is_added": is_in,
                "source": item["source"],
            },
        ))

    scored_matches.sort(key=lambda x: x[0])
    results: List[Dict[str, Any]] = [m[1] for m in scored_matches[:limit]]

    # Supplement with Yahoo Finance live search only when local partial search found few matches
    if allow_remote and len(results) < 6 and len(clean_query) >= 2:
        encoded = urllib.parse.quote(clean_query)
        search_url = f"https://query2.finance.yahoo.com/v1/finance/search?q={encoded}&quotesCount=12&newsCount=0"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        try:
            req = urllib.request.Request(search_url, headers=headers)
            with urllib.request.urlopen(req, timeout=2.5) as response:
                raw_data = json.loads(response.read().decode("utf-8"))
                quotes = raw_data.get("quotes", [])
                for q in quotes:
                    full_sym = q.get("symbol", "")
                    exch = (q.get("exchange") or "").upper()
                    qtype = (q.get("quoteType") or "").upper()

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
                        "source": "Yahoo Finance Live Feed",
                    })
                    if len(results) >= limit:
                        break
        except Exception:
            pass

    # If the user typed a valid custom ticker directly that wasn't in the catalog, offer direct entry
    direct_sym = q_upper
    if direct_sym and direct_sym not in seen_tickers and 2 <= len(direct_sym) <= 20 and direct_sym.replace("-", "").replace("&", "").isalnum():
        results.append({
            "symbol": direct_sym,
            "name": f"{direct_sym} Limited",
            "sector": "Indian Equities",
            "exchange": "NSE",
            "yahoo_ticker": f"{direct_sym}.NS",
            "is_added": direct_sym in existing_symbols,
            "source": "Custom NSE Symbol",
        })

    return results[:limit]


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

    # Register in Valkey queue if available, otherwise fallback to SQLite queue
    try:
        from storage.queue_manager import ValkeyQueueManager
        qm = ValkeyQueueManager(db_path=db_path)
        qm.enqueue_symbols([new_stock], force=False)
    except Exception as e:
        print(f"Notice: Could not insert {clean_sym} into queue: {e}")

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

    # Clean from queue (Valkey if available, else SQLite)
    try:
        from storage.queue_manager import ValkeyQueueManager
        qm = ValkeyQueueManager(db_path=db_path)
        qm.remove_symbol(clean_sym)
    except Exception:
        pass

    return {
        "status": "removed",
        "symbol": clean_sym,
        "total_symbols": len(filtered_list),
        "message": f"Successfully removed {clean_sym} from symbols.json."
    }
