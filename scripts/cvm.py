"""CVM dados abertos — fonte primária (ouro) dos fundamentos.

Conjuntos usados (gratuitos, sem token, atualizados diariamente pela CVM):
  • DFP (anual) e ITR (trimestral): DRE, balanço (BPA/BPP), DFC e composição
    do capital (nº de ações) de TODAS as companhias abertas;
  • FCA: ticker ↔ código CVM, segmento de listagem (Novo Mercado, N1, N2...),
    espécie de controle (estatal/privado), situação do emissor (ex.:
    recuperação judicial) e setor de atividade;
  • Cadastro: nome comercial (para casar manchetes de notícias);
  • IPE: fatos relevantes, comunicados, resultados e proventos.

Cada zip anual (~13–20 MB, com todas as companhias) é baixado uma vez e
convertido num JSON enxuto só com as contas-chave, reaproveitado pela análise
e pelo screener. Valores em R$ (escala "MIL" já convertida).

TTM (últimos 12 meses) = último exercício anual + acumulado do ano corrente
(ITR) − mesmo período do ano anterior. O balanço vem do último ITR.
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import unicodedata
import zipfile
from datetime import date, datetime, timedelta

from config import CACHE_DIR
from net import download, log

BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
DIR = os.path.join(CACHE_DIR, "cvm")
PARSER_VERSION = 3
DIA = 86400

FLUXOS = ("receita", "custo", "lucro_bruto", "ebit", "resultado_financeiro", "receitas_financeiras",
          "despesas_financeiras", "lair", "ir", "descontinuadas", "lucro_liquido", "lucro_controladora",
          "fco", "fci", "fcfin", "depreciacao", "capex", "dividendos_pagos", "emissao_acoes")
ESTOQUES = ("ativo_total", "ativo_circulante", "caixa", "aplicacoes", "recebiveis", "estoques",
            "imobilizado", "intangivel", "passivo_total", "passivo_circulante", "passivo_nao_circulante",
            "emprestimos_cp", "emprestimos_lp", "pl", "pl_controladora", "minoritarios",
            "reservas_lucros", "lucros_acumulados", "layout")

# Fallback ticker → CD_CVM quando o FCA não trouxer o ticker
OVERRIDES = {"PETR3": 9512, "PETR4": 9512, "WEGE3": 5410, "BBAS3": 1023, "EGIE3": 17329,
             "RENT3": 19739, "MGLU3": 22470}

IPE_CATEGORIAS = ("Fato Relevante", "Comunicado ao Mercado", "Dados Econômico-Financeiros",
                  "Relatório Proventos")


def norm(s: str) -> str:
    """Minúsculas, sem acentos e com espaços simples."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _f(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _iter(z, name, cols):
    """Itera as colunas pedidas de um CSV (latin-1, ';') dentro do zip, em streaming."""
    with z.open(name) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, encoding="latin-1", newline=""), delimiter=";")
        header = next(rd, None) or []
        pos = [header.index(c) if c in header else -1 for c in cols]
        for row in rd:
            yield [row[p] if 0 <= p < len(row) else "" for p in pos]


# ---------------------------------------------------------------------------
# Mapeamento das contas (código CVM + checagem pela descrição)
# ---------------------------------------------------------------------------
def _keep(grp, conta):
    depth = conta.count(".") + 1
    if grp == "dre":
        return conta.startswith("3.") and depth <= 3
    if grp == "bpa":
        return (conta == "1" or conta.startswith("1.")) and depth <= 3
    if grp == "bpp":
        return (conta == "2" or conta.startswith("2.")) and depth <= 3
    return conta.startswith("6.") and (depth <= 3 or (depth == 4 and conta.startswith("6.01.01.")))


def _v(a, code, *kw, nao=()):
    x = a.get(code)
    if x is None:
        return None
    desc, val = x
    if kw and not any(k in desc for k in kw):
        return None
    if nao and any(k in desc for k in nao):
        return None
    return val


def _filhos(a, pai):
    """Contas filhas diretas de `pai` → [(código, descrição, valor)] ordenadas."""
    pre, n = pai + ".", pai.count(".") + 1
    return sorted((c, d, v) for c, (d, v) in a.items() if c.startswith(pre) and c.count(".") == n)


