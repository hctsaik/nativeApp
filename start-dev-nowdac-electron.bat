@echo off
title CIM Platform - DEV (no-WDAC / static portal)
echo [DEV-NOWDAC] Starting WITHOUT vite (esbuild.exe is WDAC-blocked on this machine).
echo [DEV-NOWDAC] Serves the PRE-BUILT portal dist and loads it in dev Electron.
echo [DEV-NOWDAC] NOTE: no HMR; portal source changes need a rebuild on a machine
echo [DEV-NOWDAC]       where esbuild is allowed. Engine/backend run from source.

rem Preflight: same submodule guard as start-dev.bat
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

rem -- Clean stray processes / ports --------------------------------------------
taskkill /F /IM electron.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:5173 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:19222 "') do taskkill /F /PID %%a >nul 2>&1
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*engine.py*--control-port*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
timeout /t 2 /nobreak >nul

rem -- Resolve a Python 3.11 interpreter (same logic as start-dev.bat) -----------
if not defined PYTHON (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  for /f "delims=" %%p in ('python -c "import sys;print(sys.executable) if sys.version_info[:2]==(3,11) else ''" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  echo [DEV-NOWDAC][ERROR] Could not find Python 3.11. Install it ^(then 'py -3.11' works^) or set PYTHON.
  exit /b 1
)
"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
"%PYTHON%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
  echo [DEV-NOWDAC][ERROR] Engine interpreter missing uvicorn/fastapi: %PYTHON%
  echo [DEV-NOWDAC][ERROR]     "%PYTHON%" -m pip install -r "%~dp0sidecar\python-engine\requirements.txt"
  exit /b 1
)
echo [DEV-NOWDAC] Using Python: %PYTHON%

rem -- Verify a pre-built portal exists -----------------------------------------
if not exist "%~dp0apps\portal-react\dist\index.html" (
  echo [DEV-NOWDAC][ERROR] No pre-built portal at apps\portal-react\dist.
  echo [DEV-NOWDAC][ERROR] Build it on a machine where esbuild is allowed:
  echo [DEV-NOWDAC][ERROR]     npm --prefix apps\portal-react run build
  exit /b 1
)

rem -- Start the static portal server (node is allowed by WDAC) ------------------
echo [DEV-NOWDAC] Launching static portal server on http://127.0.0.1:5173 ...
start "CIM Portal (static, no-WDAC)" cmd /k "node ""%~dp0scripts\win\serve-portal-dist.js"""
timeout /t 2 /nobreak >nul

rem -- Launch Electron pointed at the static server (bypasses vite/esbuild) ------
echo [DEV-NOWDAC] Launching Electron ...
start "CIM Electron (no-WDAC)" cmd /k "cd /d %~dp0apps\host-electron&& set ELECTRON_RUN_AS_NODE=&& set PYTHON=%PYTHON%&& set CIM_DEV_MODE=1&& set PORTAL_DEV_URL=http://127.0.0.1:5173&& node launch-electron.js"
