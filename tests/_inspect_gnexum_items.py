import sys, os, json, asyncio
sys.path.insert(0, os.getcwd())
from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.token_manager import get_token

async def main():
    tok = await get_token()
    print('token present:', bool(tok))
    items = await fetch_items_for_record(123, normalize=True)
    print('items count:', len(items))
    if items:
        import pprint
        pprint.pprint(items[0])
        # print all keys seen across first 5
        keys = set()
        for it in items[:5]:
            if isinstance(it, dict):
                keys.update(it.keys())
        print('\nkeys sample:', sorted(list(keys)))

if __name__ == '__main__':
    asyncio.run(main())
