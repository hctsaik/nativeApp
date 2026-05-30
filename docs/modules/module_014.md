# module_014 — Export（多格式匯出）

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_014` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation` |
| 上游依賴 | module_026（manifest）、module_012（分類結果） |

將當前 Manifest 的 X-AnyLabeling 標注結果批次匯出為 ML 訓練常用格式，或回傳至外部任務系統（iWISC deliver_result）。

---

## 支援格式

| 格式 | 說明 |
|------|------|
| `coco_json` | COCO JSON（含 categories、images、annotations；支援 rectangle + polygon） |
| `yolo_txt` | YOLO txt + `data.yaml` + `classes.txt`；bbox 座標正規化 |
| `pascal_voc` | Pascal VOC XML（`Annotations/`）+ `ImageSets/Main/{split}.txt` |
| `imagefolder` | PyTorch ImageFolder 結構：`{split}/{label}/{filename}` |
| `csv` | 平面 CSV：file_path、split、label、classification、x1/y1/x2/y2 |

---

## 架構

```
014_input.py   → 讀 shared.json 取 manifest_id，選格式、輸出目錄、分割比
014_process.py → 解析 X-AnyLabeling JSON、執行各格式匯出、寫 annotation_exports 記錄
014_output.py  → 各格式輸出路徑 + 開啟資料夾按鈕
_config.py     → 設定持久化、分類 config 讀取、shared manifest 解析
```

---

## Input Page（`014_input.py`）

- **不顯示 Manifest 選擇器**：自動從 `shared.json` 取 manifest_id
- **格式多選**：至少選一種
- **輸出目錄**：預設 `{CIM_LOG_DIR}/exports/module_014_{manifest_id[:12]}/`
- **Train/Val/Test 分割**（可選）：啟用時設定比例（須加總 = 100）；關閉則全部放 `"all"` 群組

回傳 params：

```python
{
    "manifest_id": str,
    "export_formats": list[str],   # ["coco_json", "yolo_txt", ...]
    "export_dir": str,
    "enable_split": bool,
    "split_train": int,            # 百分比，enable_split=False 時忽略
    "split_val": int,
    "split_test": int,
    "stratified": bool,
}
```

---

## Process（`014_process.py`）

### 主流程

```
execute_logic()
  ├─ 從 DB 取 items + 讀 X-AnyLabeling JSON → shapes_map
  ├─ 讀分類 config → classifications
  ├─ _build_split_groups() → {"train":[item_id,...], "val":[], "test":[]}
  └─ 對每個選定格式呼叫對應 export_* 函式
```

### Shape 解析（`_parse_shapes`）

| shape_type | 處理方式 |
|------------|---------|
| `rectangle` | 取 `points[0]`(x1,y1) 和 `points[-1]`(x2,y2) |
| `polygon` | 原始 points 保留；bbox 為 min/max 外接矩形 |
| 其他（point、line…）| 跳過 |

### 分割邏輯

- `enable_split=False`：所有 item 歸 `"all"`，匯出無 train/val/test 子目錄
- `enable_split=True`：以 `split_train:split_val:split_test` 比例隨機分割；`stratified=True` 時依分類標籤做 stratified split

### 匯出記錄

每次執行成功後，將各格式的結果寫入 `annotation_exports` 資料表（供 module_015 Dashboard 讀取）。

---

## Output Page（`014_output.py`）

- 各格式顯示輸出路徑 + 📂 開啟資料夾按鈕
- 統計：標注圖片數 / 分類圖片數 / 格式數

---

## 資料流

```
shared.json → manifest_id
manifest.sqlite → items（file_path, item_id, width, height）
{image_dir}/{stem}.json → X-AnyLabeling shapes
module_012_classifications_{mid[:12]}.json → classification labels
        │
        ▼
014_process.execute_logic()
  ├─ coco_json → {export_dir}/coco/{split}/annotations.json
  ├─ yolo_txt  → {export_dir}/yolo/{labels,images}/{split}/*.txt + data.yaml
  ├─ pascal_voc→ {export_dir}/voc/{Annotations,JPEGImages,ImageSets/Main}/
  ├─ imagefolder→ {export_dir}/imagefolder/{split}/{label}/{filename}
  └─ csv       → {export_dir}/csv/annotations.csv
```

---

## 常見問題

### 匯出後 train/ 資料夾是空的

`split_train` 設為 0，或 Manifest 沒有任何有標注的圖片。確認 Annotation 頁面已完成標注。

### ImageFolder 匯出後某些圖片被跳過

這些圖片在 module_012 沒有分類標籤。ImageFolder 須依標籤建資料夾，無標籤的圖片計入 `_skipped`。
