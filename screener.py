"""Screener — funil etapas 1–3 do guia.

Etapa 1–2: universo B3 → ações ativas → filtro de liquidez (market cap + volume).
Etapa 3 (--deep): para as sobreviventes (top N por valor de mercado), roda o mesmo
pipeline da análise completa (yfinance + build_metrics) e ranqueia pelo score
determinístico (0–70) + red flags.

Uso:
    python screener.py                    # lista ações líquidas + CSV
    python screener.py --deep --top 40    # ranqueia top 40 por score determinístico
"""
import argparse
import json
import sys

import brapi
from analysis import build_metrics, deterministic_score, red_flags
from config import MIN_VOLUME_FINANCEIRO


def list_active_stocks():
    """Pagina /tickers e devolve todas as ações ativas da B3."""
    stocks = []
    page = 1
    while True:
        d = brapi._get("/tickers", {"limit": 1000, "page": page})
        for x in d.get("results", []):
            if x.get("assetType") == "stock" and x.get("isActive"):
                stocks.append(x)
        if not d.get("pagination", {}).get("hasNextPage"):
            break
        page += 1
    return stocks


def with_liquidity(stocks, min_mc=1e9):
    out = []
    for s in stocks:
        q = s.get("quote") or {}
        mc = q.get("marketCap") or 0
        px = q.get("lastPrice") or 0
        vol = q.get("volume") or 0
        if mc >= min_mc and px * vol >= MIN_VOLUME_FINANCEIRO:
            out.append({
                "symbol": s["symbol"],
                "nome": s.get("longName") or s.get("name"),
                "setor": s.get("sector"),
                "subsector": s.get("subsector"),
                "market_cap": mc,
                "preco": px,
                "vol_fin_dia": px * vol,
            })
    out.sort(key=lambda x: -x["market_cap"])
    return out


def deep_rank(candidates):
    ranked = []
    for i, c in enumerate(candidates, 1):
        try:
            raw = brapi.fetch_ticker(c["symbol"])
            m = build_metrics(raw)
            sc = deterministic_score(m)
            flags = red_flags(m)
            ranked.append({
                **c,
                "score_screen": sc["total_deterministico"],
                "pe": m["pe"],
                "roe": m["roe"],
                "margem_liquida": m["margem_liquida"],
                "cresc_lucro": m["cresc_lucro"],
                "divida_liquida_ebitda": m["divida_liquida_ebitda"],
                "red_flags": [f["flag"] for f in flags],
            })
            print(f"[{i}/{len(candidates)}] {c['symbol']}: {sc['total_deterministico']}/70", file=sys.stderr)
        except Exception as e:
            print(f"[{i}/{len(candidates)}] {c['symbol']}: erro {e}", file=sys.stderr)
    ranked.sort(key=lambda x: -x["score_screen"])
    return ranked


def main():
    ap = argparse.ArgumentParser(description="Screener B3 — funil etapas 1–3")
    ap.add_argument("--deep", action="store_true", help="Ranquear por score determinístico (0–70)")
    ap.add_argument("--top", type=int, default=30, help="Nº de candidatas a analisar no --deep")
    ap.add_argument("--min-mc", type=float, default=1e9, help="Market cap mínimo (R$)")
    ap.add_argument("--out", default="screener.json", help="Saída JSON")
    args = ap.parse_args()

    stocks = list_active_stocks()
    liq = with_liquidity(stocks, min_mc=args.min_mc)
    print(f"Universo: {len(stocks)} ações ativas → {len(liq)} líquidas (mc≥R${args.min_mc/1e6:.0f}mi)",
          file=sys.stderr)

    if args.deep:
        ranked = deep_rank(liq[: args.top])
        payload = {"screener": ranked}
    else:
        payload = {"screener": liq}

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)

    print("\n# Screener B3\n")
    if args.deep:
        print("| # | Ticker | Empresa | Setor | Score | P/L | ROE | Marg.Líq | Dív.Líq/EBITDA | Flags |")
        print("|--:|--------|---------|-------|------:|----:|----:|---------:|---------------:|------:|")
        for i, r in enumerate(payload["screener"], 1):
            nf = len(r.get("red_flags", []))
            flags = f"{nf} flag(s)" if nf else "—"
            print(f"| {i} | {r['symbol']} | {r['nome'][:24]} | {r['setor'] or '—'} | **{r['score_screen']}** | "
                  f"{_x(r['pe'])} | {_pct(r['roe'])} | {_pct(r['margem_liquida'])} | "
                  f"{_x(r['divida_liquida_ebitda'])} | {flags} |")
    else:
        print("| # | Ticker | Empresa | Setor | Market Cap | Vol. R$/dia |")
        print("|--:|--------|---------|-------|-----------:|------------:|")
        for i, r in enumerate(payload["screener"], 1):
            print(f"| {i} | {r['symbol']} | {r['nome'][:28]} | {r['setor'] or '—'} | "
                  f"R$ {r['market_cap']/1e9:.1f} bi | R$ {r['vol_fin_dia']/1e6:.1f} mi |")
    print(f"\n[gravado] {args.out}")


def _x(x, nd=1):
    return f"{x:.{nd}f}x" if x is not None else "—"


def _pct(x):
    return f"{x*100:.0f}%" if x is not None else "—"


if __name__ == "__main__":
    main()
