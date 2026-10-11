"""
Main Entrypoint for NSE Multi-Agent RAG & Stock Prediction System.
Features real-time progress bar, live ETA telemetry, Valkey/SQLite task queueing,
and high-speed single-LLM synthesis per stock.
"""

import json
import sys
import os
import signal
import concurrent.futures
import time
from datetime import datetime

# Ensure project root is in sys.path
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

from config import SYMBOLS_FILE_PATH, OLLAMA_MODEL, VERBOSE_LOGGING, MAX_PARALLEL_WORKERS, MAX_SYMBOL_WORKERS
from storage.queue_manager import ValkeyQueueManager
from storage.cache_manager import CacheManager
from agents.macro_sentinel import BackgroundMacroSentinel
from graph import MultiAgentWorkflow

def load_symbols():
    if not os.path.exists(SYMBOLS_FILE_PATH):
        print(f"Error: {SYMBOLS_FILE_PATH} not found.")
        return []
    with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data.get("symbols", [])

def render_progress_bar(current: int, total: int, items_this_run: int, elapsed_this_run: float):
    """Renders an intuitive visual progress bar with percentage and accurate ETA."""
    pct = int((current / max(1, total)) * 100)
    bar_length = 25
    filled_length = int(bar_length * current // max(1, total))
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    if items_this_run > 0:
        avg_time_per_item = elapsed_this_run / items_this_run
        remaining_items = total - current
        eta_seconds = max(0, int(avg_time_per_item * remaining_items))
        if eta_seconds < 120:
            eta_str = f"ETA: ~{eta_seconds}s remaining"
        else:
            eta_str = f"ETA: ~{eta_seconds // 60}m {eta_seconds % 60}s remaining"
    else:
        eta_str = "ETA: calculating..."
    
    return f"Progress: [{bar}] {pct}% ({current}/{total}) | Elapsed: {int(elapsed_this_run)}s | {eta_str}"

def main():
    print("=" * 80)
    print("  📈 NSE MULTI-AGENT RAG & STOCK PREDICTION SYSTEM")
    print(f"  Model Engine: Ollama ({OLLAMA_MODEL}) [Zero-Cost High-Speed Pipeline]")
    print(f"  Execution Mode: Dual Parallel ({MAX_SYMBOL_WORKERS} symbols x {MAX_PARALLEL_WORKERS} agent threads)")
    print(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    symbols_list = load_symbols()
    if not symbols_list:
        print("No stock symbols found in symbols.json.")
        return

    # Start Background Market Sentinel Thread (Common Macro Monitor)
    sentinel = BackgroundMacroSentinel()
    sentinel.start()

    executor_ref = None

    def graceful_exit(signum=None, frame=None):
        print("\n\n🛑 Process interrupted by user (Ctrl+C). Cleaning up workers & threads...")
        try:
            sentinel.stop()
        except Exception:
            pass
        if executor_ref:
            try:
                executor_ref.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
        print("👋 Execution terminated cleanly.")
        sys.exit(0)

    # Register signal handlers for graceful interrupt
    try:
        signal.signal(signal.SIGINT, graceful_exit)
        signal.signal(signal.SIGTERM, graceful_exit)
    except Exception:
        pass

    try:
        # Initialize Valkey / Persistent SQLite Queue Manager
        queue_mgr = ValkeyQueueManager()
        cache_mgr = CacheManager()
        queue_mgr.enqueue_symbols(symbols_list)
        
        q_status = queue_mgr.get_queue_status()
        total_symbols = len(symbols_list)
        completed_already = q_status.get('completed', 0)
        pending_count = q_status.get('pending', 0)

        print(f"\n📦 QUEUE STATUS: {q_status.get('engine')}")
        print(f"   • Total Symbols: {total_symbols} | Pending: {pending_count} | Completed: {completed_already}\n")

        workflow = MultiAgentWorkflow()

        reports_dir = os.path.join(PROJECT_ROOT, "reports")
        os.makedirs(reports_dir, exist_ok=True)
        timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_filepath = os.path.join(reports_dir, f"NSE_Stock_Predictions_{timestamp_str}.md")
        latest_report_filepath = os.path.join(reports_dir, "NSE_Stock_Predictions_latest.md")

        report_markdown = []
        report_markdown.append("# NSE Multi-Agent Stock Analysis & Prediction Report")
        report_markdown.append(f"**Generated At**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        report_markdown.append(f"**Model Engine**: Ollama (`{OLLAMA_MODEL}`) [Zero-Cost Local Setup]  ")
        report_markdown.append(f"**Total Symbols**: {total_symbols}\n")
        report_markdown.append("---")

        results_dict = {}
        completed_counter = completed_already
        items_this_run = 0
        pipeline_start_time = time.time()

        def process_symbol_task(task):
            nonlocal completed_counter, items_this_run
            symbol = task.get("symbol")
            company_name = task.get("name", "")
            sector = task.get("sector", "")
            task_id = task.get("_task_id")

            t_start = time.time()
            print(f"🚀 [Started] {symbol:<10} ({company_name}) | Processing engines & Ollama synthesis...")
            sys.stdout.flush()

            try:
                res = workflow.run_analysis(symbol, company_name, sector)
                queue_mgr.mark_completed(symbol, task_id)
                elapsed = time.time() - t_start
                
                completed_counter += 1
                items_this_run += 1

                signal_data = res.get("structured_signal", {})
                verdict = signal_data.get("action_verdict", "HOLD")
                conf = signal_data.get("confidence_rating", "MEDIUM")
                target = signal_data.get("when_to_sell_target", "N/A")
                sl = signal_data.get("stop_loss", "N/A")

                # Clean Live Telemetry Output
                prog_str = render_progress_bar(completed_counter, total_symbols, items_this_run, time.time() - pipeline_start_time)
                print(f"✅ [{completed_counter}/{total_symbols}] {symbol:<10} | VERDICT: {verdict:<10} | Target: {target:<12} | SL: {sl:<10} | ({elapsed:.2f}s)")
                print(f"   {prog_str}\n")
                sys.stdout.flush()

                return symbol, company_name, sector, res
            except Exception as e:
                print(f"⚠️ Error processing {symbol}: {e}\n")
                sys.stdout.flush()
                return symbol, company_name, sector, None

        # Dequeue pending tasks from Valkey / SQLite queue
        pending_tasks = []
        while True:
            t = queue_mgr.dequeue_symbol()
            if not t:
                break
            pending_tasks.append(t)

        if pending_tasks:
            print(f"⚡ Processing {len(pending_tasks)} pending stock symbol(s) using {MAX_SYMBOL_WORKERS} parallel symbol streams...\n")
            with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_SYMBOL_WORKERS) as executor:
                executor_ref = executor
                future_to_task = {executor.submit(process_symbol_task, t): t for t in pending_tasks}
                for future in concurrent.futures.as_completed(future_to_task):
                    sym, c_name, sec, res = future.result()
                    if res:
                        results_dict[sym] = {"name": c_name, "sector": sec, "result": res}
        else:
            print(f"\n✨ All {total_symbols} queued stock tasks are already completed!")

        # Always format and save full report from SQLite cache for all symbols in symbols.json
        for item in symbols_list:
            sym = item.get("symbol", "").upper()
            c_name = item.get("name", "")
            sec = item.get("sector", "")
            
            # Fetch latest prediction from cache if available
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=168)
            if synth_res:
                report_text = synth_res.get("final_report", "No report text returned.")
                last_price = synth_res.get("last_price", "N/A")

                report_markdown.append(f"\n## {sym} - {c_name}")
                report_markdown.append(f"**Sector**: {sec}  | **Last Price**: Rs. {last_price}\n")
                report_markdown.append(report_text)
                report_markdown.append("\n---\n")

        full_report_content = "\n".join(report_markdown)
        with open(report_filepath, "w", encoding="utf-8") as f:
            f.write(full_report_content)
        with open(latest_report_filepath, "w", encoding="utf-8") as f:
            f.write(full_report_content)

        # Generate multi-source news markdown reports in date-named folder (2 files: general and stock-specific)
        try:
            from tools.news_tools import NewsSentimentEngine
            news_engine = NewsSentimentEngine(cache_manager=cache_mgr)
            news_res = news_engine.generate_both_reports(symbols=symbols_list)
            news_path = f"{news_res.get('general_market_news')} & {news_res.get('stock_specific_news')}"
        except Exception as e:
            news_path = "N/A"
            print(f"⚠️ [News Report Notice] Could not generate news markdown reports: {e}")

        print("\n" + "═" * 80)
        print("🎉 REPORT GENERATION COMPLETE!")
        print(f"   • Total Pipeline Time: {int(time.time() - pipeline_start_time)} seconds")
        print(f"   • Stock Predictions Report: {latest_report_filepath}")
        print(f"   • Multi-Source News Reports: {news_path}")
        print("═" * 80 + "\n")
    except KeyboardInterrupt:
        graceful_exit()
    finally:
        sentinel.stop()

if __name__ == "__main__":
    main()
