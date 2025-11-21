import os
from typing import Any, Dict

import httpx


def _get_token(name: str) -> str:
    return os.getenv(name, "")


async def post_simpliroute(route_payload: Dict[str, Any]) -> httpx.Response:
    url = os.getenv("SIMPLIR_ROUTE_BASE_URL") or "https://api.simpliroute.com"
    token = _get_token("SIMPLIR_ROUTE_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{url}/v1/routes/visits/", json=route_payload, headers=headers)
    return resp


async def post_gnexum_update(payload: Dict[str, Any]) -> httpx.Response:
    # Placeholder: Gnexum endpoint must be configured by the user
    url = os.getenv("GNEXUM_BASE_URL", "https://api.gnexum.local")
    token = _get_token("GNEXUM_TOKEN")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{url}/updates/status", json=payload, headers=headers)
    return resp
