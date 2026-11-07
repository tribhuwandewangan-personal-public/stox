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
import urllib.parse
from datetime import datetime
import threading
import sqlite3


class NaNSafeEncoder(json.JSONEncoder):
    """
    JSON encoder that converts NaN/Infinity floats to null and handles numpy scalars.
    Python's json module emits bare NaN/Infinity by default, which is invalid JSON,
    and fails on numpy scalars like np.bool_. This encoder fixes that globally for the dashboard.
    """
    def iterencode(self, obj, _one_shot=False):
        # Pre-sanitize the object tree before encoding
        return super().iterencode(self._sanitize(obj), _one_shot)

    def _sanitize(self, obj):
        if hasattr(obj, 'item') and callable(obj.item):
            try:
                obj = obj.item()
            except Exception:
                pass

        if isinstance(obj, float):
            if math.isnan(obj) or math.isinf(obj):
                return None
            return obj
        elif isinstance(obj, dict):
            return {k: self._sanitize(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._sanitize(v) for v in obj]
        return obj

    def default(self, o):
        if hasattr(o, 'item') and callable(o.item):
            return o.item()
        if hasattr(o, '__bool__'):
            return bool(o)
        return str(o)

def safe_json_dumps(obj) -> bytes:
    """Serialize obj to JSON bytes, replacing NaN/Infinity with null."""
    return json.dumps(obj, cls=NaNSafeEncoder).encode("utf-8")

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import OLLAMA_MODEL, SYMBOLS_FILE_PATH, CACHE_DB_PATH
from storage.cache_manager import CacheManager
from storage.queue_manager import ValkeyQueueManager
from graph import MultiAgentWorkflow
from tools.historical_data_tools import HistoricalDataEngine
from tools.tech_tools import TechnicalAnalysisEngine
from tools.events_tools import EventsEngine
from tools.long_term_strategy import long_term_engine
from tools.symbol_search_tools import search_internet_symbols, add_symbol_to_json, remove_symbol_from_json

PORT = int(os.getenv("DASHBOARD_PORT", "8765"))
cache_mgr = CacheManager()
queue_mgr = ValkeyQueueManager()
hist_engine = HistoricalDataEngine(cache_manager=cache_mgr)
tech_engine = TechnicalAnalysisEngine(rag_engine=hist_engine, cache_manager=cache_mgr)
events_engine = EventsEngine(cache_manager=cache_mgr)
_workflow_instance = None

def get_workflow():
    global _workflow_instance
    if _workflow_instance is None:
        _workflow_instance = MultiAgentWorkflow(cache_mgr)
    return _workflow_instance

def get_all_stock_data():
    symbols_list = []
    if os.path.exists(SYMBOLS_FILE_PATH):
        with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            symbols_list = json.load(f).get("symbols", [])

    # Get live queue statuses from SQLite queue
    queue_statuses = queue_mgr.get_symbol_statuses()

    results = []
    for s in symbols_list:
        sym = s.get("symbol", "").upper()
        name = s.get("name", "")
        sector = s.get("sector", "")
        q_status = queue_statuses.get(sym, "pending")

        # Get latest synthesizer output: check fresh first (72h), then fall back to latest available
        synth_output = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=72)
        is_stale = False
        if not synth_output:
            synth_output = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=None)
            if synth_output:
                is_stale = True

        tech_output = cache_mgr.get_latest_agent_output(sym, "Technical Analysis Agent", max_age_hours=None)
        hist_output = cache_mgr.get_latest_agent_output(sym, "Historical Data RAG Agent", max_age_hours=None)
        news_output = cache_mgr.get_latest_agent_output(sym, "News & Sentiment Agent", max_age_hours=None)
        risk_output = cache_mgr.get_latest_agent_output(sym, "Risk & Volatility Agent", max_age_hours=None)
        fund_output = cache_mgr.get_latest_agent_output(sym, "Fundamental Analyst Agent", max_age_hours=None)

        # Get detected patterns
        patterns = []
        if tech_output and "detected_patterns" in tech_output:
            patterns = tech_output.get("detected_patterns", [])
        elif tech_output and "raw_indicators" in tech_output and "detected_patterns" in tech_output["raw_indicators"]:
            patterns = tech_output["raw_indicators"].get("detected_patterns", [])
        else:
            try:
                patterns = tech_engine.detect_chart_patterns(hist_engine.load_symbol_history(sym, limit_days=90))
            except Exception:
                patterns = []

        # Get upcoming events
        events = {}
        if fund_output and "upcoming_events" in fund_output:
            events = fund_output.get("upcoming_events", {})
        else:
            try:
                events = events_engine.fetch_stock_events(sym)
            except Exception:
                events = {}

        # Quick sparkline data for inline visual chart (last 25 candles)
        sparkline = []
        try:
            cached_candles = cache_mgr.get_cached_candles(sym, limit_days=25)
            sparkline = [round(float(c.get("CLOSE_PRICE", 0)), 2) for c in cached_candles]
        except Exception:
            sparkline = []

        # Compute Long-Term Strategy & Multi-Year Compounder Evaluation
        last_price = 100.0
        if tech_output and "raw_indicators" in tech_output and tech_output["raw_indicators"].get("last_price"):
            last_price = float(tech_output["raw_indicators"]["last_price"])
        elif sparkline:
            last_price = float(sparkline[-1])

        short_verdict = "HOLD"
        if synth_output and "structured_signal" in synth_output:
            short_verdict = synth_output["structured_signal"].get("action_verdict", "HOLD")

        long_term_signal = long_term_engine.evaluate_long_term_stock(
            symbol=sym,
            name=name,
            sector=sector,
            last_price=last_price,
            short_verdict=short_verdict
        )

        # Enrich structured_signal with long-term metrics
        if synth_output and "structured_signal" in synth_output:
            synth_output["structured_signal"]["long_term_signal"] = long_term_signal
            synth_output["structured_signal"]["long_term_target"] = long_term_signal["long_term_target"]
            synth_output["structured_signal"]["long_term_verdict"] = long_term_signal["long_term_verdict"]
            synth_output["structured_signal"]["long_term_horizon"] = long_term_signal["long_term_horizon"]
            synth_output["structured_signal"]["suggested_long_term_peers"] = long_term_signal["suggested_long_term_peers"]

        results.append({
            "long_term_signal": long_term_signal,
            "symbol": sym,
            "name": name,
            "sector": sector,
            "queue_status": q_status,
            "is_stale": is_stale,
            "has_analysis": synth_output is not None,
            "synth_output": synth_output,
            "tech_output": tech_output,
            "hist_output": hist_output,
            "news_output": news_output,
            "risk_output": risk_output,
            "fund_output": fund_output,
            "patterns": patterns,
            "events": events,
            "sparkline": sparkline
        })
    return results

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
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Accept")
        self.end_headers()

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        path = parsed_path.path

        if path == "/api/status":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            
            q_status = queue_mgr.get_queue_status()
            shared_bulletin = cache_mgr.get_latest_market_bulletin()
            macro_items = cache_mgr.get_cached_macro(max_age_hours=24)

            resp_data = {
                "model": OLLAMA_MODEL,
                "timestamp": datetime.now().isoformat(),
                "queue_status": q_status,
                "bulletin": shared_bulletin,
                "macro_items": macro_items
            }
            self.wfile.write(safe_json_dumps(resp_data))
            return

        elif path == "/api/stocks":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            stocks_data = get_all_stock_data()
            self.wfile.write(safe_json_dumps(stocks_data))
            return

        elif path.startswith("/api/history"):
            query = urllib.parse.parse_qs(parsed_path.query)
            sym = query.get("symbol", [""])[0].upper().strip()
            raw_days = query.get("days", ["90"])[0]
            try:
                days = int(''.join(c for c in str(raw_days) if c.isdigit())) or 90
            except Exception:
                days = 90

            try:
                chart_data = tech_engine.get_chart_data(sym, limit_days=days) if sym else {"error": "Missing symbol", "candles": []}
            except Exception as e:
                print(f"Error fetching chart data for {sym}: {e}", flush=True)
                chart_data = {"symbol": sym, "candles": [], "error": str(e)}

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(safe_json_dumps(chart_data))
            return

        elif path.startswith("/api/events"):
            query = urllib.parse.parse_qs(parsed_path.query)
            sym = query.get("symbol", [""])[0].upper()

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            events_data = events_engine.fetch_stock_events(sym) if sym else {"upcoming_macro_catalysts": events_engine.get_upcoming_macro_events()}
            self.wfile.write(safe_json_dumps(events_data))
            return

        elif path.startswith("/api/search-symbol"):
            query = urllib.parse.parse_qs(parsed_path.query)
            q_str = query.get("q", [""])[0].strip()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            matches = search_internet_symbols(q_str) if q_str else []
            self.wfile.write(safe_json_dumps({"query": q_str, "results": matches}))
            return

        elif path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            html_path = os.path.join(PROJECT_ROOT, "static", "index.html")
            if os.path.exists(html_path):
                with open(html_path, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.wfile.write(b"Dashboard HTML missing.")
            return

        elif path.startswith("/news_reports/") or path.startswith("/reports/") or path.startswith("/news/"):
            # Normalize path and map aliases
            norm_path = path
            if path.startswith("/news/"):
                norm_path = "/news_reports/" + path[len("/news/"):]

            rel_path = norm_path.lstrip("/")
            target_file = os.path.abspath(os.path.join(PROJECT_ROOT, rel_path))
            is_inside_root = target_file.lower().startswith(os.path.abspath(PROJECT_ROOT).lower())
            
            if is_inside_root and os.path.exists(target_file) and os.path.isfile(target_file):
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
            static_filepath = os.path.join(PROJECT_ROOT, "static", path.lstrip("/"))
            if os.path.exists(static_filepath) and os.path.isfile(static_filepath):
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

    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == "/api/trigger":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            req_data = json.loads(body.decode('utf-8')) if body else {}
            symbol = req_data.get("symbol", "").upper()

            # Find company name and sector
            c_name, c_sec = "", ""
            if os.path.exists(SYMBOLS_FILE_PATH):
                try:
                    with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
                        for s_item in json.load(f).get("symbols", []):
                            if s_item.get("symbol", "").upper() == symbol:
                                c_name = s_item.get("name", "")
                                c_sec = s_item.get("sector", "")
                                break
                except Exception:
                    pass

            def run_single():
                with sqlite3.connect(cache_mgr.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("UPDATE persistent_stock_queue SET status = 'in_progress' WHERE symbol = ?", (symbol,))
                    conn.commit()
                try:
                    get_workflow().run_analysis(symbol, company_name=c_name, sector=c_sec, force_refresh=True)
                    queue_mgr.mark_completed(symbol)
                except Exception as e:
                    print(f"⚠️ Error in single stock analysis for {symbol}: {e}")
                    with sqlite3.connect(cache_mgr.db_path) as conn:
                        cursor = conn.cursor()
                        cursor.execute("UPDATE persistent_stock_queue SET status = 'pending' WHERE symbol = ?", (symbol,))
                        conn.commit()

            threading.Thread(target=run_single, daemon=True).start()

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(safe_json_dumps({"status": "triggered", "symbol": symbol}))
            return

        elif parsed_path.path == "/api/add-symbol":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            req_data = json.loads(body.decode('utf-8')) if body else {}
            sym = req_data.get("symbol", "").upper().strip()
            name = req_data.get("name", "").strip()
            sector = req_data.get("sector", "").strip()
            exchange = req_data.get("exchange", "NSE").strip()

            res = add_symbol_to_json(symbol=sym, name=name, sector=sector, exchange=exchange)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(safe_json_dumps(res))
            return

        elif parsed_path.path == "/api/remove-symbol":
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            req_data = json.loads(body.decode('utf-8')) if body else {}
            sym = req_data.get("symbol", "").upper().strip()

            res = remove_symbol_from_json(symbol=sym)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(safe_json_dumps(res))
            return

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True

def start_dashboard_server(port=None):
    if port is None:
        port = PORT
    os.makedirs(os.path.join(PROJECT_ROOT, "static"), exist_ok=True)
    for p in [port, port + 1, port + 2]:
        try:
            with ThreadedTCPServer(("", p), DashboardHandler) as httpd:
                print(f"🌐 [Realtime Dashboard Server] Running live at http://localhost:{p}", flush=True)
                httpd.serve_forever()
                break
        except OSError:
            continue

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Real-Time Dashboard Server for NSE Stock Predictor")
    parser.add_argument("--port", type=int, default=PORT, help="Port to run the dashboard server on")
    args, _ = parser.parse_known_args()
    start_dashboard_server(port=args.port)
