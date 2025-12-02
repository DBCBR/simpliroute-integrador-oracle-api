**Scripts Overview**
- **Propósito:** conter os pequenos utilitários e runners necessários para operar o integrador Gnexum → SimpliRoute.
- **Localização:** `scripts/` (conservamos apenas os scripts operacionais mínimos).

**Preservados**:
- `scripts/run_polling_inprocess.py` : runner dry-run que busca registros (stub ou Gnexum real), gera payloads e grava artefatos em `data/output/`.
- `scripts/send_one_to_simpliroute.py` : utilitário para enviar um único payload (guardado por `SEND_CONFIRM`).
- `scripts/token_refresher.py` : processo opcional que chama periodicamente o refresh/login para manter `GNEXUM_TOKEN` atualizado.
- `scripts/update_env_with_login.py` : script para executar login manual e persistir tokens em `settings/.env`.

**Comportamento importante**
- Por padrão o runner roda em `dry-run` e NÃO faz chamadas reais ao SimpliRoute.
- Para ativar chamadas reais ao Gnexum defina `USE_REAL_GNEXUM=1` e garanta que as variáveis de conexão estejam corretas.
- O `token_manager` agora tenta `refresh` usando `GNEXUM_REFRESH_TOKEN` antes de fazer um login completo.

**Variáveis de ambiente relevantes**
- `GNEXUM_LOGIN_URL` : URL do endpoint de login (ex.: `https://gnexum.example.com/api/auth/login`).
- `GNEXUM_LOGIN_USERNAME` / `GNEXUM_LOGIN_PASSWORD` ou `GNEXUM_LOGIN_PAYLOAD` : credenciais ou payload JSON.
- `GNEXUM_REFRESH_TOKEN` : refresh token (opcional, obtido após login se disponível).
- `GNEXUM_TOKEN_REFRESH_URL` ou `GNEXUM_REFRESH_URL` : endpoint para renovar token (se existir).
- `GNEXUM_API_URL` : endpoint base/consulta para obter registros (usado por `run_polling_inprocess.py`).
- `USE_REAL_GNEXUM` : `1` para usar Gnexum real; por padrão `0` (dry-run).
- `DRY_RUN_SAVE_PAYLOADS` : `1` para salvar payloads em `data/output/payloads`.
- `DRY_RUN_PRINT_ONLY` : `1` para apenas imprimir previews em vez de gravar arquivos.
- `SIMPLIR_ROUTE_TOKEN` : token do SimpliRoute (usado apenas quando enviar realmente).
- `SEND_CONFIRM` : quando setado em `1` habilita envio real no utilitário de envio único.

**Comandos úteis (PowerShell)**
- Obter token manual e persistir em `settings/.env`:
```powershell
$env:GNEXUM_LOGIN_URL='https://gnexum.example.com/api/auth/login'
# definir credenciais via env ou editar settings/.env
python .\scripts\update_env_with_login.py
```

- Rodar o runner em dry-run (gera artefatos em `data/output/`):
```powershell
$env:USE_REAL_GNEXUM='0'
python .\scripts\run_polling_inprocess.py
```

- Rodar o runner usando Gnexum real (APENAS quando as credenciais estiverem corretas):
```powershell
$env:USE_REAL_GNEXUM='1'
python .\scripts\run_polling_inprocess.py
```

- Iniciar o token refresher em background (mantém token atualizado usando refresh/login):
```powershell
python .\scripts\token_refresher.py
```

**Como validar o fluxo de refresh**
- Configure `GNEXUM_LOGIN_URL` e faça login uma vez com `update_env_with_login.py`.
- Se a resposta de login fornecer `refresh_token`, ele ficará salvo em `settings/.env`.
- O `token_manager.get_token()` tentará `refresh_and_store()` antes de iniciar um novo login completo.

**Limpeza de artefatos**
- Os artefatos de dry-run ficam em `data/output/payloads/` e `data/output/simulated_requests/`.
- Para apagar artefatos manualmente:
```powershell
Remove-Item -Recurse -Force data\output\payloads\*;
Remove-Item -Recurse -Force data\output\simulated_requests\*;
```

**Observações finais**
- Preservamos apenas o conjunto mínimo de scripts operacionais; se quiser que eu restaure algum utilitário específico ou adicione um teste de integração para o fluxo de refresh, eu posso implementar na sequência.

---
Arquivo gerado automaticamente como parte da limpeza do repositório.
