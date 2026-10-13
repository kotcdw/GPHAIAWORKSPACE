# GPHA Audit Workspace - start the development server.
# Usage:  .\run.ps1
#
# 1. installs/updates Python dependencies (uv sync)
# 2. checks the database is reachable and applies pending migrations
# 3. starts the app on http://127.0.0.1:8001
# If step 2 fails the server is NOT started, so nobody types data into an
# app that cannot save it.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

Write-Host "==> Syncing dependencies" -ForegroundColor Cyan
uv sync
if ($LASTEXITCODE -ne 0) { Write-Host "uv sync failed" -ForegroundColor Red; exit 1 }

Write-Host "==> Checking database and applying migrations" -ForegroundColor Cyan
uv run python -m scripts.init_db
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "The database is not reachable, so the app was not started." -ForegroundColor Red
    Write-Host "Start MySQL with:  docker compose up -d   (then run .\run.ps1 again)" -ForegroundColor Yellow
    exit 2
}

Write-Host "==> Starting GPHA Audit Workspace on http://127.0.0.1:8001" -ForegroundColor Green
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
