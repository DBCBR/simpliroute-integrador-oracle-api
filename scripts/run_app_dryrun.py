import sys
import time
from types import SimpleNamespace

# Garantir que o diretório do projeto esteja no path (para permitir import 'src.*')
import os
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, proj_root)

print("Starting SimpliRoute app in DRY-RUN mode (no external POSTs)")

try:
    # Import e monkeypatch do cliente antes do uvicorn iniciar a app
    from src.integrations.simpliroute import client as sr_client
except Exception as e:
    print("failed to import client:", e)
    raise

async def fake_post_simpliroute(route_payload):
    print("[DRY-RUN] post_simpliroute called with payload sample:", dict(route_payload) if isinstance(route_payload, dict) else "<list>")
    # Simular resposta bem-sucedida
    return SimpleNamespace(status_code=200, text='{"simulated": true}')

# Substituir a função real pelo stub
sr_client.post_simpliroute = fake_post_simpliroute
try:
    # Também sobrescrever a referência já importada no módulo app (caso app tenha feito
    # `from .client import post_simpliroute` antes da nossa monkeypatch)
    from src.integrations.simpliroute import app as sr_app
    sr_app.post_simpliroute = fake_post_simpliroute
except Exception:
    # se não conseguir, seguir em frente — a monkeypatch no client já funciona para
    # imports dinâmicos realizados após este ponto
    pass

import uvicorn

def run_for(seconds: int = 12):
    config = uvicorn.Config("src.integrations.simpliroute.app:app", host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)

    import threading

    t = threading.Thread(target=server.run, daemon=True)
    t.start()

    print(f"Server started in dry-run mode, will run for ~{seconds}s")
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass

    print("Requesting server shutdown...")
    server.should_exit = True
    t.join()
    print("Server stopped.")


if __name__ == "__main__":
    run_for(12)
