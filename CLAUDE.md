# CIM Hybrid Edge Platform — AI 協作指引

## 啟動方式

### 開發模式（新架構：**Tauri 殼**，正式主線）
```powershell
# 啟動一律走 Tauri 殼（nativeApp_Light）；portal / Python engine / cim-modules / 外部工具
# 完全共用、不變——只有「殼」從 Electron 換成 Tauri。根目錄任一支都會自動轉導到 Tauri：
start-dev.bat          # = 轉導 → start-dev-tauri.bat
start-dev-nowdac.bat   # = 轉導 → start-dev-tauri.bat
# 或直接：
start-dev-tauri.bat
```
> **啟動以 Tauri 為主**：Tauri dev 載「預建 portal dist」(不跑 Vite/esbuild)，由 Rust spawn 原始碼 engine。
> ⚠️ **WDAC 實測**：強制模式 WDAC 機器上 `tauri dev` 的 **cargo build 會被擋**（未簽章 build-script/debug exe，
> `os error 4551`，與擋 esbuild 同類）。`start-dev-tauri.bat` 會**自動退回 `start-dev-nowdac-electron.bat`**
> （本機唯一能跑的 LOCAL DEV）。Tauri 的 WDAC 好處在**簽章 release**（`tauri build`），不在 dev；
> 要本機跑 Tauri dev 需 IT 放行 `src-tauri\target` 或改在可編譯機器產簽章版部署。詳見 [`docs/platform/startup-tauri.md`](docs/platform/startup-tauri.md)。
> **舊 Electron DEV 殼仍為備援**：`start-dev-electron.bat` / `start-dev-nowdac-electron.bat`。
> Tauri 殼專案在 **sibling repo `..\nativeApp_Light\5_PG_Develop`**（首次需 `npm install` + Rust toolchain/rustup）。
> 完整啟動清單、各 .bat 處置、前置需求與 WDAC 說明見 [`docs/platform/startup-tauri.md`](docs/platform/startup-tauri.md)。

### 首次設定（解壓 source zip 或全新 clone 後）
```powershell
# 1) 平台 + submodule 外掛（AI4BI / LV / cim-modules）。clone 時帶 --recurse-submodules，
#    或事後補：
git submodule update --init --recursive

# 2) Labeling 外掛是「外部 junction」（不在 git 樹內，每次 clone 要重掛一次）：
git clone https://github.com/hctsaik/ANnoTation.git ..\ANnoTation
scripts\win\link-labeling.bat            # 建 plugins\labeling -> ..\ANnoTation junction

# 3) 相依
npm install
pip install -r sidecar/python-engine/requirements.txt                       # engine 核心（lean）
py -3.11 -m pip install -r sidecar/python-engine/plugins/labeling/requirements-labeling.txt  # Labeling 專屬

# 4) Tauri 殼（新架構，正式主線）— 與 nativeApp 同層的 sibling repo `..\nativeApp_Light`
#    （若尚未取得，先把 nativeApp_Light clone 到 nativeApp 的同一層）
cd ..\nativeApp_Light\5_PG_Develop
npm install          # Tauri 前端相依（另需 Rust toolchain：rustup）
cd ..\..\nativeApp

# 5) 啟動（一律 Tauri；start-dev.bat 會自動轉導到 start-dev-tauri.bat）
start-dev.bat
```
> 完整拓樸（submodule vs junction、約束）見 [`docs/platform/repo-topology.md`](docs/platform/repo-topology.md)。
> 各工具的重量級相依（LV 的 torch/umap、Labeling 的 ultralytics 等）**不在上面**，
> engine 首次啟動該工具時才依 `plugin.yaml requires:` 建隔離 per-tool venv 自動安裝。
> 已用全新資料夾驗證過上述步驟可 E2E 跑通（clone×3→junction→pip/npm→engine 啟動，
> catalog 正確註冊 app-lv + sheet-annotation + labeling 模組）。

## WDAC（Windows App Control）— 已定論，勿再重複討論

> 這題已反覆討論多次。以下是**最終結論**：遇到 WDAC 相關現象，**直接照此處理，不要再重新調查、
> 重新提方案、或反覆評估**。背景與實測見 [`docs/platform/startup-tauri.md`](docs/platform/startup-tauri.md)。

