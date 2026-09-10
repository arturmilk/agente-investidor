"""Orquestrador do Agente Bolsa.

Uso:
    python analyze.py PETR4 VALE3 ITUB4 [--horizonte 6m] [--out resultados.json] [--noticias]

Coleta dados, calcula métricas, score determinístico e red flags,
e grava um JSON + imprime um resumo em markdown.
A análise qualitativa (qualidade, risco, tese, ranking final) é feita
pela camada de raciocínio sobre esse JSON.
"""
import argparse
import json
import sys
import traceback

import brapi
from analysis import build_metrics, deterministic_score, red_flags
from config import DEFAULT_TICKERS


def analyze_symbols(symbols, with_news=False):
    results = []
    errors = []
    for s in symbols:
        try:
            raw = brapi.fetch_ticker(s)
            m = build_metrics(raw)
            score = deterministic_score(m)
            flags = red_flags(m)
            entry = {
                "metricas": m,
                "score_deterministico": score,
                "red_flags": flags,
            }
            if with_news:
                kws = [s]
                nome = m.get("nome") or ""
                if nome:
                    kws.append(nome.split(" ")[0])
                entry["noticias"] = _load_news(kws)
            results.append(entry)
            print(f"[ok] {s}: score determinístico {score['total_deterministico']}/70", file=sys.stderr)
        except Exception as e:
            msg = f"{s}: {e}"
            errors.append(msg)
            print(f"[erro] {msg}", file=sys.stderr)
    return results, errors


def _load_news(keywords):
    try:
        import news
        return news.search_news(keywords)
    except Exception:
        return []


def _load_macro():
    try:
        import macro
        return macro.snapshot()
    except Exception:
        return {}


def fmt_pct(x, nd=1):
    return f"{x*100:.{nd}f}%" if x is not None else "—"


def _x(x, nd=1, suffix="x"):
    return f"{x:.{nd}f}{suffix}" if x is not None else "—"


def markdown_summary(results):
    lines = ["# Resumo quantitativo (score determinístico — máximo 70 pts)\n"]
    header = ("| Ticker | Empresa | Setor | P/L | P/VP | EV/EBITDA | PEG | DY | ROE | "
              "Marg.Líq | Dív.Líq/EBITDA | Score /70 |")
    sep = "|---|---|---|---|---|---|---|---|---|---|---|---|"
    lines += [header, sep]

    for r in results:
        m = r["metricas"]
        sc = r["score_deterministico"]
        lines.append(
            f"| {m['symbol']} | {m['nome']} | {m['setor'] or '—'} | {_x(m['pe'])} | {_x(m['pvp'])} | "
            f"{_x(m['ev_ebitda'])} | {_x(m['peg'], 2)} | {fmt_pct(m['dy'], 0)} | {fmt_pct(m['roe'], 0)} | "
            f"{fmt_pct(m['margem_liquida'], 0)} | {_x(m['divida_liquida_ebitda'])} | "
            f"**{sc['total_deterministico']}** |"
        )

    lines.append("")
    lines.append("## Detalhe por ativo\n")
    for r in results:
        m = r["metricas"]
        sc = r["score_deterministico"]
        lines.append(f"### {m['symbol']} — {m['nome']}")
        lines.append(f"- **Setor**: {m['setor'] or '—'} | **Indústria**: {m['industria'] or '—'}")
        preco = f"R$ {m['preco']:.2f}" if m["preco"] is not None else "—"
        lines.append(f"- **Preço**: {preco} | **Mkt cap**: {_fmt_money(m['market_cap'])} | **Beta**: {_x(m['beta'], 2)}")
        lines.append(
            f"- **CAGR (histórico)**: receita {fmt_pct(m['cagr_receita'])}, lucro {fmt_pct(m['cagr_lucro'])}, "
            f"EPS {fmt_pct(m['cagr_eps'])}, FCF {fmt_pct(m['cagr_fcf'])}"
        )
        lines.append(
            f"- **Rentabilidade**: ROE {fmt_pct(m['roe'])}, ROA {fmt_pct(m['roa'])}; margens bruta "
            f"{fmt_pct(m['margem_bruta'])}, EBITDA {fmt_pct(m['margem_ebitda'])}, líquida "
            f"{fmt_pct(m['margem_liquida'])} (tendência {m['tendencia_margem_liquida']})"
        )
        lines.append(
            f"- **Balanço**: dívida líquida/EBITDA {_x(m['divida_liquida_ebitda'])}, "
            f"dívida/PL {_x(m['divida_equity'])}, liquidez corrente {_x(m['liquidez_corrente'])}, "
            f"cobertura de juros {_x(m['cobertura_juros'])}"
        )
        lines.append(
            f"- **Valuation**: P/L {_x(m['pe'])}, P/VP {_x(m['pvp'])}, EV/EBITDA {_x(m['ev_ebitda'])}, "
            f"P/FCF {_x(m['pfcf'])}, PEG {_x(m['peg'], 2)}, DY {fmt_pct(m['dy'], 0)}, "
            f"payout estimado {fmt_pct(m['payout_est'], 0)}"
        )
        if m["preco_alvo_medio"]:
            lines.append(f"- **Preço-alvo (consenso)**: R$ {m['preco_alvo_medio']:.2f} (upside {fmt_pct(m['upside'])})")
        if r["red_flags"]:
            lines.append("- **Red flags**: " + "; ".join(f"{f['flag']} [{f['severidade']}]" for f in r["red_flags"]))
        else:
            lines.append("- **Red flags**: nenhuma detectada")
        lines.append("")
    return "\n".join(lines)


def _fmt_money(x):
    if x is None:
        return "—"
    if abs(x) >= 1e12:
        return f"R$ {x/1e12:.2f} tri"
    if abs(x) >= 1e9:
        return f"R$ {x/1e9:.2f} bi"
    if abs(x) >= 1e6:
        return f"R$ {x/1e6:.1f} mi"
    return f"R$ {x:,.2f}"


def main():
    ap = argparse.ArgumentParser(description="Agente Bolsa — análise fundamentalista B3")
    ap.add_argument("tickers", nargs="*", help="Tickers (ex.: PETR4 VALE3). Vazio = universo padrão.")
    ap.add_argument("--horizonte", default="6m", help="Prazo de análise (ex.: 3m, 6m, 12m)")
    ap.add_argument("--out", default=None, help="Caminho do JSON de saída")
    ap.add_argument("--noticias", action="store_true", help="Buscar notícias relacionadas")
    ap.add_argument("--no-summary", action="store_true", help="Não imprimir resumo markdown")
    args = ap.parse_args()

    symbols = args.tickers or DEFAULT_TICKERS
    results, errors = analyze_symbols(symbols, with_news=args.noticias)

    payload = {
        "horizonte": args.horizonte,
        "macro": _load_macro(),
        "ativos": results,
        "erros": errors,
    }

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
        print(f"[gravado] {args.out}", file=sys.stderr)

    if not args.no_summary:
        print(markdown_summary(results))

    if not results:
        print("Nenhum ativo analisado com sucesso.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
