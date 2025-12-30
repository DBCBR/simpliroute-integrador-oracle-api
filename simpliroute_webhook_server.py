"""
Servidor de Webhook SimpliRoute — FastAPI (SÍNCRONO + Oracle THICK MODE)
- Mantém THICK MODE (Instant Client obrigatório)
- Usa SQLAlchemy síncrono (create_engine)
- Endpoint síncrono (FastAPI executa em threadpool automaticamente)
- Logging estruturado + health + stacktrace em arquivo
"""

import os
import json
import time
import logging
import traceback
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque
from typing import Any, Dict, Optional

import oracledb
from fastapi import FastAPI, Body
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


# ---------------------------
# Utilitário para ler .env
# ---------------------------
def load_env_file(env_path: Path) -> None:
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


# ---------------------------
# Configurações globais
# ---------------------------
WEBHOOK_ROUTE = "/"
HEALTH_CHECK_ROUTE = "/health_webhook"
ERROR_LOG_DIR = Path("simpliroute_webhook_error_logs")
STRUCTURED_LOG_DIR = Path("logs")
LOG_TO_FILE = False  # True = grava logs em arquivo JSON; False = apenas console


# Limite de arquivos de erro mantidos
MAX_ERROR_FILES = 50
# Lista global dos nomes dos arquivos de erro (ordenados do mais novo para o mais antigo)
error_files = []

ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Inicializa error_files com os arquivos já existentes (ordenados do mais novo para o mais antigo)
existing = sorted([f for f in ERROR_LOG_DIR.iterdir() if f.is_file() and f.name.startswith("error-")], reverse=True)
error_files.extend([str(f) for f in existing[:MAX_ERROR_FILES]])
# Remove arquivos antigos excedentes
for f in existing[MAX_ERROR_FILES:]:
    try:
        f.unlink()
    except Exception:
        pass


# ---------------------------
# Monitoramento
# ---------------------------
MAX_EVENTOS = 20
eventos_recebidos = deque(maxlen=MAX_EVENTOS)

erros_total = 0
erros_hoje = 0
data_hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def utc3_now() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=3)


def save_error_stacktrace(exc: Exception, extra_info: Optional[dict] = None) -> str:
    global erros_total, erros_hoje, data_hoje, error_files

    dt_utc3 = utc3_now()

    # Atualiza contagem diária
    if dt_utc3.date() != data_hoje:
        data_hoje = dt_utc3.date()
        erros_hoje = 0

    erros_total += 1
    erros_hoje += 1

    timestamp = dt_utc3.isoformat().split("+")[0].replace(":", "-")
    filename = ERROR_LOG_DIR / f"error-{timestamp}.txt"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"Timestamp: {dt_utc3.replace(microsecond=0).isoformat()}\n")
        f.write(f"Exception: {type(exc).__name__}: {exc}\n")
        f.write("\nStacktrace:\n")
        f.write(traceback.format_exc())
        if extra_info:
            f.write("\nExtra info:\n")
            f.write(json.dumps(extra_info, ensure_ascii=False, indent=2, default=str))

    # Atualiza lista global de arquivos
    error_files.insert(0, str(filename))
    if len(error_files) > MAX_ERROR_FILES:
        # Remove o mais antigo
        to_remove = error_files.pop()
        try:
            os.remove(to_remove)
        except Exception:
            pass

    return str(filename)


# ---------------------------
# Logger estruturado
# ---------------------------
class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        dt_utc3 = utc3_now()
        log_record = {
            "timestamp": dt_utc3.isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_record, ensure_ascii=False)


def get_logger() -> logging.Logger:
    logger = logging.getLogger("simpliroute_webhook_server")
    logger.setLevel(logging.INFO)

    if not getattr(logger, "_handler_set", False):
        logger.handlers.clear()

        if LOG_TO_FILE:
            log_file = STRUCTURED_LOG_DIR / "webhook_server.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(JsonFormatter())
            logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.addHandler(stream_handler)

        logger._handler_set = True

    return logger


logger = get_logger()


# ---------------------------
# Oracle THICK MODE + Engine síncrono
# ---------------------------
def init_oracle_thick_mode() -> None:
    """
    Inicializa o Instant Client (THICK MODE) UMA ÚNICA VEZ.
    """
    import platform

    system = platform.system().lower()

    if system == "windows":
        instantclient_path = os.path.abspath(
            "settings/instantclient/windows/instantclient-basic-windows.x64-23.26.0.0.0/instantclient_23_0"
        )
    else:
        ld_lib_path = os.environ.get("LD_LIBRARY_PATH")
        if ld_lib_path and os.path.isdir(ld_lib_path):
            instantclient_path = ld_lib_path
        else:
            instantclient_path = os.path.abspath(
                "settings/instantclient/linux/instantclient-basic-linux.x64-23.26.0.0.0/"
            )
            if not os.path.isdir(instantclient_path):
                raise RuntimeError(
                    f"Oracle Instant Client não encontrado em {instantclient_path} e LD_LIBRARY_PATH não está definida corretamente."
                )
            os.environ["LD_LIBRARY_PATH"] = instantclient_path

    # Ativa THICK MODE. Não misture com thin mode!
    oracledb.init_oracle_client(lib_dir=instantclient_path)


