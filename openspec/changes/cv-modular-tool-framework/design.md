# 設計：共用 CV 模組框架

## 目錄架構

```
sidecar/python-engine/
├── engine.py                        # 不變
├── tools/                           # 不變（現有工具）
│   ├── opencv_tool.py
│   └── sample_csv_tool.py
├── scripts/                         # ★ 新增：模組框架根目錄
│   ├── __init__.py                  # 空，讓 scripts 成為 Python package
│   ├── module_001/                  # OpenCV 影像處理（示範模組）
│   │   ├── __init__.py
│   │   ├── 001_input.py
│   │   ├── 001_process.py
│   │   ├── 001_output.py
│   │   └── 001_process_test.py      # pytest 單元測試
│   └── module_002/                  # 下一個模組佔位
│       └── ...
└── cv_framework_runner.py           # ★ 新增：Framework Runner Streamlit 入口
```

---

## 介面契約（Interface Contract）

每個模組的三個檔案必須嚴格遵守以下函數簽名，否則 Framework Runner 無法載入。

### 📥 `{ID}_input.py` — 輸入定義層

```python
def render_input() -> dict:
    """
    渲染 Streamlit 輸入組件（Slider、Uploader、Selectbox 等）。
    回傳包含所有 process 層所需參數的 dict（params_pack）。

    規範：
    - 禁止呼叫 execute_logic()
    - 禁止寫入任何 DB 或外部狀態
    - 所有 st.xxx 調用僅限此層
    """
    ...
    return params_pack: dict
```

### ⚙️ `{ID}_process.py` — 邏輯運算層

```python
def execute_logic(params: dict) -> dict:
    """
    執行核心運算（OpenCV、pandas、scikit-learn 等）。
    回傳包含所有 output 層所需資料的 dict（result_pack）。

    規範：
    - 禁止 import streamlit 或呼叫 st.xxx
    - 禁止直接操作 Streamlit session_state
    - 必須為純函式（相同輸入 → 相同輸出）
    - 允許讀取本機檔案（params 中的路徑）
    """
    ...
    return result_pack: dict
```

### 📤 `{ID}_output.py` — 結果展示層

```python
def render_output(result: dict) -> None:
    """
    根據 result_pack 渲染圖表、表格或訊息。

    規範：
    - 不應修改 result dict
    - 不應呼叫 execute_logic()
    - 不應使用 st.form 或觸發重新運算的 widget
    """
    ...
```

---

## 資料流模型（Data Flow）

```
┌──────────────────────────────────────────────────────────┐
│  Framework Runner（cv_framework_runner.py）               │
│                                                          │
│  State 0: 側邊欄列出所有 scripts/module_* 模組           │
│           使用者選取 module_001                           │
│                                                          │
│  State 1: 載入 module_001.001_input                      │
│           呼叫 render_input() → params_pack              │
│                                                          │
│  State 2: 使用者按下「▶ 執行」按鈕                        │
│           呼叫 execute_logic(params_pack) → result_pack  │
│           result_pack 存入 st.session_state              │
│                                                          │
│  State 3: 呼叫 render_output(result_pack)                │
│           渲染完成                                        │
└──────────────────────────────────────────────────────────┘
```

---

## Framework Runner 設計（`cv_framework_runner.py`）

```python
import importlib
import sys
from pathlib import Path
import streamlit as st

SCRIPTS_DIR = Path(__file__).parent / "scripts"

def discover_modules() -> dict[str, str]:
    """掃描 scripts/module_* 資料夾，回傳 {顯示名稱: module_id}。"""
    modules = {}
    for folder in sorted(SCRIPTS_DIR.glob("module_*")):
        if folder.is_dir() and (folder / "__init__.py").exists():
            mid = folder.name.split("_", 1)[1]  # "001"
            # 嘗試從 __init__.py 讀取 MODULE_NAME 常數
            init_path = folder / "__init__.py"
            name = mid
            try:
                spec = importlib.util.spec_from_file_location(f"scripts.{folder.name}", init_path)
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                name = getattr(mod, "MODULE_NAME", mid)
            except Exception:
                pass
            modules[name] = mid
    return modules

def load_layer(module_id: str, layer: str):
    """動態載入 scripts/module_{id}/{id}_{layer}.py 模組。"""
    file = SCRIPTS_DIR / f"module_{module_id}" / f"{module_id}_{layer}.py"
    spec = importlib.util.spec_from_file_location(f"scripts.module_{module_id}.{layer}", file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def main():
    st.title("CIM CV 模組框架")
    modules = discover_modules()

    with st.sidebar:
        selected_name = st.selectbox("選擇模組", list(modules.keys()))

    module_id = modules[selected_name]

    input_mod = load_layer(module_id, "input")
    process_mod = load_layer(module_id, "process")
    output_mod = load_layer(module_id, "output")

    params = input_mod.render_input()

    if st.button("▶ 執行", type="primary"):
        with st.spinner("運算中…"):
            result = process_mod.execute_logic(params)
        st.session_state["last_result"] = result

    if "last_result" in st.session_state:
        output_mod.render_output(st.session_state["last_result"])

if __name__ == "__main__":
    main()
```

---

## `__init__.py` 慣例

每個模組的 `__init__.py` 僅需一行常數，Framework Runner 用來顯示名稱：

```python
MODULE_NAME = "OpenCV 影像處理"  # 顯示在下拉選單的名稱
```

---

## engine.py 整合

在 `SQLiteToolAdapter._initialize()` seed 中新增：

```sql
INSERT OR IGNORE INTO tools (tool_id, name, script_relative_path, version,
    signature, source_commit, author, approved_at, enabled)
VALUES ('cv-framework', 'CV 模組框架', 'cv_framework_runner.py', '0.1.0',
    NULL, 'seed', 'system', NULL, 1)
```

