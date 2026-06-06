<#
.SYNOPSIS
  Download a relocatable, self-contained CPython 3.11 (python-build-standalone)
  and stage it for the Electron release bundle.

.DESCRIPTION
  A packaged release ships its own Python so a clean factory machine needs no
  separately-installed interpreter. This Python is NOT the engine runtime
  (that is the frozen engine.exe); it is the BASE interpreter that the engine's
  per-tool dependency resolver (core/tool_deps.base_python) uses to build
  isolated per-tool venvs at runtime -- the frozen engine.exe has a read-only
  embedded Python and cannot `-m venv` itself.

  Unlike the official "embeddable" zip (which deliberately omits pip and venv),
  python-build-standalone ships a full stdlib + pip + venv and is relocatable,
  which is exactly what `python -m venv` + `pip install` need.

  IMPORTANT: the version MUST match the Python that engine.exe was frozen with
  (3.11), because per-tool venv site-packages are injected into the frozen
  engine's PYTHONPATH and must be ABI-compatible.

  Output: <repo>/apps/host-electron/python-runtime/python/python.exe
  (consumed by package.json build.extraResources -> resources/python/).

.PARAMETER Version
  CPython version, e.g. 3.11.9. Must be a 3.11.x.

.PARAMETER Tag
  python-build-standalone release tag (date), e.g. 20240814.

.PARAMETER Force
  Re-download even if a staged python.exe already exists.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\win\fetch-standalone-python.ps1
#>
[CmdletBinding()]
param(
    [string]$Version = "3.11.9",
    [string]$Tag = "20240814",
    [string]$Arch = "x86_64-pc-windows-msvc",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

if ($Version -notlike "3.11.*") {
    throw "Version must be 3.11.x (must match the frozen engine.exe Python). Got: $Version"
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$destRoot = Join-Path $repoRoot "apps\host-electron\python-runtime"
$pythonExe = Join-Path $destRoot "python\python.exe"

if ((Test-Path $pythonExe) -and -not $Force) {
    $have = (& $pythonExe -c "import platform;print(platform.python_version())").Trim()
    Write-Host "[fetch-python] Already staged: $pythonExe (Python $have). Use -Force to re-download." -ForegroundColor Green
    return
}

$asset = "cpython-$Version+$Tag-$Arch-install_only.tar.gz"
$url = "https://github.com/astral-sh/python-build-standalone/releases/download/$Tag/$asset"
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) $asset

Write-Host "[fetch-python] Downloading $url" -ForegroundColor Cyan
[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile $tmp -UseBasicParsing

if (Test-Path $destRoot) { Remove-Item -Recurse -Force $destRoot }
New-Item -ItemType Directory -Force -Path $destRoot | Out-Null

# tar ships with Windows 10+; install_only archives extract to a top-level python/.
Write-Host "[fetch-python] Extracting to $destRoot" -ForegroundColor Cyan
& tar -xzf $tmp -C $destRoot
if ($LASTEXITCODE -ne 0) { throw "tar extraction failed (exit $LASTEXITCODE)" }
Remove-Item -Force $tmp

if (-not (Test-Path $pythonExe)) {
    throw "Expected $pythonExe after extraction but it is missing."
}

$ver = (& $pythonExe -c "import platform;print(platform.python_version())").Trim()
# Sanity: venv + pip must be usable (the whole point vs the embeddable zip).
& $pythonExe -c "import venv, ensurepip" 2>$null
if ($LASTEXITCODE -ne 0) { throw "Staged Python lacks venv/ensurepip -- wrong distribution?" }

Write-Host "[fetch-python] OK: Python $ver staged at $pythonExe (venv+pip present)." -ForegroundColor Green
Write-Host "[fetch-python] electron-builder will copy it to resources/python/ (see package.json)." -ForegroundColor DarkGray
