from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from src.core.config import load_config

from .client import post_simpliroute
from .mapper import build_visit_payload
from .oracle_source import fetch_grouped_records, resolve_where_clause
from .oracle_status_sync import persist_status_updates

LOGGER = logging.getLogger("simpliroute.service")
if not LOGGER.handlers:
    logging.basicConfig(level=logging.INFO)

SERVICE_LOG = Path("data/work/service_events.log")
SERVICE_LOG.parent.mkdir(parents=True, exist_ok=True)


CONFIG_CACHE: Dict[str, Any] = {}


def _load_cached_config() -> Dict[str, Any]:
    global CONFIG_CACHE
    if CONFIG_CACHE:
        return CONFIG_CACHE
    try:
        CONFIG_CACHE = load_config()
    except Exception:
        CONFIG_CACHE = {}
    return CONFIG_CACHE


def _default_limit() -> int:
    try:
        return int(os.getenv("ORACLE_FETCH_LIMIT", "25"))
    except ValueError:
        return 25


def _config_default_views() -> List[str]:
    cfg = _load_cached_config()
    oracle_cfg = (cfg or {}).get("oracle") or {}
    configured = oracle_cfg.get("default_views") or []
    if isinstance(configured, str):
        configured = [configured]
    result: List[str] = []
    for entry in configured:
        if not isinstance(entry, str):
            continue
        name = entry.strip()
        if not name:
            continue
        if name not in result:
            result.append(name)
    return result


def _env_default_views() -> List[str]:
    views: List[str] = []
    raw = os.getenv("ORACLE_VIEWS") or os.getenv("ORACLE_VIEW_LIST")
    if raw:
        for token in raw.replace(",", " ").replace(";", " ").split():
            token = token.strip()
            if token and token not in views:
                views.append(token)

    for key in (
        "ORACLE_VIEW_VISITAS",
        "ORACLE_VIEW_ENTREGAS",
        "ORACLE_VIEW_VISITA",
        "ORACLE_VIEW_ENTREGA",
        "ORACLE_VIEW",
    ):
        value = os.getenv(key)
        if value:
            v = value.strip()
            if v and v not in views:
                views.append(v)
    return views


def _default_views() -> List[str]:
    combined: List[str] = []
    for source in (_env_default_views(), _config_default_views()):
        for view in source:
            if view not in combined:
                combined.append(view)
    return combined


def _resolve_views(candidate: Sequence[str] | None) -> List[str | None]:
    if candidate:
        cleaned = [v for v in candidate if v]
        if cleaned:
            return cleaned
    defaults = _default_views()
    if defaults:
        return defaults
    # fallback para env ORACLE_VIEW (padrão do oracledb)
    fallback = os.getenv("ORACLE_VIEW")
    if fallback:
        return [fallback]
    return [None]


def _collect_records(limit: int | None, where: str | None, view_names: Sequence[str] | None) -> List[Dict[str, Any]]:
    targets = _resolve_views(view_names)
    rows: List[Dict[str, Any]] = []
    per_view_limit: int | None = None
    limit_split_across_views = False
    if limit and limit > 0:
        per_view_limit = max(1, math.ceil(limit / len(targets)))
        limit_split_across_views = len(targets) > 1
    for target_view in targets:
        effective_where = resolve_where_clause(target_view, where)
        batch = fetch_grouped_records(limit=per_view_limit, where_clause=effective_where, view_name=target_view)
        rows.extend(batch)
    if not limit_split_across_views and limit and limit > 0 and len(rows) > limit:
        rows = rows[:limit]
    return rows


def _append_service_log(entry: Dict[str, Any]) -> None:
    try:
        entry_line = json.dumps(entry, ensure_ascii=False)
    except Exception:
        entry_line = str(entry)
    with SERVICE_LOG.open("a", encoding="utf-8") as fp:
        fp.write(entry_line + "\n")


@dataclass
class PollingSettings:
    interval_minutes: int
    limit: int | None
    where_clause: str | None
    view_names: Sequence[str] | None


def _load_polling_settings() -> PollingSettings:
    cfg = _load_cached_config()
    interval = 60
    try:
        interval = int((cfg.get("simpliroute") or {}).get("polling_interval_minutes", interval))
    except Exception:
        try:
            interval = int(os.getenv("POLLING_INTERVAL_MINUTES", "60"))
        except ValueError:
            interval = 60

    limit = None
    try:
        limit = int(os.getenv("SIMPLIROUTE_POLLING_LIMIT", str(_default_limit())))
    except ValueError:
        limit = _default_limit()

    simpliroute_cfg = (cfg.get("simpliroute") or {})
    where = simpliroute_cfg.get("polling_where") or os.getenv("SIMPLIROUTE_POLL_WHERE")
    explicit_views: Sequence[str] | None = None
    env_views = _env_default_views()
    if env_views:
        explicit_views = env_views
    return PollingSettings(interval_minutes=interval, limit=limit, where_clause=where, view_names=explicit_views)


