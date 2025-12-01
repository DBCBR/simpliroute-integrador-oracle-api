"""Runner in-process: busca registros reais no Gnexum, monta payloads
e simula a escrita ao SimpliRoute (não envia nada).

Funcionalidades adicionadas:
- Busca de registros (GET) no `GNEXUM_API_URL` quando `USE_REAL_GNEXUM`.
- Para cada registro encontrado: busca items via `fetch_items_for_record`, monta payload
  com `build_visit_payload`, valida o payload e grava um arquivo com a requisição
  simulada (headers, body, url) em `data/output/simulated_requests/`.
- Mantém o comportamento de salvar payloads em `data/output/payloads/` e CSV resumo.

Uso (PowerShell):
```
$env:USE_REAL_GNEXUM='1'
$env:RUN_DURATION_SECONDS='20'
$env:RUN_MAX_RECORDS='5'  # opcional, número máximo de registros a processar por execução
python ./scripts/run_polling_inprocess.py
```

Observação: este script NÃO envia nada ao SimpliRoute. Ele grava um artefato por visita
mostrando exatamente qual seria a requisição, inclusive headers e body.
"""

import os
import sys
import asyncio
import signal
import time
import json
import re
import csv
from types import SimpleNamespace

# garantir import relativo ao projeto
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, proj_root)

from src.integrations.simpliroute import client as sr_client
from src.integrations.simpliroute.mapper import build_visit_payload
from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.token_manager import login_and_store, get_token
from src.core.config import load_config

import httpx

# carregar config
_CFG = load_config()
SAVE_PAYLOADS = bool(_CFG.get("simpliroute", {}).get("save_payloads", True))
SUMMARY_CSV = os.path.join(proj_root, 'data', 'output', 'payloads_summary.csv')


async def fake_post_simpliroute(route_payload):
    """Simula a escrita ao SimpliRoute: grava payloads e um artefato de requisição.
    Não realiza qualquer requisição externa.
    """
    try:
        preview = route_payload if isinstance(route_payload, dict) else (route_payload[0] if route_payload else {})
        title = preview.get('title') if isinstance(preview, dict) else '<list>'
    except Exception:
        title = '<preview-failed>'

    # Identificadores para arquivos
    sid = None
    try:
        sid = (preview.get('properties') or {}).get('source_ident') if isinstance(preview, dict) else None
    except Exception:
        sid = None
    if not sid:
        sid = preview.get('reference') if isinstance(preview, dict) else None
    if not sid:
        sid = 'noid'

    safe_title = re.sub(r"[^a-zA-Z0-9_-]", "-", str(title))[:60]
    ts = int(time.time())
    fname = f"{ts}_{sid}_{safe_title}.json"

    # criar diretórios
    out_dir = os.path.join(proj_root, 'data', 'output', 'payloads')
    sim_dir = os.path.join(proj_root, 'data', 'output', 'simulated_requests')
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(sim_dir, exist_ok=True)

    # salvar payload JSON
    if SAVE_PAYLOADS:
        path = os.path.join(out_dir, fname)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(route_payload, f, ensure_ascii=False, indent=2)
        print(f"[DRY-RUN] saved payload to {path}")

        # atualizar CSV resumo
        try:
            os.makedirs(os.path.dirname(SUMMARY_CSV), exist_ok=True)
            write_header = not os.path.exists(SUMMARY_CSV)
            with open(SUMMARY_CSV, 'a', encoding='utf-8', newline='') as cf:
                writer = csv.writer(cf)
                if write_header:
                    writer.writerow(['ts', 'source_ident', 'title', 'filename', 'status_code'])
                writer.writerow([ts, sid, title, fname, 200])
        except Exception as e:
            print('[DRY-RUN] failed to update CSV summary:', e)
    else:
        print('[DRY-RUN] save_payloads disabled by config; skipping file write e CSV')

    # gravar artefato simulando a requisição ao SR (headers + body)
    try:
        # normalize and produce UTF-8 JSON for the simulated artifact
        try:
            from core.encoding import dumps_utf8
            body_bytes = dumps_utf8(route_payload)
            body_json = json.loads(body_bytes.decode('utf-8'))
        except Exception:
            body_json = route_payload

        simulated = {
            'ts': ts,
            'target_url': os.getenv('SIMPLIROUTE_API_BASE', _CFG.get('simpliroute', {}).get('api_base', 'https://api.simpliroute.com')) + '/visits',
            'method': 'POST',
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Authorization': f"Bearer {os.getenv('SIMPLIR_ROUTE_TOKEN') or ''}",
            },
            'body': body_json,
        }
        sim_path = os.path.join(sim_dir, fname)
        with open(sim_path, 'w', encoding='utf-8') as sf:
            json.dump(simulated, sf, ensure_ascii=False, indent=2)
        print(f"[DRY-RUN] saved simulated request to {sim_path}")
    except Exception as e:
        print('[DRY-RUN] failed to save simulated request:', e)

    print(f"[DRY-RUN] Simulated post_simpliroute for title={title}")
    return SimpleNamespace(status_code=200, text='{"simulated": true}')


