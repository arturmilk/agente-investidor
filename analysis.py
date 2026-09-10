"""Motor de análise fundamentalista — destilado do guia do usuário.

Estrutura do score (0–100), conforme bloco 82 do guia:
  Qualidade 20 | Crescimento 20 | Rentabilidade 15 | Balanço 15 | Valuation 20 | Risco 10

Aqui são calculadas as partes QUANTITATIVAS (Crescimento + Rentabilidade +
Balanço + Valuation = 70 pts) a partir de dados gratuitos:
  - brapi.dev (cotação, perfil, setor)
  - yfinance (DRE, balanço, DFC históricos)

Todos os múltiplos (P/L, P/VP, EV/EBITDA, PEG, ROE, ROIC, margens, EPS,
payout, DY) são COMPUTADOS a partir de valores brutos — não confiamos nos
indicadores pré-calculados do Yahoo (vêm com escala inconsistente para B3).

Qualidade e Risco (30 pts) ficam para a camada de raciocínio (LLM).
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _num(x):
    return x if isinstance(x, (int, float)) else None


def _yearly(entries):
    if not entries:
        return []
    y = [e for e in entries if e.get("type") == "yearly"]
    return y or entries


def _series(entries, field):
    """Converte lista de entries em [(ano, valor)], mais recente primeiro."""
    out = []
    for e in _yearly(entries):
        y = (e.get("endDate") or "")[:4]
        v = _num(e.get(field))
        if y and v is not None:
            out.append((y, v))
    return out


def cagr(series, window=None):
    """CAGR (anual composto) da série [(ano, valor)], mais recente primeiro.

    window: usa apenas os N anos mais recentes. Se valores forem negativos/zero
    no início ou fim, retorna None (CAGR indefinido).
    """
    if not series or len(series) < 2:
        return None
    s = sorted(series, key=lambda t: t[0])  # ascendente
    if window and len(s) > window:
        s = s[-window:]
    (y0, v0), (y1, v1) = s[0], s[-1]
    years = int(y1) - int(y0)
    if years <= 0 or v0 <= 0 or v1 <= 0:
        return None
    return (v1 / v0) ** (1 / years) - 1


def _yoy(series):
    """Crescimento ano-a-ano (último vs anterior)."""
    if len(series) >= 2:
        cur = series[0][1]
        prev = series[1][1]
        if cur is not None and prev:
            return cur / prev - 1
    return None


def _trend(series, n=3):
    """Tendência simples: 'alta', 'queda' ou 'estavel' nos últimos n valores."""
    vals = [v for _, v in series if v is not None][:n]
    if len(vals) < 2:
        return "estavel"
    if all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
        return "alta"
    if all(vals[i] <= vals[i + 1] for i in range(len(vals) - 1)):
        return "queda"
    return "estavel"


def _match_ratio(num_series, den_series):
    """Razão anual (ex.: margem líquida = lucro/receita) por ano comum."""
    den = dict(den_series)
    out = []
    for y, v in num_series:
        d = den.get(y)
        if d:
            out.append((y, v / d))
    return out


def _last(series):
    return series[0][1] if series else None


# ---------------------------------------------------------------------------
# Pontuação por subcritério (0–5 cada)
# ---------------------------------------------------------------------------
def _cresc_score(g):
    if g is None:
        return 2.5
    if g >= 0.15:
        return 5
    if g >= 0.10:
        return 4
    if g >= 0.05:
        return 3
    if g >= 0.0:
        return 2
    return 1


def _roe_score(roe):
    if roe is None:
        return 2.5
    if roe >= 0.20:
        return 5
    if roe >= 0.15:
        return 4
    if roe >= 0.10:
        return 3
    if roe >= 0.05:
        return 2
    return 1


def _roic_score(roic):
    if roic is None:
        return 2.5
    if roic >= 0.15:
        return 5
    if roic >= 0.12:
        return 4
    if roic >= 0.08:
        return 3
    if roic >= 0.04:
        return 2
    return 1


def _margin_score(m):
    if m is None:
        return 2.5
    if m >= 0.20:
        return 5
    if m >= 0.12:
        return 4
    if m >= 0.07:
        return 3
    if m >= 0.03:
        return 2
    return 1


def _dl_ebitda_score(x, is_financial=False):
    """Dívida líquida/EBITDA → 0–5. Menor é melhor."""
    if is_financial or x is None:
        return 3.0
    if x < 0:
        return 5
    if x < 1:
        return 5
    if x < 2:
        return 4
    if x < 3:
        return 3
    if x < 4:
        return 2
    return 1


def _liquidez_score(cr, is_financial=False):
    if cr is None:
        return 2.5
    if is_financial:
        return 3.0 if cr > 1 else 2.0
    if cr >= 1.5:
        return 5
    if cr >= 1.2:
        return 4
    if cr >= 0.9:
        return 3
    if cr >= 0.6:
        return 2
    return 1


def _cobertura_score(icr):
    if icr is None:
        return 2.5
    if icr >= 8:
        return 5
    if icr >= 5:
        return 4
    if icr >= 3:
        return 3
    if icr >= 1.5:
        return 2
    return 1


def _peg_score(peg):
    if peg is None:
        return 2.5
    if peg <= 0:
        return 1
    if peg < 0.7:
        return 5
    if peg < 1.0:
        return 4
    if peg < 1.5:
        return 3
    if peg < 2.0:
        return 2
    return 1


def _ev_ebitda_score(x, is_financial=False):
    if is_financial or x is None:
        return 3.0
    if x <= 0:
        return 1
    if x < 5:
        return 5
    if x < 8:
        return 4
    if x < 12:
        return 3
    if x < 16:
        return 2
    return 1


def _pfcf_score(x):
    if x is None or x <= 0:
        return 1
    if x < 10:
        return 5
    if x < 15:
        return 4
    if x < 20:
        return 3
    if x < 30:
        return 2
    return 1


def _pvp_score(x):
    if x is None:
        return 2.5
    if x < 1:
        return 5
    if x < 2:
        return 4
    if x < 3:
        return 3
    if x < 5:
        return 2
    return 1


# ---------------------------------------------------------------------------
# Construção de métricas
# ---------------------------------------------------------------------------
def is_financial(raw) -> bool:
    p = raw.get("profile", {})
    txt = " ".join(str(p.get(k, "")) for k in ("sector", "industry", "sectorKey", "industryKey")).lower()
    return any(k in txt for k in ("financeiro", "banco", "bancos", "bank", "seguradora", "financial"))


def build_metrics(raw: dict) -> dict:
    q = raw.get("quote", {})
    prof = raw.get("profile", {})
    info = raw.get("info", {})
    inc = raw.get("income_statement", [])
    bal = raw.get("balance_sheet", [])
    cf = raw.get("cash_flow", [])
    dividends_12m = raw.get("dividends_12m")

    fin = is_financial(raw)

    # Séries históricas — CVM (fonte primária) tem prioridade sobre o yfinance
    cvm_series = (raw.get("cvm") or {}).get("series") or {}

    def _cvm_list(key):
        d = cvm_series.get(key)
        if not d:
            return None
        return [(str(y), v) for y, v in sorted(d.items(), reverse=True)]

    hist_receita = _cvm_list("receita") or _series(inc, "totalRevenue")
    hist_lucro = _cvm_list("lucro_liquido") or _series(inc, "netIncome")
    hist_shares = _series(inc, "dilutedAverageShares") or _series(inc, "basicAverageShares")
    hist_eps = _match_ratio(hist_lucro, hist_shares)  # lucro / nº de ações
    hist_fco = _cvm_list("fco") or _series(cf, "operatingCashFlow")
    if "fco" in cvm_series and "fci" in cvm_series:
        fco_d, fci_d = cvm_series["fco"], cvm_series["fci"]
        hist_fcf = [(str(y), fco_d.get(y, 0.0) + fci_d.get(y, 0.0)) for y in sorted(fco_d, reverse=True)]
    else:
        hist_fcf = _series(cf, "freeCashFlow")
    hist_margem_liquida = _match_ratio(hist_lucro, hist_receita)
    hist_lucro_bruto = _cvm_list("lucro_bruto") or _series(inc, "grossProfit")
    hist_margem_bruta = _match_ratio(hist_lucro_bruto, hist_receita)
    hist_ebit = _cvm_list("ebit") or _series(inc, "ebit") or _series(inc, "operatingIncome")
    hist_ebitda = _cvm_list("ebitda") or _series(inc, "ebitda")
    hist_equity = _cvm_list("patrimonio_liquido") or _series(bal, "totalStockholderEquity")
    hist_roe = _match_ratio(hist_lucro, hist_equity)
    hist_divida = _cvm_list("divida_total") or _series(bal, "totalDebt")
    hist_recebiveis = _series(bal, "netReceivables")
    hist_estoque = _series(bal, "inventory")
    hist_ativo = _cvm_list("ativo_total") or _series(bal, "totalAssets")
    hist_caixa = _cvm_list("caixa") or _series(bal, "cash")
    hist_acoes = hist_shares  # nº de ações (para detectar diluição)
    usa_cvm = bool(cvm_series)

    # Valores atuais (último ano)
    preco = _num(q.get("regularMarketPrice"))
    market_cap = _num(q.get("marketCap"))
    netIncome = _last(hist_lucro)
    equity = _last(hist_equity)
    total_assets = _last(hist_ativo)
    total_debt = _last(hist_divida)
    cash = _last(hist_caixa)
    ebitda = _last(hist_ebitda)
    ebit = _last(hist_ebit)
    revenue = _last(hist_receita)
    gross_profit = _last(hist_lucro_bruto)
    fcf = _last(hist_fcf)
    fco = _last(hist_fco)
    interest_expense = _last(_series(inc, "interestExpense"))
    income_before_tax = _last(_series(inc, "incomeBeforeTax"))
    income_tax = _last(_series(inc, "incomeTaxExpense"))
    cur_assets = _last(_series(bal, "totalCurrentAssets"))
    cur_liab = _last(_series(bal, "totalCurrentLiabilities"))
    inventory = _last(hist_estoque)
    dividends_paid = _last(_series(cf, "cashDividendsPaid")) or _last(_series(cf, "commonDividendPaid"))

    # CAGRs (5 anos)
    cagr_receita = cagr(hist_receita, window=5)
    cagr_lucro = cagr(hist_lucro, window=5)
    cagr_eps = cagr(hist_eps, window=5)
    cagr_fcf = cagr(hist_fcf, window=5)

    # --- Valuation (computado) ---
    pe = (market_cap / netIncome) if (market_cap and netIncome and netIncome > 0) else None
    pvp = (market_cap / equity) if (market_cap and equity and equity > 0) else None
    ev = (market_cap + total_debt - cash) if (market_cap is not None and total_debt is not None and cash is not None) else None
    ev_ebitda = (ev / ebitda) if (ev and ebitda) else None
    ev_receita = (ev / revenue) if (ev and revenue) else None
    ps = (market_cap / revenue) if (market_cap and revenue) else None
    pfcf = (market_cap / fcf) if (market_cap and fcf and fcf > 0) else None
    peg = (pe / (cagr_lucro * 100)) if (pe and cagr_lucro and cagr_lucro > 0) else None

    # --- Rentabilidade ---
    roe = (netIncome / equity) if (netIncome is not None and equity) else None
    roa = (netIncome / total_assets) if (netIncome is not None and total_assets) else None
    tax_rate = (income_tax / income_before_tax) if (income_tax is not None and income_before_tax) else 0.0
    tax_rate = max(0.0, min(0.5, tax_rate))
    nopat = (ebit * (1 - tax_rate)) if ebit is not None else None
    invested = (equity + total_debt - cash) if (equity is not None and total_debt is not None and cash is not None) else None
    roic = (nopat / invested) if (nopat and invested) else None

    margem_bruta = (gross_profit / revenue) if (gross_profit and revenue) else None
    margem_ebitda = (ebitda / revenue) if (ebitda and revenue) else None
    margem_liquida = (netIncome / revenue) if (netIncome is not None and revenue) else None

    # --- Balanço ---
    divida_liquida = (total_debt - cash) if (total_debt is not None and cash is not None) else None
    dl_ebitda = (divida_liquida / ebitda) if (divida_liquida is not None and ebitda) else None
    debt_to_equity = (total_debt / equity) if (total_debt is not None and equity) else None
    liquidez_corrente = (cur_assets / cur_liab) if (cur_assets and cur_liab) else None
    liquidez_seca = ((cur_assets - inventory) / cur_liab) if (cur_assets and cur_liab and inventory is not None) else None
    cobertura_juros = (ebit / abs(interest_expense)) if (ebit is not None and interest_expense not in (None, 0)) else None

    # --- Dividendos ---
    payout = (abs(dividends_paid) / netIncome) if (dividends_paid is not None and netIncome) else None
    dy = (dividends_12m / preco) if (dividends_12m is not None and preco) else None

    # --- Crescimento YoY ---
    cresc_receita = _yoy(hist_receita)
    cresc_lucro = _yoy(hist_lucro)

    # --- beta (valida) e preço-alvo ---
    beta = _num(info.get("beta"))
    if beta is not None and not (0 < beta < 3):
        beta = None
    alvo = _num(info.get("targetMeanPrice"))
    upside = ((alvo - preco) / preco) if (alvo and preco) else None

    conversao_caixa = (fcf / netIncome) if (fcf and netIncome) else None

    return {
        "symbol": raw.get("symbol"),
        "nome": q.get("shortName") or q.get("longName"),
        "nome_longo": prof.get("longName") or q.get("longName"),
        "setor": prof.get("sector"),
        "industria": prof.get("industry"),
        "negocio": (prof.get("longBusinessSummary") or "")[:800],
        "is_financial": fin,
        "fonte_cvm": usa_cvm,
        "cvm_match": (raw.get("cvm") or {}).get("match"),
        # cotação
        "preco": preco,
        "market_cap": market_cap,
        "volume_financeiro_dia": (q.get("regularMarketPrice") or 0) * (q.get("regularMarketVolume") or 0),
        "min_52s": q.get("fiftyTwoWeekLow"),
        "max_52s": q.get("fiftyTwoWeekHigh"),
        "beta": beta,
        # valuation
        "pe": pe,
        "pvp": pvp,
        "ev_ebitda": ev_ebitda,
        "ev_receita": ev_receita,
        "ps": ps,
        "pfcf": pfcf,
        "peg": peg,
        "dy": dy,
        "payout_est": payout,
        "preco_alvo_medio": alvo,
        "upside": upside,
        # rentabilidade
        "roe": roe,
        "roa": roa,
        "roic": roic,
        "margem_bruta": margem_bruta,
        "margem_ebitda": margem_ebitda,
        "margem_liquida": margem_liquida,
        # crescimento
        "cresc_receita": cresc_receita,
        "cresc_lucro": cresc_lucro,
        # balanço
        "divida_total": total_debt,
        "caixa": cash,
        "divida_liquida": divida_liquida,
        "divida_liquida_ebitda": dl_ebitda,
        "divida_equity": debt_to_equity,
        "liquidez_corrente": liquidez_corrente,
        "liquidez_seca": liquidez_seca,
        "cobertura_juros": cobertura_juros,
        # fluxo de caixa
        "fcf": fcf,
        "fco": fco,
        "conversao_caixa": conversao_caixa,
        # histórico
        "cagr_receita": cagr_receita,
        "cagr_lucro": cagr_lucro,
        "cagr_eps": cagr_eps,
        "cagr_fcf": cagr_fcf,
        "hist_receita": hist_receita,
        "hist_lucro": hist_lucro,
        "hist_eps": hist_eps,
        "hist_fcf": hist_fcf,
        "hist_margem_liquida": hist_margem_liquida,
        "hist_margem_bruta": hist_margem_bruta,
        "hist_roe": hist_roe,
        "hist_divida": hist_divida,
        "hist_recebiveis": hist_recebiveis,
        "hist_estoque": hist_estoque,
        "hist_acoes": hist_acoes,
        "tendencia_margem_liquida": _trend(hist_margem_liquida),
        "tendencia_roe": _trend(hist_roe),
    }


# ---------------------------------------------------------------------------
# Score determinístico (0–70)
# ---------------------------------------------------------------------------
def deterministic_score(m: dict) -> dict:
    fin = m["is_financial"]

    cresc = {
        "receita": _cresc_score(m["cagr_receita"]),
        "lucro": _cresc_score(m["cagr_lucro"]),
        "eps": _cresc_score(m["cagr_eps"]),
        "fcf": _cresc_score(m["cagr_fcf"]),
    }
    cresc_total = sum(cresc.values()) / 4 * 20 / 5  # 4×5 → 20

    rent = {
        "roe": _roe_score(m["roe"]),
        "roic": _roic_score(m["roic"]),
        "margem": _margin_score(m["margem_liquida"]),
    }
    if m["tendencia_margem_liquida"] == "alta":
        rent["margem"] = min(5, rent["margem"] + 0.5)
    elif m["tendencia_margem_liquida"] == "queda":
        rent["margem"] = max(1, rent["margem"] - 0.5)
    rent_total = sum(rent.values()) / 3 * 15 / 5

    bal = {
        "divida_liquida_ebitda": _dl_ebitda_score(m["divida_liquida_ebitda"], fin),
        "liquidez": _liquidez_score(m["liquidez_corrente"], fin),
        "cobertura_juros": _cobertura_score(m["cobertura_juros"]),
    }
    bal_total = sum(bal.values()) / 3 * 15 / 5

    val = {
        "peg": _peg_score(m["peg"]),
        "ev_ebitda": _ev_ebitda_score(m["ev_ebitda"], fin),
        "pfcf": _pfcf_score(m["pfcf"]),
        "pvp": _pvp_score(m["pvp"]),
    }
    val_total = sum(val.values()) / 4 * 20 / 5

    total = cresc_total + rent_total + bal_total + val_total

    return {
        "crescimento": {**cresc, "total": round(cresc_total, 1), "peso": 20},
        "rentabilidade": {**rent, "total": round(rent_total, 1), "peso": 15},
        "balanco": {**bal, "total": round(bal_total, 1), "peso": 15},
        "valuation": {**val, "total": round(val_total, 1), "peso": 20},
        "total_deterministico": round(total, 1),
        "max_deterministico": 70,
    }


# ---------------------------------------------------------------------------
# Red flags (guia, bloco 70)
# ---------------------------------------------------------------------------
def red_flags(m: dict) -> list:
    flags = []

    def cagr_serie(s):
        return cagr(s, window=5) if s else None

    # 1. Receita sobe mas caixa não
    if m["cagr_receita"] and m["cagr_receita"] > 0.05 and m["fcf"] is not None and m["fcf"] < 0:
        flags.append({"flag": "Receita sobe, mas fluxo de caixa livre negativo", "severidade": "alta"})
    # 2. Lucro sobe mas FCO cai
    if m["cagr_lucro"] and m["cagr_lucro"] > 0.05 and m["fco"] is not None and m["fco"] < 0:
        flags.append({"flag": "Lucro cresce, mas fluxo de caixa operacional negativo", "severidade": "alta"})
    # 3. Dívida cresce muito
    cagr_div = cagr_serie(m["hist_divida"])
    if cagr_div is not None and cagr_div > 0.15 and m["cagr_lucro"] is not None and cagr_div > m["cagr_lucro"] + 0.10:
        flags.append({"flag": f"Dívida cresce muito (CAGR {cagr_div:.0%}) vs lucro", "severidade": "media"})
    # 4. Contas a receber explodem (vs receita)
    cagr_recb = cagr_serie(m["hist_recebiveis"])
    if cagr_recb is not None and m["cagr_receita"] is not None and cagr_recb > m["cagr_receita"] + 0.15:
        flags.append({"flag": f"Contas a receber crescem ({cagr_recb:.0%}) muito acima da receita", "severidade": "media"})
    # 5. Estoques explodem
    cagr_estoque = cagr_serie(m["hist_estoque"])
    if cagr_estoque is not None and m["cagr_receita"] is not None and cagr_estoque > m["cagr_receita"] + 0.15:
        flags.append({"flag": f"Estoque cresce ({cagr_estoque:.0%}) muito acima da receita", "severidade": "media"})
    # 6. Margens caem continuamente
    if m["tendencia_margem_liquida"] == "queda":
        flags.append({"flag": "Margem líquida em tendência de queda", "severidade": "media"})
    # 7. Diluição (ações crescem mais que o lucro)
    cagr_acoes = cagr_serie(m["hist_acoes"])
    if cagr_acoes is not None and cagr_acoes > 0.10 and m["cagr_eps"] is not None and m["cagr_eps"] < cagr_acoes - 0.05:
        flags.append({"flag": f"Diluição: nº de ações cresce {cagr_acoes:.0%} ao ano", "severidade": "media"})
    # 8. P/L extremamente baixo
    if m["pe"] is not None and m["pe"] < 3:
        flags.append({"flag": f"P/L extremamente baixo ({m['pe']:.1f}x) sem explicação", "severidade": "media"})
    # 9. DY absurdamente alto
    if m["dy"] is not None and m["dy"] > 0.15:
        flags.append({"flag": f"Dividend yield muito alto ({m['dy']:.0%}) — possível queda de preço", "severidade": "media"})
    # 10. ROE alto por alavancagem
    if m["roe"] is not None and m["roe"] > 0.25 and m["divida_equity"] is not None and m["divida_equity"] > 1.5 and not m["is_financial"]:
        flags.append({"flag": "ROE alto possivelmente por alavancagem (dívida/PL elevado)", "severidade": "media"})
    # 11. FCF negativo recorrente (2+ anos dos últimos 3)
    fcf_vals = [v for _, v in (m["hist_fcf"] or []) if v is not None][:3]
    if len(fcf_vals) >= 2 and sum(1 for v in fcf_vals if v < 0) >= 2:
        flags.append({"flag": "Fluxo de caixa livre negativo em anos recentes", "severidade": "alta"})
    # 12. Payout insustentável (>100% do lucro)
    if m["payout_est"] is not None and m["payout_est"] > 1.0:
        flags.append({"flag": f"Payout estimado acima de 100% do lucro ({m['payout_est']:.0%})", "severidade": "media"})
    # 13. EPS e lucro divergem fortemente (dado anômalo ou diluição)
    if m["cagr_eps"] is not None and m["cagr_lucro"] is not None and abs(m["cagr_eps"] - m["cagr_lucro"]) > 0.30:
        flags.append({"flag": f"EPS ({m['cagr_eps']:.0%}) e lucro ({m['cagr_lucro']:.0%}) divergem — investigar", "severidade": "media"})

    return flags
