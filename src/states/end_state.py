from typing import Any, Dict


def finalize(ctx: Dict[str, Any]) -> None:
    """
    Estado End Process:
    - Emite resumo final e libera recursos (se houver).
    """
    logger = ctx["logger"]
    stats = ctx.get("stats", {})
    logger.info("Encerrando execução do robô")
    logger.info(
        f"Resumo: processadas={stats.get('processed', 0)} "
        f"erros={stats.get('errors', 0)} pendentes={len(ctx.get('queue', []))}"
    )
