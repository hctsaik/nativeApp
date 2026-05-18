# CIM Hybrid Edge Platform

This repository contains the first implementation scaffold for the OpenSpec
change `hybrid-edge-microfrontend-platform`.

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

### 快速開始：使用 /new-split-tool Skill

如果你在 **Claude Code**（CLI 或 VSCode 擴充功能）環境下開發，
輸入以下 slash command 即可由 AI 引導產生完整的工具骨架：

```
/new-split-tool
```

Claude 會詢問 5 個問題（Tool ID、名稱、Input/Process/Output 描述），
然後自動產生所有必要檔案並說明如何註冊到 Portal。

> Slash command 定義在 `.claude/commands/new-split-tool.md`，
> 可直接閱讀該檔案了解完整架構規範與程式碼範本。

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
