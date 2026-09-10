"""Configuração central do Agente Bolsa.

O token do brapi.dev é opcional para os 4 tickers de demonstração
(PETR4, VALE3, ITUB4, MGLU3). Para qualquer outro ticker, cadastre-se
gratuitamente em https://brapi.dev/dashboard e defina a variável de ambiente
BRAPI_TOKEN (ou cole a chave em agente-bolsa.token).

Free tier: 15.000 requisições/mês, dados fundamentalistas completos.
"""
import os

BRAPI_TOKEN = os.environ.get("BRAPI_TOKEN", "").strip()

# Tenta ler o token de um arquivo local, se a variável não existir
_token_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agente-bolsa.token")
if not BRAPI_TOKEN and os.path.exists(_token_file):
    with open(_token_file, "r", encoding="utf-8") as f:
        BRAPI_TOKEN = f.read().strip()

BASE_URL = "https://brapi.dev/api/v2"

# Universo padrão de análise (usado quando o usuário não especifica tickers)
DEFAULT_TICKERS = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBAS3", "EGIE3", "B3SA3", "RENT3"]

# Pesos do score (guia, bloco 82). Soma = 100.
# Qualidade e Risco são avaliadas pela camada de raciocínio (LLM).
# Crescimento, Rentabilidade, Balanço e Valuation são determinísticos (70 pts).
WEIGHTS = {
    "qualidade": 20,      # moat, mercado crescente, gestão, governança  (qualitativo)
    "crescimento": 20,    # receita, lucro, EPS, FCF                     (quantitativo)
    "rentabilidade": 15,  # ROE, ROIC, margens                           (quantitativo)
    "balanco": 15,        # dívida, liquidez, caixa, cobertura de juros  (quantitativo)
    "valuation": 20,      # P/L, EV/EBITDA, P/FCF, P/VP, PEG             (quantitativo)
    "risco": 10,          # regulatório, cambial, político, operacional, financeiro (qualitativo)
}

# Fontes de notícias (RSS) — nível 3 do guia
NEWS_FEEDS = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Valor Econômico": "https://www.valor.com.br/rss",
    "Brazil Journal": "https://braziljournal.com/feed/",
    "Money Times": "https://www.moneytimes.com.br/mercados/feed/",
}

# Limiar de liquidez mínima (volume financeiro diário) para o funil — em R$
MIN_VOLUME_FINANCEIRO = 5_000_000  # R$ 5 mi/dia
