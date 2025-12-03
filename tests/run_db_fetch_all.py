import os
import sys
import asyncio
import json
from datetime import datetime

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(os.path.join('settings', '.env'), override=False)

os.environ['USE_GNEXUM_DB'] = os.environ.get('USE_GNEXUM_DB', '1')
os.environ['SIMPLIROUTE_DRY_RUN'] = os.environ.get('SIMPLIROUTE_DRY_RUN', '1')

from src.integrations.simpliroute.gnexum_db import fetch_items_for_record_db
from src.integrations.simpliroute.mapper import build_visit_payload

OUTPUT_DIR = os.path.join('data', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def main(page_size: int = 50, max_pages: int = 100):
    print('Starting DB full fetch (dry-run). page_size=', page_size)
    offset = 0
    all_visits = []
    page = 0
    while page < max_pages:
        print(f'Fetching offset={offset} limit={page_size} (page {page+1})')
        rows = await fetch_items_for_record_db(None, limit=page_size, offset=offset)
        print('  got', len(rows), 'rows')
        if not rows:
            break
        for r in rows:
            try:
                v = build_visit_payload(r)
                all_visits.append(v)
            except Exception as e:
                print('  mapper error:', e)
        if len(rows) < page_size:
            break
        offset += page_size
        page += 1

    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_file = os.path.join(OUTPUT_DIR, f'visits_db_all_dryrun_{ts}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_visits, f, ensure_ascii=False, indent=2)

    print('Saved', len(all_visits), 'visits to', out_file)


if __name__ == '__main__':
    asyncio.run(main(page_size=50, max_pages=20))
