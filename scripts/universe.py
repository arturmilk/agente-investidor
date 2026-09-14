"""Universo B3: indicadores de todas as ações listadas + medianas por setor.

Usa só dados em lote (lista brapi com preço/volume/valor de mercado de toda a
bolsa + zips da CVM), então cobre ~350 companhias em segundos depois do
primeiro download. É a base do screener e da comparação setorial da análise
individual (P/L vs setor, percentis etc.).
"""
from __future__ import annotations

import json
import os
import statistics
import time
from datetime import datetime

import cvm
import indicators
import market
import scoring
import valuation
from config import CACHE_DIR
from net import log

ARQ = os.path.join(CACHE_DIR, "universo.json")
VERSAO = 1
TTL = 6 * 3600
MIN_PARES = 5
MIN_VOL_PARES = 500_000  # só entram nas medianas ações com algum giro
# (métrica, só positivos?)
CAMPOS = (("pl", True), ("pvp", True), ("ev_ebit", True), ("ev_ebitda", True), ("psr", True),
          ("dy", False), ("roe", False), ("roic", False), ("margem_liquida", False), ("dl_ebitda", False))


def _lista():
    """Preço/volume/valor de mercado de todas as ações: brapi (sem token) → Yahoo spark."""
    try:
        lista = market.universo_b3()
        if lista:
            return lista, "brapi"
    except Exception as e:
        log(f"lista brapi indisponível ({e}); usando Yahoo")
    tickers = list(cvm.fca()["tickers"])
    precos = market.precos_lote(tickers)
    return [{"symbol": t, "preco": p["preco"], "volume": p.get("volume"), "market_cap": None,
             "volume_financeiro": (p["preco"] or 0) * (p.get("volume") or 0)} for t, p in precos.items()], "yahoo"


def _agrupar(lista):
    f = cvm.fca()["tickers"]
    por_cd = {}
    for x in lista:
        info = f.get((x.get("symbol") or "").upper())
        if info and x.get("preco"):
            por_cd.setdefault(info["cd_cvm"], []).append({**x, **info})
    return por_cd


def medianas(recs):
    out = {"n": len(recs)}
    for campo, so_pos in CAMPOS:
        vals = [r["m"].get(campo) for r in recs]
        vals = [v for v in vals if v is not None and (v > 0 or not so_pos)]
        out[campo] = statistics.median(vals) if len(vals) >= 3 else None
    return out


def _pares_de(recs, setor_base, grupo, excluir=None):
    base = [r for r in recs if r["cd_cvm"] != excluir and (r.get("volume_financeiro") or 0) >= MIN_VOL_PARES]
    nivel = [("setor", [r for r in base if r["setor_base"] == setor_base]),
             ("grupo", [r for r in base if r["m"]["grupo"] == grupo]),
             ("mercado", base)]
    for nome, rs in nivel:
        if len(rs) >= MIN_PARES:
            return nome, rs
    return "mercado", base


