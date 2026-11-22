"""
Prediction tracking: log every verdict, then score it against what the stock actually did.

Lookahead-free rules:
  * A prediction is ONLY scored on daily candles strictly AFTER max(as_of_date, effective made_at date).
    (If made pre-market < 09:15 IST, that day's session is still ahead; otherwise scoring starts next session.)
  * Split/bonus re-baselining checks rescale OPEN target/stop/price levels if historical candles were replaced.
  * Target is touched   -> HIT_TARGET   (filled at target price)
  * Stop is touched     -> HIT_STOP     (filled at min(open, stop) on gap-down)
  * HORIZON_TRADING_DAYS candles pass without either -> EXPIRED (scored at that day's close)
  * Same-candle target & stop touches count conservatively as HIT_STOP.

Cohort & statistical hygiene:
  * HOLD calls are logged separately (`by_direction['hold']`, `by_verdict['HOLD']`) and excluded from
    actionable `overall` & `by_confidence` accuracy so flat HOLDs never dilute trading signal metrics.
  * Matured cohorts (`>= horizon_trading_days` elapsed) are reported alongside in-flight resolved calls.
  * Emits expectancy, profit factor, median return, two-sided Student t-stat & p-value, and model_version.
"""

import math
import re
import statistics
from datetime import date, datetime, time as dtime, timedelta
from typing import Any, Dict, List, Optional

from config import MODEL_VERSION
from tools import market_calendar

HORIZON_TRADING_DAYS = 15        # ~3 weeks: matches the "1-3 week swing" horizon of the short-term call
MIN_RELIABLE_SAMPLE = 30         # resolved calls needed in a bucket before its hit rate means anything
_MARKET_OPEN_IST = dtime(9, 15)

_NUM = re.compile(r"\d[\d,]*\.?\d*")


def parse_price(text: Any) -> Optional[float]:
    """First number in strings like 'Rs. 1,234.50' (None for 'N/A' / empty)."""
    if text is None or isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        return float(text) if text == text else None
    m = _NUM.search(str(text))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def _entry_bounds(text: Any):
    nums = [float(n.replace(",", "")) for n in _NUM.findall(str(text or "")) if n.replace(",", "").replace(".", "").isdigit()]
    if len(nums) >= 2:
        return min(nums[:2]), max(nums[:2])
    return None, None


def effective_scoring_start(pred: Dict[str, Any]) -> str:
    """
    Returns 'YYYY-MM-DD' boundary strictly after which candles can legally resolve a prediction.
    Prevents lookahead bias when historical bars already existed before `made_at`.
    """
    as_of = str(pred.get("as_of_date") or "")[:10]
    made_raw = pred.get("made_at")
    if not made_raw:
        return as_of
    try:
        made_txt = str(made_raw).strip()
        dt = datetime.fromisoformat(made_txt)
        if len(made_txt) > 10:
            ist_dt = (
                dt.astimezone(market_calendar.IST)
                if dt.tzinfo is not None
                else dt.replace(tzinfo=market_calendar.IST)
            )
            # Pre-market prediction (<09:15 IST) was produced before that calendar day's session opened
            if ist_dt.time() < _MARKET_OPEN_IST:
                eff_made = (ist_dt.date() - timedelta(days=1)).isoformat()
            else:
                eff_made = ist_dt.date().isoformat()
        else:
            eff_made = dt.date().isoformat()
        return max(as_of, eff_made) if as_of else eff_made
    except Exception:
        return as_of


