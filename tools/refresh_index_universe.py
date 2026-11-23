"""
Rebuilds the analysis universes from OFFICIAL NSE index constituent lists (niftyindices.com):

  symbols_nse_all.json      -> Nifty 100            (Nifty 50 + Nifty Next 50)       "large cap"
  symbols_midcap_250.json   -> Nifty Midcap 100     (Midcap 50 + Midcap Next 50)     "mid cap"
  symbols_nse_catalog.json  -> untouched full NSE master list (used ONLY for Add-Symbol search)

File names are kept for backwards compatibility with config.py / API universe keys
(`all_nse` = large cap, `midcap250` = mid cap). Run quarterly (NSE rebalances in Mar & Sep):

    .\\.venv\\Scripts\\python.exe tools\\refresh_index_universe.py            # download + write
    .\\.venv\\Scripts\\python.exe tools\\refresh_index_universe.py --offline  # reuse storage/index_csv/*.csv
"""

import argparse
import csv
import json
import os
import sys
import urllib.request
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from config import ALL_NSE_SYMBOLS_FILE_PATH, MIDCAP_250_SYMBOLS_FILE_PATH, SYMBOLS_FILE_PATH  # noqa: E402

CSV_DIR = os.path.join(PROJECT_ROOT, "storage", "index_csv")
CATALOG_PATH = os.path.join(PROJECT_ROOT, "symbols_nse_catalog.json")
URL = "https://www.niftyindices.com/IndexConstituent/ind_{}list.csv"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# NSE "Industry" -> this app's sector labels (used when the symbol has no sector in the catalog/curated list)
INDUSTRY_MAP = {
    "Financial Services": "Banking & Financial Services",
    "Information Technology": "Information Technology",
    "Healthcare": "Pharma & Healthcare",
    "Fast Moving Consumer Goods": "FMCG",
    "Automobile and Auto Components": "Automobiles",
    "Oil Gas & Consumable Fuels": "Oil, Gas & Consumable Fuels",
    "Metals & Mining": "Metals & Mining",
    "Power": "Power & Utilities",
    "Construction": "Infrastructure & Construction",
    "Construction Materials": "Cement & Construction Materials",
    "Capital Goods": "Capital Goods",
    "Consumer Durables": "Consumer Durables",
    "Consumer Services": "Consumer Services",
    "Telecommunication": "Telecom",
    "Realty": "Real Estate",
    "Chemicals": "Chemicals",
    "Services": "Services & Logistics",
    "Textiles": "Textiles",
    "Media Entertainment & Publication": "Media & Entertainment",
    "Diversified": "Diversified",
    "Forest Materials": "Paper & Forest Products",
}


def _fetch(name: str, offline: bool) -> list:
    path = os.path.join(CSV_DIR, f"{name}.csv")
    if not offline:
        os.makedirs(CSV_DIR, exist_ok=True)
        raw = urllib.request.urlopen(urllib.request.Request(URL.format(name), headers=HEADERS), timeout=30).read()
        with open(path, "wb") as f:
            f.write(raw)
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_sector_hints() -> dict:
    """Curated watchlist sectors win (tuned labels e.g. 'Capital Markets'); everything else uses NSE's own Industry."""
    hints = {}
    if os.path.exists(SYMBOLS_FILE_PATH):
        try:
            with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
                syms = json.load(f).get("symbols", [])
            for it in syms:
                sec = str(it.get("sector") or "").strip()
                sym = str(it.get("symbol") or "").upper().strip()
                if sym and sec and sec != "Indian Equities":
                    hints[sym] = sec
        except Exception:
            pass
    return hints


def _build(rows: list, hints: dict) -> list:
    out, seen = [], set()
    for r in rows:
        sym = (r.get("Symbol") or "").upper().strip()
        if not sym or sym in seen or sym.startswith("DUMMY"):
            continue
        seen.add(sym)
        industry = (r.get("Industry") or "").strip()
        out.append({
            "symbol": sym,
            "name": (r.get("Company Name") or sym).strip(),
            "sector": hints.get(sym) or INDUSTRY_MAP.get(industry, industry or "Indian Equities"),
            "exchange": "NSE",
        })
    return out


def _write(path: str, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="reuse previously downloaded CSVs")
    args = ap.parse_args()

    # Preserve the full master list for Add-Symbol search before the large-cap file is overwritten
    if not os.path.exists(CATALOG_PATH) and os.path.exists(ALL_NSE_SYMBOLS_FILE_PATH):
        with open(ALL_NSE_SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            old = json.load(f)
        if len(old.get("symbols", [])) > 500:
            _write(CATALOG_PATH, old)
            print(f"Saved full NSE catalog -> {CATALOG_PATH} ({len(old['symbols'])} stocks)")

    hints = _load_sector_hints()
    today = datetime.now().strftime("%Y-%m-%d")

    large = _build(_fetch("nifty50", args.offline) + _fetch("niftynext50", args.offline), hints)
    mid = _build(_fetch("niftymidcap50", args.offline) + _fetch("niftymidcap100", args.offline), hints)
    # Nifty Midcap 100 already contains Midcap 50 -> dedupe by symbol (handled in _build)
    large_syms = {x["symbol"] for x in large}
    mid = [x for x in mid if x["symbol"] not in large_syms]

    _write(ALL_NSE_SYMBOLS_FILE_PATH, {
        "description": "Nifty 100 (Nifty 50 + Nifty Next 50) - large cap analysis universe (official NSE constituents)",
        "index_universe": "NIFTY 100",
        "updated_at": today,
        "source": "niftyindices.com",
        "count": len(large),
        "symbols": large,
    })
    _write(MIDCAP_250_SYMBOLS_FILE_PATH, {
        "description": "Nifty Midcap 100 (Midcap 50 + Midcap Next 50) - mid cap analysis universe (official NSE constituents)",
        "index_universe": "NIFTY MIDCAP 100",
        "updated_at": today,
        "default_timeframe_days": 1825,
        "count": len(mid),
        "symbols": mid,
    })
    print(f"Large cap (Nifty 100): {len(large)} | Mid cap (Midcap 100): {len(mid)}")


if __name__ == "__main__":
    main()
