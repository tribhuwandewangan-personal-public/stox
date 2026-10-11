"""
LangGraph Multi-Agent Orchestrator.
Defines the StateGraph execution workflow, dispatching stock symbols from symbols.json,
checking incremental SQLite cache, invoking specialized analyst agents,
and running the Master Synthesizer Agent.
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
from tools.bhavcopy_rag import BhavcopyRAGEngine
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

# LangGraph State Schema
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
from config import VERBOSE_LOGGING, MAX_PARALLEL_WORKERS

class MultiAgentWorkflow:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()
        
        # Engines initialized with shared SQLite cache_manager
        bhav_engine = BhavcopyRAGEngine(cache_manager=self.cache_manager)
        tech_engine = TechnicalAnalysisEngine(rag_engine=bhav_engine, cache_manager=self.cache_manager)
        news_engine = NewsSentimentEngine(cache_manager=self.cache_manager)
        macro_engine = GlobalMacroEngine(cache_manager=self.cache_manager)
        risk_engine = RiskManagementEngine(rag_engine=bhav_engine, cache_manager=self.cache_manager)

        self.hist_agent = HistoricalRAGAgent(rag_engine=bhav_engine)
        self.tech_agent = TechnicalAnalysisAgent(tech_engine=tech_engine)
        self.news_agent = NewsSentimentAgent(news_engine=news_engine)
        self.macro_agent = GlobalMacroAgent(macro_engine=macro_engine)
        self.fund_agent = FundamentalAgent()
        self.risk_agent = RiskAgent(risk_engine=risk_engine)
        self.synth_agent = MasterPredictionSynthesizerAgent()

    def run_analysis(self, symbol: str, company_name: str = "", sector: str = "", force_refresh: bool = False) -> Dict[str, Any]:
        """
        Executes multi-agent workflow for a stock symbol.
        Utilizes SQLite incremental cache if outputs are fresh (<12h).
        Executes all 6 analyst agents in parallel for maximum speed!
        """
        symbol = symbol.upper()
        
        # Check incremental cache first unless force_refresh is True
        if not force_refresh:
            cached_synth = self.cache_manager.get_latest_agent_output(symbol, "Master Prediction Synthesizer Agent", max_age_hours=12)
            if cached_synth:
                safe_print(f"⚡ [Cache Hit] Returning incremental cached prediction for {symbol}")
                return cached_synth

        safe_print(f"\n🤖 [LangGraph Pipeline] Starting multi-agent analysis for {symbol} ({company_name})...")
        start_time = time.time()

        # Helper functions for parallel tasks
        def run_hist():
            if VERBOSE_LOGGING:
                safe_print(f"  ├─ [Parallel Task 1/6] Running Historical Bhavcopy RAG Agent...")
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
            out = self.fund_agent.run(symbol)
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

        # Step 1: Execute all 6 analyst agents concurrently in parallel
        agent_outputs = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_WORKERS) as executor:
            futures = [
                executor.submit(run_hist),
                executor.submit(run_tech),
                executor.submit(run_news),
                executor.submit(run_macro),
                executor.submit(run_fund),
                executor.submit(run_risk)
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    key, out = future.result()
                    agent_outputs[key] = out
                except Exception as e:
                    safe_print(f"  ⚠️ Warning: Agent task execution error: {e}")

        # Step 2: Master Prediction Synthesizer
        if VERBOSE_LOGGING:
            safe_print(f"  └─ [Synthesis Phase] Master Synthesizer combining all 6 agent outputs...")
        
        t_synth = time.time()
        final_synth = self.synth_agent.run(symbol, company_name, agent_outputs)
        
        if VERBOSE_LOGGING:
            safe_print(f"  └─ [Complete] Total multi-agent parallel runtime: {time.time()-start_time:.2f}s (Synthesis: {time.time()-t_synth:.2f}s)")

        # Save Synthesizer output in incremental cache
        self.cache_manager.save_agent_output(symbol, "Master Prediction Synthesizer Agent", final_synth)

        return final_synth
