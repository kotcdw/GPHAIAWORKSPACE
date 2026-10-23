@echo off
title Wipe data - GPHA INTERNAL AUDIT WORKSPACE
cd /d "%~dp0"
echo ============================================================
echo  Wipe data - GPHA INTERNAL AUDIT WORKSPACE
echo ============================================================
echo  Keeps users, roles, settings, libraries and the audit trail.
echo  A full backup is taken first.
echo  The database must be running (start the app with Start-GPHA.cmd first).
echo.
uv run python -m scripts.wipe_data
echo.
pause
