@echo off
rem ============================================================================
rem  CIM Hybrid Edge Platform — DEV 啟動（Tauri 殼，新架構，正式主線）
rem ----------------------------------------------------------------------------
rem  新架構：殼換成 Tauri（nativeApp_Light）；portal / Python engine / cim-modules /
rem  外部工具完全共用、不變。Tauri dev 直接載「預建 portal dist」並由 Rust 端 spawn 原始碼 engine。
rem
rem  ⚠️ WDAC 重要實測（2026-06-28）：在『強制模式 WDAC』機器上，`tauri dev` 會在 cargo
rem  編譯階段被擋——WDAC 封鎖 cargo 產出的『未簽章 build-script / debug exe』
rem  （錯誤：os error 4551「應用程式控制原則已封鎖此檔案」），與擋 esbuild 同一類問題。
rem  本機若無法自行加 WDAC 規則，LOCAL Tauri dev 暫時無法跑；本檔會『先試 Tauri、失敗就自動
rem  轉用 Electron（no-WDAC）備援』，讓你仍有可用的 DEV。詳見 docs/platform/startup-tauri.md。
rem  根治：請 IT 放行 Rust 編譯產物（src-tauri\target）或對應簽章；或在可編譯的機器
rem  `npm run tauri:build` 產『簽章版』再部署（release 簽章版 runtime 對 WDAC 友善）。
rem ============================================================================
title CIM Platform - DEV (Tauri shell)
echo [DEV-TAURI] 新架構：Tauri 殼 + 原始碼 engine（portal/engine/模組與 Electron 共用、不變）。

rem -- submodule preflight ----------------------------------------------------
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

rem -- Tauri 專案位置（nativeApp_Light 為 nativeApp 的 sibling repo）----------------
set "LIGHT=%~dp0..\nativeApp_Light\5_PG_Develop"
if not exist "%LIGHT%\src-tauri\tauri.conf.json" (
  echo [DEV-TAURI][ERROR] 找不到 Tauri 專案：%LIGHT%（請確認 nativeApp_Light 與 nativeApp 同層）。
  exit /b 1
)
if not exist "%LIGHT%\node_modules" (
  echo [DEV-TAURI][ERROR] Tauri 前端相依未安裝。請先： cd /d "%LIGHT%" ^&^& npm install
  exit /b 1
)
where cargo >nul 2>&1
if errorlevel 1 (
  echo [DEV-TAURI][ERROR] 找不到 cargo / Rust toolchain（Tauri 需要）。請安裝 Rust（rustup）。
  exit /b 1
)

rem -- 預建 portal dist 必須存在 -------------------------------------------------
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

rem -- DEV：engine 用原始碼 engine.py，由 Tauri(Rust) spawn；CIM_ENGINE_PYTHON 指直譯器 ----
echo [DEV-TAURI] 啟動 tauri dev …（首次會編譯 Rust；WDAC 機器可能在此被擋，會自動轉 Electron 備援）
pushd "%LIGHT%"
set "CIM_ENGINE_EXE=%~dp0sidecar\python-engine\engine.py"
set "CIM_ENGINE_PYTHON=%PYTHON%"
set "PYTHONUTF8=1"
call npm run tauri:dev
set "RC=%errorlevel%"
popd

if not "%RC%"=="0" (
  echo.
  echo ============================================================================
  echo [DEV-TAURI][WDAC?] Tauri 啟動/編譯失敗（rc=%RC%）。
  echo   最可能：WDAC 強制模式封鎖了 cargo 的『未簽章 build-script / debug exe』
  echo            ^(os error 4551「應用程式控制原則已封鎖此檔案」^)——與擋 esbuild 同類。
  echo   根治：IT 放行 Rust 編譯產物（src-tauri\target）/ 簽章；或在可編譯機器
  echo         `npm run tauri:build` 產簽章版再部署。詳見 docs\platform\startup-tauri.md。
  echo   本機暫時轉用 Electron（no-WDAC）備援，讓你仍有可用的 DEV ...
  echo ============================================================================
  echo.
  call "%~dp0start-dev-nowdac-electron.bat"
)
