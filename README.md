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

## Execução em modo seguro (dry-run)

Para testar o polling e a geração de payloads sem enviar nada ao SimpliRoute, use o runner in-process criado:

```powershell
# ativar virtualenv
& ".\.venv\Scripts\Activate.ps1"
# rodar por 60 segundos (salva payloads em data/output/payloads)
$env:RUN_DURATION_SECONDS=60
$env:RUN_POLLING_INTERVAL_MINUTES=1
python scripts/run_polling_inprocess.py
```

O runner fará chamadas reais ao Gnexum (autenticado com `settings/.env`) para buscar items, mas irá simular e SALVAR os payloads em `data/output/payloads/` em vez de enviá-los ao SimpliRoute.

Use `RUN_POLLING_INTERVAL_MINUTES` para ajustar o intervalo do polling durante testes, e `RUN_DURATION_SECONDS` para limitar o tempo de execução.

Por padrão o comportamento de persistência é controlado por `settings/config.yaml` em `simpliroute.save_payloads` (padrão `true`). Quando habilitado, além dos arquivos JSON em `data/output/payloads/`, o runner grava um CSV resumo em `data/output/payloads_summary.csv` contendo: `ts, source_ident, title, filename, status_code`.

---

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
