import os
import logging
from typing import Any, Dict, List
import asyncio

logger = logging.getLogger(__name__)


def _blocking_fetch(record_id: Any = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    try:
        import oracledb
    except Exception as e:
        logger.error('Oracle driver not installed: %s', e)
        return []

    host = os.getenv('ORACLE_HOST')
    port = int(os.getenv('ORACLE_PORT', '1521'))
    service = os.getenv('ORACLE_SERVICE')
    user = os.getenv('ORACLE_USER')
    password = os.getenv('ORACLE_PASS')
    schema = os.getenv('ORACLE_SCHEMA')
    view = os.getenv('ORACLE_VIEW')
    instant = os.getenv('ORACLE_INSTANT_CLIENT')

    if instant:
        try:
            oracledb.init_oracle_client(lib_dir=instant)
        except Exception:
            # may already be initialized or client not available
            pass

    if not (host and service and user and password and view):
        logger.error('Oracle connection details incomplete in env')
        return []

    dsn = oracledb.makedsn(host, port, service_name=service)
    conn = None
    try:
        conn = oracledb.connect(user=user, password=password, dsn=dsn)
        cur = conn.cursor()

        cols = '*'
        # Build query: when record_id provided, filter by it; otherwise use offset/limit pagination
        params = {}
        if record_id is not None:
            params['rid'] = int(record_id)
            sql = f"SELECT {cols} FROM {schema}.{view} WHERE (ID_ATENDIMENTO = :rid OR IDREGISTRO = :rid OR ID = :rid)"
            cur.execute(sql, params)
        else:
            # Use OFFSET .. FETCH NEXT .. ROWS ONLY (Oracle 12c+). Fallback to ROWNUM if not supported.
            try:
                sql = f"SELECT {cols} FROM {schema}.{view} OFFSET :off ROWS FETCH NEXT :lim ROWS ONLY"
                params = {'off': int(offset), 'lim': int(limit)}
                cur.execute(sql, params)
            except Exception:
                # Fallback using ROWNUM with subquery
                sql = (
                    f"SELECT * FROM (SELECT a.*, ROWNUM rnum FROM (SELECT {cols} FROM {schema}.{view}) a "
                    f"WHERE ROWNUM <= :maxrow) WHERE rnum > :minrow"
                )
                params = {'maxrow': int(offset + limit), 'minrow': int(offset)}
                cur.execute(sql, params)
        colnames = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            obj = {}
            for k, v in zip(colnames, row):
                # convert to native python types
                try:
                    if hasattr(v, 'isoformat'):
                        obj[k] = v.isoformat()
                    else:
                        obj[k] = v
                except Exception:
                    obj[k] = v
            out.append(obj)

        cur.close()
        return out
    except Exception as e:
        logger.exception('Oracle DB fetch error: %s', e)
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


async def fetch_items_for_record_db(record_id: Any = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _blocking_fetch, record_id, limit, offset)
