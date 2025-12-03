#!/usr/bin/env bash
set -euo pipefail

# Script helper para infra: build + up (compose)
# Uso: ./scripts/run_prod.sh

COMPOSE_FILE="docker-compose.prod.yml"

if command -v docker-compose >/dev/null 2>&1; then
  DOCKER_COMPOSE_CMD="docker-compose"
else
  DOCKER_COMPOSE_CMD="docker compose"
fi

echo "Building image using $DOCKER_COMPOSE_CMD..."
$DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" build --pull --no-cache

echo "Starting services (detached)..."
$DOCKER_COMPOSE_CMD -f "$COMPOSE_FILE" up -d

echo "To follow logs: $DOCKER_COMPOSE_CMD -f $COMPOSE_FILE logs -f"

echo "Ready. Dry-run payloads will be written to ./data/output"
