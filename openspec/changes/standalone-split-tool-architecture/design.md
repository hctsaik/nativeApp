# 設計：Standalone Split-Tool 架構

## 架構概覽

```
portal (Portal React)
  → 使用者從下拉選單選擇工具
  → Electron 呼叫 /tools/{tool_id}/start
  → sidecar engine 啟動兩個 Streamlit subprocess
      ├── input process  → {tool_id}_input.py   (port A)
      └── output process → {tool_id}_output.py  (port B)
  → Portal 在 Input tab 載入 iframe(port A)
  → Portal 在 Output tab 載入 iframe(port B)
  → 兩個 iframe 常駐 DOM，tab 切換用 CSS display:none
```

---

## 核心機制

### 1. Split Script 偵測（engine.py `_split_scripts`）

engine 啟動工具時，先檢查是否存在對應的分割檔：

```
tools/
├── my_tool.py            ← 登錄於 SQLite 的 script_relative_path（空 stub）
├── my_tool_input.py      ← 存在時，input process 執行此檔
└── my_tool_output.py     ← 存在時，output process 執行此檔
```

- 若 `{stem}_input.py` 和 `{stem}_output.py` **同時存在** → 分別啟動
- 否則 → input / output 都執行同一個主檔案（向下相容舊工具）

### 2. 結果傳遞（JSON 結果檔）

Input 完成執行後，透過 `tool_result.write_result()` 寫入：

```
{CIM_LOG_DIR}/{tool_id}_result.json
```

**結果檔案為固定信封格式（envelope）：**

```json
{
  "user_input":     { "...使用者填寫的欄位..." },
  "process_result": { "...運算產出的資料..." }
}
```

Output 直接讀取此檔，**不使用 polling loop**。  
Portal 收到 `EXECUTE_COMPLETE` 後會自動 reload output iframe，
output page 在每次載入時讀取最新結果並靜態渲染。

```python
# output page — 只需這樣，不需要 time.sleep / st.rerun
from tool_result import read_result

data = read_result(RESULT_FILE)
if data is None:
    st.info("尚未執行…")
    return

ui = data["user_input"]
pr = data["process_result"]
# 渲染結果 ...
```

### 3. Portal tab iframe 常駐

Portal `main.jsx` 以 CSS 取代條件渲染，保留 Streamlit session：

```jsx
{inputUrl && (
  <iframe title="Input" src={inputUrl}
    style={{ display: activeTab === "input" ? "block" : "none" }} />
)}
{outputUrl && (
  <iframe title="Output" src={outputUrl}
    style={{ display: activeTab === "output" ? "block" : "none" }} />
)}
```

**效果**：切換至 Output tab 再切回 Input tab，sidebar 的選項、參數不遺失。

### 4. Portal 驅動 Output Reload

Input 執行完成後送出 `EXECUTE_COMPLETE` postMessage，Portal 接收後：

1. 將 `outputNonce` 遞增
2. Output iframe 的 `src` 自動更新為 `{outputBaseUrl}?_r={nonce}`
3. 瀏覽器偵測到 src 改變，reload output iframe
4. Output page 讀取最新結果檔並渲染

```jsx
// main.jsx — EXECUTE_COMPLETE handler
case MessageTypes.EXECUTE_COMPLETE:
  setIsExecuting(false);
  setActiveTab("output");
  if (payload.success !== false) {
    setOutputNonce((n) => n + 1);  // ← 這一行觸發 output iframe reload
  }
  break;

// output iframe src
const outputUrl = outputBaseUrl
  ? `${outputBaseUrl}${outputNonce > 0 ? `?_r=${outputNonce}` : ""}`
  : "";
```

### 5. postMessage 協定（tool_comms）

所有 Input page 統一透過 `tool_comms` 模組通知 Portal，不需各自實作：

```python
from tool_comms import notify_start, notify_complete

if st.button("▶ 執行"):
    notify_start()
    try:
        ...運算...
        write_result(RESULT_FILE, user_input, process_result)
        notify_complete()
    except Exception as exc:
        notify_complete(success=False, error=str(exc))
```

| 函式 | 送出訊息 | Portal 動作 |
|------|---------|------------|
| `notify_start()` | `EXECUTE_START` | 顯示 loading overlay |
| `notify_complete()` | `EXECUTE_COMPLETE` `{success: true}` | 隱藏 overlay、切至 Output、reload output iframe |
| `notify_complete(success=False, error=...)` | `EXECUTE_COMPLETE` `{success: false, error: ...}` | 隱藏 overlay、留在 Input tab |

---

## 共用工具程式庫（tools/ 目錄）

| 模組 | 用途 | 主要 API |
|------|------|----------|
| `tool_comms` | Portal ↔ Streamlit 溝通 | `notify_start()` `notify_complete(success, error)` |
| `tool_result` | 讀寫結果信封檔案 | `write_result(path, user_input, process_result)` `read_result(path)` |
| `ui_utils` | RWD 圖片 + lightbox | `show_image(source, caption)` |
| `db_utils` | SQLite 存取 | `SimpleDAO(db_path)` — `query / execute / execute_many / last_insert_id` |
| `log_utils` | 雙輸出 logging | `get_logger(name)` → stdout + `{CIM_LOG_DIR}/{name}.log` |

---

