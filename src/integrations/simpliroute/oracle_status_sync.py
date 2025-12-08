import json
import logging
import os
from typing import Any, Dict, Optional, Sequence

from .oracle_source import get_connection

LOGGER = logging.getLogger(__name__)


def _status_schema() -> str:
    schema = os.getenv("ORACLE_STATUS_SCHEMA") or os.getenv("ORACLE_SCHEMA")
    if not schema:
        raise RuntimeError("ORACLE_STATUS_SCHEMA/ORACLE_SCHEMA não configurado")
    return schema.strip()


def _status_target_table() -> str:
    return os.getenv("SIMPLIROUTE_TARGET_TABLE", "TD_OTIMIZE_ALTSTAT").strip()


def _status_action_column() -> str:
    return os.getenv("SIMPLIROUTE_TARGET_ACTION_COLUMN", "ACAO").strip()


def _status_info_column() -> str:
    return os.getenv("SIMPLIROUTE_TARGET_INFO_COLUMN", "INFORMACAO").strip()


def _status_status_column() -> Optional[str]:
    raw = os.getenv("SIMPLIROUTE_TARGET_STATUS_COLUMN", "STATUS")
    return raw.strip() if raw else None


def _to_int_or_none(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(str(value).strip())
    except Exception:
        return None


def _serialize_payload(payload: Dict[str, Any]) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return str(payload)


def _map_status_to_action(status: Any) -> str:
    if not status:
        return "A"
    normalized = str(status).strip().lower()
    if normalized in {"completed", "delivered", "finished", "done"}:
        return "E"
    if normalized in {"suspended", "suspensa", "failed", "cancelled", "canceled", "paused"}:
        return "S"
    return "A"


def _map_status_code(tpregistro: Optional[int], status: Any) -> Optional[int]:
    if tpregistro not in (1, 2):
        return None

    normalized = (str(status).strip().lower() if status else "")
    completed = {"completed", "delivered", "finished", "done"}
    in_transit = {"in_progress", "on_route", "on_its_way", "en_route", "enroute", "started"}
    pending = {"pending", "scheduled", "assigned", "created", "waiting", "queued"}
    suspended = {"failed", "cancelled", "canceled", "suspended", "paused", "rejected"}

    if tpregistro == 1:
        if normalized in completed:
            return 2  # Realizada
        if normalized in in_transit:
            return 1  # Programada / em execução
        if normalized in pending or normalized == "":
            return 0
        if normalized in suspended:
            return 0
        return None

    # tpregistro == 2 -> prescrições/entregas
    if normalized in completed:
        return 2  # Dispensação
    if normalized in in_transit:
        return 3  # Em rota de entrega
    if normalized in pending or normalized == "":
        return 0  # Em preparação
    if normalized in suspended:
        return 0
    return None


def _fetch_tpregistro(cursor, schema: str, table: str, record_id: int) -> Optional[int]:
    cursor.execute(
        f"SELECT TPREGISTRO FROM {schema}.{table} WHERE IDREGISTRO = :record_id",
        {"record_id": record_id},
    )
    row = cursor.fetchone()
    if row and row[0] is not None:
        try:
            return int(row[0])
        except Exception:
            return None
    return None


def persist_status_updates(events: Sequence[Dict[str, Any]]) -> None:
    """Registra eventos recebidos do webhook diretamente na TD_OTIMIZE_ALTSTAT."""

    if not events:
        return

    schema = _status_schema()
    target_table = _status_target_table()
    action_col = _status_action_column()
    info_col = _status_info_column()
    status_col = _status_status_column()

    update_sql = f"UPDATE {schema}.{target_table} SET {action_col} = :acao, {info_col} = :informacao WHERE IDREGISTRO = :record_id"
    status_sql = None
    if status_col:
        status_sql = f"UPDATE {schema}.{target_table} SET {status_col} = :status_code WHERE IDREGISTRO = :record_id"

    with get_connection() as conn:
        cur = conn.cursor()
        for entry in events:
            if not isinstance(entry, dict):
                continue
            sr_status = entry.get("status")
            record_id = (
                entry.get("reference")
                or (entry.get("properties") or {}).get("ID_REGISTRO")
                or (entry.get("properties") or {}).get("idregistro")
                or entry.get("external_id")
                or entry.get("externalId")
            )
            record_int = _to_int_or_none(record_id)
            if record_int is None:
                continue

            params = {
                "acao": _map_status_to_action(sr_status),
                "informacao": _serialize_payload(entry),
                "record_id": record_int,
            }
            try:
                cur.execute(update_sql, params)
            except Exception as exc:
                LOGGER.warning("Falha ao atualizar registro base %s: %s", record_int, exc)

            if status_sql:
                tpregistro = _fetch_tpregistro(cur, schema, target_table, record_int)
                status_code = _map_status_code(tpregistro, sr_status)
                if status_code is not None:
                    try:
                        cur.execute(status_sql, {"status_code": status_code, "record_id": record_int})
                    except Exception as exc:
                        LOGGER.warning("Falha ao atualizar STATUS %s: %s", record_int, exc)
        try:
            conn.commit()
        except Exception as exc:
            LOGGER.error("Não foi possível executar commit dos status SR: %s", exc)

__all__ = ["persist_status_updates"]
