# module_018 — Review Gallery（標注審查）

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_018` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation` |
| 上游依賴 | module_026（manifest）、module_012（標注 JSON） |

以 Grid 縮略圖 + BBox overlay 快速瀏覽整批標注結果，支援多種篩選條件和詳細檢視。

---

## 架構

```
018_input.py   → 篩選條件、每行圖片數、BBox overlay 開關、標籤篩選
018_process.py → execute_logic()：讀取並篩選 items + annotation 狀態
018_output.py  → Grid 縮略圖 + PIL overlay 渲染 + 詳細檢視 + 分頁
_config.py     → get_manifest_db_path() / get_shared_manifest_id()
```

---

## 篩選條件

| 條件 | 說明 |
|------|------|
| 全部 | 顯示所有 items |
| 已標注 (有 BBox) | shapes 非空 |
| 未標注 | shapes 為空或無 JSON |
| 已分類 | flags.classification 非空 |
| 未分類 | flags.classification 為空 |
| 標籤篩選 | shapes 中含指定 label 的圖片 |

---

## BBox Overlay 渲染

`_render_thumb_with_overlay()` 使用 `Pillow` 渲染縮略圖：

1. 開啟原始圖片，縮放至 320×240 縮略圖
2. 依 `(img_path, ann_path, ann_mtime)` 做 LRU 快取（最多 500 張）
3. 每個 shapes[] 繪製彩色矩形框（最多 10 種循環顏色）+ 標籤文字
4. 返回 JPEG bytes，直接傳給 `st.image()`

---

## Output Page UI

- **摘要 Metrics**：顯示數 / 總計 / 含 BBox 數
- **分頁**：每頁最多 30 張（n 頁導覽）
- **詳細檢視**：點擊「🔍 詳細」顯示大圖 + BBox 數量 / 標籤 / 分類 / 路徑
- **Grid**：每行 N 欄（Input 設定），每張圖顯示縮略圖 + badge + 詳細按鈕
- **重新整理**：清除 session cache 強制重新讀取磁碟

---

## 效能

- `_get_items()` 以 manifest_id + filter + label 做 session_state 快取
- 篩選在 process 層完成，output 只 render 當頁項目（PAGE_SIZE = 30）
- PIL overlay 按 ann_path mtime 失效，重新標注後自動刷新

---

## 資料流

```
shared.json → manifest_id → manifest.sqlite → items (file_path)
        │
        ▼
018_process.execute_logic()
  ├─ 讀取每個 {stem}.json
  ├─ 判斷 has_bbox / has_classification / labels
  └─ 套用篩選條件 → enriched items

018_output.render_output()
  └─ PIL.Image + ImageDraw → BBox overlay JPEG
  └─ st.image() Grid 顯示
```
