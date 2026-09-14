"""Relatórios em Markdown: completo (terminal/arquivo) e compacto (Telegram/WhatsApp)."""
from __future__ import annotations

from datetime import datetime

NOMES_METODO = {"graham": "Graham", "bazin": "Bazin", "pl_do_setor": "P/L do setor",
                "ev_ebit_do_setor": "EV/EBIT do setor", "pvp_do_setor": "P/VP do setor",
                "pl_historico": "P/L histórico", "pvp_historico": "P/VP histórico",
                "pvp_justo_roe": "P/VP justo (ROE)"}
NOMES_PERCENTIL = {"pl": "P/L", "pvp": "P/VP", "ev_ebit": "EV/EBIT", "dy": "DY", "roe": "ROE"}
_SEV = {"alta": 0, "media": 1, "baixa": 2}


# ---------------------------------------------------------------------------
# Formatação pt-BR
# ---------------------------------------------------------------------------
def _br(s):
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def num(x, nd=1):
    return "—" if x is None else _br(f"{x:,.{nd}f}")


def pct(x, nd=1):
    if x is None:
        return "—"
    x = 0.0 if abs(x) < 0.5 * 10 ** -(nd + 2) else x  # evita "-0,0%"
    return _br(f"{x * 100:.{nd}f}") + "%"


def mult(x, nd=1):
    return "—" if x is None else _br(f"{x:.{nd}f}") + "x"


def rs(x, nd=2):
    return "—" if x is None else "R$ " + _br(f"{x:,.{nd}f}")


def rs_grande(x):
    if x is None:
        return "—"
    a, s = abs(x), "-" if x < 0 else ""
    for lim, suf, nd in ((1e12, "tri", 2), (1e9, "bi", 1), (1e6, "mi", 0)):
        if a >= lim:
            return f"{s}R$ {_br(f'{a / lim:,.{nd}f}')} {suf}"
    return f"{s}R$ {_br(f'{a / 1e3:,.0f}')} mil"


def up(x):
    return "—" if x is None else ("+" if x >= 0 else "") + pct(x, 0)


def macro_linha(mac):
    p = []
    if mac.get("selic_meta") is not None:
        p.append(f"Selic {num(mac['selic_meta'], 2)}%")
    if mac.get("ipca_12m") is not None:
        p.append(f"IPCA 12m {num(mac['ipca_12m'], 2)}%")
    if mac.get("juro_real_aprox") is not None:
        p.append(f"juro real ~{pct(mac['juro_real_aprox'])}")
    if mac.get("cambio_usd_brl"):
        p.append(f"dólar {rs(mac['cambio_usd_brl'])}")
    if mac.get("ibov"):
        p.append(f"Ibovespa {num(mac['ibov'], 0)} pts ({up(mac.get('ibov_var_12m'))} em 12m)")
    return " · ".join(p) or "indisponível"


def _pilares(sc):
    p = sc["pilares"]
    return (f"Valuation {num(p['valuation'])}/25 · Crescimento {num(p['crescimento'])}/15 · "
            f"Rentabilidade {num(p['rentabilidade'])}/15 · Saúde {num(p['saude'])}/15")


def _setor_nome(s):
    return s.get("nome") or (s.get("base") or "—").capitalize()


# ---------------------------------------------------------------------------
# Análise individual
# ---------------------------------------------------------------------------
def analise_md(p, compacto=False) -> str:
    ativos = sorted(p.get("ativos") or [], key=lambda a: -a["score"]["total_deterministico"])
    if compacto:
        return _analise_compacta(p, ativos)
    L = [f"# Agente Bolsa — análise fundamentalista ({datetime.now():%d/%m/%Y})", "",
         f"**Contexto macro:** {macro_linha(p.get('macro') or {})}", ""]
    if len(ativos) > 1:
        L += ["## Ranking — score determinístico (máx. 70; qualidade e risco, 30 pts, na análise qualitativa)", "",
              "| # | Ticker | Empresa | Selo | Score /70 | P/L | P/VP | EV/EBIT | DY 12m | ROE | Preço justo | Margem |",
              "|--:|---|---|---|--:|--:|--:|--:|--:|--:|--:|--:|"]
        for i, a in enumerate(ativos, 1):
            m, t = a["indicadores"], a["valuation"]["triangulacao"]
            L.append(f"| {i} | {a['ticker']} | {a['empresa'][:28]} | {a['selo']['selo']} | "
                     f"**{num(a['score']['total_deterministico'])}** | {mult(m.get('pl'))} | {mult(m.get('pvp'), 2)} | "
                     f"{mult(m.get('ev_ebit'))} | {pct(m.get('dy'))} | {pct(m.get('roe'), 0)} | "
                     f"{rs(t.get('preco_justo'))} | {up(t.get('upside'))} |")
        L.append("")
    for a in ativos:
        L += _ativo_md(a)
    if p.get("erros"):
        L += ["## Não analisados", ""] + [f"- {e}" for e in p["erros"]] + [""]
    L += ["---", f"_{p.get('aviso', '')}_"]
    return "\n".join(L)


