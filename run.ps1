# GPHA Internal Audit Workspace - start the development server.
# Usage:  .\run.ps1            (only this PC can open the app)
#         .\run.ps1 -Lan       (team test: colleagues on the office network can open it;
#                               same as .\run-lan.ps1)
#         .\run.ps1 -External Cloudflare | Tailscale
#                              (testers outside the office; same as .\run-external.ps1)
#
# 1. makes sure Docker Desktop and the MySQL container (gpha-mysql) are running
# 2. installs/updates Python dependencies (uv sync)
# 3. checks the database is reachable and applies pending migrations
# 4. starts the app on http://127.0.0.1:8001
# If the database cannot be reached the server is NOT started, so nobody types
# data into an app that cannot save it.

param(
    [switch]$Lan,
    [ValidateSet("", "Cloudflare", "Tailscale")]
    [string]$External = "",
    [string]$TunnelName = "",
    [string]$Hostname = "",
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

if (-not $Lan -and -not $External) {
    Write-Host "==> Starting GPHA Internal Audit Workspace on http://127.0.0.1:$Port" -ForegroundColor Green
    uv run uvicorn app.main:app --reload --host 127.0.0.1 --port $Port
    exit $LASTEXITCODE
}

# ---------------------------------------------------------------------------
# Testers outside the office (-External Cloudflare | Tailscale)
# ---------------------------------------------------------------------------
# The app itself only listens on 127.0.0.1; the tunnel carries HTTPS traffic to it, so no
# firewall port or router change is needed. Stops when this window is closed or Ctrl+C is pressed.

function Find-Tool([string]$Name, [string[]]$Candidates) {
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($c in $Candidates) { if ($c -and (Test-Path $c)) { return $c } }
    return $null
}

function Install-Tool([string]$WingetId, [string]$Label, [string]$Url) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host "$Label is not installed. Install it from $Url, then run this again." -ForegroundColor Red
        exit 2
    }
    $answer = Read-Host "$Label is not installed. Install it now with winget? (Y/N)"
    if ($answer -notmatch "^[Yy]") {
        Write-Host "Not installed. Install $Label from $Url, then run this again." -ForegroundColor Red
        exit 2
    }
    $ErrorActionPreference = "Continue"
    winget install --id $WingetId -e
    $ErrorActionPreference = "Stop"
}

