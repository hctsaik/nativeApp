# Module 002：影像資訊讀取

> **注意**：此模組已從 Portal 下拉隱藏（`enabled=0`），僅供 Sheet 內嵌使用。Scripts 資料夾保留不刪除。

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_002` |
| **用途** | 讀取固定測試圖片的中繼資料，示範最簡單的模組架構 |
| **Portal 狀態** | 停用（Sheet 內嵌使用）|

---

## Input 層（002_input.py）

- **固定影像**：僅使用 `tools/road.png`，直接顯示預覽，不提供上傳選項
- **Memo 欄位**：`st.text_input`，可輸入任意備註文字

```python
render_input() → {
    "image_path": str,   # road.png 的絕對路徑
    "memo": str          # 使用者備註（可為空字串）
}
```

---

## Process 層（002_process.py）

使用 **Pillow（PIL）** 開啟影像（而非 OpenCV）。

```python
execute_logic(params) → {
    "filename": str,
    "resolution": (int, int),  # (width, height)
    "file_size_bytes": int,
    "file_size_kb": float,
    "memo": str
}
```

> **序列化注意**：`resolution` 為 tuple，runner 序列化時自動轉為 list；output 層讀取 result.json 後以 `tuple(data["resolution"])` 還原。

---

## Output 層（002_output.py）

以 `st.table` 顯示四個欄位：檔案名稱、解析度、檔案大小、Memo。
