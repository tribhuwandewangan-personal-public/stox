@echo off
setlocal
cd /d "%~dp0"
echo ========================================================================
echo   Running NSE Dashboard Cleanup Utility...
echo ========================================================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0cleanup_server.ps1" %*
echo.
pause

