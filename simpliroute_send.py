import json
import logging
import os
import platform
import sys
import time
import traceback
import threading
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import oracledb
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from send_helper import build_visit_payload

# =========================
# Config / Diretórios
# =========================

SEND_INTERVAL_SECONDS = 60
SEND_LIMIT = int(os.getenv("ORACLE_FETCH_LIMIT", "100"))
LOG_TO_FILE = False

HEALTH_CHECK_ROUTE = "/health_send"

ERROR_LOG_DIR = Path("simpliroute_send_error_logs")
STRUCTURED_LOG_DIR = Path("logs")
ERROR_LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)


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


load_env_file(Path("settings/.env"))


def get_oracle_view() -> str:
    return os.getenv("ORACLE_VIEW_ENTREGAS") or "VWPACIENTES_ENTREGAS"


# =========================
# Logger
# =========================

class JsonFormatter(logging.Formatter):
    def format(self, record):
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


def get_logger() -> logging.Logger:
    logger = logging.getLogger("simpliroute_send")
    logger.setLevel(logging.INFO)
    if not getattr(logger, "_handler_set", False):
        logger.handlers.clear()

        if LOG_TO_FILE:
            log_file = STRUCTURED_LOG_DIR / "simpliroute_send.log"
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(JsonFormatter())
            logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.addHandler(stream_handler)

        logger._handler_set = True
    return logger


logger = get_logger()

# =========================
# Estado global monitorado
# =========================

MAX_EVENTOS = 20
eventos_enviados = deque(maxlen=MAX_EVENTOS)
eventos_lock = threading.Lock()

stats_lock = threading.Lock()
erros_total = 0
erros_hoje = 0
envios_total = 0
envios_hoje = 0
falhas_atualizacao_total = 0
falhas_atualizacao_hoje = 0
data_hoje = (datetime.now(timezone.utc) - timedelta(hours=3)).date()


def _rollover_day_if_needed(now_utc3: datetime) -> None:
    global data_hoje, erros_hoje, envios_hoje, falhas_atualizacao_hoje
    if now_utc3.date() != data_hoje:
        data_hoje = now_utc3.date()
        erros_hoje = 0
        envios_hoje = 0
        falhas_atualizacao_hoje = 0


def save_error_stacktrace(exc: Exception, extra_info: dict | None = None) -> str:
    global erros_total, erros_hoje, error_files
    dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)

    with stats_lock:
        _rollover_day_if_needed(dt_utc3)
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


# =========================
# Oracle Engine (lazy + seguro)
# =========================

_engine_lock = threading.Lock()
_engine: Optional[Engine] = None


def _init_oracle_client_once() -> None:
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

    try:
        oracledb.init_oracle_client(lib_dir=instantclient_path)
    except Exception as e:
        # Evita quebrar se já inicializou (varia conforme versão/driver)
        msg = str(e).lower()
        if "already" in msg and "initialized" in msg:
            return
        raise


def build_oracle_engine() -> Engine:
    _init_oracle_client_once()

    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASS")
    host = os.getenv("ORACLE_HOST")
    port = os.getenv("ORACLE_PORT", "1521")
    service = os.getenv("ORACLE_SERVICE")

    if not all([user, password, host, port, service]):
        raise RuntimeError("Credenciais Oracle incompletas no .env")

    dsn = f"oracle+oracledb://{user}:{password}@{host}:{port}/?service_name={service}"
    return create_engine(dsn, echo=False, future=True)


def get_engine() -> Engine:
    global _engine
    with _engine_lock:
        if _engine is None:
            try:
                _engine = build_oracle_engine()
            except Exception as exc:
                save_error_stacktrace(
                    exc,
                    extra_info={
                        "env": {
                            "ORACLE_USER": os.getenv("ORACLE_USER"),
                            "ORACLE_HOST": os.getenv("ORACLE_HOST"),
                            "ORACLE_PORT": os.getenv("ORACLE_PORT"),
                            "ORACLE_SERVICE": os.getenv("ORACLE_SERVICE"),
                            "LD_LIBRARY_PATH": os.environ.get("LD_LIBRARY_PATH"),
                        }
                    },
                )
                raise
        return _engine


# =========================
# DB / HTTP
# =========================