def _ativo_md(a):
    m, v, sc, s = a["indicadores"], a["valuation"], a["score"], a["setor"]
    fin = m["financeiro"]
    comp = a.get("setor_comparacao") or {}
    med = comp.get("medianas") or {}
    hm = (a.get("multiplos_historicos") or {}).get("mediana_5a") or {}
    q, d, gov = a["cotacao"], a["dados"], a.get("governanca") or {}
    liq = m.get("volume_medio_3m") or m.get("volume_financeiro")
    L = [f"## {a['ticker']} — {a['empresa']}", "",
         f"**{a['selo']['selo']}** · score determinístico **{num(sc['total_deterministico'])}/70** ({_pilares(sc)}) · "
         f"Qualidade (/20) e Risco (/10): análise qualitativa", "",
         f"- **Setor:** {_setor_nome(s)} — grupo {s['grupo_nome']}"
         + (f"; comparado com {comp.get('n')} pares ({comp.get('setor')})" if comp else ""),
         f"- **Cotação:** {rs(q['preco'])} ({q.get('fonte')}, {q.get('data') or 'hoje'}) · valor de mercado "
         f"{rs_grande(m['market_cap'])} ({(q.get('market_cap_info') or {}).get('fonte') or '—'})"
         + ("" if fin else f" · EV {rs_grande(m.get('ev'))}")
         + (f" · liquidez ~{rs_grande(liq)}/dia" if liq else ""),
         f"- **Dados contábeis:** {d.get('fonte')} (CVM)",
         f"- **Governança:** {gov.get('segmento_listagem') or '—'} · controle {gov.get('controle') or '—'} · "
         f"{gov.get('situacao_emissor') or '—'}", ""]
    neg = " ".join((a.get("negocio") or "").split())
    if neg:
        L += [f"> {neg[:420]}{'…' if len(neg) > 420 else ''}", ""]

    L += ["### Valuation", "", "| Indicador | Empresa | Mediana do setor | Mediana própria (5a) |",
          "|---|--:|--:|--:|", f"| P/L | {mult(m.get('pl'))} | {mult(med.get('pl'))} | {mult(hm.get('pl'))} |"]
    if m["grupo"] == "commodities" or (m.get("pl_normalizado") and m.get("pl") and m["pl_normalizado"] > 1.5 * m["pl"]):
        L.append(f"| P/L sobre lucro médio de 5 anos | {mult(m.get('pl_normalizado'))} | — | — |")
    L.append(f"| P/VP | {mult(m.get('pvp'), 2)} | {mult(med.get('pvp'), 2)} | {mult(hm.get('pvp'), 2)} |")
    if not fin:
        L += [f"| EV/EBIT | {mult(m.get('ev_ebit'))} | {mult(med.get('ev_ebit'))} | {mult(hm.get('ev_ebit'))} |",
              f"| EV/EBITDA | {mult(m.get('ev_ebitda'))} | {mult(med.get('ev_ebitda'))} | — |",
              f"| P/FCF | {mult(m.get('p_fcf'))} | — | — |"]
    L += [f"| Dividend yield 12m (caixa) | {pct(m.get('dy'))} | {pct(med.get('dy'))} | {pct(hm.get('dy'))} |",
          f"| DY mediano 5a sobre o preço atual | {pct(m.get('dy_mediano_5a'))} | — | — |",
          f"| Lucro/preço vs Selic | {pct(m.get('lucro_yield'))} | prêmio {pct(m.get('premio_lucro_selic'))} | — |", ""]
    pc = comp.get("percentis") or {}
    if pc:
        L += ["Posição no setor (percentil; 0 = menor valor): "
              + " · ".join(f"{NOMES_PERCENTIL[k]} {pc[k]}" for k in NOMES_PERCENTIL if k in pc), ""]

    g, b, t, pg = v["graham"], v["bazin"], v["triangulacao"], v.get("peg") or {}
    L += ["### Preço justo e margem de segurança", "",
          f"- **Graham** √(22,5 × LPA × VPA): {rs(g['valor_justo'])} ({up(g['margem'])}) · critérios do investidor "
          f"defensivo: {g['atendidos']}/{g['avaliados']}",
          f"- **Bazin** (dividendo mediano 5a ÷ 6%): preço-teto {rs(b['preco_teto'])} ({up(b['margem'])}) · "
          f"critérios: {b['atendidos']}/{b['avaliados']}"]
    if fin and v.get("pvp_justo_roe"):
        pr = v["premissas"]
        L.append(f"- **P/VP justo pelo ROE** (Gordon; ke {pct(pr['ke'])}, g {pct(pr['g'])}): "
                 f"{mult(v['pvp_justo_roe'], 2)} vs atual {mult(m.get('pvp'), 2)}")
    if t.get("preco_justo"):
        met = ", ".join(f"{NOMES_METODO.get(k, k)} {rs(x)}" for k, x in t["metodos"].items())
        L.append(f"- **Triangulação** ({met}): preço justo **{rs(t['preco_justo'])}** → margem de segurança "
                 f"**{up(t['upside'])}** (faixa {rs(t['faixa'][0])} a {rs(t['faixa'][1])})")
    else:
        L.append("- **Triangulação:** métodos insuficientes para um preço justo confiável")
    L.append(f"- **PEG** {num(pg.get('peg'), 2)} · **PEGY** {num(pg.get('pegy'), 2)} "
             f"(crescimento do lucro {pct(pg.get('crescimento_lucro'))} ao ano)")
    if a.get("consenso"):
        c = a["consenso"]
        L.append(f"- **Consenso de analistas (Yahoo):** alvo médio {rs(c['preco_alvo_medio'])} "
                 f"({c.get('analistas') or '?'} analistas, {c.get('recomendacao') or '—'})")
    L.append("")

    f, z = v.get("piotroski") or {}, v.get("altman_z2") or {}
    rent = (f"- ROE {pct(m.get('roe'))} (média 5a {pct(m.get('roe_medio_5a'))}) · "
            + (f"ROA {pct(m.get('roa'), 2)}" if fin else f"ROIC {pct(m.get('roic'))} · margem EBIT {pct(m.get('margem_ebit'))}")
            + f" · margem líquida {pct(m.get('margem_liquida'))} (tendência: {m.get('direcao_margem')})")
    saude = (f"- PL/ativo {pct(m.get('pl_ativo'))} · anos com lucro (5a): {m.get('anos_lucro_positivo_5a')} · "
             f"anos com ROE ≥ 12%: {m.get('anos_roe_acima_12_5a')} · desvio do ROE (5a): {pct(m.get('roe_desvio_5a'))}"
             if fin else
             f"- Dívida líquida {rs_grande(m.get('divida_liquida'))} · DL/EBITDA {mult(m.get('dl_ebitda'))} · "
             f"liquidez corrente {num(m.get('liquidez_corrente'), 2)} · cobertura de juros {mult(m.get('cobertura_juros'))}")
    qual = (f"- Piotroski (só critérios aplicáveis a bancos): {f.get('score', '—')}/{f.get('avaliados', '—')}" if fin
            else f"- Piotroski F-Score {f.get('score', '—')}/{f.get('avaliados', '—')} · "
                 f"Altman Z'' {num(z.get('z'), 2)} ({z.get('zona', '—')})")
    cresc = (f"- Crescimento anual (5a): receita {pct(m.get('tend_receita'))} · lucro {pct(m.get('tend_lucro'))} · "
             + (f"patrimônio {pct(m.get('tend_pl'))}" if fin else f"caixa operacional {pct(m.get('tend_fco'))}")
             + f" · último trimestre ({m.get('trimestre_ref') or '—'}): lucro {up(m.get('cresc_lucro_tri'))} "
               f"vs mesmo tri do ano anterior")
    L += ["### Rentabilidade, saúde e crescimento", "", rent, saude, qual, cresc, ""]
    h = a.get("historico") or {}
    if h.get("anos"):
        L += ["| Exercício | Receita | Lucro | Margem líq. | ROE | Dividendos pagos |", "|---|--:|--:|--:|--:|--:|"]
        for i, ano in enumerate(h["anos"]):
            L.append(f"| {ano} | {rs_grande(h['receita'][i])} | {rs_grande(h['lucro'][i])} | "
                     f"{pct(h['margem_liquida'][i])} | {pct(h['roe'][i])} | {rs_grande(h['dividendos'][i])} |")
        L.append("")

    al = sorted(a.get("red_flags") or [], key=lambda x: _SEV.get(x["severidade"], 3))
    L += ["### Red flags", ""] + ([f"- **[{x['severidade']}]** {x['flag']}" for x in al]
                                 or ["- Nenhuma detectada pelos filtros quantitativos."]) + [""]
    nt = a.get("noticias") or {}
    ev, gn = nt.get("cvm_eventos") or [], (nt.get("google_news") or []) + (nt.get("rss") or [])
    if ev or gn:
        L += ["### Fatos relevantes e notícias", ""]
        L += [f"- `{e['data']}` **{e['categoria']}** — {e['assunto'][:110]}" for e in ev[:6]]
        L += [f"- `{n['data']}` {n['titulo'][:120]} ({n['fonte']})" for n in gn[:6]]
        L.append("")
    return L


