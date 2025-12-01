import os
import json
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), 'settings', '.env'))

url = os.getenv('GNEXUM_API_URL')
token = os.getenv('GNEXUM_TOKEN')

if not url or not token:
    print('GNEXUM_API_URL or GNEXUM_TOKEN missing')
    raise SystemExit(2)

async def main(record_id=123):
    headers = {'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'}
    bodies = [{'idregistro': record_id}, {'record_id': record_id}, {'id': record_id}]
    async with httpx.AsyncClient(timeout=15.0) as c:
        for b in bodies:
            try:
                print('POST', url, 'body=', b)
                r = await c.post(url, json=b, headers=headers)
            except Exception as e:
                print('request failed', e)
                continue
            print('STATUS', r.status_code)
            try:
                print('BODY', json.dumps(r.json(), ensure_ascii=False)[:1000])
            except Exception:
                print('BODY_RAW', r.text[:1000])

if __name__ == '__main__':
    asyncio.run(main(123))
