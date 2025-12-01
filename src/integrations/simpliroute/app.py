import asyncio
import os
from typing import Dict, Any

from fastapi import FastAPI, Request, BackgroundTasks
import asyncio
import os
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from .mapper import build_visit_payload
from .client import post_simpliroute, post_gnexum_update
from .gnexum import fetch_items_for_record
from .token_manager import get_token, login_and_store


async def polling_task(interval_minutes: int):
    """Tarefa de polling simples (simulada).

    No PDD real, aqui faria GET na API Gnexum para buscar registros em 'A'.
    """
    while True:
        try:
            # Placeholder: simular busca de registros e envio ao SimpliRoute
            print("[polling] executando consulta ao Gnexum (simulada)")
            sample = {"tpregistro": 2, "idregistro": 123, "endereco": "Rua Exemplo, 123", "eventdate": "2025-11-21"}
            # tentar popular items via Gnexum (stub ou real, dependendo de env)
            try:
                sample_items = await fetch_items_for_record(sample.get("idregistro"))
                sample["items"] = sample_items
            except Exception:
                sample["items"] = []
            payload = build_visit_payload(sample)
            resp = await post_simpliroute(payload)
            # resp pode ser None em ambiente de teste
            status = getattr(resp, "status_code", None)
            print(f"[polling] envio SR status: {status}")
        except Exception as e:
            print(f"[polling] erro: {e}")
        # aguardar intervalo, tratar cancelamento para shutdown gracioso
        try:
            await asyncio.sleep(interval_minutes * 60)
        except asyncio.CancelledError:
            # Cancelamento esperado durante shutdown; encerrar o loop sem traceback
            print("[polling] task cancelada — encerrando polling")
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    # obter intervalo do config/env
    try:
        from core.config import load_config

        cfg = load_config()
        interval = int(cfg.get("simpliroute", {}).get("polling_interval_minutes", 60))
    except Exception:
        interval = int(os.getenv("POLLING_INTERVAL_MINUTES", 60))

    # garantir que o token do Gnexum esteja atualizado ao iniciar
    try:
        # tenta obter token válido (get_token fará login se necessário)
        tok = None
        try:
            tok = await get_token()
        except Exception:
            # se get_token não estiver disponível de forma assíncrona, tentar login
            try:
                await login_and_store()
            except Exception:
                pass
        if tok:
            print("[startup] GNEXUM token present/updated")
        else:
            print("[startup] GNEXUM token not available after login attempt")
    except Exception:
        # garantir que falhas no refresh de token não impeçam o app de subir
        print("[startup] warning: failed to refresh GNEXUM token")

    # iniciar tarefa em background
    app.state._polling_task = asyncio.create_task(polling_task(interval))
    try:
        yield
    finally:
        task = getattr(app.state, "_polling_task", None)
        if task:
            task.cancel()
            try:
                await task
            except Exception:
                pass


app = FastAPI(title="SimpliRoute Integration Service", lifespan=lifespan)


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@app.get("/health/live")
async def live() -> JSONResponse:
    return JSONResponse({"status": "alive"})


@app.get("/health/ready")
async def ready() -> JSONResponse:
    """Verifica readiness mínima:
    - presença de variáveis de ambiente essenciais (tokens)
    - tarefa de polling inicializada
    """
    token_sr = os.getenv("SIMPLIR_ROUTE_TOKEN")
    token_gn = os.getenv("GNEXUM_TOKEN")
    polling_ok = getattr(app.state, "_polling_task", None) is not None

    ready_ok = bool(polling_ok and (token_sr or token_gn))

    status = "ready" if ready_ok else "not_ready"
    return JSONResponse({"status": status, "polling_task": bool(polling_ok), "has_tokens": bool(token_sr or token_gn)})


@app.post("/webhook/simpliroute")
async def webhook_simpliroute(request: Request, background: BackgroundTasks):
    try:
        # validar JSON
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    # Validação opcional do token do webhook: se configurado, exige header Authorization: Token <token>
    expected = os.getenv("SIMPLIROUTE_WEBHOOK_TOKEN") or os.getenv("SIMPLIR_ROUTE_TOKEN") or os.getenv("SIMPLIROUTE_TOKEN")
    if expected:
        auth_hdr = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        # suportar formas: 'Token <v>' ou 'Bearer <v>'
        token_val = auth_hdr.replace("Bearer ", "").replace("Token ", "").strip()
        if token_val != expected:
            return JSONResponse({"error": "unauthorized webhook"}, status_code=401)

    # Persistir o webhook recebido (mínimo: gravar em arquivo)
    os.makedirs("data/work/webhooks", exist_ok=True)
    import time

    filename = f"data/work/webhooks/webhook_{int(time.time())}.json"
    try:
        with open(filename, "w", encoding="utf-8") as f:
            import json

            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # Agendar envio do status para Gnexum (simulado)
    background.add_task(post_gnexum_update, {"source": "simpliroute", "payload": payload})

    return {"status": "received"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("WEBHOOK_PORT", 8000))
    uvicorn.run("src.integrations.simpliroute.app:app", host="0.0.0.0", port=port, reload=False)
