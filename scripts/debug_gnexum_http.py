import os
import json
"""
Removido: utilitário de debug HTTP para Gnexum.
Mantido como placeholder; recupere do histórico se necessário.
"""

def main():
    print('debug_gnexum_http.py: removido — utilitário não essencial')

if __name__ == '__main__':
    main()
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
