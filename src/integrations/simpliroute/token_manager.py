import os
import time
import json
import logging
from typing import Optional, Dict, Any

import httpx
from dotenv import load_dotenv
import asyncio

logger = logging.getLogger(__name__)


def _env_path() -> str:
    return os.path.join("settings", ".env")


def _read_env_file() -> Dict[str, str]:
    path = _env_path()
    data: Dict[str, str] = {}
    if not os.path.exists(path):
        return data
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            data[k.strip()] = v.strip()
    return data


def _write_env_file(updates: Dict[str, str]) -> None:
    path = _env_path()
    env = _read_env_file()
    env.update(updates)
    # Preserve order: write existing keys first, then new keys
    lines = []
    for k, v in env.items():
        lines.append(f"{k}={v}\n")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines)
    except (PermissionError, OSError) as e:
        # Ambiente em container pode montar o projeto como read-only.
        # Nesse caso, não conseguimos persistir no arquivo; atualizar apenas variáveis de ambiente em memória.
        logger.debug("_write_env_file: não foi possível gravar %s, fallback para os.environ: %s", path, e)
        for k, v in updates.items():
            try:
                os.environ[k] = v
            except Exception:
                pass


async def login_and_store() -> Optional[str]:
    """Tenta efetuar login no Gnexum usando variáveis de ambiente e grava tokens em `settings/.env`.

    Requisitos (via env):
    - `GNEXUM_LOGIN_URL` : URL do endpoint de login (ex.: /api/auth/login-api)
    - `GNEXUM_LOGIN_USERNAME` e `GNEXUM_LOGIN_PASSWORD` OU `GNEXUM_LOGIN_PAYLOAD` (JSON string)

    Retorna o `access_token` em caso de sucesso, ou None.
    """
    # garantir que valores no arquivo .env substituam quaisquer valores já presentes
    load_dotenv(_env_path(), override=True)
    login_url = os.getenv("GNEXUM_LOGIN_URL")
    if not login_url:
        logger.debug("login_and_store: GNEXUM_LOGIN_URL não definido")
        return None

    payload = None
    raw = os.getenv("GNEXUM_LOGIN_PAYLOAD")
    if raw:
        try:
            payload = json.loads(raw)
        except Exception:
            logger.debug("GNEXUM_LOGIN_PAYLOAD inválido JSON")

    if payload is None:
        user = os.getenv("GNEXUM_LOGIN_USERNAME")
        pwd = os.getenv("GNEXUM_LOGIN_PASSWORD")
        if not user or not pwd:
            logger.debug("login_and_store: credenciais não fornecidas (GNEXUM_LOGIN_USERNAME/PASSWORD)")
            return None
        # escolher chave: se username contém '@' usar email
        if "@" in user:
            payload = {"email": user, "password": pwd}
        else:
            payload = {"username": user, "password": pwd}

    # tentar com retries e fallback (JSON -> form-encoded)
    resp = None
    attempts = int(os.getenv("GNEXUM_LOGIN_RETRIES", "3") or 3)
    delay = float(os.getenv("GNEXUM_LOGIN_RETRY_DELAY_SECONDS", "1") or 1)
    async with httpx.AsyncClient(timeout=20.0) as client:
        for attempt in range(1, attempts + 1):
            try:
                logger.debug("login_and_store: attempt %d POST json %s", attempt, login_url)
                resp = await client.post(login_url, json=payload)
            except Exception as e:
                logger.debug("login_and_store: POST json attempt %d failed: %s", attempt, e)
                resp = None

            if resp and resp.status_code in (200, 201):
                break

            # tentar form-encoded como fallback
            try:
                logger.debug("login_and_store: attempt %d POST form %s", attempt, login_url)
                headers = {"Content-Type": "application/x-www-form-urlencoded"}
                resp = await client.post(login_url, data=payload, headers=headers)
            except Exception as e:
                logger.debug("login_and_store: POST form attempt %d failed: %s", attempt, e)
                resp = None

            if resp and resp.status_code in (200, 201):
                break

            # esperar antes do próximo attempt (backoff simples)
            try:
                await asyncio.sleep(delay)
            except Exception:
                pass

    if not resp or resp.status_code not in (200, 201):
        try:
            body_preview = resp.text[:400] if resp is not None else '<no-response>'
        except Exception:
            body_preview = '<no-body>'
        logger.debug("login_and_store: login failed status=%s body=%s", getattr(resp, 'status_code', None), body_preview)
        return None

    try:
        data = resp.json()
    except Exception:
        logger.debug("login_and_store: resposta não é JSON")
        return None

    # Normalizar chaves possíveis, e procurar recursivamente por tokens em estruturas aninhadas
    def _find_token_in_obj(obj):
        try:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    if isinstance(v, str) and any(x in lk for x in ("access", "token")) and len(v) > 10:
                        return v
                    res = _find_token_in_obj(v)
                    if res:
                        return res
            elif isinstance(obj, list):
                for item in obj:
                    res = _find_token_in_obj(item)
                    if res:
                        return res
        except Exception:
            return None
        return None

    token = (
        data.get("access_token")
        or data.get("token")
        or data.get("accessToken")
        or _find_token_in_obj(data)
    )
    refresh = (
        data.get("refresh_token")
        or data.get("refreshToken")
        or data.get("refresh")
        or _find_token_in_obj(data.get("refresh") or {})
    )
    expires = data.get("expires_in") or data.get("expiresIn") or data.get("expires")

    if not token:
        # log detalhado para diagnóstico — não imprimir senha
        try:
            preview = resp.text[:800]
        except Exception:
            preview = '<no-body>'
        logger.debug("login_and_store: resposta sem access token; status=%s body_preview=%s", resp.status_code, preview)
        return None

    updates: Dict[str, str] = {"GNEXUM_TOKEN": token}
    if refresh:
        updates["GNEXUM_REFRESH_TOKEN"] = refresh
    if expires:
        updates["GNEXUM_EXPIRES_IN"] = str(expires)
    # carimbar momento da atualização
    updates["GNEXUM_TOKEN_UPDATED_AT"] = str(int(time.time()))

    try:
        _write_env_file(updates)
        # recarregar variáveis em runtime
        load_dotenv(_env_path(), override=True)
    except Exception as e:
        logger.debug("login_and_store: falha ao gravar .env %s", e)

    return token


async def get_token() -> Optional[str]:
    """Retorna um token válido. Se ausente/expirado e credenciais disponíveis, tenta login automático."""
    # garantir que valores no arquivo .env substituam quaisquer valores já presentes
    load_dotenv(_env_path(), override=True)
    token = os.getenv("GNEXUM_TOKEN")
    expires_in = os.getenv("GNEXUM_EXPIRES_IN")
    updated_at = os.getenv("GNEXUM_TOKEN_UPDATED_AT")

    if token:
        try:
            if expires_in and updated_at:
                exp = int(expires_in)
                upd = int(updated_at)
                now = int(time.time())
                # se faltar menos de 60s para expirar, considerar expirado
                if upd + exp - 60 > now:
                    return token
            else:
                # sem metadata, devolver token (não podemos validar)
                return token
        except Exception:
            # em caso de parse error, tentar login
            pass

    # tentar renovar via refresh token antes de efetuar novo login completo
    try:
        refreshed = await refresh_and_store()
        if refreshed:
            return refreshed
    except Exception:
        pass

    # tentar login automático se possível (fallback)
    new = await login_and_store()
    if new:
        return new

    return token
