"""
Configuration module for the NSE multi-agent stock analysis system.
The analysis engine is fully deterministic (rule-based): no LLM or external AI service is used.
"""

import os
import sys

# Ensure UTF-8 output encoding across all modules importing config
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

# Verbose & Execution Settings
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "false").lower() in ("true", "1", "yes")
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "6"))   # analyst agents per symbol
MAX_SYMBOL_WORKERS = int(os.getenv("MAX_SYMBOL_WORKERS", "4"))       # symbols analysed concurrently
AGENT_TIMEOUT_SECONDS = int(os.getenv("AGENT_TIMEOUT_SECONDS", "90"))  # max wait per analyst agent
MAX_CONCURRENT_TRIGGERS = int(os.getenv("MAX_CONCURRENT_TRIGGERS", "4"))  # dashboard "Re-Analyze" cap

# Dashboard / live quotes / scheduler
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")                    # loopback only; set 0.0.0.0 to expose (not advised)
QUOTE_SOURCES = os.getenv("QUOTE_SOURCES", "kite,yahoo")                     # provider order; yahoo is always the last resort
QUOTE_POLL_SECONDS = int(os.getenv("QUOTE_POLL_SECONDS", "300"))             # live quote refresh during market hours
AUTO_SCHEDULE = os.getenv("AUTO_SCHEDULE", "0").lower() in ("1", "true", "yes")  # opt-in pre-market refresh + post-close analysis
CATALYST_AUTO_SCAN = os.getenv("CATALYST_AUTO_SCAN", "0").lower() in ("1", "true", "yes")  # scheduled NSE/BSE/PIB catalyst scan
CATALYST_POLL_SECONDS = int(os.getenv("CATALYST_POLL_SECONDS", "900"))  # 15 min default catalyst polling interval

# Target Symbols Config Files
SYMBOLS_FILE_PATH = os.path.join(os.path.dirname(__file__), "symbols.json")
ALL_NSE_SYMBOLS_FILE_PATH = os.path.join(os.path.dirname(__file__), "symbols_nse_all.json")
MIDCAP_250_SYMBOLS_FILE_PATH = os.path.join(os.path.dirname(__file__), "symbols_midcap_250.json")
# Full NSE master list (~2,400 stocks) - used ONLY for Add-Symbol search / sector lookup, never analysed in bulk.
# `symbols_nse_all.json` = Nifty 100 (large cap), `symbols_midcap_250.json` = Nifty Midcap 100 (see tools/refresh_index_universe.py)
NSE_CATALOG_FILE_PATH = os.path.join(os.path.dirname(__file__), "symbols_nse_catalog.json")
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "storage", "cache.db")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
HISTORICAL_EXCEL_PATH = os.path.join(REPORTS_DIR, "NSE_Historical_Data.xlsx")

# Label shown in the dashboard / reports for the analysis engine
ENGINE_LABEL = "Rule-based engine (no LLM)"
MODEL_VERSION = "2.1.0"
