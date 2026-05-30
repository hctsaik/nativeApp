# CIM MCP Servers

This folder contains MCP servers for the CIM platform.

- `cim_gui_mcp`: GUI and E2E automation for the desktop app.
- `platform_mcp`: 平台層管理（tools、sheets、health）。
- Labeling 的 MCP（annotation_* 工具）已隨架構重構移至 Labeling plugin：
  `sidecar/python-engine/plugins/labeling/mcp/`（啟動：`python -m plugins.labeling.mcp.server`，PYTHONPATH=`sidecar/python-engine`）。

## platform_mcp — 平台層管理

提供 Claude 查詢與管理 CIM 平台本身的工具：

| 工具 | 說明 |
|------|------|
| `platform_health` | 確認 Python engine 健康狀態 |
| `platform_list_tools` | 列出所有已註冊的平台工具（modules） |
| `platform_get_tool` | 取得指定 tool 的詳細資訊 |
| `platform_list_sheets` | 列出所有 workflow sheet 及其 tab 配置 |
| `platform_get_sheet` | 取得指定 sheet 的 tab 詳細資訊 |
| `platform_start_tool` | 啟動指定工具 |
| `platform_stop_tool` | 停止目前執行中的工具 |

設定（`.mcp.json`）：
```json
"platform": {
  "command": "python",
  "args": ["-m", "platform_mcp.server"],
  "cwd": "C:/code/claude/nativeApp/mcp",
  "env": { "CIM_SIDECAR_PORT": "8765" }
}
```

---

## Annotation MCP Server

The annotation MCP server exposes `annotation_*` tools backed by the sidecar
annotation common component. It does not automate the X-AnyLabeling GUI; it
creates datasets, schemas, annotation sets, validation reports, review
decisions, labeling project folders, and derived exports.

For the current integration progress, runtime setup, validation status, and
next steps, see `../docs/ANNOTATION_XANYLABELING.md`.

Run manually:

```bash
cd sidecar/python-engine
set PYTHONPATH=C:/code/claude/nativeApp/sidecar/python-engine
set ANNOTATION_WORKSPACE=C:/code/claude/nativeApp/apps/host-electron/logs/annotation_workspace
python -m plugins.labeling.mcp.server
```

Common tools:

| Tool | Description |
|---|---|
| `annotation_create_dataset` | Create a canonical annotation dataset |
| `annotation_ingest_assets` | Ingest image assets into the workspace |
| `annotation_create_schema` | Create label and attribute schema |
| `annotation_create_task` | Create the MVP annotation set for a dataset/schema |
| `annotation_upsert_annotations` | Replace or merge annotations |
| `annotation_validate_set` | Validate against schema and geometry rules |
| `annotation_submit_for_review` | Submit a valid annotation set |
| `annotation_review_task` | Approve, reject, or request changes |
| `annotation_supported_annotation_formats` | List import/export format support |
| `annotation_prepare_labeling_project` | Prepare a local LabelMe/X-AnyLabeling/ISAT project folder |
| `annotation_prepare_xanylabeling_project` | Compatibility alias for X-AnyLabeling project preparation |
| `annotation_detect_xanylabeling` | Detect installed X-AnyLabeling runtime |
| `annotation_launch_xanylabeling_project` | Launch X-AnyLabeling for a prepared project folder |
| `annotation_detect_labeling_tool` | Detect a supported labeling tool runtime |
| `annotation_launch_labeling_project` | Launch a supported labeling tool for a prepared project folder |
| `annotation_import_xanylabeling` | Import LabelMe/X-AnyLabeling JSON |
| `annotation_import_annotations` | Import one supported annotation file, including LabelMe/X-AnyLabeling, ISAT, and COCO |
| `annotation_import_project_labels` | Import supported project labels directories, including LabelMe/X-AnyLabeling, ISAT, YOLO detection, and YOLO segmentation |
| `annotation_create_export` | Export LabelMe, X-AnyLabeling, ISAT, COCO, YOLO detection, or YOLO segmentation artifacts |

---

# CIM GUI MCP Server

Lets Claude operate the CIM application UI autonomously — taking screenshots, clicking buttons, filling inputs, and asserting results — without needing a human to describe what is on screen.

