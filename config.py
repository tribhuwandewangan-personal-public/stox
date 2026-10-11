"""
Configuration module for Ollama qwen2.5:7b local LLM and fallback models.
Zero-cost design: Uses local Ollama or Google Gemini Free Tier.
"""

import os
import sys
from typing import Optional

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

# Primary Local Ollama Model
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# Optional Fallback Model (Google Gemini Free Tier)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = "gemini-1.5-flash"

# Verbose & Execution Settings
VERBOSE_LOGGING = os.getenv("VERBOSE_LOGGING", "true").lower() in ("true", "1", "yes")
MAX_PARALLEL_WORKERS = int(os.getenv("MAX_PARALLEL_WORKERS", "6"))
MAX_SYMBOL_WORKERS = int(os.getenv("MAX_SYMBOL_WORKERS", "2"))

# Target Symbols Config File
SYMBOLS_FILE_PATH = os.path.join(os.path.dirname(__file__), "symbols.json")
CACHE_DB_PATH = os.path.join(os.path.dirname(__file__), "storage", "cache.db")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
HISTORICAL_EXCEL_PATH = os.path.join(REPORTS_DIR, "NSE_Historical_Data.xlsx")


def get_llm(model_name: Optional[str] = None, temperature: float = 0.2):
    """
    Instantiates and returns the configured LLM.
    Defaults to local Ollama qwen2.5:7b.
    Falls back to ChatGoogleGenerativeAI if Ollama fails or GEMINI_API_KEY is preferred.
    """
    target_model = model_name or OLLAMA_MODEL

    try:
        from langchain_ollama import ChatOllama
        return ChatOllama(
            base_url=OLLAMA_BASE_URL,
            model=target_model,
            temperature=temperature
        )
    except Exception as e:
        print(f"[Config Warning] Local Ollama ({target_model}) initialization notice: {e}")
        if GEMINI_API_KEY:
            print("[Config Info] Falling back to Google Gemini Free Tier model...")
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                google_api_key=GEMINI_API_KEY,
                temperature=temperature
            )
        raise e
