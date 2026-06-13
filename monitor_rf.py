"""
Monitor diário de índices de renda fixa ANBIMA.
Envia resumo via Telegram às 20h30 BRT (dias úteis).
Dados: IDA-DI, IDA-IPCA, IDA-IPCA Infraestrutura, IDA-IPCA ex-Infraestrutura,
       IMA-B, IMA-B 5, IMA-B 5+.
Fonte: API Índices+ da ANBIMA (precos-indices/v1/indices-mais).
"""

import base64
import logging
import os
from datetime import date, timedelta

import requests
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuração — defina tudo no .env, nunca aqui
# ---------------------------------------------------------------------------
ANBIMA_CLIENT_ID     = os.environ.get("ANBIMA_CLIENT_ID", "")
ANBIMA_CLIENT_SECRET = os.environ.get("ANBIMA_CLIENT_SECRET", "")
TELEGRAM_TOKEN       = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID     = os.environ.get("TELEGRAM_CHAT_ID", "")

# URLs da API ANBIMA (validadas na documentação oficial)
TOKEN_URL = "https://api.anbima.com.br/oauth/access-token"
IDA_URL   = "https://api.anbima.com.br/feed/precos-indices/v1/indices-mais/resultados-ida"
IMA_URL   = "https://api.anbima.com.br/feed/precos-indices/v1/indices-mais/resultados-ima"

# Subíndices desejados — nomes conforme campo `indice` da resposta da API.
# Se os nomes retornados pela API diferirem, ajuste aqui após a primeira execução com credenciais.
INDICES_IDA = {
    "IDA-DI",
    "IDA-IPCA",
    "IDA-IPCA Infraestrutura",
    "IDA-IPCA ex-Infraestrutura",
}
INDICES_IMA = {
    "IMA-B",
    "IMA-B 5",
    "IMA-B 5+",
}

TIMEOUT = 15  # segundos para chamadas HTTP


