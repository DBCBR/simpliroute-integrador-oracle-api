def test_import_main():
    import importlib

    # Garante que o pacote importa sem erros
    importlib.import_module("src.main".replace("/", "."))
    assert True