async def _run_cycle(settings: PollingSettings) -> None:
    try:
        records = await asyncio.to_thread(_collect_records, settings.limit, settings.where_clause, settings.view_names)
    except Exception as exc:
        LOGGER.exception("Erro ao coletar registros Oracle: %s", exc)
        _append_service_log({"stage": "collect", "status": "failure", "error": str(exc)})
        return

    if not records:
        LOGGER.info("Nenhum registro retornado pelas views configuradas.")
        _append_service_log({"stage": "collect", "status": "empty"})
        return

    payloads = [build_visit_payload(record) for record in records]
    LOGGER.info("Enviando %s payload(s) para o SimpliRoute", len(payloads))

    try:
        response = await post_simpliroute(payloads)
    except Exception as exc:
        LOGGER.exception("Falha ao enviar payloads ao SimpliRoute: %s", exc)
        _append_service_log({"stage": "http_request", "status": "failure", "error": str(exc), "payload_count": len(payloads)})
        return

    if response is None:
        LOGGER.error("Cliente HTTP retornou resposta vazia.")
        _append_service_log({"stage": "http_request", "status": "failure", "error": "response_none", "payload_count": len(payloads)})
        return

    body_text = response.text if hasattr(response, "text") else ""
    LOGGER.info("SimpliRoute respondeu HTTP %s", response.status_code)
    _append_service_log(
        {
            "stage": "http_request",
            "status": "success" if 200 <= response.status_code < 400 else "failure",
            "http_status": response.status_code,
            "payload_count": len(payloads),
            "body_preview": body_text[:400],
        }
    )


async def polling_task(settings: PollingSettings):
    LOGGER.info(
        "Polling agendado a cada %s minuto(s) — limite %s, filtro '%s'",
        settings.interval_minutes,
        settings.limit,
        settings.where_clause,
    )
    while True:
        await _run_cycle(settings)
        try:
            await asyncio.sleep(max(1, settings.interval_minutes) * 60)
        except asyncio.CancelledError:
            LOGGER.info("Polling cancelado — encerrando tarefa")
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = _load_polling_settings()
    poll_task = asyncio.create_task(polling_task(settings))
    app.state._polling_task = poll_task
    app.state.polling_settings = settings
    try:
        yield
    finally:
        task = getattr(app.state, "_polling_task", None)
        if task:
            task.cancel()
            try:
                await task
            except Exception:
                pass


app = FastAPI(title="SimpliRoute Integration Service", lifespan=lifespan)


def _has_simpliroute_token() -> bool:
    return bool(os.getenv("SIMPLIR_ROUTE_TOKEN") or os.getenv("SIMPLIROUTE_TOKEN"))


def _oracle_env_ready() -> bool:
    required = ("ORACLE_HOST", "ORACLE_USER", "ORACLE_PASS", "ORACLE_SERVICE")
    return all(os.getenv(var) for var in required)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/health/live")
async def live() -> JSONResponse:
    return JSONResponse({"status": "alive"})


@app.get("/health/ready")
async def ready() -> JSONResponse:
    polling_ok = getattr(app.state, "_polling_task", None) is not None
    oracle_ready = _oracle_env_ready()
    has_token = _has_simpliroute_token()
    ready_flag = bool(polling_ok and oracle_ready and has_token)
    return JSONResponse(
        {
            "status": "ready" if ready_flag else "not_ready",
            "polling_task": polling_ok,
            "oracle_ready": oracle_ready,
            "has_token": has_token,
        }
    )


def _extract_webhook_events(body: Any) -> List[Dict[str, Any]]:
    if isinstance(body, list):
        return [item for item in body if isinstance(item, dict)]
    if isinstance(body, dict):
        for key in ("visits", "data", "items"):
            value = body.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [body]
    return []


@app.post("/webhook/simpliroute")
async def webhook_simpliroute(request: Request, background: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    expected = os.getenv("SIMPLIR_ROUTE_WEBHOOK_TOKEN") or os.getenv("SIMPLIROUTE_WEBHOOK_TOKEN")
    if expected:
        auth_header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        token_val = auth_header.replace("Bearer ", "").replace("Token ", "").strip()
        if token_val != expected:
            return JSONResponse({"error": "unauthorized webhook"}, status_code=401)

    os.makedirs("data/work/webhooks", exist_ok=True)
    filename = f"data/work/webhooks/webhook_{int(time.time())}.json"
    try:
        with open(filename, "w", encoding="utf-8") as handler:
            json.dump(payload, handler, ensure_ascii=False, indent=2)
    except Exception as exc:
        LOGGER.error("Falha ao persistir payload do webhook: %s", exc)
        return JSONResponse({"error": "io_failure"}, status_code=500)

    events = _extract_webhook_events(payload)
    if events:
        background.add_task(persist_status_updates, events)

    return JSONResponse({"status": "received", "logged": filename})


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBHOOK_PORT", 8000))
    uvicorn.run("src.integrations.simpliroute.app:app", host="0.0.0.0", port=port, reload=False)
