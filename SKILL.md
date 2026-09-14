---
name: agente-bolsa
description: Análise fundamentalista e screener de ações da B3.
version: 2.0.0
author: arturmilk
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Finanças, Ações, B3, Valuation, Dividendos, Screener]
    category: finance
required_environment_variables:
  - name: BRAPI_TOKEN
    prompt: Token gratuito da brapi.dev (opcional)
    help: Crie em https://brapi.dev/dashboard — sem token o agente usa o Yahoo Finance
    required_for: Cotações mais rápidas via brapi (opcional)
---

# Agente Bolsa — análise fundamentalista de ações da B3

Responde "esta ação está barata ou cara — e por quê?" com dados oficiais (CVM, B3, Banco
Central). Calcula ~60 indicadores com os últimos 12 meses, compara com o setor e com o
histórico da própria empresa, estima o preço justo por vários métodos (Graham, Bazin,
múltiplos), detecta armadilhas de valor e dá um score 0–100: 70 pts calculados pelos
scripts + 30 pts qualitativos atribuídos por você. Também varre a bolsa inteira atrás de
oportunidades (8 estratégias). Não emite ordem de compra/venda: entrega tese, riscos e
cenários — a decisão é do usuário.

## When to Use
- "Analise PETR4", "WEGE3 está cara?", "compare ITUB4 e BBDC4", "qual o preço justo de TAEE11?"
- "Quais ações estão baratas?", "melhores pagadoras de dividendos", "ações abaixo do patrimônio",
  "fórmula mágica", "ações de qualidade", "barganhas no setor elétrico"
- Relatórios agendados (screener semanal, acompanhamento de uma lista de tickers).

## Prerequisites
- Python 3.9+ só com a biblioteca padrão (nada para instalar) e acesso à internet.
- Opcional: `BRAPI_TOKEN` (grátis) ou arquivo `agente-bolsa.token` na raiz da skill.
- A 1ª execução baixa ~100 MB da CVM e processa em ~1–2 min; depois tudo fica em cache
  (`~/.cache/agente-bolsa`; mude com `AGENTE_BOLSA_CACHE`) e as análises levam segundos.

## How to Run
Use a ferramenta `terminal`:
```bash
python3 ${HERMES_SKILL_DIR}/scripts/analyze.py PETR4 VALE3 --compacto        # para chat
python3 ${HERMES_SKILL_DIR}/scripts/analyze.py WEGE3                          # relatório completo
python3 ${HERMES_SKILL_DIR}/scripts/analyze.py ITUB4 --json --out /tmp/itub4.json
python3 ${HERMES_SKILL_DIR}/scripts/screener.py --estrategia valor --top 10 --compacto
python3 ${HERMES_SKILL_DIR}/scripts/screener.py --estrategia todas --top 5
python3 ${HERMES_SKILL_DIR}/scripts/selftest.py                               # autoteste
```

## Quick Reference
| Pedido do usuário | Comando |
|---|---|
| Analisar 1–10 tickers | `analyze.py T1 T2 ... [--compacto]` |
| Dados completos para raciocinar | `analyze.py T1 --json --out /tmp/x.json` e leia com `read_file` |
| "Ações baratas" / oportunidades | `screener.py --estrategia valor` |
| Estilo Graham / Bazin / Greenblatt | `--estrategia graham` · `bazin` · `magic` |
| Renda / dividendos | `--estrategia dividendos` (ou `bazin`) |
| Qualidade a preço razoável | `--estrategia qualidade` |
| Abaixo do patrimônio (P/VP < 1) | `--estrategia barganha` (ou `piotroski`) |
| Um setor específico | `--setor energia` · `bancos` · `commodities` · `comercio` |
| Dados novos agora | `screener.py --atualizar` (o universo fica 6h em cache) |

Opções de `analyze.py`: `--sem-noticias`, `--meses N`, `--sem-setor`, `--out arq.json`.
Opções de `screener.py`: `--top N`, `--min-liq R$`, `--min-mcap R$`, `--incluir-armadilhas`, `--out`.

## Procedure
1. **Entenda o pedido.** Tickers citados → `analyze.py`. Pedido aberto ("o que está barato?",
   "boas pagadoras") → `screener.py` com a estratégia adequada e depois `analyze.py` nos 3–5
   primeiros para aprofundar.
2. **Rode o script** (em chat use `--compacto`). Se precisar de detalhes, gere o JSON com
   `--out` e leia os campos: `indicadores`, `valuation`, `score`, `selo`, `red_flags`,
   `setor_comparacao`, `multiplos_historicos`, `governanca`, `negocio`, `noticias`.
3. **Leia o selo com senso crítico.** "Barata" só é oportunidade se os fundamentos não
   explicam o desconto. Investigue toda red flag `alta` e cada selo 🟠 (armadilha de valor).
4. **Faça a camada qualitativa** (detalhes em `references/metodologia.md` §6):
   - Qualidade 0–20: moat, mercado/crescimento, gestão/alocação de capital, governança
     (use `governanca.segmento_listagem`, `controle`, notícias).
   - Risco 0–10: regulatório, político/estatal, cambial/commodity, operacional, financeiro.
   Sem informação suficiente → nota neutra e diga "sem dados suficientes". Não invente.
5. **Score final** = `score.total_deterministico` (0–70) + Qualidade + Risco.
   ≥ 80 candidato forte · 65–79 bom com ressalvas · 50–64 neutro/acompanhar · < 50 descartar
   ou exigir tese de recuperação explícita.
6. **Responda no formato** de `references/relatorio.md`: veredito, números-chave vs setor,
   preço justo (faixa dos métodos), tese, riscos, catalisadores, red flags e o aviso final.

## Pitfalls
- Múltiplo baixo pode ser armadilha: lucro caindo, dívida alta, perda de competitividade,
  recuperação judicial, baixa liquidez. O selo 🟠 e as red flags existem para isso.
- Cíclicas/commodities parecem baratas no topo do ciclo: olhe `pl_normalizado` (lucro médio 5a).
- Lucro inflado (crédito fiscal, venda de ativo, descontinuadas) derruba o P/L artificialmente:
  as red flags de categoria `lucro` avisam — use o múltiplo normalizado nesses casos.
- Bancos/seguradoras: EV/EBITDA, dívida líquida e margens não se aplicam; use P/L, P/VP×ROE,
  DY, PL/ativo e consistência do ROE (os scripts já trocam os critérios).
- DY vem do caixa pago no DFC (empresa inteira). Dividendo extraordinário infla o DY 12m —
  compare com `dy_mediano_5a`.
- Graham (22,5) foi calibrado para juros baixos; com Selic alta ele é generoso. Use a
  triangulação, não um método isolado.
- Plano grátis da brapi aceita 1 ticker por chamada; os scripts já tratam isso e caem para
  o Yahoo se a brapi falhar. A 1ª execução é lenta (download da CVM) — avise o usuário.
- Dados contábeis são do último ITR/DFP entregue à CVM; eventos posteriores (aquisições,
  emissões) só aparecem nas notícias/fatos relevantes.

## Verification
- `python3 ${HERMES_SKILL_DIR}/scripts/selftest.py` termina com `OK`.
- A análise imprime `score determinístico` para cada ticker e nenhum `[erro]` no stderr.
- Toda resposta final traz: selo, score (determinístico + qualitativo), preço justo com a
  faixa dos métodos, principais riscos e o aviso de que não é recomendação personalizada.
