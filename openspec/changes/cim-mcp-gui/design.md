# 設計：CIM GUI MCP Server

---

## 整體架構

```
┌─────────────────────────────────────────────────────────────┐
│                   Claude Code（對話中）                       │
│   uses MCP tools → reads screenshots → makes decisions       │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP Protocol（stdio）
┌──────────────────────▼──────────────────────────────────────┐
│              cim-gui-mcp  (Python MCP Server)                │
│   mcp/cim_gui_mcp/server.py                                  │
│                                                              │
│  ┌─────────────────┐   ┌──────────────────┐                  │
│  │  SidecarClient  │   │  BrowserDriver   │                  │
│  │  (httpx)        │   │  (playwright)    │                  │
│  └────────┬────────┘   └──────────┬───────┘                  │
└───────────┼────────────────────────┼────────────────────────┘
            │ HTTP                   │ CDP / HTTP
┌───────────▼──────┐      ┌──────────▼──────────────────────┐
│  Python Sidecar  │      │  Streamlit Pages                 │
│  engine.py:8765  │      │  127.0.0.1:{dynamic ports}       │
│  /health         │      │  (started by sidecar on demand)  │
│  /tools          │      └──────────────────────────────────┘
│  /tools/*/start  │
└──────────────────┘
```

---

## 目錄結構

```
mcp/
├── cim_gui_mcp/
│   ├── __init__.py
│   ├── server.py            ← MCP server 入口點（FastMCP）
│   ├── sidecar_client.py    ← httpx wrapper for sidecar API
│   ├── browser_driver.py    ← Playwright 管理（單例）
│   └── config.py            ← 環境變數設定
├── tests/
│   ├── conftest.py
│   ├── test_sidecar_client.py  ← httpx respx mock
│   └── test_browser_driver.py  ← Playwright mock / 基礎功能
├── requirements.txt
└── README.md
```

---

## MCP Server（FastMCP）

```python
# server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("cim-gui-mcp")

@mcp.tool()
async def sidecar_health() -> str: ...

@mcp.tool()
async def browser_screenshot(url: str) -> Image: ...
```

**傳輸方式**：stdio（Claude Code 預設）
**進入點**：`python -m cim_gui_mcp.server`

---

## Tool 詳細規格

### Sidecar API Tools

#### `sidecar_health`
```
Input:  (none)
Output: str — "ok" 或 error message
Note:   讀取 CIM_SIDECAR_PORT env var，預設 8765
```

#### `sidecar_list_tools`
```
Input:  (none)
Output: JSON string — [{"tool_id", "name", "version", "category"}, ...]
```

#### `sidecar_start_tool`
```
Input:  tool_id: str
Output: JSON string — {"tool_id", "input_url", "output_url", "input_port", "output_port"}
Side effect: sidecar 啟動 Streamlit 程序，需等待就緒
```

#### `sidecar_stop_tool`
```
Input:  (none)
Output: str — "stopped"
```

---

### Browser Tools

#### `browser_screenshot`
```
Input:  url: str         # 完整 URL，例如 http://127.0.0.1:54321
        full_page: bool  # 預設 False（viewport only）
Output: Image（base64 PNG）← Claude 直接可見
Side effect: 若該 URL 無開啟頁面，自動建立
```

#### `browser_click`
```
Input:  url: str
        selector: str    # CSS selector 或 "text=按鈕文字"（Playwright 語法）
        timeout: int     # ms，預設 5000
Output: str — "clicked: {selector}"
```

#### `browser_fill`
```
Input:  url: str
        selector: str    # 輸入欄的 selector（支援 label text 定位）
        value: str
Output: str — "filled: {selector} = {value}"
```

#### `browser_get_text`
```
Input:  url: str
        selector: str    # 選填；省略則取整頁文字
Output: str — 元素或頁面的文字內容
```

#### `browser_wait_for`
```
Input:  url: str
        selector: str
        timeout: int     # ms，預設 10000
        state: str       # "visible"|"attached"|"hidden"，預設 "visible"
Output: str — "ready" 或 timeout error
```

#### `browser_close`
```
Input:  url: str   # 選填；省略則關閉所有頁面
Output: str — "closed"
```

