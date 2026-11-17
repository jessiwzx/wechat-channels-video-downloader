@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set_proxy.ps1" -State on
pause