def _analise_compacta(p, ativos):
    L = [f"📊 *Agente Bolsa* — {datetime.now():%d/%m/%Y}", macro_linha(p.get("macro") or {}), ""]
    for a in ativos:
        m, v, sc = a["indicadores"], a["valuation"], a["score"]
        med = (a.get("setor_comparacao") or {}).get("medianas") or {}
        t, f = v["triangulacao"], v.get("piotroski") or {}
        L += [f"*{a['ticker']}* — {a['empresa'][:32]}",
              f"{a['selo']['selo']} · score {num(sc['total_deterministico'])}/70",
              f"Preço {rs(m['preco'])} · P/L {mult(m.get('pl'))} (setor {mult(med.get('pl'))}) · "
              f"P/VP {mult(m.get('pvp'), 2)} · DY {pct(m.get('dy'))}",
              f"ROE {pct(m.get('roe'), 0)} · "
              + (f"PL/ativo {pct(m.get('pl_ativo'))}" if m["financeiro"]
                 else f"DL/EBITDA {mult(m.get('dl_ebitda'))} · Piotroski {f.get('score', '—')}/{f.get('avaliados', '—')}"),
              f"Preço justo ~{rs(t['preco_justo'])} ({up(t['upside'])})" if t.get("preco_justo")
              else "Preço justo: base insuficiente"]
        for x in sorted(a.get("red_flags") or [], key=lambda x: _SEV.get(x["severidade"], 3))[:2]:
            L.append(f"⚠️ {x['flag']}")
        ev = ((a.get("noticias") or {}).get("cvm_eventos") or [])[:1]
        L += [f"📰 {e['data']} {e['categoria']}: {e['assunto'][:80]}" for e in ev]
        L.append("")
    if p.get("erros"):
        L.append("Não analisados: " + "; ".join(p["erros"]))
    L.append(f"_{p.get('aviso', '')}_")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Screener
