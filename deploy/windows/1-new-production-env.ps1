# GPHA Internal Audit Workspace - step 1: create the production .env on the PRODUCTION server.
#
# Run from the application folder:   powershell -ExecutionPolicy Bypass -File deploy\windows\1-new-production-env.ps1
#
# - Generates the secret key and the encryption key on this machine (they never leave it).
# - Asks for the database account, the first administrator and the folders for data and backups.
# - Writes .env with GPHA_ENVIRONMENT=production. An existing .env is kept as .env.bak-<date>.
# Nothing is sent anywhere. Passwords are typed into hidden prompts.

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Resolve-Path "$PSScriptRoot\..\..")

function Ask([string]$label, [string]$default = "") {
    $suffix = if ($default) { " [$default]" } else { "" }
    $v = Read-Host "$label$suffix"
    if ([string]::IsNullOrWhiteSpace($v)) { return $default } else { return $v.Trim() }
}

function AskSecret([string]$label, [int]$minLength = 1) {
    while ($true) {
        $a = Read-Host "$label" -AsSecureString
        $b = Read-Host "Repeat $label" -AsSecureString
        $pa = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($a))
        $pb = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($b))
        if ($pa -ne $pb) { Write-Host "  They do not match - try again." -ForegroundColor Yellow; continue }
        if ($pa.Length -lt $minLength) { Write-Host "  Use at least $minLength characters." -ForegroundColor Yellow; continue }
        return $pa
    }
}

Write-Host ""
Write-Host "GPHA Internal Audit Workspace - production configuration" -ForegroundColor Cyan
Write-Host "Press Enter to accept a [default]." -ForegroundColor DarkGray
Write-Host ""

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv is not installed. Install it first: https://docs.astral.sh/uv/" -ForegroundColor Red; exit 2
}

# --- web address ---------------------------------------------------------------
$hostName = Ask "Server name users will type (e.g. audit.gpha.gov.gh)" "audit.gpha.gov.gh"

# --- database ------------------------------------------------------------------
Write-Host "`nDatabase (create it first with deploy\mysql\create-production-database.sql)" -ForegroundColor Cyan
$dbHost = Ask "MySQL host" "127.0.0.1"
$dbPort = Ask "MySQL port" "3306"
$dbName = Ask "Database name" "gpha_audit"
$dbUser = Ask "Database account" "gpha_app"
$dbPass = AskSecret "Database account password"
$dsn = "mysql+pymysql://{0}:{1}@{2}:{3}/{4}?charset=utf8mb4" -f `
    [uri]::EscapeDataString($dbUser), [uri]::EscapeDataString($dbPass), $dbHost, $dbPort, $dbName

# --- folders -------------------------------------------------------------------
Write-Host "`nFolders (keep them OUTSIDE the application folder)" -ForegroundColor Cyan
$uploadDir = Ask "Encrypted working papers and evidence" "C:\GPHA-Data\uploads"
$backupDir = Ask "Encrypted database backups (ideally a different disk or a network share)" "D:\GPHA-Backups"
foreach ($d in @($uploadDir, $backupDir)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }

# --- first administrator ---------------------------------------------------------
Write-Host "`nFirst Platform Administrator (change or add people in the app afterwards)" -ForegroundColor Cyan
$adminUser = Ask "Username" "gpha.admin"
$adminEmail = Ask "E-mail" "internal.audit@gpha.gov.gh"
$adminName = Ask "Full name" "GPHA Platform Administrator"
$adminPass = AskSecret "Administrator password (12+ characters)" 12
if ($adminPass -eq "Admin@12345") { Write-Host "That is the published default password - choose another." -ForegroundColor Red; exit 2 }

