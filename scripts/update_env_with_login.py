import json
from urllib import request, error
import re

login_url = 'http://10.1.1.55:3792/api/auth/login-api'
creds = {"username": "david.barcellos@solarcuidados.com.br",
         "password": "Dbcbr412294d@"}

def post(url, payload):
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, method='POST')
    req.add_header('Content-Type','application/json')
    with request.urlopen(req, timeout=15) as resp:
        return resp.read().decode('utf-8')

print('Logging in...')
body = post(login_url, creds)
j = json.loads(body)
access = j.get('access_token')
refresh = j.get('refresh_token')
expires_in = j.get('expires_in')
if not access:
    print('Login did not return access_token; aborting')
    raise SystemExit(2)

print('Got access token, updating settings/.env')

env_path = 'settings/.env'
with open(env_path, 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

out = []
re_token = re.compile(r'^GNEXUM_TOKEN=')
re_refresh = re.compile(r'^GNEXUM_REFRESH_TOKEN=')
found_token = False
found_refresh = False
for ln in lines:
    if re_token.match(ln):
        out.append('GNEXUM_TOKEN=' + access)
        found_token = True
    elif re_refresh.match(ln):
        out.append('GNEXUM_REFRESH_TOKEN=' + refresh)
        found_refresh = True
    else:
        out.append(ln)

if not found_token:
    out.append('GNEXUM_TOKEN=' + access)
if not found_refresh and refresh:
    out.append('GNEXUM_REFRESH_TOKEN=' + refresh)
if expires_in:
    out.append('GNEXUM_EXPIRES_IN=' + str(expires_in))

with open(env_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(out) + '\n')

print('settings/.env updated')