def fetch_records(limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        schema = os.getenv("ORACLE_SCHEMA")
        view = get_oracle_view()

        sql = f"""
            SELECT * FROM (
                SELECT a.*, ROWNUM rnum FROM (
                    SELECT * FROM {schema}.{view}
                    WHERE (
                        DT_ENTREGA = TO_CHAR(SYSDATE, 'YYYY-MM-DD')
                        OR DT_ENTREGA = TO_CHAR(SYSDATE + 1, 'YYYY-MM-DD')
                    )
                    AND DT_ENVIOROTEIRIZADOR IS NULL
                    ORDER BY DT_ENTREGA DESC
                ) a WHERE ROWNUM <= :max_row
            ) WHERE rnum > :offset
        """

        params = {"max_row": offset + limit, "offset": offset}
        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text(sql), params)
            columns = result.keys()
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        return rows
    except Exception as exc:
        save_error_stacktrace(
            exc,
            extra_info={
                "limit": limit,
                "offset": offset,
                "env": {"ORACLE_SCHEMA": os.getenv("ORACLE_SCHEMA")},
            },
        )
        raise


def update_envioroteirizador(id_prescription, id_protocolo, id_simpliroute) -> None:
    global envios_total, envios_hoje

    # Calcula data/hora atual em UTC-3
    now_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
    now_str = now_utc3.strftime("%Y-%m-%d %H:%M:%S")
    try:
        schema = os.getenv("ORACLE_SCHEMA")
        
        sql = f"""
            UPDATE {schema}.TD_OTIMIZE_ALTSTAT
            SET DT_ENVIOROTEIRIZADOR = TO_DATE(:dt_envio, 'YYYY-MM-DD HH24:MI:SS'),
                IDSIMPLIROUTE = :id_simpliroute
            WHERE IDREGISTRO = :id_prescription
              AND IDREFERENCE = :id_protocolo
              AND IDSIMPLIROUTE IS NOT NULL
        """
        
        params = {
            "dt_envio": now_str,
            "id_prescription": id_prescription,
            "id_protocolo": id_protocolo,
            "id_simpliroute": id_simpliroute,
        }

        engine = get_engine()
        with engine.begin() as conn:
            result = conn.execute(text(sql), params)

        if result.rowcount == 0:
            error_msg = (
                f"Nenhum registro atualizado em TD_OTIMIZE_ALTSTAT para IDREGISTRO={id_prescription}, "
                f"IDREFERENCE={id_protocolo}, IDSIMPLIROUTE={id_simpliroute}"
            )
            logger.error(error_msg)
            
            # Incrementa contador de falhas de atualização
            dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
            with stats_lock:
                _rollover_day_if_needed(dt_utc3)
                falhas_atualizacao_total += 1
                falhas_atualizacao_hoje += 1
            
            # Gera arquivo de log de erro
            save_error_stacktrace(
                Exception(error_msg),
                extra_info={
                    "id_prescription": id_prescription,
                    "id_protocolo": id_protocolo,
                    "id_simpliroute": id_simpliroute,
                    "tipo": "update_nao_afetou_registros",
                    "env": {"ORACLE_SCHEMA": schema},
                },
            )
            return

        logger.info(
            f"Atualizado DT_ENVIOROTEIRIZADOR e IDSIMPLIROUTE para IDREGISTRO={id_prescription}, IDREFERENCE={id_protocolo}, IDSIMPLIROUTE={id_simpliroute}"
        )

        dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)
        with stats_lock:
            _rollover_day_if_needed(dt_utc3)
            envios_total += 1
            envios_hoje += 1

    except Exception as exc:
        save_error_stacktrace(
            exc,
            extra_info={
                "id_prescription": id_prescription,
                "id_protocolo": id_protocolo,
                "dt_envio": now_str,
                "env": {"ORACLE_SCHEMA": os.getenv("ORACLE_SCHEMA")},
            },
        )
        raise


def send_to_simpliroute(payload: Dict[str, Any]) -> Dict[str, Any]:
    import httpx

    base_url = os.getenv("SIMPLIROUTE_API_BASE") or "https://api.simpliroute.com"
    token = os.getenv("SIMPLIROUTE_TOKEN") or "b9f38f3d5d85763de9d76dc0f063ea987497d354"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Token {token}"

    url = f"{base_url.rstrip('/')}/v1/routes/visits/"
    logger.info(f"Tentando enviar para SimpliRoute com token {token[:4]}...{token[-4:]}")
    try:
        response = httpx.post(url, json=[payload], headers=headers, timeout=30)
        logger.info(f"Enviado para SimpliRoute: HTTP {response.status_code}")
        time.sleep(2)  # evitar rate limiting
        return {"status_code": response.status_code, "body": response.text}
    except Exception as exc:
        save_error_stacktrace(exc, extra_info={"payload": payload, "url": url})
        logger.error(f"Erro ao enviar para SimpliRoute: {exc}")
        return {"status_code": None, "error": str(exc)}


# =========================
# Loop principal
# =========================

