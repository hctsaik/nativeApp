# module_017 — Label Manager（全域標籤管理）

> 最後更新：2026-05-23

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_017` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation_workflow` |
| 上游依賴 | module_010（manifest）、module_012（標注 JSON） |

掃描整個 Manifest 內所有 X-AnyLabeling JSON 的標籤（shapes[].label + flags.classification），提供全域改名、合併、刪除操作，並偵測疑似重複標籤（如 `Cat` / `cat`）。

---

## 架構

```
017_input.py   → 自動從 shared.json 取得 manifest_id，顯示 manifest 資訊
017_process.py → execute_logic() / do_rename() / do_merge() / do_delete()
017_output.py  → 標籤列表 + 個別改名/刪除 + 合併表單 + 近似重複警告
_config.py     → get_manifest_db_path() / get_shared_manifest_id()
cim_annotation/label_ops.py  → scan_labels, find_near_duplicates, rename_label, merge_labels, delete_label
```

---

## 功能

### 標籤掃描

`scan_labels(items)` 遍歷所有 annotation JSON，回傳 `{label: [file_path, ...]}` 字典。shapes[].label 與 flags.classification 皆納入統計。

### 近似重複偵測

`find_near_duplicates(labels, threshold=0.8)` 使用 `difflib.SequenceMatcher` 找出相似度 > 0.8 且 < 1.0 的標籤對，標示可能的拼寫錯誤。

### 改名 / 合併 / 刪除

所有寫入操作均使用 `tmp + os.replace` 原子寫入，避免中途失敗產生部分寫入的損毀 JSON。

| 操作 | 函式 | 說明 |
|------|------|------|
| 改名 | `rename_label(items, old, new)` | shapes[].label + flags.classification 同步更新 |
| 合併 | `merge_labels(items, sources, target)` | 多個來源標籤統一改為目標標籤 |
| 刪除 | `delete_label(items, label)` | 刪除含此標籤的所有 shapes；classification 設為空字串 |

---

## Output Page UI

1. **摘要 Metrics**：標籤種類數、涉及檔案總數
2. **近似重複警告**（展開）：列出高相似度的標籤對
3. **標籤列表**：每個標籤顯示檔案數，提供「改名」和「刪除」按鈕
4. **合併操作**：multiselect 選來源標籤，selectbox 選目標標籤
5. **重新掃描按鈕**：清除 session cache 強制重新讀取磁碟

所有操作完成後自動 rerun，結果即時反映。

---

## 資料流

```
shared.json → manifest_id → manifest.sqlite → items (file_path)
        │
        ▼
017_process.execute_logic()
  └─ scan_labels() → {label → [file_path, ...]}
  └─ find_near_duplicates() → [(a, b, ratio), ...]

使用者點擊操作
  ├─ do_rename() → rename_label() → 批次 rewrite JSON
  ├─ do_merge()  → merge_labels() → rename each source
  └─ do_delete() → delete_label() → 移除 shapes / 清空 classification
```
