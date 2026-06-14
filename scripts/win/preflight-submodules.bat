@echo off
setlocal
rem ============================================================================
rem  CIM plugin preflight  --  detect whether required plugin content is present
rem  (AI4BI git submodule + the external Labeling plugin mounted at plugins\labeling)
rem ----------------------------------------------------------------------------
rem  Called by start-dev/prod/trusted/fleet.bat before launch.
rem  ASCII-ONLY ON PURPOSE: this guard runs on other people's machines whose
rem  console codepage we do not control (Traditional-Chinese machines default to
rem  CP950). Non-ASCII echo would be mojibaked and can even corrupt cmd parsing,
rem  so all output here is plain ASCII. The full bilingual (zh-Hant) explanation
rem  lives in engine.log under the same [CIM-PREFLIGHT] marker, and in README.md.
rem
rem  Sentinel files are kept in sync with scripts\win\verify-setup.ps1 and
rem  engine.py check_submodules(). Grep [CIM-PREFLIGHT] to find / paste to an AI.
rem  exit /b 0 = ok ; exit /b 1 = plugin content missing (caller should abort)
rem ============================================================================
set "REPO_ROOT=%~dp0..\.."
set "LABELING_SENTINEL=%REPO_ROOT%\sidecar\python-engine\plugins\labeling\plugin.manifest.yaml"
set "AI4BI_SENTINEL=%REPO_ROOT%\sidecar\python-engine\vendor\AI4BI\ai4bi\ui\app.py"

set "MISSING="
if not exist "%LABELING_SENTINEL%" set "MISSING=1"
if not exist "%AI4BI_SENTINEL%"   set "MISSING=1"

if not defined MISSING exit /b 0

echo.
echo ============================================================
echo  [CIM-PREFLIGHT] required plugin content is missing.
echo ============================================================
echo.
echo  Symptom : the workflow list is missing items (Labeling / AI Report)
echo            and/or the app fails to start.
echo.
echo  Missing and how to fix:
if not exist "%LABELING_SENTINEL%" echo            - Labeling   external plugin: plugins\labeling   repo: ANnoTation
if not exist "%LABELING_SENTINEL%" echo                         FIX: clone ANnoTation next to nativeApp, then run scripts\win\link-labeling.bat
if not exist "%AI4BI_SENTINEL%"   echo            - AI Report  submodule: vendor\AI4BI       repo: AI4BI
if not exist "%AI4BI_SENTINEL%"   echo                         FIX at repo root: git submodule update --init --recursive
echo.
echo  If AI Report was obtained via ZIP download, clone with submodules instead:
echo            git clone --recurse-submodules https://github.com/hctsaik/nativeApp.git
echo.
echo  (Full zh-Hant explanation: engine.log [CIM-PREFLIGHT], or README.md)
echo ============================================================
echo.
pause
exit /b 1
