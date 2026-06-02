@echo off
title CIM Platform - DEV Mode
echo [DEV] Starting in DEV mode (CIM_DEV_MODE=1)...

rem Preflight: abort with an actionable message if git submodules are missing (see scripts\win\preflight-submodules.bat)
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

taskkill /F /IM electron.exe >nul 2>&1

for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:5173 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:19222 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:8765 "') do taskkill /F /PID %%a >nul 2>&1

timeout /t 2 /nobreak >nul

echo [DEV] Launching Electron...
set PYTHON=C:\Users\hctsa\AppData\Local\Python\pythoncore-3.11-64\python.exe
start "CIM Electron DEV" cmd /k "cd /d %~dp0apps\host-electron && set CIM_DEV_MODE=1&&npm run dev"
