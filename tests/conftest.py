"""Ajustes de PYTHONPATH para permitir imports de `src` durante os testes.

Este arquivo adiciona a raiz do repositório ao `sys.path` para que
`import src...` funcione quando o pytest executa os testes.
"""
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
# Inserir `src/` na frente do sys.path para que imports como
# `from states.init_state import init` resolvam corretamente
SRC_DIR = ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
# Também inserir a raiz do repositório para habilitar importação do
# pacote `src` (ex.: `from src.main import ...`). Isso cobre ambos os casos
# onde módulos usam `states` (quando `src` é adicionado ao sys.path)
sys.path.insert(1, str(ROOT))
