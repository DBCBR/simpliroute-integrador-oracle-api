import os
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


def _load_yaml_config(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        # Config mínima padrão caso o arquivo não exista
        return {
            "log_level": "INFO",
            "log_file": "data/work/run.log",
            "retries": 0,
            "input_dir": "data/input",
            "output_dir": "data/output",
            "seed_items": ["TX-001", "TX-002", "TX-003"],
        }
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data


def load_config() -> Dict[str, Any]:
    """
    Carrega .env (se existir) e o YAML de configuração.
    Retorna um dicionário com defaults seguros se não houver arquivo.
    """
    # Determinar caminhos relativos ao diretório raiz do projeto
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    env_path = os.path.join(base_dir, "settings", ".env")
    if os.path.exists(env_path):
        # carregar .env do diretório settings do projeto (não depender do CWD)
        load_dotenv(env_path, override=False)

    yaml_path = os.path.join(base_dir, "settings", "config.yaml")
    cfg = _load_yaml_config(yaml_path)

    # Mescla sobrescritas via env se desejar (exemplo simples):
    cfg["log_level"] = os.getenv("LOG_LEVEL", cfg.get("log_level", "INFO"))
    cfg["log_file"] = os.getenv("LOG_FILE", cfg.get("log_file", "data/work/run.log"))

    # Expor variáveis relevantes de integração no dicionário de configuração
    cfg.setdefault("integrations", {})
    cfg["integrations"]["simpliroute_api_base"] = os.getenv("SIMPLIROUTE_API_BASE") or cfg.get("simpliroute_api_base")

    return cfg
