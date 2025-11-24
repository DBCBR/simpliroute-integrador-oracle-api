import asyncio
import types

import pytest

import src.integrations.simpliroute.gnexum as gnexum


class DummyResp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class DummyClient:
    def __init__(self, responses):
        # responses: dict mapping ('get', url) or ('post', url) to DummyResp
        self.responses = responses

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        key = ("get", url)
        # fallback: try keys ignoring query
        return self.responses.get(key, DummyResp(404, {}))

    async def post(self, url, json=None, headers=None):
        key = ("post", url)
        return self.responses.get(key, DummyResp(404, {}))


def test_fetch_items_real_get(monkeypatch):
    # Simula que GNEXUM_URL responde uma lista direta
    gnexum.GNEXUM_URL = "https://gnexum.test/api/items"
    gnexum.USE_REAL_GNEXUM = True

    sample_items = [{"title": "X", "quantity_planned": 2}]

    responses = {
        ("get", "https://gnexum.test/api/items"): DummyResp(200, sample_items)
    }

    async def _run():
        monkeypatch.setattr(gnexum, "httpx", types.SimpleNamespace(AsyncClient=lambda timeout: DummyClient(responses)))
        items = await gnexum.fetch_items_for_record(42, timeout=1)
        assert isinstance(items, list)
        assert items[0]["title"] == "X"

    asyncio.run(_run())


def test_fetch_items_real_post(monkeypatch):
    # Simula que GETs falham e POST retorna objeto com 'items'
    gnexum.GNEXUM_URL = "https://gnexum.test/api/query"
    gnexum.USE_REAL_GNEXUM = True

    resp_data = {"items": [{"nome": "ItemNome", "quantidade": 3, "load": 1}]}
    responses = {
        ("get", "https://gnexum.test/api/query"): DummyResp(500, {}),
        ("get", "https://gnexum.test/api/query?record_id=99"): DummyResp(500, {}),
        ("get", "https://gnexum.test/api/query?id=99"): DummyResp(500, {}),
        ("post", "https://gnexum.test/api/query"): DummyResp(200, resp_data),
    }

    async def _run():
        monkeypatch.setattr(gnexum, "httpx", types.SimpleNamespace(AsyncClient=lambda timeout: DummyClient(responses)))
        items = await gnexum.fetch_items_for_record(99, timeout=1)
        assert isinstance(items, list)
        assert items[0]["title"] == "ItemNome"
        assert items[0]["quantity_planned"] == 3.0

    asyncio.run(_run())
