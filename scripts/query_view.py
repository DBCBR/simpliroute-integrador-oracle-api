import os
import oracledb
from dotenv import load_dotenv

# carregar variáveis de settings/.env quando rodando no container
load_dotenv('/app/settings/.env')
import traceback

instant = os.getenv('ORACLE_INSTANT_CLIENT','/opt/oracle/instantclient')
try:
    oracledb.init_oracle_client(lib_dir=instant)
except Exception as e:
    print('init failed', e)

host = os.getenv('ORACLE_HOST')
port = int(os.getenv('ORACLE_PORT','1521'))
service = os.getenv('ORACLE_SERVICE')
user = os.getenv('ORACLE_USER')
password = os.getenv('ORACLE_PASS')
schema = os.getenv('ORACLE_SCHEMA')
view = os.getenv('ORACLE_VIEW')

print('connecting to', host, service, 'user', user, 'schema', schema, 'view', view)

dsn = oracledb.makedsn(host, port, service_name=service)
try:
    conn = oracledb.connect(user=user, password=password, dsn=dsn)
    cur = conn.cursor()
    sql = f"SELECT * FROM {schema}.{view} WHERE ROWNUM <= 1"
    print('SQL:', sql)
    cur.execute(sql)
    colnames = [c[0] for c in cur.description]
    print('columns:', colnames)
    row = cur.fetchone()
    print('row:', row)
    cur.close()
    conn.close()
except Exception as e:
    print('query failed', e)
    traceback.print_exc()
