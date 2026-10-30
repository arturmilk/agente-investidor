"""Notícias e catalisadores.

- Google News (RSS de busca, aberto): manchetes por empresa nos últimos N dias
  — cobertura muito maior que feeds genéricos, que só guardam poucos dias.
- RSS de imprensa (InfoMoney, Valor, Brazil Journal, Money Times) filtrado
  por ticker/nome.
Os eventos oficiais (fato relevante, resultados, proventos) vêm do IPE da
CVM (ver cvm.eventos). Todo texto de terceiros passa por seguranca.limpar.
"""
from __future__ import annotations

import re
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from config import INDUSTRIA_GRUPO_KEYWORDS, INDUSTRIA_KEYWORDS, NEWS_FEEDS
from net import get_text, log
from seguranca import limpar, link_seguro

# frases comuns que geram falso positivo com nomes curtos (ex.: "Vale")
_RUIDO = ("vale a pena", "vale-refeicao", "vale-alimentacao", "vale refeicao", "vale alimentacao", "vale do ")
_GENERICOS = ("cotacao e indicadores", "dividendos, cotacao", "cotacao hoje", "grafico e historico")


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _data(pub):
    try:
        return parsedate_to_datetime(pub).replace(tzinfo=None)
    except Exception:
        return None


def _itens(xml_bytes):
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    out = []
    for it in root.iter("item"):
        titulo = limpar(it.findtext("title"), 200)
        if titulo:
            src = it.find("source")
            out.append({"titulo": titulo, "link": link_seguro(it.findtext("link")),
                        "resumo": limpar(it.findtext("description"), 300),
                        "dt": _data(it.findtext("pubDate") or ""),
                        "fonte": limpar(src.text, 60) if src is not None and src.text else None})
    return out


def _relevante(texto, termos):
    t = _norm(texto)
    if any(r in t for r in _RUIDO) and not any(len(k) >= 5 and k[-1].isdigit() and k in t for k in termos):
        return False
    return any(re.search(r"\b" + re.escape(k) + r"\b", t) for k in termos)


def google_news(termos, dias=90, max_itens=15) -> list:
    termos = [t for t in termos if t]
    if not termos:
        return []
    q = " OR ".join(f'"{t}"' for t in termos) + f" when:{dias}d"
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q, "hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"})
    try:
        itens = _itens(get_text(url, ttl=3 * 3600))
    except Exception as e:
        log(f"Google News: {e}")
        return []
    chaves = [_norm(t) for t in termos]
    corte = datetime.now() - timedelta(days=dias)
    out, vistos = [], set()
    for it in itens:
        if it["dt"] and it["dt"] < corte:
            continue
        if not _relevante(it["titulo"], chaves):
            continue
        if any(g in _norm(it["titulo"]) for g in _GENERICOS):  # páginas de cotação, não notícias
            continue
        base = _norm(re.sub(r"\s+-\s+[^-]+$", "", it["titulo"]))[:80]
        if base in vistos:
            continue
        vistos.add(base)
        out.append({"data": it["dt"].strftime("%Y-%m-%d") if it["dt"] else "", "titulo": it["titulo"],
                    "fonte": it["fonte"] or "Google News", "link": it["link"]})
    out.sort(key=lambda x: x["data"], reverse=True)
    return out[:max_itens]


def rss(termos, meses=3, max_itens=10) -> list:
    chaves = [_norm(t) for t in termos if t]
    corte = datetime.now() - timedelta(days=meses * 30)
    out, vistos = [], set()
    for fonte, url in NEWS_FEEDS.items():
        try:
            itens = _itens(get_text(url, ttl=3600, timeout=20, retries=2))
        except Exception:
            continue
        for it in itens:
            if it["dt"] and it["dt"] < corte:
                continue
            if _relevante(f"{it['titulo']} {it['resumo']}", chaves) and it["link"] not in vistos:
                vistos.add(it["link"])
                out.append({"data": it["dt"].strftime("%Y-%m-%d") if it["dt"] else "", "titulo": it["titulo"],
                            "fonte": fonte, "link": it["link"]})
    out.sort(key=lambda x: x["data"], reverse=True)
    return out[:max_itens]


def buscar(ticker, nome=None, dias=90) -> dict:
    termos = [ticker.upper()] + ([nome] if nome else [])
    return {"google_news": google_news(termos, dias=dias), "rss": rss(termos, meses=max(1, dias // 30))}


def industria(setor_base, grupo, dias=90, max_itens=10) -> list:
    """Notícias de TENDÊNCIA da indústria/setor (não da empresa) via Google News.

    Mapeia o setor_base da CVM para palavras-chave do setor e busca manchetes
    recentes — captura momentum setorial, rotação e ventos a favor/contra.
    """
    s = _norm(setor_base)
    kws = None
    for frag, words in INDUSTRIA_KEYWORDS:
        if _norm(frag) in s:
            kws = words
            break
    if not kws:
        kws = INDUSTRIA_GRUPO_KEYWORDS.get(grupo, [])
    if not kws:
        return []
    return google_news(kws, dias=dias, max_itens=max_itens)
