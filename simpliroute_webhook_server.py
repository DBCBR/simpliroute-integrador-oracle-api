"""
Servidor de Webhook SimpliRoute — FastAPI
Desenvolvimento simples, direto, legível e humano.
"""


import os
import json
from datetime import datetime, timezone
from datetime import timedelta
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from typing import Any, Dict, Optional
import oracledb
import traceback
import asyncio
from sqlalchemy.ext.asyncio import AsyncEngine


# Utilitário para ler .env
def load_env_file(env_path: Path):
    if not env_path.exists():
        return
    with env_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

# Carrega variáveis do .env
load_env_file(Path("settings/.env"))


# Configurações globais
WEBHOOK_ROUTE = "/"
HEALTH_CHECK_ROUTE = "/health"
ERROR_LOG_DIR = Path("simpliroute_webhook_error_logs")
STRUCTURED_LOG_DIR = Path("logs")
LOG_TO_FILE = False  # Se True, grava logs em arquivo; se False, apenas no console

# Limpa o diretório de erros ao iniciar, se existir
if ERROR_LOG_DIR.exists() and ERROR_LOG_DIR.is_dir():
    for f in ERROR_LOG_DIR.iterdir():
        try:
            if f.is_file() and f.name.startswith("error-"):
                f.unlink()
        except Exception:
            pass
ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)

# --- Monitoramento de eventos e erros ---
from collections import deque

# Armazena os últimos eventos recebidos (payloads)
MAX_EVENTOS = 20
eventos_recebidos = deque(maxlen=MAX_EVENTOS)

# Contadores de erros
erros_total = 0
erros_hoje = 0
data_hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()

# Função para salvar stacktrace de erro detalhado e contabilizar erros
def save_error_stacktrace(exc: Exception, extra_info: dict = None):
    global erros_total, erros_hoje, data_hoje
    dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
    # Atualiza contagem diária
    if dt_utc3.date() != data_hoje:
        data_hoje = dt_utc3.date()
        erros_hoje = 0
    erros_total += 1
    erros_hoje += 1
    timestamp = dt_utc3.isoformat().split('+')[0].replace(':', '-')
    error_dir = ERROR_LOG_DIR
    filename = error_dir / f"error-{timestamp}.txt"
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Timestamp: {dt_utc3.replace(microsecond=0).isoformat()}\n")
        f.write(f"Exception: {type(exc).__name__}: {exc}\n")
        f.write("\nStacktrace:\n")
        f.write(traceback.format_exc())
        if extra_info:
            f.write("\nExtra info:\n")
            f.write(json.dumps(extra_info, ensure_ascii=False, indent=2, default=str))
    return str(filename)

# Configuração do logger estruturado (sem duplicidade)
class JsonFormatter(logging.Formatter):
    def format(self, record):
        # Usa datetime.now(timezone.utc) e ajusta para UTC-3
        dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
        log_record = {
            "timestamp": dt_utc3.isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)

def get_logger():
    logger = logging.getLogger("simpliroute_webhook_server")
    logger.setLevel(logging.INFO)
    if not getattr(logger, "_handler_set", False):
        logger.handlers.clear()
        if LOG_TO_FILE:
            log_file = STRUCTURED_LOG_DIR / "webhook_server.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(JsonFormatter())
            logger.addHandler(file_handler)
            print(f"[INFO] Logs de arquivo serão salvos em: {log_file}")
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.addHandler(stream_handler)
        print(f"[INFO] Logs de terminal serão exibidos no console.")
        logger._handler_set = True
    return logger

logger = get_logger()


# --- Conexão Oracle via SQLAlchemy ---


# --- Engine assíncrono para SQLAlchemy ---
from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine

def build_async_oracle_engine() -> AsyncEngine:
    import platform
    try:
        system = platform.system().lower()
        if system == "windows":
            instantclient_path = os.path.abspath("settings/instantclient/windows/instantclient-basic-windows.x64-23.26.0.0.0/instantclient_23_0")
        else:
            ld_lib_path = os.environ.get("LD_LIBRARY_PATH")
            if ld_lib_path and os.path.isdir(ld_lib_path):
                instantclient_path = ld_lib_path
            else:
                instantclient_path = os.path.abspath("settings/instantclient/linux/instantclient-basic-linux.x64-23.26.0.0.0/")
                if not os.path.isdir(instantclient_path):
                    raise RuntimeError(f"Oracle Instant Client não encontrado em {instantclient_path} e LD_LIBRARY_PATH não está definida corretamente.")
                os.environ['LD_LIBRARY_PATH'] = instantclient_path
        # Ativa modo thick (se necessário) apenas via oracledb.init_oracle_client
        oracledb.init_oracle_client(lib_dir=instantclient_path)
        user = os.getenv("ORACLE_USER")
        password = os.getenv("ORACLE_PASS")
        host = os.getenv("ORACLE_HOST")
        port = os.getenv("ORACLE_PORT", "1521")
        service = os.getenv("ORACLE_SERVICE")
        if not all([user, password, host, port, service]):
            raise RuntimeError("Credenciais Oracle incompletas no .env")
        # DSN correto para SQLAlchemy async com oracledb (NÃO incluir mode=thick nem async_fallback)
        dsn = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
        return create_async_engine(dsn, echo=False, future=True)
    except Exception as exc:
        save_error_stacktrace(exc, extra_info={
            "env": {
                "ORACLE_USER": os.getenv("ORACLE_USER"),
                "ORACLE_HOST": os.getenv("ORACLE_HOST"),
                "ORACLE_PORT": os.getenv("ORACLE_PORT"),
                "ORACLE_SERVICE": os.getenv("ORACLE_SERVICE"),
                "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH"),
            }
        })
        raise

