import math
import textwrap
import unicodedata
import re
from datetime import datetime, date
from typing import Any, Dict, List
from collections import OrderedDict
import os
import traceback
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import os
import json
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import Any, Dict, List
from collections import OrderedDict
import unicodedata
import re

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_MATERIAL_LINE_LENGTH = 58
DEFAULT_DURATION_MINUTES = {
    "delivery": 30,
    "med": 30,
    "enf": 60,
}
DEFAULT_WINDOW_RANGES = {
    "delivery": ("00:00:00", "23:59:00", "23:59:00", "23:59:00"),
    "med": ("00:00:00", "23:59:00", "23:59:00", "23:59:00"),
    "enf": ("00:00:00", "23:59:00", "23:59:00", "23:59:00"),
}

def _minutes_to_hhmmss(minutes: int) -> str:
    try:
        m = int(minutes)
    except Exception:
        m = 0
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}:00"

def _normalize_duration(value) -> str:
    if value is None:
        return "00:00:00"
    if isinstance(value, str):
        v = value.strip()
        parts = v.split(":")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return v
        if v.isdigit():
            return _minutes_to_hhmmss(int(v))
        try:
            digits = "".join(c for c in v if c.isdigit())
            if digits:
                return _minutes_to_hhmmss(int(digits))
        except Exception:
            pass
        return "00:00:00"
    try:
        return _minutes_to_hhmmss(int(value))
    except Exception:
        return "00:00:00"

def _is_blank_duration(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (int, float)):
        try:
            return float(value) <= 0
        except Exception:
            return True
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return True
        normalized = stripped.replace(" ", "").lower()
        return normalized in {"0", "0.0", "00:00:00"}
    return False

def _normalize_numeric_string(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        return text[:-2]
    return text

def _zero_pad_quantity(value: Any) -> str:
    if value in (None, ""):
        return "0000"
    try:
        if isinstance(value, str):
            normalized = value.replace(",", ".").strip()
            num = float(normalized or 0)
        else:
            num = float(value)
    except Exception:
        return "0000"
    if num < 0:
        num = 0
    return f"{int(round(num)):04d}"

def _wrap_material_description(text: str, width: int = MAX_MATERIAL_LINE_LENGTH) -> List[str]:
    if not text:
        return []
    wrapped = textwrap.wrap(
        text,
        width=width,
        break_long_words=False,
        break_on_hyphens=False,
    )
    if wrapped:
        return [wrapped[0]]
    return [text[:width]]

def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, str):
        candidate = value.replace(",", ".").strip()
        if not candidate:
            return default
        try:
            return float(candidate)
        except Exception:
            return default
    try:
        return float(value)
    except Exception:
        return default

def _ceil_quantity(value: Any, default: float = 0.0) -> float:
    num = _to_float(value, default=default)
    try:
        return float(math.ceil(num))
    except Exception:
        return float(math.ceil(_to_float(default, 0.0)))

