# restore-electron-cache.ps1
# 在新電腦上還原 Electron 快取，讓 npm install 不需要重新下載
#
# 使用方式：
#   .\scripts\win\restore-electron-cache.ps1 -ZipPath .\electron-cache.zip

param(
    [Parameter(Mandatory)]
    [string]$ZipPath
)

$ErrorActionPreference = "Stop"

Write-Host "=== Electron 快取還原工具 ===" -ForegroundColor Cyan

# 確認 zip 存在
$absZip = [System.IO.Path]::GetFullPath($ZipPath)
if (-not (Test-Path $absZip)) {
    Write-Error "找不到 zip 檔：$absZip"
    exit 1
}

$tempDir         = "$env:TEMP\electron-cache-restore"
$electronCache   = "$env:LOCALAPPDATA\electron\Cache"
$electronBuilder = "$env:LOCALAPPDATA\electron-builder\Cache"

# 解壓縮到暫存目錄
Write-Host "`n解壓縮中..." -ForegroundColor Yellow
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
Expand-Archive -Path $absZip -DestinationPath $tempDir

# 還原 electron 快取
$srcElectron = "$tempDir\electron\Cache"
if (Test-Path $srcElectron) {
    Write-Host "`n還原 electron 快取 → $electronCache" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $electronCache -Force | Out-Null
    Copy-Item -Path "$srcElectron\*" -Destination "$electronCache\" -Recurse -Force
    $files = Get-ChildItem $electronCache | Where-Object { $_.Name -like "*.zip" }
    foreach ($f in $files) {
        $sizeMB = [math]::Round($f.Length / 1MB, 1)
        Write-Host "  + $($f.Name) ($sizeMB MB)"
    }
} else {
    Write-Host "zip 內沒有 electron 快取，略過" -ForegroundColor Gray
}

# 還原 electron-builder 快取
$srcBuilder = "$tempDir\electron-builder\Cache"
if (Test-Path $srcBuilder) {
    Write-Host "`n還原 electron-builder 快取 → $electronBuilder" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $electronBuilder -Force | Out-Null
    Copy-Item -Path "$srcBuilder\*" -Destination "$electronBuilder\" -Recurse -Force
    $dirs = Get-ChildItem $electronBuilder -Directory
    foreach ($d in $dirs) { Write-Host "  + $($d.Name)" }
} else {
    Write-Host "zip 內沒有 electron-builder 快取，略過" -ForegroundColor Gray
}

# 清理暫存
Remove-Item $tempDir -Recurse -Force

Write-Host "`n完成！現在可以執行 npm install 了" -ForegroundColor Green
