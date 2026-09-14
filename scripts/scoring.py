"""Score, red flags e selo de "barateza" do Agente Bolsa.

Score 0–100:
  Determinístico (70 pts, aqui): Valuation 25 · Crescimento 15 · Rentabilidade 15 · Saúde 15
  Qualitativo (30 pts, camada de raciocínio — SKILL.md): Qualidade 20 · Risco 10

Cada subcritério vale 1–5 (2,5 = neutro por falta de dado). Faixas absolutas
combinadas com a posição relativa à mediana do setor; regras próprias para
financeiras (P/VP×ROE, PL/ativo), utilities (tolerância maior à dívida) e
commodities (P/L e EV/EBIT sobre lucro médio de 5 anos — evita o "barato no
topo do ciclo").

Selo: cruza o valuation com os sinais de armadilha de valor (lucro caindo,
dívida alta, Z-Score, F-Score, recuperação judicial...). Barato só é
oportunidade quando os fundamentos não explicam o desconto.
"""
from __future__ import annotations

from cvm import norm
from indicators import pos

NEUTRO = 2.5
MAXIMOS = {"valuation": 25, "crescimento": 15, "rentabilidade": 15, "saude": 15}
PILARES = {"valuation": ("v_pl", "v_ev", "v_pvp", "v_rend", "v_intr"),
           "crescimento": ("c_receita", "c_lucro", "c_caixa"),
           "rentabilidade": ("r_roe", "r_roic", "r_margem"),
           "saude": ("s_divida", "s_liquidez", "s_qualidade")}
DESCRICAO = {
    "v_pl": "P/L (normalizado em commodities) vs faixas e setor",
    "v_ev": "EV/EBIT vs faixas e setor (financeiras: P/VP ajustado ao ROE)",
    "v_pvp": "P/VP vs faixas e setor (trava se ROE < 8%)",
    "v_rend": "Rendimento: dividend yield ou FCF yield",
    "v_intr": "Margem de segurança da triangulação de preço justo",
    "c_receita": "Crescimento da receita (5 anos)",
    "c_lucro": "Crescimento do lucro (5 anos) + momento do trimestre",
    "c_caixa": "Crescimento do caixa operacional (financeiras: do patrimônio)",
    "r_roe": "ROE (penaliza ROE turbinado por dívida)",
    "r_roic": "ROIC (financeiras: ROA)",
    "r_margem": "Margem líquida vs setor e tendência (financeiras: anos com ROE ≥ 12%)",
    "s_divida": "Dívida líquida/EBITDA (financeiras: PL/ativo)",
    "s_liquidez": "Liquidez corrente e cobertura de juros (financeiras: anos com lucro)",
    "s_qualidade": "Piotroski F-Score (financeiras: estabilidade do ROE)",
}


def _menor(x, lim):
    """Menor é melhor: x < lim[0] → 5 … x ≥ lim[3] → 1."""
    if x is None:
        return None
    for i, l in enumerate(lim):
        if x < l:
            return 5.0 - i
    return 1.0


def _maior(x, lim):
    """Maior é melhor: x ≥ lim[0] → 5 … x < lim[3] → 1."""
    if x is None:
        return None
    for i, l in enumerate(lim):
        if x >= l:
            return 5.0 - i
    return 1.0


def _rel_menor(x, med):
    if x is None or not med or med <= 0 or x <= 0:
        return None
    return _menor(x / med, (0.6, 0.85, 1.15, 1.5))


def _rel_maior(x, med):
    if x is None or not med or med <= 0:
        return None
    return _maior(x / med, (1.5, 1.15, 0.85, 0.6))


def _clip(x):
    return max(1.0, min(5.0, x))


