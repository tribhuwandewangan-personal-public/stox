"""
Deterministic Quantitative Portfolio Risk, Position Sizing & Indian Tax Engine.

Strictly READ-ONLY & ADVISORY ONLY:
- Computes stock/portfolio Beta vs Nifty 50 (^NSEI) from local cached daily candles
- Pairwise Pearson return correlation matrix + high-correlation cluster alerts
- Historical 1-day Portfolio VaR & CVaR (95% & 99%) + annualized volatility
- SEBI/AMFI Large / Mid / Small-cap allocation mix + Herfindahl-Hirschman Index (HHI)
- Deterministic Indian macro stress test scenarios (Nifty drawdown, Crude/INR spike, RBI rate hike, Mid/Small liquidity shock)
- ATR / fixed-fractional risk position sizing + 20D ADV liquidity impact checks
- Indian Finance Act 2024 equity delivery taxation (STCG 20% < 12m, LTCG 12.5% above Rs 1.25L >= 12m)
  and statutory NSE CNC sell transaction charges (STT, NSE txn, SEBI, GST, CDSL DP).
"""

import math
import statistics
from typing import Dict, Any, List, Optional, Set


# Nifty 50 / Nifty Next 50 Large-Cap reference set used only when market cap is not cached
_LARGE_CAP_FALLBACK: Set[str] = {
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "BHARTIARTL", "INFY", "SBIN", "LICI",
    "ITC", "HINDUNILVR", "LT", "BAJFINANCE", "HCLTECH", "MARUTI", "SUNPHARMA", "ADANIENT",
    "KOTAKBANK", "TITAN", "ONGC", "AXISBANK", "NTPC", "ULTRACEMCO", "WIPRO", "POWERGRID",
    "BAJAJFINSV", "NESTLEIND", "JSWSTEEL", "TATASTEEL", "ASIANPAINT", "M&M", "COALINDIA",
    "HAL", "BEL", "TRENT", "DRREDDY", "CIPLA", "DMART", "GRASIM", "BPCL", "IOC", "INDIGO",
}


def extract_daily_returns(candles: List[Dict[str, Any]]) -> Dict[str, float]:
    """Converts chronological candle list into {date_str: simple_daily_return}."""
    returns: Dict[str, float] = {}
    prev_c: Optional[float] = None
    for row in candles or []:
        d = str(row.get("DATE") or row.get("date") or "")[:10]
        try:
            c = float(row.get("CLOSE_PRICE") if row.get("CLOSE_PRICE") is not None else row.get("close"))
        except (TypeError, ValueError):
            continue
        if not d or not math.isfinite(c) or c <= 0:
            continue
        if prev_c is not None and prev_c > 0:
            returns[d] = (c - prev_c) / prev_c
        prev_c = c
    return returns


def compute_stock_beta(
    stock_returns: Dict[str, float],
    bench_returns: Dict[str, float],
    min_obs: int = 20,
) -> Optional[float]:
    """Computes OLS Beta = Cov(stock, bench) / Var(bench) across overlapping dates."""
    if not stock_returns or not bench_returns:
        return None
    common = sorted(set(stock_returns.keys()) & set(bench_returns.keys()))
    if len(common) < min_obs:
        return None
    xs = [bench_returns[d] for d in common]
    ys = [stock_returns[d] for d in common]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 1e-12:
        return None
    cov_xy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return round(cov_xy / var_x, 2)


def _pearson_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom = math.sqrt(sum(a * a for a in dx) * sum(b * b for b in dy))
    if denom <= 1e-12:
        return None
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(dx, dy)) / denom))


def compute_correlation_matrix(
    returns_by_symbol: Dict[str, Dict[str, float]],
    min_overlap: int = 20,
    high_corr_threshold: float = 0.75,
) -> Dict[str, Any]:
    """Computes pairwise Pearson return correlations and identifies high-correlation pairs."""
    symbols = sorted(returns_by_symbol.keys())
    matrix: Dict[str, Dict[str, Optional[float]]] = {s: {s2: (1.0 if s == s2 else None) for s2 in symbols} for s in symbols}
    high_pairs: List[Dict[str, Any]] = []
    pair_corrs: List[float] = []

    for i in range(len(symbols)):
        for j in range(i + 1, len(symbols)):
            s1, s2 = symbols[i], symbols[j]
            r1, r2 = returns_by_symbol[s1], returns_by_symbol[s2]
            common = sorted(set(r1.keys()) & set(r2.keys()))
            if len(common) < min_overlap:
                continue
            corr = _pearson_corr([r1[d] for d in common], [r2[d] for d in common])
            if corr is None:
                continue
            corr_r = round(corr, 3)
            matrix[s1][s2] = corr_r
            matrix[s2][s1] = corr_r
            pair_corrs.append(corr_r)
            if corr_r >= high_corr_threshold:
                high_pairs.append({"pair": f"{s1}-{s2}", "symbols": [s1, s2], "correlation": corr_r})

    high_pairs.sort(key=lambda p: -p["correlation"])
    avg_corr = round(sum(pair_corrs) / len(pair_corrs), 3) if pair_corrs else None
    return {
        "matrix": matrix,
        "high_correlation_pairs": high_pairs,
        "avg_pairwise_correlation": avg_corr,
    }


