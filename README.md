# Integrador SR → SimpliRoute

Ferramenta de linha de comando para coletar registros das views Oracle disponibilizadas pelo IW, mapear para o formato do SimpliRoute e enviar/visualizar os payloads gerados. O repositório também inclui um serviço FastAPI que roda continuamente (polling + webhook) para automatizar o fluxo a cada hora.

## Execução principal
- Configure as variáveis de ambiente ORACLE_* e SIMPLIROUTE_* conforme `settings/config.yaml`.
- Rode `python -m src.cli.send_to_simpliroute preview` para gerar payloads sem enviá-los (o CLI salva em `data/output/`).
- Rode `python -m src.cli.send_to_simpliroute send --send` para gerar e enviar os payloads ao SimpliRoute.
- O subcomando `auto` executa automaticamente um comando pré-configurado (padrão=`send --send`).

## Origem padrão dos dados
- A CLI agora consulta o Oracle **por padrão**, usando as views definidas nas variáveis `ORACLE_VIEW_*` ou `ORACLE_VIEWS`.
- Não é mais necessário informar `--from-db`. Esse parâmetro passa a ser apenas um atalho opcional para explicitar o comportamento padrão.
- Para usar um arquivo local com registros (por exemplo, exportados de um teste anterior), informe `--file caminho/do/arquivo.json`. Quando `--file` é usado, nenhuma consulta ao Oracle é realizada.
- As opções `--view` e `--views` só estão disponíveis quando a origem é o Oracle (isto é, quando `--file` não foi passado).

## Demais flags úteis
- `--limit`: controla quantos registros são lidos por view (padrão definido por `ORACLE_FETCH_LIMIT`, caindo para 25 se ausente).
- `--where`: injeta um filtro adicional na consulta Oracle (por exemplo, `--where "DT_ENTREGA >= SYSDATE - 1"`).
- `--no-save`: exibe os payloads no stdout em vez de gravar arquivo ao rodar `preview`.
- `--send`: habilita o envio HTTP ao SimpliRoute quando usando o subcomando `send`.

Consulte `python -m src.cli.send_to_simpliroute --help` para detalhes completos.

### Tipos de visita enviados ao SimpliRoute
- Visitas médicas são marcadas automaticamente como `visit_type = med_visit`.
- Visitas de enfermagem usam `visit_type = enf_visit`.
- Entregas (`TPREGISTRO = 2` ou views `ENTREGAS`) enviam `visit_type = rota_log`.
- Valores diferentes vindos do IW são ignorados para manter o catálogo alinhado às tags homologadas pelo time Solar Cuidados.

## Execução automática via Docker
- O `Dockerfile` e os arquivos `docker-compose*.yml` oferecem dois perfis:
	- Serviços `simpliroute_cli*` / `integrador*` para execuções sob demanda do CLI (comando `python -m src.cli.send_to_simpliroute auto`).
	- `simpliroute_service` / `integrador_service` para o processo contínuo FastAPI (polling + webhook) que roda 24/7 e expõe `http://localhost:8000`.
- Os serviços contínuos já incluem healthcheck (`/health/live`) e montam `data/work/` para persistir logs/webhooks.
- Para alterar o comando executado automaticamente no CLI, defina `SIMPLIROUTE_AUTO_COMMAND` (ex.: `preview --limit 5`).
- Para o serviço FastAPI, ajuste `POLLING_INTERVAL_MINUTES`, `SIMPLIROUTE_POLLING_LIMIT` e as variáveis do webhook no `settings/.env`.
- Exemplos de uso:
	- `docker compose up simpliroute_cli_limit1`
	- `docker compose up simpliroute_service`
	- `docker compose -f docker-compose.prod.yml up integrador_service`

### Teste manual do webhook
- Com o serviço rodando (local ou via Docker), envie um payload de teste usando `tests/manual/webhook_sample.http` (compatível com a extensão REST Client) ou adapte-o para `curl`/PowerShell.
- Lembre-se de preencher o header `Authorization: Bearer <SIMPLIR_ROUTE_WEBHOOK_TOKEN>` se a variável estiver configurada.
- Verifique `data/work/webhooks/` e a tabela `SIMPLIROUTE_STATUS_LOG` para confirmar o recebimento.

## Estrutura do Oracle Instant Client
- Coloque os pacotes dentro de `settings/instantclient/`:
	- `settings/instantclient/windows/`: descompacte aqui o Instant Client usado no Windows (por exemplo `instantclient_23_0`).
	- `settings/instantclient/linux/`: armazene os `.zip` do Instant Client Linux (Basic/Basic Lite). O `Dockerfile` os instalará em `/opt/oracle/instantclient` automaticamente.
- Se `ORACLE_INSTANT_CLIENT` não estiver definido, o CLI procura automaticamente em `settings/instantclient/windows/instantclient_*`. Ainda é possível definir a variável manualmente caso o cliente esteja em outro caminho.
