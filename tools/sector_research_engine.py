"""
Dynamic LLM-Powered Sector & Industry Research Engine.

Architecture:
1. Qualitative Sector & Value-Chain Research (Google Gemini LLM ONLY):
   - Breaks down any sector/industry into supply-chain / value-chain components.
   - Identifies Market Leaders, Bottlenecks (chokepoints with pricing power),
     and Critical Beneficiaries, plus NSE-listed ticker symbols.
2. Dynamic Ticker Validation (no static symbols.json):
   - Validates Gemini-suggested NSE tickers via HistoricalDataEngine / yfinance.
3. Quantitative Stock Analysis (Existing Stox Rule-Based Tools ONLY):
   - Runs MultiAgentWorkflow (Historical RAG, Technical, News, Macro, Fundamental, Risk,
     Master Synthesizer) on each validated symbol to compute deterministic scores and verdicts.
4. SQLite Persistence:
   - Stores all sector runs, value-chain components, and scored stocks in storage/cache.db.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

import requests

from storage.cache_manager import CacheManager


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

ROLE_BONUSES = {
    "bottleneck": 6.0,
    "critical_beneficiary": 4.0,
    "market_leader": 3.0,
    "challenger": 0.0,
}

_SECTOR_PROMPT_TEMPLATE = """You are a senior institutional Indian equity research analyst specializing in NSE-listed companies and industrial value-chain economics.
Perform a DEEP, exhaustive, institutional-grade industry and value-chain research report for:

SECTOR / INDUSTRY QUERY: "{sector_query}"

Go far beyond surface-level names. Decompose the entire industry value chain into 6 to 9 granular layers (from upstream raw materials/feedstock, specialized sub-components & IP, bottleneck manufacturing equipment, Tier-1 OEMs, EPC/system integrators, to downstream operators & aftermarket).

For every layer, analyze:
- Where the profit pool sits, pricing power, entry barriers (certifications, gestation period, capex/IP), and why supply is constrained if it is a bottleneck.
- The most relevant NSE-listed Indian companies (exact NSE ticker WITHOUT '.NS' or '.BO', e.g. 'CGPOWER', 'BEL', 'POWERGRID', 'TRENT', 'ABB', 'SIEMENS', 'CUMMINSIND').
- Classify each company's role strictly as one of:
  - "bottleneck": Controls a scarce, high-barrier chokepoint or critical input where supply is constrained and margins expand.
  - "critical_beneficiary": Disproportionate earnings/order-book beneficiary of sector capex, import substitution, or policy shift.
  - "market_leader": Dominant market share, scale, balance sheet, and pricing power in this layer.
  - "challenger": High-growth pure-play or emerging challenger gaining share.

