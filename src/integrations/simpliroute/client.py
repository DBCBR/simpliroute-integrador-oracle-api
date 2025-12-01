import os
from typing import Any, Dict, Iterable, List, Optional

import httpx
from core.encoding import dumps_utf8


def _get_token(names: Iterable[str]) -> str:
    for n in names:
        val = os.getenv(n)
        if val:
            return val
    return ""


async def post_simpliroute(route_payload: Dict[str, Any]) -> Optional[httpx.Response]:
    """Envia um ou vários visits ao endpoint `/v1/routes/visits/`.

    Aceita tanto um dict (será embrulhado em lista) quanto uma lista.
    Usa header `Authorization: Token <token>` conforme documentação.
    Procura por várias variações de variável de ambiente para compatibilidade.
    """
    # suportar múltiplos nomes de env para compatibilidade
    base = os.getenv("SIMPLIROUTE_API_BASE") or os.getenv("SIMPLIR_ROUTE_BASE_URL") or os.getenv("SIMPLIROUTE_API_BASE_URL") or "https://api.simpliroute.com"
    token = _get_token(["SIMPLIROUTE_TOKEN", "SIMPLIR_ROUTE_TOKEN", "SIMPLIROUTE_API_TOKEN"])

    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Token {token}"

    # garantir que enviamos uma lista conforme exemplos da API
    body: List[Dict[str, Any]]
    if isinstance(route_payload, list):
        body = route_payload
    else:
        body = [route_payload]

    try:
        content = dumps_utf8(body)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{base.rstrip('/')}/v1/routes/visits/", content=content, headers=headers)
        return resp
    except Exception:
        return None


async def post_gnexum_update(payload: Dict[str, Any]) -> Optional[httpx.Response]:
    # Placeholder: Gnexum endpoint must be configured by the user
    url = os.getenv("GNEXUM_BASE_URL", "https://api.gnexum.local")
    token = _get_token(["GNEXUM_TOKEN"])
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{url.rstrip('/')}/updates/status", json=payload, headers=headers)
        return resp
    except Exception:
        # Em ambiente de teste/sem configuração, falhas de rede não devem
        # quebrar a aplicação. Log e retorne None para indicar falha.
        return None
