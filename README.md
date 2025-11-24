# Integrador SR — Integração SimpliRoute

Integração entre o sistema IW (Gnexum) e a plataforma SimpliRoute.
Este repositório contém um serviço Python mínimo que implementa:

- Endpoint webhook para receber notificações do SimpliRoute.
- Tarefa de polling configurável para buscar registros no Gnexum.
- Clientes HTTP e mapeadores para construir payloads conforme o PDD.

IMPORTANTE: não commite credenciais. Utilize `settings/.env` (arquivo
excluído do controle de versão) para configurar tokens localmente.

---

## Novidades nesta branch

Esta branch adiciona suporte básico de autenticação com o Gnexum e
facilita testes locais:

- `src/integrations/simpliroute/token_manager.py`: helper para fazer
  login (quando credenciais fornecidas), armazenar `GNEXUM_TOKEN` e
  `GNEXUM_REFRESH_TOKEN` em `settings/.env` (com fallback para memória
  quando o volume está montado como read-only).
- Integração do token manager em `gnexum.py` (uso de `get_token()` e
  retry automático em caso de 401).
- Tarefa em background no `lifespan` do FastAPI que chama
  `get_token()` periodicamente para manter o token válido em memória.
- Alteração no `docker-compose.yml` (dev): monta `./settings` como
  volume gravável para permitir persistência de tokens locais.
- `scripts/e2e_run.py`: utilitário para executar um teste end-to-end
  (buscar items no Gnexum, mapear e enviar ao SimpliRoute).

> Observação: para produção recomendamos usar um secret manager e não
> persistir tokens em arquivos do repositório.

---

## Estrutura do repositório

- `src/` — código fonte do serviço e integrações.
- `settings/` — arquivo `config.yaml` e variáveis de ambiente locais.
- `data/` — arquivos de input/output e dados gerados (não versionados).
- `tests/` — testes unitários.

---

## Requisitos

- Python 3.11+
- Dependências listadas em `requirements.txt`.

Recomendado: criar um virtualenv antes de instalar as dependências.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Configuração local

1. Copie/prepare o arquivo `settings/.env` localmente (não commite):

```powershell
copy settings\.env.example settings\.env
```

2. Preencha as variáveis necessárias — variáveis úteis:

- `GNEXUM_API_URL` — endpoint de leitura do Gnexum (ex.: eventos).
- `GNEXUM_TOKEN`, `GNEXUM_REFRESH_TOKEN`, `GNEXUM_EXPIRES_IN` — podem
  ser preenchidos manualmente para teste, ou gerados pelo
  `token_manager` se fornecer `GNEXUM_LOGIN_URL` e credenciais.
- (Opcional) `GNEXUM_LOGIN_URL`, `GNEXUM_LOGIN_USERNAME`,
  `GNEXUM_LOGIN_PASSWORD` ou `GNEXUM_LOGIN_PAYLOAD` — necessários para
  login automático.

O arquivo `settings/.env` está listado no `.gitignore`.

---

## Como testar localmente (rápido)

1) Subir containers (recria e rebuild):

```powershell
docker-compose up -d --build --force-recreate
```

2) Verificar health:

```powershell
docker ps --filter "name=simpliroute_service"
curl http://localhost:8000/health/ready
```

3) Teste rápido do Gnexum usando o token presente em `settings/.env`:

```powershell
python scripts/probe_use_env.py
# ou dentro do container
docker exec simpliroute_service python scripts/probe_use_env.py
```

4) Teste end-to-end (Gnexum -> SimpliRoute):

```powershell
# dentro do container (recomendado para usar o mesmo ambiente)
docker exec simpliroute_service python scripts/e2e_run.py
```

O `e2e_run` mostrará os items buscados, o payload montado e a resposta do
SimpliRoute. Nota: SimpliRoute exige `address` não-vazio — se o registro
do Gnexum não fornecer endereço, o envio retornará 400. Para teste, pode
ser necessário preencher `address` no payload de teste ou ajustar o
mapper.

---

## Observações de segurança e produção

- Atualmente, por conveniência de desenvolvimento, `docker-compose.yml`
  monta `./settings` como um volume gravável para permitir persistir o
  `settings/.env`. Em ambiente de produção, substitua esse fluxo por um
  secret manager (Docker secrets, Kubernetes Secrets, Azure Key Vault,
  etc.) e remova a montagem de `settings` como gravável.
- Nunca comite `settings/.env` nem tokens no repositório.

---

## Sugestões de próximos passos

- Implementar persistência segura via secret manager (PR separada).
- Adicionar logs/metrics no `token_manager` e observar falhas de login.
- Criar testes de integração automatizados que usem um mock do SimpliRoute
  para validar payloads.

---

Se quiser, eu adiciono um README específico em
`src/integrations/simpliroute/` com exemplos de payloads e campos
esperados pelo SimpliRoute.
# Integrador SR — Integração SimpliRoute

Integração entre o sistema IW (Gnexum) e a plataforma SimpliRoute.
Este repositório contém um serviço Python mínimo que implementa:

- Endpoint webhook para receber notificações do SimpliRoute.
- Tarefa de polling configurável para buscar registros no Gnexum.
- Clientes HTTP e mapeadores para construir payloads conforme o PDD.

IMPORTANTE: não commite credenciais. Utilize `settings/.env` (a partir de
`settings/.env.example`) para configurar tokens localmente.

---

## Estrutura do repositório

- `src/` — código fonte do serviço e integrações.
- `settings/` — arquivo `config.yaml` e exemplo de variáveis de ambiente.
- `data/` — arquivos de input/output e dados gerados (não versionados).
- `tests/` — testes unitários.

---

## Requisitos

- Python 3.11+
- Dependências listadas em `requirements.txt`.

Recomendado: criar um virtualenv antes de instalar as dependências.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## Configuração local

1. Copie o arquivo de exemplo de variáveis de ambiente:

```powershell
copy settings\.env.example settings\.env
```

2. Preencha `settings/.env` com os tokens necessários (não commite este
   arquivo). O arquivo `Pendencias.txt` contém tokens locais — mantenha
   este arquivo fora do controle de versão.

---

## Executando em desenvolvimento

```powershell
# executar a API com uvicorn
python -m uvicorn src.integrations.simpliroute.app:app --host 0.0.0.0 --port 8000
```

O webhook ficará disponível em `http://localhost:8000/webhook/simpliroute`.

---

## Docker (desenvolvimento)

O projeto inclui `Dockerfile` e `docker-compose.yml`. Para subir o serviço:

```powershell
docker-compose build
docker-compose up -d
```

Parar e remover:

```powershell
docker-compose down
```

OBS: o `docker-compose.yml` usa `settings/.env` como `env_file`. Não
commite variáveis sensíveis.

---

## Testes

Executar a suíte de testes com `pytest`:

```powershell
pytest -q
```

---

## Fluxo de contribuição

- Crie branches a partir de `dev` para cada feature: `feature/<nome>`.
- Faça merge das features em `dev` após revisão; apague a branch de
  feature depois do merge (o `dev` permanece até aprovação para `main`).

---

## Referências

- Documento PDD: `📄 PDD - Integração SimpliRoute (IW).md` (detalhes funcionais).

---

Se quiser, posso adicionar um README menor em `src/integrations/simpliroute/`
com exemplos de payload e instruções específicas da integração.
