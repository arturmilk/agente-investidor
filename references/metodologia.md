# Metodologia do Agente Bolsa

Base de conhecimento usada pelos scripts e pela camada de raciocínio. Consolida o conteúdo
de três guias sobre "como saber se uma ação está barata" (Clear, Toro, Capitalizo) com os
métodos clássicos de value investing (Graham, Bazin, Greenblatt, Piotroski, Altman, Lynch).

## 1. O que é uma ação "barata"

1. **Barato não é preço nominal baixo.** Uma ação de R$ 2 pode estar cara e uma de R$ 100,
   barata; o que importa é o preço em relação ao que a empresa gera (lucro, caixa,
   dividendos) e possui (patrimônio). "Ações de centavos" costumam ser empresas com
   dificuldades, baixa liquidez e governança fraca. *(Clear, Toro)*
2. **Barata = abaixo do valor intrínseco, com margem de segurança.** Comprar "uma nota de
   R$ 1 por R$ 0,50" (Graham). Quanto maior a incerteza, maior a margem exigida. *(Capitalizo)*
3. **Nenhum indicador decide sozinho.** P/L, P/VP e DY precisam ser lidos juntos e
   junto com receitas, margens, dívida e fluxo de caixa. *(Toro, Clear, Capitalizo)*
4. **Compare com o setor e com a própria história.** P/L abaixo da média do setor ou da
   média histórica da empresa sugere desconto; acima pode ser justificado por crescimento. *(Toro)*
5. **Armadilha de valor.** Múltiplo baixo muitas vezes reflete lucro caindo, dívida alta,
   perda de competitividade ou perspectivas ruins — a ação "barata" continua caindo. *(Clear, Capitalizo)*
6. **Cíclicas e commodities** (varejo, construção, turismo; petróleo, mineração, agro)
   ficam baratas em crises e parecem baratas no topo do ciclo. Normalize o lucro. *(Clear)*
7. **Dividendos só contam com histórico consistente.** DY alto de um ano isolado costuma ser
   extraordinário ou sinal de queda do preço. *(Clear, Toro)*
8. **Liquidez e macro importam.** Baixa liquidez dificulta sair da posição; Selic, câmbio e
   ciclo econômico mudam o custo de oportunidade. *(Clear)*

## 2. Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| DRE, balanço, fluxo de caixa (5 anos + ITR) | CVM dados abertos (DFP/ITR) | Oficial. Lucro/PL dos controladores. TTM = anual + acumulado do ano − mesmo período do ano anterior |
| Nº de ações | CVM (composição do capital) e B3 | B3 desempata quando há evento após o último ITR |
| Ticker ↔ empresa, segmento de listagem, controle, situação | CVM FCA | Novo Mercado/N1/N2, estatal/privado, recuperação judicial |
| Fatos relevantes, resultados, proventos | CVM IPE | Últimos 3 meses por padrão |
| Cotação, volume, valor de mercado (toda a B3) | brapi.dev | Lista completa sem token; cotação individual com token |
| Histórico de preços e proventos por ação | Yahoo Finance | Múltiplos históricos e DY por classe |
| Selic, IPCA, câmbio | Banco Central (SGS) | Custo de capital: ke = Selic + 5 p.p. |
| Notícias | Google News (busca por empresa) + RSS (InfoMoney, Valor, Brazil Journal, Money Times) | Sentimento e catalisadores |

## 3. Indicadores