async_engine = build_async_oracle_engine()

# --- engine é variável global e compartilhada para o motor de acesso ao banco ---

async def registrar_payload_oracle(payload: dict, engine: AsyncEngine, logger) -> None:
    """
    Insere um registro da payload na tabela Oracle TD_OTIMIZE_ALTSTAT.
    O campo INFORMACAO recebe o JSON completo.
    """
    try:
        schema = os.getenv("ORACLE_SCHEMA")
        table = os.getenv("ORACLE_TABLE", "TD_OTIMIZE_ALTSTAT")
        def to_int(val):
            try:
                return int(val) if val is not None else None
            except Exception:
                return None
        def get_first(*keys):
            for k in keys:
                v = payload.get(k)
                if v not in (None, ""):
                    return v
            return None
        eventdate = datetime.now(timezone.utc) - timedelta(hours=3)
        tpregistro = None
        tp_val = get_first("tpregistro", "TPREGISTRO")
        try:
            tp_val_int = int(tp_val)
            if tp_val_int in (1, 2):
                tpregistro = tp_val_int
        except Exception:
            pass
        if tpregistro is None:
            visit_type = (payload.get("visit_type") or "").lower()
            if visit_type in ("rota_log", "adm_log", "acr_log", "ret_log", "pad_log", "entrega", "delivery"):
                tpregistro = 2
            elif visit_type in ("med", "medico", "enf", "enfermeiro", "enfermagem"):
                tpregistro = 1
            else:
                tpregistro = 2
        idreference = to_int(get_first("reference"))
        idregistro = None
        if tpregistro == 1:
            idadmission = to_int(get_first("reference"))
        else:
            idadmission = None
            idregistro = str(get_first("reference"))[:6]
        status_str = str(payload.get("status") or "").lower()
        status = None
        informacao = None
        if status_str == "completed":
            status = 5
            informacao = "Entregue"
        elif status_str == "partial":
            status = 4
            informacao = "Entrega parcial"
        elif status_str in ("failed", "cancelled", "canceled", "not_delivered", "undelivered"):
            status = 6
            informacao = "Falha na entrega"
        
        checkout_comment = payload.get("checkout_comment")
        checkout_rota2 = payload.get("extra_field_values", {}).get("checkout_rota2")
        if checkout_comment is None:
            checkout_comment = ""
        if checkout_rota2 is None:
            checkout_rota2 = ""
        obs = checkout_comment + " | " + checkout_rota2
        if obs == " | ":
            obs = None
        insert_sql = f"""
            INSERT INTO {schema}.{table} (IDREFERENCE, EVENTDATE, IDADMISSION, IDREGISTRO, TPREGISTRO, STATUS, INFORMACAO, OBS)
            VALUES (:idreference, :eventdate, :idadmission, :idregistro, :tpregistro, :status, :informacao, :obs)
        """
        params = {
            "idreference": idreference,
            "eventdate": eventdate,
            "idadmission": idadmission,
            "idregistro": idregistro,
            "tpregistro": tpregistro,
            "status": status,
            "informacao": informacao,
            "obs": obs,
        }
        logger.info(json.dumps({"trace": "params para insert", **params}, ensure_ascii=False, default=str))        
        try:
            async with engine.begin() as conn:
                await conn.execute(text(insert_sql), params)
            logger.info(f"Payload registrado no banco Oracle: idreference={idreference} idadmission={idadmission} status={status}")
        except Exception as exc:
            save_error_stacktrace(exc, extra_info={"params": params})
            tb_str = traceback.format_exc()
            logger.error(f"Falha ao inserir payload no banco Oracle: {exc}\nTraceback:\n{tb_str}")
    except Exception as exc:
        save_error_stacktrace(exc, extra_info={"payload": payload})
        logger.error(f"Erro inesperado em registrar_payload_oracle: {exc}")


app = FastAPI(title="SimpliRoute Webhook Server")

# >>>>>> Função principal de recebimento do webhook na rota




@app.post(WEBHOOK_ROUTE)
async def receive_webhook(request: Request):
    import time
    start_time = time.perf_counter()
    try:
        try:
            payload = await request.json()
        except Exception as exc:
            save_error_stacktrace(exc, extra_info={"request_body": await request.body()})
            logger.error(f"Falha ao decodificar JSON: {exc}")
            return JSONResponse({"error": "invalid json"}, status_code=400)

        logger.info(f"Payload recebido:\n{json.dumps(payload, ensure_ascii=False)[:200]}...")

        # Executa rotina principal
        await registrar_payload_oracle(payload, async_engine, logger)

        # Calcula tempo de execução
        elapsed = time.perf_counter() - start_time

        # Adiciona evento ao monitoramento
        eventos_recebidos.appendleft({
            "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
            "payload_preview": json.dumps(payload, ensure_ascii=False)[:200],
            "exec_time_s": round(elapsed, 4)
        })

        return JSONResponse({"status": "received"})
    except Exception as exc:
        save_error_stacktrace(exc)
        logger.error(f"Exceção não controlada em receive_webhook: {exc}")
        return JSONResponse({"error": "internal_server_error"}, status_code=500)


# --- Rota de health check ---
@app.get(HEALTH_CHECK_ROUTE)
async def health_check():
    """
    Retorna informações de saúde do serviço, incluindo últimos eventos e contagem de erros.
    """
    dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
    return JSONResponse({
        "status": "ok",
        "hora_atual": dt_utc3.isoformat(),
        "error_log_dir": str(ERROR_LOG_DIR.resolve()),
        "ultimos_eventos": list(eventos_recebidos),
        "erros": {
            "total": erros_total,
            "hoje": erros_hoje,
        }
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simpliroute_webhook_server:app", host="0.0.0.0", port=8000, reload=False)
