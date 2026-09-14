"""Screener B3 — encontra ações baratas (e boas) no universo inteiro da bolsa.

Uso:
    python screener.py [--estrategia valor] [--top 15] [--setor energia]
                       [--min-liq 2000000] [--min-mcap 500000000]
                       [--incluir-armadilhas] [--atualizar] [--compacto] [--out arq.json]

Estratégias (--estrategia):
  valor       maior score determinístico, sem armadilhas de valor (padrão)
  graham      investidor defensivo de Graham: P/L ≤ 15, P/VP ≤ 1,5, lucro em 5 anos; por margem de Graham
  bazin       Décio Bazin: DY mediano ≥ 6%, dividendos todo ano, dívida < PL; por margem ao preço-teto
  magic       Fórmula Mágica (Greenblatt): ranking EV/EBIT + ROIC; exclui financeiras e utilities
  dividendos  renda: DY 12m e 5a ≥ 5%, pagamento consistente e payout sustentável
  qualidade   ROE/ROIC altos, margens, dívida baixa, F-Score ≥ 6, lucro limpo — ordenado por qualidade
  barganha    P/VP < 1 com lucro, ROE ≥ 8% e sem sinais graves de armadilha
  piotroski   F-Score ≥ 7, ordenado pelo menor P/VP (estratégia original de Piotroski)
  todas       roda todas e mostra o top de cada uma
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

import macro as macro_mod
import report
import universe
from config import MIN_MARKET_CAP, MIN_VOLUME_FINANCEIRO
from cvm import norm
from report import mult, num, pct, up

AVISO = ("Triagem quantitativa com dados públicos (CVM, B3). Não é recomendação de investimento: "
         "aprofunde cada nome com a análise completa antes de decidir.")


def _f(r, k):
    return r["m"].get(k)


def _sem_armadilha_grave(r):
    return not any(a["categoria"] == "armadilha" and a["severidade"] == "alta" for a in r["alertas"])


def _lucro_limpo(r):
    """Sem suspeita de lucro não recorrente/inflado (crédito fiscal, pico, descontinuadas)."""
    return not any(a["categoria"] == "lucro" and a["severidade"] in ("alta", "media") for a in r["alertas"])


def _lucro_ok(r):
    return (_f(r, "lucro_ttm") or 0) > 0 and (_f(r, "pl_contabil") or 0) > 0


def _dy5(r):
    return _f(r, "dy_mediano_5a") if _f(r, "dy_mediano_5a") is not None else (_f(r, "dy_medio_5a") or 0)


ESTRATEGIAS = {
    "valor": {
        "titulo": "Valor (score do agente)",
        "descricao": "Maior score determinístico (valuation + crescimento + rentabilidade + saúde), "
                     "excluindo possíveis armadilhas de valor.",
        "filtro": lambda r: _lucro_ok(r) and r["selo"]["codigo"] != "armadilha",
        "ordem": lambda r: -r["score"]["total_deterministico"],
        "extra": ("Margem", lambda r: up(r["valuation"]["upside"])),
    },
    "graham": {
        "titulo": "Graham (investidor defensivo)",
        "descricao": "P/L ≤ 15, P/VP ≤ 1,5 (ou P/L × P/VP ≤ 22,5), lucro positivo nos últimos 5 anos; "
                     "ordenado pela margem sobre o valor intrínseco √(22,5 × LPA × VPA).",
        "filtro": lambda r: _lucro_ok(r) and _f(r, "pl") and _f(r, "pvp") and _f(r, "pl") <= 15
                  and (_f(r, "pvp") <= 1.5 or _f(r, "pl") * _f(r, "pvp") <= 22.5)
                  and (_f(r, "anos_lucro_positivo_5a") or 0) >= 5,
        "ordem": lambda r: -(r["valuation"]["graham_margem"] or -9),
        "extra": ("Graham (critérios)", lambda r: f"{up(r['valuation']['graham_margem'])} "
                                                  f"({r['valuation']['graham_criterios']}/{r['valuation']['graham_avaliados']})"),
    },
    "bazin": {
        "titulo": "Bazin (dividendos com segurança)",
        "descricao": "DY mediano de 5 anos ≥ 6% sobre o preço atual, dividendos em todos os anos, lucro positivo "
                     "e dívida líquida < PL; ordenado pela margem ao preço-teto (dividendo mediano ÷ 6%).",
        "filtro": lambda r: _lucro_ok(r) and _dy5(r) >= 0.06 and (_f(r, "anos_com_dividendos_5a") or 0) >= 5
                  and (_f(r, "financeiro") or (_f(r, "dl_pl") is not None and _f(r, "dl_pl") < 1)),
        "ordem": lambda r: -(r["valuation"]["bazin_margem"] or -9),
        "extra": ("Preço-teto", lambda r: up(r["valuation"]["bazin_margem"])),
    },
    "magic": {
        "titulo": "Fórmula Mágica (Greenblatt)",
        "descricao": "Soma dos rankings de EV/EBIT (mais barato) e ROIC (mais rentável); exclui financeiras "
                     "e utilities, como no método original.",
        "filtro": lambda r: not _f(r, "financeiro") and _f(r, "grupo") != "utilities"
                  and (_f(r, "ev_ebit") or 0) > 0 and (_f(r, "roic") or 0) > 0 and _lucro_ok(r),
        "ordem": None,  # ranking combinado calculado à parte
        "extra": ("EV/EBIT · ROIC", lambda r: f"{mult(_f(r, 'ev_ebit'))} · {pct(_f(r, 'roic'), 0)}"),
    },
    "dividendos": {
        "titulo": "Dividendos consistentes",
        "descricao": "DY 12m e DY mediano 5a ≥ 5%, dividendos em ≥ 4 dos últimos 5 anos, payout ≤ 100% "
                     "(exceto utilities) e sem sinais graves de armadilha.",
        "filtro": lambda r: _lucro_ok(r) and (_f(r, "dy") or 0) >= 0.05 and _dy5(r) >= 0.05
                  and (_f(r, "anos_com_dividendos_5a") or 0) >= 4
                  and (_f(r, "grupo") == "utilities" or (_f(r, "payout") or 0) <= 1.0) and _sem_armadilha_grave(r),
        "ordem": lambda r: -(((_f(r, "dy") or 0) + _dy5(r)) / 2),
        "extra": ("DY 5a · payout", lambda r: f"{pct(_dy5(r))} · {pct(_f(r, 'payout'), 0)}"),
    },
    "qualidade": {
        "titulo": "Qualidade (a preço razoável)",
        "descricao": "ROE ≥ 15%, ROIC ≥ 12% (ou banco com ROE consistente), margem líquida ≥ 10%, dívida "
                     "controlada, F-Score ≥ 6, lucro crescendo e sem suspeita de lucro não recorrente; ordenado "
                     "por rentabilidade + saúde + crescimento.",
        "filtro": lambda r: _lucro_ok(r) and _lucro_limpo(r) and (_f(r, "roe") or 0) >= 0.15 and (
            (_f(r, "financeiro") and (_f(r, "anos_roe_acima_12_5a") or 0) >= 4) or (
                not _f(r, "financeiro") and (_f(r, "roic") or 0) >= 0.12 and (_f(r, "margem_liquida") or 0) >= 0.10
                and (_f(r, "dl_ebitda") is None or _f(r, "dl_ebitda") <= (3.5 if _f(r, "grupo") == "utilities" else 2.0))
                and (r["valuation"]["piotroski"] or 0) >= 6)) and (_f(r, "tend_lucro") or 0) > 0,
        "ordem": lambda r: -(r["score"]["pilares"]["rentabilidade"] + r["score"]["pilares"]["saude"]
                             + r["score"]["pilares"]["crescimento"]),
        "extra": ("Valuation", lambda r: f"{num(r['score']['pilares']['valuation'])}/25"),
    },
    "barganha": {
        "titulo": "Barganhas (P/VP < 1)",
        "descricao": "Negociadas abaixo do patrimônio (P/VP < 1), com lucro, ROE ≥ 8% e F-Score ≥ 5 "
                     "(ou lucro em ≥ 4 de 5 anos nas financeiras) — o desconto não é explicado pelos fundamentos.",
        "filtro": lambda r: _lucro_ok(r) and (_f(r, "pvp") or 9) < 1 and (_f(r, "roe") or 0) >= 0.08
                  and ((_f(r, "financeiro") and (_f(r, "anos_lucro_positivo_5a") or 0) >= 4)
                       or (r["valuation"]["piotroski"] or 0) >= 5) and _sem_armadilha_grave(r),
        "ordem": lambda r: _f(r, "pvp"),
        "extra": ("ROE · F-Score", lambda r: f"{pct(_f(r, 'roe'), 0)} · {r['valuation']['piotroski'] or '—'}"),
    },
    "piotroski": {
        "titulo": "Piotroski (F-Score alto e P/VP baixo)",
        "descricao": "F-Score ≥ 7 (fundamentos melhorando), ordenado pelo menor P/VP, como no estudo "
                     "original; exclui financeiras.",
        "filtro": lambda r: not _f(r, "financeiro") and (r["valuation"]["piotroski"] or 0) >= 7
                  and (r["valuation"]["piotroski_avaliados"] or 0) >= 8 and _lucro_ok(r),
        "ordem": lambda r: _f(r, "pvp") or 99,
        "extra": ("F-Score", lambda r: f"{r['valuation']['piotroski']}/{r['valuation']['piotroski_avaliados']}"),
    },
}


def rodar(snap, estrategia, top=15, setor=None, min_liq=MIN_VOLUME_FINANCEIRO, min_mcap=MIN_MARKET_CAP,
          incluir_armadilhas=False) -> dict:
    cfg = ESTRATEGIAS[estrategia]
    base = []
    for r in snap["empresas"]:
        if (r.get("volume_financeiro") or 0) < min_liq or (_f(r, "market_cap") or 0) < min_mcap:
            continue
        if any(k in norm(r.get("situacao") or "") for k in ("recuperacao", "falencia", "liquidacao")):
            continue
        if setor and norm(setor) not in norm(f"{r['setor_base']} {r['setor_cvm']} {r['m']['grupo']} {r.get('subsetor') or ''}"):
            continue
        if not incluir_armadilhas and r["selo"]["codigo"] == "armadilha":
            continue
        if cfg["filtro"](r):
            base.append(r)
    if estrategia == "magic":
        rk = {r["cd_cvm"]: i for i, r in enumerate(sorted(base, key=lambda r: _f(r, "ev_ebit")))}
        for i, r in enumerate(sorted(base, key=lambda r: -_f(r, "roic"))):
            rk[r["cd_cvm"]] += i
        base.sort(key=lambda r: rk[r["cd_cvm"]])
    else:
        base.sort(key=cfg["ordem"])
    itens = [{**r, "_extra": cfg["extra"][1](r)} for r in base[:top]]
    filtros = f"liquidez ≥ R$ {num(min_liq / 1e6, 1)} mi/dia, valor de mercado ≥ R$ {num(min_mcap / 1e6, 0)} mi"
    if setor:
        filtros += f", setor contém '{setor}'"
    if not incluir_armadilhas:
        filtros += ", sem possíveis armadilhas de valor"
    return {"estrategia": estrategia, "titulo": cfg["titulo"], "descricao": cfg["descricao"], "filtros": filtros,
            "universo_n": snap["n"], "aprovadas": len(base), "coluna_extra": cfg["extra"][0], "itens": itens,
            "gerado_em": snap.get("gerado_em"), "aviso": AVISO}


def main():
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description="Screener B3 — ações baratas e de qualidade")
    ap.add_argument("--estrategia", default="valor", choices=list(ESTRATEGIAS) + ["todas"])
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--setor", help="filtra por setor/grupo (ex.: energia, bancos, commodities, comercio)")
    ap.add_argument("--min-liq", type=float, default=MIN_VOLUME_FINANCEIRO, help="volume financeiro mínimo (R$/dia)")
    ap.add_argument("--min-mcap", type=float, default=MIN_MARKET_CAP, help="valor de mercado mínimo (R$)")
    ap.add_argument("--incluir-armadilhas", action="store_true", help="não remove possíveis armadilhas de valor")
    ap.add_argument("--atualizar", action="store_true", help="força recalcular o universo (ignora cache de 6h)")
    ap.add_argument("--compacto", action="store_true", help="saída curta para chat")
    ap.add_argument("--out", help="grava o resultado em JSON")
    args = ap.parse_args()

    snap = universe.carregar(macro_mod.snapshot(), forcar=args.atualizar)
    nomes = list(ESTRATEGIAS) if args.estrategia == "todas" else [args.estrategia]
    top = min(args.top, 8) if args.estrategia == "todas" else args.top
    resultados = [rodar(snap, e, top, args.setor, args.min_liq, args.min_mcap, args.incluir_armadilhas) for e in nomes]
    if args.out:
        slim = [{**res, "itens": [{"symbol": r["symbol"], "outros": r["outros"], "nome": r["nome"],
                                   "setor": r.get("setor_nome") or r["setor_base"], "selo": r["selo"],
                                   "score": r["score"], "valuation": r["valuation"], "indicadores": r["m"],
                                   "alertas": r["alertas"], "destaque": r["_extra"]}
                                  for r in res["itens"]]} for res in resultados]
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump({"gerado_em": datetime.now().isoformat(timespec="seconds"), "resultados": slim},
                      f, ensure_ascii=False, indent=2, default=str)
        print(f"[gravado] {args.out}", file=sys.stderr)
    print("\n\n".join(report.screener_md(res, args.compacto) for res in resultados))


if __name__ == "__main__":
    main()
