#requires -Version 5.1
<#
.SYNOPSIS
  CIM 平台 + AI4BI 安裝驗證（doctor）。逐項檢查前置需求與安裝狀態；
  全部 PASS 代表 start-dev.bat 能乾淨啟動整個 app（含 📊 AI Report / AI4BI）。

.DESCRIPTION
  頭號地雷：AI4BI 必須裝進「start-dev.bat 啟動 engine 時實際使用的那一支
  Python 3.11」（engine 在該直譯器裡 import ai4bi）。本腳本沿用 start-dev.bat
  的解析邏輯（$env:PYTHON > 舊版 set PYTHON= > 自動偵測 py -3.11），用同一支
  直譯器驗證 ai4bi 是否可 import，直接擋掉「裝到別支 Python」這個最常見的失敗。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:fail = 0
$script:warn = 0

function Pass($m)    { Write-Host "  [PASS] $m" -ForegroundColor Green }
function Fail($m)    { Write-Host "  [FAIL] $m" -ForegroundColor Red;    $script:fail++ }
function Warn($m)    { Write-Host "  [WARN] $m" -ForegroundColor Yellow; $script:warn++ }
function Section($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }

Write-Host "CIM 平台 + AI4BI 安裝驗證" -ForegroundColor White
Write-Host "repo root: $repoRoot"

# ── 1. 前置工具 ──────────────────────────────────────────────
Section "前置工具"
foreach ($t in 'git', 'node', 'npm') {
    $c = Get-Command $t -ErrorAction SilentlyContinue
    if ($c) { Pass "$t 存在（$($c.Source)）" } else { Fail "$t 找不到 — 請先安裝" }
}

# ── 2. 解析 start-dev.bat 實際使用的 Python ─────────────────
Section "Engine Python（start-dev.bat 實際會啟動的那一支）"
$startDev = Join-Path $repoRoot 'start-dev.bat'
$py = $null
if ($env:PYTHON) {
    $py = $env:PYTHON
    Warn "目前 shell 已設 `$env:PYTHON=$py（執行時會覆蓋 start-dev.bat 的自動偵測）"
} elseif (Test-Path $startDev) {
    # start-dev.bat 可能仍硬編 set PYTHON=（舊版），或改為自動偵測（新版）。
    $line = Select-String -Path $startDev -Pattern '^\s*set\s+PYTHON=(.+)$' | Select-Object -First 1
    if ($line -and $line.Matches[0].Groups[1].Value.Trim()) {
        $py = $line.Matches[0].Groups[1].Value.Trim()
    } else {
        # 鏡像 start-dev.bat 的自動偵測：優先 py -3.11。
        $detected = (& py -3.11 -c "import sys;print(sys.executable)" 2>$null)
        if ($detected) { $py = $detected.Trim() }
    }
}
if (-not $py) { $py = 'python' }

# 解析成實際的 exe 路徑
$pyExe = $null
if (Test-Path $py) {
    $pyExe = (Resolve-Path $py).Path
} else {
    $cmd = Get-Command $py -ErrorAction SilentlyContinue
    if ($cmd) { $pyExe = $cmd.Source }
}

if (-not $pyExe) {
    Fail "找不到 Python：'$py' 既不是有效路徑、也不在 PATH 上。"
    Write-Host "         → 安裝 Python 3.11（讓 'py -3.11' 可用），或在執行前設 `$env:PYTHON 指向其 python.exe。" -ForegroundColor DarkGray
} else {
    Pass "Engine 將使用：$pyExe"
    $ver = (& $pyExe -c "import sys;print('%d.%d.%d'%sys.version_info[:3])" 2>$null)
    if ($ver -like '3.11.*') { Pass "版本 $ver（符合 3.11）" }
    else { Fail "版本 $ver — 需要 3.11.x（與 engine host 直譯器對齊）" }
}

# ── 3. AI4BI submodule ──────────────────────────────────────
Section "AI4BI submodule"
$ai4biApp = Join-Path $repoRoot 'sidecar\python-engine\vendor\AI4BI\ai4bi\ui\app.py'
if (Test-Path $ai4biApp) {
    Pass "submodule 已 checkout（找到 ai4bi/ui/app.py）"
} else {
    Fail "vendor/AI4BI 未初始化"
    Write-Host "         → 執行：git submodule update --init --recursive" -ForegroundColor DarkGray
}

# ── 4. Node 依賴 ────────────────────────────────────────────
Section "Node 依賴"
if (Test-Path (Join-Path $repoRoot 'node_modules')) {
    Pass "node_modules 存在"
} else {
    Fail "node_modules 不存在"
    Write-Host "         → 執行：npm install" -ForegroundColor DarkGray
}

