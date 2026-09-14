"""Métodos de valor justo e de qualidade — determinísticos, com premissas explícitas.

- Graham: VI = √(22,5 × LPA × VPA) + critérios do investidor defensivo (adaptados).
- Bazin: preço-teto = dividendo médio por ação ÷ 6%.
- Múltiplos: mediana do setor e da própria história × fundamento da empresa.
- P/VP justo pelo ROE (Gordon): (ROE − g) ÷ (ke − g), com ke = Selic + prêmio.
- Triangulação: mediana dos métodos aplicáveis → preço justo e margem de segurança.
- Piotroski F-Score (0–9): melhora de rentabilidade, caixa, alavancagem e eficiência.
- Altman Z''-Score (versão para mercados emergentes/não industriais): risco de insolvência.
- PEG e PEGY (Lynch): P/L relativo ao crescimento (e dividendos).

Nenhum método é "o" valor justo; a triangulação existe para mostrar a faixa.
"""
from __future__ import annotations

import math
import statistics

from config import BAZIN_DY_MINIMO, CRESCIMENTO_PERPETUO, GRAHAM_MULTIPLO
from indicators import circulacao, div, lucro, pl_ctrl, pos


def _ult(anual, n=5):
    return [anual[a] for a in sorted(anual)[-n:]]


def graham(m, anual):
    lpa, vpa, preco = m.get("lpa"), m.get("vpa"), m.get("preco")
    vi = math.sqrt(GRAHAM_MULTIPLO * lpa * vpa) if (pos(lpa) and pos(vpa)) else None
    ult = _ult(anual)
    lucros = [lucro(p) for p in ult]
    divs = [p.get("dividendos_pagos") for p in ult]
    fin = m.get("financeiro")
    pl_, pvp = m.get("pl"), m.get("pvp")
    crit = {
        "lucro_positivo_5a": all(pos(x) for x in lucros) if len(lucros) >= 4 else None,
        "dividendos_todos_os_anos": all(pos(x) for x in divs) if len(divs) >= 4 else None,
        "lucro_crescente": (sum(lucros[-3:]) > sum(lucros[:3])) if (len(lucros) >= 5 and None not in lucros) else None,
        "pl_ate_15": pl_ is not None and pl_ <= 15,
        "pvp_ate_1_5": pvp is not None and pvp <= 1.5,
        "pl_x_pvp_ate_22_5": pl_ is not None and pvp is not None and pl_ * pvp <= GRAHAM_MULTIPLO,
        "liquidez_corrente_min_1_5": None if (fin or m.get("liquidez_corrente") is None) else m["liquidez_corrente"] >= 1.5,
        "divida_liquida_ate_pl": None if (fin or m.get("dl_pl") is None) else m["dl_pl"] <= 1.0,
        "porte_min_2bi": pos(m.get("market_cap")) and m["market_cap"] >= 2e9,
    }
    av = [v for v in crit.values() if v is not None]
    return {"valor_justo": vi, "margem": div(vi, preco) - 1 if vi and preco else None,
            "criterios": crit, "atendidos": sum(av), "avaliados": len(av)}


def bazin(m):
    """Preço-teto pelo dividendo MEDIANO de 5 anos (não a média: evita inflar com extraordinários)."""
    preco, dpa_ttm = m.get("preco"), m.get("dpa_ttm")
    dpa_ref = m.get("dpa_mediano_5a") if m.get("dpa_mediano_5a") is not None else m.get("dpa_medio_5a")
    dy_ref = m.get("dy_mediano_5a") if m.get("dy_mediano_5a") is not None else m.get("dy_medio_5a")
    teto = dpa_ref / BAZIN_DY_MINIMO if pos(dpa_ref) else None
    teto_ttm = dpa_ttm / BAZIN_DY_MINIMO if pos(dpa_ttm) else None
    crit = {
        "dy_mediano_5a_min_6": dy_ref is not None and dy_ref >= BAZIN_DY_MINIMO,
        "dividendos_todos_os_anos": m.get("anos_com_dividendos_5a", 0) >= 5,
        "divida_liquida_menor_que_pl": None if m.get("financeiro") or m.get("dl_pl") is None else m["dl_pl"] < 1.0,
        "lucro_positivo_5a": m.get("anos_lucro_positivo_5a", 0) >= 5,
    }
    av = [v for v in crit.values() if v is not None]
    return {"preco_teto": teto, "margem": div(teto, preco) - 1 if teto and preco else None,
            "preco_teto_ttm": teto_ttm, "criterios": crit, "atendidos": sum(av), "avaliados": len(av)}


