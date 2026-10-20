# renda-fixa-monitor

Agente diário que acompanha proxies de renda fixa negociados na B3 e envia um resumo via Telegram.

## Fonte e cobertura

Os dados são obtidos do Yahoo Finance para estes ETFs:

| Referência aproximada | Ticker | Uso no relatório |
|---|---|---|
| IMA-B | `IMAB11.SA` | Variação diária e em 12 meses |
| IRF-M | `IRFM11.SA` | Variação diária e em 12 meses |
| IMA-B 5+ | `B5P211.SA` | Variação diária e em 12 meses |

Os ETFs são proxies negociados na B3; seus resultados podem divergir dos índices que representam. O programa não consulta uma API oficial de índices nem depende de credenciais de dados pagas.

## Configuração

Instale as dependências:

```bash
python -m pip install -r requirements.txt
```

Defina estas variáveis no arquivo `.env` na pasta do projeto:

```dotenv
TELEGRAM_TOKEN=token_do_bot
TELEGRAM_CHAT_ID=id_do_chat
```

O `.env` está no `.gitignore`; não versione nem compartilhe o token real do bot.

## Execução

```bash
cd ~/projects/renda-fixa-monitor
python monitor_rf.py
```

O processo fica ativo e agenda uma consulta de segunda a sexta às 20h30, no fuso `America/Sao_Paulo`. A primeira consulta ocorre no próximo horário agendado; iniciar o processo não dispara um relatório imediatamente. Os logs aparecem no console.

Em produção, o processo pode ser mantido por um serviço `systemd --user` chamado `renda-fixa-monitor.service`.

## Limitações

- A variação é calculada com dados históricos dos ETFs retornados pelo Yahoo Finance; indisponibilidade ou atraso dessa fonte pode afetar o relatório.
- O agendador considera dias da semana, não feriados. Se nenhum ETF tiver dados suficientes, o programa registra o problema e não envia um relatório vazio.
- O intervalo de 12 meses usa o primeiro fechamento disponível na janela de um ano retornada pela fonte.