def _extract_record_id(row):
    # tenta extrair um identificador comum em diferentes formatos de resposta
    for key in ('idregistro', 'id', 'record_id', 'ident', 'registro_id'):
        if isinstance(row, dict) and row.get(key) is not None:
            return row.get(key)
    # tentar campos numéricos no próprio objeto
    if isinstance(row, dict) and 'pk' in row:
        return row.get('pk')
    return None


async def fetch_records_list(max_records=10, timeout=8):
    """Tenta obter uma lista de registros do GNEXUM_API_URL.
    Se a URL retornar um objeto com 'data'/'rows'/'items' usa essas chaves.
    """
    url = os.getenv('GNEXUM_API_URL') or _CFG.get('integrations', {}).get('gnexum_api_url')
    use_real = os.getenv('USE_REAL_GNEXUM', 'false').lower() in ('1', 'true', 'yes')
    if not use_real or not url:
        print('[DRY-RUN] USE_REAL_GNEXUM disabled or GNEXUM_API_URL missing; using stub sample')
        return [
            {'idregistro': 123, 'tpregistro': 2, 'endereco': 'Rua Exemplo, 123', 'eventdate': '2025-11-21'}
        ]

    headers = {'Content-Type': 'application/json'}
    # tentar obter token via config/env
    token = os.getenv('GNEXUM_TOKEN')
    if token:
        headers['Authorization'] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # O Gnexum funciona via POST para buscas — tentar POST com payloads candidatos
            bodies = [
                {"limit": max_records},
                {"max": max_records},
                {"page": 1, "per_page": max_records},
                {},
            ]
            resp = None
            retried_after_login = False
            for b in bodies:
                try:
                    resp = await client.post(url, json=b, headers=headers)
                except Exception as e:
                    print(f"[DRY-RUN] Gnexum POST attempt failed: {e}")
                    resp = None
                if not resp:
                    continue
                if resp.status_code == 401:
                    print('[DRY-RUN] Gnexum returned 401 for list POST; attempting login_and_store to refresh token')
                    # tentar login automático usando token_manager e re-tentar uma vez
                    try:
                        await login_and_store()
                        new_token = await get_token()
                        if new_token:
                            headers['Authorization'] = f"Bearer {new_token}"
                            retried_after_login = True
                            # re-tentar este body com token atualizado
                            try:
                                resp = await client.post(url, json=b, headers=headers)
                            except Exception as e:
                                print(f"[DRY-RUN] Gnexum retry POST failed: {e}")
                                resp = None
                    except Exception as e:
                        print('[DRY-RUN] login_and_store failed:', e)
                    if not resp:
                        continue
                if resp.status_code in (200, 201):
                    try:
                        # A API pode devolver diretamente uma lista/objeto com items
                        data = resp.json()
                        rows = []
                        if isinstance(data, list):
                            rows = data
                        elif isinstance(data, dict):
                            rows = data.get('data') or data.get('rows') or data.get('items') or []

                        # Se não vierem rows, o Gnexum pode retornar um endpoint para consumo
                        def _is_url(s: str) -> bool:
                            try:
                                return bool(re.match(r"^https?://", str(s)))
                            except Exception:
                                return False

                        def _find_url(obj):
                            # procura chaves conhecidas
                            if not isinstance(obj, dict):
                                return None
                            for k in ('endpoint', 'url', 'href', 'location', 'data_url'):
                                v = obj.get(k)
                                if isinstance(v, str) and _is_url(v):
                                    return v
                            # procurar em valores qualquer string que seja URL
                            for v in obj.values():
                                if isinstance(v, str) and _is_url(v):
                                    return v
                            return None

                        if rows:
                            return rows[:max_records]

                        # tentar localizar um endpoint retornado para consumir
                        endpoint_url = None
                        if isinstance(data, str) and _is_url(data):
                            endpoint_url = data
                        elif isinstance(data, dict):
                            endpoint_url = _find_url(data)

                        if endpoint_url:
                            # seguir o endpoint e tentar obter os registros
                            try:
                                # tentar GET primeiro, se falhar tentar POST
                                follow = await client.get(endpoint_url, headers=headers)
                                if follow.status_code in (200, 201):
                                    follow_data = follow.json()
                                    if isinstance(follow_data, list):
                                        return follow_data[:max_records]
                                    if isinstance(follow_data, dict):
                                        follow_rows = follow_data.get('data') or follow_data.get('rows') or follow_data.get('items') or []
                                        if follow_rows:
                                            return follow_rows[:max_records]
                                # tentar POST no endpoint
                                follow = await client.post(endpoint_url, json={'limit': max_records}, headers=headers)
                                if follow.status_code in (200, 201):
                                    follow_data = follow.json()
                                    if isinstance(follow_data, list):
                                        return follow_data[:max_records]
                                    if isinstance(follow_data, dict):
                                        follow_rows = follow_data.get('data') or follow_data.get('rows') or follow_data.get('items') or []
                                        if follow_rows:
                                            return follow_rows[:max_records]
                            except Exception as e:
                                print('[DRY-RUN] failed to follow endpoint returned by Gnexum:', e)
                    except Exception as e:
                        print(f"[DRY-RUN] Gnexum POST parse error: {e}")
                        continue
                    except Exception as e:
                        print(f"[DRY-RUN] Gnexum POST parse error: {e}")
                        continue
            # se nada funcionou, avisar e retornar lista vazia (cairá no stub)
            if resp is not None:
                print(f"[DRY-RUN] Gnexum list POST attempts completed, last status={resp.status_code}")
            else:
                print('[DRY-RUN] Gnexum list POST attempts failed (no response)')
            return []
    except Exception as e:
        print('[DRY-RUN] fetch_records_list error:', e)
        return []


