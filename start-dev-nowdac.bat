@echo off
rem ============================================================================
rem  start-dev-nowdac.bat — 已轉導至新架構（Tauri）。
rem  原本這支是「WDAC 環境繞過 Vite/esbuild」的 Electron DEV 變體；新架構的 Tauri 殼
rem  本來就直接載預建 portal dist、dev 不跑 Vite，天生就是「no-WDAC-esbuild」路徑，
rem  因此這支與 start-dev 一樣轉導到 start-dev-tauri.bat。
rem  舊的 Electron no-WDAC 殼仍保留為備援：start-dev-nowdac-electron.bat。
rem ============================================================================
echo [start-dev-nowdac] 新架構：啟動已改用 Tauri（dev 不跑 esbuild，天生避開 WDAC 封鎖）。
echo [start-dev-nowdac] 轉導至 start-dev-tauri.bat ...（舊 Electron no-WDAC 殼：start-dev-nowdac-electron.bat）
call "%~dp0start-dev-tauri.bat" %*