## Architecture

```
Claude Code
    │  stdio (MCP protocol)
    ▼
cim_gui_mcp.server  (FastMCP)
    ├── sidecar_client   →  HTTP → Python sidecar (engine.py :8765)
    └── browser_driver   →  Playwright → Streamlit pages (localhost:5xxxx)
```

Claude calls tools like `sidecar_start_tool`, `browser_screenshot`, `browser_click`.
The sidecar starts a Streamlit page on a random port; the browser driver opens and caches that URL.

## Prerequisites

```bash
# 1. Install Python deps (from repo root mcp/)
cd mcp
pip install -r requirements.txt

# 2. Install Chromium for Playwright (one-time)
playwright install chromium
```

## Running the MCP server

The server is launched automatically by Claude Code when the `.claude/mcp.json` config is present.

To run manually for debugging:
```bash
cd mcp
python -m cim_gui_mcp.server
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `CIM_SIDECAR_PORT` | `8765` | Port the Python sidecar listens on |
| `CIM_MCP_HEADLESS` | `1` | `1` = headless browser, `0` = visible window |
| `CIM_MCP_TIMEOUT` | `10000` | Default Playwright timeout (ms) |

## Starting the sidecar

The sidecar must be running before Claude can call any tool.
`--control-port` is required and must match `CIM_SIDECAR_PORT` in `.claude/mcp.json` (default: `8765`).

```bash
cd sidecar/python-engine
python engine.py --control-port 8765
# Listening on http://127.0.0.1:8765
```

Optional flags:

| Flag | Default | Description |
|---|---|---|
| `--control-port` | *(required)* | Port the sidecar listens on |
| `--log-dir` | `./logs` | Directory for log output |
| `--run-streamlit-script` | — | Launch a specific tool script directly |
| `--tool-port` | — | Fixed port for the launched tool |

## Available tools

### Sidecar tools

| Tool | Description |
|---|---|
| `sidecar_health` | Verify the sidecar is up |
| `sidecar_list_tools` | List all registered tools (JSON) |
| `sidecar_start_tool(tool_id)` | Launch a tool; returns `input_url` + `output_url` |
| `sidecar_stop_tool` | Stop the active tool |

### Browser tools

| Tool | Description |
|---|---|
| `browser_screenshot(url)` | Capture a page image (Claude sees it directly) |
| `browser_click(url, selector)` | Click an element by CSS / text selector |
| `browser_fill(url, selector, value)` | Type into an input field |
| `browser_get_text(url, selector?)` | Read text from a page or element |
| `browser_wait_for(url, selector, state?)` | Block until element is visible/hidden |
| `browser_close(url?)` | Close one page or all pages |

### Assertion tools

| Tool | Description |
|---|---|
| `assert_visible(url, selector)` | PASS/FAIL + screenshot if element is visible |
| `assert_text(url, selector, expected)` | PASS/FAIL if element text contains substring |
| `assert_no_error(url)` | PASS/FAIL + screenshot if no Streamlit error alerts |

## Typical Claude workflow

```
1. sidecar_health()                          → "ok"
2. sidecar_list_tools()                      → [...] pick a tool_id
3. sidecar_start_tool("cvmod-003")           → { input_url, output_url }
4. browser_screenshot(input_url)             → [image] Claude sees the UI
5. browser_click(input_url, "text=▶ 執行")  → "clicked"
6. browser_wait_for(output_url, ".stSuccess")
7. assert_no_error(output_url)               → PASS + screenshot
8. browser_close()
```

## Running tests

```bash
cd mcp
python -m pytest tests/ -v
```

All 41 unit tests run without a real browser or sidecar (mocked with respx + AsyncMock).

## Claude Code integration

The `.mcp.json` at the repo root configures this server automatically:

```json
{
  "mcpServers": {
    "cim-gui": {
      "command": "python",
      "args": ["-m", "cim_gui_mcp.server"],
      "cwd": "C:/code/claude/nativeApp/mcp"
    }
  }
}
```

After restarting Claude Code, the `cim-gui` server will appear in `/mcp` and all tools are callable from any conversation in this project.
