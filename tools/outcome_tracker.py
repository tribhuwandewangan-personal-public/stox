"""
Prediction tracking: log every verdict, then score it against what the stock actually did.

A prediction is OPEN until, scanning the stored daily candles AFTER its as_of_date in order, either
  * the target is touched   -> HIT_TARGET   (filled at the target price)
  * the stop is touched     -> HIT_STOP     (filled at the stop, or at the open if the stock gapped through it)
  * HORIZON_TRADING_DAYS candles pass without either -> EXPIRED (scored at that day's close)
When one daily candle touches both target and stop, the stop is assumed to have been hit first (conservative:
daily data cannot show the order).

Direction is inferred from the levels: target above the signal price = long, below = short. HOLD calls are
logged too (and reported separately), so you can see whether "no action" calls were actually quiet.

Nothing here changes the model. It only measures it. Weights are never tuned automatically.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

HORIZON_TRADING_DAYS = 15        # ~3 weeks: matches the "1-3 week swing" horizon of the short-term call
MIN_RELIABLE_SAMPLE = 30         # resolved calls needed in a bucket before its hit rate means anything

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


def resolve_open_predictions(cache_manager) -> Dict[str, int]:
    """Score every OPEN prediction against stored candles. Returns counts per resulting status."""
    counts = {"HIT_TARGET": 0, "HIT_STOP": 0, "EXPIRED": 0, "still_open": 0}
    for pred in cache_manager.get_predictions("OPEN"):
        candles = [
            c for c in cache_manager.get_cached_candles(pred["symbol"], limit_days=400)
            if str(c["DATE"])[:10] > pred["as_of_date"]
        ]
        result = _score(pred, candles)
        if result is None:
            counts["still_open"] += 1
            continue
        status, outcome, ret = result
        cache_manager.resolve_prediction(pred["id"], status, outcome, ret, datetime.now().isoformat())
        counts[status] += 1
    return counts


def _bucket_stats(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    hit_t = sum(1 for r in rows if r["status"] == "HIT_TARGET")
    hit_s = sum(1 for r in rows if r["status"] == "HIT_STOP")
    exp = sum(1 for r in rows if r["status"] == "EXPIRED")
    wins = sum(1 for r in rows if (r["return_pct"] or 0) > 0)
    avg = sum((r["return_pct"] or 0) for r in rows) / n
    return {
        "n": n,
        "hit_target": hit_t,
        "hit_stop": hit_s,
        "expired": exp,
        "target_rate_pct": round(hit_t / n * 100, 1),
        "win_rate_pct": round(wins / n * 100, 1),
        "avg_return_pct": round(avg, 2),
        "reliable": n >= MIN_RELIABLE_SAMPLE,
    }


def _conf_bucket(pct: Any) -> str:
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return "unknown"
    return "75+" if p >= 75 else "55-74" if p >= 55 else "<55"


def compute_accuracy(cache_manager) -> Dict[str, Any]:
    """Aggregate hit rates / returns of resolved predictions by verdict and by confidence bucket."""
    all_rows = cache_manager.get_predictions()
    resolved = [r for r in all_rows if r["status"] != "OPEN"]
    by_verdict: Dict[str, List[Dict[str, Any]]] = {}
    by_conf: Dict[str, List[Dict[str, Any]]] = {}
    for r in resolved:
        by_verdict.setdefault(r["verdict"] or "?", []).append(r)
        by_conf.setdefault(_conf_bucket(r["confidence_pct"]), []).append(r)
    return {
        "logged": len(all_rows),
        "open": len(all_rows) - len(resolved),
        "resolved": len(resolved),
        "overall": _bucket_stats(resolved),
        "by_verdict": {k: _bucket_stats(v) for k, v in sorted(by_verdict.items())},
        "by_confidence": {k: _bucket_stats(v) for k, v in sorted(by_conf.items())},
        "horizon_trading_days": HORIZON_TRADING_DAYS,
        "min_reliable_sample": MIN_RELIABLE_SAMPLE,
        "note": (
            "Rates are only meaningful once a bucket has at least "
            f"{MIN_RELIABLE_SAMPLE} resolved calls. Same-candle target/stop touches count as stop hits."
        ),
    }
