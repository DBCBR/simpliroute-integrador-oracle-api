# Integrador SR → SimpliRoute

Ferramenta de linha de comando para coletar registros das views Oracle disponibilizadas pelo IW, mapear para o formato do SimpliRoute e enviar/visualizar os payloads gerados.

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

## Execução automática via Docker
- O `Dockerfile` e os arquivos `docker-compose*.yml` executam `python -m src.cli.send_to_simpliroute auto` por padrão, ou seja, o container já dispara `send --send` assim que sobe.
- Para alterar o comando executado automaticamente, defina `SIMPLIROUTE_AUTO_COMMAND` (ex.: `preview --limit 5`) no `settings/.env` ou passe `--command` ao chamar `python -m src.cli.send_to_simpliroute auto`.
- Se quiser apenas inspecionar os payloads sem enviar, defina `SIMPLIROUTE_DRY_RUN=1` no mesmo arquivo ou remova a flag `--send` no valor de `SIMPLIROUTE_AUTO_COMMAND`.
- A execução manual permanece disponível: basta rodar `python -m src.cli.send_to_simpliroute <subcomando>` em qualquer ambiente com Python.
- Compose oferece serviços prontos:
	- `simpliroute_cli` (ou `integrador` no `docker-compose.prod.yml`): fluxo completo, envia todos os registros respeitando `ORACLE_FETCH_LIMIT`.
	- `simpliroute_cli_limit1` / `integrador_limit1`: envia apenas 1 visita + 1 entrega (`send --limit 1 --send`).
	- `simpliroute_cli_preview` / `integrador_preview`: gera payloads sem enviar (`preview`).
	- `simpliroute_cli_preview_limit1` / `integrador_preview_limit1`: preview limitado a 1 registro por view.
- Para executar basta escolher o serviço, por exemplo `docker compose up simpliroute_cli_limit1` ou `docker compose -f docker-compose.prod.yml up integrador_preview`.

## Estrutura do Oracle Instant Client
- Coloque os pacotes dentro de `settings/instantclient/`:
	- `settings/instantclient/windows/`: descompacte aqui o Instant Client usado no Windows (por exemplo `instantclient_23_0`).
	- `settings/instantclient/linux/`: armazene os `.zip` do Instant Client Linux (Basic/Basic Lite). O `Dockerfile` os instalará em `/opt/oracle/instantclient` automaticamente.
- Se `ORACLE_INSTANT_CLIENT` não estiver definido, o CLI procura automaticamente em `settings/instantclient/windows/instantclient_*`. Ainda é possível definir a variável manualmente caso o cliente esteja em outro caminho.
