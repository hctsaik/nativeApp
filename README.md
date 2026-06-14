# CIM Hybrid Edge Platform

A hybrid edge platform that lets engineers **build and ship their own tools**
(declarative no-code / low-code) on an Electron + React portal + Python FastAPI
sidecar (Streamlit split-tools). The Labeling (X-AnyLabeling) feature is the
benchmark "real tool"; the same scaffold → hot-reload → publish flow builds new
tools. See `docs/platform/selfbuild-tool-shipping-evaluation.md`.

## Structure

```text
apps/
  host-electron/
  portal-react/
sidecar/
  python-engine/
    tests/
packages/
  shared-protocol/
```

## Development

> ⚠️ **不要用 GitHub「Download ZIP」取得本專案。** AI Report (AI4BI) 以 git
> **submodule** 掛載；ZIP / 淺 clone **不含** submodule 內容。影像標註（Labeling）則是
> **外部外掛**：獨立 repo（ANnoTation），用目錄 junction 掛進 `plugins/labeling`。
> 兩者缺任一都會讓對應工具從清單消失、app 無法正常啟動。

Clone the platform **with submodules** (AI4BI lives in a git submodule):

```bash
git clone --recurse-submodules https://github.com/hctsaik/nativeApp.git
# already cloned without submodules? run this at the repo root:
git submodule update --init --recursive
```

Mount the **Labeling** plugin — it lives in its own repo (ANnoTation) and is
developed independently; the platform loads it from `plugins/labeling` via a
directory junction:

```bash
# clone ANnoTation next to the nativeApp repo, then create the junction
git clone https://github.com/hctsaik/ANnoTation.git ../ANnoTation
scripts\win\link-labeling.bat
```

Install JavaScript dependencies:

```bash
npm install
```

Install Python sidecar dependencies in your preferred virtual environment:

```bash
pip install -r sidecar/python-engine/requirements.txt
```

Run the Electron host and React portal:

```bash
npm run dev
```

The Electron main process starts the FastAPI sidecar, allocates dynamic local
ports, and opens the React portal. The sample Streamlit tool starts on demand.
The sidecar waits for Streamlit to be fully ready before returning the tool URL,
so the portal iframe loads only after the tool server is accepting connections.

## 全新電腦安裝（含 AI4BI）

> 完整、經 clean-room 實測、可讓 **Claude Code 直接照做**的下載＋安裝 runbook 見
> **[`docs/INSTALL.md`](docs/INSTALL.md)**（含三 repo clone、隔離 venv、doctor 驗證、實測結果）。
> 以下為摘要。

AI4BI（📊 AI Report）以 git submodule 置於 `sidecar/python-engine/vendor/AI4BI`，
並 editable 裝進 **engine 所用的同一支 Python 3.11**。完整流程如下。

### 前置需求

- Git、Node.js（LTS）
- **Python 3.11**（需與 engine host 直譯器一致；`start-dev.bat` 會自動以 `py -3.11` 偵測）
- AI4BI submodule 來源是私有 repo（`github.com/hctsaik/AI4BI`），新機器需有存取權

### 步驟

```powershell
# 1) Clone 時一併拉 submodule（若已 clone，改跑第 2 行）
git clone --recurse-submodules <native-app repo url>
git submodule update --init --recursive

# 2) Node 依賴（Electron + portal + workspaces）
npm install

# 3) 平台核心 Python 依賴（瘦核心，plugin-agnostic）
#    py -3.11 = start-dev.bat 自動偵測的同一支；多支時改用其絕對路徑
py -3.11 -m pip install -r sidecar/python-engine/requirements.txt

# 4) AI4BI plugin（editable，裝進同一支 3.11；plotly/duckdb 等隨它一起裝）
py -3.11 -m pip install -e "sidecar/python-engine/vendor/AI4BI[llm]"

# 5) 影像標註 plugin（外部 repo ANnoTation；clone 到 nativeApp 旁，再用 junction 掛載）
git clone https://github.com/hctsaik/ANnoTation.git ..\ANnoTation
scripts\win\link-labeling.bat
#    專屬相依（torch/ultralytics 等）
py -3.11 -m pip install -r "sidecar/python-engine/plugins/labeling/requirements-labeling.txt"

# 6) 啟動整個 app（會自動偵測 Python 3.11）
start-dev.bat
```

