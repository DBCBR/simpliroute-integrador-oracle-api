from typing import Any, Dict


def init(cfg: Dict[str, Any], logger) -> Dict[str, Any]:
    """
    Estado Init:
    - Carrega/valida pré-requisitos mínimos.
    - Inicializa o contexto compartilhado (cfg, logger, fila simples).
    - Define max_retries a partir de cfg["max_retries"] (default=0).
    """
    logger.info("Init: carregando contexto e preparando fila em memória")

    queue_items = cfg.get("seed_items", ["TX-001", "TX-002", "TX-003"])
    max_retries = int(cfg.get("max_retries", 0) or 0)

    ctx: Dict[str, Any] = {
        "cfg": cfg,
        "logger": logger,
        "queue": list(queue_items),  # lista simples simulando uma fila
        "stats": {"processed": 0, "errors": 0},
        "max_retries": max_retries,
    }
    logger.info(f"Init: max_retries configurado para {max_retries}")
    return ctx
