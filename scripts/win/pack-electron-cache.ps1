# pack-electron-cache.ps1
# Usage:
#   .\scripts\win\pack-electron-cache.ps1
#   .\scripts\win\pack-electron-cache.ps1 -OutputPath D:\share\electron-cache.zip

param(
    # Default lands at repo root (script now lives in scripts/win/, so two levels up).
    [string]$OutputPath = "$PSScriptRoot\..\..\electron-cache.zip"
)

$ErrorActionPreference = "Stop"

$electronCache   = "$env:LOCALAPPDATA\electron\Cache"
$electronBuilder = "$env:LOCALAPPDATA\electron-builder\Cache"
$tempDir         = "$env:TEMP\electron-cache-pack"

Write-Host "=== Electron Cache Packer ===" -ForegroundColor Cyan

if (-not (Test-Path $electronCache)) {
    Write-Error "Electron cache not found: $electronCache"
    exit 1
}

if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path "$tempDir\electron\Cache" | Out-Null

# Copy x64 zip only
Write-Host "`nCopying electron cache (x64)..." -ForegroundColor Yellow
Get-ChildItem $electronCache | Where-Object { $_.Name -like "*-win32-x64.zip" -and $_.Name -like "*v39.8.9*" } | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination "$tempDir\electron\Cache\"
    $sizeMB = [math]::Round($_.Length / 1MB, 1)
    Write-Host "  + $($_.Name) ($sizeMB MB)"
}


# Compress
$absOutput = [System.IO.Path]::GetFullPath($OutputPath)
Write-Host "`nCompressing -> $absOutput" -ForegroundColor Yellow
if (Test-Path $absOutput) { Remove-Item $absOutput -Force }
Compress-Archive -Path "$tempDir\*" -DestinationPath $absOutput

$sizeMB = [math]::Round((Get-Item $absOutput).Length / 1MB, 1)
Write-Host "`nDone! Size: $sizeMB MB" -ForegroundColor Green
Write-Host "Run on the new machine:" -ForegroundColor Cyan
Write-Host "  .\scripts\restore-electron-cache.ps1 -ZipPath electron-cache.zip"

Remove-Item $tempDir -Recurse -Force
