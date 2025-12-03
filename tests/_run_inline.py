import importlib, inspect, sys
# ensure project root is on sys.path so `tests` package can be imported
sys.path.insert(0, "")
mod = importlib.import_module('tests.test_mapper_fixed')
fail = 0
for name, func in inspect.getmembers(mod, inspect.isfunction):
    if name.startswith('test_'):
        try:
            print('RUN', name)
            func()
            print('OK', name)
        except AssertionError as ae:
            fail += 1
            print('FAIL', name, ae)
        except Exception as e:
            fail += 1
            print('ERROR', name, e)
print('TOTAL FAILURES', fail)
if fail:
    sys.exit(1)
