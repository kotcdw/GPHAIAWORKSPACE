# GPHA INTERNAL AUDIT WORKSPACE - step 3: run the app as a Windows service (starts with the server,
# restarts itself after a failure). Uses NSSM (https://nssm.cc - a single nssm.exe).
#
# Run in an ADMINISTRATOR PowerShell:
#   powershell -ExecutionPolicy Bypass -File deploy\windows\3-install-service.ps1 -Nssm C:\tools\nssm\win64\nssm.exe
#
# The app listens on 127.0.0.1:8001 only; users reach it through Apache (Laragon) or Caddy over HTTPS.

param(
    [Parameter(Mandatory = $true)][string]$Nssm,
    [string]$ServiceName = "GPHA-Audit",
    [int]$Port = 8001
)
$ErrorActionPreference = "Stop"
$app = (Resolve-Path "$PSScriptRoot\..\..").Path

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Run this in an Administrator PowerShell." -ForegroundColor Red; exit 2
}
if (-not (Test-Path $Nssm)) { Write-Host "nssm.exe not found at $Nssm" -ForegroundColor Red; exit 2 }
$uv = (Get-Command uv -ErrorAction Stop).Source

# The full path to uv is used, so the service does not depend on a user profile PATH.
New-Item -ItemType Directory -Force -Path "$app\logs" | Out-Null

& $Nssm stop $ServiceName 2>$null | Out-Null
& $Nssm remove $ServiceName confirm 2>$null | Out-Null

& $Nssm install $ServiceName $uv "run --no-dev uvicorn app.main:app --host 127.0.0.1 --port $Port --proxy-headers --forwarded-allow-ips 127.0.0.1 --no-server-header"
& $Nssm set $ServiceName AppDirectory $app
& $Nssm set $ServiceName DisplayName "GPHA INTERNAL AUDIT WORKSPACE"
& $Nssm set $ServiceName Description "GPHA INTERNAL AUDIT WORKSPACE (FastAPI on 127.0.0.1:$Port)"
& $Nssm set $ServiceName Start SERVICE_AUTO_START
& $Nssm set $ServiceName AppStdout "$app\logs\service.log"
& $Nssm set $ServiceName AppStderr "$app\logs\service.log"
& $Nssm set $ServiceName AppRotateFiles 1
& $Nssm set $ServiceName AppRotateBytes 10485760
& $Nssm set $ServiceName AppExit Default Restart
& $Nssm set $ServiceName AppRestartDelay 5000
& $Nssm set $ServiceName AppEnvironmentExtra "UV_CACHE_DIR=$app\.uv-cache"
& $Nssm start $ServiceName

Start-Sleep -Seconds 8
try {
    $h = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 10
    Write-Host "Service running: $($h.status), database revision $($h.database.revision)" -ForegroundColor Green
} catch {
    Write-Host "The service did not answer yet. Look at $app\logs\service.log" -ForegroundColor Yellow
}
Write-Host "Next: HTTPS front end - deploy\laragon\gpha-audit.conf (Apache) or deploy\Caddyfile." -ForegroundColor Cyan