Return ONLY valid JSON matching this exact schema:
{{
  "normalized_sector": "Clean canonical sector name",
  "overview": {{
    "thesis": "3-5 sentence deep structural thesis explaining why this sector matters now and where value accrues",
    "tam_and_growth": "Addressable market size in India/exports and expected multi-year growth rate (CAGR)",
    "unit_economics": "Key margin drivers, operating leverage, working capital dynamics, and raw material pass-through",
    "policy_and_regulatory_tailwinds": ["PLI / policy / tariff / indigenization tailwind 1", "tailwind 2"],
    "bottleneck_summary": "Explicit identification of the #1 chokepoint in the value chain and who captures the scarcity rent",
    "demand_drivers": ["concrete driver 1", "concrete driver 2", "concrete driver 3"],
    "capex_cycle_stage": "Early | Expansion | Peak | Consolidation",
    "key_risks": ["risk 1", "risk 2", "risk 3"],
    "bear_case_triggers": ["what could break the thesis 1", "trigger 2"]
  }},
  "components": [
    {{
      "name": "Value-Chain Layer Name",
      "description": "Detailed explanation of what this layer does and its strategic importance",
      "is_bottleneck_layer": true,
      "pricing_power": "High | Medium | Low",
      "entry_barriers": "Specific barriers: IP, approvals, capex intensity, lead times, switching costs",
      "capacity_bottleneck_reason": "Why supply cannot scale rapidly (or 'N/A' if commoditized)",
      "value_capture_score": 9,
      "companies": [
        {{
          "symbol": "NSE_TICKER",
          "company_name": "Full Company Name",
          "role_tag": "bottleneck | critical_beneficiary | market_leader | challenger",
          "moat_type": "Capacity Scarcity | Technology/IP | Scale & Distribution | Regulatory/Certification | Cost Advantage",
          "revenue_purity": "Pure-Play (>70%) | Core Segment (30-70%) | Diversified (<30%)",
          "bottleneck_exposure": "Direct Chokepoint | High Beneficiary | Moderate | Downstream",
          "rationale": "2-3 sentence deep explanation of competitive positioning, pricing power, and order-book/capex leverage"
        }}
      ]
    }}
  ]
}}
"""


def _load_gemini_api_key() -> str:
    """Reads GEMINI_API_KEY from environment or project-root .env file."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key:
        return key
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == "GEMINI_API_KEY":
                        return v.strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
    """Parses JSON from Gemini output, stripping markdown code fences if present."""
    text = (raw_text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _to_float(val: Any) -> Optional[float]:
    try:
        if val is None:
            return None
        f = float(val)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def call_gemini_sector_research(
    sector_query: str,
    api_key: str,
    model: str = DEFAULT_GEMINI_MODEL,
    use_search: bool = False,
    timeout: int = 60,
) -> Dict[str, Any]:
    """
    Calls Google Gemini REST API to perform sector/value-chain decomposition.
    Uses low-cost lite models and minimal thinking effort by default.
    """
    candidate_models = list(dict.fromkeys([
        model,
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-lite",
        "gemini-2.0-flash",
        "gemini-3.8-flash",
    ]))
    search_modes = [True, False] if use_search else [False]
    last_error = "Gemini API request failed"

    for m in candidate_models:
        url = f"{GEMINI_API_BASE}/{m}:generateContent?key={api_key}"
        for search_on in search_modes:
            gen_cfg: Dict[str, Any] = {
                "temperature": 0.15,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            }
            if "2.5" in m or "3." in m:
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
            payload: Dict[str, Any] = {
                "contents": [{"parts": [{"text": _SECTOR_PROMPT_TEMPLATE.format(sector_query=sector_query)}]}],
                "generationConfig": gen_cfg,
            }
            if search_on:
                payload["tools"] = [{"google_search": {}}]

            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code < 400:
                data = resp.json()
                candidates = data.get("candidates") or []
                if not candidates:
                    raise RuntimeError("Gemini returned no candidates for sector research")
                parts = (candidates[0].get("content") or {}).get("parts") or []
                raw_text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
                if not raw_text:
                    raise RuntimeError("Gemini returned an empty response")
                return _extract_json_payload(raw_text)

            last_error = f"Gemini API error ({resp.status_code}) on {m}: {resp.text[:300]}"
            if resp.status_code in (400, 404, 429):
                continue
            raise RuntimeError(last_error)

    raise RuntimeError(
        f"{last_error}. Check your Google AI Studio quota/billing at https://ai.dev/rate-limit "
        f"or set GEMINI_MODEL in .env to an active model on your plan."
    )


class SectorResearchEngine:
    """
    Coordinates Gemini sector/value-chain discovery with Stox's existing deterministic
    fundamental & technical analysis tools, persisting all results in SQLite.
    """

    def __init__(
        self,
        cache_manager: Optional[CacheManager] = None,
        workflow_factory: Optional[Callable[[], Any]] = None,
        gemini_caller: Optional[Callable[..., Dict[str, Any]]] = None,
    ):
        self.cache_manager = cache_manager or CacheManager()
        self._workflow_factory = workflow_factory
        self._gemini_caller = gemini_caller or call_gemini_sector_research

    def _get_workflow(self):
        if self._workflow_factory is not None:
            return self._workflow_factory()
        from graph import MultiAgentWorkflow
        return MultiAgentWorkflow(cache_manager=self.cache_manager)

    def _validate_nse_symbol(self, symbol: str, workflow: Any) -> bool:
        """Dynamically validates an NSE symbol using HistoricalDataEngine (no symbols.json)."""
        sym = re.sub(r"\.(NS|BO)$", "", str(symbol or "").upper().strip())
        if not sym or not re.match(r"^[A-Z0-9&-]{1,20}$", sym):
            return False
        try:
            hist_engine = getattr(workflow, "hist_engine", None)
            if hist_engine is not None:
                df = hist_engine.load_symbol_history(sym, limit_days=30)
                if df is not None and not df.empty:
                    return True
        except Exception:
            pass
        return False

    def _score_symbol_with_existing_tools(
        self,
        symbol: str,
        company_name: str,
        sector_name: str,
        role_tag: str,
        workflow: Any,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Runs Stox's existing rule-based MultiAgentWorkflow (no LLM) on a symbol
        and extracts fundamental, technical, and composite scores.
        """
        validated = self._validate_nse_symbol(symbol, workflow)
        if not validated:
            return {
                "validated": False,
                "fundamental_score": None,
                "technical_score": None,
                "composite_score": None,
                "verdict": "INVALID_SYMBOL",
                "quant_snapshot": {"error": "Symbol could not be validated on NSE/BSE feed"},
            }

        synth = workflow.run_analysis(
            symbol,
            company_name=company_name,
            sector=sector_name,
            force_refresh=force_refresh,
        ) or {}

        structured = synth.get("structured_signal") or {}
        verdict = structured.get("action_verdict") or "HOLD"
        evidence_score = _to_float(structured.get("evidence_score")) or 0.0

        fund_out = self.cache_manager.get_latest_agent_output(symbol, "Fundamental Analyst Agent") or {}
        tech_out = self.cache_manager.get_latest_agent_output(symbol, "Technical Analysis Agent") or {}

        fund_score = _to_float(
            fund_out.get("fundamental_score")
            or (fund_out.get("forensic_analysis") or {}).get("overall_score")
            or (fund_out.get("raw_fundamentals") or {}).get("fundamental_score")
        )
        tech_score = _to_float(
            tech_out.get("technical_score")
            or (tech_out.get("raw_indicators") or {}).get("technical_score")
        )

        base_quant = evidence_score
        if fund_score is not None and tech_score is not None:
            base_quant = round(0.55 * fund_score + 0.45 * tech_score, 2)
        elif fund_score is not None:
            base_quant = round(0.6 * fund_score + 0.4 * evidence_score, 2)
        elif tech_score is not None:
            base_quant = round(0.6 * tech_score + 0.4 * evidence_score, 2)

        role_bonus = ROLE_BONUSES.get(role_tag, 0.0)
        composite_score = round(base_quant + role_bonus, 2)

        lt = structured.get("long_term_signal") or {}
        snapshot = {
            "last_price": synth.get("last_price"),
            "confidence_rating": structured.get("confidence_rating"),
            "evidence_score": evidence_score,
            "entry_range": structured.get("when_to_buy_entry"),
            "target_price": structured.get("when_to_sell_target"),
            "stop_loss": structured.get("stop_loss"),
            "long_term_verdict": lt.get("long_term_verdict"),
            "long_term_target": lt.get("long_term_target"),
            "key_rationale": structured.get("key_rationale"),
            "role_bonus": role_bonus,
        }

        return {
            "validated": True,
            "fundamental_score": fund_score,
            "technical_score": tech_score,
            "composite_score": composite_score,
            "verdict": verdict,
            "quant_snapshot": snapshot,
        }

    def run_research(
        self,
        sector_query: str,
        use_search: bool = True,
        model: str = DEFAULT_GEMINI_MODEL,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        1. Calls Gemini to decompose `sector_query` into value-chain components & NSE tickers.
        2. Saves the run & components in SQLite.
        3. Runs existing Stox deterministic analysis tools on every discovered ticker.
        4. Returns the full persisted run with ranked stocks.
        """
        query = (sector_query or "").strip()
        if not query:
            raise ValueError("sector_query is required")

        api_key = _load_gemini_api_key()
        if not api_key and self._gemini_caller is call_gemini_sector_research:
            run_id = self.cache_manager.create_sector_research_run(
                sector_query=query,
                normalized_sector=query,
                model_used=model,
                status="missing_api_key",
                error_message="GEMINI_API_KEY is not configured. Add GEMINI_API_KEY to your .env or environment variables to run LLM sector research.",
            )
            return self.cache_manager.get_sector_research_run(run_id) or {"id": run_id, "status": "missing_api_key"}

        try:
            gemini_data = self._gemini_caller(
                sector_query=query,
                api_key=api_key,
                model=model,
                use_search=use_search,
            )
        except Exception as e:
            run_id = self.cache_manager.create_sector_research_run(
                sector_query=query,
                normalized_sector=query,
                model_used=model,
                status="error",
                error_message=str(e),
            )
            return self.cache_manager.get_sector_research_run(run_id) or {"id": run_id, "status": "error", "error_message": str(e)}

        normalized_sector = str(gemini_data.get("normalized_sector") or query).strip()
        overview = gemini_data.get("overview") or {}
        components = gemini_data.get("components") or []

        run_id = self.cache_manager.create_sector_research_run(
            sector_query=query,
            normalized_sector=normalized_sector,
            model_used=model,
            overview=overview,
            components=components,
            status="ready",
        )

        workflow = self._get_workflow()
        scored_rows: List[Dict[str, Any]] = []
        seen_pairs = set()

        for comp in components:
            comp_name = str(comp.get("name") or "Core Segment").strip()
            for co in (comp.get("companies") or []):
                raw_sym = str(co.get("symbol") or "").upper().strip()
                sym = re.sub(r"\.(NS|BO)$", "", raw_sym)
                if not sym or (sym, comp_name) in seen_pairs:
                    continue
                seen_pairs.add((sym, comp_name))

                role_tag = str(co.get("role_tag") or "challenger").strip().lower()
                if role_tag not in ROLE_BONUSES:
                    role_tag = "challenger"
                company_name = str(co.get("company_name") or sym).strip()
                rationale = str(co.get("rationale") or "").strip()

                metrics = self._score_symbol_with_existing_tools(
                    symbol=sym,
                    company_name=company_name,
                    sector_name=normalized_sector,
                    role_tag=role_tag,
                    workflow=workflow,
                    force_refresh=force_refresh,
                )
                snap = metrics.get("quant_snapshot") or {}
                snap["moat_type"] = str(co.get("moat_type") or "").strip()
                snap["revenue_purity"] = str(co.get("revenue_purity") or "").strip()
                snap["bottleneck_exposure"] = str(co.get("bottleneck_exposure") or "").strip()
                metrics["quant_snapshot"] = snap
                scored_rows.append({
                    "symbol": sym,
                    "company_name": company_name,
                    "component_name": comp_name,
                    "role_tag": role_tag,
                    "rationale": rationale,
                    **metrics,
                })

        self.cache_manager.save_sector_value_chain_stocks(run_id, scored_rows)
        out = self.cache_manager.get_sector_research_run(run_id) or {"id": run_id, "status": "ready"}
        try:
            from tools import events_bus
            stocks = out.get("stocks") or []
            top = stocks[0] if stocks else None
            top_txt = f" Top pick: {top['symbol']} ({top['verdict']}, {top['composite_score']})" if top else ""
            events_bus.publish("sector_research_done", {
                "symbol": top["symbol"] if top else None,
                "sector": normalized_sector,
                "count": len(stocks),
                "message": f"Sector research ready for '{normalized_sector}' ({len(stocks)} stocks).{top_txt}",
            })
        except Exception:
            pass
        return out

    def rescore_run(self, run_id: int, force_refresh: bool = True) -> Optional[Dict[str, Any]]:
        """
        Re-runs ONLY Stox's existing deterministic fundamental/technical analysis
        on tickers already stored in SQLite for `run_id` (zero Gemini calls).
        """
        run = self.cache_manager.get_sector_research_run(run_id)
        if not run:
            return None

        workflow = self._get_workflow()
        normalized_sector = run.get("normalized_sector") or run.get("sector_query") or ""
        updated_rows: List[Dict[str, Any]] = []

        for st in (run.get("stocks") or []):
            sym = st["symbol"]
            metrics = self._score_symbol_with_existing_tools(
                symbol=sym,
                company_name=st.get("company_name") or sym,
                sector_name=normalized_sector,
                role_tag=st.get("role_tag") or "challenger",
                workflow=workflow,
                force_refresh=force_refresh,
            )
            updated_rows.append({
                "symbol": sym,
                "company_name": st.get("company_name") or sym,
                "component_name": st.get("component_name") or "",
                "role_tag": st.get("role_tag") or "challenger",
                "rationale": st.get("rationale") or "",
                **metrics,
            })

        self.cache_manager.save_sector_value_chain_stocks(run_id, updated_rows)
        return self.cache_manager.get_sector_research_run(run_id)
