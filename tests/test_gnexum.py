import asyncio

from src.integrations.simpliroute import gnexum


def test_fetch_items_stub_mode():
    # garantir que, em modo padrão (USE_REAL_GNEXUM não setado), retorna lista
    items = asyncio.run(gnexum.fetch_items_for_record(9999))
    assert isinstance(items, list)
    assert len(items) >= 0
    # se existem elementos, checar keys mínimas
    if items:
        assert "title" in items[0]
        assert "quantity_planned" in items[0]
