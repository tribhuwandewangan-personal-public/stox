"""
Online Multi-Source Financial News Fetcher & Report Generator.

Produces exactly two markdown files per date in news_reports/<YYYY-MM-DD>/:
1. general_market_news.md: Common market news (Crude Oil price & trend, Rupee (USD/INR) trend,
   global market cues, FII/DII flows, RBI/macro factors, and local/global market-moving headlines).
2. stock_specific_news.md: Stock-specific news from multiple sources (The Economic Times,
   Moneycontrol, Livemint, Business Standard, Reuters, etc.) for all target stocks in a SINGLE file.

Features:
- Live macro market telemetry via yfinance (Brent, WTI, USD/INR, DXY, US 10Y Yield, S&P 500, Nasdaq, Gold)
- Multi-source RSS aggregation with publisher extraction, URL links, snippets, and sentiment scoring
- Incremental SQLite caching (storage/cache.db)
"""

import os
import sys
import json
import re
import html
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import concurrent.futures
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Dict, Any, Optional, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from config import SYMBOLS_FILE_PATH, VERBOSE_LOGGING
from storage.cache_manager import CacheManager
from tools.macro_tools import GlobalMacroEngine


def clean_text(text: str) -> str:
    """Strips HTML tags and unescapes HTML entities."""
    if not text:
        return ""
    text = html.unescape(text)
    clean = re.sub(r"<[^<]+?>", "", text)
    return " ".join(clean.split())


# ----------------------------------------------------------------------
# Business Activity & Recommendation Filter Rules
# ----------------------------------------------------------------------
SPAM_RECOMMENDATION_PATTERNS = [
    re.compile(r"\b(?:buy|sell|hold|accumulate)\s+(?:call|target|rating|recommendation)\b", re.I),
    re.compile(r"\bstocks?\s+to\s+(?:buy|watch|track|sell|trade)\b", re.I),
    re.compile(r"\bhot\s+stocks?\b", re.I),
    re.compile(r"\bshare\s+price\s+(?:live|today|chart|target|forecast|prediction)\b", re.I),
    re.compile(r"\bstock\s+price\s+(?:live|today|chart|target|forecast|prediction)\b", re.I),
    re.compile(r"\bprice\s+target\s+(?:of|raised|cut|sees|hike)\b", re.I),
    re.compile(r"\btarget\s+price\b", re.I),
    re.compile(r"\bmultibagger\b", re.I),
    re.compile(r"\bshould\s+you\s+(?:buy|sell|hold|invest)\b", re.I),
    re.compile(r"\btradingview\b", re.I),
    re.compile(r"\bforecast\s+for\s+202\d\b", re.I),
    re.compile(r"\btechnical\s+view\b", re.I),
    re.compile(r"\bsupport[–\-]resistance\b", re.I),
    re.compile(r"\bnse/bse\s+live\b", re.I),
    re.compile(r"\bmarket\s+summary\b", re.I),
    re.compile(r"\bexpert\s+recommendations?\b", re.I),
    re.compile(r"\bmovers\s+and\s+shakers\b", re.I),
    re.compile(r"\bhere'?s\s+what\s+analysts\b", re.I),
    re.compile(r"\btop\s+picks?\b", re.I),
    re.compile(r"\bbrokerages?\s+maintain\b", re.I),
    re.compile(r"\bbulls\s+vs\s+bears\b", re.I),
]


def is_recommendation_spam(title: str, snippet: str = "") -> bool:
    """Detects broker recommendation clickbait, price target spam, and ticker tracker pages."""
    text = f"{title} {snippet}"
    return any(p.search(text) for p in SPAM_RECOMMENDATION_PATTERNS)


BUSINESS_CATEGORIES = {
    "Orders & Contracts": {
        "badge": "🎯 [Order / Deal]",
        "patterns": [
            re.compile(r"\b(?:order|contract|deal|bid|mandate|project)s?\s+(?:win|won|bag|bagged|worth|valued at|of)\b", re.I),
            re.compile(r"\b(?:order\s*book|order\s*backlog|order\s*pipeline)\b", re.I),
            re.compile(r"\b(?:secures|bags|awarded|wins)\s+(?:new\s+)?(?:order|contract|deal|tender)\b", re.I),
            re.compile(r"\b(?:signs|pact|mou|agreement)\s+(?:with|for)\b", re.I),
        ]
    },
    "M&A & Partnerships": {
        "badge": "🤝 [M&A / Partnership]",
        "patterns": [
            re.compile(r"\b(?:acquires|acquisition|merger|amalgamation|stake\s+purchase)\b", re.I),
            re.compile(r"\b(?:buys|picks\s+up)\s+(?:stake|equity)\b", re.I),
            re.compile(r"\b(?:joint\s+venture|tie-up|partnership|strategic\s+alliance)\b", re.I),
        ]
    },
    "Capacity & Expansion": {
        "badge": "🏭 [Expansion / Capex]",
        "patterns": [
            re.compile(r"\b(?:commissions|commissioned|capacity\s+expansion|new\s+plant|new\s+facility)\b", re.I),
            re.compile(r"\b(?:commercial\s+production|commercial\s+operations|capex|groundbreaking)\b", re.I),
            re.compile(r"\b(?:opens|launches)\s+(?:new\s+)?(?:facility|unit|plant|store)\b", re.I),
        ]
    },
    "Financial Results": {
        "badge": "📊 [Earnings / Performance]",
        "patterns": [
            re.compile(r"\b(?:net\s+profit|revenue|ebitda|pat)\s+(?:rises|jumps|surges|grows|up|beats|falls|drops|down)\b", re.I),
            re.compile(r"\b(?:q[1-4]|quarterly|half-yearly|annual)\s+(?:results|profit|earnings|revenue)\b", re.I),
            re.compile(r"\b(?:declares|recommends)\s+(?:dividend|interim\s+dividend|bonus\s+issue)\b", re.I),
        ]
    },
    "Regulatory & Operations": {
        "badge": "⚖️ [Regulatory / Ops]",
        "patterns": [
            re.compile(r"\b(?:fda\s+approval|clearance|environmental\s+nod|patent\s+granted|cci\s+approval)\b", re.I),
            re.compile(r"\b(?:sanction|tax\s+notice|penalty|inspection|investigation|sebi|cbi|ed\s+raid)\b", re.I),
        ]
    }
}


