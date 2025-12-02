import importlib
try:
    m = importlib.import_module('oracledb')
    print('oracledb version', getattr(m, '__version__', 'unknown'))
except Exception as e:
    print('import error:', e)
