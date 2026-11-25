"""
Primary-Source Corporate Catalyst Ingestion Engine.

Monitors primary Indian equity disclosure feeds:
  - NSE Corporate Announcements (orders, JVs, acquisitions, capacity expansion)
  - BSE Corporate Announcements
  - PIB (Press Information Bureau) Ministry releases
Degrades gracefully offline or when exchanges rate-limit.
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

from tools.catalyst_scorer import classify_catalyst_category, extract_deal_value_cr


_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def make_event_hash(source: str, symbol: str, announced_at: str, title: str) -> str:
    raw = f"{source.upper()}|{symbol.upper()}|{announced_at[:10]}|{title.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def fetch_nse_announcements(limit: int = 60, timeout: float = 6.0) -> List[Dict[str, Any]]:
    """Fetches latest equity corporate announcements from NSE India."""
    results: List[Dict[str, Any]] = []
    try:
        sess = requests.Session()
        sess.headers.update(_HEADERS)
        sess.get("https://www.nseindia.com", timeout=timeout)
        resp = sess.get(
            "https://www.nseindia.com/api/corporate-announcements?index=equities",
            timeout=timeout,
        )
        if resp.status_code != 200:
            return results
        items = resp.json()
        if not isinstance(items, list):
            return results

        for it in items[:limit]:
            sym = str(it.get("symbol") or "").upper().strip()
            desc = str(it.get("desc") or "").strip()
            att_text = str(it.get("attchmntText") or "").strip()
            title = desc or att_text
            if not sym or not title:
                continue
            dt_raw = str(it.get("an_dt") or it.get("sort_date") or datetime.now().strftime("%Y-%m-%d"))
            announced_at = dt_raw[:10]
            cat = classify_catalyst_category(title, att_text)
            results.append({
                "event_hash": make_event_hash("NSE", sym, announced_at, title),
                "symbol": sym,
                "company_name": str(it.get("sm_name") or sym).strip(),
                "source": "NSE",
                "source_url": str(it.get("attchmntFile") or "https://www.nseindia.com/companies-listing/corporate-filings-announcements"),
                "announced_at": announced_at,
                "title": title,
                "summary": att_text[:500],
                "category": cat,
                "deal_value_cr": extract_deal_value_cr(f"{title} {att_text}"),
            })
    except Exception:
        pass
    return results


def fetch_bse_announcements(limit: int = 40, timeout: float = 6.0) -> List[Dict[str, Any]]:
    """Fetches latest corporate announcements from BSE India."""
    results: List[Dict[str, Any]] = []
    try:
        today_str = datetime.now().strftime("%Y%m%d")
        url = (
            "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
            f"?pageno=1&strCat=-1&strPrevDate={today_str}&strScrip=&strSearch=P&strToDate={today_str}&strType=C&subcategory=-1"
        )
        headers = {**_HEADERS, "Referer": "https://www.bseindia.com/corporates/ann.html"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return results
        payload = resp.json()
        rows = payload.get("Table") or []
        for it in rows[:limit]:
            sym = str(it.get("SCRIP_CD") or it.get("SLONGNAME") or "").upper().strip()
            title = str(it.get("HEADLINE") or it.get("NEWSSUB") or "").strip()
            if not sym or not title:
                continue
            dt_raw = str(it.get("NEWS_DT") or datetime.now().strftime("%Y-%m-%d"))[:10]
            summary = str(it.get("MORE") or "")[:500]
            cat = classify_catalyst_category(title, summary)
            results.append({
                "event_hash": make_event_hash("BSE", sym, dt_raw, title),
                "symbol": sym,
                "company_name": str(it.get("SLONGNAME") or sym).strip(),
                "source": "BSE",
                "source_url": "https://www.bseindia.com/corporates/ann.html",
                "announced_at": dt_raw,
                "title": title,
                "summary": summary,
                "category": cat,
                "deal_value_cr": extract_deal_value_cr(f"{title} {summary}"),
            })
    except Exception:
        pass
    return results


def fetch_pib_releases(limit: int = 20, timeout: float = 5.0) -> List[Dict[str, Any]]:
    """Fetches PIB ministry press releases for policy & govt contract catalysts."""
    results: List[Dict[str, Any]] = []
    try:
        resp = requests.get(
            "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
            headers=_HEADERS,
            timeout=timeout,
        )
        if resp.status_code != 200 or not resp.text.strip():
            return results
        root = ET.fromstring(resp.text)
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "https://pib.gov.in/").strip()
            desc = (item.findtext("description") or "").strip()
            if not title:
                continue
            cat = classify_catalyst_category(title, desc)
            if cat == "ROUTINE":
                continue
            announced_at = datetime.now().strftime("%Y-%m-%d")
            results.append({
                "event_hash": make_event_hash("PIB", "GOVT", announced_at, title),
                "symbol": "GOVT_POLICY",
                "company_name": "Ministry / PIB Policy Release",
                "source": "PIB",
                "source_url": link,
                "announced_at": announced_at,
                "title": title,
                "summary": desc[:500],
                "category": cat,
                "deal_value_cr": extract_deal_value_cr(f"{title} {desc}"),
            })
    except Exception:
        pass
    return results


def collect_primary_catalysts(limit_per_source: int = 50) -> List[Dict[str, Any]]:
    """Collects and deduplicates announcements across NSE, BSE, and PIB."""
    seen = set()
    merged: List[Dict[str, Any]] = []
    for ev in (
        fetch_nse_announcements(limit=limit_per_source)
        + fetch_bse_announcements(limit=limit_per_source)
        + fetch_pib_releases(limit=20)
    ):
        h = ev["event_hash"]
        if h in seen:
            continue
        seen.add(h)
        merged.append(ev)
    return merged
