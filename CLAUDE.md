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

### Sheet 驅動機制
新 workflow sheet 由 YAML 定義，engine 啟動時自動載入（掃 `sidecar/python-engine/sheets/*.yaml` **與** `plugins/*/sheets/*.yaml`）。
加一個新 sheet 只需新增 YAML 檔，不需修改 engine.py。

目前只有一個 annotation sheet：`plugins/labeling/sheets/annotation.yaml`（🐜 影像標註，4 tabs）— 已隨架構重構移入 Labeling plugin。

### 環境變數由 engine 注入，不可手動設定
`CIM_SHEET_ID`、`CIM_PLUGIN_ID`、`CIM_TOOL_ID`、`CIM_LOG_DIR` 等變數由
`ToolProcessManager._make_env()`（engine.py ~line 596）在 spawn Streamlit 子程序時自動注入。

**不可直接執行任何 `sidecar/python-engine/tools/*.py`**（包括 `sheet_runner.py`），
必須透過 Electron 啟動整個 app，engine 才會正確注入這些變數。

## 共用功能在哪（DB / Log / config / 共用 UI）

**開發新模組/plugin 前先查權威索引：[`docs/platform/shared-components.md`](docs/platform/shared-components.md)**，不要各自重造。重點：

- **Log**：`tools/log_utils.py` 的 `get_logger(name)`
- **Manifest DB DAL**：`scripts/shared/_manifest_db.py`（函式收 `db_path`）
- **通用 SQLite**：`tools/db_utils.py` 的 `SimpleDAO`
- **工具結果/通訊**：`tools/tool_result.py`、`tools/tool_comms.py`
- **模組設定/路徑**：各模組 `scripts/module_NNN/_config.py`（目前重複，重構 P2 會抽共用 helper）
- **共用 Streamlit UI**：`scripts/shared/ui_components.py`、`image_widget.py`、`_help.py`（見 `/common-component`）
- **外部系統連接**：`cim_platform/connector.py`（`ExternalSystemConnector`）
- **標注領域服務**：`annotation/services.py`（`AnnotationService`）

> 平台正進行架構重構（共用碼→`core/`、Labeling→`plugins/labeling/`、凍結數字 ID）。
> 路線圖與決策見 [`docs/platform/architecture-restructure-discussion.md`](docs/platform/architecture-restructure-discussion.md)。
> 平台級文件一律放 `docs/platform/`，勿在 `docs/` 根目錄建同名重複檔。

## 常見錯誤與處理

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `Missing CIM_SHEET_ID or CIM_PLUGIN_ID` | 直接執行 `sheet_runner.py`，或 source zip 未含 `tools.sqlite` | 改用 `start-dev.bat` 啟動整個 app；或確認打包時有帶 `--include-file` |
| Electron app 啟動後印出 Node.js 版本就退出 | `ELECTRON_RUN_AS_NODE=1` 殘留在環境 | 移除該環境變數，或用 `apps/host-electron/launch-electron.js` workaround |
| `xanylabeling.exe` 被 WDAC 封鎖 | Windows Application Control 政策封鎖 uv trampoline | `012_output.py` 必須維持 `py -3.11 -c "import sys; sys.path.insert(...); from anylabeling.app import main; main()"`，不要改回直接執行 `xanylabeling.exe` |
| iWISC 任務列表空白 | 外部 iWISC server 未啟動，或尚未註冊外部系統連線 | 啟動 iwsc-sample-server（port 8765）；**註冊外部系統有 no-code GUI 表單**：管理中心 Tools → External（`management_runner._render_external_system_register`，寫入 `config/external_systems.yaml`，token 走環境變數）；亦可用 `AnnotationService.register_tenant` / annotation MCP `register_tenant`。非-REST 協定用 `python tools/scaffold.py connector <name>` 產 connector 骨架（放 `core/integrations/connectors/`，啟動時 `core.integrations.registry.autodiscover()` 自動註冊）|

## 架構地雷（容易踩的坑）

- **新增 postMessage 類型**：`packages/shared-protocol/src/index.js` 的 `MessageTypes` 和
  `index.test.js` 必須同步更新，否則 `isProtocolMessage` 會過濾掉新訊息
- **Portal 導航觸發**：任何會切換 tab 或 route 的邏輯，都要確認不會被
  `suppressPollerNavUntilRef`（2s poller 防覆蓋機制）或 `EXECUTE_START` suppress 蓋掉