def _dre(a):
    o = {"receita": _v(a, "3.01"), "custo": _v(a, "3.02", "custo"), "lucro_bruto": _v(a, "3.03", "bruto")}
    ll_code = rf_code = None
    for c, d, v in _filhos(a, "3"):
        if "antes do resultado financeiro" in d:
            o["ebit"] = v
        elif d.startswith("resultado financeiro"):
            o["resultado_financeiro"], rf_code = v, c
        elif "antes" in d and ("tributos" in d or "imposto" in d):
            o.setdefault("lair", v)
        elif "imposto de renda" in d or "tributos sobre o lucro" in d:
            o["ir"] = v
        elif "descontinuad" in d:
            o["descontinuadas"] = v
        elif (("lucro" in d or "prejuizo" in d) and ("do periodo" in d or "do exercicio" in d)
              and "antes" not in d and "continuad" not in d):
            o["lucro_liquido"], ll_code = v, c
    if ll_code:
        for c, d, v in _filhos(a, ll_code):
            if "controlador" in d and "nao control" not in d:
                o["lucro_controladora"] = v
    if rf_code:
        for c, d, v in _filhos(a, rf_code):
            if "receita" in d:
                o["receitas_financeiras"] = v
            elif "despesa" in d:
                o["despesas_financeiras"] = v
    return o


def _bpa(a):
    o = {"ativo_total": _v(a, "1")}
    d101 = (a.get("1.01") or ("", None))[0]
    if "circulante" in d101:
        o.update(layout="geral", ativo_circulante=_v(a, "1.01"), caixa=_v(a, "1.01.01", "caixa"),
                 aplicacoes=_v(a, "1.01.02", "aplica"), recebiveis=_v(a, "1.01.03", "receber"),
                 estoques=_v(a, "1.01.04", "estoque"), imobilizado=_v(a, "1.02.03", "imobilizado"),
                 intangivel=_v(a, "1.02.04", "intangive"))
    elif "caixa" in d101:  # instituições financeiras: balanço sem circulante
        o.update(layout="financeiro", caixa=_v(a, "1.01"))
    return o


def _bpp(a):
    o = {"passivo_total": _v(a, "2"),
         "passivo_circulante": _v(a, "2.01", "circulante", nao=("nao circulante",)),
         "passivo_nao_circulante": _v(a, "2.02", "nao circulante"),
         "emprestimos_cp": _v(a, "2.01.04", "emprestimo", "financiamento"),
         "emprestimos_lp": _v(a, "2.02.01", "emprestimo", "financiamento")}
    for c, d, v in _filhos(a, "2"):
        if "patrimonio liquido" in d:
            o["pl"] = v
            for _, d2, v2 in _filhos(a, c):
                if "nao control" in d2:
                    o["minoritarios"] = v2
                elif "controlador" in d2:
                    o["pl_controladora"] = v2
                elif "reservas de lucro" in d2:
                    o["reservas_lucros"] = v2
                elif "acumulad" in d2 and ("lucro" in d2 or "prejuizo" in d2):
                    o["lucros_acumulados"] = v2
    if o.get("pl") is not None and o.get("pl_controladora") is None:
        o["pl_controladora"] = o["pl"] - (o.get("minoritarios") or 0.0)
    return o


_DEP = ("deprecia", "amortiza", "exaust", "deplec")
_DEP_NAO = ("juros", "captac", "emprestimo", "financiamento", "debenture", "custo de transac",
            "custos de transac")
_CAPEX = ("imobilizad", "intangive", "ativo fixo", "ativos de contrato", "ativo de contrato", "infraestrutura")
_CAPEX_NAO = ("venda", "aliena", "recebimento", "baixa", "resgate")
_DIV = ("dividend", "juros sobre capital", "juros sobre o capital", "juros s/ capital", "juros s/capital",
        "jcp", "provento", "remuneracao aos acionistas", "remuneracao ao acionista")
_DIV_NAO = ("nao control", "nao-control", "minoritar", "recebid", "recebimento")
_EMISSAO = ("aumento de capital", "emissao de acoes", "integraliza", "subscricao", "oferta publica",
            "exercicio de opc", "acoes em tesouraria")