def build_prediction_record(symbol: str, synth_output: Dict[str, Any], as_of_date: Optional[str]) -> Optional[Dict[str, Any]]:
    """Turn a synthesizer output into a prediction_log row, or None when it has no usable levels."""
    sig = (synth_output or {}).get("structured_signal") or {}
    price = parse_price((synth_output or {}).get("last_price"))
    target = parse_price(sig.get("when_to_sell_target"))
    stop = parse_price(sig.get("stop_loss"))
    if not as_of_date or price is None or price <= 0 or target is None or stop is None or target == price:
        return None
    entry_lo, entry_hi = _entry_bounds(sig.get("when_to_buy_entry"))
    return {
        "symbol": symbol,
        "made_at": market_calendar.now_ist().isoformat(),
        "as_of_date": as_of_date,
        "verdict": sig.get("action_verdict"),
        "confidence_pct": sig.get("confidence_percentage"),
        "price_at_signal": price,
        "entry_lo": entry_lo,
        "entry_hi": entry_hi,
        "target": target,
        "stop": stop,
        "evidence_score": sig.get("evidence_score"),
        "breakdown": sig.get("evidence_breakdown"),
        "horizon_days": HORIZON_TRADING_DAYS,
        "model_version": MODEL_VERSION,
        "split_adjusted_factor": 1.0,
    }


def _score(pred: Dict[str, Any], candles: List[Dict[str, Any]]):
    """Return (status, outcome_price, return_pct) or None while still open."""
    price, target, stop = pred["price_at_signal"], pred["target"], pred["stop"]
    long_side = target > price
    horizon = int(pred.get("horizon_days") or HORIZON_TRADING_DAYS)

    seen = 0
    for c in candles:
        seen += 1
        o, h, l, cl = c["OPEN_PRICE"], c["HIGH_PRICE"], c["LOW_PRICE"], c["CLOSE_PRICE"]
        if long_side:
            stop_hit, target_hit = l <= stop, h >= target
            stop_fill = min(o, stop)           # gap down through the stop fills at the open
        else:
            stop_hit, target_hit = h >= stop, l <= target
            stop_fill = max(o, stop)
        if stop_hit:                            # includes the "both in one candle" case
            outcome, status = stop_fill, "HIT_STOP"
        elif target_hit:
            outcome, status = target, "HIT_TARGET"
        elif seen >= horizon:
            outcome, status = cl, "EXPIRED"
        else:
            continue
        ret = (outcome - price) / price * 100 if long_side else (price - outcome) / price * 100
        return status, round(outcome, 2), round(ret, 2)
    return None


def _detect_split_rebase_factor(pred: Dict[str, Any], all_candles: List[Dict[str, Any]]) -> Optional[float]:
    """
    Detects whether historical_candles has been split/bonus re-adjusted since `pred` was logged.
    Returns scaling factor (new / old) when re-baselining is required, else None.
    """
    price_sig = float(pred.get("price_at_signal") or 0.0)
    if price_sig <= 0 or not all_candles:
        return None
    as_of = str(pred.get("as_of_date") or "")[:10]
    already_scaled = float(pred.get("split_adjusted_factor") or 1.0)

    as_of_close: Optional[float] = None
    split_prod = 1.0
    for c in all_candles:
        d = str(c.get("DATE") or "")[:10]
        if d == as_of:
            try:
                val = float(c.get("CLOSE_PRICE") or 0.0)
                if val > 0:
                    as_of_close = val
            except (TypeError, ValueError):
                pass
        elif d > as_of:
            try:
                sp = float(c.get("SPLITS") or 0.0)
                if sp > 0 and sp != 1.0:
                    split_prod *= sp
            except (TypeError, ValueError):
                pass

    if as_of_close is not None and as_of_close > 0:
        ratio = as_of_close / price_sig
        # Rebase if a split occurred after as_of OR stored as_of close shifted materially (>12% from corporate re-adjust)
        if abs(ratio - 1.0) > 0.12 or (split_prod != 1.0 and abs(ratio - 1.0) > 0.05):
            if 0.01 <= ratio <= 100.0:
                return round(ratio, 6)
    elif split_prod > 1.0 and abs(already_scaled - 1.0) < 1e-4:
        inv = 1.0 / split_prod
        if 0.01 <= inv <= 100.0:
            return round(inv, 6)
    return None


