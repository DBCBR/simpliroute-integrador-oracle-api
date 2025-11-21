from typing import Any, Dict, List


def build_visit_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Constrói payload mínimo para criação de visita no SimpliRoute.

    Exemplo mínimo com mapeamento do PDD: title, address, planned_date (quando aplicável).
    """
    tp = int(record.get("tpregistro", 1))
    title = f"{record.get('idadmission','')}-{record.get('idregistro','')}"
    payload: Dict[str, Any] = {
        "title": title,
        "address": record.get("endereco_geolocalizacao") or record.get("endereco") or "",
        "metadata": {"idregistro": record.get("idregistro")},
    }
    if tp == 2:
        # Entrega - usar planned_date field
        payload["planned_date"] = record.get("eventdate")
        payload["load"] = record.get("volume", 0)
    else:
        # Visita
        payload["duration"] = record.get("duration", 30)

    # items: placeholder, deve ser preenchido consultando TD_OTIMIZE_ITENS
    payload["items"] = record.get("items", [])

    return payload


def build_items_from_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items = []
    for r in rows:
        items.append({
            "name": r.get("nome", "item"),
            "qty": r.get("quantidade", 1),
        })
    return items
