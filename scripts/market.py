"""Cotações e dados de mercado (brapi.dev + Yahoo Finance, sem custo).

- brapi.dev v2: lista completa da B3 com preço, volume e valor de mercado
  (`/tickers`, funciona até sem token) e cotação/perfil por ticker (exige o
  token gratuito; o plano grátis aceita 1 ativo por requisição).
- Yahoo Finance (aberto): cotação, histórico mensal de ~6 anos (preço
  ajustado por desdobramentos) e proventos por ação — base dos múltiplos
  históricos, do DY por classe e fallback de cotação.
- yfinance (opcional): consenso de preço-alvo, se estiver instalado.
"""
from __future__ import annotations

import urllib.parse
from datetime import datetime, timedelta, timezone

from config import BRAPI_BASE, BRAPI_TOKEN
from net import get_json, log

YAHOO_CHART = "https://query2.finance.yahoo.com/v8/finance/chart/{sym}?range={rng}&interval={itv}&events=div%2Csplit"
YAHOO_SPARK = "https://query1.finance.yahoo.com/v7/finance/spark?symbols={syms}&range=1d&interval=1d"


def _brapi(path, params=None, ttl=1800):
    url = BRAPI_BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"Authorization": f"Bearer {BRAPI_TOKEN}"} if BRAPI_TOKEN else None
    j = get_json(url, ttl=ttl, headers=headers)
    if isinstance(j, dict) and j.get("error"):
        raise RuntimeError(f"brapi: {j.get('message')}")
    return j


def _iso(ts):
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


def universo_b3(ttl=6 * 3600) -> list:
    """Todas as ações ativas da B3 (inclui units) com preço, volume e valor de mercado."""
    out, page = [], 1
    while page <= 10:
        j = _brapi("/tickers", {"limit": 1000, "page": page}, ttl=ttl)
        for x in j.get("results", []):
            if x.get("assetType") != "stock" or not x.get("isActive"):
                continue
            q = x.get("quote") or {}
            preco, vol = q.get("lastPrice"), q.get("volume")
            out.append({"symbol": x.get("symbol"), "nome": x.get("longName") or x.get("name"),
                        "setor_brapi": x.get("sector"), "subsetor": x.get("subsector"),
                        "preco": preco, "volume": vol, "market_cap": q.get("marketCap"),
                        "volume_financeiro": (preco or 0) * (vol or 0), "variacao_dia": q.get("changePercent")})
        if not (j.get("pagination") or {}).get("hasNextPage"):
            break
        page += 1
    return out


def historico(symbol, rng="6y", interval="1mo", ttl=6 * 3600) -> dict | None:
    """Yahoo: cotação atual, 52 semanas, fechamentos mensais e proventos por ação."""
    sym = symbol if symbol.startswith("^") or "." in symbol else symbol.upper() + ".SA"
    url = YAHOO_CHART.format(sym=urllib.parse.quote(sym), rng=rng, itv=interval)
    try:
        j = get_json(url, ttl=ttl)
    except Exception as e:
        log(f"Yahoo {symbol}: {e}")
        return None
    res = ((j.get("chart") or {}).get("result") or [None])[0]
    if not res:
        return None
    meta = res.get("meta") or {}
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    closes, vols = q.get("close") or [], q.get("volume") or []
    mensal = []
    for i, ts in enumerate(res.get("timestamp") or []):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        v = vols[i] if i < len(vols) else None
        mensal.append((_iso(ts), float(c), float(v) if v is not None else None))
    ev = res.get("events") or {}
    proventos = sorted((_iso(d.get("date")), float(d.get("amount") or 0)) for d in (ev.get("dividends") or {}).values())
    desdobr = sorted((_iso(s.get("date")), s.get("splitRatio")) for s in (ev.get("splits") or {}).values())
    return {"preco": meta.get("regularMarketPrice"), "min_52s": meta.get("fiftyTwoWeekLow"),
            "max_52s": meta.get("fiftyTwoWeekHigh"), "volume_dia": meta.get("regularMarketVolume"),
            "nome": meta.get("longName") or meta.get("shortName"), "data": _iso(meta.get("regularMarketTime")),
            "mensal": mensal, "proventos": proventos, "desdobramentos": desdobr}


