"""
Peer Valuation Comparison Engine.
Performs automated peer-relative valuation benchmarking for NSE-listed companies.

Deterministic, rule-based, read-only advisory module.
No order placement. No LLM calls for quantitative numbers.
"""

from typing import Dict, Any, List, Optional
import re
import statistics


# ---------------------------------------------------------------------------
# Static sector → peer symbol map (NSE)
# ---------------------------------------------------------------------------
SECTOR_PEER_MAP: Dict[str, List[str]] = {
    "AUTO": ["TMPV", "M&M", "MARUTI", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT"],
    "IT": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTM"],
    "BANKING": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "SBIN", "AXISBANK", "INDUSINDBK"],
    "PHARMA": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "BIOCON", "AUROPHARMA"],
    "FMCG": ["HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "DABUR", "GODREJCP"],
    "ENERGY": ["RELIANCE", "ONGC", "BPCL", "IOC", "HINDPETRO", "GAIL"],
    "METALS": ["TATASTEEL", "JSWSTEEL", "HINDALCO", "VEDL", "COALINDIA", "NMDC"],
    "INFRA": ["LT", "NTPC", "POWERGRID", "ADANIPORTS", "ULTRACEMCO", "AMBUJACEM"],
    "CONSUMER": ["TITAN", "ASIANPAINT", "PIDILITIND", "BERGEPAINT", "HAVELLS", "VGUARD"],
    "NBFC": ["BAJFINANCE", "BAJAJFINSV", "CHOLAFIN", "MUTHOOTFIN", "MANAPPURAM", "LICHSGFIN"],
    "CAPITAL_GOODS": ["LT", "ABB", "SIEMENS", "CUMMINSIND", "POLYCAB", "BHEL"],
    "DEFENCE": ["HAL", "BEL", "BDL", "MAZDOCK", "COCHINSHIP", "DATAPATTNS"],
    "CHEMICALS": ["PIDILITIND", "SRF", "DEEPAKNTR", "PIIND", "NAVINFLUOR", "AETHER"],
    "CAPITAL_MARKETS": ["BSE", "CDSL", "MCX", "ANGELONE", "360ONE", "CAMS"],
    "TELECOM": ["BHARTIARTL", "INDUSTOWER", "TATACOMM", "IDEA", "HFCL"],
    "REALTY": ["DLF", "GODREJPROP", "OBEROIRLTY", "LODHA", "PRESTIGE", "PHOENIXLTD"],
}

# Sector keyword aliases to map raw sector strings onto canonical keys
_SECTOR_ALIASES: Dict[str, str] = {
    # AUTO
    "automobile": "AUTO", "automobiles": "AUTO", "auto": "AUTO", "automotive": "AUTO",
    "auto ancillaries": "AUTO", "auto components": "AUTO",
    "two wheeler": "AUTO", "two-wheeler": "AUTO",
    # IT
    "information technology": "IT", "it services": "IT", "software": "IT",
    "technology": "IT", "it": "IT",
    # BANKING
    "bank": "BANKING", "banking": "BANKING", "financial services": "BANKING",
    # CAPITAL MARKETS
    "capital markets": "CAPITAL_MARKETS", "fintech": "CAPITAL_MARKETS", "exchange": "CAPITAL_MARKETS",
    # PHARMA
    "pharma": "PHARMA", "pharmaceutical": "PHARMA", "pharmaceuticals": "PHARMA", "healthcare": "PHARMA",
    "drugs": "PHARMA",
    # FMCG
    "fmcg": "FMCG", "consumer staples": "FMCG", "consumer defensive": "FMCG",
    "fast moving consumer goods": "FMCG", "food": "FMCG", "beverages": "FMCG",
    # ENERGY
    "energy": "ENERGY", "oil": "ENERGY", "gas": "ENERGY", "petroleum": "ENERGY",
    "oil & gas": "ENERGY",
    # METALS
    "metals": "METALS", "mining": "METALS", "steel": "METALS",
    "metal & mining": "METALS", "metals & mining": "METALS", "basic materials": "METALS",
    # CAPITAL GOODS
    "capital goods": "CAPITAL_GOODS", "electricals": "CAPITAL_GOODS", "electrical equipment": "CAPITAL_GOODS",
    "machinery": "CAPITAL_GOODS", "industrial engineering": "CAPITAL_GOODS", "industrial": "CAPITAL_GOODS",
    # DEFENCE
    "defence": "DEFENCE", "defense": "DEFENCE", "aerospace": "DEFENCE", "shipbuilding": "DEFENCE",
    # CHEMICALS
    "chemicals": "CHEMICALS", "specialty chemicals": "CHEMICALS", "agrochemicals": "CHEMICALS",
    # TELECOM
    "telecom": "TELECOM", "telecommunications": "TELECOM",
    # REALTY
    "real estate": "REALTY", "realty": "REALTY",
    # INFRA
    "infra": "INFRA", "infrastructure": "INFRA", "construction": "INFRA",
    "power": "INFRA", "utilities": "INFRA", "cement": "INFRA",
    # CONSUMER
    "consumer discretionary": "CONSUMER", "consumer cyclical": "CONSUMER", "consumer durables": "CONSUMER",
    "consumer goods": "CONSUMER", "consumer": "CONSUMER", "paints": "CONSUMER",
    # NBFC
    "nbfc": "NBFC", "non banking financial": "NBFC",
    "non-banking financial": "NBFC", "finance": "NBFC",
}