def compute_portfolio_var_cvar(
    returns_by_symbol: Dict[str, Dict[str, float]],
    weights: Dict[str, float],
    portfolio_value: float,
    min_obs: int = 20,
) -> Dict[str, Any]:
    """
    Computes historical 1-day 95% and 99% VaR and Expected Shortfall (CVaR) from empirical
    weighted daily portfolio returns (requiring >= 70% portfolio weight coverage per day).
    """
    empty_res = {
        "available": False,
        "observations": 0,
        "var_95_pct": None,
        "var_95_rs": None,
        "cvar_95_pct": None,
        "cvar_95_rs": None,
        "var_99_pct": None,
        "var_99_rs": None,
        "cvar_99_pct": None,
        "cvar_99_rs": None,
        "annualized_volatility_pct": None,
    }
    if not returns_by_symbol or not weights or portfolio_value <= 0:
        return empty_res

    all_dates = sorted({d for rets in returns_by_symbol.values() for d in rets.keys()})
    port_rets: List[float] = []
    for d in all_dates:
        cov_wt = sum(weights.get(sym, 0.0) for sym, rets in returns_by_symbol.items() if d in rets)
        if cov_wt < 0.70:
            continue
        day_r = sum(weights.get(sym, 0.0) * rets[d] for sym, rets in returns_by_symbol.items() if d in rets)
        port_rets.append(day_r / cov_wt)

    n = len(port_rets)
    if n < min_obs:
        return {**empty_res, "observations": n}

    losses = sorted(-r for r in port_rets)  # positive = loss

    def _var_cvar(alpha: float) -> tuple:
        idx = min(n - 1, max(0, int(math.ceil(alpha * n)) - 1))
        var_val = max(0.0, losses[idx])
        tail = [x for x in losses[idx:] if x >= 0] or [var_val]
        cvar_val = max(var_val, sum(tail) / len(tail))
        return round(var_val * 100.0, 2), round(var_val * portfolio_value, 2), round(cvar_val * 100.0, 2), round(cvar_val * portfolio_value, 2)

    v95_p, v95_r, c95_p, c95_r = _var_cvar(0.95)
    v99_p, v99_r, c99_p, c99_r = _var_cvar(0.99)
    ann_vol = round(statistics.stdev(port_rets) * math.sqrt(252.0) * 100.0, 2)

    return {
        "available": True,
        "observations": n,
        "var_95_pct": v95_p,
        "var_95_rs": v95_r,
        "cvar_95_pct": c95_p,
        "cvar_95_rs": c95_r,
        "var_99_pct": v99_p,
        "var_99_rs": v99_r,
        "cvar_99_pct": c99_p,
        "cvar_99_rs": c99_r,
        "annualized_volatility_pct": ann_vol,
    }


def classify_sebi_cap_tier(
    symbol: str,
    market_cap_cr: Optional[float] = None,
    midcap_symbols: Optional[Set[str]] = None,
) -> str:
    """
    Classifies Indian equities into SEBI/AMFI Large / Mid / Small-cap buckets:
    - Large Cap (Top 100): >= Rs. 85,000 Cr
    - Mid Cap (101-250): >= Rs. 27,500 Cr or member of Nifty Midcap 250 list
    - Small Cap (251+): < Rs. 27,500 Cr
    """
    sym_u = str(symbol or "").upper().strip()
    if market_cap_cr is not None and market_cap_cr > 0:
        if market_cap_cr >= 85000.0:
            return "Large Cap"
        if market_cap_cr >= 27500.0:
            return "Mid Cap"
        return "Small Cap"
    if sym_u in _LARGE_CAP_FALLBACK:
        return "Large Cap"
    if midcap_symbols and sym_u in midcap_symbols:
        return "Mid Cap"
    return "Small Cap"


def compute_hhi_concentration(weights: Dict[str, float]) -> Dict[str, Any]:
    """Computes Herfindahl-Hirschman Index (0 to 10,000) across normalized stock weights."""
    clean = [max(0.0, float(w)) for w in (weights or {}).values()]
    tot = sum(clean)
    if tot <= 0:
        return {"hhi": 0.0, "effective_num_stocks": 0.0, "regime": "Empty"}
    norm = [w / tot for w in clean]
    hhi = sum((w * 100.0) ** 2 for w in norm)
    eff_n = round(10000.0 / hhi, 2) if hhi > 0 else 0.0
    if hhi > 2500.0:
        regime = "Highly Concentrated"
    elif hhi >= 1500.0:
        regime = "Moderately Concentrated"
    else:
        regime = "Diversified"
    return {"hhi": round(hhi, 1), "effective_num_stocks": eff_n, "regime": regime}


