# Integração SimpliRoute

Este diretório contém a integração com a API do SimpliRoute (envio de `Visit` objects) e a ponte com o Gnexum.

Variáveis de ambiente (arquivo `settings/.env`):

- `SIMPLIR_ROUTE_TOKEN` : token da API SimpliRoute. Usado no header `Authorization: Token <token>`.
- `SIMPLIROUTE_API_BASE` : URL base da API SimpliRoute (ex: `https://api.simpliroute.com`). O cliente adiciona o path `/v1/routes/visits/`.
- `SIMPLIROUTE_WEBHOOK_TOKEN` : (opcional) token para validar webhooks locais.
- `GNEXUM_API_URL` : URL do endpoint do Gnexum para buscar itens por registro.
- `GNEXUM_TOKEN` : token para autenticar chamadas ao Gnexum (se aplicável).
- `USE_REAL_GNEXUM` : `true|false` — se `true`, a integração fará chamadas reais ao `GNEXUM_API_URL`; se `false`, usa dados simulados.
- `WEBHOOK_PORT` : porta onde a aplicação expõe endpoints (padrão `8000`).
- `POLLING_INTERVAL_MINUTES` : intervalo (em minutos) entre execuções do polling (padrão `60`).

Como rodar localmente (sem Docker):

1. Crie e ative um virtualenv com Python 3.11+

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Copie/edite `settings/.env` com as variáveis necessárias.

3. Execute a aplicação:

```powershell
uvicorn src.integrations.simpliroute.app:app --reload --host 0.0.0.0 --port 8000
```

Com Docker / docker-compose (recomendado para reproduzir ambiente):

```powershell
# rebuild se necessário
docker compose build --no-cache
docker compose up -d
# verificar logs
docker compose logs -f simpliroute
# health
Invoke-RestMethod -Uri http://localhost:8000/health/ready
```

Endpoints úteis:

- `GET /health` — checa estado geral.
- `GET /health/live` — liveness probe.
- `GET /health/ready` — readiness probe (usado pelo healthcheck do container).
- `POST /webhook/simpliroute` — webhook (protegido por `SIMPLIROUTE_WEBHOOK_TOKEN` se configurado).

Notas sobre Gnexum:

- A implementação atual tenta `POST` primeiro com vários formatos de corpo (ex: `{idregistro}`, `{record_id}`, `{id}`) e, em seguida, tenta `GET` como fallback.
- Os resultados são normalizados para um array `items` usado no `Visit` enviado ao SimpliRoute.

Testes:

- Executar `pytest` para executar os testes adicionados (ex.: `tests/test_smoke.py`).

Se quiser que eu teste chamadas reais ao Gnexum, confirme que o `GNEXUM_API_URL` e `GNEXUM_TOKEN` são válidos e estão acessíveis a partir do container; eu posso executar o teste a seguir.
