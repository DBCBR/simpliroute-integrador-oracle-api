import os
import sys
import argparse
import asyncio
import json
from datetime import datetime

sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv(os.path.join('settings', '.env'), override=False)

parser = argparse.ArgumentParser()
parser.add_argument('--view', help='ORACLE view to read (overrides ORACLE_VIEW env)', default=None)
args = parser.parse_args()

if args.view:
    os.environ['ORACLE_VIEW'] = args.view

os.environ['USE_GNEXUM_DB'] = os.environ.get('USE_GNEXUM_DB', '1')
os.environ['SIMPLIROUTE_DRY_RUN'] = os.environ.get('SIMPLIROUTE_DRY_RUN', '1')

from src.integrations.simpliroute.gnexum_db import fetch_items_for_record_db
from src.integrations.simpliroute.mapper import build_visit_payload

OUTPUT_DIR = os.path.join('data', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def main():
    print('Using DB fetch, reading first rows from view...')
    items = await fetch_items_for_record_db(None, limit=20)
    print('Fetched', len(items), 'rows from DB')
    visits = []
    for it in items[:10]:
        try:
            v = build_visit_payload(it)
            visits.append(v)
        except Exception as e:
            print('Mapper error for item:', e)

    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_file = os.path.join(OUTPUT_DIR, f'visits_db_dryrun_{ts}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(visits, f, ensure_ascii=False, indent=2)
    print('Saved', len(visits), 'visits to', out_file)


if __name__ == '__main__':
    asyncio.run(main())
