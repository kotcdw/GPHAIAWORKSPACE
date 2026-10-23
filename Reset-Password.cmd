@echo off
title Reset a GPHA INTERNAL AUDIT WORKSPACE password
cd /d "%~dp0"
echo ============================================================
echo  Reset a password - GPHA INTERNAL AUDIT WORKSPACE
echo ============================================================
echo  The database must be running (start the app with Start-GPHA.cmd first).
echo.
uv run python -m scripts.reset_password
echo.
pause
