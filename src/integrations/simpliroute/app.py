import asyncio
import os
from typing import Dict, Any

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse

from .mapper import build_visit_payload
from .client import post_simpliroute, post_gnexum_update

app = FastAPI(title="SimpliRoute Integration Service")


async def polling_task(interval_minutes: int):
    """Tarefa de polling simples (simulada).

    No PDD real, aqui faria GET na API Gnexum para buscar registros em 'A'.
    """
    while True:
        try:
            # Placeholder: simular busca de registros e envio ao SimpliRoute
            # Em implementação real: consultar Gnexum e montar payloads
            print("[polling] executando consulta ao Gnexum (simulada)")
            # Exemplo de payload simulado
            sample = {"tpregistro": 2, "idregistro": 123, "endereco": "Rua Exemplo, 123", "eventdate": "2025-11-21"}
            payload = build_visit_payload(sample)
            # chamar cliente (não bloquear o loop)
            resp = await post_simpliroute(payload)
            print(f"[polling] envio SR status: {resp.status_code}")
        except Exception as e:
            print(f"[polling] erro: {e}")
        await asyncio.sleep(interval_minutes * 60)


@app.on_event("startup")
async def startup_event():
    # obter intervalo do config/env
    try:
        from core.config import load_config

        cfg = load_config()
        interval = int(cfg.get("simpliroute", {}).get("polling_interval_minutes", 60))
    except Exception:
        interval = int(os.getenv("POLLING_INTERVAL_MINUTES", 60))

    # iniciar tarefa em background
    app.state._polling_task = asyncio.create_task(polling_task(interval))


@app.on_event("shutdown")
async def shutdown_event():
    task = getattr(app.state, "_polling_task", None)
    if task:
        task.cancel()


@app.post("/webhook/simpliroute")
async def webhook_simpliroute(request: Request, background: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)

    # Persistir o webhook recebido (mínimo: gravar em arquivo)
    os.makedirs("data/work/webhooks", exist_ok=True)
    filename = f"data/work/webhooks/webhook_{int(asyncio.get_event_loop().time())}.json"
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
