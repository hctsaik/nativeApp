@echo off
title CIM Platform - FLEET Simulation
echo [FLEET] Single-machine fleet simulation: 1 registry + 2 devices.
echo [FLEET] Each device is a state-isolated engine (own --log-dir / tools.sqlite)
echo [FLEET] all subscribing to one registry via CIM_DISTRIBUTION_SOURCE.

rem Preflight: abort with an actionable message if git submodules are missing (see scripts\win\preflight-submodules.bat)
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

setlocal
rem Resolve Python 3.11 (override by setting PYTHON before running); prefer py -3.11.
if not defined PYTHON (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  for /f "delims=" %%p in ('python -c "import sys;print(sys.executable) if sys.version_info[:2]==(3,11) else ''" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  echo [FLEET][ERROR] Could not find Python 3.11. Install it ^(py -3.11^) or set PYTHON to its python.exe path.
  exit /b 1
)
set ENGINE_DIR=%~dp0sidecar\python-engine
set FLEET_ROOT=%~dp0tmp\fleet
set REGISTRY_URL=http://127.0.0.1:9000

echo [FLEET] Engine python: %PYTHON%

rem --- free ports from a previous run ---
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:9000 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:8100 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:8101 "') do taskkill /F /PID %%a >nul 2>&1

if not exist "%FLEET_ROOT%" mkdir "%FLEET_ROOT%"

echo [FLEET] Starting registry-server on %REGISTRY_URL% ...
start "FLEET registry" cmd /k cd /d %ENGINE_DIR% ^&^& %PYTHON% tools\registry_server.py --port 9000 --store %FLEET_ROOT%\registry-store

timeout /t 2 /nobreak >nul

echo [FLEET] Starting device A (control-port 8100) ...
start "FLEET deviceA" cmd /k cd /d %ENGINE_DIR% ^&^& set CIM_DEV_MODE=1^&^& set CIM_DISTRIBUTION_SOURCE=%REGISTRY_URL%^&^& %PYTHON% engine.py --control-port 8100 --log-dir %FLEET_ROOT%\deviceA

echo [FLEET] Starting device B (control-port 8101) ...
start "FLEET deviceB" cmd /k cd /d %ENGINE_DIR% ^&^& set CIM_DEV_MODE=1^&^& set CIM_DISTRIBUTION_SOURCE=%REGISTRY_URL%^&^& %PYTHON% engine.py --control-port 8101 --log-dir %FLEET_ROOT%\deviceB

echo.
echo [FLEET] ===== DEMO: publish one tool to the whole fleet =====
echo   cd %ENGINE_DIR%
echo   %PYTHON% tools\fleet_publish.py scripts\module_007 --registry %REGISTRY_URL% --channel prod
echo.
echo   Then each device picks it up (no restart):
echo     curl -X POST http://127.0.0.1:8100/reload
echo     curl -X POST http://127.0.0.1:8101/reload
echo   Verify it landed on both devices:
echo     curl http://127.0.0.1:8100/tools
echo     curl http://127.0.0.1:8101/tools
echo.
endlocal