---

### Assertion Tools

#### `assert_visible`
```
Input:  url: str
        selector: str
Output: dict — {"pass": bool, "message": str, "screenshot": base64_png}
```

#### `assert_text`
```
Input:  url: str
        selector: str
        expected: str    # 子字串比對（contains，不是完全相等）
Output: dict — {"pass": bool, "actual": str, "expected": str}
```

#### `assert_no_error`
```
Input:  url: str
Output: dict — {"pass": bool, "errors": [str]}
Note:   掃描 Streamlit 的 .stAlert[data-baseweb="notification"] 錯誤訊息
```

---

## BrowserDriver（Playwright 單例管理）

```python
class BrowserDriver:
    """Single Playwright browser instance, pages keyed by URL."""
    _browser: Browser | None = None
    _pages: dict[str, Page] = {}

    async def get_page(self, url: str) -> Page:
        if url not in self._pages or self._pages[url].is_closed():
            page = await self._browser.new_page()
            await page.goto(url, wait_until="networkidle")
            self._pages[url] = page
        return self._pages[url]

    async def screenshot(self, url: str) -> bytes: ...
    async def click(self, url: str, selector: str) -> None: ...
    async def fill(self, url: str, selector: str, value: str) -> None: ...
    async def get_text(self, url: str, selector: str | None) -> str: ...
```

**Playwright selector 策略**（Streamlit 特化）：

| 用途 | selector 範例 |
|------|-------------|
| 按鈕（文字） | `"button:has-text('▶ 執行')"` |
| 按鈕（Playwright text） | `"text=▶ 執行"` |
| Slider label | `"[data-testid='stSlider'] >> text=Width"` |
| Streamlit 錯誤 | `".stAlert"` |
| 任意文字 | `"text=執行完成"` |

---

## 設定（config.py）

```python
SIDECAR_PORT = int(os.environ.get("CIM_SIDECAR_PORT", "8765"))
SIDECAR_BASE = f"http://127.0.0.1:{SIDECAR_PORT}"
BROWSER_HEADLESS = os.environ.get("CIM_MCP_HEADLESS", "1") == "1"
DEFAULT_TIMEOUT = int(os.environ.get("CIM_MCP_TIMEOUT", "10000"))
```

`CIM_MCP_HEADLESS=0` 可讓瀏覽器視窗可見（debug 用）。

---

## Claude Code 整合（`.claude/mcp.json`）

```json
{
  "mcpServers": {
    "cim-gui": {
      "command": "python",
      "args": ["-m", "cim_gui_mcp.server"],
      "cwd": "${workspaceFolder}/mcp",
      "env": {
        "CIM_SIDECAR_PORT": "8765",
        "CIM_MCP_HEADLESS": "1"
      }
    }
  }
}
```

---

## 測試策略

### Unit tests（不需要執行中的 App）

| 測試檔 | 測試內容 |
|--------|---------|
| `test_sidecar_client.py` | mock httpx，驗證請求格式與回傳解析 |
| `test_browser_driver.py` | mock Playwright，驗證 page lifecycle |
| `test_config.py` | env var fallback |

### Integration tests（需要 sidecar 執行中）

標記為 `@pytest.mark.integration`，預設跳過，CI 可選擇性執行。

---

## 設計決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| MCP framework | FastMCP（`mcp` package） | 官方 SDK，最少 boilerplate |
| Browser engine | Playwright Chromium | 支援 async、headless、CDP；已知可連接 Electron |
| 傳輸方式 | stdio | Claude Code 原生支援，零配置 |
| Browser 單例 | 是 | 避免每次 tool call 重啟瀏覽器（慢且不穩定） |
| Streamlit selector | CSS + Playwright text | Streamlit 無固定 ID，需用文字定位 |
| `CIM_MCP_HEADLESS=0` | 支援但預設 headless | Debug 時可看到 Claude 在操作什麼 |
| Layer 2（Electron CDP） | 不納入 MVP | 需要 `ELECTRON_DEBUG=1` 啟動，增加複雜度；Layer 1 覆蓋主要場景 |
