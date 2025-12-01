import json
import sys
from urllib import request, error

def post_json(url, payload, headers=None, timeout=15):
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode('utf-8')
            return resp.getcode(), dict(resp.getheaders()), body
    except error.HTTPError as e:
        try:
            body = e.read().decode('utf-8')
        except Exception:
            body = '<no body>'
        return e.code, dict(e.headers), body
    except Exception as e:
        return None, {}, f'ERROR: {e}'


def try_login_and_call():
    login_url = 'http://10.1.1.55:3792/api/auth/login-api'
    events_url = 'http://10.1.1.55:3792/api/solarcuidados/v1/Gbuscartabelaeventos?disablePagination=false&page=1&limit=10'

    creds = {
        "username": "david.barcellos@solarcuidados.com.br",
        "password": "Dbcbr412294d@"
    }

    print('POST', login_url)
    status, headers, body = post_json(login_url, creds)
    print('Login -> status:', status)
    print('Login headers:', headers)
    print('Login body:', body)

    token = None
    try:
        j = json.loads(body)
        # try common fields
        if isinstance(j, dict):
            token = j.get('access_token') or j.get('token') or j.get('data', {}).get('access_token') if j.get('data') else None
            # try to find any field that looks like a JWT
            if not token:
                for v in j.values():
                    if isinstance(v, str) and v.count('.') >= 2 and len(v) > 100:
                        token = v
                        break
    except Exception:
        pass

    if not token:
        print('No token extracted from login response. Aborting events call.')
        return

    print('Extracted token (head...tail):', token[:8] + '...' + token[-8:])

    headers = {'Authorization': 'Bearer ' + token}
    print('\nPOST', events_url)
    status, headers_resp, body_resp = post_json(events_url, {'params': []}, headers=headers)
    print('Events -> status:', status)
    print('Events headers:', headers_resp)
    print('Events body:', body_resp)


if __name__ == '__main__':
    try:
        try_login_and_call()
    except Exception as e:
        print('ERROR', e)
        sys.exit(2)