_EMISSAO_NAO = ("debenture", "nota comercial", "titulo", "bond", "emprestimo", "financiamento", "custo",
                "gasto", "nao control", "recompra", "aquisicao")


def _dfc(a):
    o = {"fco": _v(a, "6.01"), "fci": _v(a, "6.02"), "fcfin": _v(a, "6.03")}
    dep = [abs(v) for _, d, v in _filhos(a, "6.01.01")
           if any(k in d for k in _DEP) and not any(k in d for k in _DEP_NAO)]
    o["depreciacao"] = sum(dep) if dep else None
    capex = [-v for _, d, v in _filhos(a, "6.02")
             if v < 0 and any(k in d for k in _CAPEX) and not any(k in d for k in _CAPEX_NAO)]
    o["capex"] = sum(capex) if capex else None
    divs = [-v for _, d, v in _filhos(a, "6.03")
            if v < 0 and any(k in d for k in _DIV) and not any(k in d for k in _DIV_NAO)]
    o["dividendos_pagos"] = sum(divs) if divs else (0.0 if o["fcfin"] is not None else None)
    # entrada de caixa por emissão de ações (separa diluição real de bonificação/desdobramento)
    emis = [v for _, d, v in _filhos(a, "6.03")
            if v > 0 and any(k in d for k in _EMISSAO) and not any(k in d for k in _EMISSAO_NAO)]
    o["emissao_acoes"] = sum(emis) if emis else (0.0 if o["fcfin"] is not None else None)
    return o


_DERIVA = {"dre": _dre, "bpa": _bpa, "bpp": _bpp, "dfc": _dfc, "dfc_md": _dfc}


# ---------------------------------------------------------------------------
# Leitura dos zips DFP/ITR → estrutura por companhia
# ---------------------------------------------------------------------------
_ARQUIVOS = (("DRE", "dre"), ("BPA", "bpa"), ("BPP", "bpp"), ("DFC_MI", "dfc"), ("DFC_MD", "dfc_md"))
_COLS = ("CD_CVM", "CNPJ_CIA", "DENOM_CIA", "DT_REFER", "VERSAO", "ORDEM_EXERC", "DT_INI_EXERC",
         "DT_FIM_EXERC", "CD_CONTA", "DS_CONTA", "VL_CONTA", "ESCALA_MOEDA")
_COLS_ACOES = ("CNPJ_CIA", "DT_REFER", "VERSAO", "QT_ACAO_ORDIN_CAP_INTEGR", "QT_ACAO_PREF_CAP_INTEGR",
               "QT_ACAO_TOTAL_CAP_INTEGR", "QT_ACAO_ORDIN_TESOURO", "QT_ACAO_PREF_TESOURO",
               "QT_ACAO_TOTAL_TESOURO")


def _parse(zpath, prefix, ano):
    """Lê as demonstrações consolidadas; companhias sem consolidado usam as individuais."""
    z = zipfile.ZipFile(zpath)
    names = set(z.namelist())
    raw, cias, acoes = {}, {}, {}
    com_consolidado = set()
    for tipo in ("con", "ind"):
        for arq, grp in _ARQUIVOS:
            name = f"{prefix}_cia_aberta_{arq}_{tipo}_{ano}.csv"
            if name not in names:
                continue
            for cd, cnpj, nome, dt_refer, versao, ordem, dt_ini, dt_fim, conta, ds, vl, escala in _iter(z, name, _COLS):
                cd = cd.strip()
                if not cd.isdigit():
                    continue
                icd = int(cd)
                if tipo == "ind" and icd in com_consolidado:
                    continue
                conta = conta.strip()
                if not _keep(grp, conta):
                    continue
                val = _f(vl)
                if val is None:
                    continue
                if escala.strip().upper().startswith("MIL"):
                    val *= 1000.0
                o = "u" if norm(ordem).startswith("ult") else "p"
                contas = raw.setdefault((icd, dt_refer, o, dt_ini, dt_fim, grp), {})
                ver = int(versao) if versao.isdigit() else 0
                prev = contas.get(conta)
                if prev is None or ver >= prev[0]:
                    contas[conta] = (ver, norm(ds), val)
                if icd not in cias:
                    cias[icd] = (cnpj, nome.strip())
        if tipo == "con":
            com_consolidado = {k[0] for k in raw}
    name = f"{prefix}_cia_aberta_composicao_capital_{ano}.csv"
    if name in names:
        for cnpj, dt_refer, versao, on, pn, tot, ton, tpn, ttot in _iter(z, name, _COLS_ACOES):
            ver = int(versao) if versao.isdigit() else 0
            por_data = acoes.setdefault(cnpj, {})
            if dt_refer not in por_data or ver >= por_data[dt_refer]["versao"]:
                por_data[dt_refer] = {"dt_refer": dt_refer, "versao": ver, "on": _f(on), "pn": _f(pn),
                                      "total": _f(tot), "tes_on": _f(ton), "tes_pn": _f(tpn),
                                      "tes_total": _f(ttot)}
    z.close()
    return raw, cias, acoes


