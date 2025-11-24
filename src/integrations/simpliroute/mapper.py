from typing import Any, Dict, List
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
    tp = int(record.get("tpregistro", 1))
    # Title: prefer explicit title, else idregistro, else fallback
    if record.get("title"):
        title = str(record.get("title"))
    elif record.get("idregistro"):
        title = f"visit-{record.get('idregistro')}"
    else:
        title = "visit"

    address = record.get("endereco_geolocalizacao") or record.get("endereco") or ""

    payload: Dict[str, Any] = {
        "title": title,
        "address": address,
        # properties pode ajudar a mapear origem do dado no SimpliRoute
        "properties": {"source": "gnexum", "source_ident": str(record.get("idregistro", ""))},
    }

    # planned_date if present (preferred) or from eventdate
    pd = record.get("planned_date") or record.get("eventdate")
    try:
        if isinstance(pd, (datetime, date)):
            payload["planned_date"] = pd.strftime("%Y-%m-%d")
        elif isinstance(pd, str) and pd:
            payload["planned_date"] = pd.split("T")[0]
    except Exception:
        pass

    # loads and duration
    payload["load"] = float(record.get("load") or record.get("volume") or 0.0)
    payload["load_2"] = float(record.get("load_2") or 0.0)
    payload["load_3"] = float(record.get("load_3") or 0.0)

    # Duration (service time) in HH:MM:SS when provided or fallback
    duration = record.get("duration")
    if duration is None:
        # allow 'service_time' or default 0
        duration = record.get("service_time") or 0
    payload["duration"] = _minutes_to_hhmmss(duration)

    # Items: converter para o formato esperado pela API de visits.items
    rows = record.get("items") or []
    items = []
    for r in rows:
        items.append({
            "title": r.get("title") or r.get("nome") or "item",
            "load": float(r.get("load") or 0.0),
            "load_2": float(r.get("load_2") or 0.0),
            "load_3": float(r.get("load_3") or 0.0),
            "reference": r.get("reference") or r.get("ref") or "",
            "quantity_planned": float(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 0.0),
            "notes": r.get("notes", ""),
        })
    payload["items"] = items

    return payload


def build_items_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for r in rows:
        items.append({
            "title": r.get("nome", "item"),
            "quantity_planned": float(r.get("quantidade", 1) or 1),
        })
    return items
