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
- O compose `docker-compose.prod.yml` monta `settings` como leitura (`ro`) e `data/output` como leitura/gravação para que os artefatos dry-run sejam persistidos no host.
- Variáveis importantes forçadas no compose:
  - `USE_GNEXUM_DB=1` — usa leitura via Oracle DB (views configuradas).
  - `SIMPLIROUTE_DRY_RUN=1` — evita posts reais ao SimpliRoute.
  - `DRY_RUN_SAVE_PAYLOADS=1` — salva payloads em `data/output` para revisão.

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
docker compose -f docker-compose.prod.yml up -d
# Acompanhar logs:
docker compose -f docker-compose.prod.yml logs -f
```

Se o host tiver apenas o `docker-compose` binário:

```bash
docker-compose -f docker-compose.prod.yml build --pull --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

4. Parar a stack:

```bash
docker compose -f docker-compose.prod.yml down
```

**Executar fetch DB one-off (gerar payloads imediatamente)**

```bash
# Executa o script que busca do DB, mapeia e salva payloads em data/output
docker compose -f docker-compose.prod.yml run --rm integrador python tests/run_db_fetch_all.py --page-size 100 --max-pages 0
```

- `--max-pages 0` pode significar "sem limite" dependendo do script; ajustar conforme necessário.

**Onde os artefatos aparecem**
- `data/output/` no host (montado pelo compose) conterá os arquivos `visits_db_*_dryrun_*.json` e subpastas com requests simulados.

**Notas para infra**
- Se preferirem não copiar o ZIP para o repositório, podem extrair o Instant Client num diretório do host (ex: `/opt/oracle/instantclient`) e montar esse diretório para `/opt/oracle/instantclient` dentro do container adicionando um `volumes` override no `docker-compose.prod.yml` ou via `docker compose run -v /opt/oracle/instantclient:/opt/oracle/instantclient:ro ...`.
- Certificar-se que o usuário que roda o container tem acesso de escrita ao `./data/output`.

**Suporte**
- Se quiser, eu posso abrir um branch com estes arquivos e criar um PR para `dev` (workflow: branch → PR → merge). Quer que eu faça o commit e abra o PR? Caso contrário, a equipe de infra pode copiar estes arquivos direto no servidor.
