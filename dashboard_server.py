"""
Real-Time Web Dashboard Server for NSE Multi-Agent Stock Predictor.
Serves a rich glassmorphism UI at http://localhost:8765 and exposes real-time JSON API endpoints.
Reads directly from SQLite (storage/cache.db) and Valkey queue.
"""

import http.server
import socketserver
import json
import math
import os
import sys
import time
import urllib.parse
from collections import OrderedDict
from datetime import datetime, timedelta
import threading

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import (ENGINE_LABEL, SYMBOLS_FILE_PATH, CACHE_DB_PATH, MAX_CONCURRENT_TRIGGERS, DASHBOARD_HOST,
                    QUOTE_SOURCES, QUOTE_POLL_SECONDS, AUTO_SCHEDULE, MAX_SYMBOL_WORKERS)
from storage.cache_manager import CacheManager
from storage.queue_manager import ValkeyQueueManager
from graph import MultiAgentWorkflow
from tools.historical_data_tools import HistoricalDataEngine
from tools.tech_tools import TechnicalAnalysisEngine
from tools.events_tools import EventsEngine
from tools.long_term_strategy import long_term_engine
from tools import market_calendar
from tools.quote_tools import QuoteService, QuotePoller, build_quotes_response, build_price_info
from tools.web_security import (LOOPBACK_NAMES, valid_symbol, host_header_ok, post_guard_error,
                                resolve_within)
from tools.outcome_tracker import compute_accuracy
from tools.scheduler import Scheduler
from tools.symbol_search_tools import search_internet_symbols, add_symbol_to_json, remove_symbol_from_json
from agents.macro_sentinel import BackgroundMacroSentinel
from api.services import (
    safe_json_dumps, get_all_stock_data, get_stocks_response_body, get_history_response_body,
    get_top_pattern_picks, get_pre_breakout_projections, _load_symbols_list, load_active_monitored_symbols, NaNSafeEncoder,
    SYNTH_AGENT, TECH_AGENT, HIST_AGENT, NEWS_AGENT, RISK_AGENT, FUND_AGENT, STALE_SYNTH_HOURS,
    STOCKS_CACHE_SECONDS, _stocks_lock, _stocks_cache, _pattern_memo
)
from tools import events_bus

PORT = int(os.getenv("DASHBOARD_PORT", "8765"))
cache_mgr = CacheManager()
queue_mgr = ValkeyQueueManager()
hist_engine = HistoricalDataEngine(cache_manager=cache_mgr)
tech_engine = TechnicalAnalysisEngine(rag_engine=hist_engine, cache_manager=cache_mgr)
events_engine = EventsEngine(cache_manager=cache_mgr)
quote_service = QuoteService(cache_mgr, sources=QUOTE_SOURCES)
quote_poller = QuotePoller(
    quote_service,
    symbols_loader=lambda: [x["symbol"] for x in load_active_monitored_symbols()],
    poll_seconds=QUOTE_POLL_SECONDS,
)
_workflow_instance = None

def get_workflow():
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = MultiAgentWorkflow(cache_mgr)
    return _workflow_instance

# --------------------------------------------------------------------------------------------- request security
ENFORCE_HOST_CHECK = DASHBOARD_HOST in LOOPBACK_NAMES      # blocks DNS-rebinding when bound to loopback only
MAX_BODY_BYTES = 64 * 1024
_REPORT_DIRS = ("news_reports", "reports")


# /api/trigger: bounded number of concurrent single-stock analyses, one per symbol at a time
_trigger_slots = threading.BoundedSemaphore(MAX_CONCURRENT_TRIGGERS)
_running_symbols = set()
_running_lock = threading.Lock()


