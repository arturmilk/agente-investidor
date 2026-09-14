"""Contexto macroeconômico — fontes gratuitas.

- Selic meta (% a.a.): Banco Central SGS 432
- IPCA acumulado 12 meses (%): SGS 13522
- Câmbio USD/BRL (PTAX venda): SGS 1
- Ibovespa: Yahoo (^BVSP), com variação em 12 meses

Tudo degrada graciosamente: se uma fonte falhar, o campo volta None.
"""
from config import CRESCIMENTO_PERPETUO, PREMIO_RISCO_ACOES
from market import historico
from net import get_json

SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados/ultimos/{}?formato=json"


def _sgs(serie):
    try:
        d = get_json(SGS.format(serie, 1), ttl=6 * 3600)
        return float(d[-1]["valor"]), d[-1]["data"]
    except Exception:
        return None, None


def snapshot() -> dict:
    selic, dt_selic = _sgs(432)
    ipca, dt_ipca = _sgs(13522)
    usd, dt_usd = _sgs(1)
    ibov = var12 = None
    h = historico("^BVSP", rng="2y")
    if h and h.get("preco"):
        ibov = h["preco"]
        m = h.get("mensal") or []
        if len(m) >= 13:
            var12 = ibov / m[-13][1] - 1
    out = {"selic_meta": selic, "selic_data": dt_selic, "ipca_12m": ipca, "ipca_data": dt_ipca,
           "cambio_usd_brl": usd, "cambio_data": dt_usd, "ibov": ibov, "ibov_var_12m": var12}
    if selic is not None:
        ke = selic / 100 + PREMIO_RISCO_ACOES
        out["custo_capital_proprio"] = ke
        out["crescimento_perpetuo"] = CRESCIMENTO_PERPETUO
        if ipca is not None:
            out["juro_real_aprox"] = (1 + selic / 100) / (1 + ipca / 100) - 1
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(snapshot(), ensure_ascii=False, indent=2))