if ($External) {
    Write-Host "==> Checking accounts before sharing outside the office" -ForegroundColor Cyan
    uv run python -m scripts.share_check
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not shared. Fix the accounts listed above (anyone on the internet will see the sign-in page)." -ForegroundColor Red
        exit 2
    }

    $tunnel = $null
    $ts = $null
    $url = $null

    if ($External -eq "Cloudflare") {
        $cfCandidates = @("$env:ProgramFiles\cloudflared\cloudflared.exe", "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe")
        $cf = Find-Tool "cloudflared" $cfCandidates
        if (-not $cf) {
            Install-Tool "Cloudflare.cloudflared" "cloudflared (Cloudflare Tunnel)" "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
            $cf = Find-Tool "cloudflared" $cfCandidates
            if (-not $cf) { Write-Host "cloudflared was installed. Close this window, open a new PowerShell and run this again." -ForegroundColor Yellow; exit 2 }
        }
        $log = Join-Path $env:TEMP "giaw-cloudflared.log"
        $out = Join-Path $env:TEMP "giaw-cloudflared.out"
        Remove-Item $log, $out -ErrorAction SilentlyContinue
        if ($TunnelName) {
            if (-not $Hostname) { Write-Host "With -TunnelName also give -Hostname (for example giaw-test.example.com)." -ForegroundColor Red; exit 2 }
            $cfArgs = @("tunnel", "--no-autoupdate", "run", "--url", "http://127.0.0.1:$Port", $TunnelName)
            $url = "https://$Hostname"
            $ready = "Registered tunnel connection"
        } else {
            $cfArgs = @("tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:$Port")
            $ready = "https://[a-z0-9-]+\.trycloudflare\.com"
        }
        Write-Host "==> Opening the Cloudflare tunnel" -ForegroundColor Cyan
        $tunnel = Start-Process -FilePath $cf -ArgumentList $cfArgs -PassThru -WindowStyle Hidden `
            -RedirectStandardError $log -RedirectStandardOutput $out
        $deadline = (Get-Date).AddSeconds(60)
        $found = $false
        while (-not $found) {
            if ($tunnel.HasExited) {
                Write-Host "The tunnel stopped. Last messages:" -ForegroundColor Red
                Get-Content $log -Tail 15 -ErrorAction SilentlyContinue
                exit 2
            }
            $files = @($log, $out) | Where-Object { Test-Path $_ }
            $m = if ($files) { Select-String -Path $files -Pattern $ready | Select-Object -First 1 } else { $null }
            if ($m) {
                $found = $true
                if (-not $TunnelName) { $url = $m.Matches[0].Value }
            } elseif ((Get-Date) -gt $deadline) {
                Write-Host "The tunnel did not come up within 60 seconds. Log: $log" -ForegroundColor Red
                Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
                exit 2
            } else { Start-Sleep -Seconds 1 }
        }
    } else {
        $ts = Find-Tool "tailscale" @("$env:ProgramFiles\Tailscale\tailscale.exe")
        if (-not $ts) {
            Install-Tool "Tailscale.Tailscale" "Tailscale" "https://tailscale.com/download/windows"
            $ts = Find-Tool "tailscale" @("$env:ProgramFiles\Tailscale\tailscale.exe")
            if (-not $ts) { Write-Host "Tailscale was installed. Close this window, open a new PowerShell and run this again." -ForegroundColor Yellow; exit 2 }
        }
        $ErrorActionPreference = "Continue"
        $status = (& $ts status --json 2>$null | Out-String) | ConvertFrom-Json -ErrorAction SilentlyContinue
        if (-not $status -or $status.BackendState -ne "Running") {
            Write-Host "Sign in to Tailscale in the browser window that opens..." -ForegroundColor Yellow
            & $ts up
            $status = (& $ts status --json 2>$null | Out-String) | ConvertFrom-Json -ErrorAction SilentlyContinue
        }
        if (-not $status -or $status.BackendState -ne "Running") {
            Write-Host "Tailscale is not connected. Open the Tailscale app, sign in, then run this again." -ForegroundColor Red
            exit 2
        }
        $dns = "$($status.Self.DNSName)".TrimEnd(".")
        Write-Host "==> Sharing over Tailscale (HTTPS)" -ForegroundColor Cyan
        & $ts serve --bg "http://127.0.0.1:$Port"
        $serveOk = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = "Stop"
        if (-not $serveOk -or -not $dns) {
            Write-Host "Tailscale could not share the app over HTTPS." -ForegroundColor Red
            Write-Host "In the Tailscale admin console (login.tailscale.com > DNS) turn on MagicDNS and HTTPS Certificates, then run this again." -ForegroundColor Yellow
            exit 2
        }
        $url = "https://$dns"
    }

    $env:GPHA_APP_BASE_URL = $url
    $env:GPHA_COOKIE_SECURE = "true"   # the link is HTTPS
    $env:GPHA_API_DOCS = "false"       # no public API map while shared

    Write-Host ""
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host "  GIAW is shared outside the office ($External)" -ForegroundColor Green
    Write-Host "  Testers open:   $url" -ForegroundColor Green
    if ($External -eq "Tailscale") {
        Write-Host "  Only people in your Tailscale network can open it. Invite testers at" -ForegroundColor Green
        Write-Host "  login.tailscale.com > Users > Invite users (they install Tailscale and sign in)." -ForegroundColor Green
    } elseif (-not $TunnelName) {
        Write-Host "  This link changes every time you start sharing; send the new one each time." -ForegroundColor Yellow
    }
    Write-Host "  On this PC:     http://127.0.0.1:$Port" -ForegroundColor Green
    Write-Host "  Stop sharing:   press Ctrl+C in this window (or close it)" -ForegroundColor Green
    Write-Host "  Demo / test data only. Every tester signs in with their own account." -ForegroundColor Yellow
    Write-Host "  Keep this PC awake and online while people are testing." -ForegroundColor Yellow
    Write-Host "==================================================================" -ForegroundColor Green
    Write-Host ""

    try {
        uv run uvicorn app.main:app --host 127.0.0.1 --port $Port --proxy-headers --forwarded-allow-ips 127.0.0.1
    } finally {
        if ($tunnel -and -not $tunnel.HasExited) { Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue }
        if ($ts) { $ErrorActionPreference = "Continue"; & $ts serve reset 2>$null | Out-Null }
        Write-Host "Sharing stopped." -ForegroundColor Yellow
    }
    exit 0
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
