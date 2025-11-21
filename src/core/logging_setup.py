import logging
import os
from typing import Any, Dict


def setup_logging(cfg: Dict[str, Any]) -> logging.Logger:
    """
    Configuração simples de logging:
    - Console + arquivo em data/work/run.log (padrão).
    - Nível configurável por config.yaml ou env.
    """
    os.makedirs("data/work", exist_ok=True)
    logfile = cfg.get("log_file", "data/work/run.log")
    level = cfg.get("log_level", "INFO")

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(logfile, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    return logging.getLogger("rpa_template")