def resolve_open_predictions(cache_manager) -> Dict[str, int]:
    """Score every OPEN prediction strictly on post-signal candles, re-baselining split-adjusted records."""
    counts = {"HIT_TARGET": 0, "HIT_STOP": 0, "EXPIRED": 0, "still_open": 0, "rebased": 0}
    for pred in cache_manager.get_predictions("OPEN"):
        all_candles = cache_manager.get_cached_candles(pred["symbol"], limit_days=600)

        rebase_factor = _detect_split_rebase_factor(pred, all_candles)
        if rebase_factor is not None:
            updated = 0
            if hasattr(cache_manager, "rebase_open_predictions"):
                updated = cache_manager.rebase_open_predictions(
                    pred["symbol"], rebase_factor, as_of_cutoff=pred.get("as_of_date")
                )
            counts["rebased"] += max(1, updated)
            pred = dict(pred)
            pred["price_at_signal"] = round(pred["price_at_signal"] * rebase_factor, 2)
            pred["target"] = round(pred["target"] * rebase_factor, 2)
            pred["stop"] = round(pred["stop"] * rebase_factor, 2)
            if pred.get("entry_lo") is not None:
                pred["entry_lo"] = round(pred["entry_lo"] * rebase_factor, 2)
            if pred.get("entry_hi") is not None:
                pred["entry_hi"] = round(pred["entry_hi"] * rebase_factor, 2)

        start_after = effective_scoring_start(pred)
        candles = [c for c in all_candles if str(c["DATE"])[:10] > start_after]
        result = _score(pred, candles)
        if result is None:
            counts["still_open"] += 1
            continue
        status, outcome, ret = result
        cache_manager.resolve_prediction(pred["id"], status, outcome, ret, market_calendar.now_ist().isoformat())
        counts[status] += 1
    return counts


def _student_t_two_sided_p(t_stat: float, df: int) -> float:
    """
    Dependency-free two-sided Student-t p-value (composite Simpson integration for df < 60,
    normal approximation for df >= 60).
    """
    t_abs = abs(float(t_stat))
    if not math.isfinite(t_abs) or df <= 0:
        return 1.0
    if t_abs == 0.0:
        return 1.0
    if df >= 60:
        return round(min(1.0, max(0.0, math.erfc(t_abs / math.sqrt(2.0)))), 4)

    coeff = math.gamma((df + 1.0) / 2.0) / (math.sqrt(df * math.pi) * math.gamma(df / 2.0))
    n_steps = 200
    h = t_abs / n_steps

    def _pdf(x: float) -> float:
        return coeff * ((1.0 + (x * x) / df) ** (-0.5 * (df + 1.0)))

    s = _pdf(0.0) + _pdf(t_abs)
    for i in range(1, n_steps):
        s += (4.0 if i % 2 == 1 else 2.0) * _pdf(i * h)
    cdf_diff = min(0.5, max(0.0, (h / 3.0) * s))
    return round(min(1.0, max(0.0, 1.0 - 2.0 * cdf_diff)), 4)


def _direction_bucket(row: Dict[str, Any]) -> str:
    verdict = str(row.get("verdict") or "").upper().strip()
    if verdict == "HOLD":
        return "hold"
    if verdict == "SELL":
        return "short"
    if verdict in ("BUY", "ACCUMULATE"):
        return "long"
    price = row.get("price_at_signal")
    target = row.get("target")
    if price is not None and target is not None:
        return "long" if target > price else "short"
    return "hold"


