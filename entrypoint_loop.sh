#!/bin/sh

# Script para executar o SIMPLIROUTE_AUTO_COMMAND a cada 1 hora

while true; do
    echo "[Entrypoint] Executando: python -m src.cli.send_to_simpliroute auto"
    python -m src.cli.send_to_simpliroute auto
    echo "[Entrypoint] Aguardando 1 hora para próxima execução..."
    sleep 3600
done
