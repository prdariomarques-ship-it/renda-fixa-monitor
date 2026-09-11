import logging
import os
from dotenv import load_dotenv
load_dotenv()
import sys
import requests
from datetime import date, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler
import yfinance as yf

# Configuração de log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger("monitor_rf")

TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")
TIMEOUT = 15  # segundos para chamadas HTTP

TICKERS = {
    "IMA-B (Proxy IMAB11.SA)": "IMAB11.SA",
    "IRF-M (Proxy IRFM11.SA)": "IRFM11.SA",
    "IMA-B 5+ (Proxy B5P211.SA)": "B5P211.SA"
}

def _dia_util_anterior() -> str:
    """Returns the date of the last business day (D-1) in YYYY-MM-DD format."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")

def _formatar_variacao(valor) -> str:
    try:
        v = float(valor)
        sinal = "+" if v >= 0 else ""
        return f"{sinal}{v:.4f}%"
    except (TypeError, ValueError):
        return "N/D"

def buscar_dados_yfinance() -> dict:
    """Fetches ETF data from Yahoo Finance as a proxy for ANBIMA indices."""
    resultados = {}
    for nome, ticker in TICKERS.items():
        try:
            t = yf.Ticker(ticker)
            data = t.history(period="1y")
            if not data.empty and len(data) >= 2:
                fechamento_atual = data.iloc[-1]['Close']
                fechamento_anterior = data.iloc[-2]['Close']
                variacao_diaria = ((fechamento_atual / fechamento_anterior) - 1) * 100

                fechamento_1y_atras = data.iloc[0]['Close']
                variacao_anual = ((fechamento_atual / fechamento_1y_atras) - 1) * 100

                resultados[nome] = {
                    "variacao_diaria": variacao_diaria,
                    "variacao_anual": variacao_anual
                }
            else:
                log.warning(f"Não foi possível obter histórico suficiente para {ticker}")
                resultados[nome] = None
        except Exception as e:
            log.error(f"Erro ao buscar {ticker}: {e}")
            resultados[nome] = None
    return resultados

def montar_mensagem(data_ref: str, resultados: dict) -> str:
    linhas = [
        f"📊 *Índices ANBIMA (Proxies B3) — {data_ref}*",
        ""
    ]

    for nome, dados in resultados.items():
        if dados:
            dia = _formatar_variacao(dados['variacao_diaria'])
            ano = _formatar_variacao(dados['variacao_anual'])
            linhas.append(f"*{nome}*\n  Dia {dia} | 12 Meses {ano}\n")
        else:
            linhas.append(f"*{nome}*\n  Dados indisponíveis\n")

    linhas.append("_Fonte: Yahoo Finance (ETFs B3)_")
    return "\n".join(linhas)

def enviar_telegram(mensagem: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado — mensagem não enviada:\n%s", mensagem)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem,
        "parse_mode": "Markdown",
    }
    try:
        resp = requests.post(url, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        log.info("Resumo enviado ao Telegram.")
    except requests.RequestException as exc:
        log.error("Falha ao enviar Telegram: %s", exc)

def executar() -> None:
    log.info("--- executando job renda fixa ---")

    data_ref = _dia_util_anterior()
    log.info("Data de referência: %s", data_ref)

    resultados = buscar_dados_yfinance()

    if not any(resultados.values()):
        log.warning("Nenhum dado obtido — não há mensagem para enviar.")
        return

    mensagem = montar_mensagem(data_ref, resultados)
    log.info("Mensagem montada:\n%s", mensagem)
    enviar_telegram(mensagem)

def main() -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado — resumos serão apenas logados.")

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Dias úteis (seg–sex) às 20h30 BRT.
    scheduler.add_job(
        executar,
        trigger="cron",
        day_of_week="mon-fri",
        hour=20,
        minute=30,
    )

    log.info("Monitor RF (yfinance proxy) iniciado — job agendado para seg–sex às 20h30 BRT.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Monitor RF encerrado.")

if __name__ == "__main__":
    main()
