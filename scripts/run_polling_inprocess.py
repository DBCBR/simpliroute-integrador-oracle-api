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
python .\scripts\run_polling_inprocess.py
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
        simulated = {
            'ts': ts,
            'target_url': os.getenv('SIMPLIROUTE_API_BASE', _CFG.get('simpliroute', {}).get('api_base', 'https://api.simpliroute.com')) + '/visits',
            'method': 'POST',
            'headers': {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {os.getenv('SIMPLIR_ROUTE_TOKEN') or ''}",
            },
            'body': route_payload,
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
            resp = await client.get(url, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                rows = []
                if isinstance(data, list):
                    rows = data
                elif isinstance(data, dict):
                    rows = data.get('data') or data.get('rows') or data.get('items') or []
                # limitar número de registros
                return rows[:max_records]
            else:
                print(f"[DRY-RUN] Gnexum list request returned {resp.status_code}; falling back to stub")
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
    records = await fetch_records_list(max_records=max_records)
    if not records:
        print('[DRY-RUN] No records found; exiting')
        return

    # processar cada registro: montar payload e simular POST
    for r in records:
        rid = _extract_record_id(r) or r.get('idregistro') or r.get('id') or 'unknown'
        try:
            items = await fetch_items_for_record(rid)
        except Exception as e:
            print(f"[DRY-RUN] failed to fetch items for {rid}: {e}")
            items = []

        # montar objeto similar ao que o mapper espera
        sample = {
            'tpregistro': r.get('tpregistro') or r.get('tp') or 2,
            'idregistro': rid,
            'endereco': r.get('endereco') or r.get('address') or r.get('rua') or None,
            'eventdate': r.get('eventdate') or r.get('planned_date') or r.get('date') or None,
            'items': items,
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
