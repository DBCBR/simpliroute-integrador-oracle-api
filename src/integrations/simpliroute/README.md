````markdown
# Integração SimpliRoute

Este pacote concentra o serviço FastAPI responsável por:

- Ler periodicamente as views Oracle e enviar visitas/entregas ao SimpliRoute.
- Expor endpoints de healthcheck.
- Receber webhooks do SimpliRoute e refletir os status no banco Oracle.

## Variáveis principais (`settings/.env`)

### Oracle
- `ORACLE_HOST`, `ORACLE_PORT`, `ORACLE_SERVICE`, `ORACLE_USER`, `ORACLE_PASS`, `ORACLE_SCHEMA`.
- `ORACLE_VIEWS` ou `ORACLE_VIEW_VISITAS`/`ORACLE_VIEW_ENTREGAS` para controlar as views consumidas.
- `ORACLE_POLL_WHERE` para filtros (`WHERE`) adicionais.
- `ORACLE_STATUS_SCHEMA` (opcional) — schema usado ao atualizar a tabela de status (default: `ORACLE_SCHEMA`).
- `SIMPLIROUTE_TARGET_TABLE` (default `TD_OTIMIZE_ALTSTAT`).
- `SIMPLIROUTE_TARGET_ACTION_COLUMN` (default `ACAO`) — recebe `A/E/S` conforme status do SR.
- `SIMPLIROUTE_TARGET_INFO_COLUMN` (default `INFORMACAO`) — armazena o JSON completo recebido no webhook.
- `SIMPLIROUTE_TARGET_STATUS_COLUMN` (default `STATUS`) — preenche códigos numéricos (0/1/2/3) conforme `TPREGISTRO`.

### SimpliRoute
- `SIMPLIR_ROUTE_TOKEN` (ou `SIMPLIROUTE_TOKEN`).
- `SIMPLIROUTE_API_BASE` (default `https://api.simpliroute.com`).
- `SIMPLIR_ROUTE_WEBHOOK_TOKEN` / `SIMPLIROUTE_WEBHOOK_TOKEN` para validar `POST /webhook/simpliroute`.

### Serviço
- `POLLING_INTERVAL_MINUTES` (default `60`).
- `SIMPLIROUTE_POLLING_LIMIT` (default usa `ORACLE_FETCH_LIMIT`).
- `WEBHOOK_PORT` (default `8000`).

## Execução local

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn src.integrations.simpliroute.app:app --reload --host 0.0.0.0 --port 8000
```

## Docker / Compose

```powershell
# serviço que roda continuamente
docker compose build simpliroute_service
docker compose up simpliroute_service
Invoke-RestMethod -Uri http://localhost:8000/health/ready
```

### Endpoints
- `GET /health`, `/health/live`, `/health/ready`.
- `POST /webhook/simpliroute` — grava o payload bruto em `data/work/webhooks/` e agenda `persist_status_updates()` para refletir no Oracle.

### Fluxo de polling
1. `_collect_records()` lê as views configuradas usando `fetch_grouped_records`.
2. Cada registro passa por `build_visit_payload()`.
3. O lote é enviado para `/v1/routes/visits/` via `post_simpliroute`.
4. O resultado é registrado em `data/work/service_events.log`.

### Webhook → Oracle
`persist_status_updates()` grava diretamente na `SIMPLIROUTE_TARGET_TABLE`, preenchendo `ACAO` (A/E/S), `INFORMACAO` (payload bruto) e, quando configurado, a coluna `STATUS` (0/1/2/3) conforme a combinação `TPREGISTRO` + status recebido. Ajuste as variáveis para apontar o schema/tabela corretos do IW.

## Testes
Execute `pytest tests/test_mapper.py` para validar o mapeamento principal. Os utilitários anteriores ligados ao Gnexum foram descontinuados.
````
