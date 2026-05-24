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
npm install
pip install -r sidecar/python-engine/requirements.txt
start-dev.bat
```

## 協作規則

- **語言**：一律使用繁體中文對話與撰寫說明（commit message 除外）
- **完成功能後**：同步更新對應文件（`docs/`、README），並新增或更新單元測試；
  確認 `npm run test:python` 與 `npm test` 全過後再 commit

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
`ToolProcessManager._make_env()`（engine.py ~line 596）在 spawn Streamlit 子程序時自動注入。

**不可直接執行任何 `sidecar/python-engine/tools/*.py`**（包括 `sheet_runner.py`），
必須透過 Electron 啟動整個 app，engine 才會正確注入這些變數。

## 常見錯誤與處理

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `Missing CIM_SHEET_ID or CIM_PLUGIN_ID` | 直接執行 `sheet_runner.py`，或 source zip 未含 `tools.sqlite` | 改用 `start-dev.bat` 啟動整個 app；或確認打包時有帶 `--include-file` |
| Electron app 啟動後印出 Node.js 版本就退出 | `ELECTRON_RUN_AS_NODE=1` 殘留在環境 | 移除該環境變數，或用 `apps/host-electron/launch-electron.js` workaround |
| `xanylabeling.exe` 被 WDAC 封鎖 | Windows Application Control 政策封鎖 uv trampoline | `012_output.py` 必須維持 `py -3.11 -c "import sys; sys.path.insert(...); from anylabeling.app import main; main()"`，不要改回直接執行 `xanylabeling.exe` |

## 架構地雷（容易踩的坑）

- **新增 postMessage 類型**：`packages/shared-protocol/src/index.js` 的 `MessageTypes` 和
  `index.test.js` 必須同步更新，否則 `isProtocolMessage` 會過濾掉新訊息
- **Portal 導航觸發**：任何會切換 tab 或 route 的邏輯，都要確認不會被
  `suppressPollerNavUntilRef`（2s poller 防覆蓋機制）或 `EXECUTE_START` suppress 蓋掉

## 工具開發規則

- 每個工具由兩個 Streamlit 程序組成（split-tool 架構）：`*_input.py` + `*_output.py`
- Output page **禁止** `time.sleep + st.rerun()` polling loop；portal 收到 `EXECUTE_COMPLETE` 後會自動 reload
- 新工具需在 `engine.py` 的 seed 區塊（`source="seed"`）新增 inline entry，並確認 `seed_tools()` 函式有呼叫到

詳見 `README.md` 的「開發新工具」章節。

## Streamlit Output 頁效能規則

**每次 rerun 都會重新執行整個 render 函式**，三條強制規則：

1. **mtime 驅動增量更新**：掃描結果快取在 `session_state`，rerun 時只做 `stat()` 比對，mtime 變才重讀 JSON。禁止對所有 item 直接跑 `json.loads()` / `Path.exists()` 迴圈。
2. **大型列表必須分頁（PAGE_SIZE = 50）**：列表超過 50 項時每次 rerun widget 樹線性爆炸，禁止一次 render 所有項目。
3. **禁止 loop 內 `list.index()`（O(N²)）**：loop 前建 `{item_id: idx}` dict，改為 O(1) 查表。

參考實作：`sidecar/python-engine/scripts/module_012/012_output.py`（`_scan_items` / `_incremental_refresh` / `_get_items`）

完整說明與程式碼範例見 `docs/patterns/streamlit_output_perf.md`

## 測試

```powershell
npm run test:python     # Python sidecar 單元測試
npm test                # JavaScript shared-protocol 單元測試
```

## 打包

- 原始碼 zip → `/package-source`
- Electron 可攜式安裝包 → `/package-build`