---

## 測試策略

- **每個 `{ID}_process.py` 必須有對應的 `{ID}_process_test.py`**
- 測試使用 pytest，直接 import process 層（無 Streamlit 依賴）
- 輸入：合成的小型資料（numpy array、dict）
- 驗證：輸出形狀、類型、數值合理性

```python
# 範例：001_process_test.py
import numpy as np
from scripts.module_001.process_001 import execute_logic

def test_grayscale_output_shape():
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    result = execute_logic({"image": img, "operation": "grayscale"})
    assert result["processed_image"].shape == (100, 100)
```

---

## Claude Code Skill 規格（`/new-cv-module`）

### 觸發方式

```
/new-cv-module
```

### Skill 執行流程

1. **詢問參數**（如尚未提供）：
   - 模組 ID（3 位數字，如 `002`）
   - 模組中文名稱（如 `CSV 數據分析`）
   - 輸入描述（如 `上傳 CSV 檔，選擇欄位`）
   - 運算描述（如 `移動平均，可調 window size`）
   - 輸出描述（如 `Plotly 折線圖`）

2. **生成檔案**：
   - `scripts/module_{ID}/__init__.py`（含 MODULE_NAME）
   - `scripts/module_{ID}/{ID}_input.py`（含 render_input() stub + Streamlit 組件）
   - `scripts/module_{ID}/{ID}_process.py`（含 execute_logic() stub + 核心邏輯）
   - `scripts/module_{ID}/{ID}_output.py`（含 render_output() stub + 圖表）
   - `scripts/module_{ID}/{ID}_process_test.py`（含基本 pytest 測試）

3. **提示確認**：
   - 列出已生成的檔案
   - 提示「執行 `npm run test:python` 確認測試通過」
   - 提示「engine.py 已自動更新 seed，重啟 sidecar 後可在框架下拉選單看到新模組」

### Skill 檔案位置

```
.claude/commands/new-cv-module.md
```

### Skill 能力邊界

- **可以**：生成符合介面契約的骨架程式碼
- **可以**：根據描述推斷適合的 Streamlit 組件和 OpenCV/pandas 函式
- **不應該**：修改 `engine.py` 的 SQLiteToolAdapter 結構
- **不應該**：生成超過 150 行的 process 層（複雜邏輯需人工審閱）

---

## 快速開始：以 module_002 為例建立新模組

以下步驟以 `module_002`（影像資訊讀取）為範本，說明如何建立一個新的 CV 模組。

### 1. 建立資料夾與 `__init__.py`

```bash
mkdir sidecar/python-engine/scripts/module_003
```

```python
# module_003/__init__.py
MODULE_NAME = "你的模組名稱"
```

### 2. 實作三層檔案

**`003_input.py`** — 收集使用者輸入，回傳 dict：
```python
import streamlit as st
from pathlib import Path

_TOOLS_DIR = Path(__file__).resolve().parent.parent.parent / "tools"

def render_input() -> dict:
    memo = st.text_input("備註")
    return {"image_path": str(_TOOLS_DIR / "road.png"), "memo": memo}
```

**`003_process.py`** — 純運算，禁止 `import streamlit`：
```python
import os
from pathlib import Path
from PIL import Image

def execute_logic(params: dict) -> dict:
    path = params["image_path"]
    with Image.open(path) as img:
        w, h = img.size
    return {"filename": Path(path).name, "resolution": (w, h), "memo": params["memo"]}
```

**`003_output.py`** — 渲染結果：
```python
import streamlit as st

def render_output(result: dict) -> None:
    w, h = result["resolution"]
    st.table({"欄位": ["檔案", "解析度", "備註"],
              "值": [result["filename"], f"{w}×{h}", result["memo"]]})
```

### 3. 撰寫測試並執行

```bash
cd sidecar/python-engine
python -m pytest scripts/module_003/ -v
```

### 4. 使用 `/new-cv-module` 自動生成骨架

執行 `/new-cv-module` skill，依提示輸入模組 ID 和描述，Claude 會自動生成上述 5 個檔案並執行測試。

---

## 框架契約摘要表

| 層 | 檔案 | 必須實作 | 回傳型別 | 禁止事項 |
|----|------|----------|----------|----------|
| Input | `{ID}_input.py` | `render_input()` | `dict`（可序列化為 JSON） | 呼叫 `execute_logic` |
| Process | `{ID}_process.py` | `execute_logic(params: dict)` | `dict`（純 Python 型別） | `import streamlit`、任何 st.xxx |
| Output | `{ID}_output.py` | `render_output(result: dict)` | `None` | 觸發重新運算 |
| Test | `{ID}_process_test.py` | pytest 測試 | — | — |

**JSON 序列化限制：** `execute_logic` 的回傳值會序列化為 JSON 再傳給 `render_output`，因此回傳 dict 只能包含 `str / int / float / bool / list / tuple / None`。numpy array 等物件無法序列化，會被丟棄。

---

## 設計決策說明

| 決策 | 選擇 | 理由 |
|------|------|------|
| 模組探索方式 | 掃描 `scripts/module_*` 資料夾 | 不需要改動 engine.py，新增模組只需加資料夾 |
| process 層純粹性 | 禁止 import streamlit | 保證可被 C# API 直接呼叫，也可被 pytest 測試 |
| 動態載入方式 | `importlib.util` | 不污染全域 sys.modules，重新選模組時可重載 |
| 現有工具相容性 | 保持 tools/ 目錄不變 | 向後相容，opencv_tool.py 繼續獨立運作 |
| Skill 語言 | Claude Code markdown skill | 利用現有 Claude Code 基礎設施，無需安裝額外工具 |
