@echo off
rem ============================================================================
rem  CIM Hybrid Edge Platform — DEV 啟動（Tauri 殼，新架構，正式主線）
rem ----------------------------------------------------------------------------
rem  新架構：殼換成 Tauri（nativeApp_Light），**portal / Python engine / cim-modules /
rem  外部工具完全共用、不變**。Tauri dev 直接載「預建 portal dist」(不跑 Vite/esbuild →
rem  避開本機 WDAC 對 esbuild 的封鎖)，並由 Rust 端自動 spawn 原始碼 engine。
rem  詳見 docs/platform/startup-tauri.md 與根目錄 CLAUDE.md「啟動方式」。
rem
rem  Electron 舊殼已退為備援：start-dev-electron.bat / start-dev-nowdac-electron.bat。
rem ============================================================================
title CIM Platform - DEV (Tauri shell)
echo [DEV-TAURI] 新架構：Tauri 殼 + 原始碼 engine（portal/engine/模組與 Electron 共用、不變）。

rem -- submodule preflight（engine 仍需 cim-modules / labeling 到位）---------------
call "%~dp0scripts\win\preflight-submodules.bat"
if errorlevel 1 exit /b 1

rem -- Tauri 專案位置（nativeApp_Light 為 nativeApp 的 sibling repo）----------------
set "LIGHT=%~dp0..\nativeApp_Light\5_PG_Develop"
if not exist "%LIGHT%\src-tauri\tauri.conf.json" (
  echo [DEV-TAURI][ERROR] 找不到 Tauri 專案：%LIGHT%
  echo [DEV-TAURI][ERROR] 請確認 nativeApp_Light 與 nativeApp 放在同一層（例如 C:\code\claude\ 下）。
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

rem -- 預建 portal dist 必須存在（Tauri dev 載靜態 dist，不跑 Vite）------------------
if not exist "%~dp0apps\portal-react\dist\index.html" (
  echo [DEV-TAURI][ERROR] 找不到預建 portal：apps\portal-react\dist
  echo [DEV-TAURI][ERROR] 在可用 esbuild 的機器建一次： npm --prefix apps\portal-react run build
  exit /b 1
)

rem -- 解析 Python 3.11（engine 以原始碼跑；沿用 start-dev 的偵測邏輯）---------------
if not defined PYTHON (
  for /f "delims=" %%p in ('py -3.11 -c "import sys;print(sys.executable)" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  for /f "delims=" %%p in ('python -c "import sys;print(sys.executable) if sys.version_info[:2]==(3,11) else ''" 2^>nul') do set "PYTHON=%%p"
)
if not defined PYTHON (
  echo [DEV-TAURI][ERROR] 找不到 Python 3.11（py -3.11）。請安裝或先設 PYTHON。
  exit /b 1
)
"%PYTHON%" -c "import uvicorn" >nul 2>&1
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

rem -- 清理殘留 engine（崩潰留下、仍佔動態 control-port 的子程序）---------------------
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*engine.py*--control-port*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

rem -- DEV：engine 用『原始碼』engine.py，由 Tauri(Rust)spawn；CIM_ENGINE_PYTHON 指直譯器 --
rem    （sidecar.rs：CIM_ENGINE_EXE 副檔名為 .py → 以 CIM_ENGINE_PYTHON 執行原始碼）
set "ENGINE_PY=%~dp0sidecar\python-engine\engine.py"
echo [DEV-TAURI] engine（原始碼）= %ENGINE_PY%

rem -- 啟動 Tauri dev（首次會編譯 Rust，請稍候；之後載 portal dist + 自動 spawn engine）--
echo [DEV-TAURI] 啟動 tauri dev …
start "CIM Tauri DEV" cmd /k "cd /d %LIGHT% && set CIM_ENGINE_EXE=%ENGINE_PY%&& set CIM_ENGINE_PYTHON=%PYTHON%&& set PYTHONUTF8=1&& npm run tauri:dev"
