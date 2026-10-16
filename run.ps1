# GPHA Internal Audit Workspace - start the development server.
# Usage:  .\run.ps1            (only this PC can open the app)
#         .\run.ps1 -Lan       (team test: colleagues on the office network can open it;
#                               same as .\run-lan.ps1)
#
# 1. makes sure Docker Desktop and the MySQL container (gpha-mysql) are running
# 2. installs/updates Python dependencies (uv sync)
# 3. checks the database is reachable and applies pending migrations
# 4. starts the app on http://127.0.0.1:8001
# If the database cannot be reached the server is NOT started, so nobody types
# data into an app that cannot save it.

param(
    [switch]$Lan,
    [int]$Port = 8001
)

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

if (-not $Lan) {
    Write-Host "==> Starting GPHA Internal Audit Workspace on http://127.0.0.1:$Port" -ForegroundColor Green
    uv run uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# Team test on the office network (-Lan)
# ---------------------------------------------------------------------------
# Plain HTTP, no encryption: use demo / test data only, never real GPHA audit files.

Write-Host "==> Finding this PC's network address" -ForegroundColor Cyan
$ip = $null
try {
    $cfg = Get-NetIPConfiguration -ErrorAction Stop |
        Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq "Up" -and $_.InterfaceAlias -notmatch "vEthernet|WSL|Docker|VirtualBox|VMware|Loopback" } |
        Select-Object -First 1
    if ($cfg) { $ip = ($cfg.IPv4Address | Select-Object -First 1).IPAddress }
} catch { }
if (-not $ip) {
    Write-Host "Could not find a network address. Is this PC connected to the office network or Wi-Fi?" -ForegroundColor Red
    exit 2
}

# The firewall rule below covers Domain and Private networks only.
try {
    $profileName = (Get-NetConnectionProfile -InterfaceAlias $cfg.InterfaceAlias -ErrorAction Stop).NetworkCategory
    if ("$profileName" -eq "Public") {
        Write-Host "This network is set to 'Public' in Windows, so colleagues will be blocked." -ForegroundColor Yellow
        Write-Host "Ask IT, or set it to Private: Settings > Network & internet > (your connection) > Private network." -ForegroundColor Yellow
    }
} catch { }

Write-Host "==> Checking Windows Firewall for port $Port" -ForegroundColor Cyan
$ruleName = "GIAW team test (TCP $Port)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    $ruleCmd = "New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -Profile Domain,Private | Out-Null"
    $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    if ($isAdmin) {
        Invoke-Expression $ruleCmd
    } else {
        Write-Host "Windows will ask for administrator approval once, to open port $Port for the office network." -ForegroundColor Yellow
        try {
            Start-Process powershell -Verb RunAs -Wait -ArgumentList "-NoProfile -Command $ruleCmd"
        } catch {
            Write-Host "Approval was not given. Colleagues will not be able to connect until port $Port is allowed." -ForegroundColor Red
        }
    }
    if (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue) {
        Write-Host "Firewall rule '$ruleName' added (Domain and Private networks only)." -ForegroundColor Green
    }
} else {
    Write-Host "Firewall rule '$ruleName' already present." -ForegroundColor Green
}

# Links in e-mails must point at this PC, not at 127.0.0.1 (this overrides .env for this run only).
$url = "http://${ip}:$Port"
$env:GPHA_APP_BASE_URL = $url

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "  GIAW team test is starting" -ForegroundColor Green
Write-Host "  Colleagues open:   $url" -ForegroundColor Green
Write-Host "  On this PC:        http://127.0.0.1:$Port" -ForegroundColor Green
Write-Host "  Stop:              press Ctrl+C in this window" -ForegroundColor Green
Write-Host "  Demo / test data only - this link is not encrypted (HTTP)." -ForegroundColor Yellow
Write-Host "  Keep this PC awake and on the network while people are testing." -ForegroundColor Yellow
Write-Host "==================================================================" -ForegroundColor Green
Write-Host ""

uv run uvicorn app.main:app --host 0.0.0.0 --port $Port
exit $LASTEXITCODE