# ---------------------------------------------------------------------------
def screener_md(res, compacto=False) -> str:
    itens = res.get("itens") or []
    extra = res.get("coluna_extra")
    if compacto:
        L = [f"🔎 *Screener B3 — {res['titulo']}* ({datetime.now():%d/%m/%Y})", res["descricao"], ""]
        for i, r in enumerate(itens, 1):
            m = r["m"]
            L.append(f"{i}. *{r['symbol']}* {r['nome'][:22]} — {r['selo']['selo'].split(' ', 1)[0]} "
                     f"score {num(r['score']['total_deterministico'])} · P/L {mult(m.get('pl'))} · "
                     f"P/VP {mult(m.get('pvp'), 2)} · DY {pct(m.get('dy'))}"
                     + (f" · {extra} {r['_extra']}" if extra else ""))
        if not itens:
            L.append("Nenhuma ação passou nos filtros.")
        L += ["", f"_{res.get('aviso', '')}_"]
        return "\n".join(L)
    L = [f"# Screener B3 — {res['titulo']} ({datetime.now():%d/%m/%Y})", "", res["descricao"], "",
         f"Universo: {res['universo_n']} companhias com dados · aprovadas nos filtros: {res['aprovadas']} · "
         f"filtros: {res['filtros']}", ""]
    cab = "| # | Ticker | Empresa | Setor | Selo | Score /70 | P/L | P/VP | EV/EBIT | DY | ROE |"
    sep = "|--:|---|---|---|---|--:|--:|--:|--:|--:|--:|"
    if extra:
        cab += f" {extra} |"
        sep += "--:|"
    L += [cab, sep]
    for i, r in enumerate(itens, 1):
        m = r["m"]
        linha = (f"| {i} | {r['symbol']} | {r['nome'][:26]} | {(r.get('setor_nome') or r['setor_base'])[:24]} | "
                 f"{r['selo']['selo']} | **{num(r['score']['total_deterministico'])}** | {mult(m.get('pl'))} | "
                 f"{mult(m.get('pvp'), 2)} | {mult(m.get('ev_ebit'))} | {pct(m.get('dy'))} | {pct(m.get('roe'), 0)} |")
        if extra:
            linha += f" {r['_extra']} |"
        L.append(linha)
    if not itens:
        L.append("\nNenhuma ação passou nos filtros.")
    L += ["", "Para aprofundar: `python scripts/analyze.py TICKER` (histórico, notícias e red flags completas).",
          "", "---", f"_{res.get('aviso', '')}_"]
    return "\n".join(L)
