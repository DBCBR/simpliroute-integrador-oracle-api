import os
import json
from dotenv import load_dotenv
import httpx

# Carrega settings/.env
load_dotenv(os.path.join('settings', '.env'), override=False)

url = os.getenv('GNEXUM_API_URL')
if not url:
    print('GNEXUM_API_URL not set in settings/.env')
    raise SystemExit(1)

token = os.getenv('GNEXUM_TOKEN')
headers = {'Content-Type': 'application/json'}
if token:
    headers['Authorization'] = f'Bearer {token}'

# Payload de exemplo: tente com idregistro=123 (ajuste conforme necessário)
payload = {'idregistro': 123}

print('POST', url)
print('Headers:', {k: (v[:8] + '...' if k.lower().find('authorization')!=-1 else v) for k,v in headers.items()})
print('Payload:', json.dumps(payload, ensure_ascii=False))

try:
    with httpx.Client(timeout=30.0) as client:
        r = client.post(url, json=payload, headers=headers)
    print('status_code:', r.status_code)
    text = r.text
    if len(text) > 8000:
        print('body (truncated 8000):')
        print(text[:8000])
    else:
        print('body:')
        print(text)
except Exception as e:
    print('error:', e)
    raise
