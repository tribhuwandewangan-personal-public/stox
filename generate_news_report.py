"""
Standalone Runner to Collect Financial News and Generate Markdown Reports.
Creates a separate folder with the date in its name (news_reports/YYYY-MM-DD/)
containing exactly TWO files:
1. general_market_news.md: Macro/common news (Crude Oil, Rupee, US/Global cues, FII/DII, Market catalysts).
2. stock_specific_news.md: Stock-specific news from multiple sources for all tracked stocks in a single file.

Usage:
    uv run python generate_news_report.py
    uv run python generate_news_report.py --force-refresh
    uv run python generate_news_report.py --date 2026-10-11
    uv run python generate_news_report.py --symbols RELIANCE,TATAMOTORS,HDFCBANK
"""

import os
import sys
import argparse
import json
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from config import SYMBOLS_FILE_PATH
from tools.news_tools import NewsSentimentEngine


def load_symbols():
    if not os.path.exists(SYMBOLS_FILE_PATH):
        print(f"Error: {SYMBOLS_FILE_PATH} not found.")
        return []
    with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("symbols", [])


def main():
    parser = argparse.ArgumentParser(description="Collect financial news and generate exactly two reports (generic and stock-specific) in a date folder.")
    parser.add_argument("--date", type=str, default=None, help="Target date in YYYY-MM-DD format (defaults to current date)")
    parser.add_argument("--symbols", type=str, default=None, help="Comma-separated symbols to filter (e.g. RELIANCE,HDFCBANK)")
    parser.add_argument("--force-refresh", action="store_true", help="Bypass SQLite cache and fetch fresh live online news")
    parser.add_argument("--output-dir", type=str, default=None, help="Base output directory (defaults to ./news_reports)")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent workers for fetching news feeds")
    args = parser.parse_args()

    all_symbols = load_symbols()
    if not all_symbols:
        print("No stock symbols loaded.")
        return

    if args.symbols:
        filter_set = {s.strip().upper() for s in args.symbols.split(",")}
        target_symbols = [s for s in all_symbols if s.get("symbol", "").upper() in filter_set]
        if not target_symbols:
            print(f"None of the specified symbols ({args.symbols}) match entries in symbols.json.")
            return
    else:
        target_symbols = all_symbols

    target_date = args.date or datetime.now().strftime("%Y-%m-%d")

    engine = NewsSentimentEngine()
    result = engine.generate_both_reports(
        symbols=target_symbols,
        date_str=target_date,
        output_base_dir=args.output_dir,
        force_refresh=args.force_refresh,
        max_workers=args.workers
    )

    print("Summary:")
    print(f"• Output Date Directory: {result['date_folder']}")
    print(f"• 1️⃣  Generic Market News File: {result['general_market_news']}")
    print(f"• 2️⃣  Stock-Specific News File: {result['stock_specific_news']}")


if __name__ == "__main__":
    main()
