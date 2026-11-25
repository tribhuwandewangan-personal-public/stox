"""
Market-hours aware background scheduler (runs inside the dashboard process; disable with AUTO_SCHEDULE=0).

  * Pre-market (from 08:45 IST on trading days, once per day): refresh macro indicators and stock news.
  * Post-close (from 16:00 IST for the most recent completed session, once per session): download the final
    daily candles, re-run the analysis for every symbol, score open predictions, prune old agent outputs.

Jobs are keyed by date in the kv_state table, so restarting the dashboard never repeats a finished job, and a
session missed because the PC was off is caught up the next time the dashboard starts (e.g. Friday's analysis
runs on Saturday).
"""

import concurrent.futures
import threading
from datetime import datetime, time as dtime
from typing import Any, Callable, Dict, List, Optional

from tools import market_calendar
from tools.outcome_tracker import resolve_open_predictions
from tools import events_bus

PREMARKET_FROM = dtime(8, 45)
POSTCLOSE_FROM = dtime(16, 15)   # wait until 15:30 + 45m EOD_DATA_BUFFER (16:15 IST) so today's candle is final
TICK_SECONDS = 60
PRUNE_KEEP_DAYS = 30


class Scheduler:
    def __init__(
        self,
        cache_manager,
        workflow_getter: Callable[[], Any],
        symbols_loader: Callable[[], List[Dict[str, Any]]],
        max_workers: int = 4,
        on_symbol_done: Optional[Callable[[str], None]] = None,
        clock: Callable[[], datetime] = market_calendar.now_ist,
    ):
        self.cache = cache_manager
        self.workflow_getter = workflow_getter
        self.symbols_loader = symbols_loader
        self.max_workers = max_workers
        self.on_symbol_done = on_symbol_done
        self.clock = clock
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = threading.Lock()          # one job at a time

    # ---- lifecycle -------------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True, name="SchedulerThread")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception as e:                # the scheduler must never die
                print(f"⚠️ [Scheduler] tick failed: {type(e).__name__}: {e}", flush=True)
            if self._stop.wait(TICK_SECONDS):
                break

    # ---- decisions -------------------------------------------------------------------------------
    def due_jobs(self, now: Optional[datetime] = None) -> List[str]:
        """Names of jobs that should run now ('premarket', 'postclose'). Pure decision, no side effects."""
        n = now or self.clock()
        due = []
        today = n.date()
        if (market_calendar.is_trading_day(today) and n.time() >= PREMARKET_FROM
                and not market_calendar.is_session_complete(today, n)
                and not self.cache.get_state(f"sched.premarket.{today.isoformat()}")):
            due.append("premarket")
        session = market_calendar.last_completed_session(n)
        # Post-close work waits for 16:00 on the session day itself; a later day means it is already overdue
        after_hours = session < today or n.time() >= POSTCLOSE_FROM
        if after_hours and not self.cache.get_state(f"sched.postclose.{session.isoformat()}"):
            due.append("postclose")
        return due

    def tick(self, now: Optional[datetime] = None) -> List[str]:
        """Run whatever is due. Returns the names of the jobs that ran."""
        ran = []
        for job in self.due_jobs(now):
            if not self._running.acquire(blocking=False):
                break
            try:
                n = now or self.clock()
                if job == "premarket":
                    self.run_premarket()
                    self.cache.set_state(f"sched.premarket.{n.date().isoformat()}", n.isoformat())
                else:
                    session = market_calendar.last_completed_session(n)
                    self.run_postclose()
                    self.cache.set_state(f"sched.postclose.{session.isoformat()}", n.isoformat())
                ran.append(job)
            except Exception as e:
                print(f"⚠️ [Scheduler] job '{job}' failed (will retry next tick): {type(e).__name__}: {e}", flush=True)
            finally:
                self._running.release()
        return ran

    # ---- jobs ------------------------------------------------------------------------------------
    def run_premarket(self) -> None:
        from tools.macro_tools import GlobalMacroEngine
        from tools.news_tools import NewsSentimentEngine
        print("🗓️ [Scheduler] Pre-market refresh: macro + news", flush=True)
        GlobalMacroEngine(self.cache).fetch_macro_indicators(max_age_hours=0.05)
        news = NewsSentimentEngine(self.cache)
        symbols = self.symbols_loader()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(lambda s: news.fetch_stock_news(s["symbol"], s.get("name", ""), force_refresh=True), symbols))
        try:
            events_bus.publish("scheduler", {
                "job": "premarket",
                "message": f"Pre-market macro & news refresh completed for {len(symbols)} symbols.",
            })
        except Exception:
            pass

    def run_postclose(self) -> None:
        symbols = self.symbols_loader()
        workflow = self.workflow_getter()
        print(f"🗓️ [Scheduler] Post-close run for {len(symbols)} symbols: sync -> analyse -> score -> prune", flush=True)
        workflow.hist_engine.sync_all_symbols(symbols)
        if hasattr(workflow.hist_engine, "sync_benchmarks"):
            try:
                workflow.hist_engine.sync_benchmarks()
            except Exception as e:
                print(f"⚠️ [Scheduler] benchmark sync warning: {type(e).__name__}: {e}", flush=True)

        def _analyse(item: Dict[str, Any]) -> None:
            sym = item["symbol"].upper()
            try:
                workflow.run_analysis(sym, company_name=item.get("name", ""), sector=item.get("sector", ""), force_refresh=True)
                if self.on_symbol_done:
                    self.on_symbol_done(sym)
                # Publish analysis completion event for WebSocket broadcast
                events_bus.publish(events_bus.ANALYSIS_DONE, {
                    "symbol": sym,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                print(f"⚠️ [Scheduler] analysis failed for {sym}: {type(e).__name__}: {e}", flush=True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            list(pool.map(_analyse, symbols))

        counts = resolve_open_predictions(self.cache)
        pruned = self.cache.prune_agent_runs(PRUNE_KEEP_DAYS)
        print(f"🗓️ [Scheduler] Post-close done. Predictions scored: {counts}; old agent rows pruned: {pruned}", flush=True)
        try:
            events_bus.publish("scheduler", {
                "job": "postclose",
                "message": f"Post-close sync & analysis finished for {len(symbols)} symbols.",
            })
        except Exception:
            pass
