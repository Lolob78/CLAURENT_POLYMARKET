"""Moteur de news factuelles pour l'analyse des marchés.

Deux sources gratuites sans clé API :
- Google News RSS  : news ACTUELLES (bot 24/7 live)
- GDELT            : news DATÉES par fenêtre temporelle (backtest OOS honnête)

Le but : donner au judge des FAITS (titres, sources, dates) au lieu de
"no news available" — c'est ce qui transforme la chance en stratégie.
"""
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import List, Dict

import aiohttp

from src.utils.logger import get_logger

logger = get_logger("news_engine")

GOOGLE_NEWS = "https://news.google.com/rss/search"
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
GDELT_LOCK = asyncio.Lock()  # GDELT rate limit : 1 requête / 5s
GDELT_MIN_INTERVAL = 5.5
_last_gdelt = 0.0


def _parse_rss(xml_text: str, max_results: int) -> List[Dict]:
    """Parse un flux RSS Google News en liste de dicts {title, source, date}."""
    items = []
    try:
        root = ET.fromstring(xml_text)
        for it in root.findall(".//item"):
            title = (it.findtext("title") or "").strip()
            source = (it.findtext("source") or "").strip()
            pub = (it.findtext("pubDate") or "").strip()
            if title:
                items.append({"title": title, "source": source, "date": pub})
            if len(items) >= max_results:
                break
    except ET.ParseError as e:
        logger.warning("rss_parse_error", error=str(e))
    return items


def _clean_query(question: str) -> str:
    """Nettoie la question en mots-clés de recherche."""
    import re
    q = re.sub(r"^(will|is|are|does|can|has|would|should)\s+", "", question, flags=re.I)
    q = re.sub(r"\s*\?$", "", q).strip()
    q = re.sub(r"\s+by\s+(january|february|march|april|may|june|july|august|september|october|november|december).*$", "", q, flags=re.I)
    return q[:120]


async def fetch_news_now(question: str, max_results: int = 6) -> str:
    """News ACTUELLES via Google News RSS (bot live). Rapide, sans clé."""
    query = _clean_query(question)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                GOOGLE_NEWS,
                params={"q": query, "hl": "en-US", "gl": "US", "ceid": "US:en"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return "No recent news available."
                text = await resp.text()
        items = _parse_rss(text, max_results)
        if not items:
            return "No recent news available."
        lines = [f"- ({it['source']}) {it['title']}" for it in items]
        logger.info("news_fetched", source="google", count=len(items), query=query[:40])
        return "\n".join(lines)
    except Exception as e:
        logger.warning("news_fetch_error", source="google", error=str(e))
        return "No recent news available."


async def fetch_news_at(question: str, end_ts: int, max_results: int = 6,
                        window_days: int = 14) -> str:
    """News DATÉES via GDELT — fenêtre [end_ts - window_days, end_ts].

    Pour le backtest OOS : le LLM voit les news de l'ÉPOQUE, pas celles
    d'aujourd'hui (pas de look-ahead). Rate limit : 1 req / 5s.
    """
    global _last_gdelt
    query = _clean_query(question)
    end_dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    start_dt = end_dt - timedelta(days=window_days)
    start_str = start_dt.strftime("%Y%m%d%H%M%S")
    end_str = end_dt.strftime("%Y%m%d%H%M%S")
    try:
        # Respect du rate limit GDELT (1 requête / 5s)
        async with GDELT_LOCK:
            now = asyncio.get_event_loop().time()
            wait = GDELT_MIN_INTERVAL - (now - _last_gdelt)
            if wait > 0:
                await asyncio.sleep(wait)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    GDELT_URL,
                    params={
                        "query": f'"{query}"',
                        "mode": "artlist",
                        "maxrecords": max_results,
                        "format": "json",
                        "startdatetime": start_str,
                        "enddatetime": end_str,
                    },
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    _last_gdelt = asyncio.get_event_loop().time()
                    if resp.status != 200:
                        return "No news found for this period."
                    data = await resp.json()
        articles = data.get("articles", [])
        if not articles:
            return "No news found for this period."
        lines = []
        for a in articles[:max_results]:
            d = a.get("seendate", "")[:8]
            date_str = f"{d[0:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
            lines.append(f"- [{date_str}] ({a.get('domain', '?')}) {a.get('title', '')[:150]}")
        logger.info("news_fetched", source="gdelt", count=len(lines),
                    query=query[:40], start=start_str[:8], end=end_str[:8])
        return "\n".join(lines)
    except Exception as e:
        logger.warning("news_fetch_error", source="gdelt", error=str(e))
        return "No news found for this period."
