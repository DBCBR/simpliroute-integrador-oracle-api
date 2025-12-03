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
parser.add_argument('--page-size', type=int, default=50)
parser.add_argument('--max-pages', type=int, default=100)
args = parser.parse_args()

if args.view:
    os.environ['ORACLE_VIEW'] = args.view

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
        # If rows contain item-level columns (ITEM_ID/ITEM_TITLE), group by ID_ATENDIMENTO
        if rows and any('ITEM_ID' == k or k.upper().startswith('ITEM_') for k in rows[0].keys()):
            groups = {}
            for r in rows:
                rid = r.get('ID_ATENDIMENTO') or r.get('REFERENCE') or r.get('idregistro') or r.get('id')
                if rid is None:
                    # fallback: use TITLE as grouping key when id absent
                    rid = r.get('TITLE') or r.get('REFERENCE')
                key = str(rid)
                if key not in groups:
                    groups[key] = {'base': {}, 'items': []}
                    # copy base attributes from first row
                    groups[key]['base'] = dict(r)
                # build item from row
                item = {
                    'title': r.get('ITEM_TITLE') or r.get('ITEM') or r.get('PRODUTO') or r.get('NOME'),
                    'reference': r.get('ITEM_REFERENCE') or r.get('ITEM_REF') or r.get('ITEM_REFERENCE') or r.get('ITEM_REFERENCE'),
                    'quantity_planned': float(r.get('QUANTITY_PLANNED') or r.get('QUANTITY') or r.get('QUANTIDADE') or 1.0),
                    'load': float(r.get('LOAD') or 0.0),
                }
                groups[key]['items'].append(item)

            # build combined records
            for g in groups.values():
                rec = dict(g['base'])
                rec['items'] = g['items']
                try:
                    v = build_visit_payload(rec)
                    all_visits.append(v)
                except Exception as e:
                    print('  mapper error:', e)
        else:
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
    view_label = os.environ.get('ORACLE_VIEW', 'unknown').lower()
    out_file = os.path.join(OUTPUT_DIR, f'visits_db_all_{view_label}_dryrun_{ts}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(all_visits, f, ensure_ascii=False, indent=2)

    print('Saved', len(all_visits), 'visits to', out_file)


if __name__ == '__main__':
    asyncio.run(main(page_size=args.page_size, max_pages=args.max_pages))