def _media(*xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def pontuar(m, val, med=None) -> dict:
    med = med or {}
    grupo, fin = m["grupo"], m["financeiro"]
    util, comm = grupo == "utilities", grupo == "commodities"
    n, sem = {}, []

    def put(k, x):
        if x is None:
            n[k] = NEUTRO
            sem.append(k)
        else:
            n[k] = round(_clip(x), 2)

    # ---- Valuation (25)
    ll = m.get("lucro_ttm")
    # lucro 12m muito acima da média de 5 anos (pico/não recorrente): usa o múltiplo normalizado
    pico = pos(m.get("lucro_medio_5a")) and pos(ll) and ll > 1.5 * m["lucro_medio_5a"]
    if ll is not None and ll <= 0:
        put("v_pl", 1.0)
    else:
        base = m["pl_normalizado"] if ((comm or pico) and m.get("pl_normalizado")) else m.get("pl")
        put("v_pl", _media(_menor(base, (6, 9, 12, 16)), _rel_menor(m.get("pl"), med.get("pl"))))
    if fin:
        pvp, roe = m.get("pvp"), m.get("roe")
        if pvp and pos(roe) and pos(med.get("pvp")) and pos(med.get("roe")):
            put("v_ev", _menor((pvp / med["pvp"]) / (roe / med["roe"]), (0.6, 0.85, 1.15, 1.5)))
        elif pvp and val.get("pvp_justo_roe"):
            put("v_ev", _menor(pvp / val["pvp_justo_roe"], (0.6, 0.85, 1.15, 1.5)))
        else:
            put("v_ev", None)
    else:
        evn, evt = m.get("ev_ebit_normalizado"), m.get("ev_ebit")
        pico_ebit = evn is not None and evt is not None and evn > 1.5 * evt
        base = evn if ((comm or pico_ebit) and evn) else evt
        if base is None and m.get("ebit_ttm") is not None and m["ebit_ttm"] <= 0:
            put("v_ev", 1.0)
        else:
            put("v_ev", _media(_menor(base, (5, 8, 11, 15)), _rel_menor(m.get("ev_ebit"), med.get("ev_ebit"))))
    pvp = m.get("pvp")
    if m.get("pl_contabil") is not None and m["pl_contabil"] <= 0:
        put("v_pvp", 1.0)
    else:
        x = _media(_menor(pvp, (1.0, 1.5, 2.5, 4.0)), _rel_menor(pvp, med.get("pvp")))
        if x is not None and pvp is not None and pvp < 1 and (m.get("roe") or 0) < 0.08:
            x = min(x, 3.0)  # patrimônio que não rende: barato por um motivo
        put("v_pvp", x)
    s_dy = _maior(_media(m.get("dy"), m.get("dy_mediano_5a")), (0.10, 0.07, 0.05, 0.03))
    s_fcf = None if (fin or m.get("fco_atipico")) else _maior(m.get("fcf_yield"), (0.12, 0.08, 0.05, 0.02))
    cands = [x for x in (s_dy, s_fcf) if x is not None]
    put("v_rend", max(cands) if cands else None)
    put("v_intr", _maior((val.get("triangulacao") or {}).get("upside"), (0.5, 0.25, 0.05, -0.15)))

    # ---- Crescimento (15)
    def g(a, b):
        return m.get(a) if m.get(a) is not None else m.get(b)
    put("c_receita", _maior(g("tend_receita", "cagr_receita_5a"), (0.15, 0.10, 0.05, 0.0)))
    gl = g("tend_lucro", "cagr_lucro_5a")
    cl = _maior(gl, (0.15, 0.10, 0.05, 0.0)) if gl is not None else (2.0 if pos(ll) else 1.0)
    ct = m.get("cresc_lucro_tri")
    if ct is not None:
        cl = cl - 1 if ct <= -0.30 else (cl + 0.5 if ct >= 0.30 else cl)
    put("c_lucro", cl)
    if fin:
        put("c_caixa", _maior(g("tend_pl", "cagr_pl_5a"), (0.15, 0.10, 0.06, 0.02)))
    elif m.get("fco_atipico"):
        put("c_caixa", None)
    else:
        put("c_caixa", _maior(g("tend_fco", "cagr_fco_5a"), (0.15, 0.10, 0.05, 0.0)))

    # ---- Rentabilidade (15)
    roe = m.get("roe")
    r = _maior(roe, (0.20, 0.15, 0.10, 0.05))
    if r is not None and not fin and not util and roe > 0.20 and (m.get("dl_ebitda") or 0) > 3.5:
        r -= 1  # ROE turbinado por dívida
    put("r_roe", r)
    if fin:
        put("r_roic", _maior(m.get("roa"), (0.02, 0.015, 0.01, 0.005)))
        k = m.get("anos_roe_acima_12_5a")
        put("r_margem", float(max(1, min(5, k))) if k is not None else None)
    else:
        put("r_roic", _maior(m.get("roic"), (0.15, 0.12, 0.08, 0.04)))
        ml = m.get("margem_liquida")
        x = _media(_maior(ml, (0.20, 0.12, 0.07, 0.03)), _rel_maior(ml, med.get("margem_liquida")))
        if x is not None:
            x += {"alta": 0.5, "queda": -0.5}.get(m.get("direcao_margem"), 0.0)
        put("r_margem", x)

    # ---- Saúde financeira (15)
    if fin:
        put("s_divida", _maior(m.get("pl_ativo"), (0.12, 0.09, 0.07, 0.05)))
        k = m.get("anos_lucro_positivo_5a")
        put("s_liquidez", {5: 5.0, 4: 3.0}.get(k, 1.0) if k is not None else None)
        put("s_qualidade", _menor(m.get("roe_desvio_5a"), (0.02, 0.04, 0.06, 0.09)))
    else:
        dl, dle = m.get("divida_liquida"), m.get("dl_ebitda")
        if dl is not None and dl <= 0:
            put("s_divida", 5.0)
        elif m.get("ebitda_ttm") is not None and m["ebitda_ttm"] <= 0:
            put("s_divida", 1.0)
        else:
            put("s_divida", _menor(dle, (2.5, 3.5, 4.5, 5.5) if util else (1, 2, 3, 4)))
        # com caixa líquido, a cobertura de juros não é risco (despesa financeira inclui variação cambial)
        cobertura = 5.0 if (dl is not None and dl <= 0) else _maior(m.get("cobertura_juros"), (8, 5, 3, 1.5))
        put("s_liquidez", _media(_maior(m.get("liquidez_corrente"), (1.5, 1.2, 0.9, 0.6)), cobertura))
        f = val.get("piotroski") or {}
        s = f.get("score")
        put("s_qualidade", None if f.get("avaliados", 0) < 7 else
            5.0 if s >= 8 else 4.0 if s == 7 else 3.0 if s >= 5 else 2.0 if s >= 3 else 1.0)

    pil = {p: round(sum(n[k] for k in ks), 1) for p, ks in PILARES.items()}
    total = round(sum(pil.values()), 1)
    return {"subcriterios": n, "pilares": pil, "maximos": MAXIMOS, "total_deterministico": total,
            "max_deterministico": 70, "score_quant_100": round(total / 70 * 100, 1),
            "pendente_llm": {"qualidade": 20, "risco": 10}, "sem_dado": sem}


# ---------------------------------------------------------------------------
# Red flags
# ---------------------------------------------------------------------------
def alertas(m, val, gov=None, ttm_info=None) -> list:
    out = []

    def add(txt, sev, cat):
        out.append({"flag": txt, "severidade": sev, "categoria": cat})

    fin, grupo = m["financeiro"], m["grupo"]
    util = grupo == "utilities"
    ll, lm, tl = m.get("lucro_ttm"), m.get("lucro_medio_5a"), m.get("tend_lucro")

    # --- Armadilha de valor: lucro caindo, dívida alta, perda de competitividade, insolvência
    sit = (gov or {}).get("situacao_emissor") or ""
    if any(k in norm(sit) for k in ("recuperacao", "falencia", "liquidacao", "paralisada")):
        add(f"Situação do emissor na CVM: {sit}", "alta", "armadilha")
    if m.get("pl_contabil") is not None and m["pl_contabil"] <= 0:
        add("Patrimônio líquido negativo", "alta", "armadilha")
    if ll is not None and ll <= 0:
        add("Prejuízo nos últimos 12 meses", "alta", "armadilha")
    elif pos(lm) and ll is not None and ll < 0.6 * lm:
        if tl is not None and tl < -0.05:
            add("Lucro em queda estrutural (12m < 60% da média de 5 anos e tendência negativa)", "alta", "armadilha")
        else:
            add("Lucro dos últimos 12 meses bem abaixo da média de 5 anos", "media", "armadilha")
    elif tl is not None and tl < -0.10:
        add(f"Tendência de queda do lucro ({tl:.0%} ao ano)", "media", "armadilha")
    tr = m.get("tend_receita")
    if tr is not None and tr < -0.05:
        add(f"Receita encolhendo ({tr:.0%} ao ano) — possível perda de competitividade", "media", "armadilha")
    if m.get("direcao_margem") == "queda":
        add("Margem líquida em queda há 3 exercícios", "media", "armadilha")
    if grupo == "commodities" and pos(m.get("pl")) and pos(m.get("pl_normalizado")) \
            and m["pl_normalizado"] > 1.5 * m["pl"]:
        add("Cíclica com lucro acima da média histórica: P/L atual pode ser 'barato no topo do ciclo'",
            "media", "armadilha")
    if not fin:
        dle = m.get("dl_ebitda")
        if dle is not None and dle > (5.0 if util else 3.5):
            add(f"Dívida líquida/EBITDA elevada ({dle:.1f}x)", "alta", "armadilha")
        if m.get("ebitda_ttm") is not None and m["ebitda_ttm"] <= 0 and (m.get("divida_liquida") or 0) > 0:
            add("EBITDA negativo com dívida líquida", "alta", "armadilha")
        cj = m.get("cobertura_juros")
        if cj is not None and cj < 1.5 and (m.get("divida_liquida") or 0) > 0:
            add(f"Cobertura de juros baixa (EBIT/despesa financeira = {cj:.1f}x)", "alta", "armadilha")
        z = val.get("altman_z2")
        if z and z["zona"] == "risco":
            add(f"Altman Z'' na zona de risco ({z['z']:.2f} < 1,1)", "alta", "armadilha")
        f = val.get("piotroski") or {}
        if f.get("avaliados", 0) >= 7 and f["score"] <= 3:
            add(f"Piotroski F-Score fraco ({f['score']}/{f['avaliados']})", "alta" if f["score"] <= 2 else "media",
                "armadilha")
        if m.get("anos_fco_negativo_3a", 0) >= 2:
            add("Caixa operacional negativo em 2 dos últimos 3 exercícios", "alta", "armadilha")

    vol = m.get("volume_medio_3m") or m.get("volume_financeiro")
    if vol is not None and vol < 1e6:
        add(f"Baixa liquidez (~R$ {vol / 1e3:.0f} mil/dia): difícil entrar e sair", "media", "mercado")

    # --- Qualidade do lucro
    if m.get("ir_positivo"):
        add("Imposto de renda positivo (crédito fiscal) inflando o lucro — o recorrente é menor", "media", "lucro")
    if m.get("descontinuadas_relevantes"):
        add("Lucro com efeito relevante de operações descontinuadas", "media", "lucro")
    if pos(lm) and pos(ll) and ll > 2 * lm:
        add("Lucro 12m acima do dobro da média de 5 anos — checar não recorrentes/pico de ciclo", "media", "lucro")
    if not fin and pos(ll) and m.get("fco_ttm") is not None and m["fco_ttm"] < 0.5 * ll and not m.get("fco_atipico"):
        add("Caixa operacional bem abaixo do lucro (baixa conversão do lucro em caixa)", "media", "lucro")
    if m.get("fco_atipico"):
        add("Caixa operacional muito acima do EBITDA (capital de giro/antecipação de recebíveis): "
            "FCF desconsiderado no score", "baixa", "lucro")
    if m.get("pl") is not None and m["pl"] < 3:
        add(f"P/L muito baixo ({m['pl']:.1f}x) — verificar ganhos não recorrentes", "media", "lucro")

    # --- Dividendos
    dy = m.get("dy")
    if dy is not None and dy > 0.15:
        add(f"Dividend yield de {dy:.0%} — provável extraordinário/não recorrente", "media", "dividendos")
    if m.get("payout") is not None and m["payout"] > 1.0 and not util:
        add(f"Payout acima de 100% do lucro ({m['payout']:.0%})", "media", "dividendos")

    # --- Balanço / diluição
    d = m.get("diluicao_anual")
    if d is not None and d > 0.03:
        add(f"Diluição: nº de ações cresce {d:.1%} ao ano com emissões em caixa", "media", "balanco")
    for ano, var in m.get("aumentos_sem_emissao") or []:
        if var > 0.05:
            add(f"Nº de ações +{var:.0%} em {ano} sem emissão em caixa (bonificação, desdobramento ou "
                "incorporação) — confirme no RI", "baixa", "dados")
    if not fin:
        cdv, cll, crc = m.get("cagr_divida_5a"), m.get("cagr_lucro_5a"), m.get("cagr_receita_5a")
        if cdv is not None and cdv > 0.15 and (cll is None or cdv > cll + 0.10):
            add(f"Dívida bruta cresce {cdv:.0%} ao ano, mais que o lucro", "media", "balanco")
        if m.get("cagr_recebiveis_5a") is not None and crc is not None and m["cagr_recebiveis_5a"] > crc + 0.15:
            add("Contas a receber crescem muito acima da receita", "media", "balanco")
        if m.get("cagr_estoques_5a") is not None and crc is not None and m["cagr_estoques_5a"] > crc + 0.15:
            add("Estoques crescem muito acima da receita", "media", "balanco")
        if m.get("anos_fcf_negativo_3a", 0) >= 2 and not m.get("fco_atipico"):
            add("Fluxo de caixa livre negativo em 2 dos últimos 3 exercícios", "media", "balanco")
        if (m.get("roe") or 0) > 0.25 and (m.get("dl_pl") or 0) > 1.5:
            add("ROE alto sustentado por alavancagem (dívida líquida > 1,5× PL)", "media", "balanco")

    # --- Dados
    ref = (ttm_info or {}).get("ref")
    if ref:
        from datetime import date
        idade = (date.today() - date.fromisoformat(ref)).days
        if idade > 200:
            add(f"Demonstrações defasadas (último período: {ref})", "baixa", "dados")
    return out


# ---------------------------------------------------------------------------
# Selo de barateza
# ---------------------------------------------------------------------------
def selo(sc, al, m, val) -> dict:
    v = sc["pilares"]["valuation"]
    qual = sc["pilares"]["rentabilidade"] + sc["pilares"]["saude"]
    trap = sum(2 if a["severidade"] == "alta" else 1 for a in al
               if a["categoria"] == "armadilha" and a["severidade"] in ("alta", "media"))
    motivos = [a["flag"] for a in al if a["categoria"] == "armadilha"][:4]
    peg = (val.get("peg") or {}).get("peg")
    grave = any(a["severidade"] == "alta" for a in al)
    lucro_duvidoso = any(a["categoria"] == "lucro" and a["severidade"] in ("alta", "media") for a in al)
    if v >= 16 and trap >= 3:
        cod, txt = "armadilha", "🟠 Possível armadilha de valor"
    elif v >= 16 and qual >= 20 and trap == 0 and not grave and not lucro_duvidoso:
        cod, txt = "barata_solida", "🟢 Barata com fundamentos sólidos"
    elif v >= 16:
        cod, txt = "barata_ressalvas", "🟡 Barata, com ressalvas"
    elif v >= 11:
        cod, txt = ("justa_qualidade", "⚪ Preço justo — empresa de qualidade") if qual >= 22 else ("justa", "⚪ Preço justo")
    elif peg is not None and peg < 1 and (m.get("tend_lucro") or 0) > 0.10:
        cod, txt = "cara_crescimento", "🔵 Cara nos múltiplos, mas o crescimento pode justificar"
    else:
        cod, txt = "cara", "🔴 Cara"
    return {"codigo": cod, "selo": txt, "valuation": v, "qualidade_quant": round(qual, 1),
            "pontos_armadilha": trap, "motivos": motivos}
