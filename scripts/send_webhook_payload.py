import json
from datetime import datetime
from urllib import request, error

payload = {
    "id": 747461901,
    "reference": "4007560",
    "status": "completed",
    "visit_type": "acr_log",
    "title": "Natalia Nunes Abreu",
    "address": "Rua Gavião Peixoto, 332 - Icaraí, Niteroi - RJ, 24230090",
    "eventdate": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "checkout_time": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    "checkout_comment": "Teste manual via webhook",
    "latitude": "-22.907110",
    "longitude": "-43.106840",
    "contact_name": "Maria Elisa",
    "contact_phone": "+5521997657695",
    "planned_date": "2025-12-10",
    "properties": {"record_type": "entrega"},
}

body = json.dumps(payload).encode("utf-8")
req = request.Request(
    "http://localhost:8000/webhook/simpliroute",
    data=body,
    headers={"Content-Type": "application/json"},
)

try:
    with request.urlopen(req) as resp:
        print(resp.status, resp.read().decode())
except error.HTTPError as exc:
    print(exc.code, exc.read().decode())
    raise