# ── 5. Python 套件（在 engine 的那支直譯器內驗證）──────────
if ($pyExe) {
    Section "Python 套件（在 engine 直譯器內）"
    $engineReq = "& `"$pyExe`" -m pip install -r `"$repoRoot\sidecar\python-engine\requirements.txt`""
    $ai4biReq  = "& `"$pyExe`" -m pip install -e `"$repoRoot\sidecar\python-engine\vendor\AI4BI[llm]`""

    $modules = @(
        @{ name = 'fastapi';   group = 'engine'; hint = $engineReq },
        @{ name = 'streamlit'; group = 'engine'; hint = $engineReq },
        @{ name = 'pandas';    group = 'engine'; hint = $engineReq },
        @{ name = 'ai4bi';     group = 'ai4bi';  hint = $ai4biReq },
        @{ name = 'duckdb';    group = 'ai4bi';  hint = $ai4biReq },
        @{ name = 'plotly';    group = 'ai4bi';  hint = $ai4biReq }
    )
    foreach ($m in $modules) {
        & $pyExe -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$($m.name)') else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Pass "$($m.name) 可匯入"
        } else {
            Fail "$($m.name) 缺少（$($m.group) 依賴）"
            Write-Host "         → $($m.hint)" -ForegroundColor DarkGray
        }
    }
    # AI4BI 進入點（bi_runner.py 實際載入的模組）
    & $pyExe -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('ai4bi.ui.app') else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Pass "進入點 ai4bi.ui.app 可載入（bi_runner 能啟動 AI4BI）"
    } else {
        Fail "ai4bi.ui.app 載不到 — AI4BI 沒有正確裝進這支 python（最常見：裝到別支）"
        Write-Host "         → $ai4biReq" -ForegroundColor DarkGray
    }
}

# ── 6. Labeling 影像標註（與 AI4BI 並行的獨立功能）─────────
Section "Labeling 影像標註"
$labelingDir = Join-Path $repoRoot 'sidecar\python-engine\plugins\labeling'
if (Test-Path (Join-Path $labelingDir 'plugin.manifest.yaml')) {
    Pass "labeling 外掛已掛載（plugins/labeling，外部 repo: ANnoTation）"
} else {
    Fail "找不到 plugins/labeling/plugin.manifest.yaml（外部外掛未掛載）"
    Write-Host "         → 先把 ANnoTation clone 到 nativeApp 旁，再執行 scripts\win\link-labeling.bat" -ForegroundColor DarkGray
}
# 平台契約檔：labeling 依賴的 host 共用碼（見 docs/platform/labeling-independence-plan.md §2）
$contractFiles = @(
    'sidecar\python-engine\core',
    'sidecar\python-engine\scripts\shared\_config_base.py',
    'sidecar\python-engine\scripts\shared\_help.py',
    'sidecar\python-engine\scripts\shared\_manifest_db.py',
    'sidecar\python-engine\scripts\shared\ui_components.py',
    'sidecar\python-engine\tools\db_utils.py'
)
$missingContract = @($contractFiles | Where-Object { -not (Test-Path (Join-Path $repoRoot $_)) })
if ($missingContract.Count -eq 0) {
    Pass "平台契約齊全（core/ + 5 個共用工具檔）"
} else {
    Fail "缺少 labeling 契約檔：$($missingContract -join ', ')"
}
if ($pyExe) {
    $labelingReq = "& `"$pyExe`" -m pip install -r `"$repoRoot\sidecar\python-engine\plugins\labeling\requirements-labeling.txt`""
    # Annotation UI 相依（labeling 專屬 — 缺了基本標注會壞）
    foreach ($mod in 'streamlit_image_annotation', 'streamlit_autorefresh') {
        & $pyExe -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$mod') else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { Pass "$mod 可匯入（annotation UI）" }
        else { Fail "$mod 缺少（annotation UI）"; Write-Host "         → $labelingReq" -ForegroundColor DarkGray }
    }
    # AI 預標相依（選用 — 缺了 AI Pre-labeling 不可用，基本標注不受影響）
    foreach ($mod in 'ultralytics', 'torch') {
        & $pyExe -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('$mod') else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { Pass "$mod 可匯入（AI 預標）" }
        else { Warn "$mod 未裝 — AI Pre-labeling (module_016) 不可用，基本標注不受影響" }
    }
}

# ── 7. LLM 模式（選用，資訊性）─────────────────────────────
Section "LLM 模式（選用）"
if ($env:ANTHROPIC_API_KEY) {
    Pass "ANTHROPIC_API_KEY 已設 — 可用自然語言/LLM 模式"
} else {
    Warn "未設 ANTHROPIC_API_KEY — AI4BI 會走非-LLM 模式（仍可正常使用）"
}

# ── 結果 ────────────────────────────────────────────────────
Section "結果"
if ($script:fail -eq 0) {
    Write-Host "[OK] 全部通過（提醒 $($script:warn) 項）。start-dev.bat 應可乾淨啟動，含 AI Report (AI4BI) 與 影像標註。" -ForegroundColor Green
    exit 0
} else {
    Write-Host "[X] 失敗 $($script:fail) 項、提醒 $($script:warn) 項。請依上面 → 的指示修正後再跑一次。" -ForegroundColor Red
    exit 1
}