**環境事實（固定）**：本開發機（`COLA\hctsa`，公司 Azure AD/MDM 託管）WDAC 為**強制模式**（含 user-mode），
**封鎖一切未簽章執行檔**。已知被擋：`esbuild.exe`（+`@rollup\*.node`，Vite build/dev）、
`cargo` 的 build-script/debug exe（`tauri dev`，`os error 4551`）、`xanylabeling.exe`（uv trampoline）。
**未被擋、可正常跑**：`electron.exe`、`node`、`python`。
**權限事實（固定）**：使用者**非 admin、無 ConfigCI、無法自行加 WDAC 規則**；公司 MDM 會還原本機 supplemental 政策。
→ **根治（把路徑/簽章加進允許清單）只能請 IT 做，不在 AI 可處理範圍，也不需要 AI 反覆嘗試繞過。**

**現行做法 = 決議（就這樣做，別再找別的）**：
1. **不在本機 build 被擋的東西**（esbuild / cargo）。一律用「**在允許的機器預先 build 好的產物**」：
   portal 用預建 `apps/portal-react/dist`；要更新前端就在 esbuild 允許的機器 `npm --prefix apps/portal-react run build` 後帶回。
2. **本機 DEV 啟動 = Electron（no-WDAC）：靜態服務預建 dist + 跑 dev `electron.exe`**（electron 沒被擋）。
   = `start-dev-nowdac-electron.bat`。直接跑 `start-dev.bat` 即可——它先試 Tauri、被擋就**自動退回這條**，結果就是這條。
   （`start-trusted.bat`/`prepare-trusted-electron.bat`「複製 Electron 到信任路徑」**目前用不到**，因為 `electron.exe` 本來就沒被擋；僅在日後 IT 連 electron 也收緊時才需要。）
3. **xanylabeling**：用 `py -3.11 -c "...main()"` 啟動，**永遠不要**改回直接執行 `xanylabeling.exe`（見下方常見錯誤表）。

**Tauri 與 WDAC 的定論**：Tauri 是**目標架構**，但 **`tauri dev` 在本機 build 不起來**（cargo 產未簽章 exe 被擋，與 esbuild 同類）。
Tauri 的 WDAC 好處**只在「簽章 release」**（`tauri build` → 簽章 nsis、runtime 放行，且該簽章仍需 IT 信任）。
**在 IT 放行 `src-tauri\target`（或信任簽章）之前，本機 Tauri dev 不可行；LOCAL DEV 一律維持上面第 2 點的 Electron-nowdac。**
別再嘗試讓本機 `tauri dev` 跑起來、別再評估這件事。

**給 AI 的規則**：看到「Application Control policy has blocked / os error 4551 / esbuild blocked」等，
**不需重新診斷或提新解**——成因與對策已固定如上。需要 IT 動作的事，**陳述一次、交給 User**，不要反覆討論或自行嘗試繞過。

## 協作規則

- **語言**：一律使用繁體中文對話與撰寫說明（commit message 除外）
- **完成功能後**：同步更新對應文件（`docs/`、README），並新增或更新單元測試；
  確認 `npm run test:python` 與 `npm test` 全過後再 commit

## 架構關鍵點

### 啟動鏈（新架構：Tauri）
```
start-dev.bat ( → start-dev-tauri.bat )
  → Tauri 殼 (nativeApp_Light/5_PG_Develop;Rust + 系統 WebView2)
    → 載入預建 portal dist (apps/portal-react/dist) + 由 Rust spawn Python FastAPI engine
      → Python engine (sidecar/python-engine/engine.py)
        → Streamlit 子程序（按需啟動，含注入環境變數）
```
> 殼以外完全不變：engine、cim-modules、portal、Streamlit 工具與 Electron 版**共用同一份**。
> 舊 Electron 鏈（備援）：`start-dev-electron.bat → Electron (apps/host-electron) → 同一 engine`。
> ⚠️ 註：dev-log server `127.0.0.1:19222`（cim-gui MCP / 舊 E2E 探測 sidecar 埠用）是 **Electron 殼專屬**；
> Tauri 殼改由 portal 經 `window.cimHost.getAppConfig()` 取得控制埠，沒有 19222。

