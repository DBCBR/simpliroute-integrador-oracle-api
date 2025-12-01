import os
import logging
from typing import Any, Dict, List
import httpx

# Config via env
GNEXUM_URL = os.getenv("GNEXUM_API_URL")
USE_REAL_GNEXUM = os.getenv("USE_REAL_GNEXUM", "false").lower() in ("1", "true", "yes")
logger = logging.getLogger(__name__)

from .token_manager import get_token, login_and_store


async def fetch_items_for_record(record_id: Any, timeout: int = 8) -> List[Dict[str, Any]]:
    """Tenta buscar items para um registro no Gnexum.

    Comportamento:
    - Se USE_REAL_GNEXUM desligado ou GNEXUM_URL ausente -> retorna stub seguro.
    - Se ligado, tenta GET no endpoint definido e normaliza resposta para o formato esperado pelo mapper.
    """
    # modo stub por padrão (desenvolvimento)
    if not USE_REAL_GNEXUM or not GNEXUM_URL:
        # modo stub seguro: não retornar items falsos — deixar lista vazia
        return []

    headers = {"Content-Type": "application/json; charset=utf-8"}
    # obter token através do token manager (pode efetuar login se necessário)
    try:
        token = await get_token()
    except Exception:
        token = None
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Tentar várias formas de chamada para acomodar contrato desconhecido:
    # 1) GET direto em GNEXUM_URL
    # 2) GET com ?record_id= ou ?id=
    # 3) POST com body {idregistro: ...} ou {record_id: ...}
    candidates_get = [
        GNEXUM_URL,
        f"{GNEXUM_URL.rstrip('/')}?record_id={record_id}",
        f"{GNEXUM_URL.rstrip('/')}?id={record_id}",
    ]

    async def _normalize(data):
        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            # suportar vários formatos
            rows = data.get("items") or data.get("rows") or data.get("data") or []
        items = []
        for r in rows:
            items.append({
                "title": r.get("title") or r.get("nome") or "item",
                "quantity_planned": float(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 0),
                "load": float(r.get("load", 0) or 0),
                "load_2": float(r.get("load_2", 0) or 0),
                "load_3": float(r.get("load_3", 0) or 0),
                "reference": r.get("reference") or r.get("ref") or "",
                "notes": r.get("notes", ""),
            })
        return items

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Preferir POST: a API Gnexum usa POST para operações
            bodies = [{"idregistro": record_id}, {"record_id": record_id}, {"id": record_id}]
            for b in bodies:
                try:
                    logger.debug("Gnexum: POST %s body=%s", GNEXUM_URL, b)
                    resp = await client.post(GNEXUM_URL, json=b, headers=headers)
                except Exception as e:
                    logger.debug("Gnexum POST failed: %s", e)
                    continue
                if resp.status_code == 401:
                    # token inválido/expirado: tentar login automático e repetir uma vez
                    logger.debug("Gnexum: recebeu 401, tentando login automático e re-tentar")
                    await login_and_store()
                    # recarregar token
                    try:
                        token = await get_token()
                        if token:
                            headers["Authorization"] = f"Bearer {token}"
                    except Exception:
                        pass
                    try:
                        resp = await client.post(GNEXUM_URL, json=b, headers=headers)
                    except Exception as e:
                        logger.debug("Gnexum retry POST failed: %s", e)
                        continue

                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        items = await _normalize(data)
                        if items:
                            logger.debug("Gnexum: returned %d items via POST", len(items))
                            return items
                    except Exception as e:
                        logger.debug("Gnexum POST parse error: %s", e)
                        continue

            # Se POSTs não devolveram items, tentar GETs como fallback
            for url in candidates_get:
                try:
                    logger.debug("Gnexum: GET %s", url)
                    resp = await client.get(url, headers=headers)
                except Exception as e:
                    logger.debug("Gnexum GET failed: %s", e)
                    continue
                if resp.status_code == 401:
                    logger.debug("Gnexum: GET recebeu 401, tentando login e re-tentar")
                    await login_and_store()
                    try:
                        token = await get_token()
                        if token:
                            headers["Authorization"] = f"Bearer {token}"
                    except Exception:
                        pass
                    try:
                        resp = await client.get(url, headers=headers)
                    except Exception as e:
                        logger.debug("Gnexum retry GET failed: %s", e)
                        continue

                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        items = await _normalize(data)
                        if items:
                            logger.debug("Gnexum: returned %d items via GET", len(items))
                            return items
                    except Exception as e:
                        logger.debug("Gnexum GET parse error: %s", e)
                        continue

    except Exception as e:
        logger.debug("Gnexum overall error: %s", e)
        # falha genérica: retornar fallback seguro
        return []

    return []