def _bucket_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    hit_t = sum(1 for r in rows if r["status"] == "HIT_TARGET")
    hit_s = sum(1 for r in rows if r["status"] == "HIT_STOP")
    exp = sum(1 for r in rows if r["status"] == "EXPIRED")

    rets = [float(r["return_pct"] or 0.0) for r in rows]
    win_rets = [x for x in rets if x > 0]
    loss_rets = [x for x in rets if x <= 0]

    avg = sum(rets) / n
    med = statistics.median(rets)
    avg_win = (sum(win_rets) / len(win_rets)) if win_rets else 0.0
    avg_loss = (sum(loss_rets) / len(loss_rets)) if loss_rets else 0.0  # negative or 0

    sum_win = sum(win_rets)
    sum_loss = abs(sum(loss_rets))
    if sum_loss > 0:
        profit_factor: Optional[float] = round(sum_win / sum_loss, 2)
    elif sum_win > 0:
        profit_factor = 99.99
    else:
        profit_factor = 0.0

    std_ret: Optional[float] = round(statistics.stdev(rets), 3) if n > 1 else None
    t_stat: Optional[float] = None
    p_value: Optional[float] = None
    if n > 1:
        raw_std = statistics.stdev(rets)
        if raw_std > 1e-9:
            t_val = avg / (raw_std / math.sqrt(n))
            t_stat = round(t_val, 3)
            p_value = _student_t_two_sided_p(t_val, n - 1)
        elif avg != 0.0:
            t_stat = 99.99 if avg > 0 else -99.99
            p_value = 0.0

    return {
        "n": n,
        "hit_target": hit_t,
        "hit_stop": hit_s,
        "expired": exp,
        "target_rate_pct": round(hit_t / n * 100, 1),
        "win_rate_pct": round(len(win_rets) / n * 100, 1),
        "avg_return_pct": round(avg, 2),
        "expectancy_pct": round(avg, 3),
        "median_return_pct": round(med, 2),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "profit_factor": profit_factor,
        "std_return_pct": std_ret,
        "t_stat": t_stat,
        "p_value": p_value,
        "statistically_significant": bool(n >= MIN_RELIABLE_SAMPLE and p_value is not None and p_value < 0.05 and avg > 0),
        "reliable": n >= MIN_RELIABLE_SAMPLE,
    }


def _conf_bucket(pct: Any) -> str:
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return "unknown"
    return "75+" if p >= 75 else "55-74" if p >= 55 else "<55"


def _latest_market_date(cache_manager) -> str:
    try:
        with cache_manager._get_connection() as conn:
            row = conn.execute("SELECT MAX(date) FROM historical_candles").fetchone()
            if row and row[0]:
                return str(row[0])[:10]
    except Exception:
        pass
    try:
        return market_calendar.last_completed_session().isoformat()
    except Exception:
        return date.today().isoformat()


def _is_matured(row: Dict[str, Any], as_of_market_dt: date) -> bool:
    start_str = effective_scoring_start(row)
    if not start_str:
        return False
    try:
        start_d = datetime.strptime(start_str[:10], "%Y-%m-%d").date()
        horizon = int(row.get("horizon_days") or HORIZON_TRADING_DAYS)
        return market_calendar.trading_days_after(start_d, as_of_market_dt) >= horizon
    except Exception:
        return False


