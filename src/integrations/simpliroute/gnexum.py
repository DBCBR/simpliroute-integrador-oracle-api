import os
import logging
from typing import Any, Dict, List
import httpx

# Config via env
# Note: evaluate GNEXUM settings at call-time so tests and runtime reloads work
logger = logging.getLogger(__name__)

from .token_manager import get_token, login_and_store


async def fetch_items_for_record(record_id: Any, timeout: int = 8, normalize: bool = True) -> List[Dict[str, Any]]:
    """Tenta buscar items para um registro no Gnexum.

    Comportamento:
    - Se USE_REAL_GNEXUM desligado ou GNEXUM_URL ausente -> retorna stub seguro.
    - Se ligado, tenta GET no endpoint definido e normaliza resposta para o formato esperado pelo mapper.
    """
    # avaliar variáveis de ambiente em tempo de execução (permite override em testes)
    # Preferir valores definidos no módulo (útil para testes que sobrescrevem
    # `gnexum.GNEXUM_URL` e `gnexum.USE_REAL_GNEXUM`), cair para env quando ausentes.
    module_url = globals().get("GNEXUM_URL")
    env_url = os.getenv("GNEXUM_API_URL")
    GNEXUM_URL = module_url if module_url else env_url

    module_flag = globals().get("USE_REAL_GNEXUM")
    env_flag = os.getenv("USE_REAL_GNEXUM")
    if module_flag is not None:
        use_real = bool(module_flag)
    elif env_flag is not None:
        use_real = env_flag.lower() in ("1", "true", "yes")
    else:
        use_real = False

    if not use_real or not GNEXUM_URL:
        # modo stub seguro: não retornar items falsos — deixar lista vazia
        return []

    # If configured, read directly from the Oracle DB view instead of calling the HTTP endpoint
    try:
        use_db = os.getenv('USE_GNEXUM_DB')
        if use_db is not None and str(use_db).lower() in ('1', 'true', 'yes'):
            try:
                from .gnexum_db import fetch_items_for_record_db
                # delegate to DB reader (which will run blocking calls in an executor)
                items = await fetch_items_for_record_db(record_id)
                if items:
                    return items
            except Exception:
                # fall back to HTTP behavior on error
                logger.debug('Gnexum DB fetch failed, falling back to HTTP')
    except Exception:
        pass

    # retry configuration (env overrides)
    try:
        FETCH_RETRIES = int(os.getenv("GNEXUM_FETCH_RETRIES", "2"))
    except Exception:
        FETCH_RETRIES = 2
    try:
        FETCH_DELAY = float(os.getenv("GNEXUM_FETCH_RETRY_DELAY_SECONDS", "1"))
    except Exception:
        FETCH_DELAY = 1.0

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
        # Normalizar rows em items simples esperados pelos testes e consumidores:
        # cada item terá ao menos: title, quantity_planned, load
        rows = []
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("items") or data.get("rows") or data.get("data") or []

        out = []
        for r in rows:
            # If row is not a dict, keep the simple representation
            if not isinstance(r, dict):
                out.append({"title": str(r), "quantity_planned": 1.0, "load": 0.0})
                continue
            # Preserve the entire row so the mapper can access any field returned by Gnexum
            item = dict(r)
            # Coerce a few common numeric fields to expected types to avoid surprises
            try:
                if "quantity_planned" in item or "quantidade" in item or "qty" in item:
                    item["quantity_planned"] = float(item.get("quantity_planned") or item.get("quantidade") or item.get("qty") or 1.0)
            except Exception:
                item["quantity_planned"] = 1.0
            try:
                item["load"] = float(item.get("load") or 0.0)
            except Exception:
                item["load"] = 0.0
            # ensure title exists
            item["title"] = item.get("title") or item.get("nome") or item.get("NOME") or item.get("ESPECIALIDADE") or item.get("TIPOVISITA") or "item"
            out.append(item)

        # Filtrar linhas para o registro solicitado (quando possível)
        try:
            rid = int(record_id)
            matched = [it for it in out if isinstance(it, dict) and int(it.get("ID_ATENDIMENTO") or it.get("idregistro") or it.get("id") or 0) == rid]
            if matched:
                return matched
        except Exception:
            pass

        return out

    # perform HTTP operations with limited retries and backoff
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Tentar GETs primeiro (mais seguro para endpoints que já retornam lista)
            for attempt in range(1, FETCH_RETRIES + 2):
                for url in candidates_get:
                    resp = None
                    try:
                        logger.debug("Gnexum: GET %s (attempt %d)", url, attempt)
                        resp = await client.get(url, headers=headers)
                    except Exception as e:
                        logger.debug("Gnexum GET failed (attempt %d): %s", attempt, e)
                        resp = None

                    if not resp:
                        continue

                    if resp.status_code == 401:
                        # try to refresh/login and retry immediately once
                        logger.debug("Gnexum: GET recebeu 401, tentando refresh/login e re-tentar")
                        try:
                            newtok = await refresh_and_store()
                            if not newtok:
                                # fallback to full login
                                await login_and_store()
                        except Exception:
                            pass
                        try:
                            token = await get_token()
                            if token:
                                headers["Authorization"] = f"Bearer {token}"
                        except Exception:
                            pass

                        # try again immediately
                        try:
                            resp = await client.get(url, headers=headers)
                        except Exception as e:
                            logger.debug("Gnexum retry GET failed: %s", e)
                            resp = None

                    if not resp:
                        continue

                    if resp.status_code in (200, 201):
                        try:
                            data = resp.json()
                            if normalize:
                                items = await _normalize(data)
                                if items:
                                    logger.debug("Gnexum: returned %d items via GET (normalized)", len(items))
                                    return items
                            else:
                                rows = data if isinstance(data, list) else data.get("items") or data.get("rows") or data.get("data") or []
                                try:
                                    rid = int(record_id)
                                    matched = [r for r in rows if isinstance(r, dict) and int(r.get("ID_ATENDIMENTO") or r.get("idregistro") or r.get("id") or 0) == rid]
                                    if matched:
                                        return matched
                                except Exception:
                                    pass
                                return rows
                        except Exception as e:
                            logger.debug("Gnexum GET parse error: %s", e)
                            continue

                # backoff between attempts
                if attempt <= FETCH_RETRIES:
                    try:
                        await asyncio.sleep(FETCH_DELAY * attempt)
                    except Exception:
                        pass

            # Se GETs não devolveram items, tentar POSTs como fallback (com retries)
            bodies = [{"idregistro": record_id}, {"record_id": record_id}, {"id": record_id}]
            for attempt in range(1, FETCH_RETRIES + 2):
                for b in bodies:
                    resp = None
                    try:
                        logger.debug("Gnexum: POST %s body=%s (attempt %d)", GNEXUM_URL, b, attempt)
                        resp = await client.post(GNEXUM_URL, json=b, headers=headers)
                    except Exception as e:
                        logger.debug("Gnexum POST failed (attempt %d): %s", attempt, e)
                        resp = None

                    if not resp:
                        continue

                    if resp.status_code == 401:
                        logger.debug("Gnexum: POST recebeu 401, tentando refresh/login e re-tentar")
                        try:
                            newtok = await refresh_and_store()
                            if not newtok:
                                await login_and_store()
                        except Exception:
                            pass
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
                            resp = None

                    if not resp:
                        continue

                    if resp.status_code in (200, 201):
                        try:
                            data = resp.json()
                            if normalize:
                                items = await _normalize(data)
                                if items:
                                    logger.debug("Gnexum: returned %d items via POST (normalized)", len(items))
                                    return items
                            else:
                                rows = data if isinstance(data, list) else data.get("items") or data.get("rows") or data.get("data") or []
                                try:
                                    rid = int(record_id)
                                    matched = [r for r in rows if isinstance(r, dict) and int(r.get("ID_ATENDIMENTO") or r.get("idregistro") or r.get("id") or 0) == rid]
                                    if matched:
                                        return matched
                                except Exception:
                                    pass
                                return rows
                        except Exception as e:
                            logger.debug("Gnexum POST parse error: %s", e)
                            continue

                if attempt <= FETCH_RETRIES:
                    try:
                        await asyncio.sleep(FETCH_DELAY * attempt)
                    except Exception:
                        pass

    except Exception as e:
        logger.debug("Gnexum overall error: %s", e)
        # falha genérica: retornar fallback seguro
        return []

    return []
