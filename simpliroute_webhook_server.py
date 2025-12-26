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
# Forçar thick mode do Oracle
import oracledb
import traceback


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
WEBHOOK_LOG_DIR = Path("simpliroute_webhook_logs")
STRUCTURED_LOG_DIR = Path("logs")

# Garante que os diretórios existem
WEBHOOK_LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)

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
        log_file = STRUCTURED_LOG_DIR / "webhook_server.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger._handler_set = True
        # Prints informativos sobre onde os logs serão salvos
        print(f"[INFO] Logs de arquivo serão salvos em: {log_file}")
        print(f"[INFO] Logs de terminal serão exibidos no console.")
    return logger

logger = get_logger()


# --- Conexão Oracle via SQLAlchemy ---

def build_oracle_engine() -> Engine:
    import platform
    system = platform.system().lower()
    if system == "windows":
        instantclient_path = os.path.abspath("settings/instantclient/windows/instantclient-basic-windows.x64-23.26.0.0.0/instantclient_23_0")
    else:
        # Se LD_LIBRARY_PATH já estiver definida, use-a diretamente
        ld_lib_path = os.environ.get("LD_LIBRARY_PATH")
        if ld_lib_path and os.path.isdir(ld_lib_path):
            instantclient_path = ld_lib_path
        else:
            # Caminho padrão esperado
            instantclient_path = os.path.abspath("settings/instantclient/linux/instantclient-basic-linux.x64-23.26.0.0.0/")
            if not os.path.isdir(instantclient_path):
                raise RuntimeError(f"Oracle Instant Client não encontrado em {instantclient_path} e LD_LIBRARY_PATH não está definida corretamente.")
            os.environ['LD_LIBRARY_PATH'] = instantclient_path
            
    oracledb.init_oracle_client(lib_dir=instantclient_path)

    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASS")
    host = os.getenv("ORACLE_HOST")
    port = os.getenv("ORACLE_PORT", "1521")
    service = os.getenv("ORACLE_SERVICE")
    if not all([user, password, host, port, service]):
        raise RuntimeError("Credenciais Oracle incompletas no .env")
    dsn = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
    return create_engine(dsn, echo=False, future=True)

engine = build_oracle_engine()

# --- engine é variável global e compartilhada para o motor de acesso ao banco ---

def registrar_payload_oracle(payload: dict, engine: Engine, logger) -> None:
    """
    Insere um registro da payload na tabela Oracle TD_OTIMIZE_ALTSTAT.
    O campo INFORMACAO recebe o JSON completo.
    """
    schema = os.getenv("ORACLE_SCHEMA")
    table = os.getenv("ORACLE_TABLE", "TD_OTIMIZE_ALTSTAT")
    # Mapeamento básico
    def to_int(val):
        try:
            return int(val) if val is not None else None
        except Exception:
            return None

    # Mapeamento detalhado conforme regras do mapper.py
    def get_first(*keys):
        for k in keys:
            v = payload.get(k)
            if v not in (None, ""):
                return v
        return None

    # EVENTDATE: sempre data/hora atuais (UTC-3)
    eventdate = datetime.now(timezone.utc) - timedelta(hours=3)

    # TPREGISTRO: usar se existir e for 1 ou 2, senão inferir por visit_type
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
            tpregistro = 2  # default entrega
            
    #
    # O id reference é sempre o campo do JSON "reference"
    # O id admission é igual ao reference se tpregistro=1 (visita), caso contrário é nulo
    # O id registro é os 6 primeiros caracteres do reference se tpregistro=2 (entrega), caso contrário é nulo. Isso corresponde ao ID PRESCRICAO
    #
    idreference = to_int(get_first("reference"))
    idregistro = None
    if tpregistro == 1: # Visita
        idadmission = to_int(get_first("reference"))
    else: # Entrega
        idadmission = None
        idregistro = str(get_first("reference"))[:6]

    # STATUS: completed=5, partial=4, failed/cancelled/canceled/not_delivered/undelivered=6
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
    
    obs = checkout_comment + " | " + checkout_rota2

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
    try:
        with engine.begin() as conn:
            conn.execute(text(insert_sql), params)
        logger.info(f"Payload registrado no banco Oracle: idreference={idreference} idadmission={idadmission} status={status}")
    except Exception as exc:
        tb_str = traceback.format_exc()
        logger.error(f"Falha ao inserir payload no banco Oracle: {exc}\nTraceback:\n{tb_str}")


app = FastAPI(title="SimpliRoute Webhook Server")

# >>>>>> Função principal de recebimento do webhook na rota

@app.post(WEBHOOK_ROUTE)
async def receive_webhook(request: Request):
    try:
        try:
            payload = await request.json()
        except Exception as exc:
            logger.error(f"Falha ao decodificar JSON: {exc}")
            return JSONResponse({"error": "invalid json"}, status_code=400)

        # Salva o payload em arquivo com nome ISO8601
        now = (datetime.now(timezone.utc) - timedelta(hours=3)).replace(microsecond=0).isoformat().replace(":", "-")
        filename = WEBHOOK_LOG_DIR / f"webhook_{now}.json"
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            logger.info(f"Payload salvo em {filename}")
        except Exception as exc:
            logger.error(f"Falha ao salvar payload: {exc}")
            return JSONResponse({"error": "io_failure"}, status_code=500)

        # Log estruturado
        logger.info(json.dumps({
            "event": "webhook_received",
            "filename": str(filename),
            "payload_preview": str(payload)[:200]
        }, ensure_ascii=False))

        # Registra no banco Oracle
        try:
            registrar_payload_oracle(payload, engine, logger)
        except Exception as exc:
            logger.error(f"Falha ao registrar payload no banco Oracle: {exc}")

        return JSONResponse({"status": "received", "logged": str(filename)})
    except Exception as exc:
        tb_str = traceback.format_exc()
        logger.error(f"Exceção não controlada em receive_webhook: {exc}\nTraceback:\n{tb_str}")
        return JSONResponse({"error": "internal_server_error"}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("simpliroute_webhook_server:app", host="0.0.0.0", port=8000, reload=False)
