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

rem ── Resolve a Python 3.11 interpreter ───────────────────────────────────────
rem Override by setting PYTHON before running this script. Otherwise prefer the
rem Windows py launcher (py -3.11), then a 3.11 'python' on PATH.
rem NOTE: AI4BI / xanylabeling are pip-installed into THIS interpreter; if you
rem use a custom one, install the deps into the same one (see README).
if not defined PYTHON (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  for /f "delims=" %%p in ('python -c "import sys;print(sys.executable) if sys.version_info[:2]==(3,11) else ''" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  echo [DEV][ERROR] Could not find Python 3.11.
  echo [DEV][ERROR] Install it ^(then 'py -3.11' works^), or set PYTHON to its python.exe path before running.
  exit /b 1
)
echo [DEV] Using Python: %PYTHON%

echo [DEV] Launching Electron...
start "CIM Electron DEV" cmd /k "cd /d %~dp0apps\host-electron && set CIM_DEV_MODE=1&&npm run dev"
