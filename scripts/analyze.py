"""Agente Bolsa — análise fundamentalista profunda de ações da B3.

Uso:
    python analyze.py PETR4 VALE3 WEGE3 [--out resultado.json] [--compacto]
                      [--sem-noticias] [--meses 3] [--sem-setor] [--json]

Para cada ticker: demonstrações oficiais da CVM (12 meses), cotação, múltiplos
atuais e históricos, comparação com o setor, Graham/Bazin/triangulação de
preço justo, Piotroski/Altman, score determinístico 0–70 (+30 qualitativos
pela camada de raciocínio), red flags, selo de barateza e notícias/fatos
relevantes dos últimos meses.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime

import b3
import cvm
import indicators
import macro as macro_mod
import market
import news
import report
import scoring
import universe
import valuation
from config import DEFAULT_TICKERS
from net import log
from seguranca import AVISO as AVISO_EXTERNO, limpar, ticker_valido

AVISO = ("Análise de apoio à decisão baseada em dados públicos (CVM, B3, Banco Central). "
         "Não é recomendação personalizada de investimento.")


def _nome_curto(nome):
    n = re.sub(r"\b(S\.?A\.?|S/A|CIA\.?|COMPANHIA|HOLDING|PARTICIPACOES|PARTICIPAÇÕES)\b", " ", nome or "",
               flags=re.I)
    return re.sub(r"\s+", " ", n).strip(" -.,") or nome


def _precos_da_lista():
    try:
        return {x["symbol"]: x for x in market.universo_b3()}
    except Exception as e:
        log(f"lista de preços da B3 indisponível: {e}")
        return {}


def analisar(ticker, mac, snap=None, lista=None, noticias=True, meses=3) -> dict:
    t = (ticker or "").strip().upper()
    if not ticker_valido(t):
        raise RuntimeError("ticker inválido (formato esperado: PETR4, TAEE11)")
    if t.endswith("F") and len(t) >= 6:
        t = t[:-1]  # mercado fracionário → ticker padrão
    q = market.cotacao(t)
    if not q or not q.get("preco"):
        raise RuntimeError("cotação indisponível (ticker existe?)")
    cd, motivo = cvm.resolve(t, q.get("nome"))
    if not cd:
        raise RuntimeError("companhia não encontrada nos dados da CVM")
    emp = cvm.empresa(cd)
    if not emp:
        raise RuntimeError("sem demonstrações financeiras na CVM")
    lista = lista or {}
    info_t = cvm.fca()["tickers"].get(t) or {}
    classe = info_t.get("classe")

    # preço das outras classes (valor de mercado exato) e referência de valor de mercado
    precos_cl, vols = {}, {}
    for tk, cl in cvm.tickers_da_empresa(cd).items():
        x = lista.get(tk) or {}
        if cl in ("ON", "PN") and x.get("preco") and (x.get("volume_financeiro") or 0) >= vols.get(cl, -1):
            precos_cl[cl], vols[cl] = x["preco"], x.get("volume_financeiro") or 0
    if classe in ("ON", "PN"):
        precos_cl[classe] = q["preco"]
    mcap_ref = q.get("market_cap") or (lista.get(t) or {}).get("market_cap")
    args = (emp, q["preco"], classe, mcap_ref, precos_cl, info_t.get("acoes_por_unit"))
    mcap, mcap_info = indicators.valor_mercado(*args)
    if mcap_info.get("fonte") != "CVM (ações) × cotação" or mcap_info.get("aviso"):
        oficiais = b3.acoes(cd)  # desempate: nº de ações atual segundo a B3
        if oficiais:
            mcap, mcap_info = indicators.valor_mercado(*args, acoes_oficiais=oficiais)
    if not mcap:
        raise RuntimeError("não foi possível estimar o valor de mercado")

    hist = market.historico(t)
    setor = cvm.setor_cvm(cd)
    m = indicators.calcular(emp, q["preco"], mcap, setor, mac, hist)
    m["volume_financeiro"] = (q.get("volume") or 0) * q["preco"] or None
    hm = indicators.multiplos_historicos(emp, q["preco"], mcap, hist, m["financeiro"])
    comp = None
    if snap:
        try:
            comp = universe.comparar(cd, setor, m["grupo"], m, snap)
        except Exception as e:
            log(f"{t}: comparação setorial falhou ({e})")
    med = (comp or {}).get("medianas")
    val = valuation.avaliar(m, emp, med, hm, mac, (hist or {}).get("desdobramentos"))
    sc = scoring.pontuar(m, val, med)
    gov = cvm.governanca(cd, t)
    al = scoring.alertas(m, val, gov, emp["ttm_info"])
    perfil = market.perfil(t)
    historico = m.pop("historico")
    ent = {
        "ticker": t, "empresa": emp["nome"], "nome_comercial": cvm.nome_comercial(cd), "cd_cvm": cd,
        "cnpj": emp["cnpj"],
        "setor": {"cvm": setor, "nome": indicators.setor_nome(setor), "base": indicators.setor_base(setor),
                  "grupo": m["grupo"], "grupo_nome": indicators.GRUPO_NOME.get(m["grupo"]),
                  "subsetor_b3": limpar((lista.get(t) or {}).get("subsetor"), 80) or None,
                  "industria": limpar(perfil.get("industry"), 80) or None},
        # texto de terceiros (brapi): limpo e marcado como conteúdo externo nos relatórios
        "negocio": limpar(perfil.get("longBusinessSummary"), 1500),
        "governanca": gov,
        "cotacao": {**q, "market_cap_usado": mcap, "market_cap_info": mcap_info},
        "dados": {**emp["ttm_info"], "resolucao_cvm": motivo, "trimestre": (emp.get("trimestre") or {}).get("ref")},
        "indicadores": m,
        "historico": historico,
        "multiplos_historicos": hm,
        "setor_comparacao": comp,
        "valuation": val,
        "score": sc,
        "selo": scoring.selo(sc, al, m, val),
        "red_flags": al,
        "consenso": market.consenso(t),
    }
    if noticias:
        nome_n = _nome_curto(cvm.nome_comercial(cd) or emp["nome"])
        setor_b = indicators.setor_base(setor)
        ent["noticias"] = {
            "cvm_eventos": cvm.eventos(cd, meses),
            **news.buscar(t, nome_n, dias=meses * 30),
            "industria": news.industria(setor_b, m["grupo"], dias=meses * 30),
        }
    return ent


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Agente Bolsa — análise fundamentalista de ações da B3")
    ap.add_argument("tickers", nargs="*", help="Tickers (ex.: PETR4 VALE3). Vazio = universo padrão.")
    ap.add_argument("--out", help="grava o JSON completo neste arquivo")
    ap.add_argument("--json", action="store_true", help="imprime o JSON completo em vez do relatório")
    ap.add_argument("--compacto", action="store_true", help="relatório curto para chat (Telegram/WhatsApp)")
    ap.add_argument("--sem-noticias", action="store_true", help="não busca notícias/fatos relevantes")
    ap.add_argument("--sem-setor", action="store_true", help="não compara com os pares do setor")
    ap.add_argument("--meses", type=int, default=3, help="janela de notícias/eventos (meses)")
    args = ap.parse_args()

    tickers = [t.upper() for t in (args.tickers or DEFAULT_TICKERS)]
    mac = macro_mod.snapshot()
    lista = _precos_da_lista()
    snap = None
    if not args.sem_setor:
        try:
            snap = universe.carregar(mac)
        except Exception as e:
            log(f"comparação setorial indisponível: {e}")
    ativos, erros = [], []
    for t in tickers:
        try:
            ativos.append(analisar(t, mac, snap, lista, not args.sem_noticias, args.meses))
            log(f"[ok] {t}")
        except Exception as e:
            erros.append(f"{limpar(t, 20)}: {e}")
            log(f"[erro] {limpar(t, 20)}: {e}")
    payload = {"gerado_em": datetime.now().isoformat(timespec="seconds"), "macro": mac, "ativos": ativos,
               "erros": erros, "aviso": AVISO,
               "conteudo_externo": {"campos": ["ativos[].negocio", "ativos[].noticias"], "aviso": AVISO_EXTERNO}}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        log(f"[gravado] {args.out}")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    else:
        print(report.analise_md(payload, compacto=args.compacto))
    if not ativos:
        sys.exit(1)


if __name__ == "__main__":
    main()