def pvp_justo_roe(roe, ke, g=CRESCIMENTO_PERPETUO):
    """P/VP justificado (Gordon): quanto vale cada R$ de patrimônio dado o ROE sustentável."""
    if roe is None or ke is None or ke <= g or roe <= g:
        return None
    return (roe - g) / (ke - g)


def peg(m):
    g = m.get("tend_lucro") if m.get("tend_lucro") is not None else m.get("cagr_lucro_5a")
    pl_ = m.get("pl")
    out = {"crescimento_lucro": g, "peg": None, "pegy": None}
    if pl_ and g is not None:
        if g > 0:
            out["peg"] = pl_ / (g * 100)
        dy = m.get("dy_medio_5a") or m.get("dy") or 0.0
        if g + dy > 0:
            out["pegy"] = pl_ / ((g + dy) * 100)
    return out


def piotroski(anual, financeiro=False, desdobramentos=None):
    """F-Score com os dois últimos exercícios anuais. Em bancos, só os critérios aplicáveis."""
    anos = sorted(anual)
    if len(anos) < 2:
        return None
    a1, a0 = anual[anos[-1]], anual[anos[-2]]
    at1, at0 = a1.get("ativo_total"), a0.get("ativo_total")
    ll1, ll0 = a1.get("lucro_liquido"), a0.get("lucro_liquido")
    roa1, roa0 = div(ll1, at1), div(ll0, at0)
    fco1 = a1.get("fco")

    def razao(p, a, b):
        return div(p.get(a), p.get(b))

    def alav(p):
        lp = p.get("emprestimos_lp")
        return div(lp or 0.0, p.get("ativo_total")) if p.get("ativo_total") else None

    c = {"roa_positivo": None if roa1 is None else roa1 > 0,
         "fco_positivo": None if (financeiro or fco1 is None) else fco1 > 0,
         "roa_melhorou": None if None in (roa1, roa0) else roa1 > roa0,
         "fco_maior_que_lucro": None if (financeiro or None in (fco1, ll1)) else fco1 > ll1}
    if financeiro:
        c.update(alavancagem_caiu=None, liquidez_melhorou=None, margem_bruta_melhorou=None, giro_melhorou=None)
    else:
        l1, l0 = alav(a1), alav(a0)
        lc1, lc0 = razao(a1, "ativo_circulante", "passivo_circulante"), razao(a0, "ativo_circulante", "passivo_circulante")
        mb1, mb0 = razao(a1, "lucro_bruto", "receita"), razao(a0, "lucro_bruto", "receita")
        g1, g0 = razao(a1, "receita", "ativo_total"), razao(a0, "receita", "ativo_total")
        c["alavancagem_caiu"] = None if None in (l1, l0) else l1 <= l0
        c["liquidez_melhorou"] = None if None in (lc1, lc0) else lc1 > lc0
        c["margem_bruta_melhorou"] = None if None in (mb1, mb0) else mb1 > mb0
        c["giro_melhorou"] = None if None in (g1, g0) else g1 > g0
    # não emitiu ações: pelo DFC (entrada de caixa por emissão > 1% do PL); senão pelo nº de ações
    ac1, ac0 = a1.get("_acoes"), a0.get("_acoes")
    c["sem_emissao_de_acoes"] = None
    emis, pl1 = a1.get("emissao_acoes"), a1.get("pl")
    if emis is not None and pos(pl1):
        c["sem_emissao_de_acoes"] = emis <= 0.01 * pl1
    elif ac1 and ac0:
        r = ac1 / ac0
        if desdobramentos:
            from indicators import split_ratio
            dt0, dt1 = a0.get("dt_fim", ""), a1.get("dt_fim", "")
            for d, rr in desdobramentos:
                f = split_ratio(rr)
                if d and f and dt0 < d <= dt1:
                    r /= f
        c["sem_emissao_de_acoes"] = r <= 1.02 or r > 1.35  # salto grande = desdobramento/bonificação
    av = [v for v in c.values() if v is not None]
    return {"score": sum(av), "avaliados": len(av), "criterios": c, "anos": [anos[-2], anos[-1]]}


