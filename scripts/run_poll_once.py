import sys
import asyncio
import os

sys.path.insert(0, os.path.abspath('src'))

from integrations.simpliroute.gnexum import fetch_items_for_record
from integrations.simpliroute.mapper import build_visit_payload


async def fake_post_simpliroute(route_payload):
    print('[DRY-RUN] Would POST to SimpliRoute with payload sample keys:', list(route_payload.keys()))
    return type('R', (), {'status_code': 200, 'text': '{"simulated": true}'})


async def main(record_id=123):
    print('Fetching items for record', record_id)
    items = await fetch_items_for_record(record_id, normalize=False)
    print('Got items count:', len(items))
    sample = {'tpregistro': 2, 'idregistro': record_id, 'endereco': None}
    sample['items'] = items
    payload = build_visit_payload(sample)
    print('Built payload keys:', list(payload.keys()))
    resp = await fake_post_simpliroute(payload)
    print('Simulated post status:', getattr(resp, 'status_code', None))


if __name__ == '__main__':
    asyncio.run(main(123))
