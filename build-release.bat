@echo off
REM =========================================================================
REM  build-release.bat — 一鍵打包 CIM Hybrid Edge Platform
REM
REM  輸出：release\CIM Hybrid Edge Platform*.exe  (portable，無需安裝)
REM
REM  前置需求（Build machine 上才需要）：
REM    - Python 3.11+  (pyinstaller 使用)
REM    - Node.js 18+
REM    - pip install pyinstaller
REM =========================================================================

setlocal enabledelayedexpansion
set "ROOT=%~dp0"
set "SIDECAR=%ROOT%sidecar\python-engine"
set "ELECTRON=%ROOT%apps\host-electron"

echo.
echo [1/4] 建置 Python engine (PyInstaller)...
cd /d "%SIDECAR%"
pyinstaller engine.spec --clean --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller 失敗
    exit /b 1
)
echo       完成 -^> dist\engine.exe

echo.
echo [2/4] 建置 React Portal...
cd /d "%ROOT%apps\portal-react"
call npm run build
if errorlevel 1 (
    echo ERROR: React build 失敗
    exit /b 1
)
echo       完成 -^> dist\

echo.
echo [3/4] 打包 Electron (portable)...
cd /d "%ELECTRON%"
call npm run package:portable:x64
if errorlevel 1 (
    echo ERROR: Electron build 失敗
    exit /b 1
)
echo       完成

echo.
echo [4/4] 輸出清單:
dir /b "%ROOT%release\*.exe" 2>nul || dir /b "%ROOT%release\" 2>nul
echo.
echo =========================================
echo  打包完成！
echo  輸出目錄：%ROOT%release\
echo =========================================
