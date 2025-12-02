import os
import asyncio
from types import SimpleNamespace

import src.integrations.simpliroute.token_manager as tm


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self._payload = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None, data=None, headers=None):
        # return a successful refresh response
        return FakeResponse(200, {"access_token": "new-token-xyz", "refresh_token": "new-refresh-abc", "expires_in": 3600})


def test_refresh_and_store_monkeypatch(monkeypatch):
    env_path = os.path.join("settings", ".env")
    # backup if exists
    bak = None
    if os.path.exists(env_path):
        bak = env_path + ".bak"
        os.rename(env_path, bak)

    try:
        # ensure env variables present
        os.environ.pop("GNEXUM_TOKEN", None)
        os.environ["GNEXUM_REFRESH_TOKEN"] = "old-refresh"
        os.environ["GNEXUM_TOKEN_REFRESH_URL"] = "https://example.local/refresh"

        # monkeypatch httpx.AsyncClient used in module
        monkeypatch.setattr(tm, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

        token = asyncio.run(tm.refresh_and_store())
        assert token == "new-token-xyz"

        # settings/.env should contain the new token (loadable)
        assert os.path.exists(env_path)
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "GNEXUM_TOKEN=new-token-xyz" in content
        assert "GNEXUM_REFRESH_TOKEN=new-refresh-abc" in content

    finally:
        # cleanup: restore backup
        if bak and os.path.exists(bak):
            if os.path.exists(env_path):
                os.remove(env_path)
            os.rename(bak, env_path)


def test_get_token_uses_refresh(monkeypatch):
    # ensure no GNEXUM_TOKEN exists so get_token will attempt refresh
    os.environ.pop("GNEXUM_TOKEN", None)
    os.environ["GNEXUM_REFRESH_TOKEN"] = "old-refresh"
    os.environ["GNEXUM_TOKEN_REFRESH_URL"] = "https://example.local/refresh"

    monkeypatch.setattr(tm, "httpx", SimpleNamespace(AsyncClient=FakeAsyncClient))

    env_path = os.path.join("settings", ".env")
    bak = None
    if os.path.exists(env_path):
        bak = env_path + ".bak"
        os.rename(env_path, bak)
    try:
        token = asyncio.run(tm.get_token())
        assert token == "new-token-xyz"
    finally:
        # restore backup
        if bak and os.path.exists(bak):
            if os.path.exists(env_path):
                os.remove(env_path)
            os.rename(bak, env_path)
import asyncio
import types
import os

import pytest

import src.integrations.simpliroute.token_manager as token_manager


class DummyResp:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class DummyClient:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        return self.resp


def test_login_and_store_success(monkeypatch, tmp_path):
    envfile = tmp_path / "envtest"

    # redirecionar _env_path para arquivo temporário
    monkeypatch.setattr(token_manager, "_env_path", lambda: str(envfile))

    # mock httpx.AsyncClient to return a known token
    resp = DummyResp(200, {"access_token": "tk-123", "refresh_token": "r-1", "expires_in": 3600})
    monkeypatch.setattr(token_manager, "httpx", types.SimpleNamespace(AsyncClient=lambda timeout: DummyClient(resp)))

    monkeypatch.setenv("GNEXUM_LOGIN_URL", "https://gnexum.test/login")
    monkeypatch.setenv("GNEXUM_LOGIN_USERNAME", "user@example.com")
    monkeypatch.setenv("GNEXUM_LOGIN_PASSWORD", "secret")

    async def _run():
        tok = await token_manager.login_and_store()
        assert tok == "tk-123"
        # arquivo .env criado e contém a variável
        text = envfile.read_text(encoding="utf-8")
        assert "GNEXUM_TOKEN=tk-123" in text

    asyncio.run(_run())


def test_get_token_uses_existing(monkeypatch, tmp_path):
    envfile = tmp_path / "envtest"
    envfile.write_text("GNEXUM_TOKEN=abc\nGNEXUM_EXPIRES_IN=3600\nGNEXUM_TOKEN_UPDATED_AT=9999999999\n", encoding="utf-8")
    monkeypatch.setattr(token_manager, "_env_path", lambda: str(envfile))

    # prevent actual login attempts
    monkeypatch.setattr(token_manager, "login_and_store", lambda: None)

    async def _run():
        tok = await token_manager.get_token()
        assert tok == "abc"

    asyncio.run(_run())
