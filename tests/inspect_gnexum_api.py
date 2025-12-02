import os
import sys
import asyncio
import json
from dotenv import load_dotenv

sys.path.insert(0, os.getcwd())
load_dotenv(os.path.join('settings', '.env'), override=False)

from src.integrations.simpliroute.token_manager import get_token
import httpx


COMMON_QUERIES = [
    '',
    '?page=1&per_page=50',
    '?page=1&per_page=100',
    '?limit=100',
    '?offset=0&limit=100',
    '?start=0&length=100',
    '?tab=1',
    '?aba=1',
    '?status=all',
]


async def inspect():
    GNEXUM_URL = os.getenv('GNEXUM_API_URL')
    if not GNEXUM_URL:
        print('GNEXUM_API_URL não configurado no env (settings/.env).')
        return

    tok = await get_token()
    headers = {'Accept': 'application/json'}
    if tok:
        headers['Authorization'] = f'Bearer {tok}'

    async with httpx.AsyncClient(timeout=15) as client:
        for q in COMMON_QUERIES:
            url = GNEXUM_URL.rstrip('/') + q
            print('\n=== QUERY:', q or '(sem query)')
            print('URL:', url)
            try:
                r = await client.get(url, headers=headers)
            except Exception as e:
                print('Request failed:', e)
                continue

            print('Status:', r.status_code)
            # print some headers that often hold pagination info
            for h in ('X-Total-Count', 'X-Page', 'X-Per-Page', 'Link'):
                if h in r.headers:
                    print(f'Header {h}:', r.headers.get(h))

            # try parse as json
            try:
                data = r.json()
            except Exception:
                txt = r.text
                print('Non-JSON response sample:', txt[:400].replace('\n',' '))
                continue

            # show top-level keys and types
            if isinstance(data, dict):
                print('Top-level keys:', list(data.keys()))
                # common pagination keys
                for k in ('total', 'count', 'meta', 'pagination', 'records_total'):
                    if k in data:
                        print(f'Found key {k}:', type(data.get(k)), data.get(k))

                # try to find rows container
                rows = None
                for candidate in ('items', 'rows', 'data', 'records', 'results'):
                    if candidate in data and isinstance(data[candidate], (list, dict)):
                        rows = data[candidate]
                        print('Rows found in key:', candidate, 'len:', len(rows) if hasattr(rows, '__len__') else 'unknown')
                        break

                if rows is None:
                    # if dict with numeric keys or list-like
                    if isinstance(data, list):
                        rows = data
                    else:
                        # try nested structures
                        for v in data.values():
                            if isinstance(v, list):
                                rows = v
                                print('Inferred rows from a nested list, len:', len(rows))
                                break

                if isinstance(rows, list):
                    print('Sample item keys (first 3):')
                    for i, it in enumerate(rows[:3]):
                        if isinstance(it, dict):
                            print('  item', i, 'keys:', list(it.keys()))
                        else:
                            print('  item', i, 'type:', type(it), 'value-sample:', str(it)[:100])
                    print('Returned count:', len(rows))
                else:
                    print('Rows not a list (type):', type(rows))

            elif isinstance(data, list):
                print('Response is a list, len:', len(data))
                print('Sample item keys (first 3):')
                for i, it in enumerate(data[:3]):
                    if isinstance(it, dict):
                        print('  item', i, 'keys:', list(it.keys()))
                    else:
                        print('  item', i, 'type:', type(it))

            else:
                print('Response type:', type(data))


if __name__ == '__main__':
    asyncio.run(inspect())
