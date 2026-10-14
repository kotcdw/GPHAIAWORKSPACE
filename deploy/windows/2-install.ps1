# GPHA Internal Audit Workspace - step 2: install dependencies, create the (empty) schema and the first
# administrator, then run the production readiness check.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows\2-install.ps1

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path "$PSScriptRoot\..\..")

if (-not (Test-Path .env)) { Write-Host "No .env - run deploy\windows\1-new-production-env.ps1 first." -ForegroundColor Red; exit 2 }
if (-not (Select-String -Path .env -Pattern "^GPHA_ENVIRONMENT=production" -Quiet)) {
    Write-Host ".env is not a production configuration (GPHA_ENVIRONMENT=production missing)." -ForegroundColor Red; exit 2
}

Write-Host "==> Installing dependencies (no development tools)" -ForegroundColor Cyan
uv sync --no-dev --frozen
if ($LASTEXITCODE -ne 0) { Write-Host "uv sync failed" -ForegroundColor Red; exit 1 }

Write-Host "==> Creating the database schema and the first administrator" -ForegroundColor Cyan
uv run --no-dev python -m scripts.init_db
if ($LASTEXITCODE -ne 0) { Write-Host "Database step failed - check GPHA_DATABASE_URL and that the database exists." -ForegroundColor Red; exit 1 }

New-Item -ItemType Directory -Force -Path logs | Out-Null

Write-Host "==> Production readiness check" -ForegroundColor Cyan
uv run --no-dev python scripts/production_check.py
if ($LASTEXITCODE -ne 0) { Write-Host "Fix the items above, then run this script again." -ForegroundColor Yellow; exit 1 }

Write-Host ""
Write-Host "Installed. Next: deploy\windows\3-install-service.ps1 (runs the app as a Windows service)." -ForegroundColor Green
