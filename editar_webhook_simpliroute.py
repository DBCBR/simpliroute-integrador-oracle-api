import os
import json
import requests
from typing import Optional, Dict, Any

SIMPLIROUTE_WEBHOOKS_URL = "https://api.simpliroute.com/v1/addons/webhooks/"
# https://api-v2.otimize.med.br


class SimpliRouteWebhookError(RuntimeError):
    pass


def _request(
    method: str,
    token: str,
    payload: Dict[str, Any],
    timeout: int = 15,
) -> requests.Response:
    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }
    return requests.request(
        method=method,
        url=SIMPLIROUTE_WEBHOOKS_URL,
        headers=headers,
        data=json.dumps(payload),
        timeout=timeout,
    )


def create_or_update_webhook(
    token: str,
    event_name: str,
    target_url: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Cria um webhook no SimpliRoute (POST). Se já existir, atualiza (PUT).
    Retorna o JSON da resposta quando disponível.
    """
    payload = {
        "webhook": event_name,
        "url": target_url,
        "headers": {
            "Content-Type": "application/json",
            **(extra_headers or {}),
        },
    }

    # 1) tenta criar (POST)
    resp = _request("POST", token, payload)

    if resp.ok:
        # Alguns endpoints retornam JSON; outros podem retornar vazio
        try:
            return resp.json()
        except ValueError:
            return {"status_code": resp.status_code, "text": resp.text}

    # 2) se falhar, tenta atualizar (PUT) — comum quando já existe
    # (Se a API retornar um erro diferente, você ainda vai ver abaixo.)
    resp_put = _request("PUT", token, payload)

    if resp_put.ok:
        try:
            return resp_put.json()
        except ValueError:
            return {"status_code": resp_put.status_code, "text": resp_put.text}

    # 3) se ambos falharem, lança erro com detalhes
    raise SimpliRouteWebhookError(
        "Falha ao criar/atualizar webhook.\n"
        f"POST => {resp.status_code}: {resp.text}\n"
        f"PUT  => {resp_put.status_code}: {resp_put.text}"
    )


def list_webhooks(token: str) -> Dict[str, Any]:
    """
    Lista configurações atuais de webhooks do add-on.
    """
    headers = {"Authorization": f"Token {token}", "Content-Type": "application/json"}
    resp = requests.get(SIMPLIROUTE_WEBHOOKS_URL, headers=headers, timeout=15)
    if not resp.ok:
        raise SimpliRouteWebhookError(f"Falha no GET => {resp.status_code}: {resp.text}")
    return resp.json()


if __name__ == "__main__":
    # Pegue o token do ambiente para não vazar no código:
    # Linux/macOS: export SIMPLIROUTE_TOKEN="..."
    # Windows PS:  $env:SIMPLIROUTE_TOKEN="..."
    token = "b9f38f3d5d85763de9d76dc0f063ea987497d354"
    if not token:
        raise SystemExit("Defina a env SIMPLIROUTE_TOKEN com seu token da SimpliRoute.")

    event = "visit_checkout_detailed"
    ngrok_url = "https://api-v2.otimize.med.br"
    #ngrok_url = "https://dissatisfied-nonnationally-jesse.ngrok-free.dev"


    result = create_or_update_webhook(
        token=token,
        event_name=event,
        target_url=ngrok_url,
    )
    print("Webhook criado/atualizado:", json.dumps(result, indent=2, ensure_ascii=False))

    current = list_webhooks(token)
    print("\nConfig atual de webhooks:", json.dumps(current, indent=2, ensure_ascii=False))