def _sanitize_email(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text or "@" not in text:
        return None
    if not EMAIL_PATTERN.match(text):
        return None
    return text

# --- Função para montar o payload SimpliRoute ---
# Copie a função build_visit_payload completa daqui para baixo (inclusive as funções internas)
from typing import Any, Dict

def build_visit_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Constrói payload compatível com SimpliRoute para criação de visita.

    Regras aplicadas a partir do PDD:
    - `title` deve existir (usamos idregistro/idadmission como fallback)
    - `address` obrigatório (string)
    - Para entregas (`tpregistro==2`) usamos `planned_date` (YYYY-MM-DD)
    - `duration` é enviado no formato HH:MM:SS para visitas
    - `items` convertido para o shape esperado pela API
    - adiciona `properties.source` e `properties.source_ident` para rastreabilidade
    """
    # suportar chaves vindas do Gnexum que podem estar em CAIXA ALTA
    def _normalize_key_name(s: str) -> str:
        try:
            s = str(s)
        except Exception:
            return str(s)
        s = s.strip().lower()
        # remove accents
        s = unicodedata.normalize("NFKD", s)
        s = "".join(c for c in s if unicodedata.category(c) != "Mn")
        # keep only alnum and underscore
        s = "".join(c for c in s if c.isalnum() or c == "_")
        return s

    def _get(k, *alts, default=None):
        # try exact keys first
        for key in (k,) + alts:
            if key in record and record.get(key) is not None:
                return record.get(key)
        # case/format-insensitive lookup: normalize keys and compare
        target_names = [str(x) for x in (k,) + alts if x]
        target_norms = {_normalize_key_name(t): t for t in target_names}
        for rec_key, rec_val in record.items():
            if rec_val is None:
                continue
            rn = _normalize_key_name(rec_key)
            if rn in target_norms:
                return rec_val
        # fallback: try to match by common aliases (e.g., ITEM_TITLE -> title)
        aliases = {
            'item_title': ('item_title', 'produto', 'nome', 'title'),
            'quantity_planned': ('quantity_planned', 'quantidade', 'qty'),
            'planned_date': ('planned_date', 'dt_visita', 'eventdate'),
            'address': ('address', 'endereco', 'endereco_geolocalizacao'),
            'contact_phone': ('contact_phone', 'telefones', 'contact_phone'),
        }
        for alias_key, candidates in aliases.items():
            if _normalize_key_name(k) == alias_key:
                for c in candidates:
                    for rec_key, rec_val in record.items():
                        if _normalize_key_name(rec_key) == _normalize_key_name(c) and rec_val not in (None, ''):
                            return rec_val
        return default

    tp = int(_get("tpregistro", "TPREGISTRO", default=1) or 1)

    # Detect if this run is reading from a deliveries view.
    source_view = str(record.get("_source_view") or "").upper()
    env_view = os.getenv("ORACLE_VIEW", "").upper()
    view_name = source_view or env_view
    is_entrega_view = "ENTREGAS" in view_name or "ENTREGA" in view_name

    # Title: use `NOME_PACIENTE` when available (user requirement)
    id_at = _get("ID_ATENDIMENTO") or _get("idregistro") or _get("id")
    nome_paciente = _get("NOME_PACIENTE") or _get("nome_paciente") or _get("NOME") or _get("nome")
    if nome_paciente:
        title = str(nome_paciente)
    elif _get("title"):
        title = str(_get("title"))
    elif id_at:
        title = str(id_at)
    else:
        title = "visit"

    address = _get("address") or _get("endereco_geolocalizacao") or _get("ENDERECO") or _get("endereco") or ""

    payload: Dict[str, Any] = {
        "title": title,
        "address": address,
        # properties: deixar vazio aqui, vamos preencher apenas chaves úteis depois
        "properties": {},
    }

    rows = record.get("items") or record.get("rows") or record.get("ITEMS") or []
    first_row = rows[0] if rows else {}

    def _get_from_any(field_name: str, *alts: str):
        value = _get(field_name, *alts)
        if value not in (None, ""):
            return value
        for row in rows:
            if not isinstance(row, dict):
                continue
            for key in (field_name,) + alts:
                if row.get(key) not in (None, ""):
                    return row.get(key)
        return None

    delivery_note_lines: List[str] = []

    def _normalize_descriptor_value(value: Any) -> str:
        if value is None:
            return ""
        try:
            text = str(value).strip()
        except Exception:
            return ""
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_only = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
        return ascii_only.lower()

    descriptor_parts: List[str] = []

    def _collect_descriptors(*values: Any) -> None:
        for value in values:
            norm = _normalize_descriptor_value(value)
            if norm:
                descriptor_parts.append(norm)

    _collect_descriptors(
        _get("ESPECIALIDADE"),
        _get("especialidade"),
        _get("TIPOVISITA"),
        _get("tipovisita"),
        record.get("visit_type"),
        record.get("notes"),
    )
    for row in rows:
        if not isinstance(row, dict):
            continue
        _collect_descriptors(
            row.get("ESPECIALIDADE"),
            row.get("especialidade"),
            row.get("TIPOVISITA"),
            row.get("tipovisita"),
            row.get("TIPO_ENTREGA"),
            row.get("TIPO"),
            row.get("notes"),
        )

    descriptor_blob = " ".join(descriptor_parts)

    def _infer_delivery_visit_type(default_type: str = "rota_log") -> str:
        """Define a tag logística priorizando o valor homolgado (TP_ENTREGA/TIPO_ENTREGA)."""

        candidate_fields = (
            "TP_ENTREGA",
            "tp_entrega",
            "TIPO_ENTREGA",
            "tipo_entrega",
            "TIPO",
            "tipo",
            "SUBTIPO",
            "subtipo",
            "MOTIVO",
            "motivo",
            "DESC_TIPO",
            "desc_tipo",
            "TIPO_MOVIMENTO",
            "tipo_movimento",
            "TIPO_MOVIMENTACAO",
            "tipo_movimentacao",
        )

        descriptors: List[str] = []
        exact_tokens: List[str] = []
        for field in candidate_fields:
            value = _get(field)
            if value not in (None, ""):
                text = str(value)
                descriptors.append(text)
                exact_tokens.append(text)

        for row in rows:
            if not isinstance(row, dict):
                continue
            for field in candidate_fields:
                value = row.get(field)
                if value not in (None, ""):
                    text = str(value)
                    descriptors.append(text)
                    exact_tokens.append(text)

        if descriptor_blob:
            descriptors.append(descriptor_blob)

        normalized_exact = [_normalize_descriptor_value(val) for val in exact_tokens]
        allowed_tags = {"rota_log", "adm_log", "acr_log"}
        disabled_tags = {"ret_log", "pad_log"}
        for token in normalized_exact:
            if token in allowed_tags:
                return token
            if token in disabled_tags:
                return default_type

        normalized_blob = " ".join(_normalize_descriptor_value(val) for val in descriptors if val not in (None, ""))

        if "acresc" in normalized_blob:
            return "acr_log"
        if "admis" in normalized_blob:
            return "adm_log"

        # Retirada (ret_log) e mudança de PAD (pad_log) ainda não estão ativos.
        return default_type

    visit_category = None
    if is_entrega_view or tp == 2:
        visit_category = "delivery"
    elif any(token in descriptor_blob for token in ("rota", "motoboy", "rota_log", "entrega")):
        visit_category = "delivery"
    elif any(token in descriptor_blob for token in ("enferm", "enfermeir")):
        visit_category = "enf"
    elif any(token in descriptor_blob for token in ("medic", "pediatr")):
        visit_category = "med"

    is_delivery_like = visit_category == "delivery"

    # mark source if this behaves like a delivery dataset
    if is_entrega_view or is_delivery_like:
        payload["properties"]["record_type"] = "entrega"

    # additional top-level fields expected by SimpliRoute — fill when available, else blank/empty
    payload["tracking_id"] = _get("tracking_id") or _get("TRACKING_ID") or _get("tracking") or ""
    payload["order"] = _get("order") or _get("ORDER") or None
    payload["route"] = _get("route") or _get("ROUTE") or None
    payload["route_estimated_time_start"] = _get("route_estimated_time_start") or _get("ROUTE_ESTIMATED_TIME_START") or None
    payload["route_status"] = _get("route_status") or _get("ROUTE_STATUS") or None
    payload["programmed_date"] = _get("programmed_date") or _get("programmed") or None
    payload["estimated_time_arrival"] = _get("estimated_time_arrival") or None
    payload["estimated_time_departure"] = _get("estimated_time_departure") or None
    payload["checkin_time"] = _get("checkin_time") or _get("CHECKIN_TIME") or None
    payload["checkout_time"] = _get("checkout_time") or _get("CHECKOUT_TIME") or None
    payload["checkout_latitude"] = _get("checkout_latitude") or _get("CHECKOUT_LATITUDE") or None
    payload["checkout_longitude"] = _get("checkout_longitude") or _get("CHECKOUT_LONGITUDE") or None
    payload["checkout_comment"] = _get("checkout_comment") or _get("CHECKOUT_COMMENT") or ""
    payload["checkout_observation"] = _get("checkout_observation") or _get("CHECKOUT_OBSERVATION") or None
    payload["signature"] = _get("signature") or None
    payload["pictures"] = _get("pictures") or []
    payload["created"] = _get("created") or _get("created_at") or None
    payload["modified"] = _get("modified") or _get("updated_at") or None
    payload["eta_predicted"] = _get("eta_predicted") or None
    payload["eta_current"] = _get("eta_current") or None
    payload["driver"] = _get("driver") or None
    payload["vehicle"] = _get("vehicle") or None
    payload["priority"] = bool(_get("priority") or False)
    payload["has_alert"] = bool(_get("has_alert") or False)
    # preserve numeric zero values (do not coerce falsy 0 into None)
    pl = _get("priority_level")
    payload["priority_level"] = pl if pl is not None else None
    payload["extra_field_values"] = _get("extra_field_values") or {}
    # also allow top-level extra fields to be included in extra_field_values
    # e.g., checkout_enfermagem, nome_profissional
    for k in ("checkout_enfermagem", "nome_profissional"):
        if k in record and record.get(k) is not None:
            payload["extra_field_values"][k] = record.get(k)
    payload["geocode_alert"] = _get("geocode_alert") or None
    payload["current_eta"] = _get("current_eta") or None
    payload["fleet"] = _get("fleet") or None
    payload["on_its_way"] = _get("on_its_way") or None
    payload["seller"] = _get("seller") or None
    payload["is_route_completed"] = _get("is_route_completed") if _get("is_route_completed") is not None else False

    # planned_date if present (preferred) or from eventdate
    # suportar campo DT_VISITA vindo do Gnexum
    pd = (
        _get("planned_date")
        or _get("eventdate")
        or _get("EVENTDATE")
        or _get("DT_VISITA")
        or _get("dt_visita")
        or _get("DT_ENTREGA")
        or _get("dt_entrega")
    )
    try:
        if isinstance(pd, (datetime, date)):
            payload["planned_date"] = pd.strftime("%Y-%m-%d")
        elif isinstance(pd, str) and pd:
            payload["planned_date"] = pd.split("T")[0]
    except Exception:
        pass

    # Window times (delivery often uses wide windows) — prefer record values when present
    payload["window_start"] = _get("window_start") or _get("WINDOW_START") or None
    payload["window_end"] = _get("window_end") or _get("WINDOW_END") or None
    payload["window_start_2"] = _get("window_start_2") or _get("WINDOW_START_2") or None
    payload["window_end_2"] = _get("window_end_2") or _get("WINDOW_END_2") or None

    def _apply_window_defaults() -> None:
        defaults = DEFAULT_WINDOW_RANGES.get(visit_category)
        if not defaults:
            return
        window_start_1, window_end_1, window_start_2, window_end_2 = defaults
        if not payload.get("window_start"):
            payload["window_start"] = window_start_1
        if not payload.get("window_end"):
            payload["window_end"] = window_end_1
        if not payload.get("window_start_2"):
            payload["window_start_2"] = window_start_2
        if not payload.get("window_end_2"):
            payload["window_end_2"] = window_end_2

    _apply_window_defaults()

    # loads and duration
    payload["load"] = float(_get("load") or _get("volume") or 0.0)
    payload["load_2"] = float(_get("load_2") or 0.0)
    payload["load_3"] = float(_get("load_3") or 0.0)

    # Duration (service time) in HH:MM:SS when provided or fallback
    duration = _get("duration")
    if _is_blank_duration(duration):
        duration = _get("service_time")
    if _is_blank_duration(duration):
        default_minutes = DEFAULT_DURATION_MINUTES.get(visit_category)
        if default_minutes is not None:
            duration = default_minutes
    payload["duration"] = _normalize_duration(duration)

    # contact/reference/notes fields expected by SimpliRoute
    contact_name = _get("PESSOACONTATO") or _get("contact_name") or ""
    contact_phone = _get("TELEFONES") or _get("contact_phone") or ""
    contact_email = _sanitize_email(_get("EMAIL") or _get("contact_email"))
    payload["contact_name"] = contact_name
    payload["contact_phone"] = contact_phone
    payload["contact_email"] = contact_email

    def _delivery_reference() -> str:
        prescricao = _get_from_any("ID_PRESCRICAO")
        protocolo = _get_from_any("ID_PROTOCOLO")
        if prescricao and protocolo:
            # Referência = protocolo + prescrição
            return f"{_normalize_numeric_string(protocolo)}{_normalize_numeric_string(prescricao)}"
        return ""

    def _prefix_notes(notes_value):
        """Add [A] prefix to notes field."""
        if not notes_value:
            return "[A]"
        notes_str = str(notes_value)
        if notes_str.startswith("[A]"):
            return notes_str
        return f"[A]{notes_str}"

    if is_delivery_like:
        reference_value = _delivery_reference() or _get("reference") or _get("ID_ATENDIMENTO") or _get("idregistro") or ""
    else:
        reference_value = _get("reference") or _get("ID_ATENDIMENTO") or _get("idregistro") or ""
    payload["reference"] = str(reference_value)
    payload["notes"] = _prefix_notes(_get("notes") or "")

    # Items: converter para o formato esperado pela API de visits.items

    # Latitude/longitude: include only when present and non-empty in the source record.
    # If absent, leave as None so the client/pruner will omit the keys and allow SR to geocode.
    lat_src = _get("latitude") or _get("LATITUDE") or _get("lat") or _get("LAT")
    lon_src = _get("longitude") or _get("LONGITUDE") or _get("lon") or _get("LON")
    payload["latitude"] = str(lat_src) if lat_src not in (None, "") else None
    payload["longitude"] = str(lon_src) if lon_src not in (None, "") else None

    # if contact fields are empty at record-level, use first row values
    if not payload.get("contact_name"):
        payload["contact_name"] = first_row.get("PESSOACONTATO") or first_row.get("pessoacontato") or payload.get("contact_name") or ""
    if not payload.get("contact_phone"):
        payload["contact_phone"] = first_row.get("TELEFONES") or first_row.get("telefones") or payload.get("contact_phone") or ""
    if payload.get("contact_email") in (None, ""):
        payload["contact_email"] = _sanitize_email(
            first_row.get("EMAIL") or first_row.get("email") or payload.get("contact_email")
        )

    def _map_gnexum_row_to_item(r: Dict[str, Any]) -> Dict[str, Any]:
        # Criar um item representando a visita/serviço para este row do Gnexum
        title = r.get("ESPECIALIDADE") or r.get("TIPOVISITA") or r.get("nome") or r.get("title") or "service"
        profissional = r.get("PROFISSIONAL") or r.get("PROFISSIONAL") or ""
        periodicidade = r.get("PERIODICIDADE") or r.get("periodicidade") or ""
        telefones = r.get("TELEFONES") or r.get("telefones") or ""
        contato = r.get("PESSOACONTATO") or r.get("PESSOACONTATO") or ""
        email = r.get("EMAIL") or r.get("email") or ""
        cpf = r.get("CPF") or r.get("cpf") or ""

        notes_parts = []
        if profissional:
            notes_parts.append(f"Prof: {profissional}")
        if periodicidade:
            notes_parts.append(f"Periodicidade: {periodicidade}")
        if telefones:
            notes_parts.append(f"Tel: {telefones}")
        if contato:
            notes_parts.append(f"Contato: {contato}")
        if email:
            notes_parts.append(f"Email: {email}")
        if cpf:
            notes_parts.append(f"CPF: {cpf}")

        notes = "; ".join(notes_parts)

        return {
            "title": title,
            "load": float(r.get("load") or 0.0),
            "load_2": float(r.get("load_2") or 0.0),
            "load_3": float(r.get("load_3") or 0.0),
            "reference": str(r.get("ID_ATENDIMENTO") or r.get("idregistro") or r.get("reference") or ""),
            "quantity_planned": _ceil_quantity(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 1.0, default=1.0),
            "notes": _prefix_notes(notes),
        }

    # Determine visit type to decide whether to include items.
    # Check record-level fields and all rows: if any mention 'medic'/'enferm' we omit items.
    visit_type_candidates = []
    visit_type_candidates.append(_get("ESPECIALIDADE") or _get("TIPOVISITA") or _get("visit_type") or "")
    visit_type_candidates.append(first_row.get("ESPECIALIDADE") or first_row.get("TIPOVISITA") or "")
    # also inspect every row for ESPECIALIDADE/TIPOVISITA
    for r in rows:
        try:
            visit_type_candidates.append((r.get("ESPECIALIDADE") or r.get("TIPOVISITA") or ""))
        except Exception:
            continue

    visit_type_combined = " ".join([str(x) for x in visit_type_candidates if x]).lower()

    # For delivery view, always try to build items from rows using delivery-oriented fields
    if is_entrega_view or is_delivery_like:
        items = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            # try several possible field names used in delivery views
            title_candidates = [
                "NOME_MATERIAL",
                "PRODUTO",
                "NOME",
                "DESCRICAO",
                "descricao",
                "title",
                "nome",
            ]
            title_item = None
            for cand in title_candidates:
                if cand in r and r.get(cand) not in (None, ""):
                    title_item = r.get(cand)
                    break
            if not title_item:
                title_item = "item"

            qty_requested_raw = (
                r.get("QTD_ITEM_SOLICITADO")
                or r.get("QTDE_SOLICITADA")
                or r.get("QTD_SOLICITADA")
                or r.get("QUANTIDADE")
                or r.get("quantity_planned")
                or r.get("quantidade")
                or r.get("qty")
                or 1.0
            )
            qty_delivered_raw = (
                r.get("QTD_ITEM_ENVIADO")
                or r.get("QTDE_ATENDIDA")
                or r.get("QTD_ENTREGUE")
                or r.get("QTD_ITEM_ENTREGUE")
                or r.get("QTD_SEPARADA")
                or r.get("quantity_delivered")
                or 0.0
            )

            qty_planned = _ceil_quantity(qty_requested_raw, default=1.0)
            qty_delivered = _ceil_quantity(qty_delivered_raw, default=0.0)

            item_reference = (
                r.get("ID_MATERIAL")
                or r.get("ID_ITEM")
                or r.get("IDRESUPPLY")
                or r.get("ID_PROTOCOLO")
                or r.get("ID_ATENDIMENTO")
                or r.get("reference")
                or ""
            )

            suffix = f"{_zero_pad_quantity(qty_delivered)}/{_zero_pad_quantity(qty_planned)}"
            wrapped_lines = _wrap_material_description(str(title_item))
            if wrapped_lines:
                wrapped_lines[-1] = f"{wrapped_lines[-1]} - {suffix}"
                delivery_note_lines.extend(wrapped_lines)

            # note: `quantity_delivered` remains None per integration contract
            # but suffix and internal representations should use ceiled numbers
            item = {
                "title": title_item,
                "status": "pending",
                "load": float(r.get("load") or 0.0),
                "load_2": float(r.get("load_2") or 0.0),
                "load_3": float(r.get("load_3") or 0.0),
                "reference": str(item_reference),
                "quantity_planned": qty_planned,
                "quantity_delivered": None,
            }
            items.append(item)
        payload["items"] = items
    else:
        # When visit type indicates medical or nursing visit, do not include items
        if any(tok in visit_type_combined for tok in ("medic", "médic", "enferm", "enfermeir")):
            # explicit: no items key for médico/enfermeiro visits
            pass
        else:
            items = []
            for r in rows:
                if isinstance(r, dict) and any(k in r for k in ("ESPECIALIDADE", "TIPOVISITA", "PROFISSIONAL", "PERIODICIDADE")):
                    base = _map_gnexum_row_to_item(r)
                else:
                    base = {
                        "title": r.get("title") or r.get("nome") or "item",
                        "load": float(r.get("load") or 0.0),
                        "load_2": float(r.get("load_2") or 0.0),
                        "load_3": float(r.get("load_3") or 0.0),
                        "reference": r.get("reference") or r.get("ref") or "",
                        "quantity_planned": _ceil_quantity(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 0.0, default=0.0),
                        "notes": _prefix_notes(r.get("notes", "")),
                    }

                # adapt item shape to SimpliRoute expected fields
                item = {
                    # title, load fields kept
                    "title": base.get("title"),
                    "status": "pending",
                    "load": float(base.get("load") or 0.0),
                    "load_2": float(base.get("load_2") or 0.0),
                    "load_3": float(base.get("load_3") or 0.0),
                    "reference": base.get("reference") or "",
                    "quantity_planned": _ceil_quantity(base.get("quantity_planned") or 1.0, default=1.0),
                    "quantity_delivered": None,
                }
                items.append(item)
            payload["items"] = items

    # assemble final payload as OrderedDict to respect the exact field order required
    def _norm_str(s: Any) -> Any:
        if isinstance(s, str):
            try:
                return unicodedata.normalize("NFC", s)
            except Exception:
                return s
        return s

    def _normalize_obj(obj: Any):
        # preserve OrderedDict type when normalizing
        if isinstance(obj, OrderedDict):
            new = OrderedDict()
            for k, v in obj.items():
                new[k] = _normalize_obj(v)
            return new
        if isinstance(obj, dict):
            new = {}
            for k, v in obj.items():
                new[k] = _normalize_obj(v)
            return new
        if isinstance(obj, list):
            return [_normalize_obj(v) for v in obj]
        return _norm_str(obj)

    ordered = OrderedDict()
    ordered["id"] = None
    ordered["order"] = payload.get("order")
    ordered["tracking_id"] = payload.get("tracking_id") or None
    ordered["status"] = _get("status") or payload.get("status") or "pending"
    ordered["title"] = payload.get("title")
    ordered["address"] = payload.get("address")
    # prefer the payload latitude/longitude when available to avoid re-geocoding
    ordered["latitude"] = payload.get("latitude")
    ordered["longitude"] = payload.get("longitude")
    ordered["load"] = payload.get("load", 0.0)
    ordered["load_2"] = payload.get("load_2", 0.0)
    ordered["load_3"] = payload.get("load_3", 0.0)
    ordered["window_start"] = payload.get("window_start")
    ordered["window_end"] = payload.get("window_end")
    ordered["window_start_2"] = payload.get("window_start_2")
    ordered["window_end_2"] = payload.get("window_end_2")
    ordered["duration"] = payload.get("duration")
    ordered["contact_name"] = payload.get("contact_name")
    ordered["contact_phone"] = payload.get("contact_phone")
    ordered["contact_email"] = payload.get("contact_email")
    ordered["reference"] = payload.get("reference")
    ordered["notes"] = _prefix_notes(payload.get("notes") or "")
    ordered["skills_required"] = []
    ordered["skills_optional"] = []
    ordered["tags"] = []
    ordered["planned_date"] = payload.get("planned_date")
    ordered["programmed_date"] = payload.get("programmed_date")
    ordered["route"] = payload.get("route")
    ordered["route_status"] = payload.get("route_status")
    ordered["estimated_time_arrival"] = payload.get("estimated_time_arrival")
    ordered["estimated_time_departure"] = payload.get("estimated_time_departure")
    ordered["checkin_time"] = payload.get("checkin_time")
    ordered["checkout_time"] = payload.get("checkout_time")
    ordered["checkout_latitude"] = payload.get("checkout_latitude")
    ordered["checkout_longitude"] = payload.get("checkout_longitude")
    ordered["checkout_comment"] = payload.get("checkout_comment") or ""
    ordered["checkout_observation"] = payload.get("checkout_observation")
    ordered["signature"] = payload.get("signature")
    ordered["pictures"] = payload.get("pictures") or []
    ordered["created"] = payload.get("created")
    ordered["modified"] = payload.get("modified")
    ordered["eta_predicted"] = payload.get("eta_predicted")
    ordered["eta_current"] = payload.get("eta_current")
    ordered["driver"] = payload.get("driver")
    ordered["vehicle"] = payload.get("vehicle")
    ordered["priority"] = bool(payload.get("priority") or False)
    ordered["has_alert"] = bool(payload.get("has_alert") or False)
    ordered["priority_level"] = payload.get("priority_level")
    ordered["extra_field_values"] = payload.get("extra_field_values") or {}
    ordered["geocode_alert"] = payload.get("geocode_alert")
    # placeholder ensures visit_type stays immediately after geocode_alert in final JSON
    ordered["visit_type"] = None
    # visit_type: prefer mapping derived from ESPECIALIDADE; do not use raw TIPOVISITA
    # TIPOVISITA will be preserved in properties for traceability.
    visit_type_val = (
        _get("TIPOVISITA") or _get("tipovisita") or (first_row.get("TIPOVISITA") if isinstance(first_row, dict) else None) or None
    )
    # Map ESPECIALIDADE (valor do Gnexum) para a key esperada pelo SimpliRoute
    esp_val_record = (_get("ESPECIALIDADE") or _get("especialidade") or (first_row.get("ESPECIALIDADE") if isinstance(first_row, dict) else "") or "")

    esp_clean = _normalize_descriptor_value(esp_val_record)

    visit_type_key = None
    if esp_clean and ("enferm" in esp_clean or "enfermeir" in esp_clean or "enfermeito" in esp_clean):
        visit_type_key = "enf_visit"
    elif esp_clean and any(tok in esp_clean for tok in ("medico", "medica", "med", "pediatria")):
        visit_type_key = "med_visit"

    # Definir visit_type APENAS quando houver mapeamento conhecido a partir de ESPECIALIDADE.
    if visit_type_key:
        ordered["visit_type"] = visit_type_key
    else:
        # se não temos mapeamento por ESPECIALIDADE, tentar inferir pela string de TIPOVISITA
        if isinstance(visit_type_val, str) and visit_type_val:
            vt_norm = _normalize_descriptor_value(visit_type_val)
            if "enferm" in vt_norm:
                ordered["visit_type"] = "enf_visit"
            elif any(tok in vt_norm for tok in ("medico", "medica", "med", "pediatria")):
                ordered["visit_type"] = "med_visit"
    ordered["current_eta"] = payload.get("current_eta")
    ordered["fleet"] = payload.get("fleet")
    ordered["seller"] = payload.get("seller")
    ordered["is_route_completed"] = payload.get("is_route_completed") if payload.get("is_route_completed") is not None else False

    # copy known property keys / values from record or rows (we don't add a `properties` block)
    prof = (
        _get("PROFISSIONAL")
        or _get("profissional")
        or first_row.get("PROFISSIONAL")
        or first_row.get("profissional")
        or (payload.get("extra_field_values") or {}).get("nome_profissional")
    )
    esp = (_get("ESPECIALIDADE") or _get("especialidade") or first_row.get("ESPECIALIDADE") or first_row.get("especialidade") or "")
    # Periodicidade: aceitar várias variações e procurar também dentro das rows
    per = (
        _get("PERIODICIDADE")
        or _get("periodicidade")
        or _get("PERIODICIDADE_VISITA")
        or _get("periodicidade_visita")
        or _get("FREQUENCIA")
        or _get("frequencia")
        or first_row.get("PERIODICIDADE")
        or first_row.get("periodicidade")
        or first_row.get("PERIODICIDADE_VISITA")
        or first_row.get("periodicidade_visita")
        or first_row.get("FREQUENCIA")
        or first_row.get("frequencia")
    )
    # if still not found, try scanning record keys (normalized) and then rows
    def _find_period_in_mapping(mapping: Dict[str, Any]):
        for k, v in mapping.items():
            if not k:
                continue
            kn = str(k).lower()
            kn_norm = "".join(c for c in unicodedata.normalize("NFKD", kn) if unicodedata.category(c) != "Mn")
            if "period" in kn_norm or "periodic" in kn_norm or "frequ" in kn_norm:
                if v:
                    return v
        return None

    if not per:
        # scan top-level record
        try:
            per = _find_period_in_mapping(record) or per
        except Exception:
            pass

    if not per and isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            found = _find_period_in_mapping(r)
            if found:
                per = found
                break
    # TIPOVISITA original value for traceability
    # Prefer record-level values, else first non-empty value from rows
    def _first_non_empty(*values):
        for v in values:
            try:
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    return s
            except Exception:
                continue
        return ""

    tipovisita_val = _first_non_empty(
        _get("TIPOVISITA"), _get("tipovisita"),
        first_row.get("TIPOVISITA") if isinstance(first_row, dict) else None,
        first_row.get("tipovisita") if isinstance(first_row, dict) else None,
    )

    # Find ESPECIALIDADE: record-level preferred, else scan rows for first non-empty
    esp_val = _first_non_empty(_get("ESPECIALIDADE"), _get("especialidade"))
    if not esp_val and isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            candidate = _first_non_empty(r.get("ESPECIALIDADE"), r.get("especialidade"))
            if candidate:
                esp_val = candidate
                break

    # Format notes as "ESPECIALIDADE - TIPOVISITA" (omit separator when missing)
    if esp_val and tipovisita_val:
        payload["notes"] = _prefix_notes(f"{esp_val} - {tipovisita_val}")
    else:
        payload["notes"] = _prefix_notes(esp_val or tipovisita_val or "")

    # Safety: if the properties or visit_type explicitly indicate a medical/nursing visit,
    # ensure we do NOT include items even if rows were present upstream.
    esp_val = (esp or ordered.get("visit_type") or "")
    if isinstance(esp_val, str) and any(tok in esp_val.lower() for tok in ("medico", "médico", "med", "enferm", "enfermeir", "enfermeito")):
        ordered.pop("items", None)

    # items: include only when present in payload (we omitted for medico/enfermeiro)
    if "items" in payload:
        ordered["items"] = payload.get("items")
    else:
        ordered["items"] = []


    # Ensure final notes assembled from available fields (record-level or rows)
    def _first_non_empty_local(*vals):
        for v in vals:
            try:
                if v is None:
                    continue
                s = str(v).strip()
                if s:
                    return s
            except Exception:
                continue
        return ""

    # prefer record-level ESPECIALIDADE/TIPOVISITA, else first row that has them
    final_esp = _first_non_empty_local(_get("ESPECIALIDADE"), _get("especialidade"))
    if not final_esp and isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            cand = _first_non_empty_local(r.get("ESPECIALIDADE"), r.get("especialidade"))
            if cand:
                final_esp = cand
                break

    final_tip = _first_non_empty_local(_get("TIPOVISITA"), _get("tipovisita"))
    if not final_tip and isinstance(rows, list):
        for r in rows:
            if not isinstance(r, dict):
                continue
            cand = _first_non_empty_local(r.get("TIPOVISITA"), r.get("tipovisita"))
            if cand:
                final_tip = cand
                break

    if final_esp and final_tip:
        ordered["notes"] = _prefix_notes(f"{final_esp} - {final_tip}")
    elif final_esp:
        ordered["notes"] = _prefix_notes(final_esp)
    elif final_tip:
        ordered["notes"] = _prefix_notes(final_tip)

    # If this is delivery dataset, prefer explicit delivery visit_type and notes
    if is_entrega_view or is_delivery_like:
        try:
            # deliveries usam tags específicas (rota/admissao/acrescimo)
            ordered["visit_type"] = _infer_delivery_visit_type("rota_log")
            if delivery_note_lines:
                ordered["notes"] = _prefix_notes("\n".join(delivery_note_lines))
            else:
                delivery_note = _get("TIPO_ENTREGA") or _get("TIPO") or final_esp or final_tip or "ENTREGA"
                ordered["notes"] = _prefix_notes(str(delivery_note))
        except Exception:
            ordered["notes"] = _prefix_notes(ordered.get("notes") or "ENTREGA")

    # Normalize strings throughout the ordered payload (NFC)
    ordered = _normalize_obj(ordered)

    # Ensure all keys from the example JSON remain present. For missing values, use
    # sensible empty defaults (no literal 'None'/'NULL' strings):
    string_keys = {
        "id",
        "title",
        "address",
        "window_start",
        "window_end",
        "window_start_2",
        "window_end_2",
        "duration",
        "contact_name",
        "contact_phone",
        "contact_email",
        "reference",
        "notes",
        "planned_date",
        "programmed_date",
        "route",
        "route_estimated_time_start",
        "route_status",
        "estimated_time_arrival",
        "estimated_time_departure",
        "checkin_time",
        "checkout_time",
        "checkout_latitude",
        "checkout_longitude",
        "checkout_comment",
        "checkout_observation",
        "signature",
        "created",
        "modified",
        "eta_predicted",
        "eta_current",
        "current_eta",
        "geocode_alert",
        "fleet",
        "seller",
    }
    list_keys = {"skills_required", "skills_optional", "tags", "pictures"}
    dict_keys = {"extra_field_values"}
    bool_keys = {"priority", "has_alert", "is_route_completed"}
    numeric_keys = {"load", "load_2", "load_3", "driver", "vehicle", "priority_level"}
    coord_keys = {"latitude", "longitude"}

    for k in list(ordered.keys()):
        v = ordered.get(k)
        if v is None:
            if k in list_keys:
                ordered[k] = []
            elif k in dict_keys:
                ordered[k] = {}
            elif k in bool_keys:
                ordered[k] = False
            elif k in numeric_keys:
                # leave numeric keys as None so the client will omit them
                ordered[k] = None
            elif k in coord_keys:
                # coordinates: leave as None to allow geocoding if absent
                ordered[k] = None
            elif k in string_keys:
                # leave strings as None so they are omitted when not present
                ordered[k] = None
            else:
                ordered[k] = None

    # If items is present but empty, remove it (do not send empty items array for medico/enfermeiro)
    if "items" in ordered and (ordered.get("items") is None or (isinstance(ordered.get("items"), list) and len(ordered.get("items")) == 0)):
        ordered.pop("items", None)

    return ordered
