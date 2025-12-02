from typing import Any, Dict, List
from collections import OrderedDict
import unicodedata
from datetime import datetime, date


def _minutes_to_hhmmss(minutes: int) -> str:
    """Converte minutos inteiros em string 'HH:MM:SS' usada pelo campo duration."""
    try:
        m = int(minutes)
    except Exception:
        m = 0
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}:00"


def _normalize_duration(value) -> str:
    """Aceita várias representações de duração e retorna 'HH:MM:SS'.

    - Se já estiver no formato HH:MM:SS, retorna como está.
    - Se for número (minutos) converte para HH:MM:SS.
    - Se for string contendo apenas minutos ('20') converte.
    - Caso inválido, retorna '00:00:00'.
    """
    if value is None:
        return "00:00:00"
    # já no formato HH:MM:SS
    if isinstance(value, str):
        v = value.strip()
        parts = v.split(":")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            return v
        # se for um número em string
        if v.isdigit():
            return _minutes_to_hhmmss(int(v))
        # tentar extrair minutos se for como '20m' ou '20 min'
        try:
            digits = "".join(c for c in v if c.isdigit())
            if digits:
                return _minutes_to_hhmmss(int(digits))
        except Exception:
            pass
        return "00:00:00"
    # se for inteiro/float (minutos)
    try:
        return _minutes_to_hhmmss(int(value))
    except Exception:
        return "00:00:00"


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
    def _get(k, *alts, default=None):
        for key in (k,) + alts:
            if key in record and record.get(key) is not None:
                return record.get(key)
        return default

    tp = int(_get("tpregistro", "TPREGISTRO", default=1) or 1)

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
    payload["priority_level"] = _get("priority_level") or None
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
    pd = _get("planned_date") or _get("eventdate") or _get("EVENTDATE") or _get("DT_VISITA") or _get("dt_visita")
    try:
        if isinstance(pd, (datetime, date)):
            payload["planned_date"] = pd.strftime("%Y-%m-%d")
        elif isinstance(pd, str) and pd:
            payload["planned_date"] = pd.split("T")[0]
    except Exception:
        pass

    # loads and duration
    payload["load"] = float(_get("load") or _get("volume") or 0.0)
    payload["load_2"] = float(_get("load_2") or 0.0)
    payload["load_3"] = float(_get("load_3") or 0.0)

    # Duration (service time) in HH:MM:SS when provided or fallback
    duration = _get("duration")
    if duration is None:
        # allow 'service_time' or default 0
        duration = _get("service_time") or 0
    payload["duration"] = _normalize_duration(duration)

    # contact/reference/notes fields expected by SimpliRoute
    contact_name = _get("PESSOACONTATO") or _get("contact_name") or ""
    contact_phone = _get("TELEFONES") or _get("contact_phone") or ""
    contact_email = _get("EMAIL") or _get("contact_email") or None
    payload["contact_name"] = contact_name
    payload["contact_phone"] = contact_phone
    payload["contact_email"] = contact_email
    payload["reference"] = str(_get("reference") or _get("ID_ATENDIMENTO") or _get("idregistro") or "")
    payload["notes"] = _get("notes") or ""

    # Items: converter para o formato esperado pela API de visits.items
    rows = record.get("items") or record.get("rows") or record.get("ITEMS") or []

    # use first row as fallback source for visit-level fields when present
    first_row = rows[0] if rows else {}

    # latitude/longitude: mapear quando disponíveis (prevenir re-geocoding)
    lat = _get("latitude") or _get("LATITUDE") or _get("lat") or None
    lon = _get("longitude") or _get("LONGITUDE") or _get("lon") or _get("lng") or None
    # fallback para campos na primeira linha
    if not lat and isinstance(first_row, dict):
        lat = first_row.get("latitude") or first_row.get("LATITUDE") or first_row.get("checkout_latitude")
    if not lon and isinstance(first_row, dict):
        lon = first_row.get("longitude") or first_row.get("LONGITUDE") or first_row.get("checkout_longitude")
    try:
        payload["latitude"] = float(lat) if lat not in (None, "") else None
    except Exception:
        payload["latitude"] = None
    try:
        payload["longitude"] = float(lon) if lon not in (None, "") else None
    except Exception:
        payload["longitude"] = None

    # if contact fields are empty at record-level, use first row values
    if not payload.get("contact_name"):
        payload["contact_name"] = first_row.get("PESSOACONTATO") or first_row.get("pessoacontato") or payload.get("contact_name") or ""
    if not payload.get("contact_phone"):
        payload["contact_phone"] = first_row.get("TELEFONES") or first_row.get("telefones") or payload.get("contact_phone") or ""
    if payload.get("contact_email") in (None, ""):
        payload["contact_email"] = first_row.get("EMAIL") or first_row.get("email") or payload.get("contact_email")

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
            "quantity_planned": float(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 1.0),
            "notes": notes,
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
                    "quantity_planned": float(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 0.0),
                    "notes": r.get("notes", ""),
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
                "visit": None,
                "notes": base.get("notes") or "",
                "quantity_planned": float(base.get("quantity_planned") or 1.0),
                "quantity_delivered": 0.0,
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
    ordered["window_start"] = None
    ordered["window_end"] = None
    ordered["window_start_2"] = None
    ordered["window_end_2"] = None
    ordered["duration"] = payload.get("duration")
    ordered["contact_name"] = payload.get("contact_name")
    ordered["contact_phone"] = payload.get("contact_phone")
    ordered["contact_email"] = payload.get("contact_email")
    ordered["reference"] = payload.get("reference")
    ordered["notes"] = payload.get("notes") or ""
    ordered["skills_required"] = []
    ordered["skills_optional"] = []
    ordered["tags"] = []
    ordered["planned_date"] = payload.get("planned_date")
    ordered["programmed_date"] = payload.get("programmed_date")
    ordered["route"] = payload.get("route")
    ordered["route_estimated_time_start"] = payload.get("route_estimated_time_start")
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
    # visit_type: prefer mapping derived from ESPECIALIDADE; do not use raw TIPOVISITA
    # TIPOVISITA will be preserved in properties for traceability.
    visit_type_val = (
        _get("TIPOVISITA") or _get("tipovisita") or (first_row.get("TIPOVISITA") if isinstance(first_row, dict) else None) or None
    )
    # Map ESPECIALIDADE (valor do Gnexum) para a key esperada pelo SimpliRoute
    esp_val_record = (_get("ESPECIALIDADE") or _get("especialidade") or (first_row.get("ESPECIALIDADE") if isinstance(first_row, dict) else "") or "")

    esp_lower = str(esp_val_record or "").lower()

    visit_type_key = None
    if esp_lower and ("enferm" in esp_lower or "enfermeito" in esp_lower):
        visit_type_key = "enf_visit"
    elif esp_lower and any(tok in esp_lower for tok in ("medico", "médico", "med", "pediatria")):
        visit_type_key = "médica"

    # Definir visit_type APENAS quando houver mapeamento conhecido a partir de ESPECIALIDADE.
    if visit_type_key:
        ordered["visit_type"] = visit_type_key
    else:
        # se não temos mapeamento por ESPECIALIDADE, tentar inferir pela string de TIPOVISITA
        if isinstance(visit_type_val, str) and visit_type_val:
            vt_low = visit_type_val.lower()
            if "enferm" in vt_low:
                ordered["visit_type"] = "enf_visit"
            elif any(tok in vt_low for tok in ("med", "méd", "pediatria")):
                ordered["visit_type"] = "médica"
    ordered["current_eta"] = payload.get("current_eta")
    ordered["fleet"] = payload.get("fleet")
    ordered["seller"] = payload.get("seller")
    ordered["on_its_way"] = payload.get("on_its_way") if payload.get("on_its_way") is not None else None
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
        payload["notes"] = f"{esp_val} - {tipovisita_val}"
    else:
        payload["notes"] = esp_val or tipovisita_val or ""

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

    ordered["on_its_way"] = None

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
        ordered["notes"] = f"{final_esp} - {final_tip}"
    elif final_esp:
        ordered["notes"] = final_esp
    elif final_tip:
        ordered["notes"] = final_tip

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
    bool_keys = {"priority", "has_alert", "is_route_completed", "on_its_way"}
    numeric_keys = {"load", "load_2", "load_3", "driver", "vehicle", "priority_level", "latitude", "longitude"}

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
                # Use empty string for coordinates/numbers if original data absent
                ordered[k] = ""
            elif k in string_keys:
                ordered[k] = ""
            else:
                # Default to empty string to avoid sending literal nulls
                ordered[k] = ""

    # If items is present but empty, remove it (do not send empty items array for medico/enfermeiro)
    if "items" in ordered and (ordered.get("items") is None or (isinstance(ordered.get("items"), list) and len(ordered.get("items")) == 0)):
        ordered.pop("items", None)

    return ordered


def build_items_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for r in rows:
        items.append({
            "title": r.get("nome", "item"),
            "quantity_planned": float(r.get("quantidade", 1) or 1),
        })
    return items
