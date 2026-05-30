# Module 006 — 動物影像標記

> **完整技術文件**：[docs/modules/module_006.md](../../../../../docs/modules/module_006.md)
> **使用者操作指南**：[guide.html](guide.html)（嵌入於 Input 頁面「📖 使用說明」）

---

## 快速參考

### 檔案清單

| 檔案 | 用途 |
|---|---|
| `plugin.yaml` | 模組宣告（id, name, runner, version）|
| `_config.py` | 讀寫 `{CIM_LOG_DIR}/config/module_006.json` |
| `006_input.py` | Streamlit Input 頁面，`render_input() → dict` |
| `006_process.py` | 純計算，`execute_logic(params) → dict`，**禁止 Streamlit** |
| `guide.html` | 使用者操作指南（HTML，嵌入於 Input 頁）|

> output 層位於 `tools/animal_tagger_output.py`

---

## render_input() 回傳合約

```python
{
    "filter": str,      # "ALL" | "貓" | "狗" | "大象"
    "db_path": str,     # 預設 testData/animal/animals.db
    "image_dir": str    # 預設 testData/animal/
}
```

## execute_logic() 行為

```python
# 成功（DB 存在）
params  →  params（原封不動）

# DB 不存在
params  →  {**params, "error": "db_not_found"}
```

---

## 設定系統

設定檔：`{CIM_LOG_DIR}/config/module_006.json`

```json
{ "annotation_labels": ["眼睛", "鼻子", "嘴巴"] }
```

```python
from _config import get_annotation_labels, set_annotation_labels
labels = get_annotation_labels()   # → list[str]
set_annotation_labels(["眼", "鼻"])
```

---

## 標注 JSON 格式（動物影像）

```json
{
    "image": "cat_001.jpg",
    "bboxes": [[x, y, w, h]],
    "labels": [0],
    "label_list": ["貓", "狗", "大象", "unknown"],
    "updated_at": "2026-05-16 10:00:00"
}
```

檔名規則：`{stem}_annotations.json`，與影像同目錄存放。
