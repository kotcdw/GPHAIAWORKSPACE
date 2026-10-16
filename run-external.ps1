# GPHA Internal Audit Workspace - share the app with testers outside the office.
#
# Usage:
#   .\run-external.ps1                       Cloudflare quick tunnel: a new https://....trycloudflare.com
#                                            link each time; testers need only a browser.
#   .\run-external.ps1 -Mode Tailscale       Private: only people invited to your Tailscale network
#                                            (they install Tailscale); fixed https://<pc>.<tailnet>.ts.net link.
#   .\run-external.ps1 -TunnelName giaw -Hostname giaw-test.example.com
#                                            Cloudflare named tunnel with a fixed address (set up once,
#                                            see README "Testers outside the office").
#
# Before sharing it refuses to start while any active account still uses a published password
# (Admin@12345, the demo password or GPHA_ADMIN_PASSWORD from .env). The app listens on this PC
# only (127.0.0.1); the tunnel carries encrypted HTTPS, so no firewall or router change is needed.
# Demo or test data only until GPHA approves hosting (see MAINPLAN).
param(
    [ValidateSet("Cloudflare", "Tailscale")]
    [string]$Mode = "Cloudflare",
    [string]$TunnelName = "",
    [string]$Hostname = "",
    [int]$Port = 8001
)
& (Join-Path $PSScriptRoot "run.ps1") -External $Mode -TunnelName $TunnelName -Hostname $Hostname -Port $Port
exit $LASTEXITCODE
