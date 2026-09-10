"""Contexto macroeconômico — fontes gratuitas (sem plano pago).

- IBOV (pontos): brapi.dev `^BVSP`
- IPCA 12 meses (%): Banco Central SGS série 13522
- Selic efetiva anualizada (% a.a.): Banco Central SGS 4390 (compõe 12 meses)
- Câmbio USD/BRL: Banco Central SGS série 1 (última cotação)

Tudo degrada graciosamente: se uma fonte falhar, o campo volta None.
"""
import requests

from brapi import _get

BCB = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados?formato=json"


def _bcb(serie, data_inicial=None, data_final=None):
    url = BCB.format(serie)
    if data_inicial:
        url += f"&dataInicial={data_inicial}"
    if data_final:
        url += f"&dataFinal={data_final}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    d = r.json()
    return d if isinstance(d, list) else None


def selic_anualizada():
    """Selic efetiva (a.a.), compondo os últimos 12 meses da série mensal."""
    try:
        d = _bcb(4390)
        if not d or len(d) < 12:
            return None
        fator = 1.0
        for x in d[-12:]:
            fator *= (1 + float(x["valor"]) / 100)
        return (fator - 1) * 100
    except Exception:
        return None


def ipca_12m():
    """IPCA acumulado 12 meses (%)."""
    try:
        d = _bcb(13522)
        return float(d[-1]["valor"]) if d else None
    except Exception:
        return None


def cambio_usd():
    """Cotação USD/BRL (última)."""
    try:
        d = _bcb(1, data_inicial="01/07/2026", data_final="08/09/2026")
        return float(d[-1]["valor"]) if d else None
    except Exception:
        return None


def ibov():
    """Pontos do Ibovespa."""
    try:
        return _get("/stocks/quote", {"symbols": "^BVSP"})["results"][0]["data"]["regularMarketPrice"]
    except Exception:
        return None


def snapshot():
    return {
        "ibov": ibov(),
        "ipca_12m": ipca_12m(),
        "selic_anualizada": selic_anualizada(),
        "cambio_usd_brl": cambio_usd(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
