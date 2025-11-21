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
    env_path = os.path.join("settings", ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    yaml_path = os.path.join("settings", "config.yaml")
    cfg = _load_yaml_config(yaml_path)

    # Mescla sobrescritas via env se desejar (exemplo simples):
    cfg["log_level"] = os.getenv("LOG_LEVEL", cfg.get("log_level", "INFO"))
    cfg["log_file"] = os.getenv("LOG_FILE", cfg.get("log_file", "data/work/run.log"))

    return cfg
