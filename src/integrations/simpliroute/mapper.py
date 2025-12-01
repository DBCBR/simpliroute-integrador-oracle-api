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
    # suportar chaves vindas do Gnexum que podem estar em CAIXA ALTA
    def _get(k, *alts, default=None):
        for key in (k,) + alts:
            if key in record and record.get(key) is not None:
                return record.get(key)
        return default

    tp = int(_get("tpregistro", "TPREGISTRO", default=1) or 1)

    # Title: prefer explicit title, else patient name, else idregistro/ID_ATENDIMENTO, else fallback
    if _get("title"):
        title = str(_get("title"))
    elif _get("NOME_PACIENTE", "nome_paciente"):
        title = f"visit-{_get('NOME_PACIENTE', 'nome_paciente')}"
    elif _get("idregistro") or _get("ID_ATENDIMENTO"):
        title = f"visit-{_get('idregistro') or _get('ID_ATENDIMENTO')}"
    else:
        title = "visit"

    address = _get("endereco_geolocalizacao") or _get("ENDERECO") or _get("endereco") or ""

    payload: Dict[str, Any] = {
        "title": title,
        "address": address,
        # properties pode ajudar a mapear origem do dado no SimpliRoute
        "properties": {"source": "gnexum", "source_ident": str(record.get("idregistro", ""))},
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

    # Items: converter para o formato esperado pela API de visits.items
    rows = record.get("items") or record.get("rows") or record.get("ITEMS") or record.get("items") or []
    items = []
    for r in rows:
        # suportar campos vindos do Gnexum
        item_title = r.get("title") or r.get("nome") or r.get("ESPECIALIDADE") or r.get("TIPOVISITA") or "item"
        items.append({
            "title": item_title,
            "load": float(r.get("load") or 0.0),
            "load_2": float(r.get("load_2") or 0.0),
            "load_3": float(r.get("load_3") or 0.0),
            "reference": r.get("reference") or r.get("ref") or r.get("ID_ATENDIMENTO") or r.get("ID") or "",
            "quantity_planned": float(r.get("quantity_planned") or r.get("qty") or r.get("quantidade") or 1.0),
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