### Sheet 驅動機制
新 workflow sheet 由 YAML 定義，engine 啟動時自動載入（掃 `sidecar/python-engine/sheets/*.yaml` **與** `plugins/*/sheets/*.yaml`）。
加一個新 sheet 只需新增 YAML 檔，不需修改 engine.py。

目前只有一個 annotation sheet：`plugins/labeling/sheets/annotation.yaml`（🐜 影像標註，4 tabs）— 已隨架構重構移入 Labeling plugin。

### Catalog 事實來源 = 宣告式 YAML，tools.sqlite 是衍生快取
工具/sheet 清單的**唯一定義權威**是宣告式文字檔：各 `plugin.yaml`、sheet 的 `*.yaml`、
以及「無 plugin.yaml 工具」的 `config/seed.yaml`（static_tools / disable_tools /
prod_enable_tools / renames / sheet_tab_deletions；由 `engine._load_static_seed()` 讀取）。

`tools.sqlite` 是 **per-device 衍生快取**（`<log_dir>/data/tools.sqlite`，gitignored），
engine 每次啟動 `_initialize()` 都從上述 YAML 冪等重建——**檔案不存在會自動新建並填好**。
所以：**不要把 `tools.sqlite` 進版控、不要手動編輯它**。新增「無 plugin.yaml 的工具」改 `config/seed.yaml`。

想砍掉重練（pull 後保證乾淨）：`engine --rebuild-catalog`（boot 前先刪 DB 再重建）。
背景與決議見 [`docs/platform/catalog-source-of-truth-discussion.md`](docs/platform/catalog-source-of-truth-discussion.md)。

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
- **模組設定/路徑**：各模組 `_config.py` 委派共用 `scripts/shared/_config_base.py`（`load_config`/`atomic_write`/`manifest_db_path`/`manifest_key` 等；目前僅 `module_012` 仍含特例邏輯未完全委派）
- **共用 Streamlit UI**：`scripts/shared/ui_components.py`、`image_widget.py`、`_help.py`（見 `/common-component`）
- **宣告式表單/輸出**：`core/forms.py`（`form:`，欄位 text/number/integer/select/multiselect/checkbox/slider/textarea/file/**date**/**time**）、`core/output.py`（`output:`）
- **外部 GUI 啟動器**：`core/external_gui.py`（宣告式 `external_gui:`：exe 解析 / env 淨化 / WDAC workaround / 單例鎖 / PID 監看 / 輸出回收+parse）
- **外部系統連接**：`core/integrations/connector.py`（`ExternalSystemConnector`）+ `core/integrations/registry.py`（connector 工廠 + `autodiscover()`，掃 `core/integrations/connectors/*.py` 自動註冊）
- **RBAC / 身分**：`core/rbac.py` + `config/permissions.yaml`；`auth_provider.py`（`get_current_role` / `set_identity`，engine `/whoami` `/set-role`，CLI `tools/set_role.py`）
- **工具自帶相依**：`core/tool_deps.py`（plugin.yaml 宣告 `requires:` → engine 自動建隔離 per-tool venv 安裝並注入 PYTHONPATH；frozen 用 `CIM_PYTHON`、離線用 `CIM_WHEELHOUSE`）；見 [`docs/platform/per-tool-dependencies.md`](docs/platform/per-tool-dependencies.md)
- **Fleet 分發**：`core/distribution/`（`ToolDistributionSource` + 簽章 artifact）+ `tools/registry_server.py` + `tools/fleet_publish.py` + `start-fleet.bat`（單機模擬）；env-gated `CIM_DISTRIBUTION_SOURCE`；見 [`docs/platform/fleet-distribution.md`](docs/platform/fleet-distribution.md)
- **標注領域服務**：`plugins/labeling/domain/services.py`（`AnnotationService`）

> 平台正進行架構重構（共用碼→`core/`、Labeling→`plugins/labeling/`、凍結數字 ID）。
> 路線圖與決策見 [`docs/platform/architecture-restructure-discussion.md`](docs/platform/architecture-restructure-discussion.md)。
> 平台級文件一律放 `docs/platform/`，勿在 `docs/` 根目錄建同名重複檔。

## 常見錯誤與處理

