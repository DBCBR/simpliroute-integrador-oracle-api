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
        # prune body to only fields expected by SimpliRoute to avoid sending extra info
        allowed_visit_fields = [
            "order","tracking_id","status","title","address","latitude","longitude",
            "load","load_2","load_3","window_start","window_end","window_start_2","window_end_2",
            "duration","contact_name","contact_phone","contact_email","reference","notes",
            "skills_required","skills_optional","tags","planned_date","programmed_date","route",
            "estimated_time_arrival","estimated_time_departure","checkin_time","checkout_time",
            "checkout_latitude","checkout_longitude","checkout_comment","checkout_observation",
            "signature","pictures","created","modified","eta_predicted","eta_current",
            "priority","has_alert","priority_level","extra_field_values","geocode_alert",
            "visit_type","current_eta","fleet","seller","properties","items","on_its_way"
        ]

        allowed_item_fields = [
            "id","title","status","load","load_2","load_3","reference","visit",
            "notes","quantity_planned","quantity_delivered"
        ]

        def prune_visit(v: dict) -> dict:
            out = {}
            for k in allowed_visit_fields:
                if k in v and v[k] is not None:
                    # copy only allowed keys
                    out[k] = v[k]
            # prune properties subkeys if present: keep only expected property keys
            if "properties" in out and isinstance(out["properties"], dict):
                props = out["properties"]
                kept = {k: props[k] for k in props if k in ("PROFISSIONAL", "ESPECIALIDADE", "PERIODICIDADE")}
                if kept:
                    out["properties"] = kept
                else:
                    out.pop("properties", None)
            # prune items
            if "items" in out and isinstance(out["items"], list):
                items = []
                for it in out["items"]:
                    if not isinstance(it, dict):
                        continue
                    newi = {k: it[k] for k in allowed_item_fields if k in it and it[k] is not None}
                    if newi:
                        items.append(newi)
                if items:
                    out["items"] = items
                else:
                    out.pop("items", None)
            return out

        if isinstance(body, list):
            pruned = [prune_visit(v) for v in body]
        else:
            pruned = prune_visit(body)

        content = dumps_utf8(pruned)
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
