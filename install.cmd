@echo off
rem Double-click this file to install Live Pilot Studio. Flags pass through: install.cmd -Update
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set LP_EXIT=%ERRORLEVEL%
echo.
pause
exit /b %LP_EXIT%
