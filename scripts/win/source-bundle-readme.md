# 安裝步驟（READ ME FIRST）

這是一個**已經拼裝好**的單一 bundle:AI4BI、LV、Labeling(ANnoTation)的原始碼
**已實體放進**正確位置(`sidecar\python-engine\vendor\AI4BI`、`vendor\LV`、
`plugins\labeling`)。所以你**不需要** git、不需要 `--recurse-submodules`、
不需要建任何 junction —— 那些步驟都做好了。解壓這個資料夾就可以直接裝。

> 本 bundle 由 `scripts\win\make-source-bundle.ps1` 自動產生。

## 前置需求
- **Node.js**(LTS)
- **Python 3.11**:打開 PowerShell 打 `py -3.11 --version` 要看得到 3.11.x。
  (PATH 上的 `python` 可能是別的版本,所以下面一律用 `py -3.11`。)

## 安裝(在本資料夾根目錄開 PowerShell,依序貼上)

```powershell
# 0) 繁體中文(CP950)機器務必先設這個,否則 pip 讀檔會 UnicodeDecodeError
$env:PYTHONUTF8 = "1"

# 1) Node 相依（若第一次卡在 esbuild 失敗，刪掉 node_modules 再跑一次即可）
npm install

# 2) Python 相依（都裝進 py -3.11）
py -3.11 -m pip install -r sidecar\python-engine\requirements.txt
py -3.11 -m pip install -e "sidecar\python-engine\vendor\AI4BI[llm]"
py -3.11 -m pip install -r sidecar\python-engine\plugins\labeling\requirements-labeling.txt

# 3) 驗證（要看到「[OK] 全部通過」才算成功）
powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1

# 4) 啟動
start-dev.bat
```

## 三個最常見的雷
1. **沒設 `PYTHONUTF8=1`** → pip 讀 requirements.txt 爆 `UnicodeDecodeError: 'cp950'`。先設就好。
2. **第一次 `npm install` 卡 esbuild**(`errno -4094`)→ `Remove-Item node_modules -Recurse -Force` 再跑一次。
3. **用錯 Python** → 一律 `py -3.11`,不要用裸 `python`/`pip`(可能是 Store 的 3.14 stub)。

> 更完整的官方安裝說明見 repo 根目錄 `INSTALL.md`（權威；舊 `docs\INSTALL.md` 已過時）。

## 注意
- 這個 bundle **沒有 git**。日後要更新,請取得新的 bundle 重裝,**不能** `git pull`。
- LV 的重相依(torch 等)會在「**第一次啟動 LV 工具**」時由平台自動建隔離 venv 安裝,
  不用手動裝;模型權重首次使用會自動下載。
- 打包成 exe 的版本才需要處理 Windows Smart App Control 簽章問題;用上面的 dev 方式啟動不受影響。
