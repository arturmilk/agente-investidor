"""Cliente da API brapi.dev v2 (dados da B3).

Sem token: apenas PETR4, VALE3, ITUB4, MGLU3 respondem.
Com token (free): qualquer ticker, 15k req/mês.
"""
import json
import os
import time
import urllib.parse

import requests

from config import BASE_URL, BRAPI_TOKEN

_HEADERS = {"User-Agent": "agente-bolsa/1.0"}
if BRAPI_TOKEN:
    _HEADERS["Authorization"] = f"Bearer {BRAPI_TOKEN}"

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Controle de taxa: o plano gratuito impõe limite por rajada (429).
# Espaçamos as chamadas e fazemos backoff exponencial em 429.
_last_req = 0.0
_MIN_INTERVAL = 0.4  # segundos entre requisições


def _throttle():
    global _last_req
    wait = _MIN_INTERVAL - (time.time() - _last_req)
    if wait > 0:
        time.sleep(wait)
    _last_req = time.time()


def _cache_path(url: str) -> str:
    key = url.replace("/", "_").replace(":", "_").replace("?", "_").replace("&", "_").replace("=", "_")
    return os.path.join(CACHE_DIR, key[-140:] + ".json")


def _get(path: str, params: dict = None, use_cache: bool = True, ttl: int = 1800):
    url = BASE_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    cp = _cache_path(url)
    if use_cache and os.path.exists(cp) and (time.time() - os.path.getmtime(cp)) < ttl:
        with open(cp, "r", encoding="utf-8") as f:
            return json.load(f)

    last_err = None
    for attempt in range(6):
        try:
            _throttle()
            r = requests.get(url, headers=_HEADERS, timeout=30)
            r.raise_for_status()
            j = r.json()
            if j.get("error"):
                raise RuntimeError(f"brapi: {j.get('message')} (código {j.get('code')})")
            if use_cache:
                with open(cp, "w", encoding="utf-8") as f:
                    json.dump(j, f, ensure_ascii=False)
            return j
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                backoff = min(30, 2 ** (attempt + 1))
                time.sleep(backoff)
                last_err = e
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Falha ao buscar {path}: {last_err}")


def _data(j, idx=0):
    return j["results"][idx]["data"]


def fetch_ticker(symbol: str) -> dict:
    """Coleta todos os dados de um ticker: cotação/perfil via brapi (grátis)
    e fundamentos via yfinance (grátis). Retorna dict no formato do analysis.py."""
    import fundamentals
    s = symbol.strip().upper()

    quote = _data(_get("/stocks/quote", {"symbols": s}))
    try:
        profile = _data(_get("/stocks/profile", {"symbols": s}))
    except Exception:
        profile = {}

    yf = fundamentals.fetch_yf(s)

    # CVM (fonte primária/ouro) — corrige bancos/Petrobras/ADRs; nunca bloqueia se falhar
    cvm = {}
    try:
        import cvm as _cvm
        nome = quote.get("longName") or quote.get("shortName") or ""
        cvm = _cvm.get_fundamentals(s, nome)
    except Exception:
        cvm = {}

    return {
        "symbol": s,
        "quote": quote,
        "profile": profile,
        "income_statement": yf["income_statement"],
        "balance_sheet": yf["balance_sheet"],
        "cash_flow": yf["cash_flow"],
        "info": yf["info"],
        "dividends_12m": yf["dividends_12m"],
        "cvm": cvm,
    }


def macro() -> dict:
    """Dados macro (Selic, IPCA, PIB etc.). Requer token."""
    return _data(_get("/macro/latest"))


def quote_index(symbol: str = "^BVSP") -> dict:
    """Cotação de um índice. Requer token."""
    return _data(_get("/stocks/quote", {"symbols": symbol}))
