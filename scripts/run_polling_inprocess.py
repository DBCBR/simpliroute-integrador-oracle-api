"""Runner in-process para executar a tarefa de polling real usando Gnexum,
mas sem enviar POSTs ao SimpliRoute (dry-run).

Uso:
  - Para rodar indefinidamente: `python scripts/run_polling_inprocess.py`
  - Para rodar por N segundos e sair: `RUN_DURATION_SECONDS=20 python scripts/run_polling_inprocess.py`

O script injeta um stub assíncrono em `post_simpliroute` para evitar chamadas externas.
"""
import os
import sys
import asyncio
import signal
from types import SimpleNamespace

# Garantir import relativo ao projeto
proj_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, proj_root)

from src.integrations.simpliroute import client as sr_client
from src.integrations.simpliroute.app import polling_task
from src.integrations.simpliroute import app as sr_app
from src.core.config import load_config

# carregar config em tempo de import para controlar persistência
_CFG = load_config()
SAVE_PAYLOADS = bool(_CFG.get("simpliroute", {}).get("save_payloads", True))
SUMMARY_CSV = os.path.join(proj_root, 'data', 'output', 'payloads_summary.csv')


async def fake_post_simpliroute(route_payload):
    # Apenas log curto para inspeção; não faz POST real.
    try:
        preview = route_payload if isinstance(route_payload, dict) else route_payload[0]
        title = preview.get('title') if isinstance(preview, dict) else '<list>'
    except Exception:
        title = '<preview-failed>'
    # salvar payload em data/output/payloads para inspeção (apenas se habilitado)
    try:
        import json, time, re, csv

        # tentar extrair identificador fonte
        sid = None
        try:
            sid = (preview.get('properties') or {}).get('source_ident') if isinstance(preview, dict) else None
        except Exception:
            sid = None
        if not sid:
            sid = preview.get('reference') if isinstance(preview, dict) else None
        if not sid:
            sid = 'noid'

        # sanitize title for filename
        safe_title = re.sub(r"[^a-zA-Z0-9_-]", "-", str(title))[:60]
        fname = f"{int(time.time())}_{sid}_{safe_title}.json"

        if SAVE_PAYLOADS:
            out_dir = os.path.join(proj_root, 'data', 'output', 'payloads')
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, fname)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(route_payload, f, ensure_ascii=False, indent=2)
            print(f"[DRY-RUN] saved payload to {path}")

            # atualizar CSV resumo
            try:
                os.makedirs(os.path.dirname(SUMMARY_CSV), exist_ok=True)
                write_header = not os.path.exists(SUMMARY_CSV)
                with open(SUMMARY_CSV, 'a', encoding='utf-8', newline='') as cf:
                    writer = csv.writer(cf)
                    if write_header:
                        writer.writerow(['ts', 'source_ident', 'title', 'filename', 'status_code'])
                    writer.writerow([int(time.time()), sid, title, fname, 200])
            except Exception as e:
                print('[DRY-RUN] failed to update CSV summary:', e)
        else:
            print('[DRY-RUN] save_payloads disabled by config; skipping file write and CSV')
    except Exception as e:
        print('[DRY-RUN] failed to save payload:', e)
    print(f"[DRY-RUN] Simulated post_simpliroute for title={title}")
    return SimpleNamespace(status_code=200, text='{"simulated": true}')


async def main():
    # injetar stub no módulo client
    # patch client module(s)
    try:
        sr_client.post_simpliroute = fake_post_simpliroute
    except Exception:
        pass

    # Também sobrescrever a referência em possíveis nomes de módulo do app,
    # pois o módulo pode ter sido importado com ou sem o prefixo 'src'.
    import importlib
    for modname in ("src.integrations.simpliroute.app", "integrations.simpliroute.app"):
        try:
            m = importlib.import_module(modname)
            m.post_simpliroute = fake_post_simpliroute
        except Exception:
            pass

    # carregar config para pegar intervalo (fallback para env)
    cfg = load_config()
    # Priority: explicit override for testing -> env RUN_POLLING_INTERVAL_MINUTES -> POLLING_INTERVAL_MINUTES -> config
    interval = None
    try:
        interval = int(os.getenv('RUN_POLLING_INTERVAL_MINUTES') or os.getenv('POLLING_INTERVAL_MINUTES') or cfg.get("simpliroute", {}).get("polling_interval_minutes", 60))
    except Exception:
        interval = 60

    # criar task de polling (usar função importada)
    polling = asyncio.create_task(polling_task(interval))

    # trap Ctrl+C
    stop_event = asyncio.Event()

    def _on_signal(sig, frame=None):
        print(f"Received signal {sig}; shutting down polling task...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, lambda s=s: _on_signal(s))
        except NotImplementedError:
            # Windows asyncio may not support add_signal_handler in some contexts
            pass

    # opcional: rodar apenas por um tempo se variável setada
    run_seconds = int(os.getenv('RUN_DURATION_SECONDS', '0') or 0)
    try:
        if run_seconds > 0:
            print(f"Running polling for {run_seconds}s (dry-run: no SR POSTs). Interval={interval}min")
            await asyncio.wait_for(stop_event.wait(), timeout=run_seconds)
        else:
            print(f"Running polling until interrupted (dry-run). Interval={interval}min")
            await stop_event.wait()
    except asyncio.TimeoutError:
        print("Run duration expired; cancelling polling task...")

    # cancelar e aguardar
    polling.cancel()
    try:
        await polling
    except asyncio.CancelledError:
        pass

    print("Polling stopped. Exiting.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("KeyboardInterrupt received; exiting")
