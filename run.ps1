# GPHA Internal Audit Workspace - start the development server.
# Usage:  .\run.ps1
#
# 1. makes sure Docker Desktop and the MySQL container (gpha-mysql) are running
# 2. installs/updates Python dependencies (uv sync)
# 3. checks the database is reachable and applies pending migrations
# 4. starts the app on http://127.0.0.1:8001
# If the database cannot be reached the server is NOT started, so nobody types
# data into an app that cannot save it.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Native-command stderr must not abort the script (Windows PowerShell 5.1 treats
# redirected stderr as an error when ErrorActionPreference is Stop).
function Test-Docker {
    $ErrorActionPreference = "Continue"
    try { docker info *> $null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}

function Get-MySqlHealth {
    $ErrorActionPreference = "Continue"
    try { return (docker inspect -f "{{.State.Health.Status}}" gpha-mysql 2>$null) } catch { return "unknown" }
}

Write-Host "==> Checking Docker" -ForegroundColor Cyan
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Docker is not installed or not on PATH. Install Docker Desktop, then run .\run.ps1 again." -ForegroundColor Red
    exit 2
}
if (-not (Test-Docker)) {
    $dockerDesktop = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerDesktop) {
        Write-Host "Docker Desktop is not running - starting it (this can take a minute)..." -ForegroundColor Yellow
        Start-Process -FilePath $dockerDesktop | Out-Null
    } else {
        Write-Host "Docker is not running. Start Docker Desktop, then run .\run.ps1 again." -ForegroundColor Red
        exit 2
    }
    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Test-Docker)) {
        if ((Get-Date) -gt $deadline) {
            Write-Host "Docker did not start within 3 minutes. Open Docker Desktop, wait until it says 'Engine running', then run .\run.ps1 again." -ForegroundColor Red
            exit 2
        }
        Start-Sleep -Seconds 3
    }
}

Write-Host "==> Starting the MySQL database (docker compose up -d)" -ForegroundColor Cyan
$ErrorActionPreference = "Continue"
docker compose up -d
$ErrorActionPreference = "Stop"
if ($LASTEXITCODE -ne 0) { Write-Host "Could not start the MySQL container." -ForegroundColor Red; exit 2 }

Write-Host "==> Waiting for MySQL to accept connections" -ForegroundColor Cyan
$deadline = (Get-Date).AddMinutes(2)
do {
    $health = Get-MySqlHealth
    if ($health -eq "healthy") { break }
    if ((Get-Date) -gt $deadline) {
        Write-Host "MySQL is not healthy yet (status: $health). Check: docker compose logs mysql" -ForegroundColor Red
        exit 2
    }
    Start-Sleep -Seconds 2
} while ($true)

Write-Host "==> Syncing dependencies" -ForegroundColor Cyan
uv sync
if ($LASTEXITCODE -ne 0) { Write-Host "uv sync failed" -ForegroundColor Red; exit 1 }

Write-Host "==> Checking database and applying migrations" -ForegroundColor Cyan
uv run python -m scripts.init_db
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "The database is not reachable, so the app was not started." -ForegroundColor Red
    Write-Host "Check: docker compose ps   and   docker compose logs mysql" -ForegroundColor Yellow
    exit 2
}

Write-Host "==> Starting GPHA Internal Audit Workspace on http://127.0.0.1:8001" -ForegroundColor Green
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