def _upd(dest, campos, grp):
    for k, v in campos.items():
        if v is None:
            continue
        if grp == "dfc_md":  # método direto só preenche lacunas do indireto
            dest.setdefault(k, v)
        else:
            dest[k] = v


def _blocos(raw):
    out = {}
    for (cd, dt_refer, o, dt_ini, dt_fim, grp), contas in raw.items():
        a = {c: (d, v) for c, (_, d, v) in contas.items()}
        out.setdefault(cd, {})[(dt_refer, o, dt_ini, dt_fim, grp)] = _DERIVA[grp](a)
    return out


def _acoes_por_cd(cias, acoes):
    cnpj_cd = {v[0]: cd for cd, v in cias.items()}
    out = {}
    for cnpj, por_data in acoes.items():
        cd = cnpj_cd.get(cnpj)
        if cd is not None:
            out[cd] = por_data
    return out


def _build_dfp(raw, cias, acoes):
    ac = _acoes_por_cd(cias, acoes)
    out = {}
    for cd, blocos in _blocos(raw).items():
        per = {"u": {}, "p": {}}
        for (dt_refer, o, dt_ini, dt_fim, grp), campos in blocos.items():
            alvo = per[o].setdefault(dt_fim, {"dt_fim": dt_fim})
            if dt_ini:
                alvo.setdefault("dt_ini", dt_ini)
            _upd(alvo, campos, grp)
        cnpj, nome = cias.get(cd, ("", ""))
        out[str(cd)] = {"cnpj": cnpj, "nome": nome, "u": per["u"], "p": per["p"], "acoes": ac.get(cd, {})}
    return out


def _build_itr(raw, cias, acoes):
    ac = _acoes_por_cd(cias, acoes)
    out = {}
    for cd, blocos in _blocos(raw).items():
        ult = max(k[0] for k in blocos)
        sel = {k: v for k, v in blocos.items() if k[0] == ult}
        cnpj, nome = cias.get(cd, ("", ""))
        rec = {"cnpj": cnpj, "nome": nome, "dt_refer": ult}
        for o, n_ytd, n_tri in (("u", "ytd", "tri"), ("p", "ytd_ant", "tri_ant")):
            dre = sorted({(k[2], k[3]) for k in sel if k[1] == o and k[4] == "dre"})
            if not dre:
                continue
            ytd = {"dt_ini": dre[0][0], "dt_fim": dre[0][1]}
            tri = {"dt_ini": dre[-1][0], "dt_fim": dre[-1][1]}
            for k, campos in sel.items():
                if k[1] != o:
                    continue
                if k[4] == "dre":
                    if (k[2], k[3]) == (ytd["dt_ini"], ytd["dt_fim"]):
                        _upd(ytd, campos, "dre")
                    if (k[2], k[3]) == (tri["dt_ini"], tri["dt_fim"]):
                        _upd(tri, campos, "dre")
                elif k[4] in ("dfc", "dfc_md") and k[3] == ytd["dt_fim"]:
                    _upd(ytd, campos, k[4])
            rec[n_ytd], rec[n_tri] = ytd, tri
        bal = {"dt_fim": ult}
        for k, campos in sel.items():
            if k[1] == "u" and k[4] in ("bpa", "bpp") and k[3] == ult:
                _upd(bal, campos, k[4])
        rec["bal"] = bal
        por_data = ac.get(cd) or {}
        if por_data:
            rec["acoes"] = por_data[max(por_data)]
        out[str(cd)] = rec
    return out


