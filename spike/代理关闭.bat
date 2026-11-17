@echo off
rem 网络异常时双击本文件即可恢复（关闭系统代理）
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0set_proxy.ps1" -State off
pause
