from typing import Any, Dict, Optional


def get_next(ctx: Dict[str, Any]) -> Optional[Any]:
    """
    Estado Get Transaction Data:
    - Obtém próxima transação da fila.
    - Retorna None quando não houver mais.
    """
    q = ctx["queue"]
    tx = q.pop(0) if q else None
    if tx is not None:
        ctx["logger"].info(f"GetTransaction: próxima transação -> {tx}")
    else:
        ctx["logger"].info("GetTransaction: nenhuma transação restante")
    return tx
