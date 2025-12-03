import oracledb
import traceback

print('oracledb version:', getattr(oracledb, '__version__', 'n/a'))

try:
    oracledb.init_oracle_client(lib_dir='/opt/oracle/instantclient')
    print('init_oracle_client: success')
except Exception as e:
    print('init_oracle_client: failed', e)
    traceback.print_exc()

try:
    print('clientversion:', oracledb.clientversion())
except Exception as e:
    print('clientversion: failed', e)
    traceback.print_exc()

# Check shared libs exist
import os
ic = '/opt/oracle/instantclient'
print('instantclient exists:', os.path.isdir(ic))
if os.path.isdir(ic):
    print('files:')
    for f in os.listdir(ic):
        if f.startswith('libclntsh') or f.startswith('libclntshcore') or f.startswith('libocci'):
            print(' -', f)
