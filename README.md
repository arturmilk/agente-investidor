# Agente Bolsa v2 — análise fundamentalista de ações da B3

Skill para o [Hermes Agent](https://hermes-agent.nousresearch.com) (e para uso direto no
terminal) que responde **"esta ação está barata ou cara — e por quê?"** com dados oficiais
e varre a bolsa inteira atrás de oportunidades.

> ⚠️ Ferramenta de análise e apoio à decisão com dados públicos. Não é recomendação
> personalizada de investimento e não substitui um profissional certificado (CVM/Anbima).

## O que ele faz

- **Dados oficiais da CVM**: DRE, balanço e fluxo de caixa de 6 exercícios + últimos 12 meses
  (DFP + ITR), para ~350 companhias listadas, incluindo bancos, holdings e units.
- **~60 indicadores**: P/L, P/L normalizado, P/VP, EV/EBIT, EV/EBITDA, P/FCF, DY (12m e mediano
  de 5 anos), payout, ROE, ROA, ROIC, margens, dívida líquida/EBITDA, liquidez, cobertura de juros,
  crescimento de 5 anos, diluição etc.
- **Comparação com o setor** (mediana e percentil entre os pares) e **com a própria história**
  (P/L, P/VP, EV/EBIT e DY medianos dos últimos 5 anos).
- **Preço justo por triangulação**: Graham, Bazin, múltiplos do setor, múltiplos históricos e
  P/VP justo pelo ROE → preço justo, faixa e margem de segurança.
- **Qualidade e risco quantitativos**: Piotroski F-Score, Altman Z''-Score, qualidade do lucro.
- **Detector de armadilha de valor** e **selo**: 🟢 barata sólida · 🟡 barata com ressalvas ·
  🟠 possível armadilha · ⚪ preço justo · 🔵 cara mas crescendo · 🔴 cara.
- **Score 0–100**: 70 pts calculados (valuation, crescimento, rentabilidade, saúde) + 30 pts
  qualitativos (qualidade e risco) avaliados pelo LLM seguindo `references/metodologia.md`.
- **Screener com 8 estratégias**: valor, Graham, Bazin, Fórmula Mágica, dividendos, qualidade,
  barganhas (P/VP < 1) e Piotroski.
- **Notícias e catalisadores**: fatos relevantes/resultados/proventos da CVM + Google News + RSS.
- **Governança**: segmento de listagem, controle (estatal/privado), recuperação judicial.

## O que mudou em relação à v1

| v1 | v2 |
|---|---|
| Fundamentos do Yahoo (imprecisos na B3) com CVM parcial | CVM como fonte principal, com TTM trimestral, lucro/PL dos controladores, capex e dividendos pelo fluxo de caixa |
| 1 ticker por vez; lista de tickers fixa | Universo inteiro da B3 em segundos + screener com 8 estratégias |
| Sem comparação setorial/histórica | Medianas e percentis do setor + múltiplos históricos de 5 anos |
| Sem preço justo | Graham, Bazin, múltiplos e triangulação com margem de segurança |
| Red flags simples | Piotroski, Altman, qualidade do lucro, detector de armadilha e selo |
| Dependia de `requests`, `pandas`, `yfinance` | Só a biblioteca padrão do Python |
| Caminhos do Windows no SKILL.md | SKILL.md no formato do Hermes (`${HERMES_SKILL_DIR}`), cache fora da pasta da skill |
| — | Autoteste (`scripts/selftest.py`) |

## Instalação na VPS (Hermes Agent)

No terminal onde o comando `hermes` funciona (se o Hermes roda em Docker, use o terminal do
container, ex.: Gerenciador Docker → hermes-agent → Terminal):

```bash
# 1) coloque a skill na pasta de skills do Hermes
mkdir -p ~/.hermes/skills/finance
cd ~/.hermes/skills/finance
unzip /caminho/para/agente-bolsa.zip          # cria ~/.hermes/skills/finance/agente-bolsa
# (ou: git clone https://github.com/arturmilk/agente-bolsa)

# 2) opcional: token gratuito da brapi.dev (sem ele o agente usa o Yahoo)
echo "SEU_TOKEN" > ~/.hermes/skills/finance/agente-bolsa/agente-bolsa.token

# 3) teste (a 1ª análise baixa ~100 MB da CVM e leva 1–2 min; depois é rápido)
python3 ~/.hermes/skills/finance/agente-bolsa/scripts/selftest.py
python3 ~/.hermes/skills/finance/agente-bolsa/scripts/analyze.py PETR4 --compacto

# 4) confira que o Hermes reconheceu a skill
hermes skills list
```

