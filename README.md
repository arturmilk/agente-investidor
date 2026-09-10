# Agente Bolsa — Análise Fundamentalista de Ações da B3

Agente de IA para **apoio à decisão** em investimentos na bolsa brasileira (B3), focado em
médio prazo (semanas a meses). Coleta dados reais, pontua cada ativo de 0 a 100 e entrega
ranking + tese + riscos, seguindo um método de análise fundamentalista destilado do guia do
usuário.

> ⚠️ **Disclaimer**: ferramenta de análise e apoio à decisão, baseada em dados públicos.
> Não é recomendação personalizada de investimento e não substitui consultor de valores
> mobiliários credenciado (CVM/Anbima).

## Estrutura

```
agente-bolsa/
├── SKILL.md          # Metodologia completa (score, critérios, formato do relatório)
├── config.py         # Pesos do score, tickers padrão, feeds de notícias, token
├── brapi.py          # Cliente da API brapi.dev v2 (dados da B3)
├── analysis.py       # Métricas derivadas + score determinístico (70 pts) + red flags
├── news.py           # Monitor de notícias (RSS: InfoMoney, Valor, Brazil Journal, Money Times)
├── analyze.py        # Orquestrador CLI (coleta → análise → JSON + resumo markdown)
├── resultados.json   # Saída de exemplo
└── .cache/           # Cache local das chamadas (30 min TTL)
```

## Requisitos

- Python 3.11+ com `requests`, `yfinance` e `pandas` (instalar com `python -m pip install yfinance`).
- Token gratuito do [brapi.dev](https://brapi.dev/dashboard) — necessário para cotação/perfil/
  lista de tickers de qualquer ativo. Salve a chave em `agente-bolsa.token` (uma linha).
- Fundamentos (DRE/balanço/DFC) vêm do **yfinance**, que é gratuito e não precisa de token.

## Uso

```bash
# 1. (uma vez) Defina o token gratuito — necessário para tickers fora dos 4 de demonstração
export BRAPI_TOKEN="sua-chave"        # ou: salve a chave em agente-bolsa.token

# 2. Analisar tickers específicos
cd C:\Users\usuario\agente-bolsa
python analyze.py PETR4 VALE3 WEGE3 --out resultados.json

# 3. Com notícias relacionadas
python analyze.py PETR4 VALE3 --noticias

# 4. Universo padrão (config.py)
python analyze.py
```

A saída contém:
- **score determinístico (0–70)** — crescimento, rentabilidade, balanço e valuation;
- **métricas completas** — múltiplos, margens, CAGRs, dívida, caixa, histórico;
- **red flags** — sinais de alerta do guia (receita sobe mas caixa não, payout > 100%, etc.).

A parte **qualitativa (0–30)** — qualidade/moat e risco — e a **tese/ranking final** são feitas
pela camada de raciocínio (o LLM), seguindo o `SKILL.md`.

## Fontes de dados

- **CVM dados abertos** (primária, via `cvm.py`): DFP anual — lucro líquido, receita, patrimônio
  líquido, dívida, caixa, EBITDA e fluxo de caixa. Corrige imprecisões do Yahoo.
- **yfinance** (fallback): DRE/balanço/DFC, ações em circulação, beta, preço-alvo (sufixo `.SA`).
- **brapi.dev v2** (grátis, exige token): cotação, perfil/setor, lista de tickers (screener).
- **Banco Central (BCB)** (grátis): Selic, IPCA e câmbio.
- **RSS**: InfoMoney, Valor Econômico, Brazil Journal, Money Times.

⚠️ Resíduos: dividendos/DY/payout ainda vêm do Yahoo (não-confiáveis para B3). Valide na CVM.

## Como é pontuado (0–100)

| Pilar | Peso | Fonte |
|---|---|---|
| Qualidade | 20 | LLM (moat, mercado, gestão, governança) |
| Crescimento | 20 | dados (CAGR 5a de receita, lucro, EPS, FCF) |
| Rentabilidade | 15 | dados (ROE, ROIC, margem) |
| Balanço | 15 | dados (dívida/EBITDA, liquidez, juros) |
| Valuation | 20 | dados (PEG, EV/EBITDA, P/FCF, P/VP) |
| Risco | 10 | LLM (regulatório, cambial, político, operacional, financeiro) |

Detalhes dos limiares em `analysis.py` e `SKILL.md`.