def construir(macro=None) -> dict:
    t0 = time.time()
    lista, fonte = _lista()
    por_cd = _agrupar(lista)
    recs, emps = [], {}
    for cd, tks in por_cd.items():
        emp = cvm.empresa(cd)
        if not emp:
            continue
        tks.sort(key=lambda x: x.get("volume_financeiro") or 0)
        principal = tks[-1]
        precos_cl = {x["classe"]: x["preco"] for x in tks if x["classe"] in ("ON", "PN")}
        args = (emp, principal["preco"], principal["classe"], principal.get("market_cap"), precos_cl,
                principal.get("acoes_por_unit"))
        mcap, info = indicators.valor_mercado(*args)
        if info.get("fonte") != "CVM (ações) × cotação" or info.get("aviso"):
            import b3
            oficiais = b3.acoes(cd)  # desempate: nº de ações atual segundo a B3
            if oficiais:
                mcap, info = indicators.valor_mercado(*args, acoes_oficiais=oficiais)
        if not mcap:
            continue
        setor = cvm.setor_cvm(cd)
        try:
            m = indicators.calcular(emp, principal["preco"], mcap, setor, macro)
        except Exception as e:
            log(f"universo: {principal['symbol']} ignorada ({e})")
            continue
        m.pop("historico", None)
        m["volume_financeiro"] = principal.get("volume_financeiro")
        gov = cvm.governanca(cd, principal["symbol"])
        emps[cd] = emp
        recs.append({"cd_cvm": cd, "symbol": principal["symbol"], "outros": [x["symbol"] for x in tks[:-1]],
                     "nome": emp["nome"], "setor_cvm": setor, "setor_base": indicators.setor_base(setor),
                     "setor_nome": indicators.setor_nome(setor),
                     "subsetor": principal.get("subsetor"), "segmento": principal.get("segmento"),
                     "controle": gov.get("controle"), "situacao": gov.get("situacao_emissor"),
                     "volume_financeiro": principal.get("volume_financeiro"), "mcap_info": info,
                     "dados_ref": emp["ttm_info"]["ref"], "m": m, "_gov": gov})
    # medianas por setor/grupo e avaliação completa de cada companhia
    for r in recs:
        nivel, pares = _pares_de(recs, r["setor_base"], r["m"]["grupo"])
        med = medianas(pares)
        emp = emps[r["cd_cvm"]]
        val = valuation.avaliar(r["m"], emp, med, None, macro)
        sc = scoring.pontuar(r["m"], val, med)
        al = scoring.alertas(r["m"], val, r.pop("_gov"), emp["ttm_info"])
        r.update(pares={"nivel": nivel, "n": med["n"]}, valuation=_resumo_val(val), score=sc, alertas=al,
                 selo=scoring.selo(sc, al, r["m"], val))
    snap = {"versao": VERSAO, "gerado_em": datetime.now().isoformat(timespec="seconds"), "fonte_precos": fonte,
            "n": len(recs), "empresas": recs}
    os.makedirs(os.path.dirname(ARQ), exist_ok=True)
    with open(ARQ + ".tmp", "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, default=str)
    os.replace(ARQ + ".tmp", ARQ)
    log(f"universo: {len(recs)} companhias em {time.time() - t0:.1f}s (preços: {fonte})")
    return snap


def _resumo_val(val):
    g, b, t, p = val["graham"], val["bazin"], val["triangulacao"], val.get("piotroski") or {}
    z = val.get("altman_z2") or {}
    return {"graham_valor_justo": g["valor_justo"], "graham_margem": g["margem"], "graham_criterios": g["atendidos"],
            "graham_avaliados": g["avaliados"], "bazin_preco_teto": b["preco_teto"], "bazin_margem": b["margem"],
            "bazin_criterios": b["atendidos"], "bazin_avaliados": b["avaliados"],
            "preco_justo": t["preco_justo"], "upside": t["upside"], "n_metodos": t["n_metodos"],
            "piotroski": p.get("score"), "piotroski_avaliados": p.get("avaliados"),
            "altman_z2": z.get("z"), "altman_zona": z.get("zona"), "peg": (val.get("peg") or {}).get("peg")}


_SNAP = None


def carregar(macro=None, forcar=False) -> dict:
    """Snapshot do universo (cache de 6h; reconstrói se vencido)."""
    global _SNAP
    if _SNAP is not None and not forcar:
        return _SNAP
    if not forcar and os.path.exists(ARQ) and (time.time() - os.path.getmtime(ARQ)) < TTL:
        try:
            with open(ARQ, encoding="utf-8") as f:
                snap = json.load(f)
            if snap.get("versao") == VERSAO:
                _SNAP = snap
                return snap
        except (OSError, ValueError):
            pass
    _SNAP = construir(macro)
    return _SNAP


def comparar(cd, setor_cvm, grupo, m, snap=None) -> dict:
    """Medianas dos pares (excluindo a própria empresa) e percentil da empresa em cada métrica."""
    snap = snap or carregar()
    nivel, pares = _pares_de(snap["empresas"], indicators.setor_base(setor_cvm), grupo, excluir=int(cd))
    med = medianas(pares)
    pct = {}
    for campo, so_pos in CAMPOS:
        x = m.get(campo)
        vals = [r["m"].get(campo) for r in pares]
        vals = [v for v in vals if v is not None and (v > 0 or not so_pos)]
        if x is not None and len(vals) >= 3 and (x > 0 or not so_pos):
            pct[campo] = round(100 * sum(1 for v in vals if v < x) / len(vals))
    top = sorted(pares, key=lambda r: -(r["m"].get("market_cap") or 0))[:8]
    return {"nivel": nivel, "setor": indicators.setor_base(setor_cvm) if nivel == "setor" else
            (indicators.GRUPO_NOME.get(grupo) if nivel == "grupo" else "mercado"),
            "n": med["n"], "medianas": med, "percentis": pct,
            "principais_pares": [{"symbol": r["symbol"], "nome": r["nome"], "pl": r["m"].get("pl"),
                                  "pvp": r["m"].get("pvp"), "dy": r["m"].get("dy"), "roe": r["m"].get("roe"),
                                  "ev_ebit": r["m"].get("ev_ebit"), "score": r["score"]["total_deterministico"]}
                                 for r in top]}
