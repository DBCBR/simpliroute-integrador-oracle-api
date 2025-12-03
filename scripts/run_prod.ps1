# Script helper PowerShell para infra: build + up (compose)
# Uso: .\scripts\run_prod.ps1

param()

$composeFile = 'docker-compose.prod.yml'

if (Get-Command docker-compose -ErrorAction SilentlyContinue) {
  $cmd = 'docker-compose'
} else {
  $cmd = 'docker compose'
}

Write-Host "Building image using $cmd..."
& $cmd -f $composeFile build --pull --no-cache

Write-Host "Starting services (detached)..."
& $cmd -f $composeFile up -d

Write-Host "Pronto. Para seguir logs: $cmd -f $composeFile logs -f"
Write-Host "Os payloads dry-run serão salvos em ./data/output"
