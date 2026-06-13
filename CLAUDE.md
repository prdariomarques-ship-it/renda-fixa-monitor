# renda-fixa-monitor

Agente diário que busca os fechamentos dos índices de renda fixa da ANBIMA e envia um resumo via Telegram.

## O que faz

- Job único às **20h30 BRT, dias úteis (seg–sex)**.
- Busca dados D-1 de dois endpoints da API Índices+ da ANBIMA:
  - `resultados-ida` → IDA-DI, IDA-IPCA, IDA-IPCA Infraestrutura, IDA-IPCA ex-Infraestrutura
  - `resultados-ima` → IMA-B, IMA-B 5, IMA-B 5+
- Envia resumo formatado no Telegram com variação do dia e no ano por índice.

## Por que 20h30

- IDA é publicado a partir das 11h — dado D-1 disponível de manhã.
- IMA-B é publicado a partir das **20h** — dado D-1 só disponível à noite.
- Um job único às 20h30 garante que ambos os índices estejam com D-1 completo.

## Autenticação ANBIMA

OAuth2 client_credentials (validado na documentação oficial):

```
POST https://api.anbima.com.br/oauth/access-token
Authorization: Basic base64(client_id:client_secret)
Content-Type: application/json
Body: {"grant_type": "client_credentials"}
```

Token expira em 3600s — renovado a cada execução do job.

Chamadas à API usam `Authorization: Bearer <token>` + header `client_id`.

## Endpoints (documentação oficial)

| Índice | Endpoint | Publicação |
|--------|----------|------------|
| IDA | `GET https://api.anbima.com.br/feed/precos-indices/v1/indices-mais/resultados-ida?data=AAAA-MM-DD` | 11h+ |
| IMA | `GET https://api.anbima.com.br/feed/precos-indices/v1/indices-mais/resultados-ima?data=AAAA-MM-DD` | 20h+ |

Campos usados: `indice`, `variacao_diaria`, `variacao_anual`, `data_referencia`.

## Credenciais necessárias no .env

```
ANBIMA_CLIENT_ID=       ← gerado no portal developers.anbima.com.br
ANBIMA_CLIENT_SECRET=   ← gerado no portal developers.anbima.com.br
TELEGRAM_TOKEN=         ← mesmo bot do spcx-monitor e signal-engine
TELEGRAM_CHAT_ID=883232211
```

## Calibração dos nomes de índice

Os nomes em `INDICES_IDA` e `INDICES_IMA` em `monitor_rf.py` precisam bater exatamente
com o campo `indice` retornado pela API. Na primeira execução com credenciais reais,
o log imprime todos os nomes recebidos — ajuste os sets se necessário.

## Limitações conhecidas

- **Feriados nacionais**: o APScheduler filtra apenas fins de semana. Em feriados o job
  tenta executar e a API pode retornar dados vazios ou erro — comportamento esperado,
  não é bug.
- **Sem retry automático**: se a API falhar, o próximo ciclo é no dia seguinte. Adicionar
  retry com backoff se a confiabilidade for crítica.

## Execução

```bash
cd ~/projects/renda-fixa-monitor
python monitor_rf.py          # inicia scheduler
```

Em produção: **systemd user service** (`renda-fixa-monitor.service`).

## Dependências

`requests`, `python-dotenv`, `apscheduler`.
