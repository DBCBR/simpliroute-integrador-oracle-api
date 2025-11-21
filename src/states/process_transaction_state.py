from typing import Any, Dict
# Se/quando sua lógica identificar erro de regra, levante BusinessRuleException:
# from core.exceptions import BusinessRuleException


def process(ctx: Dict[str, Any], tx: Any) -> None:
    """
    Estado Process Transaction:
    - Executa a lógica de negócio para uma transação.
    - Importante: não capturar exceções aqui, para que o main.py
      diferencie BusinessRuleException de outros erros e aplique retry.
    """
    logger = ctx["logger"]

    logger.info(f"Processando transação: {tx}")

    # >>> Coloque aqui a lógica real do seu robô <<<
    # Exemplos de uso:
    # - Para erro de regra de negócio (NÃO retentar):
    #   raise BusinessRuleException("CPF inválido para faturar")
    #
    # - Para erro transitório (retentar):
    #   raise TimeoutError("HTTP 504 ao chamar sistema X")
    #
    # Caso sucesso, não retorne nada e não levante exceção.
    logger.debug(f"Transação {tx} processada com sucesso (exemplo).")
