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
import argparse
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

# Thread-safe null-safe stream wrapper — prevents "lost sys.stderr" crashes
# when parallel worker threads try to print after the main thread has exited
# or when Python is running without an attached terminal (e.g. nohup / service).
class _SafeStream:
    """Wraps sys.stdout/stderr so writes never raise, even if the underlying
    stream is closed or None (common in detached/parallel contexts on Windows)."""
    def __init__(self, stream, encoding="utf-8"):
        self._stream = stream
        self.encoding = encoding
        self.errors = "replace"
    def write(self, s):
        try:
            if self._stream and not getattr(self._stream, "closed", False):
                self._stream.write(s)
        except Exception:
            pass
    def flush(self):
        try:
            if self._stream and not getattr(self._stream, "closed", False):
                self._stream.flush()
        except Exception:
            pass
    def fileno(self):
        try:
            return self._stream.fileno()
        except Exception:
            return -1
    def isatty(self):
        try:
            return self._stream.isatty()
        except Exception:
            return False

if sys.stdout is None or getattr(sys.stdout, "closed", False):
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None or getattr(sys.stderr, "closed", False):
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

sys.stdout = _SafeStream(sys.stdout)
sys.stderr = _SafeStream(sys.stderr)

from config import SYMBOLS_FILE_PATH, OLLAMA_MODEL, VERBOSE_LOGGING, MAX_PARALLEL_WORKERS, MAX_SYMBOL_WORKERS
from storage.queue_manager import ValkeyQueueManager
from storage.cache_manager import CacheManager
from agents.macro_sentinel import BackgroundMacroSentinel
from graph import MultiAgentWorkflow

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
        if hasattr(sys.stdout, "flush"):
            sys.stdout.flush()
    except Exception:
        pass

def load_symbols():
    if not os.path.exists(SYMBOLS_FILE_PATH):
        print(f"Error: {SYMBOLS_FILE_PATH} not found.")
        return []
    try:
        with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("symbols", [])
    except Exception as e:
        print(f"[Error] Failed to parse {SYMBOLS_FILE_PATH}: {e}")
        return []

