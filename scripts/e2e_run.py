import asyncio
import sys
import json

# garantir que possamos importar o pacote src quando executado dentro do container
sys.path.insert(0, "/app")

from src.integrations.simpliroute import gnexum, mapper, client


async def main(record_id: int):
    print(f"E2E: buscando items para registro {record_id} no Gnexum...")
    items = await gnexum.fetch_items_for_record(record_id)
    print(f"E2E: encontrados {len(items)} items")

    record = {
        "tpregistro": 1,
        "idregistro": record_id,
        "endereco": "",
        "eventdate": None,
        "items": items,
    }

    payload = mapper.build_visit_payload(record)
    print("E2E: payload gerado:")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:2000])

    print("E2E: enviando payload ao SimpliRoute...")
    resp = await client.post_simpliroute(payload)
    if resp is None:
        print("E2E: request falhou (None)")
        return

    try:
        status = resp.status_code
        text = resp.text
    except Exception:
        status = getattr(resp, 'status', 'unknown')
        text = '<no body>'

    print(f"E2E: SimpliRoute status={status}")
    print(text[:4000])


if __name__ == '__main__':
    # escolher um idregistro conhecido; altere se desejar
    rid = 5761019
    asyncio.run(main(rid))
