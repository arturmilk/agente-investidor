"""Parser da CVM (dados abertos) — fonte primária/ouro do guia.

Busca fundamentos anuais (DFP) oficiais de qualquer companhia aberta da B3,
corrigindo as imprecisões do yfinance (bancos, Petrobras, empresas com ADR).

Fluxo ticker → dados:
  1. nome da empresa (perfil brapi) → CD_CVM (cadastro CVM, match normalizado);
  2. para cada ano (DFP), baixa o zip (com cache) e extrai as contas-chave.

Custo: ~13 MB/ano, baixado UMA vez e reaproveitado para todos os tickers
(cada zip contém todas as companhias). CD_CVM é zero-padded a 6 dígitos;
VL_CONTA está na escala "MIL" (×1000).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sys
import time
import unicodedata
import urllib.request
import zipfile

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cvm_cache")
os.makedirs(CACHE, exist_ok=True)

BASE = "https://dados.cvm.gov.br/dados/CIA_ABERTA"
CADASTRO_URL = f"{BASE}/CAD/DADOS/cad_cia_aberta.csv"

# Contas extraídas por demonstração: (código CD_CONTA, palavra-chave de descrição).
# A palavra-chave resolve códigos que mudam por setor (PL de banco é 2.07, não 2.03).
DRE_CONTA = {"receita": ("3.01", None), "lucro_bruto": ("3.03", None), "ebit": ("3.05", None), "lucro_liquido": ("3.11", "consolidado do periodo")}
BPA_CONTA = {"ativo_total": ("1", None), "caixa": ("1.01.01", None)}
BPP_CONTA = {"patrimonio_liquido": (None, "patrimonio liquido"), "divida_cp": ("2.01.04", None), "divida_lp": ("2.02.01", None)}
DFC_CONTA = {"fco": ("6.01", None), "fci": ("6.02", None), "depreciacao": ("6.01.01.04", "depreciacao")}

# Overrides determinísticos ticker → CD_CVM (para casos em que o match falha)
OVERRIDES = {
    "PETR4": 9512, "PETR3": 9512,
    "WEGE3": 5410,
    "BBAS3": 1023,
    "EGIE3": 17329,
    "RENT3": 19739,
    "MGLU3": 22470,
}

YEARS = [2021, 2022, 2023, 2024, 2025]


def _log(msg):
    print(f"[cvm] {msg}", file=sys.stderr)


def _download(url, cache_name):
    path = os.path.join(CACHE, cache_name)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    _log(f"baixando {cache_name} ...")
    tmp = path + ".part"
    urllib.request.urlretrieve(url, tmp)
    os.replace(tmp, path)
    return path


def normalize(s):
    s = unicodedata.normalize("NFKD", s or "")
    s = s.encode("ascii", "ignore").decode("ascii").upper()
    for tok in ("S.A.", "S/A", "COMPANHIA", "COMPANY"):
        s = s.replace(tok, " ")
    s = re.sub(r"\b(S\s*A|PFD|PN|PNA|PNB|EDR|UNT|ED|NM|CIA)\b", " ", s)
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def get_cadastro():
    path = _download(CADASTRO_URL, "cad_cia_aberta.csv")
    with open(path, encoding="latin-1") as f:
        return list(csv.DictReader(f, delimiter=";"))


def find_cd_cvm(company_name, ticker):
    """Retorna (CD_CVM, motivo) para um nome de empresa e ticker."""
    ticker = (ticker or "").upper()
    if ticker in OVERRIDES:
        return OVERRIDES[ticker], "override"

    q = normalize(company_name)
    if not q:
        return None, "sem_nome"

    cad = get_cadastro()
    ativos = [r for r in cad if (r.get("SIT") or "").strip() == "ATIVO"]

    # 1. match exato normalizado
    for r in ativos:
        if normalize(r["DENOM_SOCIAL"]) == q:
            return int(r["CD_CVM"]), "exato"

    # 2. prefixo (query é prefixo do nome normalizado, ou vice-versa)
    cands = []
    for r in ativos:
        dn = normalize(r["DENOM_SOCIAL"])
        if dn and (dn.startswith(q) or q.startswith(dn)):
            cands.append(r)
    if cands:
        cands.sort(key=lambda r: len(normalize(r["DENOM_SOCIAL"])))
        return int(cands[0]["CD_CVM"]), "prefixo"

    return None, "nao_encontrado"


def _escala_factor(escala):
    return 1000.0 if (escala or "").strip().upper() == "MIL" else 1.0


def get_dfp_series(cd_cvm, years=None):
    """Extrai as contas-chave anuais de uma companhia (por CD_CVM).

    Retorna {ano: {conta: valor}}.
    """
    years = years or YEARS
    cd = f"{int(cd_cvm):06d}"
    result = {}

    # cache em disco (24h): evita re-ler os zips a cada análise
    cache_file = os.path.join(CACHE, f"cvm_{int(cd_cvm)}.json")
    if os.path.exists(cache_file) and (time.time() - os.path.getmtime(cache_file)) < 86400:
        with open(cache_file, encoding="utf-8") as f:
            cached = json.load(f)
        return {int(k): v for k, v in cached.items()}

    for y in years:
        url = f"{BASE}/DOC/DFP/DADOS/dfp_cia_aberta_{y}.zip"
        try:
            path = _download(url, f"dfp_{y}.zip")
            z = zipfile.ZipFile(path)
        except Exception as e:
            _log(f"ano {y}: {e}")
            continue

        def extract(fname, contas, use_ordem=True):
            if fname not in z.namelist():
                return {}
            rows = csv.DictReader(io.StringIO(z.read(fname).decode("latin-1")), delimiter=";")
            best = {}  # key -> (versao, valor)
            for r in rows:
                if r["CD_CVM"].strip() != cd:
                    continue
                if use_ordem and (r.get("ORDEM_EXERC") or "").strip() != "ÚLTIMO":
                    continue
                cd_conta = (r.get("CD_CONTA") or "").strip()
                ds_norm = normalize(r.get("DS_CONTA") or "").lower()
                for key, (code, desc_kw) in contas.items():
                    if cd_conta == code or (desc_kw and desc_kw in ds_norm):
                        try:
                            vl = float(r["VL_CONTA"])
                        except ValueError:
                            continue
                        ver = int(r.get("VERSAO") or "0")
                        vl = vl * _escala_factor(r.get("ESCALA_MOEDA"))
                        if key not in best or ver > best[key][0]:
                            best[key] = (ver, vl)
                        break
            return {k: v[1] for k, v in best.items()}

        dre = extract(f"dfp_cia_aberta_DRE_con_{y}.csv", DRE_CONTA)
        bpa = extract(f"dfp_cia_aberta_BPA_con_{y}.csv", BPA_CONTA)
        bpp = extract(f"dfp_cia_aberta_BPP_con_{y}.csv", BPP_CONTA)
        dfc = extract(f"dfp_cia_aberta_DFC_MI_con_{y}.csv", DFC_CONTA)

        merged = {**dre, **bpa, **bpp, **dfc}
        # dívida total = CP + LP
        if "divida_cp" in bpp or "divida_lp" in bpp:
            cp = bpp.get("divida_cp", 0.0) or 0.0
            lp = bpp.get("divida_lp", 0.0) or 0.0
            merged["divida_total"] = cp + lp

        # EBITDA = EBIT + depreciação/amortização (ambos da CVM)
        if "ebit" in dre and "depreciacao" in dfc:
            merged["ebitda"] = dre["ebit"] + dfc["depreciacao"]

        if merged:
            result[y] = merged

    # Remove anos "placeholder" (DFP incompleta): receita ou ativo anômalo ~0
    if len(result) >= 2:
        max_ativo = max((abs(v.get("ativo_total") or 0)) for v in result.values())
        max_receita = max((abs(v.get("receita") or 0)) for v in result.values())
        for y in list(result.keys()):
            ativo = abs(result[y].get("ativo_total") or 0)
            rec = abs(result[y].get("receita") or 0)
            if (max_ativo > 0 and ativo < 0.01 * max_ativo) or (max_receita > 0 and rec < 0.01 * max_receita):
                del result[y]

    # grava cache (anos como string para JSON)
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({str(k): v for k, v in result.items()}, f)

    return result


def get_fundamentals(ticker, company_name):
    """Orquestra: ticker + nome → CD_CVM → séries anuais CVM.

    Retorna {"cd_cvm", "match", "series"} onde series é {conta: {ano: valor}}.
    """
    cd_cvm, motivo = find_cd_cvm(company_name, ticker)
    if cd_cvm is None:
        return {"cd_cvm": None, "match": motivo, "series": {}}

    anos = get_dfp_series(cd_cvm)
    if not anos:
        return {"cd_cvm": cd_cvm, "match": motivo, "series": {}}

    # transpor {ano: {conta: valor}} → {conta: {ano: valor}}
    series = {}
    for ano, contas in anos.items():
        for conta, valor in contas.items():
            series.setdefault(conta, {})[ano] = valor

    return {"cd_cvm": cd_cvm, "match": motivo, "series": series}


if __name__ == "__main__":
    import json
    ticker = sys.argv[1] if len(sys.argv) > 1 else "PETR4"
    nome = sys.argv[2] if len(sys.argv) > 2 else ""
    d = get_fundamentals(ticker, nome)
    print("cd_cvm:", d["cd_cvm"], "| match:", d["match"])
    for conta, anos in d["series"].items():
        vals = {a: round(v / 1e9, 1) for a, v in sorted(anos.items())}
        print(f"  {conta:18} (R$ bi): {vals}")