| Indicador | Fórmula | Leitura |
|---|---|---|
| P/L | Valor de mercado ÷ lucro 12m dos controladores | Anos para "recuperar" o preço com o lucro atual |
| P/L normalizado | Valor de mercado ÷ lucro médio de 5 anos | Usar em cíclicas e quando o lucro 12m está atípico |
| P/VP | Valor de mercado ÷ patrimônio dos controladores | < 1: abaixo do patrimônio — só é barganha se o ROE for razoável |
| EV/EBIT | (Valor de mercado + dívida líquida) ÷ EBIT 12m | Múltiplo operacional, neutro à estrutura de capital |
| EV/EBITDA | EV ÷ (EBIT + depreciação) | Idem, antes de depreciação |
| P/FCF | Valor de mercado ÷ (FCO − capex) | Preço sobre o caixa livre |
| DY 12m | Dividendos + JCP pagos (caixa, DFC) ÷ valor de mercado | Conferir com o DY mediano de 5 anos |
| DY mediano 5a | Mediana dos dividendos pagos em 5 anos ÷ valor de mercado atual | Robusto a extraordinários (base do Bazin) |
| Payout | Dividendos 12m ÷ lucro 12m | > 100% só é sustentável em casos específicos (ex.: elétricas) |
| LPA / VPA | Lucro ou PL × (preço ÷ valor de mercado) | Por ação da classe analisada |
| Earnings yield | EBIT ÷ EV | Inverso do EV/EBIT (Greenblatt) |
| Lucro/preço vs Selic | 1 ÷ P/L − Selic | Prêmio da ação sobre a renda fixa |
| ROE | Lucro dos controladores ÷ PL dos controladores | Rentabilidade do acionista |
| ROA | Lucro consolidado ÷ ativo total | Essencial em bancos (≥ 1,5% é bom) |
| ROIC | EBIT × (1 − alíquota efetiva) ÷ (PL + dívida líquida) | Retorno do capital investido |
| Margens | Bruta, EBITDA, EBIT e líquida sobre a receita | Tendência de 3 anos importa |
| Dívida líquida/EBITDA | (Empréstimos CP+LP − caixa − aplicações) ÷ EBITDA | > 3,5x alto (utilities: > 5x) |
| Liquidez corrente | Ativo circulante ÷ passivo circulante | ≥ 1,5 confortável |
| Cobertura de juros | EBIT ÷ despesas financeiras | < 1,5x é risco (ignorado com caixa líquido) |
| PL/ativo | Patrimônio ÷ ativo total | Capitalização de bancos |
| Crescimento | Regressão log-linear de 5 anos (e CAGR) | Receita, lucro, caixa operacional, PL |
| PEG / PEGY | P/L ÷ crescimento % (÷ (crescimento + DY) %) | < 1 atrativo (Lynch) |

## 4. Preço justo (triangulação)

Cada método é calculado quando aplicável; o preço justo é a **mediana** dos métodos (mínimo 2)
e a **margem de segurança** = preço justo ÷ preço − 1. A faixa (mín–máx) mostra a incerteza.

| Método | Fórmula | Quando usar |
|---|---|---|
| Graham | √(22,5 × LPA × VPA) — 22,5 = P/L 15 × P/VP 1,5 | Lucro e PL positivos; generoso com Selic alta |
| Bazin | Dividendo mediano 5a por ação ÷ 6% | Pagadoras consistentes (≥ 4 de 5 anos) |
| P/L do setor | Mediana do P/L dos pares × LPA (normalizado em commodities) | Sempre que houver pares |
| EV/EBIT do setor | (Mediana EV/EBIT × EBIT − dívida líquida) por ação | Não financeiras |
| P/VP do setor | Mediana P/VP dos pares × VPA | Financeiras |
| P/L (e P/VP) histórico | Mediana própria de 5 anos × LPA (VPA) | Com histórico de preços |
| P/VP justo pelo ROE | (ROE − g) ÷ (ke − g), ke = Selic + 5 p.p., g = 4% | Financeiras |

Critérios do investidor defensivo (Graham, adaptados): lucro positivo em 5 anos, dividendos
todos os anos, lucro recente > lucro antigo, P/L ≤ 15, P/VP ≤ 1,5, P/L × P/VP ≤ 22,5,
liquidez corrente ≥ 1,5, dívida líquida ≤ PL e porte ≥ R$ 2 bi.

Critérios de Bazin: DY mediano ≥ 6%, dividendos em todos os 5 anos, dívida líquida < PL,
lucro positivo nos 5 anos.

## 5. Score determinístico (70 pts, calculado pelos scripts)

Cada subcritério vale 1–5 (2,5 = neutro por falta de dado). Faixas absolutas são combinadas
(média) com a posição relativa à mediana do setor quando há pares suficientes (≥ 5).

**Valuation (25)**
- P/L: < 6 → 5 · < 9 → 4 · < 12 → 3 · < 16 → 2 · senão 1 (prejuízo = 1). Commodities e lucro
  12m > 1,5× a média de 5 anos usam o P/L normalizado.
- EV/EBIT: < 5 → 5 · < 8 → 4 · < 11 → 3 · < 15 → 2 · senão 1. Financeiras: (P/VP ÷ mediana)
  ÷ (ROE ÷ mediana) — pagar mais caro só por mais rentabilidade.
- P/VP: < 1 → 5 · < 1,5 → 4 · < 2,5 → 3 · < 4 → 2 · senão 1; limitado a 3 se ROE < 8%.
- Rendimento: maior entre DY (média do 12m e do mediano 5a: ≥ 10% → 5 · ≥ 7% → 4 · ≥ 5% → 3 ·
  ≥ 3% → 2) e FCF yield (≥ 12% → 5 · ≥ 8% → 4 · ≥ 5% → 3 · ≥ 2% → 2).
