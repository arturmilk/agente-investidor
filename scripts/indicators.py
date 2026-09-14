"""Indicadores fundamentalistas a partir dos dados oficiais (CVM) + cotação.

Convenções
- Valores em R$; percentuais como fração (0,15 = 15%).
- Resultado = últimos 12 meses (TTM) quando há ITR; balanço = o mais recente.
- Lucro e PL = parcela dos controladores (o que pertence ao acionista).
  Margens e ROA usam o lucro consolidado (mesma base da receita/ativo).
- Valores por ação derivam do valor de mercado (LPA = lucro × preço ÷ valor
  de mercado), o que neutraliza erros de escala no nº de ações da CVM.
"""
from __future__ import annotations

import math
import re
import statistics

from config import IR_PADRAO
from cvm import norm


# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------
def div(a, b):
    return a / b if (a is not None and b not in (None, 0)) else None


def pos(x):
    return x is not None and x > 0


def lucro(p):
    """Lucro dos controladores (ou consolidado, se a linha não existir)."""
    if not p:
        return None
    v = p.get("lucro_controladora")
    return v if v is not None else p.get("lucro_liquido")


def pl_ctrl(p):
    if not p:
        return None
    v = p.get("pl_controladora")
    return v if v is not None else p.get("pl")


def ebitda(p):
    e, d = p.get("ebit"), p.get("depreciacao")
    return e + d if (e is not None and d is not None) else None


def divida_bruta(p):
    cp, lp = p.get("emprestimos_cp"), p.get("emprestimos_lp")
    return (cp or 0.0) + (lp or 0.0) if (cp is not None or lp is not None) else None


def caixa_total(p):
    c, a = p.get("caixa"), p.get("aplicacoes")
    return (c or 0.0) + (a or 0.0) if (c is not None or a is not None) else None


def circulacao(rec):
    if not rec or not rec.get("total"):
        return None
    return rec["total"] - (rec.get("tes_total") or 0.0)


def split_ratio(r):
    """'2:1' → 2.0 (desdobramento), '1:10' → 0.1 (grupamento), '11:10' → 1.1 (bonificação)."""
    try:
        a, b = str(r).split(":")
        a, b = float(a), float(b)
        return a / b if a > 0 and b > 0 else None
    except (ValueError, TypeError):
        return None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def _serie(anual, fn, n=6):
    anos = sorted(anual)[-n:]
    return [(a, fn(anual[a])) for a in anos]


def cagr(serie, anos=5):
    """Crescimento anual composto entre o primeiro e o último ponto (até `anos` anos)."""
    pts = [(int(a), v) for a, v in serie if v is not None][-(anos + 1):]
    if len(pts) < 3:
        return None
    (y0, v0), (y1, v1) = pts[0], pts[-1]
    if v0 <= 0 or v1 <= 0 or y1 <= y0:
        return None
    return (v1 / v0) ** (1 / (y1 - y0)) - 1


