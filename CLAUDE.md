# CIM Hybrid Edge Platform — AI 協作指引

## 啟動方式

### 開發模式
```powershell
# 根目錄執行（會開 Electron + React portal + Python engine）
start-dev.bat
# 或
cd apps/host-electron && npm run dev
```

### 首次設定（解壓 source zip 或全新 clone 後）
```powershell
python restore_gmail_safe_filenames.py   # 僅 Gmail-safe zip 需要
npm install
pip install -r sidecar/python-engine/requirements.txt
start-dev.bat
```

## 架構關鍵點

### 啟動鏈
```
start-dev.bat
  → Electron (apps/host-electron)
    → Python FastAPI engine (sidecar/python-engine/engine.py)
      → Streamlit 子程序（按需啟動，含注入環境變數）
```

### 環境變數由 engine 注入，不可手動設定
`CIM_SHEET_ID`、`CIM_PLUGIN_ID`、`CIM_TOOL_ID`、`CIM_LOG_DIR` 等變數由
`ToolProcessManager._make_env()`（engine.py ~line 484）在 spawn Streamlit 子程序時自動注入。

**不可直接執行任何 `sidecar/python-engine/tools/*.py`**（包括 `sheet_runner.py`），
必須透過 Electron 啟動整個 app，engine 才會正確注入這些變數。

## 常見錯誤與處理

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `Missing CIM_SHEET_ID or CIM_PLUGIN_ID` | 直接執行 `sheet_runner.py`，或 source zip 未含 `tools.sqlite` | 改用 `start-dev.bat` 啟動整個 app；或確認打包時有帶 `--include-file` |
| Electron app 啟動後印出 Node.js 版本就退出 | `ELECTRON_RUN_AS_NODE=1` 殘留在環境 | 移除該環境變數，或用 `apps/host-electron/launch-electron.js` workaround |
| `xanylabeling.exe` 被 WDAC 封鎖 | Windows Application Control 政策 | `012_output.py` 已改用 `python.exe -c "from anylabeling.app import main; main()"` 繞過 |

## 工具開發規則

- 每個工具由兩個 Streamlit 程序組成（split-tool 架構）：`*_input.py` + `*_output.py`
- Output page **禁止** `time.sleep + st.rerun()` polling loop；portal 收到 `EXECUTE_COMPLETE` 後會自動 reload
- 新工具需在 `engine.py` 的 `seed_tools` 清單中新增 entry

詳見 `README.md` 的「開發新工具」章節。

## 測試

```powershell
npm run test:python     # Python sidecar 單元測試
npm test                # JavaScript shared-protocol 單元測試
```

## 日誌位置

`apps/host-electron/logs/`（`CIM_LOG_DIR`）

## 打包

```powershell
# 原始碼 zip（換電腦用，含 sheet 工具資料庫設定）
python packages/source-code-packager/scripts/package_source_zip.py `
  --root . --include-all `
  --exclude-dir .venv-xanylabeling --exclude-dir .claude `
  --exclude-dir external_exe --exclude-dir release --exclude-dir _release --exclude-dir testData `
  --exclude-dir logs --exclude-dir tmp `
  --include-file "apps/host-electron/logs/data/tools.sqlite" `
  --name ../nativeApp_source

# 原始碼 zip（Gmail 安全模式，無資料庫）
python packages/source-code-packager/scripts/package_source_zip.py `
  --root . --include-all `
  --exclude-dir .venv-xanylabeling --exclude-dir .claude `
  --exclude-dir external_exe --exclude-dir release --exclude-dir _release --exclude-dir testData `
  --gmail-safe --name ../nativeApp_source_gmail_safe

# Electron 可攜式安裝包
npm run build
cd sidecar/python-engine && python -m PyInstaller engine.spec
npm run package:portable
```
