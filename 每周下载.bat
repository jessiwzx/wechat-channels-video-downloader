@echo off
rem ASCII-only: no chcp mid-batch (known cmd offset bug), python console IO is Unicode-safe
set PYTHONIOENCODING=
cd /d "%~dp0"
title Weekly Video Download

set "DIAG=%TEMP%\sph_weekly.log"
echo [%date% %time%] ==== bat start ==== >> "%DIAG%"

rem ---- external watchdog: auto-disable system proxy if the proxy service dies ----
start "watchdog" /min powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0src\watchdog.ps1"

set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not exist "%PY%" (
    where python >nul 2>nul && set "PY=python"
)
echo [%time%] PY=%PY% >> "%DIAG%"
"%PY%" "%~dp0src\orchestrator.py"
set RC=%ERRORLEVEL%
echo [%time%] orchestrator exited RC=%RC% >> "%DIAG%"

rem ---- belt and suspenders: always disable system proxy after exit ----
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0src\set_proxy.ps1" -State off >nul

echo.
echo ============ run finished ============
echo videos are in the archive folder under: %~dp0
if not "%RC%"=="0" echo (exit code %RC%; if network is broken, run the fix-network bat)
pause
