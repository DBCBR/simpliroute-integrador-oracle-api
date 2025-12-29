# Integrador SimpliRoute (IW)

Este projeto integra sistemas internos com a plataforma SimpliRoute, realizando envio e recebimento de dados via API e Webhook. Ele é composto principalmente por dois módulos: um servidor de webhook (FastAPI) e um script de envio de dados para a SimpliRoute.

## Principais Arquivos

- **simpliroute_webhook_server.py**  
  Servidor FastAPI que recebe notificações (webhooks) da SimpliRoute.
  - Carrega variáveis de ambiente do arquivo `settings/.env`.
  - Expõe rotas para recebimento de webhooks e health check.
  - Realiza logging estruturado e tratamento de erros.
  - Integra com banco Oracle para persistência e consulta de dados.
  - Armazena logs de erro em `simpliroute_webhook_error_logs/` e logs estruturados em `logs/`.

- **simpliroute_send.py**  
  Script responsável por enviar dados (entregas, visitas, etc.) para a API da SimpliRoute.
  - Utiliza helpers para normalização e formatação dos dados.
  - Lê configurações e credenciais do arquivo `.env`.
  - Realiza integração com banco Oracle para buscar dados a serem enviados.
  - Gera logs e arquivos de saída em `data/output/`.

- **send_helper.py**  
  Biblioteca de funções auxiliares para manipulação, normalização e validação de dados enviados/recebidos.

## Configuração

### Variáveis de Ambiente

As configurações sensíveis e de ambiente estão em `settings/.env`. Exemplo de variáveis:

```
ORACLE_HOST=10.1.1.12
ORACLE_PORT=1521
ORACLE_SERVICE=dbprod
ORACLE_USER=usuario
ORACLE_PASS=senha
SIMPLIROUTE_TOKEN=token_api
SIMPLIROUTE_API_BASE=https://api.simpliroute.com/
```

### Dependências

As dependências estão listadas em `requirements.txt`:

- fastapi
- uvicorn
- oracledb
- SQLAlchemy
- python-dotenv
- httpx
- apscheduler
- PyYAML

Instale com:

```bash
pip install -r requirements.txt
```

## Como Executar

### 1. Servidor de Webhook

Inicie o servidor FastAPI para receber webhooks:

```bash
uvicorn simpliroute_webhook_server:app --host 0.0.0.0 --port 8000
```

### 2. Envio de Dados

Execute o script de envio para a SimpliRoute:

```bash
python simpliroute_send.py
```

## Estrutura de Pastas

- `data/output/` — Armazena arquivos JSON de payloads enviados.
- `logs/` — Logs estruturados do sistema.
- `simpliroute_webhook_error_logs/` — Logs de erros do webhook.
- `settings/` — Configurações e dependências do Oracle Client.

## Observações

- Certifique-se de configurar corretamente o Oracle Instant Client conforme o SO.
- O projeto utiliza logging detalhado para facilitar troubleshooting.
- Não compartilhe o arquivo `.env` publicamente, pois contém credenciais sensíveis.
