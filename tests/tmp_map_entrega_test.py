import sys, os, json
sys.path.insert(0, os.getcwd())
from dotenv import load_dotenv
load_dotenv('settings/.env', override=False)
from src.integrations.simpliroute.mapper import build_visit_payload

sample = {
    'ID_ATENDIMENTO': 167002,
    'idregistro': 167002,
    'title': 'Maria Elisabete Arruda Fialho',
    'NOME': 'Maria Elisabete Arruda Fialho',
    'address': 'Rua Professor Gastão Bahiana, 155 Apartamento 604 - Copacabana, Rio de Janeiro - RJ, 22071030',
    'latitude': '-22.977360',
    'longitude': '-43.194550',
    'load': 0.0,
    'window_start': '07:00:00',
    'window_end': '23:00:00',
    'window_start_2': '23:59:00',
    'window_end_2': '23:59:00',
    'duration': '00:30:00',
    'TELEFONES': '21981766167',
    'reference': '167002',
    'notes': 'Entrega',
    'planned_date': '2025-12-03',
    'programmed_date': '2025-12-03',
    'route': '0ba120e2-8f2b-4854-85b0-610d4cdc8128',
    'route_estimated_time_start': '07:00:00',
    'route_status': 'started',
    'estimated_time_arrival': '11:17:00',
    'estimated_time_departure': '11:47:00',
    'checkin_time': '2025-12-03T14:22:31.598000Z',
    'checkout_time': '2025-12-03T14:23:23.579000Z',
    'checkout_latitude': '-22.978027',
    'checkout_longitude': '-43.192974',
    'checkout_comment': '',
    'checkout_observation': None,
    'signature': None,
    'pictures': [
        'https://simpli-visit-images.s3.amazonaws.com/visit-pictures/2025/12/03/36af9c0195eb45a3d38a56d0736c7a8f.jpeg',
        'https://simpli-visit-images.s3.amazonaws.com/visit-pictures/2025/12/03/61fce81bcfb19ba979d168e794ebdce7.jpeg',
        'https://simpli-visit-images.s3.amazonaws.com/visit-pictures/2025/12/03/6b2a6d887888f61ffbfb92500797e9c1.jpeg',
    ],
    'created': '2025-11-26T12:07:18.752287Z',
    'modified': '2025-12-03T14:23:30.595475Z',
    'eta_predicted': '2025-12-03T11:17:00-03:00',
    'eta_current': '2025-12-03T11:17:00-03:00',
    'driver': 469728,
    'vehicle': 628920,
    'priority': False,
    'has_alert': False,
    'priority_level': 0,
    'extra_field_values': {'conferencia_solar': 'NÃO', 'checkout_rota': ''},
    'geocode_alert': None,
    'visit_type': 'rota',
    'current_eta': '2025-12-03T14:41:00Z',
    'fleet': None,
    'on_its_way': None,
    'seller': None,
    'is_route_completed': False
}
# Force ORACLE_VIEW to deliveries so mapper treats as entrega
os.environ['ORACLE_VIEW'] = 'VWPACIENTES_ENTREGAS'

out = build_visit_payload(sample)
print(json.dumps(out, ensure_ascii=False, indent=2))
