import os
import json
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# load env
load_dotenv(os.path.join('settings', '.env'), override=False)

# ensure dry-run
os.environ['SIMPLIROUTE_DRY_RUN'] = os.environ.get('SIMPLIROUTE_DRY_RUN', '1')

from src.integrations.simpliroute.token_manager import login_and_store, get_token
from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.mapper import build_visit_payload
from src.integrations.simpliroute.client import post_simpliroute

OUTPUT_DIR = os.path.join('data', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    # ensure token
    tok = await get_token()
    if not tok:
        print('No token present, attempting login...')
        tok = await login_and_store()
    print('Using GNEXUM token present:', bool(tok))

    # One-shot fetch: try several strategies to retrieve records
    print('Fetching items from Gnexum...')
    # we will attempt to fetch by a sample id and also a generic call
    items = []
    try:
        # attempt normalized fetch for a sample record (123)
        items = await fetch_items_for_record(123, normalize=True)
    except Exception as e:
        print('fetch_items_for_record(123) error:', e)
    if not items:
        try:
            # try fetch with record_id as string
            items = await fetch_items_for_record('123', normalize=True)
        except Exception as e:
            print('fetch_items_for_record("123") error:', e)

    print(f'Fetched {len(items)} items')

    visits = []
    for it in items:
        visit = build_visit_payload(it)
        visits.append(visit)
        # call post_simpliroute (dry-run should print preview)
        resp = await post_simpliroute(visit)
        status = getattr(resp, 'status_code', None)
        print('post_simpliroute returned status:', status)

    # save visits to file for inspection
    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_file = os.path.join(OUTPUT_DIR, f'visits_dryrun_{ts}.json')
    try:
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(visits, f, ensure_ascii=False, indent=2)
        print('Saved visits to', out_file)
    except Exception as e:
        print('Failed to save visits:', e)

if __name__ == '__main__':
    asyncio.run(main())
