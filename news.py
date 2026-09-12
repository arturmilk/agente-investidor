"""Monitor de notícias por RSS — nível 3 do guia.

Fetches RSS abertos (InfoMoney, Valor, Brazil Journal, Money Times) e
filtra por palavras-chave (ticker, nome da empresa) e por janela de tempo
(padrão: últimos 3 meses).
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

import requests

from config import NEWS_FEEDS

_TAG_RE = re.compile(r"<[^>]+>")


def _norm(s: str) -> str:
    """Minúsculas + remove acentos (para casamento robusto de palavras)."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return s.lower()


def _clean(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").replace("&nbsp;", " ").strip()


def _parse_date(pub: str):
    if not pub:
        return None
    try:
        return parsedate_to_datetime(pub).replace(tzinfo=None)
    except Exception:
        return None


_feed_cache = {}


def fetch_feed(url: str, timeout: int = 25) -> list:
    if url in _feed_cache:
        return _feed_cache[url]
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (agente-bolsa)"}, timeout=timeout)
        r.raise_for_status()
    except Exception:
        return []
    try:
        root = ET.fromstring(r.content)
    except ET.ParseError:
        return []
    items = []
    for it in root.iter("item"):
        title = _clean(it.findtext("title", ""))
        link = (it.findtext("link") or "").strip()
        desc = _clean(it.findtext("description", ""))
        pub = (it.findtext("pubDate") or "").strip()
        if title:
            items.append({"titulo": title, "link": link, "resumo": desc[:400], "data": pub})
    _feed_cache[url] = items
    return items


def search_news(keywords, feeds: dict = None, max_results: int = 25, per_feed: int = 80,
                meses: int = 3) -> list:
    """Busca notícias dos últimos `meses` que contenham qualquer palavra-chave.

    keywords: lista de termos (ex.: ['PETR4', 'Petrobras']).
    """
    feeds = feeds or NEWS_FEEDS
    kws = [_norm(k) for k in keywords if k]
    corte = datetime.now() - timedelta(days=meses * 30)
    hits = []
    for source, url in feeds.items():
        for item in fetch_feed(url)[:per_feed]:
            dt = _parse_date(item.get("data"))
            if dt and dt < corte:
                continue
            text = _norm(f"{item['titulo']} {item['resumo']}")
            if any(k in text for k in kws):
                data = dt.strftime("%Y-%m-%d") if dt else (item.get("data") or "")
                hits.append({**item, "data": data, "fonte": source})
    # dedupe por link
    seen, unique = set(), []
    for h in hits:
        if h["link"] and h["link"] not in seen:
            seen.add(h["link"])
            unique.append(h)
    return unique[:max_results]
