"""B3 — API pública do site de empresas listadas (sem token).

Fornece o nº de ações ATUAL de cada companhia (ordinárias e preferenciais).
É o árbitro do valor de mercado quando a referência da brapi e o nº de ações
do último ITR da CVM divergem — por exemplo, após bonificação, desdobramento,
grupamento ou emissão ocorridos depois do último balanço.
"""
from __future__ import annotations

import base64
import json

from net import get_json, log

BASE = "https://sistemaswebb3-listados.b3.com.br/listedCompaniesProxy/CompanyCall/"
DIA = 86400


def _get(endpoint, payload, ttl):
    arg = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode()
    return get_json(BASE + endpoint + "/" + arg, ttl=ttl, timeout=20, retries=2)


def _int(s):
    try:
        return int(str(s).replace(".", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def detalhe(cd_cvm) -> dict:
    """Código do emissor (ex.: 'EGIE'), segmento e tickers/ISINs da companhia."""
    try:
        return _get("GetDetail", {"codeCVM": str(int(cd_cvm)), "language": "pt-br"}, ttl=30 * DIA) or {}
    except Exception as e:
        log(f"B3 detalhe {cd_cvm}: {e}")
        return {}


def suplemento(cd_cvm) -> dict:
    emissor = detalhe(cd_cvm).get("issuingCompany")
    if not emissor:
        return {}
    try:
        j = _get("GetListedSupplementCompany", {"issuingCompany": emissor, "language": "pt-br"}, ttl=3 * DIA)
    except Exception as e:
        log(f"B3 suplemento {emissor}: {e}")
        return {}
    return (j[0] if isinstance(j, list) and j else j) or {}


def acoes(cd_cvm) -> dict | None:
    """Nº de ações atual segundo a B3: {"on", "pn", "total"} (inclui tesouraria)."""
    s = suplemento(cd_cvm)
    on, pn = _int(s.get("numberCommonShares")), _int(s.get("numberPreferredShares"))
    if not on and not pn:
        return None
    return {"on": on or 0, "pn": pn or 0, "total": (on or 0) + (pn or 0)}
