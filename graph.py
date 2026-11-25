"""
Multi-Agent Orchestrator.
Dispatches stock symbols from symbols.json, checks the incremental SQLite cache, runs the specialized
analyst agents in parallel (with a hard timeout) and then the deterministic Master Synthesizer Agent.
"""

from typing import Dict, Any, List, TypedDict, Annotated
import json
import sys
import os

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

def safe_print(*args, **kwargs):
    try:
        print(*args, **kwargs)
    except UnicodeEncodeError:
        try:
            enc = getattr(sys.stdout, "encoding", "ascii") or "ascii"
            clean_args = [str(a).encode(enc, errors="replace").decode(enc, errors="replace") for a in args]
            print(*clean_args, **kwargs)
        except Exception:
            pass

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from storage.cache_manager import CacheManager
from tools.historical_data_tools import HistoricalDataEngine
from tools.tech_tools import TechnicalAnalysisEngine
from tools.news_tools import NewsSentimentEngine
from tools.macro_tools import GlobalMacroEngine
from tools.risk_tools import RiskManagementEngine
from agents.historical_rag_agent import HistoricalRAGAgent
from agents.technical_agent import TechnicalAnalysisAgent
from agents.news_sentiment_agent import NewsSentimentAgent
from agents.macro_agent import GlobalMacroAgent
from agents.fundamental_agent import FundamentalAgent
from agents.risk_agent import RiskAgent
from agents.synthesizer_agent import MasterPredictionSynthesizerAgent
from tools.outcome_tracker import build_prediction_record

# State schema (documentation of the data flowing through the pipeline)
class StockAnalysisState(TypedDict):
    symbol: str
    company_name: str
    sector: str
    incremental_cache_hit: bool
    historical_rag_output: Dict[str, Any]
    technical_output: Dict[str, Any]
    news_sentiment_output: Dict[str, Any]
    macro_output: Dict[str, Any]
    fundamental_output: Dict[str, Any]
    risk_output: Dict[str, Any]
    final_prediction_output: Dict[str, Any]

import concurrent.futures
import time
from config import VERBOSE_LOGGING, MAX_PARALLEL_WORKERS, AGENT_TIMEOUT_SECONDS