- Margem de segurança da triangulação: ≥ 50% → 5 · ≥ 25% → 4 · ≥ 5% → 3 · ≥ −15% → 2 · senão 1.

**Crescimento (15)** — receita, lucro e caixa operacional (financeiras: patrimônio):
≥ 15% a.a. → 5 · ≥ 10% → 4 · ≥ 5% → 3 · ≥ 0 → 2 · negativo → 1. Lucro do último trimestre
−30% a/a tira 1 ponto; +30% soma 0,5.

**Rentabilidade (15)**
- ROE: ≥ 20% → 5 · ≥ 15% → 4 · ≥ 10% → 3 · ≥ 5% → 2; −1 se ROE > 20% com DL/EBITDA > 3,5.
- ROIC: ≥ 15% → 5 · ≥ 12% → 4 · ≥ 8% → 3 · ≥ 4% → 2. Financeiras: ROA ≥ 2% → 5 · ≥ 1,5% → 4 ·
  ≥ 1% → 3 · ≥ 0,5% → 2.
- Margem líquida: ≥ 20% → 5 · ≥ 12% → 4 · ≥ 7% → 3 · ≥ 3% → 2, ±0,5 pela tendência.
  Financeiras: nº de anos com ROE ≥ 12% nos últimos 5.

**Saúde financeira (15)**
- DL/EBITDA: caixa líquido → 5 · < 1 → 5 · < 2 → 4 · < 3 → 3 · < 4 → 2 · senão 1 (utilities:
  < 2,5 · 3,5 · 4,5 · 5,5). Financeiras: PL/ativo ≥ 12% → 5 · ≥ 9% → 4 · ≥ 7% → 3 · ≥ 5% → 2.
- Liquidez corrente (≥ 1,5 → 5 …) e cobertura de juros (≥ 8x → 5 …). Financeiras: anos com lucro.
- Piotroski F-Score: ≥ 8 → 5 · 7 → 4 · 5–6 → 3 · 3–4 → 2 · ≤ 2 → 1. Financeiras: desvio do ROE.

**Piotroski F-Score (0–9)**: ROA > 0; FCO > 0; ROA subiu; FCO > lucro; alavancagem (dívida
LP/ativo) caiu; liquidez corrente subiu; não emitiu ações (DFC); margem bruta subiu; giro do
ativo subiu. **Altman Z''**: 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4 (capital de giro, lucros
retidos, EBIT e PL/passivo sobre o ativo); > 2,6 zona segura, < 1,1 zona de risco.

## 6. Camada qualitativa (30 pts, você atribui)

**Qualidade (0–20)** — 0 a 5 cada, com justificativa curta e rastreável:
- **Moat**: marca, escala/custo, rede, patentes, custo de troca, regulação, distribuição.
- **Mercado**: tamanho e crescimento do mercado; ganho de participação; demanda estrutural.
- **Gestão**: histórico de alocação de capital, execução, aquisições que criaram valor.
- **Governança**: segmento (Novo Mercado > N2 > N1 > Básico), tag along, controle
  estatal (interferência) ou familiar, partes relacionadas, respeito ao minoritário.

**Risco (0–10)** — 0 a 2 cada (2 = risco baixo):
regulatório · político/estatal · cambial/commodity · operacional (concentração, execução) ·
financeiro (alavancagem, refinanciamento, diluição).

Sem informação: 2,5 (qualidade) ou 1 (risco) e escreva "sem dados suficientes".

**Faixas do score final**: ≥ 80 candidato forte · 65–79 bom, com ressalvas · 50–64 neutro,
acompanhar · < 50 descartar ou exigir tese de recuperação explícita.

## 7. Selo de barateza e armadilhas de valor

| Selo | Regra |
|---|---|
| 🟢 Barata com fundamentos sólidos | Valuation ≥ 16/25, rentabilidade + saúde ≥ 20/30, nenhum sinal de armadilha, nenhuma red flag alta e lucro "limpo" |
| 🟡 Barata, com ressalvas | Valuation ≥ 16/25, mas com algum sinal que exige investigação |
| 🟠 Possível armadilha de valor | Valuation ≥ 16/25 e pontos de armadilha ≥ 3 (alta = 2, média = 1) |
| ⚪ Preço justo (— empresa de qualidade) | Valuation entre 11 e 16 (qualidade ≥ 22/30) |
| 🔵 Cara, mas o crescimento pode justificar | Valuation < 11, PEG < 1 e lucro crescendo > 10% a.a. |
| 🔴 Cara | Valuation < 11 |

