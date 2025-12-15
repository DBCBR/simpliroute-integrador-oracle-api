import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Sequence

from .oracle_source import get_connection

LOGGER = logging.getLogger(__name__)

REFERENCE_COLUMN = "IDREFERENCE"
EVENTDATE_COLUMN = "EVENTDATE"
IDADMISSION_COLUMN = "IDADMISSION"
IDREGISTRO_COLUMN = "IDREGISTRO"
TPREGISTRO_COLUMN = "TPREGISTRO"


def _status_schema() -> str:
    schema = os.getenv("ORACLE_STATUS_SCHEMA") or os.getenv("ORACLE_SCHEMA")
    if not schema:
        raise RuntimeError("ORACLE_STATUS_SCHEMA/ORACLE_SCHEMA não configurado")
    return schema.strip()


def _status_target_table() -> str:
    return os.getenv("SIMPLIROUTE_TARGET_TABLE", "TD_OTIMIZE_ALTSTAT").strip()


def _status_info_column() -> str:
    return os.getenv("SIMPLIROUTE_TARGET_INFO_COLUMN", "INFORMACAO").strip()


def _status_id_column() -> str:
    # Por padrão usamos IDADMISSION (equivalente ao ID_ATENDIMENTO das views)
    return os.getenv("SIMPLIROUTE_TARGET_ID_COLUMN", "IDADMISSION").strip()


def _status_status_column() -> Optional[str]:
    raw = os.getenv("SIMPLIROUTE_TARGET_STATUS_COLUMN", "STATUS")
    return raw.strip() if raw else None


def _deliveries_view_name() -> Optional[str]:
    for key in ("ORACLE_VIEW_ENTREGAS", "ORACLE_VIEW_VISITAS", "ORACLE_VIEW"):
        value = os.getenv(key)
        if value:
            return value.strip()
    return None


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


def _map_delivery_status(status: Any, checkout_comment: Any) -> Optional[int]:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None

    comment_hint = str(checkout_comment or "").strip().lower()
    if "parcial" in comment_hint:
        return 4

    partial_tokens = {"partial", "partial_delivery", "partially_delivered", "partial_completed"}
    completed_tokens = {"completed", "delivered", "finished", "done"}
    failed_tokens = {
        "failed",
        "cancelled",
        "canceled",
        "suspended",
        "paused",
        "rejected",
        "not_delivered",
        "undelivered",
    }

    if normalized in partial_tokens or "partial" in normalized:
        return 4
    if normalized in completed_tokens:
        return 5
    if normalized in failed_tokens:
        return 6
    return None


def _infer_tpregistro(entry: Dict[str, Any], fallback: int = 2) -> int:
    value = entry.get("TPREGISTRO") or entry.get("tpregistro")
    tp = _to_int_or_none(value)
    if tp in (1, 2):
        return tp

    visit_type = str(entry.get("visit_type") or "").lower()
    delivery_tags = {"rota_log", "adm_log", "acr_log", "ret_log", "pad_log"}
    if visit_type in delivery_tags:
        return 2

    record_type = str((entry.get("properties") or {}).get("record_type") or "").lower()
    if record_type == "entrega":
        return 2

    return fallback


def _parse_iso_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _extract_from_entry(entry: Dict[str, Any], *keys: str) -> Any:
    search_keys = [k.lower() for k in keys if k]
    containers = [entry]
    for nested_key in ("properties", "extra_field_values", "payload", "metadata"):
        nested = entry.get(nested_key)
        if isinstance(nested, dict):
            containers.append(nested)
    for container in containers:
        if not isinstance(container, dict):
            continue
        for raw_key, value in container.items():
            if value in (None, "") or not isinstance(raw_key, str):
                continue
            if raw_key.lower() in search_keys:
                return value
    return None


def _extract_numeric(entry: Dict[str, Any], *keys: str) -> Optional[int]:
    value = _extract_from_entry(entry, *keys)
    return _to_int_or_none(value)


def _resolve_event_datetime(entry: Dict[str, Any]) -> datetime:
    for key in ("checkout_time", "eventdate", "event_date", "status_date", "completed_at", "modified", "updated_at", "created"):
        candidate = _extract_from_entry(entry, key)
        dt_val = _parse_iso_datetime(candidate)
        if dt_val:
            return _normalize_datetime(dt_val)
    return datetime.utcnow()


def _resolve_record_identifier(entry: Dict[str, Any]) -> Optional[int]:
    record_id = entry.get("reference")
    if record_id in (None, ""):
        record_id = entry.get("external_id") or entry.get("externalId")
    if record_id in (None, ""):
        record_id = _extract_from_entry(entry, "ID_REGISTRO", "idregistro")
    if record_id in (None, ""):
        record_id = _extract_from_entry(entry, "IDADMISSION", "ID_ATENDIMENTO", "IDREFERENCE")
    return _to_int_or_none(record_id)


def _fetch_base_identifiers(cur, schema: str, table: str, record_id: int, primary_column: str) -> Dict[str, Any]:
    candidates = [primary_column, IDREGISTRO_COLUMN, IDADMISSION_COLUMN, REFERENCE_COLUMN]
    seen = set()
    for column in candidates:
        if not column or column in seen:
            continue
        seen.add(column)
        try:
            cur.execute(
                f"""
                SELECT {REFERENCE_COLUMN}, {IDADMISSION_COLUMN}, {IDREGISTRO_COLUMN}, {TPREGISTRO_COLUMN}
                FROM {schema}.{table}
                WHERE {column} = :record_id
                ORDER BY {EVENTDATE_COLUMN} DESC FETCH FIRST 1 ROWS ONLY
                """,
                {"record_id": record_id},
            )
        except Exception as exc:
            LOGGER.debug("Falha ao consultar %s.%s via coluna %s: %s", schema, table, column, exc)
            continue
        row = cur.fetchone()
        if row:
            return {
                REFERENCE_COLUMN: _to_int_or_none(row[0]) or row[0],
                IDADMISSION_COLUMN: _to_int_or_none(row[1]) or row[1],
                IDREGISTRO_COLUMN: _to_int_or_none(row[2]) or row[2],
                TPREGISTRO_COLUMN: _to_int_or_none(row[3]) or row[3],
            }
    return {}


