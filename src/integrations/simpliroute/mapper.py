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

    # Title: prefer `ID_ATENDIMENTO` + `NOME_PACIENTE` when available
    id_at = _get("ID_ATENDIMENTO") or _get("idregistro") or _get("id")
    nome_paciente = _get("NOME_PACIENTE") or _get("nome_paciente") or _get("NOME") or _get("nome")
    if id_at:
        # format: "<ID_ATENDIMENTO> <NOME_PACIENTE>" (concatenate ID and name)
        title = f"{id_at} {nome_paciente}".strip() if nome_paciente else str(id_at)
    elif _get("title"):
        title = str(_get("title"))
    elif nome_paciente:
        title = str(nome_paciente)
    else:
        title = "visit"

    address = _get("endereco_geolocalizacao") or _get("ENDERECO") or _get("endereco") or ""

    payload: Dict[str, Any] = {
        "title": title,
        "address": address,
        # properties: deixar vazio aqui, vamos preencher apenas chaves úteis depois
        "properties": {},
    }

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
    payload["duration"] = _minutes_to_hhmmss(duration)

    # contact/reference/notes fields expected by SimpliRoute
    contact_name = _get("PESSOACONTATO") or _get("contact_name") or ""
    contact_phone = _get("TELEFONES") or _get("contact_phone") or ""
    contact_email = _get("EMAIL") or _get("contact_email") or None
    payload["contact_name"] = contact_name
    payload["contact_phone"] = contact_phone
    payload["contact_email"] = contact_email
    payload["reference"] = str(_get("ID_ATENDIMENTO") or _get("idregistro") or "")
    payload["notes"] = _get("notes") or ""

    # Items: converter para o formato esperado pela API de visits.items
    rows = record.get("items") or record.get("rows") or record.get("ITEMS") or record.get("items") or []

    # use first row as fallback source for visit-level fields when present
    first_row = rows[0] if rows else {}

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
    ordered["order"] = None
    ordered["tracking_id"] = None
    ordered["status"] = "pending"
    ordered["title"] = payload.get("title")
    ordered["address"] = payload.get("address")
    ordered["latitude"] = None
    ordered["longitude"] = None
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
    ordered["programmed_date"] = None
    ordered["route"] = None
    ordered["estimated_time_arrival"] = None
    ordered["estimated_time_departure"] = None
    ordered["checkin_time"] = None
    ordered["checkout_time"] = None
    ordered["checkout_latitude"] = None
    ordered["checkout_longitude"] = None
    ordered["checkout_comment"] = ""
    ordered["checkout_observation"] = None
    ordered["signature"] = None
    ordered["pictures"] = []
    ordered["created"] = None
    ordered["modified"] = None
    ordered["eta_predicted"] = None
    ordered["eta_current"] = None
    ordered["priority"] = False
    ordered["has_alert"] = False
    ordered["priority_level"] = None
    ordered["extra_field_values"] = None
    ordered["geocode_alert"] = None
    # visit_type: prefer mapping derived from ESPECIALIDADE; do not use raw TIPOVISITA
    # TIPOVISITA will be preserved in properties for traceability.
    visit_type_val = (
        _get("TIPOVISITA") or _get("tipovisita") or first_row.get("TIPOVISITA") or first_row.get("tipovisita") or None
    )
    # Map ESPECIALIDADE (valor do Gnexum) para a key esperada pelo SimpliRoute
    esp_val_record = (_get("ESPECIALIDADE") or _get("especialidade") or first_row.get("ESPECIALIDADE") or first_row.get("especialidade") or "")

    def _strip_accents(s: str) -> str:
        try:
            return "".join(c for c in unicodedata.normalize("NFKD", s) if unicodedata.category(c) != "Mn")
        except Exception:
            return s

    esp_norm = _strip_accents(str(esp_val_record or "").lower()).strip()
    esp_lower = str(esp_val_record or "").lower()

    # Mapeamento conhecido: chaves/labels possíveis mapeadas para as keys do SR
    esp_to_visit_type = {
        "enfermagem": "enf_visit",
        "medica": "mÃ©dica",
        "médica": "mÃ©dica",
        "mÃ©dica": "mÃ©dica",
    }

    visit_type_key = None
    # tentativa de correspondência por substring tanto no valor cru quanto na versão sem acentos
    if esp_lower and "enferm" in esp_lower:
        visit_type_key = "enf_visit"
    elif esp_lower and any(tok in esp_lower for tok in ("med", "méd", "mÃ", "pediatria")):
        visit_type_key = "mÃ©dica"

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
                ordered["visit_type"] = "mÃ©dica"
    ordered["current_eta"] = None
    ordered["fleet"] = None
    ordered["seller"] = None

    # properties: include existing properties and add PROFESSIONAL/ESPECIALIDADE/PERIODICIDADE
    # Use OrderedDict to guarantee insertion order in properties
    props = OrderedDict()
    # copy known property keys: prefer record-level values, fallback to first_row
    prof = (_get("PROFISSIONAL") or _get("profissional") or first_row.get("PROFISSIONAL") or first_row.get("profissional"))
    esp = (_get("ESPECIALIDADE") or _get("especialidade") or first_row.get("ESPECIALIDADE") or first_row.get("especialidade"))
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
    # Inserir properties na ordem desejada: PROFISSIONAL, ESPECIALIDADE, PERIODICIDADE, TIPOVISITA
    # Garantir que sempre existam as 4 chaves (valor = string vazia quando não houver informação)
    props["PROFISSIONAL"] = prof or ""
    props["ESPECIALIDADE"] = esp or ""
    props["PERIODICIDADE"] = per or ""
    # incluir TIPOVISITA na propriedade para rastreabilidade (valor original do Gnexum)
    tipovisita_val = (_get("TIPOVISITA") or _get("tipovisita") or first_row.get("TIPOVISITA") or first_row.get("tipovisita") or "")
    props["TIPOVISITA"] = tipovisita_val or ""
    ordered["properties"] = props

    # Safety: if the properties or visit_type explicitly indicate a medical/nursing visit,
    # ensure we do NOT include items even if rows were present upstream.
    esp_val = (props.get("ESPECIALIDADE") or ordered.get("visit_type") or "")
    if isinstance(esp_val, str) and any(tok in esp_val.lower() for tok in ("medic", "médic", "enferm", "enfermeir")):
        ordered.pop("items", None)

    # items: include only when present in payload (we omitted for medico/enfermeiro)
    if "items" in payload:
        ordered["items"] = payload.get("items")
    else:
        ordered["items"] = []

    ordered["on_its_way"] = None

    # If id is None, remove it so SimpliRoute will generate the identifier on create
    if ordered.get("id") is None:
        ordered.pop("id", None)

    # Normalize strings throughout the ordered payload (NFC)
    ordered = _normalize_obj(ordered)

    # Remove keys whose value is None (don't send nulls unless we explicitly have a value)
    for k in list(ordered.keys()):
        if ordered[k] is None:
            ordered.pop(k, None)

    # If items is present but empty, remove it (don't send empty items array for medico/enfermeiro)
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
