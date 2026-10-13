# GPHA Audit Workspace - start the development server.
# Usage:  .\run.ps1

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
