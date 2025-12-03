from dotenv import load_dotenv
import os
import json
from pathlib import Path

# load env
load_dotenv(os.path.join('settings', '.env'), override=False)

out_dir = Path('data') / 'output'
files = sorted(out_dir.glob('visits_db_all_dryrun_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    print('Nenhum arquivo dry-run encontrado em data/output')
    raise SystemExit(1)

file = files[0]
print('Using file:', file)

data = json.loads(file.read_text(encoding='utf-8'))
if not data:
    print('Arquivo vazio')
    raise SystemExit(1)

visit = data[0]

# Allowed fields copied from src/integrations/simpliroute/client.py
allowed_visit_fields = [
    "order","tracking_id","status","title","address","latitude","longitude",
    "load","load_2","load_3","window_start","window_end","window_start_2","window_end_2",
    "duration","contact_name","contact_phone","contact_email","reference","notes",
    "skills_required","skills_optional","tags","planned_date","programmed_date","route",
    "estimated_time_arrival","estimated_time_departure","checkin_time","checkout_time",
    "checkout_latitude","checkout_longitude","checkout_comment","checkout_observation",
    "signature","pictures","created","modified","eta_predicted","eta_current",
    "priority","has_alert","priority_level","extra_field_values","geocode_alert",
    "visit_type","current_eta","fleet","seller","properties","items","on_its_way"
]

allowed_item_fields = [
    "id","title","status","load","load_2","load_3","reference","visit",
    "notes","quantity_planned","quantity_delivered"
]


def prune_visit(v: dict) -> dict:
    out = {}
    for k in allowed_visit_fields:
        if k in v and v[k] is not None:
            out[k] = v[k]
    # properties handling: keep specific keys
    if "properties" in out and isinstance(out["properties"], dict):
        props = out["properties"]
        kept = {k: props[k] for k in props if k in ("PROFISSIONAL", "ESPECIALIDADE", "PERIODICIDADE", "TIPOVISITA")}
        if kept:
            out["properties"] = kept
        else:
            out.pop("properties", None)
    # prune items
    if "items" in out and isinstance(out["items"], list):
        items = []
        for it in out["items"]:
            if not isinstance(it, dict):
                continue
            newi = {k: it[k] for k in allowed_item_fields if k in it and it[k] is not None}
            if newi:
                items.append(newi)
        if items:
            out["items"] = items
        else:
            out.pop("items", None)
    return out

pruned = prune_visit(visit)

# Build final body as list (API expects list)
body = [pruned]

# Read token from env (support multiple names)
def get_token():
    for n in ("SIMPLIROUTE_TOKEN", "SIMPLIR_ROUTE_TOKEN", "SIMPLIROUTE_API_TOKEN"):
        t = os.getenv(n)
        if t:
            return t
    return None

token = get_token()

base = os.getenv("SIMPLIROUTE_API_BASE") or os.getenv("SIMPLIR_ROUTE_BASE_URL") or os.getenv("SIMPLIROUTE_API_BASE_URL") or "https://api.simpliroute.com"

print('\n--- Headers ---')
print('Content-Type: application/json; charset=utf-8')
if token:
    print(f'Authorization: Token {token}')
else:
    print('Authorization: Token <MISSING - set SIMPLIR_ROUTE_TOKEN or SIMPLIROUTE_TOKEN in settings/.env>')

print(f'POST URL: {base.rstrip("/")}/v1/routes/visits/')

print('\n--- JSON body (copiar e colar no Postman, raw application/json) ---')
print(json.dumps(body, ensure_ascii=False, indent=2))

print('\n--- cURL exemplo ---')
if token:
    print(f"curl -X POST '{base.rstrip('/')}/v1/routes/visits/' -H 'Content-Type: application/json' -H 'Authorization: Token {token}' -d '{json.dumps(body, ensure_ascii=False)}'")
else:
    print('# Token não encontrado; insira Authorization manualmente')
    print(f"curl -X POST '{base.rstrip('/')}/v1/routes/visits/' -H 'Content-Type: application/json' -d '{json.dumps(body, ensure_ascii=False)}'")