def _fetch_source_identifiers(cur, schema: str, record_id: int) -> Dict[str, Any]:
    view_name = _deliveries_view_name()
    if not (view_name and schema and record_id):
        return {}
    try:
        cur.execute(
            f"""
            SELECT ID_PROTOCOLO, ID_ATENDIMENTO, ID_PRESCRICAO
            FROM {schema}.{view_name}
            WHERE ID_ATENDIMENTO = :rid OR ID_PROTOCOLO = :rid OR ID_PRESCRICAO = :rid
            FETCH FIRST 1 ROWS ONLY
            """,
            {"rid": record_id},
        )
    except Exception as exc:
        LOGGER.debug("Falha ao consultar view de origem %s: %s", view_name, exc)
        return {}

    row = cur.fetchone()
    if not row:
        return {}
    return {
        REFERENCE_COLUMN: _to_int_or_none(row[0]) or row[0],
        IDADMISSION_COLUMN: _to_int_or_none(row[1]) or row[1],
        IDREGISTRO_COLUMN: _to_int_or_none(row[2]) or row[2],
    }

def persist_status_updates(events: Sequence[Dict[str, Any]]) -> None:
    """Insere um registro por evento do webhook com os dados de retorno do SimpliRoute."""

    if not events:
        return

    schema = _status_schema()
    target_table = _status_target_table()
    info_col = _status_info_column()
    status_col = _status_status_column()
    id_col = _status_id_column()

    insert_columns = [REFERENCE_COLUMN, EVENTDATE_COLUMN, IDADMISSION_COLUMN, IDREGISTRO_COLUMN, TPREGISTRO_COLUMN]
    insert_params = [":idreference", ":eventdate", ":idadmission", ":idregistro", ":tpregistro"]
    if status_col:
        insert_columns.append(status_col)
        insert_params.append(":status_code")
    insert_columns.append(info_col)
    insert_params.append(":informacao")

    insert_sql = f"INSERT INTO {schema}.{target_table} ({', '.join(insert_columns)}) VALUES ({', '.join(insert_params)})"

    with get_connection() as conn:
        cur = conn.cursor()
        for entry in events:
            if not isinstance(entry, dict):
                continue

            record_int = _resolve_record_identifier(entry)
            if record_int is None:
                LOGGER.warning("Evento do webhook sem identificador numérico: %s", entry)
                continue

            sr_idreference = _extract_numeric(entry, "ID_PROTOCOLO", "IDREFERENCE", "reference")
            sr_idadmission = _extract_numeric(entry, "IDADMISSION", "ID_ATENDIMENTO")
            sr_idregistro = _extract_numeric(entry, "ID_REGISTRO", "ID_PRESCRICAO", "IDREGISTRO")

            base_identifiers = _fetch_base_identifiers(cur, schema, target_table, record_int, id_col)
            source_identifiers = _fetch_source_identifiers(cur, schema, record_int)

            idreference = (
                sr_idreference
                or base_identifiers.get(REFERENCE_COLUMN)
                or source_identifiers.get(REFERENCE_COLUMN)
                or record_int
            )
            idadmission = (
                sr_idadmission
                or base_identifiers.get(IDADMISSION_COLUMN)
                or source_identifiers.get(IDADMISSION_COLUMN)
                or record_int
            )
            idregistro = (
                sr_idregistro
                or base_identifiers.get(IDREGISTRO_COLUMN)
                or source_identifiers.get(IDREGISTRO_COLUMN)
                or record_int
            )
            tpregistro = base_identifiers.get(TPREGISTRO_COLUMN)
            if tpregistro not in (1, 2):
                tpregistro = _infer_tpregistro(entry, fallback=2)

            status_code = None
            if status_col:
                checkout_comment = _extract_from_entry(entry, "checkout_comment")
                status_code = _map_delivery_status(entry.get("status"), checkout_comment)
                if status_code is None:
                    LOGGER.warning("Status SimpliRoute não mapeado para registro %s: %s", record_int, entry.get("status"))
                    continue
            else:
                status_code = None

            event_dt = _resolve_event_datetime(entry)
            payload_str = _serialize_payload(entry)

            params = {
                "idreference": idreference,
                "eventdate": event_dt,
                "idadmission": idadmission,
                "idregistro": idregistro,
                "tpregistro": tpregistro,
                "informacao": payload_str,
            }
            if status_col:
                params["status_code"] = status_code

            try:
                cur.execute(insert_sql, params)
                LOGGER.info(
                    "SR status inserido: idreference=%s idregistro=%s status=%s event=%s",
                    idreference,
                    idregistro,
                    status_code,
                    event_dt.isoformat(timespec="milliseconds"),
                )
            except Exception as exc:
                LOGGER.warning("Falha ao inserir evento %s na tabela de status: %s", record_int, exc)

        try:
            conn.commit()
        except Exception as exc:
            LOGGER.error("Não foi possível executar commit dos status SR: %s", exc)

__all__ = ["persist_status_updates"]
