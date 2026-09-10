"""Monitor de notícias por RSS — nível 3 do guia.

Fetches RSS abertos (InfoMoney, Valor, Brazil Journal, Money Times) e
filtra por palavras-chave (ticker, nome da empresa, setor, catalisadores).
"""
import re
import xml.etree.ElementTree as ET

import requests

from config import NEWS_FEEDS

_TAG_RE = re.compile(r"<[^>]+>")


def _clean(html: str) -> str:
    return _TAG_RE.sub(" ", html or "").replace("&nbsp;", " ").strip()


def fetch_feed(url: str, timeout: int = 25) -> list:
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
    return items


def search_news(keywords, feeds: dict = None, max_results: int = 25, per_feed: int = 60) -> list:
    """Busca notícias que contenham qualquer palavra-chave.

    keywords: lista de termos (ex.: ['PETR4', 'Petrobras']).
    """
    feeds = feeds or NEWS_FEEDS
    kws = [k.lower() for k in keywords if k]
    hits = []
    for source, url in feeds.items():
        for item in fetch_feed(url)[:per_feed]:
            text = f"{item['titulo']} {item['resumo']}".lower()
            if any(k in text for k in kws):
                hits.append({**item, "fonte": source})
    # dedupe por link
    seen, unique = set(), []
    for h in hits:
        if h["link"] and h["link"] not in seen:
            seen.add(h["link"])
            unique.append(h)
    return unique[:max_results]