async def main():
    # patch client to avoid chamadas reais
    try:
        sr_client.post_simpliroute = fake_post_simpliroute
    except Exception:
        pass

    # parâmetros de execução
    run_seconds = int(os.getenv('RUN_DURATION_SECONDS', '0') or 0)
    max_records = int(os.getenv('RUN_MAX_RECORDS', '5') or 5)

    stop_event = asyncio.Event()

    def _on_signal(sig, frame=None):
        print(f"Received signal {sig}; shutting down...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, lambda s=s: _on_signal(s))
        except NotImplementedError:
            pass

    # buscar lista de registros
    # garantir token válido no início (se estiver usando Gnexum real)
    try:
        use_real = os.getenv('USE_REAL_GNEXUM', 'false').lower() in ('1', 'true', 'yes')
        if use_real:
            try:
                tok = await get_token()
                if tok:
                    print('[DRY-RUN] GNEXUM token available at startup')
                else:
                    print('[DRY-RUN] GNEXUM token not available at startup; attempted login')
            except Exception as e:
                print('[DRY-RUN] warning: get_token/login failed at startup:', e)
    except Exception:
        pass

    records = await fetch_records_list(max_records=max_records)
    if not records:
        print('[DRY-RUN] No records found; exiting')
        return

    # processar registros: se os registros vierem com ID_ATENDIMENTO, agrupar por atendimento
    grouped = {}
    key_field = None
    if records and isinstance(records, list) and any(isinstance(r, dict) and ('ID_ATENDIMENTO' in r or 'idregistro' in r) for r in records):
        # agrupar por ID_ATENDIMENTO ou idregistro
        for r in records:
            rid = r.get('ID_ATENDIMENTO') or r.get('idregistro') or r.get('id') or 'unknown'
            grouped.setdefault(rid, []).append(r)
        key_field = 'ID_ATENDIMENTO'
    else:
        # cada registro é tratado isoladamente
        for r in records:
            rid = _extract_record_id(r) or r.get('idregistro') or r.get('id') or 'unknown'
            grouped.setdefault(rid, []).append(r)

    for rid, rows in grouped.items():
        # tentar buscar items detalhados para o atendimento (se aplicável)
        try:
            items = await fetch_items_for_record(rid)
        except Exception as e:
            print(f"[DRY-RUN] failed to fetch items for {rid}: {e}")
            items = []

        # montar um sample agregando as linhas do atendimento
        first = rows[0] if rows else {}
        sample = {
            'tpregistro': first.get('tpregistro') or first.get('TPREGISTRO') or 2,
            'idregistro': rid,
            'endereco': first.get('ENDERECO') or first.get('endereco') or first.get('address') or None,
            # suportar DT_VISITA do Gnexum como data planejada
            'eventdate': first.get('DT_VISITA') or first.get('dt_visita') or first.get('eventdate') or first.get('planned_date') or first.get('date') or None,
            # combinar rows como items caso items vindos do Gnexum representem sub-itens
            'items': items or rows,
        }

        payload = build_visit_payload(sample)

        # validações simples antes de simular
        missing = [k for k in ('title', 'address', 'planned_date') if not payload.get(k)]
        if missing:
            print(f"[DRY-RUN] Warning: payload for record {rid} missing fields: {missing}")

        resp = await fake_post_simpliroute(payload)
        print(f"[DRY-RUN] simulated status for record {rid}: {getattr(resp, 'status_code', None)}")

    # aguardar se rodar por tempo limitado
    try:
        if run_seconds > 0:
            print(f"Run duration active: waiting {run_seconds}s before exit")
            await asyncio.wait_for(stop_event.wait(), timeout=run_seconds)
    except asyncio.TimeoutError:
        print('Run duration expired; exiting')


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('KeyboardInterrupt received; exiting')
