@echo off
title Reset a GPHA Internal Audit Workspace password
cd /d "%~dp0"
echo ============================================================
echo  Reset a password - GPHA Internal Audit Workspace
echo ============================================================
echo  The database must be running (start the app with Start-GPHA.cmd first).
echo.
uv run python -m scripts.reset_password
echo.
pause
