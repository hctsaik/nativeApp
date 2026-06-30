#requires -Version 5.1
<#
.SYNOPSIS
  Build a self-contained, pre-assembled SOURCE bundle zip of the CIM platform
  (nativeApp + AI4BI + LV + Labeling) for machines that can only download ZIPs
  (no git / no submodule / no junction).

.DESCRIPTION
  Flattens the live, fully-wired checkout into ONE tree: the AI4BI and LV
  submodules and the Labeling junction are copied in as REAL content under
  vendor\AI4BI, vendor\LV and plugins\labeling. Build artifacts (node_modules,
  .git, caches, venvs, release output, bundled python runtime) are excluded.
  The recipient just unzips and runs npm install + pip install -- see the
  bundled 00-READ-ME-FIRST.md.

  ASCII-ONLY ON PURPOSE so it parses correctly on CP950 (Traditional Chinese)
  consoles. The Chinese quick-start lives in source-bundle-readme.md (UTF-8) and
  is copied byte-wise, never decoded by this script.

.PARAMETER RepoRoot
  Path to the nativeApp checkout. Default: two levels up from this script.

.PARAMETER OutDir
  Where to write the zip. Default: <RepoRoot>\release (already gitignored).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\win\make-source-bundle.ps1
#>
[CmdletBinding()]
param(
    [string]$RepoRoot,
    [string]$OutDir
)

$ErrorActionPreference = 'Stop'
function Info($m) { Write-Host "[bundle] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[bundle] ERROR: $m" -ForegroundColor Red; exit 1 }

# Resolve script dir robustly ($PSScriptRoot is empty inside param defaults under -File).
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }

if (-not $RepoRoot) { $RepoRoot = (Resolve-Path (Join-Path $scriptDir '..\..')).Path }
$RepoRoot = (Resolve-Path $RepoRoot).Path
if (-not $OutDir) { $OutDir = Join-Path $RepoRoot 'release' }
Info "repo root : $RepoRoot"

# --- 1. the three external mount points + a signature file that proves each is populated ---
$mounts = @(
    @{ Rel = 'sidecar\python-engine\vendor\AI4BI';        Sig = 'pyproject.toml';                  Label = 'AI4BI (submodule)' }
    @{ Rel = 'sidecar\python-engine\vendor\LV';            Sig = 'requirements.txt';                Label = 'LV (submodule)' }
    @{ Rel = 'sidecar\python-engine\plugins\labeling';     Sig = 'plugin.manifest.yaml';            Label = 'Labeling (junction -> ANnoTation)' }
    @{ Rel = 'sidecar\python-engine\plugins\cim-modules';  Sig = 'modules\module_001\plugin.yaml';  Label = 'CV Modules (submodule -> nativeApp_modules)' }
)

foreach ($m in $mounts) {
    $mp = Join-Path $RepoRoot $m.Rel
    if (-not (Test-Path $mp)) {
        Die "$($m.Label) missing at $($m.Rel).`n         Fix: git submodule update --init --recursive  AND  scripts\win\link-labeling.bat"
    }
    $item = Get-Item $mp
    # junction/symlink -> follow to its target; a real (submodule) dir -> use itself
    if ($item.LinkType) { $src = @($item.Target)[0] } else { $src = $mp }
    if (-not (Test-Path (Join-Path $src $m.Sig))) {
        Die "$($m.Label) looks empty ($($m.Sig) not found under $src).`n         Submodule not checked out, or junction not mounted."
    }
    $m.Src = $src
    Info "mount OK  : $($m.Rel)  <-  $src"
}

# --- 2. staging tree in TEMP (never pollutes the repo) ---
$stamp     = Get-Date -Format 'yyyyMMdd-HHmm'
$stageRoot = Join-Path ([System.IO.Path]::GetTempPath()) "cim-bundle-$stamp"
$stage     = Join-Path $stageRoot 'nativeApp'
if (Test-Path $stageRoot) { Remove-Item $stageRoot -Recurse -Force }
New-Item -ItemType Directory -Force $stage | Out-Null

$xd = @('node_modules', '__pycache__', '.git', '.github', 'dist', 'build', '.venv',
        '.venv-xanylabeling', '.tool-venvs', 'python-runtime', 'logs', 'tmp', 'release',
        '_release', '.pytest_cache', '.vite', '.mypy_cache')
# Model weights / derived caches are NEVER source: they re-download on first use
# (LV setup_models.py, labeling/transformers hubs) or rebuild (tools.sqlite). A
# stale checkout can hold ~500 MB of these, so drop them by type + a size backstop.
$xf = @('*.pyc', '*.pyo', '*.log', '.git',
        '*.pth', '*.pt', '*.onnx', '*.safetensors', '*.ckpt', '*.pb', '*.h5', '*.tflite',
        '*.sqlite', '*.sqlite-wal', '*.sqlite-shm')
$xdMounts = $mounts | ForEach-Object { Join-Path $RepoRoot $_.Rel }
# /MAX:52428800 = skip any single file > 50 MB (backstop for stray weights/datasets;
# real source files are tiny -- the repo's largest legit file is a few-MB doc).
$opt = @('/E', '/XJ', '/MAX:52428800', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')

Info 'copying platform tree (excluding the 3 mounts + artifacts) ...'
robocopy $RepoRoot $stage @opt /XD @xd @xdMounts /XF @xf | Out-Null
if ($LASTEXITCODE -ge 8) { Die "robocopy platform tree failed (code $LASTEXITCODE)" }

foreach ($m in $mounts) {
    Info "copying $($m.Label) as real content ..."
    robocopy $m.Src (Join-Path $stage $m.Rel) @opt /XD @xd /XF @xf | Out-Null
    if ($LASTEXITCODE -ge 8) { Die "robocopy $($m.Label) failed (code $LASTEXITCODE)" }
}

# --- 3. drop the Chinese quick-start (copied byte-wise; name forced ASCII so it sorts first) ---
$readme = Join-Path $scriptDir 'source-bundle-readme.md'
if (Test-Path $readme) {
    Copy-Item $readme (Join-Path $stage '00-READ-ME-FIRST.md') -Force
} else {
    Info 'WARN: source-bundle-readme.md not found next to script; bundle ships without a quick-start.'
}

# --- 4. zip ---
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force $OutDir | Out-Null }
$zip = Join-Path $OutDir "nativeApp-family-bundle-$stamp.zip"
if (Test-Path $zip) { Remove-Item $zip -Force }
Info "compressing -> $zip"
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal

# --- 5. summary + cleanup ---
$mb    = [math]::Round((Get-Item $zip).Length / 1MB, 2)
$files = (Get-ChildItem $stage -Recurse -File -Force | Measure-Object).Count
Remove-Item $stageRoot -Recurse -Force -ErrorAction SilentlyContinue

Info "DONE: $zip"
Info "      $mb MB, $files files, top folder = nativeApp\"
Write-Host ''
Write-Host 'Distribute that single zip. Recipient: unzip -> open 00-READ-ME-FIRST.md.' -ForegroundColor Green
# robocopy leaves $LASTEXITCODE=1 (="files copied"); force a clean success code.
exit 0