def compute_accuracy(
    cache_manager,
    model_version: Optional[str] = None,
    as_of_market_date: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Aggregates prediction accuracy cleanly:
    - Excludes HOLD calls from `overall` and `by_confidence` (preventing neutral-band contamination)
    - Separates matured cohorts (`>= horizon_trading_days` elapsed) from in-flight resolved calls
    - Breaks out long / short / hold directions, model versions, expectancy, profit factor & t-test significance.
    """
    all_rows = cache_manager.get_predictions(model_version=model_version)
    resolved_all = [r for r in all_rows if r["status"] != "OPEN"]
    actionable_resolved = [r for r in resolved_all if _direction_bucket(r) != "hold"]

    by_verdict: Dict[str, List[Dict[str, Any]]] = {}
    by_conf: Dict[str, List[Dict[str, Any]]] = {}
    by_dir: Dict[str, List[Dict[str, Any]]] = {"long": [], "short": [], "hold": []}
    by_conf_dir: Dict[str, Dict[str, List[Dict[str, Any]]]] = {"long": {}, "short": {}, "hold": {}}
    by_version: Dict[str, List[Dict[str, Any]]] = {}

    for r in resolved_all:
        verdict_k = r["verdict"] or "?"
        dir_k = _direction_bucket(r)
        conf_k = _conf_bucket(r["confidence_pct"])
        mv_k = str(r.get("model_version") or "legacy")

        by_verdict.setdefault(verdict_k, []).append(r)
        by_dir[dir_k].append(r)
        by_conf_dir[dir_k].setdefault(conf_k, []).append(r)

        if dir_k != "hold":
            by_conf.setdefault(conf_k, []).append(r)
            by_version.setdefault(mv_k, []).append(r)

    latest_mkt_str = (as_of_market_date or _latest_market_date(cache_manager))[:10]
    try:
        latest_mkt_dt = datetime.strptime(latest_mkt_str, "%Y-%m-%d").date()
    except Exception:
        latest_mkt_dt = date.today()
        latest_mkt_str = latest_mkt_dt.isoformat()

    matured_rows = [r for r in all_rows if _is_matured(r, latest_mkt_dt)]
    matured_resolved = [r for r in matured_rows if r["status"] != "OPEN"]
    matured_actionable = [r for r in matured_resolved if _direction_bucket(r) != "hold"]
    matured_by_dir: Dict[str, List[Dict[str, Any]]] = {"long": [], "short": [], "hold": []}
    matured_by_verdict: Dict[str, List[Dict[str, Any]]] = {}
    matured_by_conf: Dict[str, List[Dict[str, Any]]] = {}
    for r in matured_resolved:
        dir_k = _direction_bucket(r)
        matured_by_dir[dir_k].append(r)
        matured_by_verdict.setdefault(r["verdict"] or "?", []).append(r)
        if dir_k != "hold":
            matured_by_conf.setdefault(_conf_bucket(r["confidence_pct"]), []).append(r)

    in_flight_actionable = [
        r for r in actionable_resolved if not _is_matured(r, latest_mkt_dt)
    ]

    return {
        "logged": len(all_rows),
        "open": len(all_rows) - len(resolved_all),
        "resolved": len(resolved_all),
        "actionable_resolved": len(actionable_resolved),
        "overall": _bucket_stats(actionable_resolved),
        "by_direction": {k: _bucket_stats(v) for k, v in by_dir.items()},
        "by_verdict": {k: _bucket_stats(v) for k, v in sorted(by_verdict.items())},
        "by_confidence": {k: _bucket_stats(v) for k, v in sorted(by_conf.items())},
        "by_confidence_by_direction": {
            d_k: {c_k: _bucket_stats(rows) for c_k, rows in sorted(buckets.items())}
            for d_k, buckets in by_conf_dir.items()
        },
        "by_model_version": {k: _bucket_stats(v) for k, v in sorted(by_version.items())},
        "matured_cohort": {
            "as_of_market_date": latest_mkt_str,
            "logged": len(matured_rows),
            "resolved": len(matured_resolved),
            "open": len(matured_rows) - len(matured_resolved),
            "actionable_resolved": len(matured_actionable),
            "overall": _bucket_stats(matured_actionable),
            "by_direction": {k: _bucket_stats(v) for k, v in matured_by_dir.items()},
            "by_verdict": {k: _bucket_stats(v) for k, v in sorted(matured_by_verdict.items())},
            "by_confidence": {k: _bucket_stats(v) for k, v in sorted(matured_by_conf.items())},
        },
        "in_flight_resolved": {
            "n": len(in_flight_actionable),
            "stats": _bucket_stats(in_flight_actionable),
        },
        "as_of_market_date": latest_mkt_str,
        "model_version_filter": model_version,
        "horizon_trading_days": HORIZON_TRADING_DAYS,
        "min_reliable_sample": MIN_RELIABLE_SAMPLE,
        "note": (
            "Actionable overall & confidence stats exclude HOLD calls (`by_direction['hold']`). "
            f"Matured cohorts require >= {HORIZON_TRADING_DAYS} trading days post-signal; "
            f"statistical reliability requires >= {MIN_RELIABLE_SAMPLE} calls and p < 0.05."
        ),
    }
