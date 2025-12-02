import sys, os, json, asyncio, random, glob
sys.path.insert(0, os.getcwd())
from datetime import datetime
from dotenv import load_dotenv

# load env
load_dotenv(os.path.join('settings', '.env'), override=False)
# ensure dry-run
os.environ['SIMPLIROUTE_DRY_RUN'] = os.environ.get('SIMPLIROUTE_DRY_RUN', '1')

from src.integrations.simpliroute.token_manager import get_token
from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.mapper import build_visit_payload
from src.integrations.simpliroute.client import post_simpliroute

OUTPUT_DIR = os.path.join('data', 'output')
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def main():
    tok = await get_token()
    if not tok:
        print('No token, attempting login...')
        from src.integrations.simpliroute.token_manager import login_and_store
        await login_and_store()
        tok = await get_token()

    print('Using GNEXUM token present:', bool(tok))

    # load latest saved references
    prev_refs = set()
    files = sorted(glob.glob(os.path.join(OUTPUT_DIR, 'visits_dryrun_*.json')))
    if files:
        latest = files[-1]
        try:
            with open(latest, 'r', encoding='utf-8') as f:
                arr = json.load(f)
                for v in arr:
                    if isinstance(v, dict):
                        r = v.get('reference') or v.get('reference', '')
                        if r:
                            prev_refs.add(str(r))
            print('Loaded', len(prev_refs), 'previous references from', os.path.basename(latest))
        except Exception as e:
            print('Failed to read previous file:', e)

    found_items = []
    attempts = 0
    tried_ids = set()
    # try up to 100 random record ids within a wider observed range
    while attempts < 100 and len(found_items) < 2:
        rid = random.randint(12000, 40000)
        if rid in tried_ids:
            attempts += 1
            continue
        tried_ids.add(rid)
        attempts += 1
        print('Attempt', attempts, 'fetching record_id', rid)
        try:
            items = await fetch_items_for_record(rid, normalize=True)
        except Exception as e:
            print('fetch error for', rid, e)
            continue
        print('  fetched', len(items), 'items (sample refs:', [str(it.get('ID_ATENDIMENTO') or it.get('reference') or '') for it in items[:3]])
        for it in items:
            ref = str(it.get('ID_ATENDIMENTO') or it.get('reference') or it.get('ID') or it.get('id') or '')
            if ref and ref not in prev_refs:
                found_items.append(it)
        if found_items:
            break

    if not found_items:
        print('No new items found after', attempts, 'attempts. Try increasing range or attempts.')
        return

    visits = []
    for it in found_items:
        visit = build_visit_payload(it)
        visits.append(visit)
        resp = await post_simpliroute(visit)
        print('post_simpliroute returned status:', getattr(resp, 'status_code', None))

    ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
    out_file = os.path.join(OUTPUT_DIR, f'visits_dryrun_newdata_{ts}.json')
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(visits, f, ensure_ascii=False, indent=2)
    print('Saved', len(visits), 'visits to', out_file)

if __name__ == '__main__':
    asyncio.run(main())
