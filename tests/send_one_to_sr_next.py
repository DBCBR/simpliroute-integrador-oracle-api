from dotenv import load_dotenv
import os
import json
import asyncio
from pathlib import Path

from src.integrations.simpliroute.client import post_simpliroute
from src.integrations.simpliroute.mapper import build_visit_payload

# Carrega variáveis de settings/.env
load_dotenv(os.path.join('settings', '.env'), override=False)

# Localiza o arquivo dry-run mais recente
out_dir = Path('data') / 'output'
files = sorted(out_dir.glob('visits_db_all_dryrun_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
if not files:
    print('Nenhum arquivo dry-run encontrado em data/output')
    raise SystemExit(1)

file = files[0]
print('Using file:', file)

with file.open('r', encoding='utf-8') as fh:
    data = json.load(fh)

if not data:
    print('Arquivo vazio')
    raise SystemExit(1)

# Avoid sending the record already sent via Postman (reference 35215)
skip_reference = os.getenv('SKIP_REFERENCE', '35215')
visit = None
for v in data:
    ref = v.get('reference') or ''
    if str(ref) != str(skip_reference):
        # map the raw record to the SimpliRoute visit payload
        visit = build_visit_payload(v)
        break

if not visit:
    print('Não encontrei um registro diferente de', skip_reference)
    raise SystemExit(1)

print('\n--- Payload a enviar (preview) ---')
print(json.dumps(visit, ensure_ascii=False, indent=2))
print('--- end preview ---\n')

# Forçar URL canônica do SimpliRoute para evitar duplicação
os.environ['SIMPLIROUTE_API_BASE'] = 'https://api.simpliroute.com'
# Garantir que vamos realmente enviar
os.environ['SIMPLIROUTE_DRY_RUN'] = '0'

async def _send_one():
    resp = await post_simpliroute(visit)
    if resp is None:
        print('Request failed (None)')
        return
    status = getattr(resp, 'status_code', None)
    text = getattr(resp, 'text', None)
    try:
        body = resp.json() if hasattr(resp, 'json') else text
    except Exception:
        body = text
    print(f'Response status: {status}')
    print('Response body:')
    if isinstance(body, (dict, list)):
        print(json.dumps(body, ensure_ascii=False, indent=2))
    else:
        print(body)

if __name__ == '__main__':
    asyncio.run(_send_one())