def build_oracle_engine() -> Engine:
    """
    Cria engine síncrono (SQLAlchemy) usando python-oracledb em THICK MODE.
    """
    try:
        init_oracle_thick_mode()

        user = os.getenv("ORACLE_USER")
        password = os.getenv("ORACLE_PASS")
        host = os.getenv("ORACLE_HOST")
        port = os.getenv("ORACLE_PORT", "1521")
        service = os.getenv("ORACLE_SERVICE")

        if not all([user, password, host, port, service]):
            raise RuntimeError("Credenciais Oracle incompletas no .env")

        # DSN para SQLAlchemy síncrono
        dsn = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"

        # pool_pre_ping ajuda a evitar conexões mortas em ambientes long-running
        engine = create_engine(
            dsn,
            future=True,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=1800,  # recicla conexões (opcional)
        )
        return engine

    except Exception as exc:
        save_error_stacktrace(
            exc,
            extra_info={
                "env": {
                    "ORACLE_USER": os.getenv("ORACLE_USER"),
                    "ORACLE_HOST": os.getenv("ORACLE_HOST"),
                    "ORACLE_PORT": os.getenv("ORACLE_PORT"),
                    "ORACLE_SERVICE": os.getenv("ORACLE_SERVICE"),
                    "ORACLE_SCHEMA": os.getenv("ORACLE_SCHEMA"),
                    "ORACLE_TABLE": os.getenv("ORACLE_TABLE"),
                    "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH"),
                }
            },
        )
        raise


engine = build_oracle_engine()


# ---------------------------
# Persistência (SÍNCRONA)
# ---------------------------
def registrar_payload_oracle(payload: Dict[str, Any], engine: Engine, logger: logging.Logger) -> None:
    """
    Insere um registro da payload na tabela Oracle TD_OTIMIZE_ALTSTAT.
    """
    try:
        schema = (os.getenv("ORACLE_SCHEMA") or "").strip()
        table = (os.getenv("ORACLE_TABLE") or "TD_OTIMIZE_ALTSTAT").strip()

        full_table = f"{schema}.{table}" if schema else table

        def to_int(val: Any) -> Optional[int]:
            try:
                return int(val) if val is not None else None
            except Exception:
                return None

        def get_first(*keys: str) -> Any:
            for k in keys:
                v = payload.get(k)
                if v not in (None, ""):
                    return v
            return None

        eventdate = utc3_now()

        # tpregistro
        tpregistro: Optional[int] = None
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

        # idreference / idadmission / idregistro
        idreference = to_int(get_first("reference"))
        idregistro: Optional[str] = None

        if tpregistro == 1:
            idadmission = to_int(get_first("reference"))
        else:
            idadmission = None
            idregistro = str(get_first("reference"))[:6] if get_first("reference") is not None else None

        # status / informacao
        status_str = str(payload.get("status") or "").lower()
        status: Optional[int] = None
        informacao: Optional[str] = None

        if status_str == "completed":
            status = 5
            informacao = "Entregue"
        elif status_str == "partial":
            status = 4
            informacao = "Entrega parcial"
        elif status_str in ("failed", "cancelled", "canceled", "not_delivered", "undelivered"):
            status = 6
            informacao = "Falha na entrega"

        # obs
        checkout_comment = payload.get("checkout_comment") or ""
        checkout_rota2 = (payload.get("extra_field_values") or {}).get("checkout_rota2") or ""
        obs = f"{checkout_comment} | {checkout_rota2}"
        if obs == " | ":
            obs = None

        insert_sql = f"""
            INSERT INTO {full_table}
                (IDREFERENCE, EVENTDATE, IDADMISSION, IDREGISTRO, TPREGISTRO, STATUS, INFORMACAO, OBS)
            VALUES
                (:idreference, :eventdate, :idadmission, :idregistro, :tpregistro, :status, :informacao, :obs)
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
            # begin() faz commit automático ao sair sem erro
            with engine.begin() as conn:
                conn.execute(text(insert_sql), params)

            logger.info(
                f"Payload registrado no banco Oracle: idreference={idreference} idadmission={idadmission} status={status}"
            )

        except Exception as exc:
            save_error_stacktrace(exc, extra_info={"params": params, "table": full_table})
            tb_str = traceback.format_exc()
            logger.error(f"Falha ao inserir payload no banco Oracle: {exc}\nTraceback:\n{tb_str}")

    except Exception as exc:
        save_error_stacktrace(exc, extra_info={"payload": payload})
        logger.error(f"Erro inesperado em registrar_payload_oracle: {exc}")


# ---------------------------
# App FastAPI
# ---------------------------
app = FastAPI(title="SimpliRoute Webhook Server (Sync + Thick Mode)")


@app.post(WEBHOOK_ROUTE)
def receive_webhook(payload: Dict[str, Any] = Body(...)):
    start_time = time.perf_counter()
    try:
        logger.info(f"Payload recebido:\n{json.dumps(payload, ensure_ascii=False)[:200]}...")

        # rotina principal (SÍNCRONA)
        registrar_payload_oracle(payload, engine, logger)

        elapsed = time.perf_counter() - start_time

        eventos_recebidos.appendleft(
            {
                "timestamp": utc3_now().isoformat(),
                "payload_preview": json.dumps(payload, ensure_ascii=False)[:200],
                "exec_time_s": round(elapsed, 4),
            }
        )

        return JSONResponse({"status": "received"})

    except Exception as exc:
        save_error_stacktrace(exc, extra_info={"payload_preview": json.dumps(payload, ensure_ascii=False)[:200]})
        logger.error(f"Exceção não controlada em receive_webhook: {exc}")
        return JSONResponse({"error": "internal_server_error"}, status_code=500)


@app.get(HEALTH_CHECK_ROUTE)
def health_check():
    dt_utc3 = utc3_now()
    return JSONResponse(
        {
            "status": "ok",
            "hora_atual": dt_utc3.isoformat(),
            "error_log_dir": str(ERROR_LOG_DIR.resolve()),
            "ultimos_eventos": list(eventos_recebidos),
            "erros": {
                "total": erros_total,
                "hoje": erros_hoje,
            },
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("simpliroute_webhook_server:app", host="0.0.0.0", port=8000, reload=False)
