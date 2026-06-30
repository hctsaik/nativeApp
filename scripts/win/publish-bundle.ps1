#requires -Version 5.1
<#
.SYNOPSIS
  Build the pre-assembled source bundle and PUBLISH it to the dedicated artifact
  repo (default: github.com/hctsaik/nativeApp_BundleZip) -- one command, commit
  and push included.

.DESCRIPTION
  1. Runs make-source-bundle.ps1 to produce a fresh, clean bundle zip.
  2. Clones the bundle repo, drops the zip in under a STABLE name
     (nativeApp-family-bundle.zip) so the download URL never changes, refreshes
     README.md (from scripts\win\bundle-repo-readme.md) and VERSION.txt.
  3. git add / commit / push. Skips the commit if the bundle is unchanged.

  Keeps large binaries OUT of the nativeApp source repo: source + tooling live in
  nativeApp, the built artifact lives in nativeApp_BundleZip.

  ASCII-ONLY so it parses on CP950 (Traditional Chinese) consoles.

.PARAMETER BundleRepoUrl
  HTTPS url of the artifact repo. Default: the nativeApp_BundleZip repo.

.PARAMETER RepoRoot
  nativeApp checkout. Default: two levels up from this script.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\win\publish-bundle.ps1
#>
[CmdletBinding()]
param(
    [string]$BundleRepoUrl = 'https://github.com/hctsaik/nativeApp_BundleZip.git',
    [string]$RepoRoot
)

$ErrorActionPreference = 'Stop'
function Info($m) { Write-Host "[publish] $m" -ForegroundColor Cyan }
function Die($m)  { Write-Host "[publish] ERROR: $m" -ForegroundColor Red; exit 1 }

# Native git writes normal progress to stderr; under EAP=Stop that would abort the
# script. Run git with EAP=Continue and judge success only by its exit code.
function Invoke-Git {
    param([string[]]$GitArgs)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $output = & git @GitArgs 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prev
    return [pscustomobject]@{ Code = $code; Output = $output }
}
function Show-Git($r) { $r.Output | ForEach-Object { Write-Host "    git: $_" } }

$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition }
if (-not $RepoRoot)  { $RepoRoot = (Resolve-Path (Join-Path $scriptDir '..\..')).Path }
$RepoRoot = (Resolve-Path $RepoRoot).Path

$STABLE = 'nativeApp-family-bundle.zip'
$env:GIT_TERMINAL_PROMPT = '0'   # fail fast instead of hanging on a credential prompt

# --- 1. build a fresh bundle ---------------------------------------------------
Info 'building bundle (make-source-bundle.ps1) ...'
# Child process so robocopy's exit-1 ("files copied") inside it does not leak out.
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $scriptDir 'make-source-bundle.ps1') -RepoRoot $RepoRoot
if ($LASTEXITCODE -ne 0) { Die "make-source-bundle.ps1 failed ($LASTEXITCODE)" }

$zip = Get-ChildItem (Join-Path $RepoRoot 'release') -Filter 'nativeApp-family-bundle-*.zip' -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $zip) { Die 'no bundle zip found in release\ after build' }
Info "built: $($zip.Name)  ($([math]::Round($zip.Length/1MB,2)) MB)"

# --- 2. clone the artifact repo ------------------------------------------------
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("cim-bundlerepo-" + (Get-Date -Format 'yyyyMMdd-HHmmss'))
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
Info "cloning $BundleRepoUrl ..."
$r = Invoke-Git @('clone', '--depth', '1', $BundleRepoUrl, $tmp)
if ($r.Code -ne 0) {
    Show-Git $r
    Die "git clone failed. Check network/credentials (Git Credential Manager or 'gh auth login').`n         Repo: $BundleRepoUrl"
}

# --- 3. publish the FLATTENED TREE so GitHub web "Download ZIP" is install-ready
#        (one extract, nothing missing) -- not a zip-inside-a-zip. ---------------
Remove-Item (Join-Path $tmp 'nativeApp') -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path $tmp $STABLE) -Force -ErrorAction SilentlyContinue   # drop any legacy zip-in-repo
Expand-Archive -Path $zip.FullName -DestinationPath $tmp -Force             # -> $tmp\nativeApp\
$readmeTpl = Join-Path $scriptDir 'bundle-repo-readme.md'
if (Test-Path $readmeTpl) { Copy-Item $readmeTpl (Join-Path $tmp 'README.md') -Force }

$srcCommit = ((Invoke-Git @('-C', $RepoRoot, 'rev-parse', '--short', 'HEAD')).Output | Select-Object -First 1).ToString().Trim()
$srcDate   = ((Invoke-Git @('-C', $RepoRoot, 'log', '-1', '--format=%cd', '--date=format:%Y-%m-%d')).Output | Select-Object -First 1).ToString().Trim()
$built     = Get-Date -Format 'yyyy-MM-dd HH:mm'
@(
    "bundle      : $STABLE"
    "contents    : nativeApp + AI4BI + LV + Labeling (pre-assembled source bundle)"
    "source repo : github.com/hctsaik/nativeApp @ $srcCommit"
    "source date : $srcDate"
    "built       : $built"
    "built by    : scripts/win/publish-bundle.ps1"
) | Set-Content -Encoding utf8 (Join-Path $tmp 'VERSION.txt')

# --- 4. commit + push (skip if nothing changed) -------------------------------
# -f so nothing is skipped even if a nested .gitignore in the tree would match (guarantee "nothing missing").
(Invoke-Git @('-C', $tmp, 'add', '-A', '-f')) | Out-Null
$st = Invoke-Git @('-C', $tmp, 'status', '--porcelain')
if (-not ($st.Output | Where-Object { "$_".Trim() })) {
    Info 'bundle is identical to what is already published; nothing to commit.'
} else {
    $c = Invoke-Git @('-C', $tmp, 'commit', '-q', '-m', "Publish bundle (nativeApp@$srcCommit, built $built)")
    if ($c.Code -ne 0) { Show-Git $c; Die 'git commit failed' }
    Info 'pushing ...'
    $p = Invoke-Git @('-C', $tmp, 'push', 'origin', 'HEAD:main')
    if ($p.Code -ne 0) { Show-Git $p; Die 'git push failed (auth / network?)' }
    Info "published nativeApp@$srcCommit"
}

# --- 5. cleanup ----------------------------------------------------------------
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
$repoWeb = $BundleRepoUrl -replace '\.git$', ''
Write-Host ''
Write-Host "Done. Latest bundle is live at: $repoWeb" -ForegroundColor Green
exit 0