# --- e-mail (optional) -----------------------------------------------------------
Write-Host "`nE-mail relay for reminders and escalations (Enter to skip; the in-app bell always works)" -ForegroundColor Cyan
$smtpHost = Ask "SMTP server" ""
$smtpPort = "25"; $smtpFrom = ""; $smtpTls = "false"; $smtpUser = ""; $smtpPass = ""
if ($smtpHost) {
    $smtpPort = Ask "SMTP port" "25"
    $smtpFrom = Ask "Sender address" "internal.audit@gpha.gov.gh"
    $smtpTls = Ask "Use STARTTLS (true/false)" "false"
    $smtpUser = Ask "SMTP account (Enter if none)" ""
    if ($smtpUser) { $smtpPass = AskSecret "SMTP password" }
}

# --- secrets generated locally ------------------------------------------------
Write-Host "`nGenerating keys on this machine..." -ForegroundColor Cyan
$secret = (uv run --no-dev python -c "import secrets; print(secrets.token_urlsafe(48))").Trim()
$encKey = (uv run --no-dev python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").Trim()
if ($secret.Length -lt 32 -or $encKey.Length -lt 40) { Write-Host "Key generation failed (run 'uv sync' first)." -ForegroundColor Red; exit 1 }

if (Test-Path .env) {
    $bak = ".env.bak-{0:yyyyMMdd-HHmmss}" -f (Get-Date)
    Copy-Item .env $bak
    Write-Host "Existing .env kept as $bak" -ForegroundColor DarkGray
}

$lines = @(
    "# GPHA Internal Audit Workspace - PRODUCTION. Generated $(Get-Date -Format 'yyyy-MM-dd HH:mm') by deploy\windows\1-new-production-env.ps1",
    "# Never copy this file into e-mail, chat or source control.",
    "GPHA_ENVIRONMENT=production",
    "GPHA_SECRET_KEY=$secret",
    "GPHA_ENCRYPTION_KEY=$encKey",
    "GPHA_DATABASE_URL=$dsn",
    "GPHA_COOKIE_SECURE=true",
    "GPHA_SESSION_TTL_HOURS=10",
    "GPHA_APP_BASE_URL=https://$hostName",
    "GPHA_UPLOAD_DIR=$uploadDir",
    "GPHA_BACKUP_DIR=$backupDir",
    "GPHA_BACKUP_INTERVAL_HOURS=24",
    "GPHA_BACKUP_RETENTION=30",
    "GPHA_ESCALATION_CHECK_MINUTES=60",
    "GPHA_MFA_ENFORCED=false",
    "GPHA_ADMIN_USERNAME=$adminUser",
    "GPHA_ADMIN_PASSWORD=$adminPass",
    "GPHA_ADMIN_EMAIL=$adminEmail",
    "GPHA_ADMIN_FULL_NAME=$adminName"
)
if ($smtpHost) {
    $lines += "GPHA_SMTP_HOST=$smtpHost", "GPHA_SMTP_PORT=$smtpPort", "GPHA_SMTP_FROM=$smtpFrom", "GPHA_SMTP_STARTTLS=$smtpTls"
    if ($smtpUser) { $lines += "GPHA_SMTP_USER=$smtpUser", "GPHA_SMTP_PASSWORD=$smtpPass" }
}
Set-Content -Path .env -Value $lines -Encoding UTF8

# Only Administrators and SYSTEM (the service account) may read .env.
icacls .env /inheritance:r /grant:r "Administrators:F" "SYSTEM:F" | Out-Null

Write-Host ""
Write-Host "==================================================================================" -ForegroundColor Yellow
Write-Host " ENCRYPTION KEY - store it NOW in the GPHA password vault / sealed envelope." -ForegroundColor Yellow
Write-Host " Without it, encrypted evidence and backups can NEVER be read again." -ForegroundColor Yellow
Write-Host ""
Write-Host "   $encKey"
Write-Host "==================================================================================" -ForegroundColor Yellow
Read-Host "Type OK and press Enter once the key is stored safely" | Out-Null
Clear-Host
Write-Host ".env written (production). Next: deploy\windows\2-install.ps1" -ForegroundColor Green
Write-Host "After the first sign-in, empty the value of GPHA_ADMIN_PASSWORD in .env (leave 'GPHA_ADMIN_PASSWORD=')." -ForegroundColor DarkGray
Write-Host "It is only used to create the first account." -ForegroundColor DarkGray