def main_loop(stop_event: threading.Event) -> None:
    logger.info("Iniciando loop de envio para SimpliRoute...")
    offset = 0

    while not stop_event.is_set():
        records: List[Dict[str, Any]] = []
        logger.info(f"--- INÍCIO DE ENVIO --- (offset={offset})")

        try:
            records = fetch_records(SEND_LIMIT, offset)

            if not records:
                logger.info("Nenhum registro encontrado para envio. Resetando offset e aguardando.")
                offset = 0
                # dorme mais quando não tem nada
                stop_event.wait(10 * SEND_INTERVAL_SECONDS)
                continue

            # Avança offset “paginando” a fonte atual
            offset += len(records)

            for idx, record in enumerate(records, 1):
                if stop_event.is_set():
                    break

                start_time = time.perf_counter()
                reference = record.get("ID_ATENDIMENTO") or record.get("id_atendimento")
                logger.info(f"Enviando registro {idx}/{len(records)}: reference={reference}")

                # Normaliza chaves para build_visit_payload
                record_upper = {str(k).upper(): v for k, v in record.items()}

                try:
                    payload = build_visit_payload(record_upper)
                except Exception as exc:
                    save_error_stacktrace(exc, extra_info={"record": record})
                    logger.error(f"Erro ao montar payload para registro reference={reference}")
                    continue

                result = send_to_simpliroute(payload)
                status_code = result.get("status_code")

                if status_code is not None and 200 <= int(status_code) < 300:
                    # Atualiza DT_ENVIOROTEIRIZADOR se envio foi bem-sucedido
                    id_prescription = record.get("id_prescricao") or record.get("ID_PRESCRICAO")
                    id_protocolo = record.get("id_protocolo") or record.get("ID_PROTOCOLO")
                    id_simpliroute = "123"

                    if id_prescription and id_protocolo:
                        update_envioroteirizador(id_prescription, id_protocolo, id_simpliroute)
                    else:
                        logger.warning(
                            f"Chaves para update não encontradas: IDPRESCRIPTION={id_prescription}, ID_PROTOCOLO={id_protocolo}"
                        )

                    elapsed = time.perf_counter() - start_time
                    with eventos_lock:
                        eventos_enviados.appendleft(
                            {
                                "timestamp": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
                                "payload_preview": json.dumps(payload, ensure_ascii=False)[:200],
                                "exec_time_s": round(elapsed, 4),
                                "reference": reference,
                            }
                        )

                logger.info(f"Envio concluído: reference={reference}")

        except Exception as exc:
            save_error_stacktrace(exc, extra_info={"offset": offset})
            logger.error(f"Erro no loop de envio: {exc}\nTraceback:\n{traceback.format_exc()}")

        logger.info("--- FIM DE ENVIO ---")

        # Se chegou ao fim da “página”, reinicia offset
        if not records or len(records) < SEND_LIMIT:
            offset = 0

        stop_event.wait(SEND_INTERVAL_SECONDS)


# =========================
# FastAPI com lifespan (startup/shutdown)
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = threading.Event()
    app.state.stop_event = stop_event

    t = threading.Thread(target=main_loop, args=(stop_event,), daemon=True)
    app.state.worker_thread = t
    t.start()

    try:
        yield
    finally:
        stop_event.set()
        # opcional: join curto para fechar “limpo”
        t.join(timeout=5)


app = FastAPI(title="SimpliRoute Send Health Server", lifespan=lifespan)


@app.get(HEALTH_CHECK_ROUTE)
async def health_check():
    dt_utc3 = datetime.now(timezone.utc) - timedelta(hours=3)

    with eventos_lock:
        ultimos_eventos = list(eventos_enviados)

    with stats_lock:
        env_total = envios_total
        env_h = envios_hoje
        err_total = erros_total
        err_h = erros_hoje
        falhas_atualizacao_t = falhas_atualizacao_total
        falhas_atualizacao_h = falhas_atualizacao_hoje

    return JSONResponse(
        {
            "status": "ok",
            "hora_atual": dt_utc3.isoformat(),
            "error_log_dir": str(ERROR_LOG_DIR.resolve()),
            "ultimos_eventos": ultimos_eventos,
            "envios": {"total": env_total, "hoje": env_h},
            "erros": {"total": err_total, "hoje": err_h},
            "falhas_atualizacao_registro": {"total": falhas_atualizacao_t, "hoje": falhas_atualizacao_h},
        }
    )


# =========================
# Entrada (opcional)
# =========================

if __name__ == "__main__":
    # IMPORTANTE: passe o objeto app, NÃO "simpliroute_send:app"
    uvicorn.run(app, host="0.0.0.0", port=8001, reload=False)
