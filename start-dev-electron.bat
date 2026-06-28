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

rem Also clear stray sidecar engines from crashed runs that may still hold a
rem RANDOM dynamic control port (matched by command line, not a fixed port).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*engine.py*--control-port*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

timeout /t 2 /nobreak >nul

rem -- Resolve a Python 3.11 interpreter ----------------------------------------
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

rem The sidecar engine needs uvicorn/fastapi. The PATH 'python' is often the
rem .venv-xanylabeling tool venv WITHOUT them, which makes the engine exit with
rem "No module named 'uvicorn'" and the app never starts. Verify the chosen
rem interpreter; if it lacks them, fall back to py -3.11 (where the engine deps
rem are installed), and fail loudly with a fix if neither works.
"%PYTHON%" -c "import uvicorn" >nul 2>&1
if errorlevel 1 (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
"%PYTHON%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
  echo [DEV][ERROR] Engine interpreter is missing uvicorn/fastapi:
  echo [DEV][ERROR]     %PYTHON%
  echo [DEV][ERROR] Install the engine deps into THAT interpreter, e.g.:
  echo [DEV][ERROR]     "%PYTHON%" -m pip install -r "%~dp0sidecar\python-engine\requirements.txt"
  exit /b 1
)
echo [DEV] Engine Python verified (uvicorn/fastapi present): %PYTHON%

echo [DEV] Launching Electron...
rem Pass the verified PYTHON explicitly into the Electron window so main.js's
rem dev sidecar uses it (process.env.PYTHON) instead of falling back to PATH 'python'.
start "CIM Electron DEV" cmd /k "cd /d %~dp0apps\host-electron && set PYTHON=%PYTHON%&& set CIM_DEV_MODE=1&& npm run dev"
