# module_013 — Update（標注與分類結果回寫）

> 最後更新：2026-05-21

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_013` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation`（與 module_026、module_012 組合） |
| 上游依賴 | module_012（Annotation Session）的 manifest-scoped 分類 config |

將 module_012 的標注與分類結果整理成摘要 JSON，並支援：
- **B 操作**：偵測並確認影像同目錄的標注 JSON（X-AnyLabeling 輸出）
- **C 操作**：依分類標籤將圖片複製到整理輸出目錄的子資料夾

---

## 架構

```
013_input.py   → 讀 shared.json 取 manifest_id，設定 export_dir 和操作選項
013_process.py → 掃描標注 + 分類資料，建立 items 清單，執行 B/C 操作
013_output.py  → 預覽表格 + 確認執行按鈕
_config.py     → 設定持久化 + 分類 config / export 路徑管理
```

---

## 設定（`_config.py`）

### Manifest 解析

與 module_012 完全一致，**只讀 `shared.json`**：

```python
def get_shared_manifest_id() -> str:
    p = _CIM_LOG_DIR / "config" / "shared.json"
    return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
```

### 分類檔路徑

讀取 module_012 依 manifest 寫出的分類 config：

```
{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json
```

---

## Input Page（`013_input.py`）

- **不顯示 Manifest 選擇器**：自動從 `shared.json` 取，以 info bar 顯示
- **整理輸出目錄**：預設 `{CIM_LOG_DIR}/exports/module_013_{manifest_id[:12]}/`，可自訂
- **執行選項**：
  - **依分類整理圖片並帶走標注 JSON**（checkbox）：有分類標籤的圖片與同名 `.json` 複製到 `{export_dir}/{分類名稱}/`

回傳 result：

```python
{
    "manifest_id": str,
    "export_dir": str,
    "organize_images": bool,    # C
    "dry_run": bool,            # True = 預覽不執行
}
```

---

## Process（`013_process.py`）

### 標注偵測（B 操作）

```python
# X-AnyLabeling 將標注存在影像同目錄同名 .json
ann_src_path = Path(fp).with_suffix(".json") if fp else None
ann_src = str(ann_src_path) if (ann_src_path and ann_src_path.exists()) else ""
```

**只使用影像同目錄同名 JSON**。`b_action` 的值：

| 值 | 說明 |
|----|------|
| `copy` | 有標注 + 有 file_path（目標 = 影像同目錄） |
| `skip` | 有標注但 file_path 為空 |
| `n/a` | 無標注 |

> 注意：B 操作目前為「確認」性質（標注已在原始目錄），實際不做複製。dst = `Path(fp).parent / f"{stem}.json"` = src，因此 b_copied 計數為執行確認的圖片數。

### 分類讀取（C 操作）

```python
classifications_path = _cfg.get_classification_path(manifest_id)
classifications = json.loads(classifications_path.read_text(encoding="utf-8"))
classification = classifications.get(item_id, "") or classifications.get(filename, "")
```

`c_action` 的值：

| 值 | 說明 |
|----|------|
| `copy` | 有分類 + 有 export_dir |
| `skip` | 有分類但 export_dir 為空 |
| `n/a` | 無分類 |

C 操作目標路徑：`{export_dir}/{label}/{filename}`

### 輸出 JSON

執行後（`dry_run=False`）將摘要寫入**原始圖片資料夾**：

```
{source_folder}/update_result_{timestamp}.json
```

（若 source_folder 為空，fallback 到 `{CIM_LOG_DIR}/exports/module_013_{manifest_id[:12]}/`）

---

## Output Page（`013_output.py`）

### 預覽頁佈局（`mode == "preview"`）

1. **Metrics 摘要**：待複製圖片 / 分類數 / 含標注（直接呈現本次操作規模）
2. **路徑資訊**：原始資料夾 / 輸出目錄
3. **確認摘要 + 確認按鈕**（在詳細清單之前，一眼可見）
4. **詳細清單**（`st.expander`，預設收合）

### 詳細清單欄位

| 欄位 | 說明 |
|------|------|
| filename | 圖片檔名 |
| classification | 分類標籤（從 config 讀） |
| has_annotation | True / False |
| shape_count | 標注框數量 |
| c_action | copy / skip / n/a |
| organized_dst | C 目標路徑 |
| ann_export_dst | 標注 JSON 目標路徑 |

### 確認按鈕

預覽模式（`dry_run=True`）→ 摘要警告 + `✅ 確認執行 Update` → 觸發 `dry_run=False` 重新執行。
無分類圖片時按鈕 disabled，顯示說明提示。

---

## 資料流

```
shared.json
  └─ last_manifest_id ──────────────────────────────┐
                                                     ▼
manifest DB (.sqlite)                    module_012 classification config
  └─ items (file_path, item_id, ...)       └─ module_012_classifications_*.json
        │                                        │
        ▼                                        ▼
013_process.execute_logic()
  ├─ B: Path(fp).with_suffix(".json")  ← 影像同目錄標注
  ├─ C: {export_dir}/{label}/{filename}  ← 分類整理
  └─ output: {source_folder}/update_result_{ts}.json
```

---

## 常見問題

### 分類欄位全部空白

`shared.json` 的 manifest_id 對應的分類 config 沒有資料。可能原因：
1. module_026（資料來源）又執行了一次建立新 manifest → 新 manifest 尚無分類
2. module_012 未執行（尚未建立分類）

確認 Annotation 和 Update 的 info bar 顯示同一個 manifest 名稱。

### B 操作全部 n/a

圖片目錄下沒有同名 `.json` 檔案。需先在 Annotation 頁面用 X-AnyLabeling 完成標注並儲存。
