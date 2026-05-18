# Module 005：邊緣記錄查詢

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_005` |
| **用途** | 查詢 module_004 寫入的 `edge_records.sqlite`，支援多維度篩選、影像預覽、CSV 匯出、單筆/批次刪除 |

---

## Input 層（005_input.py）

```python
render_input() → {
    "date_from": str,       # "YYYY-MM-DD"
    "date_to": str,         # "YYYY-MM-DD"
    "parts": list[str],     # 空 list = 全部
    "image_name_kw": str,   # 空字串 = 不篩選
    "left_min": float,
    "left_max": float,
    "right_min": float,
    "right_max": float
}
```

---

## Process 層（005_process.py）

動態組裝 WHERE 條件（全用 `?` 佔位符防 SQL injection）：

```sql
DATE(timestamp) BETWEEN ? AND ?
[AND parts IN (?,...)]
[AND image_name LIKE '%?%']
[AND left_roughness BETWEEN ? AND ?]
[AND right_roughness BETWEEN ? AND ?]
ORDER BY timestamp DESC
```

---

## Output 層（005_output.py）

| 功能 | 說明 |
|---|---|
| 表格（12 欄）| 料號、影像檔名（點擊預覽）、各指標、尺寸、時間戳記、下載、刪除 |
| 影像預覽 Dialog | `@st.dialog` 顯示大圖 + 完整指標 |
| CSV 匯出 | `📥 匯出 CSV`，UTF-8 BOM 編碼 |
| 批次刪除 | `🗑️ 刪除全部` 需二次確認 |
