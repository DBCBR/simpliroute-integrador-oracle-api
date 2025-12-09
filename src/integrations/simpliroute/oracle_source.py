import logging
import os
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

import oracledb
from dotenv import load_dotenv

LOGGER = logging.getLogger(__name__)
_ENV_READY = False
_CLIENT_READY = False


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _instant_client_candidates() -> List[Path]:
    candidates: List[Path] = []
    env_path = os.getenv("ORACLE_INSTANT_CLIENT")
    if env_path:
        candidates.append(Path(env_path))

    windows_base = _project_root() / "settings" / "instantclient" / "windows"
    explicit = windows_base / "instantclient_23_0"
    if explicit.exists():
        candidates.append(explicit)
    elif windows_base.exists():
        for child in windows_base.iterdir():
            if child.is_dir() and child.name.lower().startswith("instantclient"):
                candidates.append(child)
                break

    candidates.append(Path("/opt/oracle/instantclient"))
    return candidates


def _ensure_env_loaded() -> None:
    global _ENV_READY
    if _ENV_READY:
        return
    env_path = _project_root() / "settings" / ".env"
    if env_path.exists():
        load_dotenv(str(env_path), override=False)
    _ENV_READY = True


def _init_oracle_client() -> None:
    global _CLIENT_READY
    if _CLIENT_READY:
        return
    _ensure_env_loaded()
    for candidate in _instant_client_candidates():
        if not candidate:
            continue
        if not candidate.exists():
            continue
        try:
            oracledb.init_oracle_client(lib_dir=str(candidate))
            break
        except oracledb.Error as exc:  # type: ignore[attr-defined]
            LOGGER.debug("init_oracle_client failed", exc_info=exc)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.debug("init_oracle_client unexpected failure", exc_info=exc)
    _CLIENT_READY = True


def _require_env(name: str) -> str:
    _ensure_env_loaded()
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Variável de ambiente obrigatória ausente: {name}")
    return value


def _build_connection() -> oracledb.Connection:
    _init_oracle_client()
    host = _require_env("ORACLE_HOST")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = _require_env("ORACLE_SERVICE")
    user = _require_env("ORACLE_USER")
    password = _require_env("ORACLE_PASS")

    dsn = oracledb.makedsn(host, port, service_name=service)
    return oracledb.connect(user=user, password=password, dsn=dsn)


def _group_key(row: Dict[str, Any]) -> str:
    preferred = os.getenv("ORACLE_GROUP_FIELD", "ID_ATENDIMENTO")
    candidates = [preferred, "ID_REGISTRO", "ID_PROTOCOLO", "ID_PRESCRICAO", "ID_VISITA"]
    for cand in candidates:
        if not cand:
            continue
        value = row.get(cand) or row.get(cand.lower())
        if value not in (None, ""):
            return str(value)
    return f"ROW_{row.get('ROWNUM', '')}_{id(row)}"


def resolve_where_clause(view_name: Optional[str], explicit_where: Optional[str] = None) -> Optional[str]:
    """Seleciona o filtro WHERE a ser aplicado considerando overrides por view."""

    if explicit_where:
        return explicit_where

    base_where = os.getenv("ORACLE_POLL_WHERE")
    view_upper = (view_name or "").upper()
    if not view_upper:
        return base_where

    delivery_where = os.getenv("ORACLE_POLL_WHERE_ENTREGAS") or os.getenv("ORACLE_POLL_WHERE_ENTREGA")
    visit_where = os.getenv("ORACLE_POLL_WHERE_VISITAS") or os.getenv("ORACLE_POLL_WHERE_VISITA")

    if any(token in view_upper for token in ("ENTREGA", "ROTA")) and delivery_where:
        return delivery_where
    if any(token in view_upper for token in ("VISITA", "VISIT")) and visit_where:
        return visit_where

    return base_where


def fetch_view_rows(
    limit: Optional[int] = None,
    where_clause: Optional[str] = None,
    view_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retorna rows cruas da view Oracle como lista de dicts."""
    schema = _require_env("ORACLE_SCHEMA")
    view = view_name or _require_env("ORACLE_VIEW")
    sql = f"SELECT * FROM {schema}.{view}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    params: Dict[str, Any] = {}
    if limit and limit > 0:
        sql = f"SELECT * FROM ({sql}) WHERE ROWNUM <= :limit"
        params["limit"] = int(limit)

    with _build_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            columns = [col[0] for col in cur.description]
            rows = []
            for raw in cur.fetchall():
                rows.append({col: raw[idx] for idx, col in enumerate(columns)})
    return rows


def fetch_grouped_records(
    limit: Optional[int] = None,
    where_clause: Optional[str] = None,
    view_name: Optional[str] = None,
) -> List[Dict[str, Any]]:
    effective_view = view_name or _require_env("ORACLE_VIEW")
    rows = fetch_view_rows(limit=limit, where_clause=where_clause, view_name=effective_view)
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
    for row in rows:
        key = _group_key(row)
        record = grouped.get(key)
        if record is None:
            record = dict(row)
            record["items"] = []
            record["_source_view"] = effective_view
            grouped[key] = record
        record.setdefault("items", [])
        row_copy = dict(row)
        row_copy["_source_view"] = effective_view
        record["items"].append(row_copy)
    return list(grouped.values())


def get_connection() -> oracledb.Connection:
    return _build_connection()


__all__ = ["fetch_view_rows", "fetch_grouped_records", "get_connection", "resolve_where_clause"]
