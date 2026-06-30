@echo off
rem ============================================================================
rem  start-dev.bat — 已轉導至新架構（Tauri）。
rem  啟動一律改用 Tauri 殼（已併入本 repo：apps\host-tauri）；portal / engine / 模組完全共用、不變。
rem  舊的 Electron DEV 殼仍保留為備援：start-dev-electron.bat。
rem  說明：根目錄 CLAUDE.md「啟動方式」與 docs/platform/startup-tauri.md。
rem ============================================================================
echo [start-dev] 新架構：啟動已改用 Tauri。轉導至 start-dev-tauri.bat ...
echo [start-dev] （若真的要用舊 Electron DEV 殼，請執行 start-dev-electron.bat）
call "%~dp0start-dev-tauri.bat" %*