def volume_medio(hist, meses=3):
    """Volume financeiro médio diário aproximado (R$) dos últimos meses completos."""
    if not hist or not hist.get("mensal"):
        return None
    barras = [b for b in hist["mensal"] if b[2]][-(meses + 1):-1]  # ignora o mês corrente (parcial)
    if not barras:
        return None
    return sum(c * v for _, c, v in barras) / (21.0 * len(barras))


def proventos_12m(hist, ref=None):
    """Soma dos proventos por ação pagos (data-ex) nos últimos 12 meses."""
    if not hist or not hist.get("proventos"):
        return 0.0 if hist else None
    ref = ref or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ini = (datetime.fromisoformat(ref) - timedelta(days=365)).strftime("%Y-%m-%d")
    return sum(v for d, v in hist["proventos"] if d and ini < d <= ref)


def cotacao(symbol) -> dict | None:
    """Cotação atual: brapi (com token) → Yahoo."""
    s = symbol.upper()
    if BRAPI_TOKEN:
        try:
            d = _brapi("/stocks/quote", {"symbols": s}, ttl=900)["results"][0]["data"]
            if d.get("regularMarketPrice"):
                return {"symbol": s, "preco": d.get("regularMarketPrice"), "market_cap": d.get("marketCap"),
                        "volume": d.get("regularMarketVolume"), "min_52s": d.get("fiftyTwoWeekLow"),
                        "max_52s": d.get("fiftyTwoWeekHigh"), "nome": d.get("longName") or d.get("shortName"),
                        "data": (d.get("regularMarketTime") or "")[:10], "fonte": "brapi"}
        except Exception as e:
            log(f"brapi cotação {s}: {e} — usando Yahoo")
    h = historico(s)
    if h and h.get("preco"):
        return {"symbol": s, "preco": h["preco"], "market_cap": None, "volume": h.get("volume_dia"),
                "min_52s": h.get("min_52s"), "max_52s": h.get("max_52s"), "nome": h.get("nome"),
                "data": h.get("data"), "fonte": "yahoo"}
    return None


def precos_lote(symbols) -> dict:
    """Preço atual de vários tickers via Yahoo spark (fallback sem brapi)."""
    out = {}
    syms = [s.upper() + ".SA" for s in symbols]
    for i in range(0, len(syms), 20):
        chunk = ",".join(syms[i:i + 20])
        try:
            j = get_json(YAHOO_SPARK.format(syms=urllib.parse.quote(chunk, safe=",.")), ttl=1800)
        except Exception as e:
            log(f"Yahoo spark: {e}")
            continue
        for r in (j.get("spark") or {}).get("result") or []:
            meta = ((r.get("response") or [{}])[0] or {}).get("meta") or {}
            if meta.get("regularMarketPrice"):
                out[r["symbol"].replace(".SA", "")] = {"preco": meta["regularMarketPrice"],
                                                       "volume": meta.get("regularMarketVolume")}
    return out


def perfil(symbol) -> dict:
    """Perfil (setor, indústria, descrição do negócio) — brapi, exige token."""
    if not BRAPI_TOKEN:
        return {}
    try:
        return _brapi("/stocks/profile", {"symbols": symbol.upper()}, ttl=7 * 86400)["results"][0]["data"] or {}
    except Exception:
        return {}


def consenso(symbol) -> dict | None:
    """Consenso de preço-alvo dos analistas (Yahoo via yfinance, opcional)."""
    try:
        import yfinance as yf
    except ImportError:
        return None
    try:
        info = yf.Ticker(symbol.upper() + ".SA").info or {}
    except Exception:
        return None
    alvo = info.get("targetMeanPrice")
    if not alvo:
        return None
    return {"preco_alvo_medio": alvo, "preco_alvo_min": info.get("targetLowPrice"),
            "preco_alvo_max": info.get("targetHighPrice"), "analistas": info.get("numberOfAnalystOpinions"),
            "recomendacao": info.get("recommendationKey")}
