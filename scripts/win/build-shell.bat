@echo off
rem ============================================================================
rem  build-shell.bat — 在「非 WDAC 強制」機器上 build Tauri 殼 exe 並放進 prebuilt\
rem ----------------------------------------------------------------------------
rem  cim-light.exe 不進 git（見 apps\host-tauri\.gitignore）。要跑 Tauri 殼必須先有
rem  這顆 exe：
rem    - 非 WDAC 機器：跑本檔即可（cargo build --release → 複製到 prebuilt\）。
rem    - 本開發機（WDAC 強制）：cargo 會被擋（os error 4551），無法在此 build；改在別台
rem      跑本檔，再把 apps\host-tauri\prebuilt\cim-light.exe 複製過來。
rem ============================================================================
setlocal
set "ROOT=%~dp0..\.."
set "TAURI_DIR=%ROOT%\apps\host-tauri\src-tauri"
set "PREBUILT=%ROOT%\apps\host-tauri\prebuilt"

rem -- portal dist 必須先建好（Tauri 殼載它；tauri-build 也會檢查其存在）--
if not exist "%ROOT%\apps\portal-react\dist\index.html" (
  echo [BUILD-SHELL][ERROR] 缺 portal dist：apps\portal-react\dist
  echo   先在可用 esbuild 的機器： npm --prefix apps\portal-react run build
  exit /b 1
)

rem -- cargo（Rust toolchain）--
where cargo >nul 2>&1
if errorlevel 1 (
  echo [BUILD-SHELL][ERROR] 找不到 cargo。請先裝 Rust toolchain（rustup）。
  exit /b 1
)

echo [BUILD-SHELL] cargo build --release（%TAURI_DIR%）…
pushd "%TAURI_DIR%"
cargo build --release
set "RC=%ERRORLEVEL%"
popd
if not "%RC%"=="0" (
  echo.
  echo [BUILD-SHELL][ERROR] cargo build 失敗（rc=%RC%）。
  echo   若這裡是 WDAC 強制機器，build-script/新 exe 會被擋（os error 4551）——
  echo   請改在「沒有 WDAC 強制」的機器跑本檔，再把 prebuilt\cim-light.exe 複製回來。
  exit /b 1
)

if not exist "%PREBUILT%" mkdir "%PREBUILT%"
copy /y "%TAURI_DIR%\target\release\cim-light.exe" "%PREBUILT%\cim-light.exe" >nul
if errorlevel 1 (
  echo [BUILD-SHELL][ERROR] 複製 exe 失敗（找不到 target\release\cim-light.exe？）。
  exit /b 1
)
echo [BUILD-SHELL] 完成 → %PREBUILT%\cim-light.exe
echo [BUILD-SHELL] 若要在 WDAC 機器上跑，把這顆 exe 複製到該機器同路徑的 prebuilt\ 即可。
endlocal
