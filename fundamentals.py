"""Fundamentos via yfinance (gratuito, cobre a B3 com sufixo .SA).

Converte os DataFrames do yfinance para o formato de "entries" (lista de
dicts por ano, mais recente primeiro) que o analysis.py consome.

Nota: EPS, beta e dividendYield do Yahoo vêm com escala inconsistente para
B3 — por isso NÃO confiamos neles; o analysis.py computa EPS (lucro/ações),
DY (dividendos/preço) e payout (dividendo pago/lucro) a partir de valores
brutos (lucro, nº de ações, dividendo pago), que são confiáveis.
"""
from __future__ import annotations

import pandas as pd
import yfinance as yf

# Yahoo Finance (linha do DataFrame) -> campo interno do analysis.py
INCOME_MAP = {
    "Total Revenue": "totalRevenue",
    "Gross Profit": "grossProfit",
    "Operating Income": "operatingIncome",
    "EBITDA": "ebitda",
    "EBIT": "ebit",
    "Net Income": "netIncome",
    "Interest Expense": "interestExpense",
    "Pretax Income": "incomeBeforeTax",
    "Tax Provision": "incomeTaxExpense",
    "Diluted Average Shares": "dilutedAverageShares",
    "Basic Average Shares": "basicAverageShares",
}

BALANCE_MAP = {
    "Stockholders Equity": "totalStockholderEquity",
    "Total Assets": "totalAssets",
    "Cash And Cash Equivalents": "cash",
    "Total Debt": "totalDebt",
    "Long Term Debt": "longTermDebt",
    "Accounts Receivable": "netReceivables",
    "Inventory": "inventory",
    "Current Assets": "totalCurrentAssets",
    "Current Liabilities": "totalCurrentLiabilities",
    "Total Liabilities Net Minority Interest": "totalLiab",
}

CASHFLOW_MAP = {
    "Free Cash Flow": "freeCashFlow",
    "Operating Cash Flow": "operatingCashFlow",
    "Capital Expenditure": "capitalExpenditure",
    "Investing Cash Flow": "investmentCashFlow",
    "Financing Cash Flow": "financingCashFlow",
    "Cash Dividends Paid": "cashDividendsPaid",
    "Common Stock Dividend Paid": "commonDividendPaid",
}


def _entries(df, mapping):
    """DataFrame (linhas=itens, colunas=anos) -> lista de dicts (novo->antigo)."""
    if df is None or df.empty:
        return []
    entries = []
    for col in df.columns:
        e = {"endDate": str(col.date()), "type": "yearly"}
        for yahoo_name, my_name in mapping.items():
            if yahoo_name in df.index:
                v = df.loc[yahoo_name, col]
                if v is not None and pd.notna(v):
                    try:
                        e[my_name] = float(v)
                    except (TypeError, ValueError):
                        pass
        entries.append(e)
    return entries


def _dividends_12m(t) -> float | None:
    """Dividendos por ação nos últimos 12 meses (soma)."""
    try:
        d = t.dividends
        if d is None or len(d) == 0:
            return None
        cutoff = d.index[-1] - pd.Timedelta(days=365)
        recent = d[d.index >= cutoff]
        return float(recent.sum()) if len(recent) else 0.0
    except Exception:
        return None


def fetch_yf(symbol: str) -> dict:
    """Busca fundamentos de um ticker B3 (ex.: 'WEGE3') via yfinance."""
    t = yf.Ticker(symbol.strip().upper() + ".SA")

    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    return {
        "info": info,
        "income_statement": _entries(t.income_stmt, INCOME_MAP),
        "balance_sheet": _entries(t.balance_sheet, BALANCE_MAP),
        "cash_flow": _entries(t.cashflow, CASHFLOW_MAP),
        "dividends_12m": _dividends_12m(t),
    }


if __name__ == "__main__":
    import sys
    sym = sys.argv[1] if len(sys.argv) > 1 else "WEGE3"
    d = fetch_yf(sym)
    inc = d["income_statement"]
    print("info beta:", d["info"].get("beta"), "| DY_info:", d["info"].get("dividendYield"))
    print("anos:", [e["endDate"] for e in inc])
    print("2025:", {k: (round(v) if k != "dilutedAverageShares" else v) for k, v in inc[0].items() if k not in ("endDate", "type")})
    print("dividends_12m:", d["dividends_12m"])