# ---------------------------------------------------------------------------
# Autenticação OAuth2 client_credentials
# ---------------------------------------------------------------------------
def obter_token() -> str:
    """Obtém access_token via OAuth2 client_credentials.

    A ANBIMA usa Basic Auth (base64(client_id:client_secret)) no header
    e {"grant_type": "client_credentials"} no body JSON.
    Token expira em 3600s — renovado a cada execução do job.
    """
    credencial = base64.b64encode(
        f"{ANBIMA_CLIENT_ID}:{ANBIMA_CLIENT_SECRET}".encode()
    ).decode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {credencial}",
    }
    resp = requests.post(
        TOKEN_URL,
        json={"grant_type": "client_credentials"},
        headers=headers,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    token = resp.json().get("access_token", "")
    if not token:
        raise ValueError("Resposta da ANBIMA não contém access_token.")
    log.info("Token ANBIMA obtido com sucesso.")
    return token


# ---------------------------------------------------------------------------
# Busca de dados
# ---------------------------------------------------------------------------
def _headers_api(token: str) -> dict:
    """Headers padrão para chamadas autenticadas à API ANBIMA."""
    return {
        "Authorization": f"Bearer {token}",
        "client_id": ANBIMA_CLIENT_ID,
        "Content-Type": "application/json",
    }


def _dia_util_anterior() -> str:
    """Retorna a data do último dia útil (D-1) em formato AAAA-MM-DD.

    Considera apenas fins de semana — feriados nacionais não são tratados
    automaticamente (limitação conhecida, ver CLAUDE.md).
    """
    d = date.today() - timedelta(days=1)
    # volta até encontrar um dia útil (seg=0 ... sex=4)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def buscar_ida(token: str, data_ref: str) -> list[dict]:
    """Busca resultados do IDA (Índice de Debêntures ANBIMA) para a data informada.

    Retorna lista de dicts filtrada pelos subíndices em INDICES_IDA.
    Publicado diariamente a partir das 11h.
    """
    resp = requests.get(
        IDA_URL,
        params={"data": data_ref},
        headers=_headers_api(token),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    dados = resp.json()

    # Loga nomes recebidos para facilitar calibração dos filtros
    nomes = {item.get("indice") for item in dados}
    log.info(f"IDA — índices recebidos: {nomes}")

    filtrados = [item for item in dados if item.get("indice") in INDICES_IDA]
    nao_encontrados = INDICES_IDA - {item.get("indice") for item in filtrados}
    if nao_encontrados:
        log.warning(f"IDA — não encontrados na resposta: {nao_encontrados}")

    return filtrados


def buscar_ima(token: str, data_ref: str) -> list[dict]:
    """Busca resultados do IMA (Índice de Mercado ANBIMA) para a data informada.

    Retorna lista de dicts filtrada pelos subíndices em INDICES_IMA.
    Publicado diariamente a partir das 20h.
    """
    resp = requests.get(
        IMA_URL,
        params={"data": data_ref},
        headers=_headers_api(token),
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    dados = resp.json()

    nomes = {item.get("indice") for item in dados}
    log.info(f"IMA — índices recebidos: {nomes}")

    filtrados = [item for item in dados if item.get("indice") in INDICES_IMA]
    nao_encontrados = INDICES_IMA - {item.get("indice") for item in filtrados}
    if nao_encontrados:
        log.warning(f"IMA — não encontrados na resposta: {nao_encontrados}")

    return filtrados


# ---------------------------------------------------------------------------
# Formatação da mensagem
# ---------------------------------------------------------------------------
def _formatar_variacao(valor) -> str:
    """Formata variação percentual com sinal e 4 casas decimais."""
    try:
        v = float(valor)
        sinal = "+" if v >= 0 else ""
        return f"{sinal}{v:.4f}%"
    except (TypeError, ValueError):
        return "N/D"


def montar_mensagem(data_ref: str, ida: list[dict], ima: list[dict]) -> str:
    """Monta o resumo formatado para envio no Telegram."""
    linhas = [
        f"📊 *Índices ANBIMA — {data_ref}*",
        "",
        "*IDA (Debêntures)*",
    ]

    # Ordem de exibição dos subíndices IDA
    ordem_ida = [
        "IDA-DI",
        "IDA-IPCA",
        "IDA-IPCA Infraestrutura",
        "IDA-IPCA ex-Infraestrutura",
    ]
    ida_por_nome = {item["indice"]: item for item in ida}
    for nome in ordem_ida:
        item = ida_por_nome.get(nome)
        if item:
            dia = _formatar_variacao(item.get("variacao_diaria"))
            ano = _formatar_variacao(item.get("variacao_anual"))
            linhas.append(f"  {nome}: dia {dia} | ano {ano}")
        else:
            linhas.append(f"  {nome}: dados indisponíveis")

    linhas += ["", "*IMA-B (NTN-B)*"]

    # Ordem de exibição dos subíndices IMA
    ordem_ima = ["IMA-B", "IMA-B 5", "IMA-B 5+"]
    ima_por_nome = {item["indice"]: item for item in ima}
    for nome in ordem_ima:
        item = ima_por_nome.get(nome)
        if item:
            dia = _formatar_variacao(item.get("variacao_diaria"))
            ano = _formatar_variacao(item.get("variacao_anual"))
            linhas.append(f"  {nome}: dia {dia} | ano {ano}")
        else:
            linhas.append(f"  {nome}: dados indisponíveis")

    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Envio via Telegram
# ---------------------------------------------------------------------------
def enviar_telegram(mensagem: str) -> None:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado — mensagem não enviada:\n%s", mensagem)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": mensagem,
                "parse_mode": "Markdown",
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        log.info("Resumo enviado ao Telegram.")
    except requests.RequestException as exc:
        log.error("Falha ao enviar Telegram: %s", exc)


# ---------------------------------------------------------------------------
# Job principal
# ---------------------------------------------------------------------------
def executar() -> None:
    log.info("--- executando job renda fixa ---")

    if not ANBIMA_CLIENT_ID or not ANBIMA_CLIENT_SECRET:
        log.error("ANBIMA_CLIENT_ID ou ANBIMA_CLIENT_SECRET não configurados no .env")
        return

    data_ref = _dia_util_anterior()
    log.info("Data de referência: %s", data_ref)

    try:
        token = obter_token()
    except Exception as exc:
        log.error("Falha na autenticação ANBIMA: %s", exc)
        enviar_telegram(f"⚠️ Monitor RF: falha na autenticação ANBIMA ({exc})")
        return

    ida, ima = [], []

    try:
        ida = buscar_ida(token, data_ref)
    except Exception as exc:
        log.error("Falha ao buscar IDA: %s", exc)

    try:
        ima = buscar_ima(token, data_ref)
    except Exception as exc:
        log.error("Falha ao buscar IMA: %s", exc)

    if not ida and not ima:
        log.warning("Nenhum dado obtido — não há mensagem para enviar.")
        return

    mensagem = montar_mensagem(data_ref, ida, ima)
    log.info("Mensagem montada:\n%s", mensagem)
    enviar_telegram(mensagem)


# ---------------------------------------------------------------------------
# Agendamento
# ---------------------------------------------------------------------------
def main() -> None:
    if not ANBIMA_CLIENT_ID or not ANBIMA_CLIENT_SECRET:
        log.warning(
            "ANBIMA_CLIENT_ID ou ANBIMA_CLIENT_SECRET não configurados — "
            "o job será agendado mas não conseguirá buscar dados."
        )
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram não configurado — resumos serão apenas logados.")

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")

    # Dias úteis (seg–sex) às 20h30 BRT.
    # Feriados nacionais não são filtrados automaticamente (ver CLAUDE.md).
    scheduler.add_job(
        executar,
        trigger="cron",
        day_of_week="mon-fri",
        hour=20,
        minute=30,
    )

    log.info("Monitor RF iniciado — job agendado para seg–sex às 20h30 BRT.")
    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Monitor RF encerrado.")


if __name__ == "__main__":
    main()
