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
            if not isinstance(r, dict):
                out.append({"title": str(r), "quantity_planned": 1.0, "load": 0.0})
                continue
            title = r.get("title") or r.get("nome") or r.get("NOME") or r.get("ESPECIALIDADE") or r.get("TIPOVISITA") or "item"
            try:
                qty = float(r.get("quantity_planned") or r.get("quantidade") or r.get("qty") or 1.0)
            except Exception:
                qty = 1.0
            try:
                load = float(r.get("load") or 0.0)
            except Exception:
                load = 0.0
            item = {"title": title, "quantity_planned": qty, "load": load}
            # preservar outras chaves úteis para depuração
            for extra in ("ID_ATENDIMENTO", "PROFISSIONAL", "ESPECIALIDADE", "PERIODICIDADE", "TIPOVISITA"):
                if extra in r:
                    item[extra] = r.get(extra)
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

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Tentar GETs primeiro (mais seguro para endpoints que já retornam lista)
            for url in candidates_get:
                try:
                    logger.debug("Gnexum: GET %s", url)
                    resp = await client.get(url, headers=headers)
                except Exception as e:
                    logger.debug("Gnexum GET failed: %s", e)
                    resp = None
                if not resp:
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
                        resp = None
                if not resp:
                    continue
                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        # debug output removed; use logger for diagnostics
                        if normalize:
                            items = await _normalize(data)
                            # count available via logger.debug when needed
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

            # Se GETs não devolveram items, tentar POSTs como fallback
            bodies = [{"idregistro": record_id}, {"record_id": record_id}, {"id": record_id}]
            for b in bodies:
                try:
                    logger.debug("Gnexum: POST %s body=%s", GNEXUM_URL, b)
                    resp = await client.post(GNEXUM_URL, json=b, headers=headers)
                except Exception as e:
                    logger.debug("Gnexum POST failed: %s", e)
                    resp = None
                if not resp:
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
                        resp = None
                if not resp:
                    continue
                if resp.status_code in (200, 201):
                    try:
                        data = resp.json()
                        # debug output removed; use logger for diagnostics
                        # when caller requests normalization, return normalized items
                        if normalize:
                            items = await _normalize(data)
                            # count available via logger.debug when needed
                            if items:
                                logger.debug("Gnexum: returned %d items via POST (normalized)", len(items))
                                return items
                        else:
                            # return raw rows structure (items/rows/data)
                            rows = data if isinstance(data, list) else data.get("items") or data.get("rows") or data.get("data") or []
                            # filter by record_id if possible
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

    except Exception as e:
        logger.debug("Gnexum overall error: %s", e)
        # falha genérica: retornar fallback seguro
        return []

    return []
