@echo off
setlocal

rem Preflight: abort with an actionable message if git submodules are missing (see scripts\win\preflight-submodules.bat)
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

rem Starts CIM with an Electron executable from an allow-listed/trusted path.
rem Usage:
rem   start-trusted.bat dev
rem   start-trusted.bat prod
rem
rem Configure one of these:
rem   1. Set CIM_ELECTRON_PATH before running this bat.
rem   2. Edit DEFAULT_TRUSTED_ELECTRON below.
rem
rem IMPORTANT: Electron usually needs the whole Electron dist folder, not only
rem electron.exe. If your IT policy trusts paths, copy or install the full
rem node_modules\electron\dist folder into that trusted location.

set "MODE=%~1"
if "%MODE%"=="" set "MODE=dev"

if /I "%MODE%"=="prod" (
  set "CIM_DEV_MODE_VALUE=0"
  set "TITLE_MODE=PROD"
) else (
  set "CIM_DEV_MODE_VALUE=1"
  set "TITLE_MODE=DEV"
)

title CIM Platform - %TITLE_MODE% Mode - Trusted Electron

rem Change this path to the electron.exe that your Windows App Control policy allows.
set "DEFAULT_TRUSTED_ELECTRON=C:\CIMTrusted\Electron\electron.exe"

if "%CIM_ELECTRON_PATH%"=="" (
  set "CIM_ELECTRON_PATH=%DEFAULT_TRUSTED_ELECTRON%"
)

echo [%TITLE_MODE%] Using Electron:
echo   %CIM_ELECTRON_PATH%

if not exist "%CIM_ELECTRON_PATH%" (
  echo.
  echo [ERROR] Trusted Electron executable was not found.
  echo.
  echo Fix one of these:
  echo   1. Edit DEFAULT_TRUSTED_ELECTRON in start-trusted.bat
  echo   2. Or run:
  echo      set CIM_ELECTRON_PATH=C:\path\to\trusted\electron.exe
  echo      start-trusted.bat %MODE%
  echo.
  echo If you are using a trusted folder, copy the full Electron dist folder:
  echo   C:\code\claude\nativeApp_Management\node_modules\electron\dist
  echo into the trusted location, then point CIM_ELECTRON_PATH at electron.exe there.
  pause
  exit /b 1
)

echo [%TITLE_MODE%] Checking whether Windows allows this Electron binary...
"%CIM_ELECTRON_PATH%" --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo [ERROR] Windows still blocked this Electron executable, or it cannot run.
  echo.
  echo Try this command directly to see the Windows error:
  echo   "%CIM_ELECTRON_PATH%" --version
  echo.
  echo If it says Application Control blocked the file, ask IT to trust this path/file,
  echo or set CIM_ELECTRON_PATH to a different approved Electron binary.
  pause
  exit /b 1
)

echo [%TITLE_MODE%] Cleaning old local processes/ports...
taskkill /F /IM electron.exe >nul 2>&1

for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:5173 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:19222 "') do taskkill /F /PID %%a >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| find "127.0.0.1:8765 "') do taskkill /F /PID %%a >nul 2>&1

timeout /t 2 /nobreak >nul

echo [%TITLE_MODE%] Launching CIM...
start "CIM Electron %TITLE_MODE%" cmd /k "cd /d %~dp0apps\host-electron && set ^"CIM_DEV_MODE=%CIM_DEV_MODE_VALUE%^"&& set ^"CIM_ELECTRON_PATH=%CIM_ELECTRON_PATH%^"&& npm run dev"
