FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instala dependências
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copia o projeto
COPY . /app

EXPOSE 8000

# Comando padrão para iniciar o serviço
CMD ["uvicorn", "src.integrations.simpliroute.app:app", "--host", "0.0.0.0", "--port", "8000"]