**Sinais de armadilha**: recuperação judicial/falência; PL negativo; prejuízo; lucro 12m < 60% da
média de 5 anos; tendência de queda do lucro; receita encolhendo; margem caindo 3 anos; cíclica
com lucro no pico; DL/EBITDA alto; EBITDA negativo com dívida; cobertura de juros < 1,5; Altman
na zona de risco; F-Score ≤ 3; caixa operacional negativo recorrente.

**Outras red flags**: crédito fiscal inflando o lucro; operações descontinuadas; lucro > 2× a
média; caixa operacional muito abaixo do lucro; P/L < 3; DY > 15%; payout > 100%; diluição;
dívida crescendo acima do lucro; recebíveis/estoques crescendo acima da receita; FCF negativo
recorrente; ROE sustentado por alavancagem; baixa liquidez; dados defasados.

## 8. Regras por setor

- **Bancos, seguradoras, holdings financeiras**: sem EV, dívida líquida ou margens. Valuation por
  P/L, P/VP ajustado ao ROE e DY; saúde por PL/ativo, lucro em todos os anos e estabilidade do ROE.
- **Utilities (energia, saneamento)**: dívida tolerada até ~4,5x EBITDA; payout alto é normal;
  risco regulatório/tarifário pesa na nota de risco.
- **Commodities (petróleo, mineração, siderurgia, papel e celulose, agro)**: P/L e EV/EBIT sobre
  lucro/EBIT médio de 5 anos; atenção ao preço da commodity e ao câmbio.
- **Cíclicas domésticas (varejo, construção, transporte, turismo)**: sensíveis à Selic; ficam
  baratas no aperto monetário e se valorizam rápido quando o cenário melhora.
- **Holdings** (receita ≈ 0): margens não se aplicam; o lucro vem de equivalência patrimonial.
- **Estatais**: desconto estrutural por risco político — trate na nota de risco, não como erro.

## 9. Estratégias do screener

| Estratégia | Filtro | Ordem |
|---|---|---|
| valor | lucro > 0, sem selo de armadilha | score determinístico |
| graham | P/L ≤ 15, P/VP ≤ 1,5 (ou P/L×P/VP ≤ 22,5), lucro em 5 anos | margem de Graham |
| bazin | DY mediano ≥ 6%, dividendos em 5 anos, dívida líquida < PL | margem ao preço-teto |
| magic | não financeiras nem utilities, EBIT e ROIC > 0 | soma dos rankings EV/EBIT e ROIC |
| dividendos | DY 12m e 5a ≥ 5%, pagos em ≥ 4 de 5 anos, payout ≤ 100% | DY médio |
| qualidade | ROE ≥ 15%, ROIC ≥ 12%, margem ≥ 10%, dívida baixa, F ≥ 6, lucro limpo | rentab. + saúde + cresc. |
| barganha | P/VP < 1, ROE ≥ 8%, F ≥ 5, sem armadilha grave | menor P/VP |
| piotroski | F-Score ≥ 7 (não financeiras) | menor P/VP |

Filtros comuns: liquidez ≥ R$ 2 mi/dia, valor de mercado ≥ R$ 500 mi, exclui recuperação
judicial e (por padrão) selos de armadilha.

## 10. Limitações conhecidas

- Os dados contábeis são os do último ITR/DFP entregue; fatos posteriores só aparecem nas notícias.
- Preço-alvo de consenso só aparece se o `yfinance` estiver instalado (opcional).
- Dividendos são o caixa pago no exercício (não por data-com); mudanças de política demoram a
  aparecer. JCP entra pelo valor bruto pago.
- Múltiplos históricos estimam o valor de mercado passado pelo preço ajustado e pela variação do
  nº de ações — boa aproximação, não um dado oficial.
- O score encontra candidatos; não substitui a leitura do negócio, do setor e das notícias.

## 11. Referências

- Clear — "Ações mais baratas da bolsa: como encontrar e comprar?" (master.clear.com.br/acoes-mais-baratas)
- Toro — "Como saber se uma ação está barata ou cara?" (blog.toroinvestimentos.com.br/bolsa/como-saber-acao-esta-barata)
- Capitalizo — "Ações baratas: saiba identificar barganhas" (capitalizo.com.br/acoes-baratas-barganhas)
- Benjamin Graham — *O Investidor Inteligente* (margem de segurança, investidor defensivo)
- Décio Bazin — *Faça Fortuna com Ações* (preço-teto por dividendos de 6%)
- Joel Greenblatt — *The Little Book That Beats the Market* (Fórmula Mágica)
- Joseph Piotroski (2000) — *Value Investing: The Use of Historical Financial Statement Information*
- Edward Altman — Z-Score (1968) e Z''-Score para mercados emergentes (1995)
- Peter Lynch — *O Jeito Peter Lynch de Investir* (PEG)
