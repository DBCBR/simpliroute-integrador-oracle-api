import sys
import asyncio
sys.path.insert(0, 'src')

from integrations.simpliroute.gnexum import fetch_items_for_record

async def main():
    items = await fetch_items_for_record(123, normalize=False)
    print('returned items count:', len(items))
    if items:
        print('sample item keys:', list(items[0].keys()))

if __name__ == '__main__':
    asyncio.run(main())