def run_macro_stress_tests(
    holdings: List[Dict[str, Any]],
    portfolio_beta: Optional[float],
    sector_weights_pct: Dict[str, float],
    portfolio_value: float,
) -> List[Dict[str, Any]]:
    """Deterministic scenario shocks calibrated to Indian equity sensitivities."""
    if not holdings or portfolio_value <= 0:
        return []

    eff_beta = portfolio_beta if (portfolio_beta is not None and portfolio_beta > 0) else 1.0
    nifty_shock_pct = round(-10.0 * eff_beta, 2)

    def _sec_match(sec: str, *words: str) -> bool:
        s = (sec or "").lower()
        return any(w in s for w in words)

    oil_impact = 0.0
    rate_impact = 0.0
    liq_impact = 0.0
    for h in holdings:
        w = float(h.get("current_value", 0) or 0) / portfolio_value
        sec = str(h.get("sector", ""))
        cap = str(h.get("cap_tier", "Mid Cap"))

        # Scenario 2: Brent Crude +20% & INR -5%
        if _sec_match(sec, "it", "software", "technology", "pharma"):
            oil_impact += w * 0.035  # USD-earning cushion
        elif _sec_match(sec, "paint", "aviation", "airline", "chemical", "tyre", "oil", "refin", "auto"):
            oil_impact += w * (-0.11)
        else:
            oil_impact += w * (-0.05)

        # Scenario 3: RBI +50 bps rate hike
        if _sec_match(sec, "bank", "nbfc", "financial", "real estate", "realty", "housing", "auto"):
            rate_impact += w * (-0.085)
        elif _sec_match(sec, "fmcg", "pharma", "healthcare", "utilities", "it"):
            rate_impact += w * (-0.02)
        else:
            rate_impact += w * (-0.045)

        # Scenario 4: Broad mid/small-cap liquidity drawdown
        if cap == "Small Cap":
            liq_impact += w * (-0.15)
        elif cap == "Mid Cap":
            liq_impact += w * (-0.10)
        else:
            liq_impact += w * (-0.05)

    scenarios = [
        ("Nifty -10% Broad Correction", nifty_shock_pct, f"Beta-scaled ({eff_beta:.2f}x vs Nifty 50)"),
        ("Brent +20% / INR -5% Shock", round(oil_impact * 100.0, 2), "IT/Pharma export buffer offsets crude importers"),
        ("RBI +50 bps Rate Surprise", round(rate_impact * 100.0, 2), "Heavy impact on Banking/NBFC/Realty/Auto"),
        ("Mid/Small-Cap Liquidity Shock", round(liq_impact * 100.0, 2), "-5% Large / -10% Mid / -15% Small tier shock"),
    ]
    return [
        {
            "scenario": name,
            "estimated_impact_pct": pct,
            "estimated_impact_rs": round(portfolio_value * pct / 100.0, 2),
            "note": note,
        }
        for name, pct, note in scenarios
    ]


