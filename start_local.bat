@echo off
title MNHS Review Center - Local WiFi
cd /d "%~dp0"
set MNHS_LOCAL=1
set MNHS_PORT=5000
echo.
echo   MNHS REVIEW CENTER - LOCAL WIFI
echo   ---------------------------------
echo   Students open:  http://THIS-LAPTOP-IP:5000
echo   Laptop address: run  ipconfig  and read IPv4 Address
echo   Sync results:   http://127.0.0.1:5000/admin/sync
echo.
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" run_local.py
) else (
    python run_local.py
)
echo.
echo The server stopped.
pause
