import os
import sys
import asyncio
import json

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv('settings/.env', override=False)

# Force view to entregas
os.environ['ORACLE_VIEW'] = os.environ.get('ORACLE_VIEW', 'VWPACIENTES_ENTREGAS')

from src.integrations.simpliroute.gnexum_db import fetch_items_for_record_db

async def main(limit=10):
    print('Inspecting view:', os.environ.get('ORACLE_VIEW'))
    rows = await fetch_items_for_record_db(None, limit=limit, offset=0)
    print('Fetched', len(rows), 'rows')
    if not rows:
        return
    # collect all keys
    all_keys = set()
    for r in rows:
        all_keys.update(r.keys())
    all_keys = sorted(all_keys)
    print('\nColumns found ({}):\n'.format(len(all_keys)))
    for k in all_keys:
        print(' -', k)

    # show sample values for first 5 rows
    print('\nSample rows (first {}):\n'.format(min(5, len(rows))))
    for i, r in enumerate(rows[:5]):
        print(f'Row {i+1}:')
        # show only keys with non-empty values for readability
        sample = {k: v for k, v in r.items() if v not in (None, '', [])}
        print(json.dumps(sample, ensure_ascii=False, indent=2))
        print('---')

    # quick summary: count non-null per column across fetched rows
    counts = {k: 0 for k in all_keys}
    for r in rows:
        for k in all_keys:
            v = r.get(k)
            if v not in (None, '', []):
                counts[k] += 1
    print('\nNon-empty counts (column: count of non-empty in sampled rows):')
    for k in sorted(all_keys, key=lambda x: -counts[x]):
        print(f' - {k}: {counts[k]}')

if __name__ == '__main__':
    asyncio.run(main(limit=20))
