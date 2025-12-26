import os
import traceback
import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import os
import json
import time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import oracledb
from typing import Any, Dict, List
from collections import OrderedDict
import unicodedata
import re
# --- Funções auxiliares e build_visit_payload extraídas para send_helper.py ---
from send_helper import build_visit_payload

# --- Garante que diretórios de log existem ---
LOG_DIR = Path("simpliroute_send_logs")
STRUCTURED_LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STRUCTURED_LOG_DIR.mkdir(parents=True, exist_ok=True)

SEND_INTERVAL_SECONDS = 60

def get_oracle_view():
    return os.getenv("ORACLE_VIEW_ENTREGAS") or "VWPACIENTES_ENTREGAS"

# Limite de registros por envio
SEND_LIMIT = int(os.getenv("ORACLE_FETCH_LIMIT", "100"))

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

# --- Logger estruturado ---
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
    logger = logging.getLogger("simpliroute_send")
    logger.setLevel(logging.INFO)
    if not getattr(logger, "_handler_set", False):
        log_file = STRUCTURED_LOG_DIR / "simpliroute_send.log"
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(JsonFormatter())
        logger.handlers.clear()
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
        logger._handler_set = True
        print(f"[INFO] Logs de arquivo serão salvos em: {log_file}")
        print(f"[INFO] Logs de terminal serão exibidos no console.")
    return logger

logger = get_logger()

# --- Conexão Oracle via SQLAlchemy (thick client) ---
def build_oracle_engine() -> Engine:
    import platform
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

# --- Função para buscar registros na view Oracle ---
def fetch_records(limit: int, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Busca registros da view Oracle definida, limitando a quantidade e suportando offset.
    """
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
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
        columns = result.keys()
        rows = [dict(zip(columns, row)) for row in result.fetchall()]
    return rows

def update_envioroteirizador(id_prescription, id_protocolo):
    """
    Atualiza a coluna DT_ENVIOROTEIRIZADOR na tabela TD_OTIMIZE_ALTSTAT para o registro correspondente.
    """
    schema = os.getenv("ORACLE_SCHEMA")
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sql = f"""
        UPDATE {schema}.TD_OTIMIZE_ALTSTAT
        SET DT_ENVIOROTEIRIZADOR = TO_DATE(:dt_envio, 'YYYY-MM-DD HH24:MI:SS')
        WHERE IDREGISTRO = :id_prescription AND IDREFERENCE = :id_protocolo
    """
    params = {
        "dt_envio": now_str,
        "id_prescription": id_prescription,
        "id_protocolo": id_protocolo
    }
    with engine.begin() as conn:
        result = conn.execute(text(sql), params)
        if result.rowcount == 0:
            logger.warning(f"Nenhum registro atualizado em TD_OTIMIZE_ALTSTAT para IDREGISTRO={id_prescription} e IDREFERENCE={id_protocolo}")
        else:
            logger.info(f"Atualizado DT_ENVIOROTEIRIZADOR para IDREGISTRO={id_prescription} e IDREFERENCE={id_protocolo}")

# --- Função para enviar payload ao SimpliRoute ---
def send_to_simpliroute(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Envia o payload para o endpoint SimpliRoute.
    """
    import httpx
    base_url = os.getenv("SIMPLIROUTE_API_BASE") or "https://api.simpliroute.com"
    token = os.getenv("SIMPLIROUTE_TOKEN")
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Token {token}"
    url = f"{base_url.rstrip('/')}/v1/routes/visits/"
    try:
        response = httpx.post(url, json=[payload], headers=headers, timeout=30)
        logger.info(f"Enviado para SimpliRoute: HTTP {response.status_code}")
        time.sleep(2)  # evitar rate limiting
        return {"status_code": response.status_code, "body": response.text}
    except Exception as exc:
        logger.error(f"Erro ao enviar para SimpliRoute: {exc}")
        return {"status_code": None, "error": str(exc)}

# --- Loop principal de envio ---
def main_loop():
    logger.info("Iniciando loop de envio para SimpliRoute...")
    offset = 0
    while True:
        logger.info(f"--- INÍCIO DE ENVIO --- (offset={offset})")
        try:
            records = fetch_records(SEND_LIMIT, offset)
            if not records:
                logger.info("Nenhum registro encontrado para envio.")
                offset = 0
                time.sleep(10 * SEND_INTERVAL_SECONDS)
                continue
            offset += len(records)
            for idx, record in enumerate(records, 1):
                logger.info(f"Enviando registro {offset + idx}/{offset + len(records)}: reference={record.get('ID_ATENDIMENTO')}")
                record_upper = {k.upper(): v for k, v in record.items()}
                payload = build_visit_payload(record_upper)
                result = send_to_simpliroute(payload)
                status_code = result.get("status_code")
                if status_code is not None and 200 <= int(status_code) < 300:
                    # Atualiza DT_ENVIOROTEIRIZADOR se envio foi bem-sucedido
                    id_prescription = record.get("id_prescricao")
                    id_protocolo = record.get("id_protocolo")
                    if id_prescription and id_protocolo:
                        update_envioroteirizador(id_prescription, id_protocolo)
                    else:
                        logger.warning(f"Chaves para update não encontradas: IDPRESCRIPTION={id_prescription}, ID_PROTOCOLO={id_protocolo}")
                logger.info(f"Envio concluído {offset + idx}/{offset + len(records)}: reference={record.get('ID_ATENDIMENTO')}")
        except Exception as exc:
            tb_str = traceback.format_exc()
            logger.error(f"Erro no loop de envio: {exc}\nTraceback:\n{tb_str}")
        logger.info("--- FIM DE ENVIO ---")
        # Se chegou ao fim, reinicia offset
        if not records or len(records) < SEND_LIMIT:
            offset = 0
        time.sleep(SEND_INTERVAL_SECONDS)

if __name__ == "__main__":
    main_loop()
