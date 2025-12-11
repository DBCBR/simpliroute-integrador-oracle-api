import json
import os
from pathlib import Path

import oracledb
from dotenv import load_dotenv


def _init_oracle_client() -> None:
    lib_dir = os.getenv("ORACLE_INSTANT_CLIENT")
    candidates = []
    if lib_dir:
        candidates.append(Path(lib_dir))
    candidates.append(Path(__file__).resolve().parents[1] / "settings" / "instantclient_23_0")
    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                oracledb.init_oracle_client(lib_dir=str(candidate))
                return
            except oracledb.Error:
                continue


def main(limit: int = 10) -> None:
    base_dir = Path(__file__).resolve().parents[1]
    env_path = base_dir / "settings" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    _init_oracle_client()

    host = os.getenv("ORACLE_HOST")
    port = int(os.getenv("ORACLE_PORT", "1521"))
    service = os.getenv("ORACLE_SERVICE")
    user = os.getenv("ORACLE_USER")
    password = os.getenv("ORACLE_PASS")
    table = os.getenv("SIMPLIROUTE_TARGET_TABLE", "TD_OTIMIZE_ALTSTAT")

    if not all([host, service, user, password]):
        raise RuntimeError("Variáveis de conexão Oracle faltando. Verifique settings/.env")

    dsn = oracledb.makedsn(host, port, service_name=service)
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        with conn.cursor() as cur:
            query = f"""
                SELECT IDREFERENCE,
                       TO_CHAR(EVENTDATE, 'YYYY-MM-DD HH24:MI:SS') AS EVENTDATE,
                       STATUS,
                       SUBSTR(INFORMACAO, 1, 400) AS INFORMACAO_SNIPPET
                  FROM {table}
                 ORDER BY EVENTDATE DESC
                 FETCH FIRST :limit ROWS ONLY
            """
            cur.execute(query, limit=int(limit))
            rows = cur.fetchall()
            headers = [desc[0] for desc in cur.description]

    payload = [dict(zip(headers, row)) for row in rows]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Mostra os últimos payloads persistidos na tabela de status")
    parser.add_argument("--limit", type=int, default=10, help="Quantidade de linhas (default=10)")
    args = parser.parse_args()
    main(limit=args.limit)
