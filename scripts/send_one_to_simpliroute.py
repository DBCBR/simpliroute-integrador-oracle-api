"""Enviar um único registro do Gnexum ao SimpliRoute.

Segurança: o script NÃO enviará nada a menos que a variável de ambiente
`SEND_CONFIRM` esteja definida para '1' ou 'true'. Isso evita envios acidentais.

Uso (PowerShell):
# configurar variáveis de ambiente na sua sessão (substitua os valores reais)
$env:GNEXUM_API_URL='https://api.gnexum.example/endpoint'
$env:GNEXUM_TOKEN='seu_token_gnexum'
$env:SIMPLIROUTE_API_BASE='https://api.simpliroute.com'
$env:SIMPLIROUTE_TOKEN='seu_token_simpliroute'
$env:RECORD_ID='16946'          # opcional; se omisso, o script tentará obter o primeiro registro
# Para apenas PREVIEW (não enviar):
$env:SEND_CONFIRM='0'
python .\scripts\send_one_to_simpliroute.py
# Para ENVIAR de verdade:
$env:SEND_CONFIRM='1'
python .\scripts\send_one_to_simpliroute.py
"""

import os
import sys
import asyncio
import json
from typing import Any, Dict, Optional

# garantir import relativo ao projeto
HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from src.integrations.simpliroute.gnexum import fetch_items_for_record
from src.integrations.simpliroute.mapper import build_visit_payload
from src.integrations.simpliroute.client import post_simpliroute
from src.integrations.simpliroute.token_manager import get_token

import httpx

GNEXUM_URL = os.getenv('GNEXUM_API_URL')
GNEXUM_TOKEN = os.getenv('GNEXUM_TOKEN')
SIMPLIROUTE_TOKEN = os.getenv('SIMPLIROUTE_TOKEN') or os.getenv('SIMPLIR_ROUTE_TOKEN') or os.getenv('SIMPLIROUTE_API_TOKEN')
SEND_CONFIRM = os.getenv('SEND_CONFIRM', '0').lower() in ('1', 'true', 'yes')
RECORD_ID = os.getenv('RECORD_ID')


async def fetch_record_details(record_id: str, timeout: int = 8) -> Optional[Dict[str, Any]]:
    if not GNEXUM_URL:
        return None
    headers = {'Content-Type': 'application/json'}
    if GNEXUM_TOKEN:
        headers['Authorization'] = f"Bearer {GNEXUM_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(GNEXUM_URL, json={'idregistro': record_id}, headers=headers)
            if resp.status_code in (200, 201):
                data = resp.json()
                # A API pode retornar lista ou objeto
                if isinstance(data, list) and data:
                    return data[0]
                if isinstance(data, dict):
                    # tentar extrair first row
                    rows = data.get('data') or data.get('rows') or data.get('items') or []
                    if isinstance(rows, list) and rows:
                        return rows[0]
                    # se veio o próprio registro
                    return data
    except Exception:
        return None
    return None


async def main():
    if not GNEXUM_URL:
        print('Erro: GNEXUM_API_URL não configurado. Defina $env:GNEXUM_API_URL e tente novamente.')
        return
    # obter token através do token_manager para permitir refresh automático
    try:
        token_val = await get_token()
    except Exception:
        token_val = None
    if not token_val:
        print('Aviso: GNEXUM_TOKEN não disponível; o script tentará acessar sem token (pode falhar).')
    GNEXUM_TOKEN_USED = token_val

    if not SIMPLIROUTE_TOKEN:
        print('Erro: SIMPLIROUTE_TOKEN não configurado. Defina $env:SIMPLIROUTE_TOKEN e tente novamente.')
        return

    record_id = RECORD_ID
    record_detail = None

    if not record_id:
        # tentar obter lista simples: POST {"limit":1}
        headers = {'Content-Type': 'application/json'}
        if GNEXUM_TOKEN_USED:
            headers['Authorization'] = f"Bearer {GNEXUM_TOKEN_USED}"
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(GNEXUM_URL, json={'limit': 1}, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    if isinstance(data, list) and data:
                        first = data[0]
                    elif isinstance(data, dict):
                        first = (data.get('data') or data.get('rows') or data.get('items') or [])
                        if isinstance(first, list) and first:
                            first = first[0]
                        else:
                            first = data
                    else:
                        first = None
                    if first:
                        # tentar extrair id
                        record_id = first.get('ID_ATENDIMENTO') or first.get('idregistro') or first.get('id')
                        record_detail = first
        except Exception as e:
            print('Falha ao obter lista do Gnexum:', e)
            return

    if not record_id:
        print('Não foi possível determinar um record_id a partir do Gnexum. Forneça $env:RECORD_ID e tente novamente.')
        return

    if not record_detail:
        record_detail = await fetch_record_details(record_id)

    # buscar items (detalhes) para o atendimento
    items = []
    try:
        # request raw gnexum rows so mapper sees ESPECIALIDADE/PROFISSIONAL/PERIODICIDADE/TIPOVISITA
        items = await fetch_items_for_record(record_id, normalize=False)
    except Exception as e:
        print('Falha ao buscar items no Gnexum:', e)

    # se fetch_items_for_record não retornou items, tente extrair rows/items do record_detail
    if not items and isinstance(record_detail, dict):
        fallback_rows = record_detail.get('items') or record_detail.get('rows') or record_detail.get('data') or []
        if isinstance(fallback_rows, list) and fallback_rows:
            items = fallback_rows

    sample = {
        'tpregistro': (record_detail or {}).get('tpregistro') or 2,
        'idregistro': record_id,
        'endereco': (record_detail or {}).get('ENDERECO') or (record_detail or {}).get('endereco') or None,
        'eventdate': (record_detail or {}).get('DT_VISITA') or (record_detail or {}).get('dt_visita') or (record_detail or {}).get('eventdate') or None,
        'items': items or [],
        # propagar campos relevantes do registro para que o mapper possa decidir corretamente
        'NOME_PACIENTE': (record_detail or {}).get('NOME_PACIENTE') or (record_detail or {}).get('nome') or None,
        'ID_ATENDIMENTO': record_id,
        'ESPECIALIDADE': (record_detail or {}).get('ESPECIALIDADE') or (record_detail or {}).get('especialidade'),
        'TIPOVISITA': (record_detail or {}).get('TIPOVISITA') or (record_detail or {}).get('tipovisita'),
        'PROFISSIONAL': (record_detail or {}).get('PROFISSIONAL') or (record_detail or {}).get('profissional'),
    }

    payload = build_visit_payload(sample)

    print('\n--- Payload preparado (pronto para enviar) ---\n')
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print('\n--------------------------------------------\n')

    if not SEND_CONFIRM:
        print('SEND_CONFIRM não definido; o script fará apenas o preview. Para enviar, defina $env:SEND_CONFIRM=1 e rode novamente.')
        return

    # enviar ao SimpliRoute
    print('Enviando ao SimpliRoute...')
    try:
        resp = await post_simpliroute(payload)
        if resp is None:
            print('Erro: post_simpliroute retornou None (falha na requisição).')
        else:
            print('Resposta SR: status=', getattr(resp, 'status_code', None))
            print('Body:', getattr(resp, 'text', None))
    except Exception as e:
        print('Exceção durante envio ao SimpliRoute:', e)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Cancelado pelo usuário')
