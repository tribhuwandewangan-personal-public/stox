"""
Phase 3: Historical Catalyst Backtester.

Evaluates stored or supplied corporate announcements against SQLite historical_candles
to measure 5D / 20D / 60D forward returns, peak gains, breakout hit rate (+10% within 30d),
days-to-breakout, and sustained-rally vs temporary-spike ratios across categories and tiers.
"""

from __future__ import annotations

import statistics
from typing import Any, Dict, List, Optional

import pandas as pd

from storage.cache_manager import CacheManager
from tools.historical_data_tools import HistoricalDataEngine


def run_catalyst_backtest(
    cache_manager: Optional[CacheManager] = None,
    events: Optional[List[Dict[str, Any]]] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """
    Backtests catalyst events against actual post-announcement price trajectories.
    """
    cm = cache_manager or CacheManager()
    hist_engine = HistoricalDataEngine(cache_manager=cm)
    target_events = events if events is not None else cm.get_catalyst_events(limit=limit)

    evaluated: List[Dict[str, Any]] = []
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    by_tier: Dict[str, List[Dict[str, Any]]] = {}

    for ev in target_events:
        sym = str(ev.get("symbol") or "").upper().strip()
        ann_dt = str(ev.get("announced_at") or "")[:10]
        if not sym or not ann_dt or sym == "GOVT_POLICY":
            continue

        df = hist_engine.load_symbol_history(sym, limit_days=1200)
        if df is None or df.empty:
            continue
        df = df.copy()
        df["DATE_STR"] = pd.to_datetime(df["DATE"]).dt.strftime("%Y-%m-%d")
        after = df[df["DATE_STR"] >= ann_dt].reset_index(drop=True)
        if len(after) < 6:
            continue

        base_close = float(after.iloc[0]["CLOSE_PRICE"])
        if base_close <= 0:
            continue

        ret_5d = round(((float(after.iloc[min(5, len(after) - 1)]["CLOSE_PRICE"]) - base_close) / base_close) * 100.0, 2)
        ret_20d = round(((float(after.iloc[min(20, len(after) - 1)]["CLOSE_PRICE"]) - base_close) / base_close) * 100.0, 2) if len(after) > 10 else None
        ret_60d = round(((float(after.iloc[min(60, len(after) - 1)]["CLOSE_PRICE"]) - base_close) / base_close) * 100.0, 2) if len(after) > 30 else None

        win_30 = after.iloc[:min(31, len(after))]
        peak_30d = float(win_30["HIGH_PRICE"].max())
        peak_gain_30d = round(((peak_30d - base_close) / base_close) * 100.0, 2)

        # Days to +10% breakout
        days_to_breakout = None
        for idx in range(1, len(win_30)):
            if float(win_30.iloc[idx]["HIGH_PRICE"]) >= base_close * 1.10:
                days_to_breakout = idx
                break

        sustained = bool(ret_20d is not None and ret_20d >= 5.0 and peak_gain_30d >= 8.0)

        row = {
            "symbol": sym,
            "announced_at": ann_dt,
            "category": ev.get("category") or "ROUTINE",
            "tier": ev.get("tier") or "C",
            "total_score": ev.get("total_score"),
            "ret_5d_pct": ret_5d,
            "ret_20d_pct": ret_20d,
            "ret_60d_pct": ret_60d,
            "peak_gain_30d_pct": peak_gain_30d,
            "days_to_breakout": days_to_breakout,
            "sustained_rally": sustained,
        }
        evaluated.append(row)
        by_category.setdefault(row["category"], []).append(row)
        by_tier.setdefault(row["tier"], []).append(row)

    def _agg(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        r5 = [r["ret_5d_pct"] for r in rows if r["ret_5d_pct"] is not None]
        r20 = [r["ret_20d_pct"] for r in rows if r["ret_20d_pct"] is not None]
        r60 = [r["ret_60d_pct"] for r in rows if r["ret_60d_pct"] is not None]
        dtb = [r["days_to_breakout"] for r in rows if r["days_to_breakout"] is not None]
        sustained_cnt = sum(1 for r in rows if r["sustained_rally"])
        return {
            "count": len(rows),
            "avg_ret_5d_pct": round(statistics.mean(r5), 2) if r5 else None,
            "avg_ret_20d_pct": round(statistics.mean(r20), 2) if r20 else None,
            "avg_ret_60d_pct": round(statistics.mean(r60), 2) if r60 else None,
            "breakout_hit_rate_pct": round((len(dtb) / len(rows)) * 100.0, 1) if rows else 0.0,
            "avg_days_to_breakout": round(statistics.mean(dtb), 1) if dtb else None,
            "sustained_rally_rate_pct": round((sustained_cnt / len(rows)) * 100.0, 1) if rows else 0.0,
        }

    return {
        "total_evaluated": len(evaluated),
        "summary": _agg(evaluated),
        "by_category": {k: _agg(v) for k, v in by_category.items()},
        "by_tier": {k: _agg(v) for k, v in by_tier.items()},
        "results": evaluated[:100],
    }