| 錯誤 | 原因 | 解法 |
|------|------|------|
| `Missing CIM_SHEET_ID or CIM_PLUGIN_ID` | 直接執行 `sheet_runner.py`（env 由 engine spawn 時注入，單跑沒有） | 改用 `start-dev.bat` 啟動整個 app。catalog 會由宣告式來源首啟自動重建，不需手動帶 DB；懷疑快取髒掉用 `engine --rebuild-catalog` |
| Electron app 啟動後印出 Node.js 版本就退出 | `ELECTRON_RUN_AS_NODE=1` 殘留在環境 | 移除該環境變數，或用 `apps/host-electron/launch-electron.js` workaround |
| `xanylabeling.exe` 被 WDAC 封鎖 | Windows Application Control 政策封鎖 uv trampoline | `012_output.py` 必須維持 `py -3.11 -c "import sys; sys.path.insert(...); from anylabeling.app import main; main()"`，不要改回直接執行 `xanylabeling.exe` |
| iWISC 任務列表空白 | 外部 iWISC server 未啟動，或尚未註冊外部系統連線 | 啟動 iwsc-sample-server（port 8765）；**註冊外部系統有 no-code GUI 表單**：管理中心 Tools → External（`management_runner._render_external_system_register`，寫入 `config/external_systems.yaml`，token 走環境變數）；亦可用 `AnnotationService.register_tenant` / annotation MCP `register_tenant`。非-REST 協定用 `python tools/scaffold.py connector <name>` 產 connector 骨架（放 `core/integrations/connectors/`，啟動時 `core.integrations.registry.autodiscover()` 自動註冊）|

## 架構地雷（容易踩的坑）

- **新增 postMessage 類型**：`packages/shared-protocol/src/index.js` 的 `MessageTypes` 和
  `index.test.js` 必須同步更新，否則 `isProtocolMessage` 會過濾掉新訊息
- **Portal 導航觸發**：任何會切換 tab 或 route 的邏輯，都要確認不會被
  `suppressPollerNavUntilRef`（2s poller 防覆蓋機制）或 `EXECUTE_START` suppress 蓋掉

## 工具開發規則

- **建工具骨架用 scaffold CLI（首選，免 AI agent）**：`python tools/scaffold.py module <NNN|省略=自動配下一個空號> [--name ..] [--external-gui]` / `sheet <id> --tabs a,b --create-stubs` / `plugin <name>` / `connector <name>`。form-first 預設零 Streamlit code。
- **No-code input（宣告式表單）**：簡單工具可**不寫 `*_input.py`**，改在 `plugin.yaml` 用 `form:` 宣告輸入欄位（type: text/number/integer/select/multiselect/checkbox/slider/textarea/file/date/time），框架（`cv_framework_runner`）自動渲染並把值傳給 `execute_logic(params)`。範例 `plugins/cim-modules/modules/module_007/`（零 input 程式碼）；引擎 `core/forms.py`。
- **No-code output**：`plugin.yaml` 用 `output:` 宣告呈現區塊（`core/output.py`），免寫 `*_output.py`。
- **No-code 外部 GUI 工具（Label tool 模式）**：`plugin.yaml` 宣告 `external_gui:`（exe 來源 / args / collect.parse），框架渲染啟動鈕、自動回收輸出、且**啟動前檢查 RBAC**；零 input/process/output code。引擎 `core/external_gui.py`。
- **工具自帶 Python 相依（per-tool deps）**：工具需要額外套件時，在 `plugin.yaml` 加 `requires: [pkg>=x, ...]`（或 `scaffold module --requires a,b`）。engine 啟動該工具時自動建**隔離 per-tool venv** 安裝並注入子程序 PYTHONPATH，不汙染全域、不必改 `requirements.txt`。無 `requires:` 的工具零成本。frozen 打包需 `CIM_PYTHON` 指向真 Python；離線工廠用 `CIM_WHEELHOUSE`（`pip --no-index`）。引擎 `core/tool_deps.py`，詳見 [`docs/platform/per-tool-dependencies.md`](docs/platform/per-tool-dependencies.md)。
- 進階/自訂 UI 才需手寫 `*_input.py`（`render_input()` 回傳 params dict）。
- 每個工具由兩個 Streamlit 程序組成（split-tool 架構）：`*_input.py`（或宣告式 `form:`）+ `*_output.py`（或宣告式 `output:`）
- Output page **禁止** `time.sleep + st.rerun()` polling loop；portal 收到 `EXECUTE_COMPLETE` 後會自動 reload
- **新工具免改 engine.py**：`engine._scan_and_register_plugins` 啟動時掃 `scripts/*/plugin.yaml` + `plugins/*/modules/*/plugin.yaml` 自動註冊；`engine.py` 的 seed 區塊**只剩** sheet/management/external 等無 plugin.yaml 的工具。
- **第一方 CV 模組住 `plugins/cim-modules/`（git submodule → `nativeApp_modules`）**：`scaffold module` 預設就產到這裡。改完模組要**先在 submodule 內 `git add/commit/push`，再回平台 `git add plugins/cim-modules` 釘新指標**（同 LV/AI4BI 流程）。本機開發改完直接 `POST /reload` 即生效，不需 commit。模組反向找 host 共用碼用 `plugins/*/modules/` 深度（比 scripts/ 深 2 層）；契約由 `tests/test_modules_platform_contract.py` 鎖死（只允許 `core.*` + `scripts/shared/{_config_base,_help}`）。設計見 [`docs/platform/modules-independence-and-store-plan.md`](docs/platform/modules-independence-and-store-plan.md)。
- **熱載（免重啟整個 app）**：新增/改 plugin.yaml 或 sheet YAML 後，呼叫 `POST /reload`（engine 端點，可由 MCP 或 `curl` 觸發；portal 上的「重新載入工具」鈕已移除）即重掃並出現（執行中的工具會自動重啟套用改動）。connector 同樣經 `/reload` 的 `autodiscover()` 生效。
- 新增 Sheet Tab：在 `sidecar/python-engine/sheets/` 或 `plugins/<plugin>/sheets/` 建立或修改 YAML，而非修改 engine.py（drop YAML 即自動註冊 `sheet-<id>` 可啟動工具）。
- 廢棄模組（010、019、022-025）：已標記 `enabled: false`，程式碼保留不刪除