def classify_business_activity(title: str, snippet: str = "") -> Tuple[str, str]:
    """Returns (category_name, badge) for genuine corporate events."""
    text = f"{title} {snippet}"
    for cat_name, cat_data in BUSINESS_CATEGORIES.items():
        if any(p.search(text) for p in cat_data["patterns"]):
            return cat_name, cat_data["badge"]
    return "Corporate Activity", "🏢 [Corporate]"


# ----------------------------------------------------------------------
# Institutional News Scoring: Source Credibility, Clustering, Time Decay & Severity
# ----------------------------------------------------------------------
SOURCE_CREDIBILITY_WEIGHTS: Dict[str, float] = {
    "nse": 1.25,
    "bse": 1.25,
    "sebi": 1.25,
    "rbi": 1.25,
    "reuters": 1.25,
    "bloomberg": 1.25,
    "pti": 1.20,
    "press trust of india": 1.20,
    "economic times": 1.00,
    "the economic times": 1.00,
    "livemint": 1.00,
    "mint": 1.00,
    "business standard": 1.00,
    "financial express": 1.00,
    "moneycontrol": 1.00,
    "cnbc-tv18": 1.00,
    "cnbc tv18": 1.00,
    "ndtv profit": 1.00,
    "bq prime": 1.00,
    "the hindu businessline": 1.00,
    "businessline": 1.00,
}

_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "of", "in", "on", "to", "with", "by", "from",
    "at", "as", "is", "are", "was", "were", "its", "it", "ltd", "limited", "india", "corp",
    "co", "shares", "stock", "q1", "q2", "q3", "q4", "fy26", "fy27", "rs", "cr", "crore",
})

_CRITICAL_SEVERITY_PATTERNS = [
    re.compile(r"\b(?:sebi\s+probe|sebi\s+order|fraud|scam|debt\s+default|ed\s+raid|cbi\s+probe|nclt|insolvency)\b", re.I),
    re.compile(r"\b(?:plant\s+shutdown|credit\s+downgrade|fda\s+warning|import\s+alert|regulatory\s+ban|auditor\s+resign)\b", re.I),
]
_HIGH_SEVERITY_PATTERNS = [
    re.compile(r"\b(?:mega\s+order|order\s+win|bags?\s+contract|secures?\s+order|order\s+cancellation|cancels?\s+order)\b", re.I),
    re.compile(r"\b(?:acquires|acquisition|merger|buyback|bonus\s+issue|fda\s+approval|patent\s+granted)\b", re.I),
    re.compile(r"\b(?:record\s+profit|profit\s+surge|profit\s+slump|tax\s+notice|penalty)\b", re.I),
]
_LOW_SEVERITY_PATTERNS = [
    re.compile(r"\b(?:conference|investor\s+meet|analyst\s+call|webinar|agm\s+notice|press\s+clarification)\b", re.I),
]


def get_source_credibility_weight(source: Optional[str]) -> float:
    """Returns credibility multiplier for publisher (Tier-1 exchanges/wires 1.25x, Tier-2 financial media 1.0x, unknown 0.7x)."""
    if not source:
        return 0.70
    s_norm = " ".join(str(source).lower().split())
    if s_norm in SOURCE_CREDIBILITY_WEIGHTS:
        return SOURCE_CREDIBILITY_WEIGHTS[s_norm]
    for key, wt in SOURCE_CREDIBILITY_WEIGHTS.items():
        if key in s_norm:
            return wt
    return 0.70


def compute_time_decay_weight(
    pub_date: Any, half_life_days: float = 3.0, now: Optional[datetime] = None
) -> float:
    """
    Exponential time decay 0.5 ** (age_days / half_life_days) bounded in [0.05, 1.0].
    Returns 1.0 cleanly when pub_date is absent or unparseable so fixture items remain intact.
    """
    if not pub_date or not str(pub_date).strip():
        return 1.0
    raw = str(pub_date).strip()
    dt: Optional[datetime] = None
    try:
        dt = parsedate_to_datetime(raw)
    except Exception:
        dt = None
    if dt is None:
        for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw[:25], fmt)
                break
            except ValueError:
                continue
    if dt is None:
        return 1.0

    ref = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)

    age_days = max(0.0, (ref - dt).total_seconds() / 86400.0)
    return max(0.05, round(0.5 ** (age_days / max(0.25, float(half_life_days))), 4))


def compute_event_severity(title: str, snippet: str = "") -> Tuple[float, str]:
    """Scales structural events (SEBI probe, debt default, mega M&A) higher than routine updates."""
    text = f"{title} {snippet}"
    if any(p.search(text) for p in _CRITICAL_SEVERITY_PATTERNS):
        return 1.50, "CRITICAL"
    if any(p.search(text) for p in _HIGH_SEVERITY_PATTERNS):
        return 1.25, "HIGH"
    if any(p.search(text) for p in _LOW_SEVERITY_PATTERNS):
        return 0.80, "LOW"
    return 1.00, "STANDARD"


def _title_tokens(title: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(title or "").lower())
    return {w for w in words if len(w) > 1 and w not in _STOPWORDS}


