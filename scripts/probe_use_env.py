import json
import sys
from urllib import request, error

def load_env(path='settings/.env'):
    env = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return env

env = load_env()
url = env.get('GNEXUM_API_URL')
token = env.get('GNEXUM_TOKEN')

if not url or not token:
    print('GNEXUM_API_URL or GNEXUM_TOKEN missing in settings/.env', file=sys.stderr)
    sys.exit(2)

full_url = url + '?disablePagination=false&page=1&limit=10'
data = json.dumps({'params': []}).encode('utf-8')
req = request.Request(full_url, data=data, method='POST')
req.add_header('Content-Type', 'application/json')
req.add_header('Authorization', 'Bearer ' + token)

try:
    with request.urlopen(req, timeout=15) as resp:
        print('STATUS', resp.getcode())
        print(resp.read().decode('utf-8'))
except error.HTTPError as e:
    try:
        body = e.read().decode('utf-8')
    except Exception:
        body = '<no body>'
    print('STATUS', e.code)
    print(body)
except Exception as e:
    print('ERROR', e)
