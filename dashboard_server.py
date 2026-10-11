"""
Real-Time Web Dashboard Server for NSE Multi-Agent Stock Predictor.
Serves a rich glassmorphism UI at http://localhost:8000 and exposes real-time JSON API endpoints.
Reads directly from SQLite (storage/cache.db) and Valkey queue.
"""

import http.server
import socketserver
import json
import os
import sys
import urllib.parse
from datetime import datetime
import threading

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import OLLAMA_MODEL, SYMBOLS_FILE_PATH, CACHE_DB_PATH
from storage.cache_manager import CacheManager
from storage.queue_manager import ValkeyQueueManager
from graph import MultiAgentWorkflow

PORT = 8501
cache_mgr = CacheManager()
queue_mgr = ValkeyQueueManager()
workflow = MultiAgentWorkflow(cache_mgr)

def get_all_stock_data():
    symbols_list = []
    if os.path.exists(SYMBOLS_FILE_PATH):
        with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            symbols_list = json.load(f).get("symbols", [])

    results = []
    for s in symbols_list:
        sym = s.get("symbol", "").upper()
        name = s.get("name", "")
        sector = s.get("sector", "")

        # Get latest synthesizer output
        synth_output = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=72)
        tech_output = cache_mgr.get_latest_agent_output(sym, "Technical Analysis Agent", max_age_hours=72)
        hist_output = cache_mgr.get_latest_agent_output(sym, "Historical Data RAG Agent", max_age_hours=72)
        news_output = cache_mgr.get_latest_agent_output(sym, "News & Sentiment Agent", max_age_hours=72)
        risk_output = cache_mgr.get_latest_agent_output(sym, "Risk & Volatility Agent", max_age_hours=72)
        fund_output = cache_mgr.get_latest_agent_output(sym, "Fundamental Analyst Agent", max_age_hours=72)

        results.append({
            "symbol": sym,
            "name": name,
            "sector": sector,
            "has_analysis": synth_output is not None,
            "synth_output": synth_output,
            "tech_output": tech_output,
            "hist_output": hist_output,
            "news_output": news_output,
            "risk_output": risk_output,
            "fund_output": fund_output
        })
    return results

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
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
            self.wfile.write(json.dumps(resp_data).encode("utf-8"))
            return

        elif path == "/api/stocks":
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            stocks_data = get_all_stock_data()
            self.wfile.write(json.dumps(stocks_data).encode("utf-8"))
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

            def run_single():
                workflow.run_analysis(symbol, force_refresh=True)

            threading.Thread(target=run_single, daemon=True).start()

            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "triggered", "symbol": symbol}).encode("utf-8"))
            return

def start_dashboard_server(port=PORT):
    os.makedirs(os.path.join(PROJECT_ROOT, "static"), exist_ok=True)
    for p in [port, 8502, 8503, 8080]:
        try:
            with socketserver.TCPServer(("", p), DashboardHandler) as httpd:
                print(f"🌐 [Realtime Dashboard Server] Running live at http://localhost:{p}")
                httpd.serve_forever()
                break
        except OSError:
            continue

if __name__ == "__main__":
    start_dashboard_server()