## 環境變數（由 engine `_spawn` 注入）

| 變數 | 說明 |
|------|------|
| `CIM_TOOL_ID` | 工具 ID（如 `opencv-tool`） |
| `CIM_TOOL_LAYER` | `"input"` 或 `"output"` |
| `CIM_LOG_DIR` | 結果 JSON 與 log 的寫入目錄 |
| `CIM_SELECTED_PATHS_FILE` | host 選取的檔案路徑 JSON |

---

## 結果 JSON 信封規範

固定最外層格式，內容依工具需求自訂：

```json
{
  "user_input": {
    "func_name": "高斯模糊",
    "image_label": "road.png",
    "width": 1280,
    "height": 720,
    "params": { "kernel_size": "5", "sigma": "1.0" }
  },
  "process_result": {
    "elapsed_ms": 12.3,
    "original_b64": "<base64 PNG>",
    "result_b64": "<base64 PNG>"
  }
}
```

**原則**：
- `user_input` — 使用者決定的參數（可在 Output 旁顯示輸入條件）
- `process_result` — 運算才知道的結果（含影像、統計數據等）
- **Numpy array 序列化**：`cv2.imencode(".png", img)` → base64，不可直接序列化 ndarray

---

## Input 腳本標準結構

```python
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
from tool_comms import notify_start, notify_complete
from tool_result import write_result

TOOL_ID = os.environ.get("CIM_TOOL_ID", "my-tool")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"

def main():
    st.set_page_config(page_title="My Tool — Input", layout="wide")

    # 1. 收集輸入（sidebar 或 main area）
    value = st.text_input("請輸入...")

    # 2. 執行按鈕（右上角，不被內容遮蔽）
    col_info, col_btn = st.columns([4, 1])
    with col_btn:
        execute = st.button("▶ 執行", type="primary", use_container_width=True)

    # 3. 預覽（可選）

    # 4. 執行
    if execute:
        notify_start()
        try:
            result = value.upper()   # 運算邏輯
            write_result(RESULT_FILE,
                user_input={"value": value},
                process_result={"result": result})
            notify_complete()
            st.success("執行完成，請切換至 Output 頁籤查看結果。")
        except Exception as exc:
            notify_complete(success=False, error=str(exc))
            st.error(f"執行失敗：{exc}")

if __name__ == "__main__":
    main()
```

---

## Output 腳本標準結構

```python
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
from tool_result import read_result

TOOL_ID = os.environ.get("CIM_TOOL_ID", "my-tool")
LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", "/tmp"))
RESULT_FILE = LOG_DIR / f"{TOOL_ID}_result.json"

def main():
    st.set_page_config(page_title="My Tool — Output", layout="wide")

    data = read_result(RESULT_FILE)

    if data is None:
        st.title("執行結果")
        st.info("尚未執行，請在 Input 頁籤完成輸入後按下 ▶ 執行。")
        return   # ← 靜止等待，不需要 polling loop

    ui = data["user_input"]
    pr = data["process_result"]

    st.title("執行結果")
    st.write("輸入：", ui.get("value"))
    st.write("結果：", pr.get("result"))

if __name__ == "__main__":
    main()
```

> **重要**：Output page 不可有 `time.sleep` + `st.rerun()` 的 polling loop。
> Portal 的 `EXECUTE_COMPLETE` handler 負責 reload，output page 只需靜態渲染。

---

## 工具登錄（SQLite seed）

工具主檔（stub）登錄於 `engine.py` seed，實際執行的是 split 檔：

```python
(
    "my-tool",           # tool_id
    "我的工具",           # name
    "my_tool.py",        # script_relative_path（_split_scripts 從此推導分割檔路徑）
    "0.1.0",             # version
    None,                # signature
    "seed",              # source_commit
    "system",            # author
    None,                # approved_at
    1,                   # enabled
),
```

---

## 參考實作

| 工具 | Input | Output | 特點 |
|------|-------|--------|------|
| `opencv-tool` | `opencv_tool_input.py` | `opencv_tool_output.py` | base64 影像序列化；`process_result` 含原圖+處理後圖 |
| `animal-tagger` | `animal_tagger_input.py` | `animal_tagger_output.py` | Output 直接讀寫 SQLite DB（互動式標記）；`process_result` 為空 |

---

## 測試策略

| 層次 | 測試目標 | 測試檔案 |
|------|---------|---------|
| Portal 通訊 | `notify_start` / `notify_complete` JSON 格式、`_cim` flag | `test_tool_comms.py` |
| 結果信封 | `write_result` / `read_result` 格式、舊格式退化為 None | `test_tool_result.py` |
| Split 偵測 | `_split_scripts()` fallback 邏輯 | `test_split_scripts.py` |
| 影像序列化 | `_encode_image` / `_decode_image` roundtrip | `test_opencv_tool_io.py` |
| DB 操作 | `_query_records` / `_update_tag` / `_next_untagged_index` | `test_animal_tagger.py` |
| SQLite DAO | `SimpleDAO` 全部 method | `test_db_utils.py` |
| Logging | `get_logger` handler 數量、檔案建立、level | `test_log_utils.py` |
| 工具登錄 | seed 內容、enabled flag | `test_sqlite_adapter.py` |

Streamlit UI 層不在單元測試範圍內；以 Puppeteer E2E 測試驗收。