class MultiAgentWorkflow:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()
        
        # Engines initialized with shared SQLite cache_manager
        hist_engine = HistoricalDataEngine(cache_manager=self.cache_manager)
        self.hist_engine = hist_engine
        tech_engine = TechnicalAnalysisEngine(rag_engine=hist_engine, cache_manager=self.cache_manager)
        news_engine = NewsSentimentEngine(cache_manager=self.cache_manager)
        macro_engine = GlobalMacroEngine(cache_manager=self.cache_manager)
        risk_engine = RiskManagementEngine(rag_engine=hist_engine, cache_manager=self.cache_manager)

        self.hist_agent = HistoricalRAGAgent(rag_engine=hist_engine)
        self.tech_agent = TechnicalAnalysisAgent(tech_engine=tech_engine)
        self.news_agent = NewsSentimentAgent(news_engine=news_engine)
        self.macro_agent = GlobalMacroAgent(macro_engine=macro_engine)
        self.fund_agent = FundamentalAgent(cache_manager=self.cache_manager)
        self.risk_agent = RiskAgent(risk_engine=risk_engine)
        self.synth_agent = MasterPredictionSynthesizerAgent(cache_manager=self.cache_manager)

    def run_analysis(self, symbol: str, company_name: str = "", sector: str = "", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Executes multi-agent workflow for a stock symbol.
        Utilizes SQLite incremental cache if outputs are fresh (<12h).
        Executes all 6 analyst agents in parallel for maximum speed!
        """
        symbol = symbol.upper()

        # Make sure stored candles reach the last completed NSE session. Network-free when already up to date,
        # so Re-Analyze and batch runs always analyse current data instead of whatever was stored last week.
        try:
            self.hist_engine.sync_symbol_data(symbol)
        except Exception as e:
            safe_print(f"  ⚠️ Warning: price sync failed for {symbol} ({e}); analysing stored candles")
        latest_candle = self.cache_manager.get_latest_candle_date(symbol)

        # Check incremental cache first unless force_refresh is True
        if not force_refresh:
            cached_synth = self.cache_manager.get_latest_agent_output(symbol, "Master Prediction Synthesizer Agent", max_age_hours=12)
            # Serve the cache only if it was built on the same newest candle (a newer session invalidates it) and
            # no agent failed (a "degraded" result is recomputed instead of being served for 12h)
            if (cached_synth
                    and cached_synth.get("as_of_date") == latest_candle
                    and not (cached_synth.get("data_quality") or {}).get("failed_agents")):
                safe_print(f"⚡ [Cache Hit] Returning incremental cached prediction for {symbol}")
                return cached_synth

        safe_print(f"\n🤖 [Pipeline] Starting multi-agent analysis for {symbol} ({company_name})...")
        start_time = time.time()

        # Helper functions for parallel tasks
        def run_hist():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 1/6] Running Historical Quant RAG Agent...")
            t0 = time.time()
            out = self.hist_agent.run(symbol)
            self.cache_manager.save_agent_output(symbol, "Historical Data RAG Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 1/6] Historical RAG Agent completed in {time.time()-t0:.2f}s")
            return "historical_rag", out

        def run_tech():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 2/6] Computing Technical Indicators Agent...")
            t0 = time.time()
            out = self.tech_agent.run(symbol)
            self.cache_manager.save_agent_output(symbol, "Technical Analysis Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 2/6] Technical Analysis Agent completed in {time.time()-t0:.2f}s")
            return "technical", out

        def run_news():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 3/6] Fetching Live Web News & Sentiment Agent...")
            t0 = time.time()
            out = self.news_agent.run(symbol, company_name)
            self.cache_manager.save_agent_output(symbol, "News & Sentiment Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 3/6] News & Sentiment Agent completed in {time.time()-t0:.2f}s")
            return "news_sentiment", out

        def run_macro():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 4/6] Querying Global Macro Market Sentiment Agent...")
            t0 = time.time()
            out = self.macro_agent.run(symbol)
            self.cache_manager.save_agent_output(symbol, "Global Macro Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 4/6] Global Macro Agent completed in {time.time()-t0:.2f}s")
            return "macro", out

        def run_fund():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 5/6] Analyzing Fundamental Valuation Agent...")
            t0 = time.time()
            out = self.fund_agent.run(symbol, sector=sector)
            self.cache_manager.save_agent_output(symbol, "Fundamental Analyst Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 5/6] Fundamental Analyst Agent completed in {time.time()-t0:.2f}s")
            return "fundamental", out

        def run_risk():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 6/6] Computing Risk & Volatility Bounds Agent...")
            t0 = time.time()
            out = self.risk_agent.run(symbol)
            self.cache_manager.save_agent_output(symbol, "Risk & Volatility Agent", out)
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Done 6/6] Risk & Volatility Agent completed in {time.time()-t0:.2f}s")
            return "risk", out

        # Step 1: Execute all 6 analyst agents concurrently in parallel (bounded wait)
        agent_outputs = {}
        failed_agents = []
        tasks = {
            "historical_rag": run_hist,
            "technical": run_tech,
            "news_sentiment": run_news,
            "macro": run_macro,
            "fundamental": run_fund,
            "risk": run_risk,
        }
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS)
        futures = {executor.submit(fn): name for name, fn in tasks.items()}
        try:
            for future in concurrent.futures.as_completed(futures, timeout=AGENT_TIMEOUT_SECONDS):
                name = futures[future]
                try:
                    key, out = future.result()
                    agent_outputs[key] = out
                except Exception as e:
                    failed_agents.append(name)
                    safe_print(f"  ⚠️ Warning: Agent '{name}' failed for {symbol}: {e}")
        except concurrent.futures.TimeoutError:
            for future, name in futures.items():
                if not future.done():
                    failed_agents.append(name)
                    safe_print(f"  ⚠️ Warning: Agent '{name}' timed out after {AGENT_TIMEOUT_SECONDS}s for {symbol}")
        finally:
            # Don't block on a hung agent thread; queued-but-unstarted work is cancelled
            executor.shutdown(wait=False, cancel_futures=True)

        # Step 2: Master Prediction Synthesizer
        if VERBOSE_LOGGING:
            safe_print(f"  └─ [Synthesis Phase] Master Synthesizer combining all 6 agent outputs...")
        
        t_synth = time.time()
        final_synth = self.synth_agent.run(symbol, company_name, agent_outputs, sector=sector)
        final_synth["data_quality"] = {
            "failed_agents": sorted(failed_agents),
            "agents_ok": sorted(agent_outputs.keys()),
        }
        final_synth["as_of_date"] = latest_candle
        
        if VERBOSE_LOGGING:
            safe_print(f"  └─ [Complete] Total multi-agent parallel runtime: {time.time()-start_time:.2f}s (Synthesis: {time.time()-t_synth:.2f}s)")

        # Check previous verdict before overwriting cache so we can emit verdict-change alerts
        prev_synth = self.cache_manager.get_latest_agent_output(symbol, "Master Prediction Synthesizer Agent", max_age_hours=720)
        old_verdict = ((prev_synth or {}).get("structured_signal") or {}).get("action_verdict")
        new_verdict = (final_synth.get("structured_signal") or {}).get("action_verdict")

        # Save Synthesizer output in incremental cache
        self.cache_manager.save_agent_output(symbol, "Master Prediction Synthesizer Agent", final_synth)

        try:
            from tools import events_bus
            if old_verdict and new_verdict and old_verdict != new_verdict:
                events_bus.publish("verdict_change", {
                    "symbol": symbol,
                    "old_verdict": old_verdict,
                    "new_verdict": new_verdict,
                    "price": final_synth.get("last_price"),
                    "message": f"{symbol} verdict changed: {old_verdict} -> {new_verdict}",
                })
            elif new_verdict:
                events_bus.publish("analysis_done", {
                    "symbol": symbol,
                    "verdict": new_verdict,
                    "price": final_synth.get("last_price"),
                    "message": f"{symbol} analyzed: {new_verdict} @ Rs.{final_synth.get('last_price')}",
                })
        except Exception:
            pass

        # Record the call so it can be scored against what the stock actually did (tools/outcome_tracker.py)
        try:
            record = build_prediction_record(symbol, final_synth, latest_candle)
            if record:
                self.cache_manager.log_prediction(record)
        except Exception as e:
            safe_print(f"  ⚠️ Warning: could not log prediction for {symbol}: {e}")

        return final_synth
