@echo off
rem ASCII-only: no chcp mid-batch (known cmd offset bug)
title Fix Network

echo closing proxy service and restoring direct connection...
taskkill /F /IM mitmdump.exe >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0src\set_proxy.ps1" -State off

echo.
curl -s -o NUL -w "network check: HTTP %{http_code} (200 = OK)" --max-time 10 https://www.baidu.com
echo.
echo if still offline: restart WeChat, or reboot then run this again.
pause
