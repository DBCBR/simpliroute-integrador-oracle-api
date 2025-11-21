"""Ajustes de PYTHONPATH para permitir imports de `src` durante os testes.

Este arquivo adiciona a raiz do repositório ao `sys.path` para que
`import src...` funcione quando o pytest executa os testes.
"""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
# Adiciona a pasta `src` ao PYTHONPATH para que imports como
# `from states.init_state import ...` funcionem durante os testes.
SRC_DIR = ROOT / "src"
# Inserir a raiz do repositório e também a pasta `src` para cobrir
# ambos os estilos de import usados nos testes e no código:
# - `import src.main` (requere ROOT no PYTHONPATH)
# - `from states.init_state import ...` (requere SRC_DIR no PYTHONPATH)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SRC_DIR))
