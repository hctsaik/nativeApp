# module_017 — 管理中心（Dashboard + Label Manager）

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_017` |
| Tab 標籤 | `📊 管理中心` |
| Sheet | `sheet-annotation` |
| 上游依賴 | module_026（manifest）、module_012（標注 JSON / 分類）、module_014（匯出記錄）|

原 module_015（Dashboard）與 module_017（Label Manager）合併為單一頁籤。
Output 頁以 `st.tabs` 分成兩層：

| Tab | 功能 |
|-----|------|
| 📊 統計總覽 | 標注進度、健康度指標、標籤分布圖、匯出記錄（唯讀）|
| 🏷️ 標籤管理 | 全域改名 / 合併 / 刪除，近似重複偵測 |

---

## 架構

```
017_input.py
  └─ 自動從 shared.json 取得 manifest_id，顯示 manifest 資訊

017_process.py
  ├─ execute_logic()   — 一次 IO 掃描，同時回傳 Dashboard 統計 + Label Manager 資料
  ├─ do_rename(params, old, new)
  ├─ do_merge(params, sources, target)
  └─ do_delete(params, label)

017_output.py
  ├─ _render_dashboard()     — 統計總覽 tab
  └─ _render_label_manager() — 標籤管理 tab

_config.py
  ├─ get_manifest_db_path()
  ├─ get_shared_manifest_id()
  └─ load_classifications(manifest_id)

cim_annotation/label_ops.py
  └─ scan_labels, find_near_duplicates, rename_label, merge_labels, delete_label
```

---

## execute_logic 回傳格式

```python
{
    # ── Label Manager ──────────────────────────────────
    "manifest_id":   str,
    "label_map":     dict[str, list[str]],   # {label: [file_path, ...]}
    "near_dupes":    list[tuple[str, str, float]],
    "items":         list[dict],

    # ── Dashboard ──────────────────────────────────────
    "manifest_name":        str,
    "manifest_created_at":  str,   # YYYY-MM-DD
    "source_path":          str,
    "total_items":          int,
    "annotated_xany":       int,   # 有 shapes 的圖數
    "no_json_count":        int,
    "empty_json_count":     int,
    "classified_count":     int,
    "annotated_no_class":   int,   # 有 bbox 但無分類
    "export_count":         int,
    "label_counts":         dict[str, int],
    "classification_counts":dict[str, int],
    "shapes_stats":         dict,  # {min, max, mean, median}
    "last_annotation_at":   str,
    "export_history":       list[dict],
}
```

---

## 統計總覽（Tab 1）

1. **Manifest 標頭**：名稱、來源資料夾、建立日期
2. **進度摘要 Metrics**（4 欄）：總圖數、BBox 已標注 %、已分類 %、匯出次數
3. **進度條**：標注 / 分類兩條
4. **標注健康度**（4 欄）：最後標注時間、每圖平均框數、框數範圍（min–max）、尚未標注張數（紅/綠）
5. **警告**：有 BBox 但尚未分類 → 匯出 ImageFolder/CSV 時分類欄位留空
6. **標籤分布**（左：BBox、右：分類，各一張 bar_chart）
7. **匯出記錄**：最近一次置頂 + 全部歷史 expander

---

## 標籤管理（Tab 2）

### 標籤掃描

`scan_labels(items)` 遍歷所有同名 `.json`，回傳 `{label: [file_path, ...]}` 字典。
`shapes[].label` 與 `flags.classification` 皆納入。

### 近似重複偵測

`find_near_duplicates(labels, threshold=0.8)` 使用 `difflib.SequenceMatcher`
找出相似度 > 0.8 且 < 1.0 的標籤對，提示可能拼寫錯誤。

### 改名 / 合併 / 刪除

所有寫入均使用 `.tmp` + `os.replace()` 原子寫入。

| 操作 | 函式 | 說明 |
|------|------|------|
| 改名 | `rename_label(items, old, new)` | shapes + flags.classification 同步更新 |
| 合併 | `merge_labels(items, sources, target)` | 多個來源標籤統一改為目標標籤 |
| 刪除 | `delete_label(items, label)` | 移除 shapes；flags.classification 清為空字串 |

---

## 資料流

```
shared.json
  └─ manifest_id
        │
        ▼
017_process.execute_logic()
  ├─ get_manifest_items()     → items（file_path 列表）
  ├─ scan_labels(items)       → label_map + near_dupes
  ├─ _scan_annotations(items) → annotated / label_counts / shapes_stats
  ├─ load_classifications()   → classified_count / classification_counts
  └─ get_exports()            → export_history

使用者操作（標籤管理 tab）
  ├─ do_rename() → rename_label() → 批次 rewrite JSON
  ├─ do_merge()  → merge_labels() → rename each source
  └─ do_delete() → delete_label() → 移除 shapes / 清空 classification
```

---

## session_state 快取

| key | 說明 |
|-----|------|
| `m017_label_data` | `execute_logic` 的完整回傳值（Label Manager + Dashboard 資料）|
| `m017_show_rename_{lbl}` | 控制各標籤的改名 form 展開 |
| `m017_confirm_delete_{lbl}` | 控制各標籤的刪除確認 |

操作完成或點擊「🔄 重新掃描」後清除 `m017_label_data`，觸發下次 render 時重新掃描磁碟。