> 影像標註（labeling）是**外部外掛**：原始碼在獨立 repo（`github.com/hctsaik/ANnoTation`），
> 透過目錄 junction 掛進 `sidecar/python-engine/plugins/labeling`。日後更新只需在那個外部
> ANnoTation 資料夾內 `git pull`（junction 會即時反映）。

### ⚠️ 最關鍵的一步：對齊 engine 的 Python

dev 模式下 engine 由 `start-dev.bat` 解析出的 Python 啟動
（傳給 Electron，見 `apps/host-electron/src/main.js` 的 `process.env.PYTHON`）。
**`start-dev.bat` 會自動偵測 Python 3.11**（優先用 `py -3.11`，找不到才退回 PATH 上的 3.11），
所以一般不必改檔；只要確認你機器上有 Python 3.11、且步驟 3、4 都裝進**同一支**即可。
若你有多支 3.11 或想指定特定直譯器，啟動前設環境變數覆蓋：`$env:PYTHON = "C:\...\python.exe"`。

### 確保安裝成功：跑驗證腳本

安裝完成後跑一次 doctor 腳本，全部 PASS 才代表 `start-dev.bat` 能乾淨啟動：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\win\verify-setup.ps1
```

它會解析 `start-dev.bat` 實際使用的 Python，並在**那一支**直譯器內逐項檢查：
git/node/npm、Python 3.11、submodule 已 checkout、`node_modules`、
engine 依賴（fastapi/streamlit/pandas）、AI4BI 依賴（ai4bi/duckdb/plotly）、
以及進入點 `ai4bi.ui.app`；任何一項 FAIL 都會印出對應修法。

### 常見地雷

| 症狀 | 原因 | 解法 |
|------|------|------|
| engine 啟動後立刻退出 / 找不到 python | 機器上沒有 Python 3.11（`py -3.11` 不可用） | 安裝 Python 3.11；或啟動前設 `$env:PYTHON` 指向本機 3.11 的 `python.exe` |
| 啟動 AI Report 報 `ModuleNotFoundError: ai4bi` | AI4BI 裝到了別支 Python（非 engine 用的那支） | 用步驟 4 同一支 python 重裝 |
| 清單缺「影像標註」、或啟動印出 `[CIM-PREFLIGHT]` | labeling 外掛未掛載（ANnoTation 未 clone 或 junction 未建立） | clone ANnoTation 到 nativeApp 旁，執行 `scripts\win\link-labeling.bat`；start-*.bat 啟動前會自動檢查並擋下 |
| `vendor/AI4BI` 是空資料夾、AI Report 點了壞 | clone 時沒帶 submodule | `git submodule update --init --recursive` |
| AI Report 的自然語言/LLM 功能無反應 | 未設 `ANTHROPIC_API_KEY` | 設環境變數後重啟（不設則走非-LLM 模式） |
| 更新 AI4BI 後沒生效 | — | 進 `vendor/AI4BI` 做 `git pull`（editable 即時生效）；新增相依套件時才需再跑步驟 4 |

> 正式 release（PyInstaller `engine.exe`）需另把 AI4BI 套件納入打包，
> 細節見 [`docs/AI4BI_INTEGRATION.md`](docs/AI4BI_INTEGRATION.md)。

## Implemented First Pass

- Electron host starts and stops the Python FastAPI sidecar.
- The host allocates dynamic localhost ports.
- Packaged sidecar readiness allows a longer timeout because PyInstaller
  onefile startup can spend time extracting bundled resources.
- Sidecar exposes `/health`, `/shutdown`, and tool start/stop endpoints.
- Sidecar seeds a runtime SQLite tool registry through the DB adapter boundary.
- Streamlit tools run as subprocesses, with one active tool at a time.
- Sidecar waits for the Streamlit port to be ready before returning the URL.
- Mode 1 embeds local Streamlit through an iframe.
- Mode 2 embeds a mock enterprise micro-frontend through an iframe.
- The portal sends a mock JWT through the shared `postMessage` protocol.
- Local file access is mediated by Electron's file picker.
- Host-selected file paths are synchronized to the sidecar through
  `/selected-paths`; the sample Streamlit tool can read host-selected CSV files.
- Active tool state is tracked in the portal; Start Tool switches to a Stop
  button while a tool is running.
- Sidecar unexpected exit shows a recoverable error banner in the portal and
  disables tool operations.
- Development logs are written under the app/project directory.
- Portable logs are written beside the portable executable under `logs/`.

## Annotation / X-AnyLabeling Workstream

The platform now includes an annotation common component MVP and an
X-AnyLabeling integration workflow.

Implemented:

- `annotation-core` canonical model under `sidecar/python-engine/annotation`.
- Label schema, bbox, polygon, image-level classification, validation, review,
  and approval.
- Local workspace storage with SQLite metadata and checksum artifacts.
- LabelMe / X-AnyLabeling-compatible JSON exchange.
- X-AnyLabeling project folder preparation and optional GUI launch handoff.
- COCO and YOLO detection export.
- Generic `annotation_*` MCP server under `mcp/annotation_mcp`.

X-AnyLabeling is installed in a repo-local `.venv-xanylabeling` environment and
verified as `4.0.0-beta.7`.

See [docs/ANNOTATION_XANYLABELING.md](docs/ANNOTATION_XANYLABELING.md) for the
full status, workflow, commands, validation results, and remaining scope.

## video_annotator External Launcher

`video_annotator` is exposed as an external desktop-window tool. The checked-in
launcher build lives at:

```text
LabelMe_Dino/dist/LabelMe_Dino_launcher/LabelMe_Dino.exe
```

The launcher is intentionally thin. It starts `LabelMe_Dino/main.py` with an
external Python runtime instead of bundling PyTorch, PyQt, Transformers, and
OpenCV into the executable. In development, Electron injects:

```text
LABELME_DINO_EXE=...\LabelMe_Dino\dist\LabelMe_Dino_launcher\LabelMe_Dino.exe
LABELME_DINO_RUNTIME=...\LabelMe_Dino\.venv
```

For packaged builds, the launcher folder is copied to
`resources/labelme-dino`; the runtime should be provided through
`LABELME_DINO_RUNTIME` or installed under:

```text
%LOCALAPPDATA%\CIM\labelme-dino-runtime\.venv
```

Smoke-test the launcher without opening the PyQt GUI:

```powershell
$env:LABELME_DINO_RUNTIME="C:\code\claude\nativeApp_Int\LabelMe_Dino\.venv"
.\LabelMe_Dino\dist\LabelMe_Dino_launcher\LabelMe_Dino.exe --probe-runtime
```

If Windows Application Control blocks a newly compiled unsigned launcher, the
sidecar falls back to the same external runtime by launching
`LabelMe_Dino\.venv\Scripts\python.exe LabelMe_Dino\main.py`.

## Build And Package

Build the React portal:

```bash
npm run build
```

Package the Python sidecar first:

```bash
cd sidecar/python-engine
python -m PyInstaller engine.spec
```

Then package the Electron portable app for the current machine architecture:

```bash
npm run package:portable
```

Package a Windows x64 portable app:

```bash
npm run package:portable:x64
```

The portable output is written to `release/`.
The portable executable name is currently shared across architectures, so a
later package run can overwrite an earlier portable executable.

## 開發新工具（Tool Development）

CIM 平台的每個工具由**兩個獨立 Streamlit 程序**組成（split-tool 架構），
透過一份 JSON 結果檔案交換資料，Portal 負責在執行完成後自動切換並 reload output 頁面。

### 快速開始：scaffold CLI（首選，免 AI agent）

平台內建 scaffold CLI，一行產出可跑的工具骨架，**重啟或按 portal「重新載入工具」即上線**（免改 `engine.py`）：

```bash
# 零 Streamlit code 的表單工具（input 用 form: / output 用 output: 宣告，只寫純運算）
python sidecar/python-engine/tools/scaffold.py module --name "我的工具"   # id 省略=自動配下一個空號

