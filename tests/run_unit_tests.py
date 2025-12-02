import importlib
import inspect
import sys

def run_module_tests(mod_name: str):
    try:
        mod = importlib.import_module(mod_name)
    except Exception as e:
        print(f"ERROR importing {mod_name}: {e}")
        return 2
    failures = 0
    for name, func in inspect.getmembers(mod, inspect.isfunction):
        if name.startswith("test_"):
            try:
                print(f"RUN {mod_name}.{name}")
                func()
                print(f"OK {mod_name}.{name}")
            except AssertionError as ae:
                import importlib
                import inspect
                import sys


                def run_module_tests(mod_name: str):
                    try:
                        mod = importlib.import_module(mod_name)
                    except Exception as e:
                        print(f"ERROR importing {mod_name}: {e}")
                        return 2
                    failures = 0
                    for name, func in inspect.getmembers(mod, inspect.isfunction):
                        if name.startswith("test_"):
                            try:
                                print(f"RUN {mod_name}.{name}")
                                func()
                                print(f"OK {mod_name}.{name}")
                            except AssertionError as ae:
                                failures += 1
                                print(f"FAIL {mod_name}.{name}: {ae}")
                            except Exception as e:
                                failures += 1
                                print(f"ERROR {mod_name}.{name}: {e}")
                    return failures


                def main():
                    # add project root to sys.path so imports like src.integrations... work
                    sys.path.insert(0, "")
                    # run the fixed test module
                    total_fail = run_module_tests("tests.test_mapper_fixed")
                    if total_fail == 0:
                        print("ALL OK")
                        sys.exit(0)
                    else:
                        print(f"{total_fail} failures")
                        sys.exit(1)


                if __name__ == '__main__':
                    main()