def altman_z2(t):
    """Altman Z'' (não industriais/emergentes): 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4."""
    at, pl = t.get("ativo_total"), t.get("pl")
    ac, pc, ebit = t.get("ativo_circulante"), t.get("passivo_circulante"), t.get("ebit")
    if not pos(at) or None in (ac, pc, ebit, pl) or t.get("layout") == "financeiro":
        return None
    retidos = (t.get("reservas_lucros") or 0.0) + (t.get("lucros_acumulados") or 0.0)
    passivo = at - pl
    x1, x2, x3 = (ac - pc) / at, retidos / at, ebit / at
    x4 = pl / passivo if passivo > 0 else 5.0
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zona = "segura" if z > 2.6 else ("cinzenta" if z >= 1.1 else "risco")
    return {"z": z, "zona": zona, "x": {"capital_giro_ativo": x1, "lucros_retidos_ativo": x2,
                                       "ebit_ativo": x3, "pl_passivo": x4}}


def triangulacao(m, grafo, baz, medianas_setor=None, hist_mult=None, ke=None):
    """Preço justo por vários métodos → mediana e margem de segurança."""
    preco, mcap = m.get("preco"), m.get("market_cap")
    fator = div(preco, mcap)
    fin, grupo = m.get("financeiro"), m.get("grupo")
    ll = m.get("lucro_ttm")
    ll_base = m.get("lucro_medio_5a") if (grupo == "commodities" and pos(m.get("lucro_medio_5a"))) else ll
    pl = m.get("pl_contabil")
    met = {}
    if grafo and grafo.get("valor_justo"):
        met["graham"] = grafo["valor_justo"]
    if baz and baz.get("preco_teto") and m.get("anos_com_dividendos_5a", 0) >= 4:
        met["bazin"] = baz["preco_teto"]
    med = medianas_setor or {}
    if fator:
        if pos(med.get("pl")) and pos(ll_base):
            met["pl_do_setor"] = med["pl"] * ll_base * fator
        if not fin and pos(med.get("ev_ebit")):
            ebit_base = m.get("ebit_ttm")
            if grupo == "commodities" and pos(m.get("ev_ebit_normalizado")) and pos(m.get("ev")):
                ebit_base = m["ev"] / m["ev_ebit_normalizado"]
            if pos(ebit_base) and m.get("divida_liquida") is not None:
                eq = med["ev_ebit"] * ebit_base - m["divida_liquida"]
                if eq > 0:
                    met["ev_ebit_do_setor"] = eq * fator
        if fin and pos(med.get("pvp")) and pos(pl):
            met["pvp_do_setor"] = med["pvp"] * pl * fator
        h = (hist_mult or {}).get("mediana_5a") or {}
        if pos(h.get("pl")) and pos(ll_base):
            met["pl_historico"] = h["pl"] * ll_base * fator
        if fin and pos(h.get("pvp")) and pos(pl):
            met["pvp_historico"] = h["pvp"] * pl * fator
        if fin:
            pj = pvp_justo_roe(m.get("roe_medio_5a") or m.get("roe"), ke)
            if pj and pos(pl):
                met["pvp_justo_roe"] = pj * pl * fator
    vals = [v for v in met.values() if v and v > 0]
    justo = statistics.median(vals) if len(vals) >= 2 else None
    return {"metodos": met, "preco_justo": justo, "n_metodos": len(vals),
            "faixa": [min(vals), max(vals)] if vals else None,
            "upside": div(justo, preco) - 1 if justo and preco else None}


def avaliar(m, emp, medianas_setor=None, hist_mult=None, macro=None, desdobramentos=None):
    """Roda todos os métodos para uma companhia."""
    anual = {a: dict(p) for a, p in emp["anual"].items()}
    for a, p in anual.items():  # nº de ações por exercício (para Piotroski)
        p["_acoes"] = (emp.get("acoes_hist") or {}).get(a)
    ke = (macro or {}).get("custo_capital_proprio")
    g = graham(m, anual)
    b = bazin(m)
    tri = triangulacao(m, g, b, medianas_setor, hist_mult, ke)
    return {"graham": g, "bazin": b, "peg": peg(m),
            "pvp_justo_roe": pvp_justo_roe(m.get("roe_medio_5a") or m.get("roe"), ke),
            "triangulacao": tri,
            "piotroski": piotroski(anual, m.get("financeiro"), desdobramentos),
            "altman_z2": None if m.get("financeiro") else altman_z2(emp["ttm"]),
            "premissas": {"graham_multiplo": GRAHAM_MULTIPLO, "bazin_dy_minimo": BAZIN_DY_MINIMO,
                          "ke": ke, "g": CRESCIMENTO_PERPETUO}}


def acoes_atuais(emp):
    return circulacao(emp.get("acoes"))
