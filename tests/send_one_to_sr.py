from dotenv import load_dotenv
import os
import json
import asyncio
from pathlib import Path

from src.integrations.simpliroute.client import post_simpliroute

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

# Seleciona o primeiro visit para envio
visit = data[0]

print('\n--- Payload a enviar (preview) ---')
print(json.dumps(visit, ensure_ascii=False, indent=2))
print('--- end preview ---\n')

# Garantir envio único: desabilitar dry-run para esta execução
os.environ['SIMPLIROUTE_DRY_RUN'] = '0'

async def _send_one():
    resp = await post_simpliroute(visit)
    if resp is None:
        print('Request failed (None)')
        return
    # httpx.Response or FakeResp
    status = getattr(resp, 'status_code', None)
    text = getattr(resp, 'text', None)
    try:
        body = resp.json() if hasattr(resp, 'json') else text
    except Exception:
        body = text
    print(f'Response status: {status}')
    print('Response body:')
    print(json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, (dict, list)) else body)

if __name__ == '__main__':
    asyncio.run(_send_one())
