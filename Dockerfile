FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar curl (usado pelo docker healthcheck) e dependências do sistema
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates unzip libaio-dev libaio1t64 \
    && rm -rf /var/lib/apt/lists/*
# Some distributions provide libaio as libaio.so or libaio.so.1t64; ensure libaio.so.1 exists
RUN if [ -f /lib/x86_64-linux-gnu/libaio.so.1t64 ] && [ ! -f /lib/x86_64-linux-gnu/libaio.so.1 ]; then \
            ln -s /lib/x86_64-linux-gnu/libaio.so.1t64 /lib/x86_64-linux-gnu/libaio.so.1 || true; \
        fi

# Instala dependências Python
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copia o projeto
COPY . /app

# Copia Instant Client zip (se presente) e o instala em /opt/oracle/instantclient
# Espera-se que o usuário coloque os arquivos zip Linux em settings/instantclient/linux/
RUN if [ -d "/app/settings/instantclient/linux" ]; then \
            echo "Found settings/instantclient/linux, installing..."; \
            ls -la /app/settings/instantclient/linux; \
            mkdir -p /opt/oracle; \
            for z in /app/settings/instantclient/linux/*.zip; do \
                if [ -f "$z" ]; then \
                    unzip -q "$z" -d /opt; \
                fi; \
            done; \
            # move the extracted instantclient_* folder to a consistent path
            for d in /opt/instantclient_* /opt/instantclient* /opt/instantclient_*/; do \
                if [ -d "$d" ]; then \
                    mv "$d" /opt/oracle/instantclient || true; \
                    break; \
                fi; \
            done; \
            if [ -d "/opt/oracle/instantclient" ]; then \
                echo "Instant Client installed at /opt/oracle/instantclient"; \
            else \
                echo "No Instant Client found in settings/instantclient"; \
            fi; \
        fi

# Expose Instant Client lib location to the runtime via env
ENV ORACLE_INSTANT_CLIENT=/opt/oracle/instantclient
ENV LD_LIBRARY_PATH=/opt/oracle/instantclient:$LD_LIBRARY_PATH

# Comando padrão: executa o modo automático que, por padrão, envia os dados ao SimpliRoute
CMD ["python", "-m", "src.cli.send_to_simpliroute", "auto"]
