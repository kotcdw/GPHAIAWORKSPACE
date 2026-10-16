# GPHA Internal Audit Workspace - team test on the office network.
# Usage:  .\run-lan.ps1            (port 8001)
#         .\run-lan.ps1 -Port 8080
#
# Starts the database and the app exactly like .\run.ps1, but lets colleagues on
# the office network open it at http://<this PC's address>:8001. The first time it
# asks Windows for approval to open the port in the firewall (Domain/Private only).
# Plain HTTP: demo or test data only. For the pilot use the Laragon HTTPS setup
# in deploy\PRODUCTION.md.
#
# To remove the firewall rule later (PowerShell as Administrator):
#   Remove-NetFirewallRule -DisplayName "GIAW team test (TCP 8001)"
param([int]$Port = 8001)
& (Join-Path $PSScriptRoot "run.ps1") -Lan -Port $Port
exit $LASTEXITCODE