def _ttl_zip(ano):
    hoje = date.today().year
    if ano >= hoje:
        return 12 * 3600
    if ano == hoje - 1:
        return 3 * DIA
    return 30 * DIA


def _carregar(prefix, ano):
    url = f"{BASE}/DOC/{prefix.upper()}/DADOS/{prefix}_cia_aberta_{ano}.zip"
    zpath = os.path.join(DIR, f"{prefix}_{ano}.zip")
    try:
        download(url, zpath, ttl=_ttl_zip(ano))
    except Exception as e:
        log(f"CVM {prefix.upper()} {ano} indisponível: {e}")
        return {}
    jpath = os.path.join(DIR, f"{prefix}_{ano}.v{PARSER_VERSION}.json")
    if os.path.exists(jpath) and os.path.getmtime(jpath) >= os.path.getmtime(zpath):
        with open(jpath, encoding="utf-8") as f:
            return json.load(f)
    log(f"processando CVM {prefix.upper()} {ano} (feito uma vez; depois fica em cache) ...")
    raw, cias, acoes = _parse(zpath, prefix, ano)
    data = (_build_dfp if prefix == "dfp" else _build_itr)(raw, cias, acoes)
    with open(jpath + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(jpath + ".tmp", jpath)
    return data


_DS = None


def dataset():
    """Todos os DFP (últimos 5 exercícios + ano corrente) e ITR recentes, em memória."""
    global _DS
    if _DS is None:
        hoje = date.today()
        anos_dfp = range(hoje.year - 5, hoje.year + 1)
        anos_itr = [hoje.year] if hoje.month >= 6 else [hoje.year - 1, hoje.year]
        _DS = {"dfp": {a: _carregar("dfp", a) for a in anos_dfp},
               "itr": {a: _carregar("itr", a) for a in anos_itr}}
    return _DS


# ---------------------------------------------------------------------------
# Visão por companhia: histórico anual + TTM + último trimestre + ações
# ---------------------------------------------------------------------------
def _limpa(hist):
    """Remove exercícios 'placeholder' (DFP incompleta, ativo ~0)."""
    if len(hist) < 2:
        return hist
    mx = max(abs(v.get("ativo_total") or 0) for v in hist.values())
    return {dt: v for dt, v in hist.items() if not (mx > 0 and abs(v.get("ativo_total") or 0) < 0.01 * mx)}


def _circ(rec):
    if not rec or not rec.get("total"):
        return None
    return rec["total"] - (rec.get("tes_total") or 0.0)


def _ttm(hist, itr):
    ult = max(hist) if hist else None
    base = dict(hist[ult]) if ult else {}
    info = {"tipo": "anual", "ref": ult, "fonte": f"DFP {ult[:4]}" if ult else "—"}
    if not itr or (ult and itr["dt_refer"] <= ult):
        return base, info
    ytd, ant = itr.get("ytd"), itr.get("ytd_ant")
    anual = None
    if ytd and ytd.get("dt_ini"):
        fim_anterior = (date.fromisoformat(ytd["dt_ini"]) - timedelta(days=1)).isoformat()
        anual = hist.get(fim_anterior)
    out = {}
    if anual and ant:
        for k in FLUXOS:
            a, c, p = anual.get(k), ytd.get(k), ant.get(k)
            out[k] = a + c - p if None not in (a, c, p) else a
            if k in ("capex", "depreciacao", "dividendos_pagos", "emissao_acoes") and out[k] is not None:
                out[k] = max(0.0, out[k])  # fluxos que não podem ficar negativos no TTM
        info = {"tipo": "ttm", "ref": itr["dt_refer"],
                "fonte": f"DFP {anual['dt_fim'][:4]} + ITR {itr['dt_refer']} (12 meses)"}
    else:
        out = {k: base.get(k) for k in FLUXOS}
        info = {"tipo": "anual", "ref": itr["dt_refer"],
                "fonte": f"resultado DFP {ult[:4] if ult else '—'}; balanço ITR {itr['dt_refer']}"}
    bal = itr.get("bal") or {}
    for k in ESTOQUES:
        out[k] = bal.get(k) if bal.get(k) is not None else base.get(k)
    out["dt_fim"] = itr["dt_refer"]
    return out, info


def empresa(cd) -> dict | None:
    ds = dataset()
    k = str(int(cd))
    hist, acoes_hist = {}, {}
    nome = cnpj = None
    anos = sorted(ds["dfp"])
    for ano in anos:
        c = ds["dfp"][ano].get(k)
        if not c:
            continue
        nome, cnpj = c.get("nome") or nome, c.get("cnpj") or cnpj
        hist.update(c.get("u") or {})
        acoes_hist.update(c.get("acoes") or {})
    for ano in anos:
        for dt, campos in ((ds["dfp"][ano].get(k) or {}).get("p") or {}).items():
            hist.setdefault(dt, campos)
    hist = _limpa(hist)
    itr = None
    for ano in sorted(ds["itr"]):
        c = ds["itr"][ano].get(k)
        if c and (itr is None or c["dt_refer"] > itr["dt_refer"]):
            itr = c
    if not hist and not itr:
        return None
    if itr:
        nome, cnpj = nome or itr.get("nome"), cnpj or itr.get("cnpj")
    anual = {dt[:4]: hist[dt] for dt in sorted(hist)}
    ttm, info = _ttm(hist, itr)
    trimestre = None
    if itr and itr.get("tri") and (not hist or itr["dt_refer"] > max(hist)):
        trimestre = {"ref": itr["dt_refer"], "atual": itr.get("tri"), "ano_anterior": itr.get("tri_ant")}
    cands = list(acoes_hist.values()) + ([itr["acoes"]] if itr and itr.get("acoes") else [])
    acoes = max(cands, key=lambda r: r["dt_refer"]) if cands else None
    return {"cd_cvm": int(cd), "cnpj": cnpj, "nome": nome, "anual": anual, "ttm": ttm, "ttm_info": info,
            "trimestre": trimestre, "acoes": acoes,
            "acoes_hist": {dt[:4]: _circ(r) for dt, r in sorted(acoes_hist.items()) if _circ(r)}}


def empresas() -> list:
    """Códigos CVM de todas as companhias com demonstrações recentes."""
    ds = dataset()
    cds = set()
    for ano in sorted(ds["dfp"])[-3:]:
        cds.update(ds["dfp"][ano].keys())
    for ano in ds["itr"]:
        cds.update(ds["itr"][ano].keys())
    return sorted(int(c) for c in cds)


# ---------------------------------------------------------------------------
# FCA (tickers, governança) e cadastro
# ---------------------------------------------------------------------------
_FCA = None


def fca() -> dict:
    """{"tickers": {TICKER: {cd_cvm, classe, segmento}}, "cias": {cd: {...cadastro FCA...}}}"""
    global _FCA
    if _FCA is not None:
        return _FCA
    tickers, cias = {}, {}
    hoje = date.today().year
    for ano in (hoje - 1, hoje):
        zpath = os.path.join(DIR, f"fca_{ano}.zip")
        try:
            download(f"{BASE}/DOC/FCA/DADOS/fca_cia_aberta_{ano}.zip", zpath,
                     ttl=7 * DIA if ano == hoje else 30 * DIA)
            z = zipfile.ZipFile(zpath)
        except Exception as e:
            log(f"FCA {ano} indisponível: {e}")
            continue
        names = set(z.namelist())
        cnpj_cd = {}
        geral = f"fca_cia_aberta_geral_{ano}.csv"
        if geral in names:
            cols = ("CNPJ_Companhia", "Nome_Empresarial", "Codigo_CVM", "Setor_Atividade", "Situacao_Emissor",
                    "Especie_Controle_Acionario", "Mes_Encerramento_Exercicio_Social", "Pagina_Web")
            for cnpj, nome, cod, setor, sit, controle, mes, web in _iter(z, geral, cols):
                if not cod.strip().isdigit():
                    continue
                cd = str(int(cod))
                cnpj_cd[cnpj] = cd
                cias[cd] = {"cnpj": cnpj, "nome": nome.strip(), "setor": setor.strip(), "situacao": sit.strip(),
                            "controle": controle.strip(), "mes_exercicio": mes.strip(), "site": web.strip()}
        vm = f"fca_cia_aberta_valor_mobiliario_{ano}.csv"
        if vm in names:
            cols = ("CNPJ_Companhia", "Valor_Mobiliario", "Codigo_Negociacao", "Mercado", "Segmento",
                    "Data_Fim_Negociacao", "Composicao_BDR_Unit")
            for cnpj, tipo, cod, mercado, seg, fim, comp in _iter(z, vm, cols):
                t, tn = cod.strip().upper(), norm(tipo)
                if not t or "bolsa" not in norm(mercado) or not ("acoes" in tn or "unit" in tn):
                    continue
                if fim.strip():
                    tickers.pop(t, None)
                    continue
                cd = cnpj_cd.get(cnpj)
                if not cd:
                    continue
                # classe pelo sufixo do ticker (3=ON, 4/5/6=PN, 11=unit); o FCA às vezes erra o tipo
                sufixo = re.sub(r"^[A-Z]+", "", t)
                cl = {"3": "ON", "4": "PN", "5": "PN", "6": "PN", "7": "PN", "8": "PN", "11": "UNIT"}.get(sufixo)
                cl = cl or ("UNIT" if "unit" in tn else "PN" if "preferen" in tn else "ON")
                rec = {"cd_cvm": int(cd), "classe": cl, "segmento": seg.strip()}
                if cl == "UNIT":
                    n = sum(int(x) for x in re.findall(r"\d+", re.sub(r"[A-Z]{4}\d{1,2}", " ", comp.upper())))
                    rec["acoes_por_unit"] = n or None
                tickers[t] = rec
        z.close()
    _FCA = {"tickers": tickers, "cias": cias}
    return _FCA


_CAD = None


def cadastro() -> dict:
    """Cadastro CVM: {cd: {denom_social, denom_comerc, setor, situacao}}."""
    global _CAD
    if _CAD is None:
        path = download(f"{BASE}/CAD/DADOS/cad_cia_aberta.csv", os.path.join(DIR, "cad_cia_aberta.csv"),
                        ttl=7 * DIA)
        _CAD = {}
        with open(path, encoding="latin-1", newline="") as f:
            for r in csv.DictReader(f, delimiter=";"):
                cod = (r.get("CD_CVM") or "").strip()
                if cod.isdigit():
                    _CAD[str(int(cod))] = {"denom_social": (r.get("DENOM_SOCIAL") or "").strip(),
                                           "denom_comerc": (r.get("DENOM_COMERC") or "").strip(),
                                           "setor": (r.get("SETOR_ATIV") or "").strip(),
                                           "situacao": (r.get("SIT") or "").strip()}
    return _CAD


def _norm_nome(s):
    s = norm(s).upper()
    for tok in ("S.A.", "S/A", "COMPANHIA", "COMPANY"):
        s = s.replace(tok, " ")
    s = re.sub(r"\b(S\s*A|PFD|PN|PNA|PNB|EDR|UNT|ED|NM|CIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def resolve(ticker, nome=None):
    """Ticker → (CD_CVM, motivo). Ordem: FCA oficial → overrides → nome da empresa."""
    t = (ticker or "").strip().upper()
    if t.endswith("F") and len(t) >= 6 and t[-2].isdigit():
        t = t[:-1]  # mercado fracionário (PETR4F → PETR4)
    info = fca()["tickers"].get(t)
    if info:
        return info["cd_cvm"], "fca"
    if t in OVERRIDES:
        return OVERRIDES[t], "override"
    q = _norm_nome(nome or "")
    if q:
        ativos = [(cd, r) for cd, r in cadastro().items() if r["situacao"].upper() == "ATIVO"]
        for cd, r in ativos:
            if _norm_nome(r["denom_social"]) == q:
                return int(cd), "nome_exato"
        cands = [(cd, r) for cd, r in ativos
                 if (dn := _norm_nome(r["denom_social"])) and (dn.startswith(q) or q.startswith(dn))]
        if cands:
            cands.sort(key=lambda x: len(x[1]["denom_social"]))
            return int(cands[0][0]), "nome_prefixo"
    return None, "nao_encontrado"


def tickers_da_empresa(cd) -> dict:
    """{ticker: classe} de todas as classes listadas da companhia."""
    return {t: i["classe"] for t, i in fca()["tickers"].items() if i["cd_cvm"] == int(cd)}


def governanca(cd, ticker=None) -> dict:
    f = fca()
    c = f["cias"].get(str(int(cd))) or {}
    cad = cadastro().get(str(int(cd))) or {}
    t = f["tickers"].get((ticker or "").upper()) or {}
    return {"segmento_listagem": t.get("segmento") or None, "classe": t.get("classe"),
            "controle": c.get("controle") or None, "situacao_emissor": c.get("situacao") or None,
            "setor_cvm": c.get("setor") or cad.get("setor") or None, "site_ri": c.get("site") or None}


def setor_cvm(cd) -> str:
    c = fca()["cias"].get(str(int(cd))) or {}
    return c.get("setor") or (cadastro().get(str(int(cd))) or {}).get("setor") or ""


def nome_comercial(cd) -> str:
    """Nome comercial (marca) — ideal para casar manchetes (ex.: 'PETROBRAS')."""
    r = cadastro().get(str(int(cd))) or {}
    return r.get("denom_comerc") or r.get("denom_social") or ""


# ---------------------------------------------------------------------------
# IPE — fatos relevantes, comunicados, resultados e proventos
# ---------------------------------------------------------------------------
def eventos(cd, meses=3) -> list:
    from seguranca import limpar, link_seguro  # assuntos são escritos pelas companhias: texto de terceiros
    hoje = datetime.now()
    corte = hoje - timedelta(days=meses * 30)
    cod = str(int(cd))
    out = []
    for ano in sorted({hoje.year, corte.year}):
        try:
            path = download(f"{BASE}/DOC/IPE/DADOS/ipe_cia_aberta_{ano}.zip",
                            os.path.join(DIR, f"ipe_{ano}.zip"), ttl=6 * 3600)
            z = zipfile.ZipFile(path)
            cols = ("Codigo_CVM", "Categoria", "Tipo", "Assunto", "Data_Referencia", "Data_Entrega", "Link_Download")
            for cv, cat, tipo, assunto, dref, dent, link in _iter(z, f"ipe_cia_aberta_{ano}.csv", cols):
                if cv.strip().lstrip("0") != cod or cat.strip() not in IPE_CATEGORIAS:
                    continue
                data = (dent or dref).strip()[:10]
                try:
                    dt = datetime.strptime(data, "%Y-%m-%d")
                except ValueError:
                    continue
                if dt < corte:
                    continue
                out.append({"data": data, "categoria": cat.strip(), "tipo": limpar(tipo, 120),
                            "assunto": limpar(assunto, 300) or cat.strip(), "link": link_seguro(link)})
            z.close()
        except Exception as e:
            log(f"IPE {ano}: {e}")
    out.sort(key=lambda x: x["data"], reverse=True)
    return out


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "WEGE3"
    cd, motivo = resolve(tk)
    print(f"{tk} → CD_CVM {cd} ({motivo})")
    e = empresa(cd) if cd else None
    if e:
        print(e["nome"], "|", e["ttm_info"])
        for k in ("receita", "ebit", "lucro_liquido", "lucro_controladora", "pl_controladora", "fco", "capex",
                  "dividendos_pagos", "caixa", "aplicacoes", "emprestimos_cp", "emprestimos_lp", "layout"):
            v = e["ttm"].get(k)
            print(f"  {k:20} {v/1e9:10.2f} bi" if isinstance(v, float) else f"  {k:20} {v}")
        print("  anos:", list(e["anual"]), "| ações:", e["acoes"])
        print("  governança:", governanca(cd, tk))