詳見 `README.md` 的「開發新工具」章節。

## Streamlit Output 頁效能規則

**每次 rerun 都會重新執行整個 render 函式**，三條強制規則：

1. **mtime 驅動增量更新**：掃描結果快取在 `session_state`，rerun 時只做 `stat()` 比對，mtime 變才重讀 JSON。禁止對所有 item 直接跑 `json.loads()` / `Path.exists()` 迴圈。
2. **大型列表必須分頁（PAGE_SIZE = 50）**：列表超過 50 項時每次 rerun widget 樹線性爆炸，禁止一次 render 所有項目。
3. **禁止 loop 內 `list.index()`（O(N²)）**：loop 前建 `{item_id: idx}` dict，改為 O(1) 查表。

參考實作：`sidecar/python-engine/plugins/labeling/modules/module_012/012_output.py`（`_scan_items` / `_incremental_refresh` / `_get_items`）

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

> 注意：專案內 `python` 指向 `.venv-xanylabeling`（無 pytest/fastapi）。
> 直接跑 pytest 時用 **`py -3.11 -m pytest sidecar/python-engine/tests/`**。

## Fleet 分發模擬（單機跑多裝置）

`start-fleet.bat` 在一台機器上起 **1 個 registry + 2 個狀態隔離的 engine 裝置**（各自 `--log-dir`／`tools.sqlite`），全指向同一 registry 來模擬 fleet：

```powershell
start-fleet.bat
# 在「管理機」發布一個工具到整個 fleet：
py -3.11 sidecar\python-engine\tools\fleet_publish.py sidecar\python-engine\plugins\cim-modules\modules\module_007 --registry http://127.0.0.1:9000 --channel prod
# 各裝置拉取（免重啟）：POST http://127.0.0.1:8100/reload、8101/reload
```

機制：發布的工具快照經 **HMAC 簽章**，裝置 `fetch` 時驗章，竄改的碼會被拒裝。env-gated（`CIM_DISTRIBUTION_SOURCE` 未設＝照舊單機）。production 應把 secret（`CIM_DISTRIBUTION_SECRET`）換真值、簽章升級 Ed25519。詳見 [`docs/platform/fleet-distribution.md`](docs/platform/fleet-distribution.md)。

## 打包

- 原始碼 zip → `/package-source`
- Electron 可攜式安裝包 → `/package-build`
