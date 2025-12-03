import sys, os, json, asyncio, pprint
sys.path.insert(0, os.getcwd())
from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.token_manager import get_token
from src.integrations.simpliroute.mapper import build_visit_payload

async def main():
    tok = await get_token()
    print('token present:', bool(tok))
    items = await fetch_items_for_record(123, normalize=True)
    print('items count:', len(items))
    if not items:
        return
    first = items[0]
    pprint.pprint(first)
    visit = build_visit_payload(first)
    print('\n=> mapped visit:')
    pprint.pprint(visit)

if __name__ == '__main__':
    asyncio.run(main())
