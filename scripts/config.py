"""Configuração central do Agente Bolsa.

Tudo roda só com a biblioteca padrão do Python (3.9+). As fontes de dados
são abertas: CVM (fundamentos oficiais), Banco Central (macro), Yahoo
Finance (cotações e histórico) e Google News/RSS (notícias).

Token brapi.dev (opcional, recomendado): acelera cotações e habilita o
universo completo da B3 no screener em 3 requisições. Defina a variável
de ambiente BRAPI_TOKEN ou salve a chave em `agente-bolsa.token` na raiz
da skill.

Cache: `~/.hermes/cache/agente-bolsa` quando o Hermes está instalado (fica no volume
persistente do Hermes); senão `~/.cache/agente-bolsa`. Mude com AGENTE_BOLSA_CACHE.
"""
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _cache_dir():
    if os.environ.get("AGENTE_BOLSA_CACHE"):
        return os.environ["AGENTE_BOLSA_CACHE"]
    hermes = os.path.expanduser(os.environ.get("HERMES_HOME") or os.path.join("~", ".hermes"))
    if os.path.isdir(hermes):
        return os.path.join(hermes, "cache", "agente-bolsa")
    return os.path.join("~", ".cache", "agente-bolsa")


CACHE_DIR = os.path.abspath(os.path.expanduser(_cache_dir()))
os.makedirs(CACHE_DIR, exist_ok=True)


def _token():
    tok = os.environ.get("BRAPI_TOKEN", "").strip()
    if tok:
        return tok
    path = os.path.join(SKILL_DIR, "agente-bolsa.token")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return ""


BRAPI_TOKEN = _token()
BRAPI_BASE = "https://brapi.dev/api/v2"

# Universo padrão (quando o usuário não informa tickers)
DEFAULT_TICKERS = ["PETR4", "VALE3", "ITUB4", "WEGE3", "BBAS3", "EGIE3", "B3SA3", "RENT3"]

# Filtros padrão do screener. Volume = volume financeiro do último pregão (R$).
MIN_VOLUME_FINANCEIRO = 2_000_000
MIN_MARKET_CAP = 500_000_000

# Premissas de valuation (explícitas no relatório)
PREMIO_RISCO_ACOES = 0.05    # ke = Selic + prêmio (custo do capital próprio)
CRESCIMENTO_PERPETUO = 0.04  # g nominal de longo prazo
GRAHAM_MULTIPLO = 22.5       # P/L máx. 15 × P/VP máx. 1,5 (Graham)
BAZIN_DY_MINIMO = 0.06       # dividend yield mínimo exigido por Décio Bazin
IR_PADRAO = 0.34             # IR + CSLL para NOPAT quando a alíquota efetiva é inválida

# Imprensa (RSS abertos). O Google News por empresa é consultado à parte.
NEWS_FEEDS = {
    "InfoMoney": "https://www.infomoney.com.br/feed/",
    "Valor Econômico": "https://www.valor.com.br/rss",
    "Brazil Journal": "https://braziljournal.com/feed/",
    "Money Times": "https://www.moneytimes.com.br/mercados/feed/",
}