def cluster_duplicate_headlines(
    items: List[Dict[str, Any]], similarity_threshold: float = 0.60
) -> List[Dict[str, Any]]:
    """
    Deduplicates syndicated wire copies using content-token Jaccard similarity.
    Short titles (< 3 content tokens) only deduplicate on exact normalized match so synthetic
    short fixture labels ('a', 'b', 'c') remain distinct.
    """
    if not items:
        return []

    clusters: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        norm_exact = re.sub(r"\s+", " ", title.lower())
        toks = _title_tokens(title)
        cred = get_source_credibility_weight(item.get("source"))

        matched_cluster = None
        for cl in clusters:
            if len(toks) < 3 or len(cl["tokens"]) < 3:
                if norm_exact == cl["exact"]:
                    matched_cluster = cl
                    break
            else:
                union = toks | cl["tokens"]
                jaccard = (len(toks & cl["tokens"]) / len(union)) if union else 0.0
                if jaccard >= similarity_threshold:
                    matched_cluster = cl
                    break

        if matched_cluster is None:
            rep = dict(item)
            rep["cluster_size"] = 1
            rep["syndicated_sources"] = [item.get("source") or "Web News"]
            clusters.append({"exact": norm_exact, "tokens": toks, "rep": rep, "cred": cred})
        else:
            matched_cluster["rep"]["cluster_size"] += 1
            src = item.get("source") or "Web News"
            if src not in matched_cluster["rep"]["syndicated_sources"]:
                matched_cluster["rep"]["syndicated_sources"].append(src)
            if cred > matched_cluster["cred"]:
                # Upgrade representative to higher-credibility source while keeping cluster metadata
                old_sz = matched_cluster["rep"]["cluster_size"]
                old_srcs = matched_cluster["rep"]["syndicated_sources"]
                new_rep = dict(item)
                new_rep["cluster_size"] = old_sz
                new_rep["syndicated_sources"] = old_srcs
                matched_cluster["rep"] = new_rep
                matched_cluster["cred"] = cred
                matched_cluster["tokens"] = toks
                matched_cluster["exact"] = norm_exact

    return [cl["rep"] for cl in clusters]