def _num(val: Any) -> Optional[float]:
    """Safely parse any value as a finite float; return None on failure."""
    if val is None or isinstance(val, bool):
        return None
    try:
        import math
        f = float(str(val).replace(",", "").strip())
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _resolve_sector(sector_raw: str) -> Optional[str]:
    """
    Normalise an arbitrary sector string to one of the canonical SECTOR_PEER_MAP keys.
    Returns None if unrecognised.
    """
    if not sector_raw:
        return None
    key = sector_raw.strip().upper()
    if key in SECTOR_PEER_MAP:
        return key
    lower = sector_raw.strip().lower()
    # Exact alias match first
    if lower in _SECTOR_ALIASES:
        return _SECTOR_ALIASES[lower]
    # Word-boundary match (longest alias first) so "it" never matches "capITal" or "equITies"
    for alias, canonical in sorted(_SECTOR_ALIASES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lower):
            return canonical
    return None


class PeerBenchmarkEngine:
    """
    Deterministic peer valuation benchmarking engine.
    All computations are rule-based; no LLM calls for quantitative numbers.
    Read-only — does NOT place, modify, or cancel any broker orders.
    """

    # Tolerance band (%) around the median within which a stock is "IN_LINE"
    PE_IN_LINE_PCT: float = 15.0
    ROE_IN_LINE_PCT: float = 20.0
    MARGIN_IN_LINE_PCT: float = 20.0

    def get_peer_group(self, symbol: str, sector: str) -> List[str]:
        """
        Returns up to 5 peer symbols for the given sector, excluding the subject symbol.

        Parameters
        ----------
        symbol : str
            The subject symbol (e.g. "TCS").
        sector : str
            Raw sector string (e.g. "Information Technology", "IT", "FMCG").

        Returns
        -------
        List[str]
            Up to 5 peer symbols.
        """
        canonical = _resolve_sector(sector)
        if canonical is None:
            return []
        peers = [p for p in SECTOR_PEER_MAP.get(canonical, []) if p.upper() != symbol.upper()]
        return peers[:5]

    def compute_peer_benchmarks(
        self,
        symbol: str,
        sector: str,
        fund_engine: Any,
    ) -> Dict[str, Any]:
        """
        Fetches fundamental metrics for each peer and returns sector-median benchmarks
        plus relative comparison labels for the subject symbol.

        Parameters
        ----------
        symbol : str
            Subject NSE symbol (e.g. "INFY").
        sector : str
            Raw sector string used to look up the peer group.
        fund_engine :
            Instance of FundamentalAnalysisEngine; must expose
            ``get_fundamental_metrics(symbol: str) -> dict``.

        Returns
        -------
        dict with keys:
            peers_analyzed, sector_median_pe, sector_median_pb,
            sector_median_roe, sector_median_margin, peer_comparison,
            peer_verdict, peers_data
        """
        peers = self.get_peer_group(symbol, sector)

        # Collect peer data
        peers_data: Dict[str, Dict[str, Any]] = {}
        peers_analyzed: List[str] = []

        pe_vals: List[float] = []
        pb_vals: List[float] = []
        roe_vals: List[float] = []
        margin_vals: List[float] = []
        de_vals: List[float] = []

        for peer in peers:
            try:
                metrics = fund_engine.get_fundamental_metrics(peer)
            except Exception:
                continue

            pe = _num(metrics.get("pe_ratio"))
            pb = _num(metrics.get("pb_ratio"))
            roe = _num(metrics.get("roe_pct"))
            margin = _num(metrics.get("profit_margin_pct"))
            de = _num(metrics.get("debt_to_equity"))

            # Only include peer if at least one metric is valid
            if any(v is not None for v in (pe, pb, roe, margin, de)):
                peers_analyzed.append(peer)
                peers_data[peer] = {
                    "pe_ratio": pe,
                    "pb_ratio": pb,
                    "roe_pct": roe,
                    "profit_margin_pct": margin,
                    "debt_to_equity": de,
                }
                if pe is not None and pe > 0:
                    pe_vals.append(pe)
                if pb is not None and pb > 0:
                    pb_vals.append(pb)
                if roe is not None:
                    roe_vals.append(roe)
                if margin is not None:
                    margin_vals.append(margin)
                if de is not None and de >= 0:
                    de_vals.append(de)

        # Compute medians (None if insufficient data)
        def median_or_none(lst: List[float]) -> Optional[float]:
            if not lst:
                return None
            return round(statistics.median(lst), 2)

        sector_median_pe = median_or_none(pe_vals)
        sector_median_pb = median_or_none(pb_vals)
        sector_median_roe = median_or_none(roe_vals)
        sector_median_margin = median_or_none(margin_vals)

        # Fetch the subject symbol's own metrics for comparison
        try:
            own_metrics = fund_engine.get_fundamental_metrics(symbol)
        except Exception:
            own_metrics = {}

        own_pe = _num(own_metrics.get("pe_ratio"))
        own_roe = _num(own_metrics.get("roe_pct"))
        own_margin = _num(own_metrics.get("profit_margin_pct"))

        # --- Peer comparison labels ---
        def compare_pe(val: Optional[float], median: Optional[float]) -> str:
            if val is None or median is None or median == 0:
                return "N/A"
            diff_pct = ((val - median) / median) * 100.0
            if diff_pct < -self.PE_IN_LINE_PCT:
                return "CHEAPER"
            if diff_pct > self.PE_IN_LINE_PCT:
                return "EXPENSIVE"
            return "IN_LINE"

        def compare_higher_is_better(
            val: Optional[float],
            median: Optional[float],
            band_pct: float,
        ) -> str:
            """For ROE / margin where higher = better."""
            if val is None or median is None or median == 0:
                return "N/A"
            diff_pct = ((val - median) / abs(median)) * 100.0
            if diff_pct > band_pct:
                return "SUPERIOR"
            if diff_pct < -band_pct:
                return "LAGGING"
            return "IN_LINE"

        pe_label = compare_pe(own_pe, sector_median_pe)
        roe_label = compare_higher_is_better(own_roe, sector_median_roe, self.ROE_IN_LINE_PCT)
        margin_label = compare_higher_is_better(own_margin, sector_median_margin, self.MARGIN_IN_LINE_PCT)

        peer_comparison = {
            "pe_vs_peers": pe_label,
            "roe_vs_peers": roe_label,
            "margin_vs_peers": margin_label,
        }

        # --- Narrative verdict ---
        verdict = self._build_verdict(
            symbol, own_pe, sector_median_pe, own_roe, sector_median_roe,
            pe_label, roe_label, margin_label, peers_analyzed
        )

        return {
            "peers_analyzed": peers_analyzed,
            "sector_median_pe": sector_median_pe,
            "sector_median_pb": sector_median_pb,
            "sector_median_roe": sector_median_roe,
            "sector_median_margin": sector_median_margin,
            "peer_comparison": peer_comparison,
            "peer_verdict": verdict,
            "peers_data": peers_data,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _build_verdict(
        symbol: str,
        own_pe: Optional[float],
        median_pe: Optional[float],
        own_roe: Optional[float],
        median_roe: Optional[float],
        pe_label: str,
        roe_label: str,
        margin_label: str,
        peers_analyzed: List[str],
    ) -> str:
        """Builds a human-readable peer verdict string deterministically."""
        if not peers_analyzed:
            return f"No peer data available for {symbol}. Sector mapping may be missing or peers returned no metrics."

        parts: List[str] = []

        # P/E relative comment
        if pe_label == "CHEAPER" and median_pe and own_pe:
            discount_pct = round(((median_pe - own_pe) / median_pe) * 100.0, 1)
            parts.append(
                f"{symbol} trades at a {discount_pct}% discount to sector median P/E ({own_pe:.1f}x vs {median_pe:.1f}x peers)"
            )
        elif pe_label == "EXPENSIVE" and median_pe and own_pe:
            premium_pct = round(((own_pe - median_pe) / median_pe) * 100.0, 1)
            parts.append(
                f"{symbol} commands a {premium_pct}% premium to sector median P/E ({own_pe:.1f}x vs {median_pe:.1f}x peers)"
            )
        elif pe_label == "IN_LINE" and median_pe:
            parts.append(f"{symbol} trades in line with sector median P/E (~{median_pe:.1f}x)")

        # ROE qualifier
        if roe_label == "SUPERIOR" and own_roe and median_roe:
            parts.append(
                f"with superior ROE ({own_roe:.1f}% vs sector median {median_roe:.1f}%)"
            )
        elif roe_label == "LAGGING" and own_roe and median_roe:
            parts.append(
                f"but ROE lags peers ({own_roe:.1f}% vs sector median {median_roe:.1f}%)"
            )

        # Margin qualifier
        if margin_label == "SUPERIOR":
            parts.append("and above-median profit margins")
        elif margin_label == "LAGGING":
            parts.append("with below-median profit margins")

        if parts:
            verdict = "; ".join(parts) + f" (vs {len(peers_analyzed)} peers)."
        else:
            verdict = (
                f"Peer data collected for {len(peers_analyzed)} companies; "
                "insufficient comparable metrics for a full relative verdict."
            )

        return verdict