def tendencia(serie, anos=5):
    """Crescimento anual pela regressão log-linear (robusto a um ano atípico)."""
    pts = [(int(a), v) for a, v in serie if v is not None][-(anos + 1):]
    if len(pts) < 3 or any(v <= 0 for _, v in pts):
        return None
    xs = [a for a, _ in pts]
    ys = [math.log(v) for _, v in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
    return math.exp(slope) - 1


def direcao(serie, n=3):
    """'alta', 'queda' ou 'estavel' nos últimos n pontos (monotonicidade)."""
    vals = [v for _, v in serie if v is not None][-n:]
    if len(vals) < 3:
        return "estavel"
    if all(b > a for a, b in zip(vals, vals[1:])):
        return "alta"
    if all(b < a for a, b in zip(vals, vals[1:])):
        return "queda"
    return "estavel"


# ---------------------------------------------------------------------------
# Setor
# ---------------------------------------------------------------------------
_ABREV = {"maqs., equip., veic. e pecas": "maquinas, equipamentos, veiculos e pecas",
          "const. civil, mat. const. e decoracao": "construcao civil, mat. constr. e decoracao"}
_GRUPOS = (
    ("financeiro", ("bancos", "intermediacao financeira", "seguradoras", "arrendamento mercantil",
                    "credito imobiliario", "securitizacao")),
    ("utilities", ("energia eletrica", "saneamento")),
    ("commodities", ("petroleo e gas", "extracao mineral", "metalurgia e siderurgia", "papel e celulose",
                     "petroquimicos", "agricultura", "reflorestamento")),
    ("ciclicas", ("construcao civil", "comercio", "textil", "hospedagem", "brinquedos", "maquinas",
                  "transporte", "embalagens")),
    ("defensivas", ("alimentos", "bebidas", "farmaceutico", "servicos medicos", "educacao", "telecomunicacoes")),
)
GRUPO_NOME = {"financeiro": "Financeiro", "utilities": "Utilities (energia/saneamento)",
              "commodities": "Commodities (cíclicas globais)", "ciclicas": "Cíclicas domésticas",
              "defensivas": "Defensivas", "outros": "Outros"}


def setor_base(setor_cvm):
    s = re.sub(r"^emp\. adm\. part\. -\s*", "", norm(setor_cvm))
    return _ABREV.get(s, s)


def grupo_setorial(setor_cvm, layout=None):
    if layout == "financeiro":
        return "financeiro"
    s = setor_base(setor_cvm)
    for g, kws in _GRUPOS:
        if any(k in s for k in kws):
            return g
    return "outros"


_NOME_SETOR = {"Máqs., Equip., Veíc. e Peças": "Máquinas, Equipamentos, Veículos e Peças",
               "Const. Civil, Mat. Const. e Decoração": "Construção Civil, Mat. Constr. e Decoração"}


def setor_nome(setor_cvm):
    """Nome do setor para exibição (sem o prefixo de holding 'Emp. Adm. Part. -')."""
    s = re.sub(r"^Emp\. Adm\. Part\. -\s*", "", (setor_cvm or "").strip())
    return _NOME_SETOR.get(s, s) or "—"


# ---------------------------------------------------------------------------
# Valor de mercado (reconcilia referência de mercado × ações CVM × ações B3)
# ---------------------------------------------------------------------------
def valor_mercado(emp, preco, classe=None, mcap_ref=None, precos_classes=None, acoes_por_unit=None,
                  acoes_oficiais=None):
    """→ (valor de mercado, info).

    1. Σ(ações da CVM por classe × preço da classe), quando confere com a referência (brapi);
    2. se divergem, o nº de ações ATUAL da B3 (`acoes_oficiais`) desempata — cobre
       bonificações, desdobramentos e emissões posteriores ao último ITR;
    3. sem B3, usa a referência; sem referência, a conta CVM com escala plausível.
    Ações publicadas em milhares na CVM são corrigidas automaticamente."""
    rec = emp.get("acoes") or {}
    tes_on, tes_pn = rec.get("tes_on") or 0.0, rec.get("tes_pn") or 0.0
    on = max(0.0, (rec.get("on") or 0.0) - tes_on)
    pn = max(0.0, (rec.get("pn") or 0.0) - tes_pn)
    precos_classes = precos_classes or {}
    p_acao = preco / acoes_por_unit if (classe == "UNIT" and acoes_por_unit and preco) else preco
    p_on = precos_classes.get("ON") or p_acao
    p_pn = precos_classes.get("PN") or p_acao
    calc = {s: (on * p_on + pn * p_pn) * s for s in (1, 1000)} if (on + pn) > 0 and p_acao else {}
    b3 = None
    if acoes_oficiais and acoes_oficiais.get("total") and p_acao:
        tot_cvm = (rec.get("on") or 0.0) + (rec.get("pn") or 0.0)
        esc = 1
        if tot_cvm and abs(math.log(tot_cvm * 1000 / acoes_oficiais["total"])) < abs(math.log(tot_cvm / acoes_oficiais["total"])):
            esc = 1000
        b3 = (max(0.0, acoes_oficiais.get("on", 0) - tes_on * esc) * p_on
              + max(0.0, acoes_oficiais.get("pn", 0) - tes_pn * esc) * p_pn) or None
    info = {}
    if mcap_ref and calc:
        s = min(calc, key=lambda k: abs(math.log(calc[k] / mcap_ref)))
        r = calc[s] / mcap_ref
        if 0.87 <= r <= 1.15:
            return calc[s], {"fonte": "CVM (ações) × cotação", "escala_acoes": s, "referencia": mcap_ref}
        info = {"divergencia_cvm": round(r - 1, 3), "referencia": mcap_ref}
    if b3:
        return b3, {"fonte": "B3 (ações) × cotação", **info}
    if mcap_ref:
        return mcap_ref, {"fonte": "brapi", **info}
    if not calc:
        return None, {"fonte": None}
    pl = pl_ctrl(emp.get("ttm") or {})
    s = 1
    if pos(pl):
        plaus = [k for k in (1, 1000) if 0.05 <= calc[k] / pl <= 30]
        s = plaus[0] if plaus else min(calc, key=lambda k: abs(math.log(calc[k] / pl)))
    return calc[s], {"fonte": "CVM (ações) × cotação", "escala_acoes": s, "aviso": "sem valor de mercado de referência"}


# ---------------------------------------------------------------------------
# Diluição e múltiplos históricos
# ---------------------------------------------------------------------------
def diluicao(acoes_hist, desdobramentos=None, emissoes=None):
    """Variação anual do nº de ações (diluição real).

    - Ajusta por desdobramentos/bonificações conhecidos (eventos do Yahoo).
    - Aumento sem entrada de caixa por emissão de ações no DFC (bonificação,
      desdobramento, incorporação) não conta como diluição.
    - Sem essas informações, saltos > 35% são tratados como desdobramento.
    Retorna (taxa anual média, [(ano, variação) dos aumentos sem emissão em caixa]).
    """
    pts = sorted((int(a), v) for a, v in (acoes_hist or {}).items() if v and v > 0)
    if len(pts) < 3:
        return None, []
    fatores = [(d, split_ratio(r)) for d, r in (desdobramentos or []) if d and split_ratio(r)]
    if fatores:
        pts = [(y, v * math.prod(f for d, f in fatores if d > f"{y}-12-31")) for y, v in pts]
    taxas, sem_caixa = [], []
    for (y0, v0), (y1, v1) in zip(pts, pts[1:]):
        r = v1 / v0
        if r > 1.02 and emissoes is not None and emissoes.get(str(y1)) == 0.0:
            sem_caixa.append((str(y1), r - 1))
            r = 1.0
        if 0.74 <= r <= 1.35:
            taxas.append(r ** (1 / (y1 - y0)))
    if not taxas:
        return None, sem_caixa
    return math.prod(taxas) ** (1 / len(taxas)) - 1, sem_caixa


def multiplos_historicos(emp, preco, mcap, hist, financeiro=False):
    """P/L, P/VP, EV/EBIT e DY no fim de cada exercício, com o valor de mercado histórico
    estimado pelo preço ajustado (Yahoo) e pela variação do nº de ações (CVM)."""
    if not hist or not hist.get("mensal") or not preco or not mcap:
        return {}
    fechamentos = {d[:7]: c for d, c, _ in hist["mensal"] if d}
    fatores = [(d, split_ratio(r)) for d, r in hist.get("desdobramentos") or [] if d and split_ratio(r)]
    acoes_hist, acoes_hoje = emp.get("acoes_hist") or {}, circulacao(emp.get("acoes"))
    anos = {}
    for ano in sorted(emp["anual"])[-6:]:
        p = emp["anual"][ano]
        dt = p.get("dt_fim") or f"{ano}-12-31"
        c = fechamentos.get(dt[:7])
        if not c:
            continue
        mc = mcap * c / preco
        s_y = acoes_hist.get(ano)
        if s_y and acoes_hoje:
            adj = s_y * math.prod(f for d, f in fatores if d > dt) / acoes_hoje
            if 0.7 <= adj <= 1.4:
                mc *= adj
        ll, pl = lucro(p), pl_ctrl(p)
        rec = {"preco": round(c, 2), "market_cap": mc, "pl": div(mc, ll) if pos(ll) else None,
               "pvp": div(mc, pl) if pos(pl) else None, "dy": div(p.get("dividendos_pagos"), mc)}
        if not financeiro and pos(p.get("ebit")):
            dl = (divida_bruta(p) or 0.0) - (caixa_total(p) or 0.0)
            rec["ev_ebit"] = (mc + dl) / p["ebit"]
        anos[ano] = rec
    if not anos:
        return {}
    ult = [anos[a] for a in sorted(anos)[-5:]]
    med = {k: _median([r.get(k) for r in ult]) for k in ("pl", "pvp", "ev_ebit", "dy")}
    return {"anos": anos, "mediana_5a": med}


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------
def calcular(emp, preco, mcap, setor_cvm="", macro=None, hist=None):
    """Todos os indicadores de uma companhia → dict plano (JSON-friendly)."""
    t, anual = emp["ttm"], emp["anual"]
    grupo = grupo_setorial(setor_cvm, t.get("layout"))
    fin = grupo == "financeiro"
    fator = div(preco, mcap)
    ult5 = [anual[a] for a in sorted(anual)[-5:]]

    ll, ll_cons, pl, pl_total = lucro(t), t.get("lucro_liquido"), pl_ctrl(t), t.get("pl")
    receita, ebit_, dep = t.get("receita"), t.get("ebit"), t.get("depreciacao")
    ebitda_ = ebitda(t)
    ativo = t.get("ativo_total")
    fco, capex = t.get("fco"), t.get("capex")
    fcf = fco - (capex or 0.0) if fco is not None else None
    fco_atipico = bool(not fin and pos(ebitda_) and pos(fco) and fco > 1.5 * ebitda_)

    if fin:
        divb = caixa = dl = ev = None
    else:
        divb, caixa = divida_bruta(t) or 0.0, caixa_total(t) or 0.0
        dl = divb - caixa
        ev = mcap + dl if mcap else None

    m = {"grupo": grupo, "financeiro": fin, "preco": preco, "market_cap": mcap, "ev": ev,
         "lucro_ttm": ll, "receita_ttm": receita, "ebit_ttm": ebit_, "ebitda_ttm": ebitda_,
         "pl_contabil": pl, "fco_ttm": fco, "capex_ttm": capex, "fcf_ttm": fcf, "fco_atipico": fco_atipico}

    # ---- por ação (base: valor de mercado)
    m["lpa"] = ll * fator if (ll is not None and fator) else None
    m["vpa"] = pl * fator if (pl is not None and fator) else None

    # ---- valuation
    lucros5 = [lucro(p) for p in ult5]
    ll_med = _mean(lucros5) if len([x for x in lucros5 if x is not None]) >= 3 else None
    ebits5 = [p.get("ebit") for p in ult5]
    ebit_med = _mean(ebits5) if len([x for x in ebits5 if x is not None]) >= 3 else None
    m["lucro_medio_5a"] = ll_med
    m["pl"] = div(mcap, ll) if pos(ll) else None
    m["pl_normalizado"] = div(mcap, ll_med) if pos(ll_med) else None
    m["pvp"] = div(mcap, pl) if pos(pl) else None
    receita_valida = pos(receita) and (ll_cons is None or abs(ll_cons) <= receita)  # holdings: receita ~0
    m["psr"] = div(mcap, receita) if receita_valida else None
    m["p_ebit"] = div(mcap, ebit_) if (not fin and pos(ebit_)) else None
    m["ev_ebit"] = div(ev, ebit_) if (not fin and pos(ebit_)) else None
    m["ev_ebitda"] = div(ev, ebitda_) if (not fin and pos(ebitda_)) else None
    m["ev_ebit_normalizado"] = div(ev, ebit_med) if (not fin and pos(ebit_med)) else None
    m["p_fcf"] = div(mcap, fcf) if pos(fcf) else None
    m["earnings_yield"] = div(ebit_, ev) if (not fin and pos(ev) and ebit_ is not None) else None
    m["lucro_yield"] = div(ll, mcap)
    m["fcf_yield"] = div(fcf, mcap)

    divs_ttm = t.get("dividendos_pagos")
    if divs_ttm is not None:
        divs_ttm = max(0.0, divs_ttm)  # fluxo não negativo (arredondamento entre ITRs)
    divs5 = [p.get("dividendos_pagos") for p in ult5 if p.get("dividendos_pagos") is not None]
    ok5 = len(divs5) >= 3
    m["dividendos_ttm"] = divs_ttm
    m["dy"] = div(divs_ttm, mcap)
    m["dy_medio_5a"] = div(_mean(divs5), mcap) if ok5 else None
    m["dy_mediano_5a"] = div(_median(divs5), mcap) if ok5 else None  # robusto a dividendos extraordinários
    m["anos_com_dividendos_5a"] = sum(1 for d in divs5 if d > 0)
    m["dpa_ttm"] = divs_ttm * fator if (divs_ttm is not None and fator) else None
    m["dpa_medio_5a"] = _mean(divs5) * fator if (ok5 and fator) else None
    m["dpa_mediano_5a"] = _median(divs5) * fator if (ok5 and fator) else None
    m["payout"] = div(divs_ttm, ll) if pos(ll) else None
    if hist:
        from market import proventos_12m
        p12 = proventos_12m(hist)
        m["dy_12m_acao"] = div(p12, preco) if p12 is not None else None

    # ---- rentabilidade
    m["roe"] = div(ll, pl) if pos(pl) else None
    m["roa"] = div(ll_cons if ll_cons is not None else ll, ativo)
    lair, ir = t.get("lair"), t.get("ir")
    aliq = -ir / lair if (pos(lair) and ir is not None) else None
    if aliq is None or not 0 <= aliq <= 0.5:
        aliq = IR_PADRAO
    m["aliquota_efetiva"] = aliq
    if not fin and ebit_ is not None and pl_total is not None and dl is not None:
        capital = pl_total + dl
        m["roic"] = ebit_ * (1 - aliq) / capital if capital > 0 else None
    else:
        m["roic"] = None
    base_margem = ll_cons if ll_cons is not None else ll
    m["margem_bruta"] = div(t.get("lucro_bruto"), receita) if (receita_valida and not fin) else None
    m["margem_ebitda"] = div(ebitda_, receita) if (receita_valida and not fin) else None
    m["margem_ebit"] = div(ebit_, receita) if (receita_valida and not fin) else None
    m["margem_liquida"] = div(base_margem, receita) if receita_valida else None
    m["giro_ativo"] = div(receita, ativo) if receita_valida else None

    # ---- saúde financeira
    m["divida_bruta"], m["caixa"], m["divida_liquida"] = divb, caixa, dl
    m["dl_ebitda"] = div(dl, ebitda_) if (dl is not None and pos(ebitda_)) else None
    m["dl_pl"] = div(dl, pl_total) if (dl is not None and pos(pl_total)) else None
    m["liquidez_corrente"] = div(t.get("ativo_circulante"), t.get("passivo_circulante"))
    df = t.get("despesas_financeiras")
    m["cobertura_juros"] = div(ebit_, abs(df)) if (not fin and df) else None
    m["pl_ativo"] = div(pl_total, ativo)
    m["capex_fco"] = div(capex, fco) if pos(fco) else None

    # ---- crescimento e histórico
    s_rec = _serie(anual, lambda p: p.get("receita"))
    s_ll = _serie(anual, lucro)
    s_fco = _serie(anual, lambda p: p.get("fco"))
    s_pl = _serie(anual, pl_ctrl)
    s_marg = _serie(anual, lambda p: div(p.get("lucro_liquido"), p.get("receita")) if pos(p.get("receita")) else None)
    s_roe = _serie(anual, lambda p: div(lucro(p), pl_ctrl(p)) if pos(pl_ctrl(p)) else None)
    m["cagr_receita_5a"], m["tend_receita"] = cagr(s_rec), tendencia(s_rec)
    m["cagr_lucro_5a"], m["tend_lucro"] = cagr(s_ll), tendencia(s_ll)
    m["cagr_fco_5a"], m["tend_fco"] = cagr(s_fco), tendencia(s_fco)
    m["cagr_pl_5a"], m["tend_pl"] = cagr(s_pl), tendencia(s_pl)
    m["anos_lucro_positivo_5a"] = sum(1 for p in ult5 if pos(lucro(p)))
    m["direcao_margem"] = direcao(s_marg)
    m["direcao_roe"] = direcao(s_roe)
    roes5 = [v for _, v in s_roe[-5:] if v is not None]
    m["roe_medio_5a"] = _mean(roes5)
    m["roe_desvio_5a"] = statistics.pstdev(roes5) if len(roes5) >= 3 else None
    m["anos_roe_acima_12_5a"] = sum(1 for v in roes5 if v >= 0.12)
    ult_fy = anual[sorted(anual)[-1]] if anual else {}
    m["cresc_lucro_ttm_vs_ano"] = div(ll, lucro(ult_fy)) - 1 if (pos(lucro(ult_fy)) and ll is not None
                                                                   and emp["ttm_info"]["tipo"] == "ttm") else None
    tri = emp.get("trimestre") or {}
    ta, tb = tri.get("atual") or {}, tri.get("ano_anterior") or {}
    m["trimestre_ref"] = tri.get("ref")
    m["lucro_tri"], m["lucro_tri_ano_ant"] = lucro(ta), lucro(tb)
    m["cresc_lucro_tri"] = div(lucro(ta), lucro(tb)) - 1 if (pos(lucro(tb)) and lucro(ta) is not None) else None
    m["cresc_receita_tri"] = div(ta.get("receita"), tb.get("receita")) - 1 if pos(tb.get("receita")) and ta.get("receita") is not None else None
    m["diluicao_anual"], m["aumentos_sem_emissao"] = diluicao(
        emp.get("acoes_hist"), (hist or {}).get("desdobramentos"),
        {a: p.get("emissao_acoes") for a, p in anual.items()})
    m["emissao_acoes_ttm"] = t.get("emissao_acoes")
    s_div = _serie(anual, lambda p: divida_bruta(p))
    m["cagr_divida_5a"] = cagr(s_div)
    s_recb = _serie(anual, lambda p: p.get("recebiveis"))
    s_est = _serie(anual, lambda p: p.get("estoques"))
    m["cagr_recebiveis_5a"], m["cagr_estoques_5a"] = cagr(s_recb), cagr(s_est)
    fcos3 = [p.get("fco") for p in ult5[-3:] if p.get("fco") is not None]
    m["anos_fco_negativo_3a"] = sum(1 for v in fcos3 if v < 0)
    fcfs3 = [p["fco"] - (p.get("capex") or 0.0) for p in ult5[-3:] if p.get("fco") is not None]
    m["anos_fcf_negativo_3a"] = sum(1 for v in fcfs3 if v < 0)
    m["ir_positivo"] = bool(ir is not None and ir > 0 and pos(ll) and ir > 0.2 * ll)
    desc = t.get("descontinuadas")
    m["descontinuadas_relevantes"] = bool(desc and ll and abs(desc) > 0.2 * abs(ll))
    m["historico"] = {
        "anos": [a for a, _ in s_rec],
        "receita": [v for _, v in s_rec], "lucro": [v for _, v in s_ll],
        "margem_liquida": [v for _, v in s_marg], "roe": [v for _, v in s_roe],
        "fco": [v for _, v in s_fco],
        "fcf": [(p["fco"] - (p.get("capex") or 0.0)) if p.get("fco") is not None else None
                for p in (anual[a] for a in sorted(anual)[-6:])],
        "divida_liquida": [None if fin else ((divida_bruta(p) or 0.0) - (caixa_total(p) or 0.0))
                           for p in (anual[a] for a in sorted(anual)[-6:])],
        "dividendos": [p.get("dividendos_pagos") for p in (anual[a] for a in sorted(anual)[-6:])],
    }

    # ---- mercado
    if hist:
        from market import volume_medio
        mensal = hist.get("mensal") or []
        m["min_52s"], m["max_52s"] = hist.get("min_52s"), hist.get("max_52s")
        m["dist_max_52s"] = div(preco, hist.get("max_52s")) - 1 if hist.get("max_52s") else None
        m["var_12m"] = div(preco, mensal[-13][1]) - 1 if len(mensal) >= 13 else None
        m["volume_medio_3m"] = volume_medio(hist)
    if macro and macro.get("selic_meta") is not None:
        selic = macro["selic_meta"] / 100
        m["premio_lucro_selic"] = m["lucro_yield"] - selic if m["lucro_yield"] is not None else None
    return m
