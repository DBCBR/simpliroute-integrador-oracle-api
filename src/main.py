"""
Entrypoint do RPA Template (inspirado no REFramework):
Init -> Get Transaction -> Process -> End

Regra de retry:
- BusinessRuleException => não retenta.
- Outras exceções => retenta até n vezes (cfg["retries"], default=0).
"""

from states.init_state import init
from states.get_transaction_state import get_next
from states.process_transaction_state import process
from states.end_state import finalize
from core.logging_setup import setup_logging
from core.config import load_config
from core.exceptions import BusinessRuleException


def main():
    cfg = load_config()
    logger = setup_logging(cfg)
    ctx = init(cfg, logger)

    max_retries = int(ctx.get("max_retries", 0))

    # Loop principal: busca transações e processa até não haver mais
    while True:
        tx = get_next(ctx)
        if tx is None:
            break

        attempt = 0
        while True:
            try:
                logger.info(f"Process: iniciando (tentativa {attempt + 1}/{max_retries + 1}) para {tx}")
                process(ctx, tx)
                # sucesso
                ctx["stats"]["processed"] += 1
                break
            except BusinessRuleException as bre:
                # não retenta em erro de regra de negócio
                ctx["stats"]["errors"] += 1
                logger.warning(f"BusinessRuleException em {tx}: {bre}. Não será feita retentativa.")
                break
            except Exception as ex:
                if attempt < max_retries:
                    attempt += 1
                    logger.warning(
                        f"Falha em {tx} (tentativa {attempt}/{max_retries + 1}). "
                        f"Mensagem: {ex}. Retentando..."
                    )
                    continue
                # excedeu tentativas
                ctx["stats"]["errors"] += 1
                logger.exception(
                    f"Falha definitiva em {tx} após {max_retries + 1} tentativa(s): {ex}"
                )
                break

    finalize(ctx)


if __name__ == "__main__":
    main()