python sidecar/python-engine/tools/scaffold.py module --name X --full          # 手寫 input/process/output
python sidecar/python-engine/tools/scaffold.py module --name X --external-gui   # 啟動外部 GUI（Label tool 模式，零 code）
python sidecar/python-engine/tools/scaffold.py sheet my-flow --tabs module_042,module_043 --create-stubs  # 多分頁工作流
python sidecar/python-engine/tools/scaffold.py plugin my-domain                 # 全新領域 plugin（含可跑起步模組+domain+sheet）
python sidecar/python-engine/tools/scaffold.py connector my-eqp                 # 非-REST 外部系統 connector 骨架
```

宣告式三件套（皆免寫對應 `*.py`）：`form:`（輸入欄位，含 date/time）、`output:`（呈現區塊）、
`external_gui:`（啟動外部桌面程式 → 作業 → 關閉自動回收輸出，框架處理 env 淨化 / WDAC workaround / 單例鎖 / RBAC 檢查）。
範例：`sidecar/python-engine/scripts/module_007/`（完全零 Streamlit code）。

**工具自帶相依（per-tool deps）**：工具需要額外 Python 套件時，在 `plugin.yaml` 加
`requires: [shapely>=2.0, ...]`（或 `scaffold module --requires shapely>=2.0,scikit-image`）。
engine 啟動該工具時自動建**隔離 per-tool venv** 安裝並注入 PYTHONPATH，不汙染全域、免改
`requirements.txt`。frozen 打包需設 `CIM_PYTHON`；離線工廠用 `CIM_WHEELHOUSE`。
詳見 [`docs/platform/per-tool-dependencies.md`](docs/platform/per-tool-dependencies.md)。

開發迴圈：改 plugin.yaml / sheet YAML → portal「重新載入工具」鈕（或 `POST /reload`）即重掃出現，執行中的工具會自動重啟套用改動。

### 替代：使用 /new-split-tool Skill（Claude Code 環境）

在 **Claude Code** 環境下，可用 `/new-split-tool` 由 AI 引導產生手寫 split-tool 骨架
（定義在 `.claude/commands/new-split-tool.md`）。一般情況建議優先用上面的 scaffold CLI。

---

### 架構概覽

```
{stem}_input.py   ── 使用者填寫表單 + 按下執行
      │  1. notify_start()          ← 顯示 Loading overlay
      │  2. 執行運算
      │  3. write_result(...)       ← 寫入結果 JSON
      │  4. notify_complete()       ← Portal 自動切換至 Output 並 reload
      ▼
{stem}_output.py  ── 讀取結果 JSON，靜態渲染（無 polling loop）
```

**結果 JSON 固定格式：**
```json
{
  "user_input":     { "...使用者填的欄位..." },
  "process_result": { "...運算產出的資料..." }
}
```

---

### 共用工具程式庫（`sidecar/python-engine/tools/`）

| import | 用途 | 主要 API |
|--------|------|----------|
| `tool_comms` | 與 Portal 溝通 | `notify_start()` `notify_complete(success, error)` |
| `tool_result` | 讀寫結果檔案 | `write_result(path, user_input, process_result)` `read_result(path)` |
| `ui_utils` | RWD 圖片 + lightbox | `show_image(source, caption)` |
| `db_utils` | SQLite 存取 | `SimpleDAO(db_path)` — `query` / `execute` / `execute_many` / `last_insert_id` |
| `log_utils` | 雙輸出 logging | `get_logger(name)` → stdout + `{CIM_LOG_DIR}/{name}.log` |

---

### 手動建立工具的步驟

若不使用 skill，手動步驟如下：

1. **建立三個檔案**（以 `my-tool` 為例）：
   ```
   sidecar/python-engine/tools/
   ├── my_tool.py          ← 空 stub（引擎用來偵測 split-tool）
   ├── my_tool_input.py    ← Input 頁面
   └── my_tool_output.py   ← Output 頁面
   ```

2. **Input page 最小範本**：
   ```python
   from tool_comms import notify_start, notify_complete
   from tool_result import write_result

   if st.button("▶ 執行", type="primary"):
       notify_start()
       try:
           # ... 運算 ...
           write_result(RESULT_FILE,
               user_input={"param": value},
               process_result={"output": result})
           notify_complete()
       except Exception as exc:
           notify_complete(success=False, error=str(exc))
   ```

3. **Output page 最小範本**：
   ```python
   from tool_result import read_result

   data = read_result(RESULT_FILE)
   if data is None:
       st.info("尚未執行")
       return          # ← 靜止等待，不需要 polling loop
   ui = data["user_input"]
   pr = data["process_result"]
   # ... 顯示結果 ...
   ```

4. **在 `engine.py` 的 `seed_tools` 清單中新增工具 entry**。

5. 重啟程式（`npm run dev`），新工具即出現於 Portal 選單。

---

### 重要規則

- **Output page 禁止 `time.sleep` + `st.rerun()` 的 polling loop。**  
  Portal 收到 `EXECUTE_COMPLETE` 後會自動 reload output iframe，
  output page 只需一次性渲染即可。
- 顯示圖片請用 `show_image()`，不要用 `st.image()`（後者缺乏 lightbox 與 RWD）。
- `user_input` 放「使用者決定的參數」，`process_result` 放「運算才知道的結果」。

---

## Testing

Install Python test dependencies (pytest and httpx are needed in addition to
the sidecar runtime dependencies):

```bash
pip install pytest httpx
```

Run the Python sidecar unit tests:

```bash
npm run test:python
# or directly:
python -m pytest sidecar/python-engine/tests/ -v
```

Run the JavaScript shared-protocol unit tests:

```bash
npm test
# or in the package directly:
npm test -w packages/shared-protocol
```

The Python test suite covers:

- `SQLiteToolAdapter` — seeding, listing, get, disabled-tool filtering, sort order
- `SelectedPathStore` — read, write, overwrite, empty, missing file, corrupt file
- `ToolRegistry` — delegation to adapter, unknown tool error
- `wait_for_port` — immediate listener, no listener, delayed listener
- FastAPI routes — health, tool list shape, start (success/404/500), stop,
  selected-paths CRUD, shutdown response

The JavaScript test suite covers:

- `MessageTypes` — constants and immutability
- `createMessage` — source, type, timestamp, payload defaults, payload passthrough
- `isProtocolMessage` — valid/invalid messages, all edge cases

> Note: the repo's `python` resolves to `.venv-xanylabeling` (no pytest/fastapi).
> To run pytest directly use `py -3.11 -m pytest sidecar/python-engine/tests/`.

## Fleet Distribution (single-machine simulation)

A "fleet" is N state-isolated engine instances (each with its own `--log-dir` /
`tools.sqlite`) all subscribing to one registry. `start-fleet.bat` runs one
registry plus two devices on this machine so the whole publish→pull flow can be
exercised without any cloud infrastructure:

```powershell
start-fleet.bat
# publish a tool to the whole fleet (signs the snapshot, POSTs to the registry):
py -3.11 sidecar\python-engine\tools\fleet_publish.py `
    sidecar\python-engine\scripts\module_007 `
    --registry http://127.0.0.1:9000 --channel prod