def generate_markdown_viewer_html(title: str, md_content: str, raw_url: str) -> str:
    safe_md = md_content.replace("</script>", "<\\/script>")
    template = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{{TITLE}} | NSE Multi-Agent System</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <style>
    :root {
      --bg-dark: #090d16;
      --bg-card: rgba(18, 26, 43, 0.75);
      --border-card: rgba(255, 255, 255, 0.08);
      --border-glow: rgba(56, 189, 248, 0.3);
      --accent-blue: #38bdf8;
      --accent-green: #10b981;
      --accent-purple: #8b5cf6;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body {
      background-color: var(--bg-dark);
      background-image: 
        radial-gradient(at 10% 10%, rgba(56, 189, 248, 0.06) 0px, transparent 50%),
        radial-gradient(at 90% 90%, rgba(139, 92, 246, 0.06) 0px, transparent 50%);
      color: var(--text-main);
      min-height: 100vh;
      line-height: 1.6;
    }
    .top-bar {
      position: sticky; top: 0; z-index: 100;
      background: rgba(10, 15, 26, 0.92);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border-card);
      padding: 14px 28px;
      display: flex; justify-content: space-between; align-items: center;
    }
    .bar-left { display: flex; align-items: center; gap: 14px; }
    .doc-icon {
      width: 38px; height: 38px; border-radius: 10px;
      background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
      display: flex; align-items: center; justify-content: center;
      font-weight: 700; font-size: 1.2rem;
    }
    .doc-title { font-family: 'Outfit', sans-serif; font-size: 1.15rem; font-weight: 700; color: #fff; }
    .doc-badge {
      background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent-blue); padding: 4px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600;
    }
    .bar-actions { display: flex; gap: 10px; }
    .btn {
      background: rgba(255, 255, 255, 0.06); border: 1px solid var(--border-card);
      color: #e5e7eb; padding: 7px 14px; border-radius: 8px; font-size: 0.85rem; font-weight: 500;
      text-decoration: none; cursor: pointer; transition: all 0.2s; display: inline-flex; align-items: center; gap: 6px;
    }
    .btn:hover { background: rgba(255, 255, 255, 0.12); border-color: var(--border-glow); color: #fff; transform: translateY(-1px); }
    .btn-primary { background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple)); color: #fff; border: none; font-weight: 600; }
    .btn-primary:hover { opacity: 0.95; }
    
    .content-container { max-width: 1060px; margin: 32px auto; padding: 0 24px; }
    .markdown-card {
      background: var(--bg-card);
      border: 1px solid var(--border-card);
      border-radius: 20px;
      padding: 40px;
      backdrop-filter: blur(12px);
      box-shadow: 0 16px 40px rgba(0, 0, 0, 0.3);
    }
    .markdown-body h1, .markdown-body h2, .markdown-body h3 {
      font-family: 'Outfit', sans-serif; color: #fff; margin-top: 1.6em; margin-bottom: 0.6em;
    }
    .markdown-body h1 { font-size: 1.8rem; border-bottom: 1px solid var(--border-card); padding-bottom: 0.4em; }
    .markdown-body h2 { font-size: 1.4rem; color: var(--accent-blue); }
    .markdown-body h3 { font-size: 1.15rem; color: #e2e8f0; }
    .markdown-body p { margin-bottom: 1em; color: #d1d5db; }
    .markdown-body hr { border: none; border-top: 1px solid var(--border-card); margin: 24px 0; }
    .markdown-body blockquote {
      border-left: 4px solid var(--accent-blue);
      background: rgba(56, 189, 248, 0.08);
      padding: 12px 18px; margin: 16px 0; border-radius: 0 10px 10px 0; color: #cbd5e1;
    }
    .markdown-body table {
      width: 100%; border-collapse: separate; border-spacing: 0; margin: 20px 0;
      border: 1px solid var(--border-card); border-radius: 12px; overflow: hidden;
      background: rgba(0, 0, 0, 0.2);
    }
    .markdown-body th, .markdown-body td {
      padding: 12px 16px; text-align: left; border-bottom: 1px solid var(--border-card);
    }
    .markdown-body th {
      background: rgba(15, 23, 42, 0.85); font-weight: 600; color: #93c5fd; font-size: 0.88rem;
    }
    .markdown-body tr:last-child td { border-bottom: none; }
    .markdown-body tr:hover td { background: rgba(255, 255, 255, 0.03); }
    .markdown-body a {
      color: var(--accent-blue); text-decoration: none; border-bottom: 1px dotted var(--accent-blue);
      transition: color 0.2s;
    }
    .markdown-body a:hover { color: #93c5fd; border-bottom-style: solid; }
    .markdown-body code {
      font-family: 'JetBrains Mono', monospace; font-size: 0.88em;
      background: rgba(0, 0, 0, 0.4); padding: 2px 6px; border-radius: 4px; color: #38bdf8;
    }
    .markdown-body pre {
      background: #0d1117; padding: 16px; border-radius: 10px; overflow-x: auto; margin: 16px 0;
      border: 1px solid var(--border-card);
    }
    .markdown-body pre code { background: none; padding: 0; color: #e6edf3; }
    .markdown-body ul, .markdown-body ol { padding-left: 24px; margin-bottom: 16px; color: #d1d5db; }
    .markdown-body li { margin-bottom: 6px; }
    
    #rawView {
      display: none; white-space: pre-wrap; font-family: 'JetBrains Mono', monospace;
      font-size: 0.88rem; background: #0b0f19; padding: 24px; border-radius: 12px;
      border: 1px solid var(--border-card); color: #d1d5db; line-height: 1.5;
    }
  </style>
</head>
<body>
  <div class="top-bar">
    <div class="bar-left">
      <div class="doc-icon">📄</div>
      <div>
        <div class="doc-title">{{TITLE}}</div>
      </div>
      <span class="doc-badge">Markdown Document</span>
    </div>
    <div class="bar-actions">
      <button class="btn" onclick="toggleRawView()" id="toggleBtn">📝 View Raw</button>
      <a href="{{RAW_URL}}?raw=1" download class="btn">⬇️ Download</a>
      <a href="/" class="btn btn-primary">📊 Dashboard</a>
    </div>
  </div>

  <div class="content-container">
    <div class="markdown-card">
      <div id="renderedView" class="markdown-body"></div>
      <div id="rawView"></div>
    </div>
  </div>

  <script id="rawMarkdownContent" type="text/markdown">{{CONTENT}}</script>
  <script>
    const rawContent = document.getElementById('rawMarkdownContent').textContent;
    document.getElementById('rawView').textContent = rawContent;
    
    if (window.marked) {
      marked.setOptions({ gfm: true, breaks: true });
      document.getElementById('renderedView').innerHTML = marked.parse(rawContent);
      document.querySelectorAll('#renderedView a').forEach(a => {
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
      });
    } else {
      document.getElementById('renderedView').style.display = 'none';
      document.getElementById('rawView').style.display = 'block';
    }

    let isRaw = false;
    function toggleRawView() {
      isRaw = !isRaw;
      document.getElementById('renderedView').style.display = isRaw ? 'none' : 'block';
      document.getElementById('rawView').style.display = isRaw ? 'block' : 'none';
      document.getElementById('toggleBtn').innerText = isRaw ? '👁️ Formatted View' : '📝 View Raw';
    }
  </script>
</body>
</html>"""
    return template.replace("{{TITLE}}", title).replace("{{RAW_URL}}", raw_url).replace("{{CONTENT}}", safe_md)

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def _send_json(self, code: int, obj, cors: bool = False):
        body = obj if isinstance(obj, (bytes, bytearray)) else safe_json_dumps(obj)
        self.send_response(code)
        self.send_header("Content-type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self) -> bool:
        if host_header_ok(self.headers.get("Host"), ENFORCE_HOST_CHECK):
            return True
        self.send_error(403, "Forbidden host")
        return False

    def do_OPTIONS(self):
        # No CORS: this dashboard is same-origin only, so cross-site preflights are refused
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if not self._host_ok():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/api/status":
            try:
                q_status = queue_mgr.get_queue_status()
                shared_bulletin = cache_mgr.get_latest_market_bulletin()
                macro_items = cache_mgr.get_cached_macro(max_age_hours=24)

                resp_data = {
                    "model": ENGINE_LABEL,
                    "timestamp": datetime.now().isoformat(),
                    "queue_status": q_status,
                    "bulletin": shared_bulletin,
                    "macro_items": macro_items
                }
                body = safe_json_dumps(resp_data)
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                err_body = safe_json_dumps({"error": str(e)})
                self.send_response(500)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(err_body)))
                self.end_headers()
                self.wfile.write(err_body)
            return

        elif path == "/api/stocks":
            try:
                query = urllib.parse.parse_qs(parsed_path.query)
                universe = query.get("universe", ["curated"])[0].lower().strip()
                if universe not in ("curated", "midcap250", "all_nse"):
                    universe = "curated"
                self._send_json(200, get_stocks_response_body(cache_mgr, queue_mgr, hist_engine, tech_engine, events_engine, universe=universe))
            except Exception as e:
                self._send_json(500, {"error": str(e), "stocks": []}, cors=False)
            return

        elif path == "/api/quotes":
            try:
                self._send_json(200, build_quotes_response(cache_mgr, quote_poller))
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        elif path == "/api/accuracy":
            try:
                self._send_json(200, compute_accuracy(cache_mgr))
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        elif path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return

        elif path.startswith("/api/history"):
            query = urllib.parse.parse_qs(parsed_path.query)
            sym = query.get("symbol", [""])[0].upper().strip()
            if not sym:
                self._send_json(400, {"error": "Missing symbol", "candles": []})
                return
            if not valid_symbol(sym):
                self._send_json(400, {"error": "Invalid symbol", "candles": []})
                return
            raw_days = query.get("days", ["365"])[0]
            try:
                days = int(''.join(c for c in str(raw_days) if c.isdigit())) or 365
            except Exception:
                days = 365
            interval = query.get("interval", ["1d"])[0].strip() or "1d"

            try:
                body = get_history_response_body(sym, days, cache_mgr, tech_engine, interval=interval)
                self._send_json(200, body)
            except Exception as e:
                print(f"Error fetching chart data for {sym}: {e}", flush=True)
                self._send_json(500, {"symbol": sym, "candles": [], "error": str(e)})
            return

        elif path.startswith("/api/events"):
            query = urllib.parse.parse_qs(parsed_path.query)
            sym = query.get("symbol", [""])[0].upper().strip()
            if sym and not valid_symbol(sym):
                self._send_json(400, {"error": "Invalid symbol"})
                return

            events_data = events_engine.fetch_stock_events(sym) if sym else {"upcoming_macro_catalysts": events_engine.get_upcoming_macro_events()}
            body = safe_json_dumps(events_data)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        elif path.startswith("/api/search-symbol"):
            query = urllib.parse.parse_qs(parsed_path.query)
            q_str = query.get("q", [""])[0].strip()
            matches = search_internet_symbols(q_str)
            body = safe_json_dumps({"query": q_str, "results": matches})
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        elif path.startswith("/api/portfolio"):
            try:
                from tools.kite_portfolio import KitePortfolioEngine
                port_engine = KitePortfolioEngine(cache_manager=cache_mgr)
                data = port_engine.evaluate_portfolio()
                self._send_json(200, safe_json_dumps(data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "summary": {}, "holdings": []})
            return

        elif path.startswith("/api/fundamental-picks"):
            try:
                from api.services import get_fundamental_picks_data
                query = urllib.parse.parse_qs(parsed_path.query)
                universe = query.get("universe", ["curated"])[0].lower().strip()
                data = get_fundamental_picks_data(cache_mgr, universe=universe)
                self._send_json(200, safe_json_dumps(data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "picks": [], "count": 0})
            return

        elif path.startswith("/api/macro-risk-shield"):
            try:
                from tools.macro_tools import GlobalMacroEngine, compute_macro_sentiment
                from tools.macro_risk_shield import build_macro_risk_shield
                from tools.kite_portfolio import KitePortfolioEngine

                macro_engine = GlobalMacroEngine(cache_mgr)
                macro_res = macro_engine.fetch_macro_indicators(max_age_hours=12)
                indicators = macro_res.get("indicators", [])
                sentiment = compute_macro_sentiment(indicators)

                holdings = []
                try:
                    port_engine = KitePortfolioEngine(cache_manager=cache_mgr)
                    port_data = port_engine.evaluate_portfolio()
                    holdings = port_data.get("holdings", [])
                except Exception:
                    pass

                shield_data = build_macro_risk_shield(sentiment, holdings)
                self._send_json(200, safe_json_dumps(shield_data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "risk_key": "UNAVAILABLE", "risk_label": "⚪ UNAVAILABLE"})
            return

        elif path.startswith("/api/company/"):
            ticker = path.split("/api/company/")[1].split("/")[0].split("?")[0].upper().strip()
            if not ticker or not valid_symbol(ticker):
                self._send_json(400, {"error": "Invalid ticker"})
                return
            try:
                from tools.forensic_financial_engine import ForensicFinancialEngine
                forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
                analysis = forensic_engine.analyze_company(ticker)
                gov = analysis.get("governance_telemetry", {})
                eq = analysis.get("earnings_quality", {})

                exc_amt = eq.get("exceptional_items")
                exc_items = [
                    {
                        "description": "Exceptional Items",
                        "amount": exc_amt,
                        "type": "income" if exc_amt >= 0 else "expense",
                        "category": "Other",
                    }
                ] if (exc_amt is not None and exc_amt != 0.0) else []

                company_data = {
                    "ticker": ticker,
                    "exchange": "NSE",
                    "name": analysis.get("company_name", ticker),
                    "sector": analysis.get("sector", "N/A"),
                    "promoterHoldingPct": gov.get("promoter_holding_pct"),
                    "promoterPledgePct": gov.get("promoter_pledge_pct"),
                    "auditRiskScore": gov.get("audit_risk_score"),
                    "governanceGrade": gov.get("governance_grade", "UNAUDITED"),
                    "earningsQuality": {
                        "reportedPAT": eq.get("reported_pat"),
                        "adjustedPAT": eq.get("adjusted_pat"),
                        "sustainablePAT": eq.get("sustainable_pat"),
                        "exceptionalItems": exc_items,
                        "redFlag": eq.get("quality_grade") in ("SEVERELY_DISTORTED", "MODERATELY_DISTORTED")
                    },
                    "forensicAnalysis": analysis
                }
                self._send_json(200, safe_json_dumps(company_data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "ticker": ticker})
            return

        elif path.startswith("/api/earnings/"):
            ticker = path.split("/api/earnings/")[1].split("/")[0].split("?")[0].upper().strip()
            if not ticker or not valid_symbol(ticker):
                self._send_json(400, {"error": "Invalid ticker"})
                return
            try:
                from tools.forensic_financial_engine import ForensicFinancialEngine
                forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
                analysis = forensic_engine.analyze_company(ticker)
                eq = analysis.get("earnings_quality", {})
                exc_amt = eq.get("exceptional_items")
                earnings_data = {
                    "reportedPAT": eq.get("reported_pat"),
                    "adjustedPAT": eq.get("adjusted_pat"),
                    "sustainablePAT": eq.get("sustainable_pat"),
                    "exceptionalItems": [
                        {
                            "description": "Exceptional Items",
                            "amount": exc_amt,
                            "type": "income" if exc_amt >= 0 else "expense",
                            "category": "Other"
                        }
                    ] if (exc_amt is not None and exc_amt != 0.0) else []
                }
                self._send_json(200, safe_json_dumps(earnings_data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "ticker": ticker})
            return

        elif path == "/api/catalysts/early-warning":
            query = urllib.parse.parse_qs(parsed_path.query)
            tier = query.get("tier", [""])[0].strip() or None
            sym = query.get("symbol", [""])[0].strip() or None
            try:
                limit = int(query.get("limit", ["100"])[0])
            except Exception:
                limit = 100
            try:
                events = cache_mgr.get_catalyst_events(symbol=sym, tier=tier, limit=limit)
                self._send_json(200, {"events": events, "count": len(events)})
            except Exception as e:
                self._send_json(500, {"error": str(e), "events": []})
            return

        elif path == "/api/catalysts/backtest":
            try:
                from tools.catalyst_backtest import run_catalyst_backtest
                self._send_json(200, run_catalyst_backtest(cache_manager=cache_mgr))
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return

        elif path == "/api/sector-research":
            try:
                runs = cache_mgr.list_sector_research_runs()
                self._send_json(200, {"runs": runs})
            except Exception as e:
                self._send_json(500, {"error": str(e), "runs": []})
            return

        elif path.startswith("/api/sector-research/"):
            raw_id = path.split("/api/sector-research/")[1].split("/")[0].split("?")[0].strip()
            try:
                run_id = int(raw_id)
            except ValueError:
                self._send_json(400, {"error": "Invalid run ID"})
                return
            run = cache_mgr.get_sector_research_run(run_id)
            if not run:
                self._send_json(404, {"error": "Sector research run not found"})
                return
            self._send_json(200, run)
            return

        elif path.startswith("/api/financial/"):
            parts = path.split("/api/financial/")[1].split("/")
            ticker = parts[0].split("?")[0].upper().strip() if len(parts) > 0 else ""
            statement_type = parts[1].split("?")[0].lower().strip() if len(parts) > 1 else "income"
            if not ticker or not valid_symbol(ticker):
                self._send_json(400, {"error": "Invalid ticker"})
                return
            try:
                from tools.forensic_financial_engine import ForensicFinancialEngine
                forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
                analysis = forensic_engine.analyze_company(ticker)
                eq = analysis.get("earnings_quality", {})
                cf = analysis.get("cash_conversion", {})
                solv = analysis.get("solvency_health", {})

                if statement_type == "balance":
                    statements = [{
                        "period": "LTM",
                        "totalDebt": solv.get("total_debt"),
                        "totalCash": solv.get("total_cash"),
                        "netDebt": solv.get("net_debt"),
                        "currentRatio": solv.get("current_ratio"),
                        "debtToEquity": solv.get("debt_to_equity")
                    }]
                elif statement_type == "cashflow":
                    statements = [{
                        "period": "LTM",
                        "cashFromOperations": cf.get("cfo"),
                        "capitalExpenditure": cf.get("capex"),
                        "freeCashFlow": cf.get("fcf"),
                        "cfoToPatRatio": cf.get("cfo_to_pat_ratio")
                    }]
                else:  # income
                    statements = [{
                        "period": "LTM",
                        "revenue": eq.get("revenue"),
                        "revenueGrowthPct": cf.get("revenue_growth_pct"),
                        "reportedPAT": eq.get("reported_pat"),
                        "exceptionalItems": eq.get("exceptional_items"),
                        "sustainablePAT": eq.get("sustainable_pat")
                    }]
                self._send_json(200, safe_json_dumps(statements))
            except Exception as e:
                self._send_json(500, {"error": str(e), "ticker": ticker})
            return

        elif path.startswith("/api/forensic-recommendation") or path.startswith("/api/recommendation"):
            query = urllib.parse.parse_qs(parsed_path.query)
            sym = query.get("symbol", [""])[0].upper().strip()
            if not sym or not valid_symbol(sym):
                self._send_json(400, {"error": "Missing or invalid symbol"})
                return

            price_str = query.get("price", [""])[0].strip()
            price_val = None
            try:
                if price_str:
                    price_val = float(price_str)
            except Exception:
                pass

            try:
                from tools.forensic_financial_engine import ForensicFinancialEngine
                forensic_engine = ForensicFinancialEngine(cache_manager=cache_mgr)
                data = forensic_engine.analyze_company(sym, price_override=price_val)
                self._send_json(200, safe_json_dumps(data))
            except Exception as e:
                self._send_json(500, {"error": str(e), "symbol": sym, "verdict": "ERROR"})
            return

        elif path.startswith("/api/market-scanner"):
            try:
                from tools.market_scanner import get_latest_cached_scan, run_market_scan
                cached = get_latest_cached_scan()
                if not cached.get("stocks"):
                    threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 25, "top_n": 10}, daemon=True).start()
                self._send_json(200, safe_json_dumps(cached))
            except Exception as e:
                self._send_json(500, {"error": str(e), "stocks": []})
            return

        elif path == "/api/patterns/top" or path == "/api/pattern-screener":
            try:
                query = urllib.parse.parse_qs(parsed_path.query)
                try:
                    min_upside = float(query.get("min_upside", ["0"])[0])
                except (ValueError, TypeError):
                    min_upside = 0.0
                picks = get_top_pattern_picks(cache_mgr, tech_engine, min_upside=min_upside)
                self._send_json(200, safe_json_dumps({"count": len(picks), "picks": picks}))
            except Exception as e:
                self._send_json(500, {"error": str(e), "picks": []})
            return

        elif path == "/api/patterns/pre-breakout":
            try:
                query = urllib.parse.parse_qs(parsed_path.query)
                universe = str(query.get("universe", ["monitored"])[0]).lower().strip()
                if universe not in ("monitored", "curated", "midcap250", "all_nse", "all"):
                    universe = "monitored"
                include_fresh = str(query.get("include_fresh", ["1"])[0]).strip() not in ("0", "false", "no")
                high_conviction = str(query.get("high_conviction", ["1"])[0]).strip() not in ("0", "false", "no")
                try:
                    limit = max(1, min(int(query.get("limit", ["60"])[0]), 200))
                except (ValueError, TypeError):
                    limit = 60
                payload = get_pre_breakout_projections(
                    cache_mgr,
                    tech_engine,
                    universe=universe,
                    include_fresh=include_fresh,
                    limit=limit,
                    high_conviction_only=high_conviction,
                )
                self._send_json(200, safe_json_dumps(payload))
            except Exception as e:
                self._send_json(500, {"error": str(e), "count": 0, "picks": []})
            return

        elif path == "/" or path == "/index.html":
            # UI has been replaced by the Angular application.
            # The backend now only serves API endpoints.
            # Return 404 for the legacy dashboard page.
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Dashboard UI removed. Use the Angular frontend.")
            return

        elif path.startswith("/news_reports/") or path.startswith("/reports/") or path.startswith("/news/"):
            # Normalize path and map aliases
            norm_path = path
            if path.startswith("/news/"):
                norm_path = "/news_reports/" + path[len("/news/"):]

            rel_path = norm_path.lstrip("/")
            top_dir, _, inner_path = rel_path.partition("/")
            target_file = None
            if top_dir in _REPORT_DIRS and inner_path:
                target_file = resolve_within(os.path.join(PROJECT_ROOT, top_dir), inner_path)

            if target_file:
                query = urllib.parse.parse_qs(parsed_path.query)
                is_raw = query.get("raw", ["0"])[0] == "1"
                accept_header = self.headers.get("Accept", "")

                if target_file.endswith(".md") and not is_raw and "text/html" in accept_header:
                    self.send_response(200)
                    self.send_header("Content-type", "text/html; charset=utf-8")
                    self.end_headers()
                    with open(target_file, "r", encoding="utf-8", errors="replace") as f:
                        md_content = f.read()
                    html_view = generate_markdown_viewer_html(os.path.basename(target_file), md_content, path)
                    self.wfile.write(html_view.encode("utf-8"))
                    return
                else:
                    self.send_response(200)
                    if target_file.endswith(".md"):
                        self.send_header("Content-type", "text/plain; charset=utf-8")
                    elif target_file.endswith(".json"):
                        self.send_header("Content-type", "application/json; charset=utf-8")
                    else:
                        self.send_header("Content-type", "application/octet-stream")
                    self.end_headers()
                    with open(target_file, "rb") as f:
                        self.wfile.write(f.read())
                    return
            else:
                self.send_error(404, "File Not Found")
                return

        else:
            # Serve static files if exist
            static_filepath = resolve_within(os.path.join(PROJECT_ROOT, "static"), path)
            if static_filepath:
                self.send_response(200)
                if path.endswith(".css"):
                    self.send_header("Content-type", "text/css")
                elif path.endswith(".js"):
                    self.send_header("Content-type", "application/javascript")
                self.end_headers()
                with open(static_filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "File Not Found")

    def _read_json_body(self):
        """Parsed JSON object from the request body, or None (a 400 has then already been sent)."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("body size")
            data = json.loads(self.rfile.read(length).decode('utf-8')) if length else {}
            if not isinstance(data, dict):
                raise ValueError("body must be a JSON object")
            return data
        except Exception:
            self._send_json(400, {"status": "error", "message": "Invalid request body"})
            return None

    def do_POST(self):
        if not self._host_ok():
            return
        parsed_path = urllib.parse.urlparse(self.path)
        guard = post_guard_error(self.headers)
        if guard:
            self._send_json(guard[0], {"status": "error", "message": guard[1]})
            return
        if parsed_path.path == "/api/trigger":
            req_data = self._read_json_body()
            if req_data is None:
                return
            symbol = str(req_data.get("symbol", "")).upper().strip()
            if not symbol:
                self._send_json(400, {"status": "error", "message": "Missing symbol"}, cors=False)
                return
            if not valid_symbol(symbol):
                self._send_json(400, {"status": "error", "message": "Invalid symbol"}, cors=False)
                return

            # Find company name and sector
            c_name, c_sec = "", ""
            for s_item in _load_symbols_list():
                if s_item.get("symbol", "").upper() == symbol:
                    c_name = s_item.get("name", "")
                    c_sec = s_item.get("sector", "")
                    break

            with _running_lock:
                if symbol in _running_symbols:
                    self._send_json(200, {"status": "already_running", "symbol": symbol,
                                          "message": f"{symbol} is already being analyzed."}, cors=False)
                    return
                if not _trigger_slots.acquire(blocking=False):
                    self._send_json(429, {"status": "busy", "symbol": symbol,
                                          "message": f"{MAX_CONCURRENT_TRIGGERS} analyses are already running. Try again shortly."}, cors=False)
                    return
                _running_symbols.add(symbol)

            def run_single():
                try:
                    with cache_mgr._get_connection() as conn:
                        conn.execute("UPDATE persistent_stock_queue SET status = 'in_progress' WHERE symbol = ?", (symbol,))
                    try:
                        get_workflow().run_analysis(symbol, company_name=c_name, sector=c_sec, force_refresh=True)
                        queue_mgr.mark_completed(symbol)
                        # Publish analysis completion event for WebSocket broadcast
                        events_bus.publish(events_bus.ANALYSIS_DONE, {
                            "symbol": symbol,
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception as e:
                        print(f"⚠️ Error in single stock analysis for {symbol}: {e}")
                        with cache_mgr._get_connection() as conn:
                            conn.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE symbol = ?", (symbol,))
                finally:
                    with _running_lock:
                        _running_symbols.discard(symbol)
                    _trigger_slots.release()

            threading.Thread(target=run_single, daemon=True).start()

            self._send_json(200, {"status": "triggered", "symbol": symbol}, cors=False)
            return

        elif parsed_path.path == "/api/add-symbol":
            req_data = self._read_json_body()
            if req_data is None:
                return
            sym = str(req_data.get("symbol", "")).upper().strip()
            name = str(req_data.get("name", "")).strip()[:120]
            sector = str(req_data.get("sector", "")).strip()[:80]
            exchange = str(req_data.get("exchange", "NSE")).strip()[:10]
            if not valid_symbol(sym):
                self._send_json(400, {"status": "error", "message": "Invalid symbol"})
                return

            self._send_json(200, add_symbol_to_json(symbol=sym, name=name, sector=sector, exchange=exchange, queue_manager=queue_mgr))
            return

        elif parsed_path.path == "/api/remove-symbol":
            req_data = self._read_json_body()
            if req_data is None:
                return
            sym = str(req_data.get("symbol", "")).upper().strip()
            if not valid_symbol(sym):
                self._send_json(400, {"status": "error", "message": "Invalid symbol"})
                return

            self._send_json(200, remove_symbol_from_json(symbol=sym))
            return

        elif parsed_path.path == "/api/market-scanner/scan":
            try:
                from tools.market_scanner import run_market_scan
                threading.Thread(target=run_market_scan, kwargs={"max_scan_count": 50, "top_n": 15}, daemon=True).start()
                self._send_json(200, {"status": "triggered", "message": "Market scan started in background"})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        elif parsed_path.path == "/api/catalysts/scan":
            try:
                from tools.catalyst_scanner import CatalystScannerEngine
                engine = CatalystScannerEngine(cache_manager=cache_mgr)
                self._send_json(200, engine.run_live_scan())
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        elif parsed_path.path == "/api/catalysts/analyze":
            req_data = self._read_json_body()
            if req_data is None:
                return
            sym = str(req_data.get("symbol", "")).upper().strip()
            title = str(req_data.get("title", "")).strip()
            if not sym or not valid_symbol(sym) or not title:
                self._send_json(400, {"status": "error", "message": "Valid symbol and title are required"})
                return
            try:
                from tools.catalyst_scanner import CatalystScannerEngine
                engine = CatalystScannerEngine(cache_manager=cache_mgr)
                ev = engine.analyze_and_save_event(
                    symbol=sym,
                    title=title,
                    summary=str(req_data.get("summary", "")),
                    source=str(req_data.get("source", "NSE")),
                    company_name=str(req_data.get("company_name", "")),
                    announced_at=str(req_data.get("announced_at", "")),
                    deal_value_cr=req_data.get("deal_value_cr"),
                    annual_revenue_cr=req_data.get("annual_revenue_cr"),
                )
                self._send_json(200, ev)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        elif parsed_path.path == "/api/sector-research":
            req_data = self._read_json_body()
            if req_data is None:
                return
            sector_query = str(req_data.get("sector", "")).strip()
            if not sector_query or len(sector_query) > 200:
                self._send_json(400, {"status": "error", "message": "Provide a valid sector query (1-200 chars)"})
                return
            use_search = bool(req_data.get("use_search", False))
            force_refresh = bool(req_data.get("force_refresh", False))
            try:
                from tools.sector_research_engine import SectorResearchEngine
                engine = SectorResearchEngine(cache_manager=cache_mgr)
                result = engine.run_research(sector_query, use_search=use_search, force_refresh=force_refresh)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        elif parsed_path.path.startswith("/api/sector-research/"):
            rest = parsed_path.path.split("/api/sector-research/")[1].strip("/")
            parts = rest.split("/")
            try:
                run_id = int(parts[0])
            except (ValueError, IndexError):
                self._send_json(400, {"status": "error", "message": "Invalid run ID"})
                return
            action = parts[1] if len(parts) > 1 else ""
            if action == "rescore":
                try:
                    from tools.sector_research_engine import SectorResearchEngine
                    engine = SectorResearchEngine(cache_manager=cache_mgr)
                    result = engine.rescore_run(run_id)
                    if not result:
                        self._send_json(404, {"status": "error", "message": "Sector research run not found"})
                        return
                    self._send_json(200, result)
                except Exception as e:
                    self._send_json(500, {"status": "error", "message": str(e)})
                return
            elif action == "delete":
                if not cache_mgr.delete_sector_research_run(run_id):
                    self._send_json(404, {"status": "error", "message": "Sector research run not found"})
                    return
                self._send_json(200, {"status": "deleted", "id": run_id})
                return

        self._send_json(404, {"status": "error", "message": "Unknown endpoint"})

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = sys.platform != "win32"

def open_browser_delayed(url: str, delay: float = 0.5):
    def _open():
        import time
        time.sleep(delay)
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass
    threading.Thread(target=_open, daemon=True).start()

def start_dashboard_server(port=None, open_browser=True):
    if port is None:
        port = PORT
    os.makedirs(os.path.join(PROJECT_ROOT, "static"), exist_ok=True)
    quote_poller.start()
    if AUTO_SCHEDULE:
        Scheduler(
            cache_mgr,
            workflow_getter=get_workflow,
            symbols_loader=load_active_monitored_symbols,
            max_workers=MAX_SYMBOL_WORKERS,
            on_symbol_done=queue_mgr.mark_completed,
        ).start()
        BackgroundMacroSentinel(cache_mgr).start()
        print("🗓️ [Scheduler] Auto-schedule ON (pre-market refresh 08:45 IST, post-close analysis 16:00 IST) + MacroSentinel. "
              "Disable with AUTO_SCHEDULE=0.", flush=True)
    for p in [port, port + 1, port + 2]:
        try:
            with ThreadedTCPServer((DASHBOARD_HOST, p), DashboardHandler) as httpd:
                server_url = f"http://localhost:{p}"
                frontend_url = os.getenv("FRONTEND_URL", "http://localhost:4200")
                print(f"🌐 [Realtime Dashboard Server] API running live at {server_url} | Angular UI: {frontend_url}", flush=True)
                if open_browser:
                    open_browser_delayed(frontend_url, delay=0.5)
                httpd.serve_forever()
                break
        except OSError:
            continue

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Real-Time Dashboard Server for NSE Stock Predictor")
    parser.add_argument("--port", type=int, default=PORT, help="Port to run the dashboard server on")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the web browser")
    args, _ = parser.parse_known_args()
    start_dashboard_server(port=args.port, open_browser=not args.no_browser)