def compute_atr_position_sizing(
    portfolio_capital: float,
    entry_price: float,
    stop_loss: float,
    risk_per_trade_pct: float = 1.0,
    avg_daily_volume: Optional[float] = None,
    max_single_position_pct: float = 20.0,
) -> Dict[str, Any]:
    """
    Fixed-fractional ATR/stop-loss position sizing with 20-day ADV market-impact liquidity check.
    """
    if portfolio_capital <= 0 or entry_price <= 0 or stop_loss <= 0 or stop_loss >= entry_price:
        return {
            "recommended_shares": 0,
            "position_value_rs": 0.0,
            "capital_weight_pct": 0.0,
            "max_risk_rs": 0.0,
            "adv_participation_pct": None,
            "liquidity_flag": "INSUFFICIENT_LEVELS",
        }

    risk_budget_rs = portfolio_capital * (risk_per_trade_pct / 100.0)
    risk_per_share = max(0.05, entry_price - stop_loss)
    raw_shares = int(risk_budget_rs // risk_per_share)
    max_cap_shares = int((portfolio_capital * (max_single_position_pct / 100.0)) // entry_price)
    shares = max(0, min(raw_shares, max_cap_shares))
    pos_val = round(shares * entry_price, 2)
    cap_wt = round((pos_val / portfolio_capital) * 100.0, 2)

    adv_pct: Optional[float] = None
    liq_flag = "UNVERIFIED_ADV"
    if avg_daily_volume is not None and avg_daily_volume > 0 and shares > 0:
        adv_pct = round(shares / avg_daily_volume * 100.0, 4)
        if adv_pct > 1.0:
            liq_flag = "HIGH_IMPACT"
        elif adv_pct > 0.25:
            liq_flag = "MODERATE"
        else:
            liq_flag = "LIQUID"

    return {
        "recommended_shares": shares,
        "position_value_rs": pos_val,
        "capital_weight_pct": cap_wt,
        "max_risk_rs": round(shares * risk_per_share, 2),
        "adv_participation_pct": adv_pct,
        "liquidity_flag": liq_flag,
    }


def estimate_indian_tax_and_cost_impact(
    quantity: int,
    avg_price: float,
    sell_price: float,
    holding_days: Optional[int] = None,
    realized_ltcg_ytd: float = 0.0,
    sell_fraction: float = 1.0,
) -> Dict[str, Any]:
    """
    Estimates Indian equity delivery tax (Finance Act 2024: STCG 20% < 365d, LTCG 12.5% above
    Rs 1,25,000 exemption >= 365d) and NSE CNC sell-side statutory charges (STT 0.1%, exchange
    0.00297%, SEBI 0.0001%, 18% GST on fees, Rs 15.93 DP charge) prior to trim/exit actions.
    """
    sell_qty = max(0, int(round(max(0, quantity) * max(0.0, min(1.0, sell_fraction)))))
    if sell_qty <= 0 or sell_price <= 0:
        return {
            "sell_qty": 0,
            "turnover_rs": 0.0,
            "gross_pnl": 0.0,
            "tax_regime": "NO_SALE",
            "tax_rate_pct": 0.0,
            "estimated_tax": 0.0,
            "statutory_costs": 0.0,
            "cost_pct_of_turnover": 0.0,
            "net_post_tax_pnl": 0.0,
            "tax_note": "No shares scheduled for sale.",
        }

    turnover = round(sell_qty * sell_price, 2)
    cost_basis = round(sell_qty * max(0.0, avg_price), 2)
    gross_pnl = round(turnover - cost_basis, 2)

    # NSE Equity Delivery (CNC) Sell-Side Statutory Transaction Costs
    stt = round(turnover * 0.001, 2)             # 0.1% Securities Transaction Tax on delivery sell
    exch_txn = turnover * 0.0000297              # NSE 0.00297%
    sebi_fee = turnover * 0.000001               # SEBI Rs 10/crore (0.0001%)
    gst = 0.18 * (exch_txn + sebi_fee)
    dp_charge = 15.93                            # CDSL depository debit charge per ISIN sell day
    statutory_costs = round(stt + exch_txn + sebi_fee + gst + dp_charge, 2)
    cost_pct = round(statutory_costs / turnover * 100.0, 3)

    if gross_pnl <= 0:
        tax_regime = "TAX_LOSS_HARVEST_ELIGIBLE"
        tax_rate_pct = 0.0
        estimated_tax = 0.0
        note = f"Unrealized loss Rs. {abs(gross_pnl):,.0f} (eligible to offset STCG/LTCG); statutory sell fees ~Rs. {statutory_costs:,.0f}."
    elif holding_days is not None and holding_days >= 365:
        tax_regime = "LTCG_12_5_PCT"
        tax_rate_pct = 12.5
        rem_exempt = max(0.0, 125000.0 - max(0.0, realized_ltcg_ytd))
        taxable_gain = max(0.0, gross_pnl - rem_exempt)
        estimated_tax = round(taxable_gain * 0.125, 2)
        note = (
            f"LTCG 12.5% applies (held {holding_days}d >= 365d; Rs. {rem_exempt:,.0f} annual exemption left); "
            f"est. tax Rs. {estimated_tax:,.0f} + fees Rs. {statutory_costs:,.0f}."
        )
    else:
        is_explicit_st = holding_days is not None
        tax_regime = "STCG_20_PCT" if is_explicit_st else "STCG_20_PCT_CONSERVATIVE_EST"
        tax_rate_pct = 20.0
        estimated_tax = round(gross_pnl * 0.20, 2)
        lot_msg = f"held {holding_days}d < 365d" if is_explicit_st else "lot age unavailable — verify >=365d LTCG in Zerodha Console"
        note = f"STCG 20% ({lot_msg}); est. tax Rs. {estimated_tax:,.0f} + fees Rs. {statutory_costs:,.0f}."

    net_post_tax = round(gross_pnl - estimated_tax - statutory_costs, 2)
    return {
        "sell_qty": sell_qty,
        "turnover_rs": turnover,
        "gross_pnl": gross_pnl,
        "tax_regime": tax_regime,
        "tax_rate_pct": tax_rate_pct,
        "estimated_tax": estimated_tax,
        "statutory_costs": statutory_costs,
        "cost_pct_of_turnover": cost_pct,
        "net_post_tax_pnl": net_post_tax,
        "tax_note": note,
    }
