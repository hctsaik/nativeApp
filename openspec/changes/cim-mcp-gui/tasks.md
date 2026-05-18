# Tasks：CIM GUI MCP Server

## Phase 1 — 基礎架構

- [x] `mcp/requirements.txt`：mcp, playwright, httpx, pytest, pytest-asyncio, respx
- [x] `mcp/cim_gui_mcp/__init__.py`
- [x] `mcp/cim_gui_mcp/config.py`：SIDECAR_PORT, BROWSER_HEADLESS, DEFAULT_TIMEOUT
- [x] `mcp/cim_gui_mcp/sidecar_client.py`：SidecarClient（httpx async）
- [x] `mcp/cim_gui_mcp/browser_driver.py`：BrowserDriver（Playwright 單例）
- [x] `mcp/cim_gui_mcp/server.py`：FastMCP entry point + 所有 tools
- [x] `mcp/tests/conftest.py`
- [x] `mcp/tests/test_sidecar_client.py`（respx mock）
- [x] `mcp/tests/test_browser_driver.py`（Playwright mock）
- [x] `mcp/tests/test_config.py`
- [x] `pytest mcp/tests/` 全部通過（41 tests passed）

## Phase 2 — Claude Code 整合

- [x] `.claude/mcp.json`：cim-gui server 設定
- [x] `mcp/README.md`：完整使用說明（如何啟動 sidecar、如何使用各 tool）
- [x] `playwright install chromium`（記錄在 README）
- [x] 手動驗收：Claude 呼叫 `sidecar_health()` → OK
- [x] 手動驗收：Claude 呼叫 `sidecar_start_tool("cvmod-003")` + `browser_screenshot` → 看見 UI
- [x] 手動驗收：Claude 呼叫 `browser_click` + `browser_screenshot` → 確認互動有效

## Phase 3 — 收尾

- [x] 更新 `memory/current_focus.md`