O cache fica em `~/.hermes/cache/agente-bolsa` (dentro do volume do Hermes) ou em
`~/.cache/agente-bolsa`; mude com a variável `AGENTE_BOLSA_CACHE`.

## Uso

```bash
python3 scripts/analyze.py PETR4 VALE3 WEGE3            # relatório completo em Markdown
python3 scripts/analyze.py TAEE11 --compacto            # resumo para Telegram/WhatsApp
python3 scripts/analyze.py ITUB4 --json --out itub.json # todos os dados em JSON
python3 scripts/screener.py                             # estratégia "valor", top 15
python3 scripts/screener.py --estrategia bazin --top 10 --compacto
python3 scripts/screener.py --estrategia todas --top 5
python3 scripts/screener.py --estrategia barganha --setor energia
```

Pelo Hermes (Telegram/WhatsApp), basta pedir em linguagem natural: *"analise PETR4 e VALE3"*,
*"quais ações estão baratas hoje?"*, *"me mostre as melhores pagadoras de dividendos"*.

Sugestões de agendamento (peça ao Hermes em linguagem natural):
- *"Toda segunda às 8h, horário de Brasília, rode o screener de valor da skill agente-bolsa e me mande o top 10 no formato compacto."*
- *"Todo dia útil às 18h30, analise PETR4, ITUB4 e TAEE11 no formato compacto e me avise se algum selo mudar."*
- *"Todo dia 15, rode o screener com a estratégia todas e me mande um resumo."*

## Estratégias do screener

| Estratégia | Ideia |
|---|---|
| `valor` | Maior score do agente, sem armadilhas de valor (padrão) |
| `graham` | Investidor defensivo: P/L ≤ 15, P/VP ≤ 1,5, lucro em 5 anos; margem sobre √(22,5 × LPA × VPA) |
| `bazin` | Dividendo mediano ≥ 6% ao ano, pago todo ano, dívida < PL; margem ao preço-teto |
| `magic` | Fórmula Mágica de Greenblatt: EV/EBIT baixo + ROIC alto |
| `dividendos` | DY 12m e de 5 anos ≥ 5%, pagamento consistente e payout sustentável |
| `qualidade` | ROE/ROIC altos, margens, dívida baixa, F-Score ≥ 6 e lucro limpo |
| `barganha` | P/VP < 1 com lucro, ROE ≥ 8% e sem sinais graves de armadilha |
| `piotroski` | F-Score ≥ 7 com o menor P/VP |

Metodologia completa (fórmulas, faixas de pontuação, regras por setor e rubrica qualitativa):
[`references/metodologia.md`](references/metodologia.md). Formato das respostas:
[`references/relatorio.md`](references/relatorio.md).

## Fontes de dados (todas gratuitas)

- **CVM dados abertos**: DFP, ITR, FCA, cadastro e IPE (fatos relevantes).
- **B3**: nº de ações atual (desempate do valor de mercado).
- **brapi.dev**: lista da B3 com preço, volume e valor de mercado; cotação individual (token grátis).
- **Yahoo Finance**: histórico de preços e proventos por ação; fallback de cotação.
- **Banco Central (SGS)**: Selic, IPCA e câmbio. **Google News + RSS**: notícias.

## Estrutura

```
agente-bolsa/
├── SKILL.md                  # instruções da skill para o Hermes
├── README.md
├── requirements.txt          # vazio: só biblioteca padrão
├── references/
│   ├── metodologia.md        # fórmulas, faixas, regras por setor, rubrica qualitativa
│   └── relatorio.md          # formato das respostas (chat e completo)
└── scripts/
    ├── analyze.py            # análise profunda de tickers (CLI)
    ├── screener.py           # varredura da B3 por estratégia (CLI)
    ├── selftest.py           # autoteste das fórmulas
    ├── cvm.py                # DFP/ITR/FCA/IPE da CVM → fundamentos e TTM
    ├── market.py             # brapi + Yahoo (cotação, universo, histórico)
    ├── b3.py                 # nº de ações atual pela B3
    ├── indicators.py         # indicadores, múltiplos históricos, valor de mercado
    ├── valuation.py          # Graham, Bazin, triangulação, Piotroski, Altman, PEG
    ├── scoring.py            # score 0–70, red flags e selo
    ├── universe.py           # universo B3 + medianas setoriais
    ├── macro.py · news.py · report.py · net.py · config.py
```

## Limitações

- Os números contábeis são do último ITR/DFP entregue à CVM; eventos posteriores só aparecem
  em fatos relevantes e notícias.
- DY considera o caixa efetivamente pago no período (empresa inteira), não a data-com.
- Múltiplos históricos usam valor de mercado estimado (preço ajustado × variação do nº de ações).
- O score encontra candidatos; a tese exige ler o negócio, o setor e as notícias.
