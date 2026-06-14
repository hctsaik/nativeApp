@echo off
setlocal
rem ============================================================================
rem  link-labeling.bat  --  mount the external Labeling plugin into the platform.
rem ----------------------------------------------------------------------------
rem  Labeling lives in its own repo (ANnoTation) and is developed independently.
rem  The platform loads it from sidecar\python-engine\plugins\labeling, so we
rem  mount the external clone there with a directory JUNCTION (no admin needed).
rem
rem  Default source: a sibling "ANnoTation" folder next to this nativeApp repo.
rem  Override with:  set "LABELING_SRC=D:\path\to\ANnoTation"  before running.
rem  ASCII-ONLY ON PURPOSE: runs on machines whose console codepage we do not
rem  control (Traditional-Chinese machines default to CP950).
rem ============================================================================
set "REPO_ROOT=%~dp0..\.."
set "LINK=%REPO_ROOT%\sidecar\python-engine\plugins\labeling"
if not defined LABELING_SRC set "LABELING_SRC=%REPO_ROOT%\..\ANnoTation"

echo [link-labeling] source     : %LABELING_SRC%
echo [link-labeling] mount point : %LINK%

if not exist "%LABELING_SRC%\plugin.manifest.yaml" (
  echo.
  echo [link-labeling] ERROR: Labeling source not found at the path above.
  echo.
  echo   Clone it next to nativeApp first:
  echo       git clone https://github.com/hctsaik/ANnoTation.git "%LABELING_SRC%"
  echo   Or point LABELING_SRC at an existing clone, then re-run:
  echo       set "LABELING_SRC=D:\path\to\ANnoTation"
  echo.
  exit /b 1
)

if exist "%LINK%\plugin.manifest.yaml" (
  echo [link-labeling] already mounted -- nothing to do.
  exit /b 0
)

if exist "%LINK%" (
  echo [link-labeling] ERROR: %LINK% exists but is not the labeling plugin.
  echo                 Remove it and re-run.
  exit /b 1
)

mklink /J "%LINK%" "%LABELING_SRC%"
if errorlevel 1 (
  echo [link-labeling] ERROR: failed to create junction.
  exit /b 1
)
echo [link-labeling] OK: junction created.
exit /b 0
