---
name: agente-bolsa
description: Use when analyzing or ranking B3 stocks. Score 0-100.
---

# Agente Bolsa — Análise Fundamentalista de Ações da B3

Ferramenta de **apoio à decisão** de investimento (médio prazo: semanas a meses). Analisa um
conjunto de tickers da B3, pontua de 0 a 100 e entrega **ranking + tese + riscos**, com cada
nota rastreável até os dados.

> ⚠️ **Disclaimer**: isto é análise e apoio à decisão baseada em dados públicos, não
> recomendação personalizada de investimento. Não substitui consultor de valores mobiliários
> credenciado (CVM/Anbima). Não emita recomendação de compra/venda — entregue tese, riscos e
> cenários; a decisão é do usuário.

---

## 1. Fluxo de execução (sempre nesta ordem)

1. **Coletar dados** (pipeline determinístico):
   ```bash
   cd C:\Users\usuario\agente-bolsa && python analyze.py PETR4 VALE3 WEGE3 --out /tmp/analise.json
   ```
   - Token brapi (grátis, em `agente-bolsa.token`): necessário para cotação/perfil/lista de
     tickers de qualquer ativo. Fundamentos vêm do **yfinance** (grátis, não precisa de token).
2. **Ler o JSON** de saída: `macro` (Selic/IPCA/câmbio/IBOV), `metricas`, `score_deterministico`
   (0–70) e `red_flags` por ativo.
3. **Camada qualitativa** (LLM): Qualidade (0–20) e Risco (0–10) conforme §3 e §4.
4. **Notícias/catalisadores** (automático — últimos 3 meses): eventos da CVM (fato relevante,
   comunicado, resultado, proventos) + notícias de imprensa (RSS). Já vêm no JSON como `noticias`.
5. **Montar o relatório final** no formato do §8.

**O score determinístico NÃO substitui a análise.** É um filtro para encontrar candidatos
(guia, bloco 83). A tese final exige o julgamento qualitativo sobre negócio, setor e notícias.

---

## 2. Sistema de pontuação (0–100)

| Pilar | Peso | Fonte | Subcritérios |
|---|---|---|---|
| Qualidade | 20 | LLM | moat, mercado crescente, gestão, governança (5 cada) |
| Crescimento | 20 | dados | receita, lucro, EPS, FCF — CAGR 5 anos (5 cada) |
| Rentabilidade | 15 | dados | ROE, ROIC, margem líquida (5 cada) |
| Balanço | 15 | dados | dívida líq./EBITDA, liquidez corrente, cobertura de juros (5 cada) |
| Valuation | 20 | dados | PEG, EV/EBITDA, P/FCF, P/VP (5 cada) |
| Risco | 10 | LLM | regulatório, cambial, político, operacional, financeiro (2 cada) |

- **Determinístico (70 pts)**: calculado em `analysis.py`. Limiares exatos no código.
- **Qualitativo (30 pts)**: você (LLM) atribui, com justificativa curta e rastreável.

**Faixas de interpretação (score final):**
- **≥ 80** — candidato forte (todos os pilares alinhados)
- **65–79** — candidato bom, com ressalvas específicas
- **50–64** — neutro / acompanhar
- **< 50** — descartar ou tese de recuperação explícita

---

## 3. Camada qualitativa — QUALIDADE (0–20)

Pontue cada subcritério de 0–5. Base: `profile.longBusinessSummary`, setor, notícias e razão.

- **Moat / vantagem competitiva (5)** — marca, efeito de rede, custo baixo, escala, patentes,
  custo de troca, regulação, distribuição. Quão difícil é um concorrente destruir a posição?
- **Mercado crescente (5)** — TAM grande e crescendo? Empresa ganha market share? Demanda
  estrutural (ex.: energia, tecnologia) vs. estagnada?
- **Gestão (5)** — histórico de alocação de capital, execução, cumpre guidance, aquisições
  criaram ou destruíram valor?
- **Governança (5)** — controlador, tag along, free float, segmento de listagem B3, partes
  relacionadas, alinhamento com minoritários.

**Regra**: não invente. Se não há informação, pontue neutro (2.5) e registre "sem dados
suficientes".

---

## 4. Camada qualitativa — RISCO (0–10)

Pontue cada subcritério de 0–2 (0 = risco alto, 2 = risco baixo), somando 10.

- **Regulatório** — setor regulado (bancos, energia, saneamento, saúde, telecom, seguradoras,
  educação)? Mudança de regra pode quebrar a tese?
- **Cambial** — exposição ao dólar: exportadora (USD↑ ajuda) ou importadora (USD↑ dói)?
- **Político** — risco fiscal, impostos, estatais, concessões. Pergunte: "qual o impacto
  econômico?", não aposta política.
- **Operacional** — concentração de clientes/fornecedores, commodity (ciclo), execução.
- **Financeiro** — alavancagem, liquidez, necessidade de capital, diluição.

---

## 5. Julgamento — princípios do guia (aplicar sempre)