# each device pulls it (no restart):
#   POST http://127.0.0.1:8100/reload   and   http://127.0.0.1:8101/reload
```

Each device verifies the artifact signature on fetch, so tampered/unsigned code
is rejected before it can be published locally. Enabled per device by
`CIM_DISTRIBUTION_SOURCE` (unset = unchanged single-machine behaviour). The HMAC
shared-secret signing is an MVP; production should set a real
`CIM_DISTRIBUTION_SECRET` and upgrade to Ed25519. See
[`docs/platform/fleet-distribution.md`](docs/platform/fleet-distribution.md).

## Verification Notes

Verified locally:

- `npm install`
- `python -m pip install -r sidecar/python-engine/requirements.txt`
- `npm run build`
- Python compile check for `engine.py` and the sample Streamlit tool
- Development sidecar smoke test for health, tool start, tool stop, and shutdown
- SQLite tool registry smoke test
- Selected-paths API smoke test
- `npm run package:portable`
- `npm run package:portable:x64`
- Packaged `engine.exe` smoke test for `/health` and graceful shutdown
- Packaged Electron app sidecar readiness smoke test
- Python unit test suite: 32/32 passed
- JavaScript unit test suite: 17/17 passed

Troubleshooting:

- If a packaged app reports `Sidecar readiness timed out`, check the portable
  `logs/host.log`; first startup of a PyInstaller onefile sidecar can be slower
  than development startup.
- If the packaged Electron app exits immediately and `app.exe --version` prints
  a Node.js version instead of an Electron version, remove
  `ELECTRON_RUN_AS_NODE` from the environment. That variable forces Electron to
  run as Node and prevents the desktop app from starting.
- Windows 11 Smart App Control can block newly generated unsigned or
  locally-signed executables. For this development machine, run with
  `npm run dev` during active development, or use a production code-signing
  certificate / Smart App Control policy change for packaged exe validation.
