@echo off
title CIM Platform - PROD Mode
echo [PROD] Starting in PROD mode (CIM_DEV_MODE=0)...

taskkill /F /IM electron.exe >nul 2>&1

for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:5173 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:19222 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:8765 "') do taskkill /F /PID %%a >nul 2>&1

timeout /t 2 /nobreak >nul

echo [PROD] Launching Electron...
start "CIM Electron PROD" cmd /k "cd /d %~dp0apps\host-electron && set CIM_DEV_MODE=0&&npm run dev"