- **Ciclicidade**: empresa cíclica (mineração, siderurgia, construção, commodities) pode
  parecer "barata" no topo do ciclo. P/L baixo em cíclica não é necessariamente oportunidade.
- **Expectativas**: o preço reflete o futuro, não o passado. Resultado bom pode derrubar a ação
  se o mercado esperava mais. "Comprar o fato, vender o boato."
- **Catalisador ≠ fundamento**: notícia move por dias; fundamento cria valor no longo prazo.
- **ROE × dívida juntos**: ROE alto por alavancagem é armadilha.
- **Dupla verificação**: DRE (lucro) + Balanço (patrimônio) + DFC (caixa) devem contar a mesma
  história.
- **PEG**: P/L ÷ crescimento do lucro. Crescimento alto justifica múltiplo alto.
- **Margem de segurança**: quanto maior a incerteza, maior a margem exigida entre preço e valor
  justo estimado.
- **Score não substitui análise**: serve para encontrar candidatos.

---

## 6. Red flags (nunca ignorar)

Se `red_flags` do JSON estiver não-vazio, investigue antes de qualquer conclusão. Sinais-chave:
receita sobe mas caixa não; lucro sobe mas FCO cai; dívida cresce muito; contas a receber /
estoque explodem; margens caem; diluição; P/L extremamente baixo sem explicação; DY
absurdamente alto; payout > 100%; ROE alto por alavancagem; FCF negativo recorrente; EPS e
lucro divergindo. Contextualize por setor (ex.: payout > 100% é normal em elétricas).

---

## 7. Fontes de dados (nível de confiança)

- **Primária (ouro) — usada nos scripts via `cvm.py`**: CVM dados abertos (DFP anual). É a fonte
  de **lucro líquido, receita, patrimônio líquido, dívida, caixa, EBITDA e fluxo de caixa** —
  corrige as imprecisões do Yahoo para bancos, Petrobras e ADRs. O yfinance só é usado como
  fallback (ações em circulação, beta, preço-alvo, e quando a CVM não cobre).
- **Cotação/perfil/lista de tickers**: brapi.dev v2 (grátis, exige token).
- **Eventos/notícias (automático, últimos 3 meses)**: CVM IPE — fato relevante, comunicado ao
  mercado, dados econômico-financeiros (resultados) e relatório de proventos (dividendos/JCP);
  + RSS de InfoMoney, Valor, Brazil Journal e Money Times (sentimento de imprensa).
- **Macro**: Selic e IPCA (API do Banco Central SGS), câmbio (BCB), IBOV (brapi `^BVSP`).

---

## 8. Formato do relatório final

```
## Análise — [tickers] (prazo: X)
Contexto macro relevante (Selic/câmbio/commodity), 1–2 linhas.

### Ranking
| # | Ticker | Empresa | Score /100 | Veredito |
|--:|--------|---------|-----------|----------|

### [Ticker] — score XX/100
- **Pilares**: Qualidade X/20 · Crescimento X/20 · Rentabilidade X/15 · Balanço X/15 ·
  Valuation X/20 · Risco X/10
- **Negócio**: o que faz, como ganha dinheiro (1–2 linhas).
- **Números-chave**: CAGR receita/lucro, ROE, ROIC, margem líquida, dívida líquida/EBITDA,
  P/L, EV/EBITDA, PEG, DY (tabela curta).
- **Tese**: por que cresce (ou não) no prazo X — fundamento + catalisador.
- **Riscos**: o que invalida a tese.
- **Margem de segurança / valor justo**: estimativa quando possível; senão, "sem base".
- **Veredito**: 🟢 candidato forte / 🟡 acompanhar / 🔴 descartar.
- **Red flags**: listar as do JSON e a avaliação de cada uma.

### Disclaimer
Análise de apoio à decisão, não recomendação personalizada.
```

---

## 9. Limitações conhecidas (tratar como ressalvas, não bugs)

- **Fundamentos do Yahoo não são confiáveis para alguns tickers** — especialmente bancos, Petrobras e outras com ADR/dupla listagem: lucro líquido (e valores absolutos) podem vir subestimados ou em escala errada, distorcendo P/L, ROE e CAGR. RATIOS (margens, ROE) costumam se preservar; múltiplos que dependem de valor absoluto (P/L, EV) não. **Valide números críticos na CVM/RI antes de concluir.**
- **Dividendos/DY/payout**: dados de dividendo do Yahoo são não-confiáveis para B3 (JCP,
  splits, escala) — DY e payout são **estimativas**; não tome decisão de renda por esse número
  sem conferir na fonte primária.
- **EPS histórico** é calculado como lucro/nº de ações (Diluted Average Shares do Yahoo) —
  consistente para CAGR e diluição, mas não exiba o valor absoluto como EPS oficial.
- **Cíclicas**: CAGR de lucro de 5 anos pode estar distorcido por pico/vale. Leia junto com o
  múltiplo atual e o ponto do ciclo.
- **P/FCF muito baixo** pode ser evento pontual de caixa; valide com o histórico de FCF.
- **Preço-alvo** vem do consenso do Yahoo (quando disponível); use como referência, não como
  alvo próprio.