## 工具開發規則

- **No-code input（宣告式表單）**：簡單工具可**不寫 `*_input.py`**，改在 `plugin.yaml` 用 `form:` 宣告輸入欄位（type: text/number/integer/select/multiselect/checkbox/slider/textarea/file），框架（`cv_framework_runner`）會自動渲染表單並把值傳給 `execute_logic(params)`。範例見 `scripts/module_007/`（零 input 程式碼）；表單引擎 `core/forms.py`。只需寫 `*_process.py`（運算）與 `*_output.py`（呈現）。
- 進階/自訂 UI 才需手寫 `*_input.py`（`render_input()` 回傳 params dict）。
- 每個工具由兩個 Streamlit 程序組成（split-tool 架構）：`*_input.py`（或宣告式 `form:`）+ `*_output.py`
- Output page **禁止** `time.sleep + st.rerun()` polling loop；portal 收到 `EXECUTE_COMPLETE` 後會自動 reload
- 新工具需在 `engine.py` 的 seed 區塊（`source="seed"`）新增 inline entry，並確認 `seed_tools()` 函式有呼叫到
- 新增 Sheet Tab：在 `sidecar/python-engine/sheets/` 或 `plugins/<plugin>/sheets/` 建立或修改 YAML，而非修改 engine.py
- 廢棄模組（010、019、022-025）：已標記 `enabled: false`，程式碼保留不刪除

詳見 `README.md` 的「開發新工具」章節。

## Streamlit Output 頁效能規則

**每次 rerun 都會重新執行整個 render 函式**，三條強制規則：

1. **mtime 驅動增量更新**：掃描結果快取在 `session_state`，rerun 時只做 `stat()` 比對，mtime 變才重讀 JSON。禁止對所有 item 直接跑 `json.loads()` / `Path.exists()` 迴圈。
2. **大型列表必須分頁（PAGE_SIZE = 50）**：列表超過 50 項時每次 rerun widget 樹線性爆炸，禁止一次 render 所有項目。
3. **禁止 loop 內 `list.index()`（O(N²)）**：loop 前建 `{item_id: idx}` dict，改為 O(1) 查表。

參考實作：`sidecar/python-engine/scripts/module_012/012_output.py`（`_scan_items` / `_incremental_refresh` / `_get_items`）

完整說明與程式碼範例見 `docs/patterns/streamlit_output_perf.md`

## GUI 除錯流程（MCP + Log）

當 GUI 出現錯誤、或新增/修改功能後需要驗證行為時，標準流程：

### 1. 用 MCP 截圖確認畫面狀態
```
mcp__cim-gui__browser_screenshot   → 確認目前 UI 呈現
mcp__cim-gui__assert_text          → 確認特定文字出現
mcp__cim-gui__assert_visible       → 確認元件可見
mcp__cim-gui__browser_click        → 觸發按鈕（注意：原生 <select> 無法用 MCP 操作）
```

### 2. 讀 Log 確認後端實際執行路徑
| 層級 | Log 檔位置 |
|------|-----------|
| Streamlit module input | `apps/host-electron/logs/streamlit-module_XXX-input.log` |
| Streamlit module output | `apps/host-electron/logs/streamlit-module_XXX-output.log` |
| Python process/business logic | `tmp/cim_log/module_XXX_process.log` |
| FastAPI engine | `apps/host-electron/logs/engine.log` |

### 3. 除錯準則
- **MCP 無法操作原生 `<select>`**（Glide Data Grid canvas 格亦無法點擊）；需改用鍵盤或驗證邏輯
- **`st.error()` 在 `st.rerun()` 前呼叫會被清除**：錯誤訊息必須存入 `session_state`，下次 render 再顯示
- **Streamlit subprocess 不繼承 PATH 的 Scripts/**：用 `Path(sys.executable).parent / "Scripts"` 直接查，不依賴 `shutil.which`
- 新功能完成後，**必須用 MCP screenshot 跑過 golden path**，確認畫面符合預期再 commit

## 測試

```powershell
npm run test:python     # Python sidecar 單元測試
npm test                # JavaScript shared-protocol 單元測試
```

## 打包

- 原始碼 zip → `/package-source`
- Electron 可攜式安裝包 → `/package-build`