def render_progress_bar(current: int, total: int, items_this_run: int, elapsed_this_run: float):
    """Renders an intuitive visual progress bar with percentage and accurate ETA."""
    pct = min(100, max(0, int((current / max(1, total)) * 100)))
    bar_length = 25
    filled_length = min(bar_length, max(0, int(bar_length * current // max(1, total))))
    bar = '█' * filled_length + '░' * (bar_length - filled_length)
    
    if items_this_run > 0:
        avg_time_per_item = elapsed_this_run / items_this_run
        remaining_items = max(0, total - current)
        eta_seconds = max(0, int(avg_time_per_item * remaining_items))
        if eta_seconds < 120:
            eta_str = f"ETA: ~{eta_seconds}s remaining"
        else:
            eta_str = f"ETA: ~{eta_seconds // 60}m {eta_seconds % 60}s remaining"
    else:
        eta_str = "ETA: calculating..."
    
    return f"Progress: [{bar}] {pct}% ({current}/{total}) | Elapsed: {int(elapsed_this_run)}s | {eta_str}"

def build_quick_picks_section(symbols_list: list, results_dict: dict, cache_mgr) -> str:
    """
    Builds a compact 'Today's Quick Picks' section — HIGH-confidence BUY/ACCUMULATE
    stocks ranked by Reward:Risk ratio. Designed to be scannable in under 30 seconds
    on days when you don't have time to read the full report.
    """
    picks = []

    for item in symbols_list:
        sym   = item.get("symbol", "").upper()
        cname = item.get("name", "")
        sec   = item.get("sector", "")

        # Resolve synthesis result (same cascade as main report)
        synth_res = None
        if sym in results_dict:
            synth_res = results_dict[sym]["result"]
        if not synth_res:
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=168)
        if not synth_res:
            synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=None)
        if not synth_res:
            continue

        sig      = synth_res.get("structured_signal", {})
        verdict  = str(sig.get("action_verdict", "HOLD")).upper()
        conf_raw = str(sig.get("confidence_rating", "")).upper()
        entry    = sig.get("when_to_buy_entry", "N/A")
        target   = sig.get("when_to_sell_target", "N/A")
        sl       = sig.get("stop_loss", "N/A")
        pattern  = sig.get("chart_patterns", "")
        horizon  = sig.get("holding_horizon", "")
        lp       = synth_res.get("last_price", "N/A")

        # Only HIGH-confidence BUY or ACCUMULATE
        if verdict not in ("BUY", "ACCUMULATE", "STRONG BUY"):
            continue
        if "HIGH" not in conf_raw:
            continue

        # Compute Reward:Risk ratio for ranking
        rr = 0.0
        upside = "N/A"
        try:
            _lp  = float(lp)
            _sl  = float(str(sl).replace("Rs.", "").replace(",", "").strip())
            _tgt = float(str(target).split("-")[0].replace("Rs.", "").replace(",", "").strip())

            # Directional sanity: skip stocks with inverted stop loss (LLM hallucination)
            if _sl >= _lp:   # stop loss must be BELOW price for BUY
                continue
            if _tgt <= _lp:  # target must be ABOVE price for BUY
                continue

            risk   = _lp - _sl          # always positive after guard above
            reward = _tgt - _lp
            rr     = round(reward / risk, 2)
            upside = f"+{round((_tgt - _lp) / _lp * 100, 1)}%"

            # Cap absurd R:R — indicates bad data
            if rr > 20:
                continue
        except Exception:
            upside = "N/A"

        picks.append({
            "sym":     sym,
            "cname":   cname,
            "sec":     sec,
            "verdict": verdict,
            "entry":   entry,
            "target":  target,
            "sl":      sl,
            "lp":      lp,
            "upside":  upside,
            "rr":      rr,
            "pattern": pattern,
            "horizon": horizon,
        })

    # Rank by Reward:Risk descending, cap at top 7
    picks.sort(key=lambda x: x["rr"], reverse=True)
    top_picks = picks[:7]

    if not top_picks:
        return "\n## ⚡ Today's Quick Picks\n> No HIGH-confidence BUY signals found in this run.\n\n---\n"

    lines = []
    lines.append("\n## ⚡ Today's Quick Picks")
    lines.append("> **For busy days** — HIGH-confidence BUY signals only, ranked by Reward:Risk ratio.")
    lines.append("> Entry, target and stop-loss are all you need. No need to read individual stock sections.\n")
    lines.append("| # | Symbol | Company | Sector | Last Price | Entry Range | Target | Stop Loss | Upside | R:R | Pattern |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")

    for i, p in enumerate(top_picks, 1):
        rr_disp = f"{p['rr']:.1f}x" if p["rr"] else "N/A"
        lines.append(
            f"| {i} | **{p['sym']}** | {p['cname']} | {p['sec']} "
            f"| Rs. {p['lp']} | {p['entry']} | {p['target']} "
            f"| {p['sl']} | {p['upside']} | {rr_disp} | {p['pattern']} |"
        )

    lines.append("")
    lines.append("> [!TIP]")
    lines.append("> **How to use**: Place limit orders at the lower end of the Entry Range. Stop loss is non-negotiable.")
    lines.append("> Stocks are sorted best Reward:Risk first — if you can only act on 1–2, start from the top.\n")
    lines.append("---\n")

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(description="NSE Multi-Agent RAG & Stock Prediction System")
    parser.add_argument("--force", "-f", action="store_true", help="Force fresh re-analysis of symbols (resets queue and cache)")
    parser.add_argument("--reset", action="store_true", help="Reset persistent queue status to pending and exit")
    parser.add_argument("--symbol", "-s", type=str, default="", help="Comma-separated stock symbol(s) to analyze (e.g. RELIANCE,TCS)")
    parser.add_argument("--fast", action="store_true", help="Fast quantitative synthesis mode (all 34 stocks in under 30s)")
    return parser.parse_args()

def main():
    args = parse_args()

    if args.fast:
        os.environ["FAST_MODE"] = "true"

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

    # Filter target symbols if specified
    if args.symbol:
        target_syms = {s.strip().upper() for s in args.symbol.split(",") if s.strip()}
        symbols_list = [s for s in symbols_list if s.get("symbol", "").upper() in target_syms]
        if not symbols_list:
            print(f"Error: Specified symbol(s) '{args.symbol}' not found in symbols.json.")
            return
        print(f"🎯 Filtered Targets ({len(symbols_list)}): {[s.get('symbol') for s in symbols_list]}")

    if args.reset:
        queue_mgr = ValkeyQueueManager()
        queue_mgr.reset_queue(symbols_list)
        print(f"✅ Reset queue to 'pending' for {len(symbols_list)} symbol(s). Exiting.")
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

        # Check existing queue status to determine whether to reset or resume
        q_status = queue_mgr.get_queue_status()
        pending_count = q_status.get('pending', 0)
        in_progress_count = q_status.get('in_progress', 0)

        if args.force or args.symbol:
            safe_print(f"⚡ Initializing fresh queue for {len(symbols_list)} target symbol(s)...")
            queue_mgr.reset_queue(symbols_list)
        elif pending_count == 0 and in_progress_count == 0:
            safe_print("🔄 Previous batch completed 100%. Initializing fresh queue for all target symbols...")
            queue_mgr.reset_queue(symbols_list)
        else:
            safe_print(f"⏯️ Resuming previous interrupted run ({pending_count} pending items remaining)...")
            queue_mgr.enqueue_symbols(symbols_list, force=False)
        
        q_status = queue_mgr.get_queue_status()
        total_symbols = len(symbols_list)
        completed_already = q_status.get('completed', 0)
        pending_count = q_status.get('pending', 0)

        print(f"\n📦 QUEUE STATUS: {q_status.get('engine')}")
        print(f"   • Total Symbols: {total_symbols} | Pending: {pending_count} | Completed: {completed_already}\n")

        workflow = MultiAgentWorkflow()

        reports_dir = os.path.join(PROJECT_ROOT, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        # Daily report management: if second (or subsequent) analysis of the day,
        # reuse and update today's existing file instead of creating a new report md file.
        today_str = datetime.now().strftime('%Y%m%d')
        today_prefix = f"NSE_Stock_Predictions_{today_str}"
        today_files = sorted([
            f for f in os.listdir(reports_dir)
            if f.startswith(today_prefix) and f.endswith(".md") and not f.endswith("_latest.md")
        ])

        if today_files:
            is_second_run_of_day = True
            report_filepath = os.path.join(reports_dir, today_files[-1])
            safe_print(f"📄 [Report Engine] Existing report for today found ({today_files[-1]}). Reusing and updating existing file (no new file created).")
        else:
            is_second_run_of_day = False
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_filepath = os.path.join(reports_dir, f"NSE_Stock_Predictions_{timestamp_str}.md")
            safe_print(f"📄 [Report Engine] First run of day. Creating daily report: {os.path.basename(report_filepath)}")

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
            safe_print(f"🚀 [Started] {symbol:<10} ({company_name}) | Processing engines & quantitative synthesis...")

            try:
                res = workflow.run_analysis(symbol, company_name, sector, force_refresh=args.force)
                queue_mgr.mark_completed(symbol, task_id)
                elapsed = time.time() - t_start
                
                completed_counter += 1
                items_this_run += 1

                signal_data = res.get("structured_signal", {})
                verdict = signal_data.get("action_verdict", "HOLD")
                conf = signal_data.get("confidence_rating", "MEDIUM")
                target = signal_data.get("when_to_sell_target", "N/A")
                sl = signal_data.get("stop_loss", "N/A")

                pattern_str = signal_data.get("chart_patterns", "")
                events_str = signal_data.get("upcoming_events_note", "")

                # Clean Live Telemetry Output
                prog_str = render_progress_bar(completed_counter, total_symbols, items_this_run, time.time() - pipeline_start_time)
                safe_print(f"✅ [{completed_counter}/{total_symbols}] {symbol:<10} | VERDICT: {verdict:<10} | Target: {target:<12} | SL: {sl:<10} | ({elapsed:.2f}s)")
                if pattern_str:
                    safe_print(f"   📐 Pattern: {pattern_str}")
                if events_str:
                    safe_print(f"   📅 Catalyst: {events_str}")
                safe_print(f"   {prog_str}\n")

                return symbol, company_name, sector, res
            except Exception as e:
                safe_print(f"⚠️ Error processing {symbol}: {e}\n")
                return symbol, company_name, sector, None

        # Dequeue pending tasks from Valkey / SQLite queue
        target_filter = [s["symbol"] for s in symbols_list] if args.symbol else None
        pending_tasks = []
        while True:
            t = queue_mgr.dequeue_symbol(symbols_filter=target_filter)
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

        # Always format and save full report from newly processed results or SQLite cache
        # --- Build Quick Picks section first (top of report, after header) ---
        quick_picks_md = build_quick_picks_section(symbols_list, results_dict, cache_mgr)
        report_markdown.append(quick_picks_md)

        for item in symbols_list:
            sym = item.get("symbol", "").upper()
            c_name = item.get("name", "")
            sec = item.get("sector", "")
            
            # 1. First check if we just generated results in this run
            synth_res = None
            if sym in results_dict:
                synth_res = results_dict[sym]["result"]
            
            # 2. Check fresh cache (< 7 days)
            if not synth_res:
                synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=168)
            
            # 3. Fallback to any latest cached prediction so report is never empty
            if not synth_res:
                synth_res = cache_mgr.get_latest_agent_output(sym, "Master Prediction Synthesizer Agent", max_age_hours=None)

            if synth_res:
                report_text = synth_res.get("final_report", "No report text returned.")
                last_price = synth_res.get("last_price")
                if not last_price or last_price == "N/A":
                    candles = cache_mgr.get_cached_candles(sym, limit_days=1)
                    if candles:
                        last_price = round(float(candles[-1].get("CLOSE_PRICE", 0)), 2)
                    else:
                        last_price = "N/A"

                report_markdown.append(f"\n## {sym} - {c_name}")
                report_markdown.append(f"**Sector**: {sec}  | **Last Price**: Rs. {last_price}\n")
                report_markdown.append(report_text)
                report_markdown.append("\n---\n")
            else:
                report_markdown.append(f"\n## {sym} - {c_name}")
                report_markdown.append(f"**Sector**: {sec}  | **Status**: Analysis In Progress\n")
                report_markdown.append("*Analysis in queue or calculating prediction.*\n")
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
        if is_second_run_of_day:
            print(f"   • Daily Report (Updated today's file, no new file created): {report_filepath}")
        else:
            print(f"   • Daily Report (First run of day, created): {report_filepath}")
        print(f"   • Latest Pointer: {latest_report_filepath}")
        print(f"   • Multi-Source News Reports: {news_path}")
        print("═" * 80 + "\n")
    except KeyboardInterrupt:
        graceful_exit()
    finally:
        sentinel.stop()

if __name__ == "__main__":
    main()