def score_news_items_institutional(
    items: List[Dict[str, Any]], now: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Computes deduplicated, source-credibility-, time-decay-, and severity-weighted sentiment.
    """
    raw_count = len(items or [])
    clustered = cluster_duplicate_headlines(items or [])
    if not clustered:
        return {
            "raw_count": 0,
            "clustered_count": 0,
            "bullish": 0,
            "bearish": 0,
            "neutral": 0,
            "weighted_score": 0.0,
            "critical_alerts": [],
            "clustered_items": [],
        }

    bull_cnt = 0
    bear_cnt = 0
    neut_cnt = 0
    weighted_sum = 0.0
    total_wt = 0.0
    critical_alerts: List[str] = []

    for it in clustered:
        lbl = str(it.get("sentiment_label") or "")
        is_bull = "Bullish" in lbl
        is_bear = "Bearish" in lbl
        if is_bull:
            bull_cnt += 1
            base_pol = 1.0
        elif is_bear:
            bear_cnt += 1
            base_pol = -1.0
        else:
            neut_cnt += 1
            base_pol = 0.0

        # Prefer signed score magnitude when present (at least 0.6 for unambiguous Bullish/Bearish)
        raw_sc = it.get("sentiment_score")
        if raw_sc is not None:
            try:
                sc_f = float(raw_sc)
                if is_bull:
                    signed = max(0.6, min(1.0, abs(sc_f)))
                elif is_bear:
                    signed = -max(0.6, min(1.0, abs(sc_f)))
                else:
                    signed = max(-1.0, min(1.0, sc_f))
            except (TypeError, ValueError):
                signed = base_pol
        else:
            signed = base_pol

        cred_wt = get_source_credibility_weight(it.get("source"))
        decay_wt = compute_time_decay_weight(it.get("pub_date"), now=now)
        sev_wt, sev_tier = compute_event_severity(it.get("title", ""), it.get("snippet", ""))
        item_wt = cred_wt * decay_wt * sev_wt

        it["credibility_weight"] = cred_wt
        it["time_decay_weight"] = decay_wt
        it["severity_tier"] = sev_tier
        it["effective_weight"] = round(item_wt, 3)

        if sev_tier == "CRITICAL" and it.get("title"):
            critical_alerts.append(it["title"])

        weighted_sum += signed * item_wt
        total_wt += item_wt

    w_score = round(weighted_sum / total_wt, 3) if total_wt > 0 else 0.0
    w_score = max(-1.0, min(1.0, w_score))

    return {
        "raw_count": raw_count,
        "clustered_count": len(clustered),
        "bullish": bull_cnt,
        "bearish": bear_cnt,
        "neutral": neut_cnt,
        "weighted_score": w_score,
        "critical_alerts": critical_alerts,
        "clustered_items": clustered,
    }


class NewsSentimentEngine:
    def __init__(self, cache_manager: CacheManager = None):
        self.cache_manager = cache_manager or CacheManager()

    def _quick_sentiment_score(self, text: str):
        """Word-boundary, negation-aware sentiment classifier for genuine corporate operational events."""
        text_lower = text.lower()
        # Normalize negated/idiomatic phrases before lexicon matching so e.g. "ban" never matches "bank",
        # "stop-loss" doesn't trigger "loss", and "cuts dividend" scores bearish instead of bullish.
        text_norm = re.sub(r"\bstop[-\s]?loss\b", " ", text_lower)
        text_norm = re.sub(r"\b(?:loss\s+narrows|narrows\s+loss|lifts\s+ban|ban\s+lifted|lifts\s+curbs|curbs\s+lifted|strikes\s+deal)\b", " __pos__ ", text_norm)
        text_norm = re.sub(r"\b(?:no\s+dividend|cuts?\s+dividend|skips?\s+dividend|slowing\s+growth|weak\s+demand|cancels?\s+order|order\s+cancelled|no\s+expansion)\b", " __neg__ ", text_norm)

        bullish_words = [
            "order win", "bags contract", "secures order", "profit surge", "profit rise",
            "profit jump", "revenue surge", "revenue growth", "capacity expansion",
            "commissioning", "approval granted", "patent granted", "debt reduction",
            "dividend", "record profit", "margin expansion", "acquisition", "deal signed",
            "joint venture", "commercial operations", "contract award", "expansion",
            "growth", "turnaround", "order book", "strong demand", "partnership", "__pos__"
        ]
        bearish_words = [
            "order cancellation", "profit drop", "profit slump", "loss widens",
            "revenue decline", "plant shutdown", "tax notice", "penalty",
            "investigation", "sebi probe", "fraud", "debt default", "litigation",
            "strike", "credit downgrade", "resignation", "margin contraction",
            "curbs", "ban", "loss", "slump", "deficit", "scam", "delay", "__neg__"
        ]

        tagged = []
        for w in bullish_words:
            tagged.append((w, 1))
        for w in bearish_words:
            tagged.append((w, -1))
        # Longest phrases first so composite phrases consume spans and prevent double-counting
        tagged.sort(key=lambda item: len(item[0]), reverse=True)

        bull_count = 0
        bear_count = 0
        masked = text_norm
        for w, polarity in tagged:
            pat = re.compile(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])")
            if pat.search(masked):
                if polarity > 0:
                    bull_count += 1
                else:
                    bear_count += 1
                masked = pat.sub(" ", masked)

        score = bull_count - bear_count
        if score > 0:
            return "Bullish", min(1.0, round(0.2 + (score * 0.2), 2))
        elif score < 0:
            return "Bearish", max(-1.0, round(-0.2 + (score * 0.2), 2))
        return "Neutral", 0.0

    def fetch_stock_news(self, symbol: str, company_name: str = "", force_refresh: bool = False, max_items: int = 10) -> List[Dict[str, Any]]:
        """
        Checks SQLite cache first. If empty or stale (>24h), fetches live multi-source news
        for the symbol via Google News RSS aggregator, targeting business activities (orders,
        deals, expansions, financials) and filtering out broker recommendations and stock tips.
        """
        symbol = symbol.upper()
        if not force_refresh:
            cached_news = self.cache_manager.get_cached_news(symbol, max_age_hours=24)
            if cached_news:
                return cached_news

        fetched_items: List[Dict[str, Any]] = []
        seen_titles = set()

        # Build query focused on actual business activity without stripping distinctive words down to generic stems
        clean_name = re.sub(r"\b(Limited|Ltd\.?|Corp\.?|Corporation|Pvt\.?|Private)\b", "", company_name or "", flags=re.I)
        clean_name = re.sub(r"\(India\)", "", clean_name, flags=re.I)
        clean_name = " ".join(clean_name.split())
        if len(clean_name.split()) >= 2:
            stripped_suffix = " ".join(re.sub(r"\b(Industries|Technologies|Services)\b", "", clean_name, flags=re.I).split())
            if len(stripped_suffix.split()) >= 2:
                clean_name = stripped_suffix
        name_term = f'"{clean_name}"' if (clean_name and len(clean_name) >= 3) else f'"{symbol}"'

        # Primary query: Target recent (14d) business activity, exclude recommendation spam
        query_str = f'{name_term} (order OR contract OR deal OR acquisition OR expansion OR profit OR plant OR commissioning OR partnership OR revenue OR dividend) -recommendation -brokerage -"stocks to watch" -"share price" when:14d'

        rss_items = self._fetch_rss_query(query_str, symbol, max_items=max_items)
        for item in rss_items:
            norm_title = re.sub(r"[^\w\s]", "", item["title"].lower())
            if norm_title not in seen_titles:
                seen_titles.add(norm_title)
                fetched_items.append(item)

        # Fallback query if no operational news found
        if not fetched_items:
            fallback_query = f'{name_term} (business OR company OR management OR quarterly OR results) -recommendation -brokerage when:14d'
            fallback_items = self._fetch_rss_query(fallback_query, symbol, max_items=max_items)
            for item in fallback_items:
                norm_title = re.sub(r"[^\w\s]", "", item["title"].lower())
                if norm_title not in seen_titles:
                    seen_titles.add(norm_title)
                    fetched_items.append(item)

        if fetched_items:
            self.cache_manager.save_news(symbol, fetched_items)

        return fetched_items

    def _fetch_rss_query(self, query_str: str, tag: str = "", max_items: int = 10) -> List[Dict[str, Any]]:
        """Fetches Google News RSS search feed, filtering spam and classifying business events."""
        encoded_query = urllib.parse.quote(query_str)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        items: List[Dict[str, Any]] = []

        try:
            req = urllib.request.Request(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                root = ET.fromstring(resp.read())
                for item_elem in root.findall(".//item"):
                    raw_title = clean_text(item_elem.findtext("title", ""))
                    link = item_elem.findtext("link", "")
                    pub_date = item_elem.findtext("pubDate", "")
                    raw_desc = clean_text(item_elem.findtext("description", ""))

                    source_elem = item_elem.find("source")
                    source_name = source_elem.text.strip() if source_elem is not None and source_elem.text else "Web News"

                    title = raw_title
                    if " - " in title and source_name != "Web News":
                        parts = title.rsplit(" - ", 1)
                        if parts[1].strip().lower() == source_name.lower():
                            title = parts[0].strip()

                    clean_snip = raw_desc
                    if source_name and clean_snip.endswith(source_name):
                        clean_snip = clean_snip[:-len(source_name)].strip()
                    snippet = clean_snip if (clean_snip and clean_snip != raw_title) else raw_title

                    # Filter out broker recommendations, stock tip lists, and price target noise
                    if is_recommendation_spam(title, snippet):
                        continue

                    # Classify into structured business activity category
                    category, badge = classify_business_activity(title, snippet)

                    sentiment_label, score = self._quick_sentiment_score(f"{title}. {snippet}")

                    items.append({
                        "symbol": tag,
                        "url": link,
                        "title": title,
                        "snippet": snippet,
                        "category": category,
                        "category_badge": badge,
                        "source": source_name,
                        "pub_date": pub_date or datetime.now().strftime("%a, %d %b %Y %H:%M:%S GMT"),
                        "sentiment_score": score,
                        "sentiment_label": sentiment_label
                    })
                    if len(items) >= max_items:
                        break
        except Exception as e:
            if VERBOSE_LOGGING:
                print(f"  ⚠️ [RSS Notice] Could not fetch for '{query_str}': {e}")

        return items

    # Telemetry names used by the report -> canonical indicator names in tools/macro_tools.py
    _TELEMETRY_NAMES = {
        "Brent Crude Oil": "Brent Crude Oil",
        "WTI Crude Oil": "WTI Crude Oil",
        "USD / INR (Rupee)": "USD / INR (Rupee)",
        "US Dollar Index (DXY)": "US Dollar Index (DXY)",
        "US 10Y Treasury Yield": "US 10Y Treasury Yield",
        "S&P 500 Index": "S&P 500",
        "Nasdaq Composite": "Nasdaq",
        "Gold Futures": "Gold Futures",
    }
    _TELEMETRY_UNITS = {
        "Brent Crude Oil": "USD/bbl", "WTI Crude Oil": "USD/bbl", "USD / INR (Rupee)": "INR",
        "US Dollar Index (DXY)": "pts", "US 10Y Treasury Yield": "%", "S&P 500 Index": "pts",
        "Nasdaq Composite": "pts", "Gold Futures": "USD/oz",
    }

    def fetch_market_macro_telemetry(self) -> Dict[str, Any]:
        """
        Real market indicators only (shared parallel fetch + cache in GlobalMacroEngine, max 1h old).
        Indicators that could not be fetched are simply absent from the result -- nothing is invented.
        """
        macro = GlobalMacroEngine(self.cache_manager).fetch_macro_indicators(max_age_hours=1)
        by_name = {m["indicator"]: m for m in macro.get("indicators", [])}

        results: Dict[str, Any] = {}
        for report_name, canon in self._TELEMETRY_NAMES.items():
            m = by_name.get(canon)
            if not m or m.get("value") is None:
                continue
            results[report_name] = {
                "price": m["value"],
                "change_pct": m.get("pct_change"),
                "unit": self._TELEMETRY_UNITS[report_name],
                "category": m.get("category", ""),
                "stale": bool(m.get("stale")),
            }
        return results

    def fetch_generic_market_news(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Fetches curated news across macro drivers:
        - Crude Oil developments
        - Rupee (USD/INR) & Forex news
        - FII / DII Institutional Flows & Domestic Catalysts
        - Direct premier financial headlines from Economic Times, Livemint, and Moneycontrol
        """
        def _fetch_et():
            return self._fetch_direct_rss("The Economic Times", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms", 6)

        def _fetch_mint():
            return self._fetch_direct_rss("Livemint", "https://www.livemint.com/rss/markets", 6)

        def _fetch_mc():
            return self._fetch_direct_rss("Moneycontrol", "https://www.moneycontrol.com/rss/business.xml", 6)

        def _fetch_oil():
            return self._fetch_rss_query("crude oil price OPEC energy India economy", "Oil", 5)

        def _fetch_rupee():
            return self._fetch_rss_query("Indian rupee USD INR currency RBI forex reserves", "Rupee", 5)

        def _fetch_fii():
            return self._fetch_rss_query("FII DII institutional flows Indian stock market Nifty", "FII_DII", 5)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            fut_et = executor.submit(_fetch_et)
            fut_mint = executor.submit(_fetch_mint)
            fut_mc = executor.submit(_fetch_mc)
            fut_oil = executor.submit(_fetch_oil)
            fut_rupee = executor.submit(_fetch_rupee)
            fut_fii = executor.submit(_fetch_fii)

            return {
                "market_headlines": (fut_et.result() + fut_mint.result() + fut_mc.result()),
                "oil_news": fut_oil.result(),
                "rupee_news": fut_rupee.result(),
                "fii_news": fut_fii.result()
            }

    def _fetch_direct_rss(self, source_name: str, feed_url: str, max_items: int = 5) -> List[Dict[str, Any]]:
        """Parses direct RSS feed from premier media."""
        items = []
        try:
            req = urllib.request.Request(
                feed_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            )
            with urllib.request.urlopen(req, timeout=6.0) as resp:
                root = ET.fromstring(resp.read())
                for item_elem in root.findall(".//item")[:max_items]:
                    title = clean_text(item_elem.findtext("title", ""))
                    link = item_elem.findtext("link", "")
                    pub_date = item_elem.findtext("pubDate", "")
                    desc = clean_text(item_elem.findtext("description", ""))
                    if title:
                        if is_recommendation_spam(title, desc):
                            continue
                        label, score = self._quick_sentiment_score(f"{title}. {desc}")
                        items.append({
                            "source": source_name,
                            "title": title,
                            "url": link,
                            "pub_date": pub_date,
                            "snippet": desc if desc and desc != title else title,
                            "sentiment_label": label,
                            "sentiment_score": score
                        })
        except Exception as e:
            if VERBOSE_LOGGING:
                print(f"  ⚠️ [Direct RSS Notice] {source_name}: {e}")
        return items

    def generate_both_reports(
        self,
        symbols: Optional[List[Dict[str, Any]]] = None,
        date_str: Optional[str] = None,
        output_base_dir: Optional[str] = None,
        force_refresh: bool = False,
        max_workers: int = 6
    ) -> Dict[str, Any]:
        """
        Creates exactly two markdown files in news_reports/<date_str>/:
        1. general_market_news.md (Generic macro news: Oil, Rupee, US/Global cues, FII/DII, Market catalysts)
        2. stock_specific_news.md (Stock-specific news from multiple sources in a SINGLE consolidated file)
        """
        if not date_str:
            date_str = datetime.now().strftime("%Y-%m-%d")

        news_base = output_base_dir or os.path.join(PROJECT_ROOT, "news_reports")
        date_folder = os.path.join(news_base, date_str)
        os.makedirs(date_folder, exist_ok=True)

        if symbols is None:
            if os.path.exists(SYMBOLS_FILE_PATH):
                with open(SYMBOLS_FILE_PATH, "r", encoding="utf-8") as f:
                    symbols = json.load(f).get("symbols", [])
            else:
                symbols = []

        print(f"\n================================================================================")
        print(f"  📰 GENERATING DAILY NEWS REPORTS (2 FILES)")
        print(f"  📁 Date Folder: {date_folder}")
        print(f"  1️⃣  general_market_news.md (Common: Oil, Rupee, Macro & Market Drivers)")
        print(f"  2️⃣  stock_specific_news.md (Stock Specific: All {len(symbols)} stocks in one file)")
        print(f"================================================================================")

        # -------------------------------------------------------------
        # FILE 1: GENERAL MARKET & MACRO NEWS
        # -------------------------------------------------------------
        print("  🌐 Fetching live macro metrics (Crude, Rupee, DXY, US yields) & macro news...")
        telemetry = self.fetch_market_macro_telemetry()
        macro_news = self.fetch_generic_market_news()

        brent = telemetry.get("Brent Crude Oil", {})
        wti = telemetry.get("WTI Crude Oil", {})
        rupee = telemetry.get("USD / INR (Rupee)", {})
        dxy = telemetry.get("US Dollar Index (DXY)", {})
        yield_10y = telemetry.get("US 10Y Treasury Yield", {})
        sp500 = telemetry.get("S&P 500 Index", {})
        nasdaq = telemetry.get("Nasdaq Composite", {})
        gold = telemetry.get("Gold Futures", {})

        def _px(d, prefix="", suffix=""):
            return f"{prefix}{d['price']}{suffix}" if d.get("price") is not None else "N/A"

        def _chg(d):
            return f"{d['change_pct']:+.2f}%" if d.get("change_pct") is not None else "N/A"

        g_md = []
        g_md.append(f"# 🌐 General Market News & Macro Trend Report — {date_str}")
        g_md.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')} | **Classification**: Common / Macro News\n")
        g_md.append("> **Summary**: Key global and domestic macro drivers affecting Indian stock market movements (Crude Oil, Rupee/USD exchange rate, FII/DII institutional flows, inflation, and breaking news catalysts).\n")
        g_md.append("---")

        # Telemetry Dashboard
        g_md.append("\n## 📊 Live Macro Telemetry Dashboard\n")
        g_md.append("| Indicator | Value | Daily Change | Key Impact on Indian Equities |")
        g_md.append("| :--- | :---: | :---: | :--- |")
        if brent.get("price") is None:
            brent_impact = "Data unavailable"
        else:
            brent_impact = '🔴 Headwind: Elevates import bill & inflation' if brent["price"] > 85 else '🟢 Tailwind: Benign crude aids margins'
        if rupee.get("change_pct") is None:
            rupee_impact = "Data unavailable"
        else:
            rupee_impact = '🔴 Weakening rupee pressurizes CAD & imported inputs' if rupee["change_pct"] > 0.1 else '🟢 Stable rupee bolsters FII confidence & currency stability'
        g_md.append(f"| **🛢️ Brent Crude Oil** | `{_px(brent, '$')}` | `{_chg(brent)}` | {brent_impact} |")
        g_md.append(f"| **🛢️ WTI Crude Oil** | `{_px(wti, '$')}` | `{_chg(wti)}` | US energy benchmark; impacts global transport costs |")
        g_md.append(f"| **💵 USD / INR (Rupee)** | `{_px(rupee, '₹')}` | `{_chg(rupee)}` | {rupee_impact} |")
        g_md.append(f"| **💵 US Dollar Index (DXY)** | `{_px(dxy, '', ' pts')}` | `{_chg(dxy)}` | Stronger dollar drives capital outflows from Emerging Markets |")
        g_md.append(f"| **📈 US 10Y Bond Yield** | `{_px(yield_10y, '', '%')}` | `{_chg(yield_10y)}` | Elevated US yields trigger FII equity sales into US debt |")
        g_md.append(f"| **🇺🇸 S&P 500 Index** | `{_px(sp500, '', ' pts')}` | `{_chg(sp500)}` | Global risk appetite bellwether |")
        g_md.append(f"| **💻 Nasdaq Composite** | `{_px(nasdaq, '', ' pts')}` | `{_chg(nasdaq)}` | Key lead indicator for Indian IT sector stocks |")
        g_md.append(f"| **🪙 Gold Futures** | `{_px(gold, '$')}` | `{_chg(gold)}` | Safe-haven demand proxy amidst geopolitical stress |")
        g_md.append("\n---\n")

        # 1. Crude Oil Detailed Trend
        g_md.append("## 🛢️ 1. Crude Oil Trend & Economic Impact")
        g_md.append(f"**Current Brent Price**: `{_px(brent, '$', ' / bbl')}` ({_chg(brent)})  ")
        g_md.append(f"**Current WTI Price**: `{_px(wti, '$', ' / bbl')}` ({_chg(wti)})\n")
        g_md.append("### Sectoral Transmission Channels:")
        g_md.append("- **Oil Marketing Companies (IOC, BPCL, HPCL)**: Higher crude squeezes retail fuel gross marketing margins.")
        g_md.append("- **Aviation & Logistics (InterGlobe Aviation)**: Aviation Turbine Fuel (ATF) accounts for ~40% of operating costs.")
        g_md.append("- **Paints & Specialty Chemicals (Asian Paints, Berger)**: Crude derivatives form critical raw material inputs (titanium dioxide, solvents).")
        g_md.append("- **Upstream Producers (ONGC, Oil India)**: Direct beneficiaries of higher realization per barrel.\n")
        
        if macro_news["oil_news"]:
            g_md.append("### Latest Crude Oil Market Headlines:")
            for it in macro_news["oil_news"]:
                t_link = f"[{it['title']}]({it['url']})" if it.get("url") else it["title"]
                sig = "🟢 Bullish" if "Bullish" in it.get("sentiment_label", "") else ("🔴 Bearish" if "Bearish" in it.get("sentiment_label", "") else "⚪ Neutral")
                g_md.append(f"- **[{it['source']}]** {t_link} *({it['pub_date'][:25]})* — {sig}")
                if it.get("snippet") and it.get("snippet") != it["title"]:
                    g_md.append(f"  > {it['snippet'][:180]}...")
            g_md.append("")
        g_md.append("---\n")

        # 2. Rupee Trend
        g_md.append("## 💵 2. Indian Rupee (USD/INR) & Forex Dynamics")
        g_md.append(f"**Current Exchange Rate**: `{_px(rupee, '₹', ' per USD')}` ({_chg(rupee)})\n")
        g_md.append("### Market Implications:")
        g_md.append("- **IT & Tech Services (TCS, Infosys, Coforge)**: A weaker rupee boosts rupee revenue realizations from US-denominated billing.")
        g_md.append("- **Pharma Exporters (Sun Pharma, Cipla)**: Improved export margins in US and European markets.")
        g_md.append("- **Importers & Electronics (Dixon, Kaynes, Oil Refiners)**: Elevates component import landed costs.")
        g_md.append("- **RBI Defense**: RBI actively manages volatility using its forex reserves.\n")

        if macro_news["rupee_news"]:
            g_md.append("### Latest Rupee & Currency Headlines:")
            for it in macro_news["rupee_news"]:
                t_link = f"[{it['title']}]({it['url']})" if it.get("url") else it["title"]
                sig = "🟢 Bullish" if "Bullish" in it.get("sentiment_label", "") else ("🔴 Bearish" if "Bearish" in it.get("sentiment_label", "") else "⚪ Neutral")
                g_md.append(f"- **[{it['source']}]** {t_link} *({it['pub_date'][:25]})* — {sig}")
                if it.get("snippet") and it.get("snippet") != it["title"]:
                    g_md.append(f"  > {it['snippet'][:180]}...")
            g_md.append("")
        g_md.append("---\n")

        # 3. Institutional Flows & Domestic Catalysts
        g_md.append("## 🏦 3. Institutional Flows (FII / DII) & Domestic Catalysts")
        g_md.append("- **Foreign Institutional Investors (FII)**: Heavily sensitive to US 10Y yields and DXY dollar strength.")
        g_md.append("- **Domestic Institutional Investors (DII)**: Mutual fund SIP inflows continue to provide robust counter-cyclical liquidity.\n")
        
        if macro_news["fii_news"]:
            g_md.append("### Latest Institutional & Market Flow Headlines:")
            for it in macro_news["fii_news"]:
                t_link = f"[{it['title']}]({it['url']})" if it.get("url") else it["title"]
                sig = "🟢 Bullish" if "Bullish" in it.get("sentiment_label", "") else ("🔴 Bearish" if "Bearish" in it.get("sentiment_label", "") else "⚪ Neutral")
                g_md.append(f"- **[{it['source']}]** {t_link} *({it['pub_date'][:25]})* — {sig}")
                if it.get("snippet") and it.get("snippet") != it["title"]:
                    g_md.append(f"  > {it['snippet'][:180]}...")
            g_md.append("")
        g_md.append("---\n")

        # 4. Market-Moving Headlines
        g_md.append("## 📰 4. Curated Market-Moving Headlines of the Day")
        g_md.append("*Top breaking news curated directly from The Economic Times, Livemint, and Moneycontrol*\n")
        g_md.append("| Source | Headline | Published Time | Signal |")
        g_md.append("| :--- | :--- | :--- | :---: |")
        for mh in macro_news["market_headlines"]:
            t_link = f"[{mh['title']}]({mh['url']})" if mh.get("url") else mh['title']
            badge = "🟢 Bullish" if "Bullish" in mh.get("sentiment_label", "") else ("🔴 Bearish" if "Bearish" in mh.get("sentiment_label", "") else "⚪ Neutral")
            pub = mh.get("pub_date", "Today")[:25]
            g_md.append(f"| **{mh['source']}** | {t_link} | {pub} | {badge} |")
        g_md.append("\n---\n")

        general_market_file = os.path.join(date_folder, "general_market_news.md")
        with open(general_market_file, "w", encoding="utf-8") as f:
            f.write("\n".join(g_md))

        # -------------------------------------------------------------
        # FILE 2: STOCK SPECIFIC NEWS (ONE CONSOLIDATED FILE)
        # -------------------------------------------------------------
        print(f"  📈 Fetching stock-specific news from multiple sources for {len(symbols)} stocks...")
        stock_news_map: Dict[str, Dict[str, Any]] = {}
        all_sources_counter: Dict[str, int] = {}
        sentiment_tally = {"Bullish": 0, "Neutral": 0, "Bearish": 0}
        total_stock_articles = 0

        def _fetch_sym(stock_meta):
            sym = stock_meta.get("symbol", "").upper()
            c_name = stock_meta.get("name", "")
            sec = stock_meta.get("sector", "")
            items = self.fetch_stock_news(sym, c_name, force_refresh=force_refresh)
            return sym, c_name, sec, items

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            fut_to_sym = {executor.submit(_fetch_sym, s): s for s in symbols}
            for fut in concurrent.futures.as_completed(fut_to_sym):
                sym, c_name, sec, items = fut.result()
                stock_news_map[sym] = {"name": c_name, "sector": sec, "items": items}
                total_stock_articles += len(items)
                for it in items:
                    src = it.get("source", "Web")
                    all_sources_counter[src] = all_sources_counter.get(src, 0) + 1
                    lbl = it.get("sentiment_label", "Neutral")
                    if "Bullish" in lbl:
                        sentiment_tally["Bullish"] += 1
                    elif "Bearish" in lbl:
                        sentiment_tally["Bearish"] += 1
                    else:
                        sentiment_tally["Neutral"] += 1

        s_md = []
        s_md.append(f"# 📊 Stock-Specific News Digest — {date_str}")
        s_md.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')} | **Classification**: Tracked Equities Dossier  ")
        s_md.append(f"**Total Tracked Stocks**: {len(symbols)} | **Total Curated Articles**: {total_stock_articles}  ")
        s_md.append(f"**Aggregate Sentiment**: 🟢 Bullish: {sentiment_tally['Bullish']} | ⚪ Neutral: {sentiment_tally['Neutral']} | 🔴 Bearish: {sentiment_tally['Bearish']}\n")
        
        s_md.append("### 🌐 Distinct Information Sources Represented")
        source_pills = [f"`{k} ({v})`" for k, v in sorted(all_sources_counter.items(), key=lambda x: -x[1])[:10]]
        s_md.append(" • ".join(source_pills) + "\n")
        s_md.append("---")

        # Quick Index Table
        s_md.append("\n## 📑 Stock Quick Navigation & Sentiment Heatmap\n")
        s_md.append("| Symbol | Company Name | Sector | Articles | Primary Activity | Top Sources | Overall Signal |")
        s_md.append("| :--- | :--- | :--- | :---: | :--- | :--- | :---: |")

        for s in symbols:
            sym = s.get("symbol", "").upper()
            d = stock_news_map.get(sym, {"name": s.get("name", ""), "sector": s.get("sector", ""), "items": []})
            items = d["items"]
            sources_present = list(dict.fromkeys(it.get("source", "Web") for it in items))[:3]
            sources_str = ", ".join(sources_present) if sources_present else "N/A"
            avg_score = sum(it.get("sentiment_score", 0.0) for it in items) / max(1, len(items))

            # Determine dominant business activity category badge
            cat_counts = {}
            for it in items:
                cb = it.get("category_badge") or "🏢 [Corporate]"
                cat_counts[cb] = cat_counts.get(cb, 0) + 1
            primary_cat = sorted(cat_counts.items(), key=lambda x: -x[1])[0][0] if cat_counts else "🏢 [Corporate]"

            if avg_score > 0.15:
                sig = f"🟢 Bullish ({avg_score:+.2f})"
            elif avg_score < -0.15:
                sig = f"🔴 Bearish ({avg_score:+.2f})"
            else:
                sig = f"⚪ Neutral ({avg_score:+.2f})"

            anchor = f"{sym.lower()}---{d['name'].lower().replace(' ', '-').replace('&', '').replace('(', '').replace(')', '').replace('.', '')}"
            s_md.append(f"| [**{sym}**](#{anchor}) | {d['name']} | {d['sector']} | {len(items)} | {primary_cat} | {sources_str} | {sig} |")

        s_md.append("\n---\n")

        # Detailed Company-by-Company Breakdown (all in this single file!)
        s_md.append("## 🏢 Detailed Company-by-Company News Dossier\n")

        for s in symbols:
            sym = s.get("symbol", "").upper()
            d = stock_news_map.get(sym, {"name": s.get("name", ""), "sector": s.get("sector", ""), "items": []})
            items = d["items"]
            c_name = d["name"]
            sec = d["sector"]

            avg_score = sum(it.get("sentiment_score", 0.0) for it in items) / max(1, len(items))
            if avg_score > 0.15:
                verdict_badge = f"🟢 **Bullish Bias** (Score: {avg_score:+.2f})"
            elif avg_score < -0.15:
                verdict_badge = f"🔴 **Bearish Bias** (Score: {avg_score:+.2f})"
            else:
                verdict_badge = f"⚪ **Neutral / Balanced** (Score: {avg_score:+.2f})"

            s_md.append(f"### {sym} — {c_name}")
            s_md.append(f"**Sector**: {sec} | **Articles Collected**: {len(items)} | **News Verdict**: {verdict_badge}\n")

            if not items:
                s_md.append("*No recent articles found for this stock today.*\n")
            else:
                for idx, it in enumerate(items, 1):
                    src = it.get("source", "Web")
                    title = it.get("title", "")
                    url = it.get("url", "#")
                    title_link = f"[{title}]({url})" if url and url != "#" else title
                    pub = it.get("pub_date", "")[:25]
                    snip = it.get("snippet", "")
                    lbl = it.get("sentiment_label", "Neutral")
                    badge = "🟢 Bullish" if "Bullish" in lbl else ("🔴 Bearish" if "Bearish" in lbl else "⚪ Neutral")
                    cat_badge = it.get("category_badge", "🏢 [Corporate]")

                    s_md.append(f"{idx}. {cat_badge} **[{src}]** {title_link} *({pub})*")
                    if snip and snip != title:
                        s_md.append(f"   > {snip[:220]}...")
                    s_md.append(f"   > **Signal**: {badge} (Score: {it.get('sentiment_score', 0.0):+.2f})\n")

            s_md.append("---\n")

        stock_specific_file = os.path.join(date_folder, "stock_specific_news.md")
        with open(stock_specific_file, "w", encoding="utf-8") as f:
            f.write("\n".join(s_md))

        # Top-level pointers in news_reports/
        latest_market = os.path.join(news_base, "latest_market_news.md")
        latest_stocks = os.path.join(news_base, "latest_stocks_news.md")
        with open(latest_market, "w", encoding="utf-8") as f:
            f.write("\n".join(g_md))
        with open(latest_stocks, "w", encoding="utf-8") as f:
            f.write("\n".join(s_md))

        print(f"\n================================================================================")
        print(f"  🎉 SUCCESS! 2 REPORT FILES GENERATED IN {date_folder}")
        print(f"  1️⃣  Generic News:        {general_market_file}")
        print(f"  2️⃣  Stock-Specific News: {stock_specific_file}")
        print(f"================================================================================\n")

        return {
            "date_folder": date_folder,
            "general_market_news": general_market_file,
            "stock_specific_news": stock_specific_file,
            "latest_market": latest_market,
            "latest_stocks": latest_stocks
        }


if __name__ == "__main__":
    engine = NewsSentimentEngine()
    engine.generate_both_reports()
