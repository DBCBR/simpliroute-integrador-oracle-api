import os
import sys
import json
import asyncio
from pathlib import Path

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv('settings/.env', override=False)

from src.integrations.simpliroute.client import post_simpliroute

# Find latest entregas dryrun file
out_dir = Path('data') / 'output'
files = sorted(out_dir.glob('visits_db_all_vwpacientes_entregas_dryrun_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    print('Nenhum arquivo de entregas dry-run encontrado em data/output')
    raise SystemExit(1)

file = files[0]
print('Using file:', file)
with file.open('r', encoding='utf-8') as fh:
    data = json.load(fh)

if not data:
    print('Arquivo vazio')
    raise SystemExit(1)

# pick first entrega
entrega = data[0]
print('\n--- Payload a enviar (resumido) ---')
print(json.dumps({k: entrega.get(k) for k in ['title','address','reference','tracking_id','planned_date','visit_type','items']}, ensure_ascii=False, indent=2))
print('--- end preview ---\n')

# ensure canonical base and force real send
os.environ['SIMPLIROUTE_API_BASE'] = 'https://api.simpliroute.com'
os.environ['SIMPLIROUTE_DRY_RUN'] = '0'

async def _send_one():
    resp = await post_simpliroute(entrega)
    if resp is None:
        print('Request failed (None)')
        return
    status = getattr(resp, 'status_code', None)
    text = getattr(resp, 'text', None)
    print('Response status:', status)
    try:
        body = resp.json()
        print(json.dumps(body, ensure_ascii=False, indent=2))
    except Exception:
        print(text)

if __name__ == '__main__':
    asyncio.run(_send_one())
