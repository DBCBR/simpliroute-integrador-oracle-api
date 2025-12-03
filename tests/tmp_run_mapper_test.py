from src.integrations.simpliroute.mapper import build_visit_payload
import json
from pathlib import Path
f=sorted((Path('data') / 'output').glob('visits_db_all_dryrun_*.json'), key=lambda p:p.stat().st_mtime, reverse=True)[0]
with f.open('r', encoding='utf-8') as fh:
    d=json.load(fh)
v=build_visit_payload(d[0])
print(json.dumps(v, ensure_ascii=False, indent=2))
