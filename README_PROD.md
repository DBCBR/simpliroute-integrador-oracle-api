# Deploy Produção (modo *production-like*, apenas dry-run)

Este arquivo descreve os passos mínimos para a equipe de infra executar a aplicação num host Linux em modo "production-like" mas sem postar dados reais ao SimpliRoute (variáveis de ambiente configuradas para dry-run).

**Pré-requisitos (infra)**
- Docker Engine e Docker Compose (plugin `docker compose`) instalados no host Linux.
- Arquivo `settings/.env` com as variáveis de ambiente de produção (protegido, não commitar).
- Oracle Instant Client ZIP (ex: `instantclient-basic-linux.x64-23.26.0.0.0.zip`) fornecido pelo time de segurança/infra.
  - Colocar o ZIP em `settings/instantclient/` na raiz do projeto antes de buildar a imagem (a `Dockerfile` do projeto já tenta extrair o ZIP durante o build).

**Segurança**
- Nunca commitar chaves, senhas ou o `settings/.env` no repositório.
- Recomenda-se que o `settings/.env` seja fornecido via um caminho seguro no host (ex: diretório montado somente para o processo Docker).

**Como o deploy funciona (visão rápida)**
- A imagem é construída a partir da `Dockerfile` do repositório. Se o Instant Client estiver presente em `settings/instantclient/*.zip`, o build extrai os bins e ativa o modo "thick" do `python-oracledb`.
- O compose `docker-compose.prod.yml` monta `settings` como leitura (`ro`) e `data/output` / `data/work` como leitura/gravação para que os artefatos dry-run e os logs/webhooks do serviço sejam persistidos no host.
- Variáveis importantes forçadas no compose:
  - `SIMPLIROUTE_DRY_RUN=1` — evita posts reais ao SimpliRoute durante smoke-tests.
  - `DRY_RUN_SAVE_PAYLOADS=1` — salva payloads em `data/output` para revisão.
  - `POLLING_INTERVAL_MINUTES=60` — executa o ciclo automático a cada hora.

**Passos para executar (Linux)**
1. Colocar o Instant Client ZIP no host (exemplo):

```bash
mkdir -p settings/instantclient
cp /secure/location/instantclient-basic-linux.x64-23.26.0.0.0.zip settings/instantclient/
```

2. Confirmar que `settings/.env` foi colocado com permissões restritas (ex: 600) e contém as variáveis ORACLE_* e SIMPLIROUTE_* necessárias.

3. Build e start com Docker Compose (recomendado):

```bash
# Se sua instalação usa o plugin moderno:
docker compose -f docker-compose.prod.yml build --pull --no-cache
docker compose -f docker-compose.prod.yml up -d integrador_service
# Acompanhar logs do serviço contínuo:
docker compose -f docker-compose.prod.yml logs -f integrador_service
```

Se o host tiver apenas o `docker-compose` binário:

```bash
docker-compose -f docker-compose.prod.yml build --pull --no-cache
docker-compose -f docker-compose.prod.yml up -d integrador_service
```

4. Parar a stack:

```bash
docker compose -f docker-compose.prod.yml down
```

**Onde os artefatos aparecem**
- `data/output/` no host (montado pelo compose) conterá os arquivos `visits_db_*_dryrun_*.json` e subpastas com requests simulados.
- `data/work/` armazenará `service_events.log` e os JSONs recebidos pelo webhook (`data/work/webhooks/`).

**Notas para infra**
- Se preferirem não copiar o ZIP para o repositório, podem extrair o Instant Client num diretório do host (ex: `/opt/oracle/instantclient`) e montar esse diretório para `/opt/oracle/instantclient` dentro do container adicionando um `volumes` override no `docker-compose.prod.yml` ou via `docker compose run -v /opt/oracle/instantclient:/opt/oracle/instantclient:ro ...`.
- Certificar-se que o usuário que roda o container tem acesso de escrita a `./data/output` **e** `./data/work`.

**Procedimento de teste sem envios reais**

Adicionamos uma forma segura de a equipe de infra executar smoke-tests sem postar dados ao SimpliRoute:

- Arquivo: `settings/.env.test` (presente no repositório). Deve conter:
  - `SIMPLIR_ROUTE_TOKEN=` (vazio)
  - `SIMPLIROUTE_POLL_WHERE=1=0`
  - `SIMPLIROUTE_DISABLE_SEND=1`

- Override compose: `docker-compose.test.yml` força `SIMPLIROUTE_AUTO_COMMAND: "preview"` nos serviços CLI.

- Comando de exemplo (Linux):

```bash
docker compose -f docker-compose.prod.yml -f docker-compose.test.yml --env-file settings/.env.test up -d --build
```

- Confirmação de que nada foi enviado:
  - `docker compose -f docker-compose.prod.yml -f docker-compose.test.yml --env-file settings/.env.test logs --tail 200`
  - `ls data/output | grep send_to_sr_`

Observação: a combinação de token vazio + `SIMPLIROUTE_DISABLE_SEND=1` + override `preview` é defesa em profundidade para evitar envios acidentais durante testes.

**Suporte**
- Se quiser, eu posso abrir um branch com estes arquivos e criar um PR para `dev` (workflow: branch → PR → merge). Quer que eu faça o commit e abra o PR? Caso contrário, a equipe de infra pode copiar estes arquivos direto no servidor.
