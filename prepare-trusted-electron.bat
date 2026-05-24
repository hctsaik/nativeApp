@echo off
setlocal

rem Copies the full Electron dist folder to a location your Windows App Control
rem policy can trust. Run this after the target folder/path is allow-listed.
rem Usage:
rem   prepare-trusted-electron.bat C:\CIMTrusted\Electron
rem
rem Then start with:
rem   set CIM_ELECTRON_PATH=C:\CIMTrusted\Electron\electron.exe
rem   start-trusted.bat dev

set "SOURCE_DIR=%~dp0node_modules\electron\dist"
set "TARGET_DIR=%~1"

if "%TARGET_DIR%"=="" set "TARGET_DIR=C:\CIMTrusted\Electron"

echo Source:
echo   %SOURCE_DIR%
echo Target:
echo   %TARGET_DIR%
echo.

if not exist "%SOURCE_DIR%\electron.exe" (
  echo [ERROR] Electron source folder was not found.
  echo Run npm install first, then try again.
  pause
  exit /b 1
)

echo Copying Electron dist folder...
robocopy "%SOURCE_DIR%" "%TARGET_DIR%" /MIR /R:2 /W:2
set "ROBOCOPY_EXIT=%ERRORLEVEL%"

if %ROBOCOPY_EXIT% GEQ 8 (
  echo.
  echo [ERROR] robocopy failed with code %ROBOCOPY_EXIT%.
  pause
  exit /b %ROBOCOPY_EXIT%
)

echo.
echo Done.
echo.
echo Now ask Windows/IT policy to trust this executable if it is not already trusted:
echo   %TARGET_DIR%\electron.exe
echo.
echo Test it with:
echo   "%TARGET_DIR%\electron.exe" --version
echo.
echo Start CIM with:
echo   set CIM_ELECTRON_PATH=%TARGET_DIR%\electron.exe
echo   start-trusted.bat dev
echo.
pause

