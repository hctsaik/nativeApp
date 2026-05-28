# module_015 — Dashboard（已合併至 module_017）

> ⚠️ **已廢棄**：module_015 的所有功能已合併至 [module_017 — 管理中心](module_017.md)（2026-05-23）。
> `sheet.yaml` 已移除此 tab；程式碼保留但不再被啟動。

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_015` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation` |
| 上游依賴 | module_026（manifest）、module_012（分類）、module_014（匯出記錄） |

顯示當前 Manifest 的標注進度、資料品質指標和匯出歷史，協助判斷資料集是否可進入訓練。

---

## 架構

```
015_input.py   → 讀 shared.json 取 manifest_id（無選擇器）
015_process.py → 掃描 X-AnyLabeling JSON + 分類 config + 匯出記錄
015_output.py  → 指標卡、進度條、分布圖、匯出記錄
_config.py     → shared manifest 解析 + 分類 config 路徑
```

---

## Process（`015_process.py`）

### `_scan_annotations(items)`

一次 IO pass 掃描所有 item 的 `{stem}.json`：

| 回傳欄位 | 說明 |
|----------|------|
| `annotated_ids` | 有 shapes（≥1 個框）的 item_id 集合 |
| `annotated` | `len(annotated_ids)` |
| `no_json` | 找不到 JSON 檔的 item 數 |
| `empty_json` | JSON 存在但 `shapes == []` 的 item 數 |
| `label_counts` | `{bbox_label: shape_count}` |
| `shapes_stats` | `{min, max, mean, median}` 每圖框數 |
| `last_annotation_at` | 最新 JSON mtime 的格式化時間字串 |

### `execute_logic(params)` 回傳

```python
{
    "mode": "done" | "idle" | "error",
    "manifest_name": str,
    "manifest_created_at": str,     # YYYY-MM-DD
    "source_path": str,             # 圖片來源資料夾
    "total_items": int,
    "annotated_xany": int,          # 有 bbox shapes 的圖片數
    "no_json_count": int,
    "empty_json_count": int,
    "classified_count": int,        # 有分類標籤的圖片數
    "annotated_no_class": int,      # 有 bbox 但沒分類（跨欄位一致性警告用）
    "export_count": int,
    "label_counts": dict[str, int],
    "classification_counts": dict[str, int],
    "shapes_stats": dict,
    "last_annotation_at": str,
    "export_history": list[dict],
}
```

---

## Output Page（`015_output.py`）

### 版面佈局

1. **Manifest 標頭**：名稱、來源資料夾路徑、建立日期
2. **進度摘要（4 欄）**：總圖數 / BBox 已標注（% delta）/ 已分類（% delta）/ 匯出次數
3. **進度條**：BBox 完成度 + 分類完成度
4. **標注健康度（4 欄）**：最後標注時間 / 平均框數 / 框數範圍 / 尚未標注（紅色警示）
5. **警告提示**：
   - 有 bbox 但無分類 → 警告影響 ImageFolder/CSV 匯出
   - 全無標注 → 提示前往 Annotation 頁籤
6. **BBox 標籤分布** + **分類標籤分布**（並排 bar chart）
7. **匯出記錄**：最近一次置頂顯示；多筆時折疊進 expander

---

## 常見問題

### 標注健康度顯示「—」

目前 Manifest 無任何 X-AnyLabeling JSON（尚未標注），或所有 JSON 的 `shapes` 都是空陣列。

### `annotated_no_class` 觸發警告

某些圖片已完成 bbox 標注，但 module_012 的分類 config 沒有對應 item_id 的記錄。  
解決：回到 Annotation 頁面，對這些圖片設定分類標籤，或用 AI Pre-labeling 補充分類。
