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
