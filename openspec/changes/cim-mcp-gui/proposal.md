# 變更：CIM GUI MCP Server（cim-mcp-gui）

## 為何需要此變更

目前開發流程的瓶頸：

1. **Claude 看不見 GUI**：每次 UI 改動後，需要人工啟動 App、截圖、描述所見，再告訴 Claude 是否符合 Spec。Claude 無法自驗。
2. **無法 iteration**：修改 → 人工測試 → 反饋 → 修改 的週期完全依賴人工，速度慢、容易漏測。
3. **Spec 與實作的落差只靠人工發現**：Design Doc 裡描述的 UI 行為（按鈕 icon、toast 訊息、表格欄位）無法自動驗證。

## 變更目標

建立一個 **MCP Server**，讓 Claude 能夠：

1. **看見 GUI**：對任何 Streamlit 工具或 Portal 截圖，直接得到可視的畫面
2. **操作 GUI**：點擊按鈕、填寫輸入、切換 Tab
3. **讀取狀態**：取得頁面文字、確認元素是否可見
4. **自驗 Spec**：對照 design.md 的預期行為，自行判斷是否通過

## 核心概念：兩層測試架構

```
┌──────────────────────────────────────────────────────────┐
│   Layer 1 — Tool Testing（無需 Electron）                 │
│   Playwright → Streamlit URL（直接連接工具 Port）          │
│   適用：模組 UI、Workflow Tab、功能邏輯驗證               │
├──────────────────────────────────────────────────────────┤
│   Layer 2 — Full App Testing（需要 Electron）             │
│   Playwright → CDP Port 9222 → Electron Window           │
│   適用：Portal 下拉選單、Start/Stop 按鈕、整體 UX 驗證    │
└──────────────────────────────────────────────────────────┘
```

MVP 優先實作 Layer 1（價值最高、複雜度最低）。
Layer 2 待 Layer 1 穩定後加入。

## MCP Tools 清單（MVP）

### Sidecar API Tools
| Tool | 說明 |
|------|------|
| `sidecar_health` | GET /health，確認 sidecar 執行中 |
| `sidecar_list_tools` | GET /tools，列出可用工具 |
| `sidecar_start_tool(tool_id)` | POST /tools/{id}/start，啟動工具並回傳 URL |
| `sidecar_stop_tool` | POST /tools/stop |

### Browser Tools（Playwright → Streamlit）
| Tool | 說明 |
|------|------|
| `browser_screenshot(url)` | 截圖並回傳 base64 PNG（Claude 可直接看） |
| `browser_click(url, selector)` | 點擊 CSS selector 或文字 |
| `browser_fill(url, selector, value)` | 填寫輸入欄 |
| `browser_get_text(url, selector?)` | 取得頁面或元素文字 |
| `browser_wait_for(url, selector, timeout?)` | 等待元素出現 |
| `browser_close(url?)` | 關閉瀏覽器頁面 |

### Assertion Tools
| Tool | 說明 |
|------|------|
| `assert_visible(url, selector)` | 確認元素可見，回傳 pass/fail + 截圖 |
| `assert_text(url, selector, expected)` | 確認文字符合預期 |
| `assert_no_error(url)` | 確認頁面無 Streamlit 錯誤 alert |

## 使用流程（示意）

```
Claude:
  1. sidecar_health()                    → OK, port=8765
  2. sidecar_start_tool("cvmod-003")     → {input_url, output_url}
  3. browser_screenshot(input_url)       → [看見 Input 表單]
  4. browser_fill(input_url, "Width", "600")
  5. browser_click(input_url, "▶ 執行")
  6. browser_wait_for(output_url, ".stImage")
  7. browser_screenshot(output_url)      → [看見生成的影像]
  8. assert_no_error(output_url)         → PASS
  ✓ 自動確認模組 003 功能正常
```

## 不納入（MVP）

- Layer 2（Electron CDP 控制）
- 自動化 CI/CD pipeline 整合
- 影像相似度比對（pixel diff）
- 效能測量
