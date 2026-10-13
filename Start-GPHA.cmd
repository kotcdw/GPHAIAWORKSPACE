@echo off
title GPHA Internal Audit Workspace
cd /d "%~dp0"
echo ============================================================
echo  GPHA Internal Audit Workspace - (re)start
echo ============================================================
echo.
echo Stopping any old copy of the app on port 8001...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
timeout /t 2 /nobreak >nul
powershell -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue) { exit 1 } else { exit 0 }"
if errorlevel 1 (
  echo.
  echo The old app could not be stopped - it may have been started as Administrator.
  echo Right-click this file and choose "Run as administrator", or restart the PC.
  echo.
  pause
  exit /b 1
)
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
echo.
echo The app has stopped. Press any key to close this window.
pause >nul
