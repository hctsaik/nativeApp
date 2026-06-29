@echo off
rem ============================================================================
rem  CIM Hybrid Edge Platform — DEV 啟動（Tauri 殼，新架構，正式主線）
rem ----------------------------------------------------------------------------
rem  本機主線 = 跑「既有已 build 的」Tauri exe `cim-light.exe`（portal / Python engine /
rem  cim-modules / 外部工具完全共用、不變）。
rem
rem  ⚠️ WDAC 定論（見 CLAUDE.md「## WDAC」+ docs/platform/startup-tauri.md）：
rem  本機 WDAC 強制模式擋「新編譯出來的未簽章 exe」（含 cargo build-script）→ **不要在本機跑
rem  `tauri dev`/`tauri build`**（會被擋 os error 4551）。但「跑既有 exe」可以，所以本檔直接執行
rem  已 build 好的 cim-light.exe。要更新 Rust 殼本身 → 在沒有 WDAC 強制的機器 build 後帶回。
rem ============================================================================
title CIM Platform - DEV (Tauri shell)
echo [DEV-TAURI] 跑既有的 Tauri 殼 cim-light.exe + 原始碼 engine（portal/engine/模組與 Electron 共用、不變）。

rem -- submodule preflight ----------------------------------------------------
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

rem -- Tauri 專案位置（nativeApp_Light 為 nativeApp 的 sibling repo）----------------
set "LIGHT=%~dp0..\nativeApp_Light\5_PG_Develop"
if not exist "%LIGHT%\src-tauri\tauri.conf.json" (
  echo [DEV-TAURI][ERROR] 找不到 Tauri 專案：%LIGHT%（請確認 nativeApp_Light 與 nativeApp 同層）。
  exit /b 1
)

rem -- 找「既有已 build」的 Tauri exe（release 優先，否則 debug）。不在本機重編。-----------
set "TAURI_EXE=%LIGHT%\src-tauri\target\release\cim-light.exe"
if not exist "%TAURI_EXE%" set "TAURI_EXE=%LIGHT%\src-tauri\target\debug\cim-light.exe"
if not exist "%TAURI_EXE%" (
  echo.
  echo [DEV-TAURI][ERROR] 找不到已 build 的 Tauri exe（cim-light.exe）。
  echo   本機 WDAC 擋 cargo 重編，無法在此 build；請在「沒有 WDAC 強制的機器」
  echo   `npm run tauri:build`（或 tauri:dev）產生 exe 後帶回，或請 IT 放行 src-tauri\target。
  echo   詳見 docs\platform\startup-tauri.md。本機暫時轉用 Electron（no-WDAC）備援 ...
  echo.
  call "%~dp0start-dev-nowdac-electron.bat"
  exit /b 0
)
echo [DEV-TAURI] 既有 Tauri exe：%TAURI_EXE%

rem -- 預建 portal dist 必須存在（Tauri 載靜態 dist）-------------------------------
if not exist "%~dp0apps\portal-react\dist\index.html" (
  echo [DEV-TAURI][ERROR] 找不到預建 portal：apps\portal-react\dist
  echo [DEV-TAURI][ERROR] 在可用 esbuild 的機器建一次： npm --prefix apps\portal-react run build
  exit /b 1
)

rem -- 解析 Python 3.11（engine 以原始碼跑）---------------------------------------
if not defined PYTHON (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  echo [DEV-TAURI][ERROR] 找不到 Python 3.11（py -3.11）。請安裝或先設 PYTHON。
  exit /b 1
)
"%PYTHON%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
"%PYTHON%" -c "import uvicorn, fastapi" >nul 2>&1
if errorlevel 1 (
  echo [DEV-TAURI][ERROR] engine 直譯器缺 uvicorn/fastapi：%PYTHON%
  echo [DEV-TAURI][ERROR]   "%PYTHON%" -m pip install -r "%~dp0sidecar\python-engine\requirements.txt"
  exit /b 1
)
echo [DEV-TAURI] Using Python: %PYTHON%

rem -- 清理殘留 engine --------------------------------------------------------
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*engine.py*--control-port*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

rem -- 啟動既有 Tauri exe（cwd=src-tauri：對映 cargo run 的 cwd，log 落 src-tauri\logs）-------
rem    engine 用原始碼 engine.py（CIM_ENGINE_EXE 為 .py → 以 CIM_ENGINE_PYTHON 執行）。
set "ENGINE_PY=%~dp0sidecar\python-engine\engine.py"
echo [DEV-TAURI] 啟動 Tauri 視窗（cim-light.exe）…
start "CIM Tauri DEV" cmd /k "cd /d %LIGHT%\src-tauri && set CIM_ENGINE_EXE=%ENGINE_PY%&& set CIM_ENGINE_PYTHON=%PYTHON%&& set PYTHONUTF8=1&& %TAURI_EXE%"
