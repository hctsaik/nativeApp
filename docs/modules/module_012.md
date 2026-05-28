# module_012 — Annotation Session（標注作業管理）

> 最後更新：2026-05-19

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_012` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation`（與 module_026、module_013 組合） |
| 上游依賴 | module_026（資料來源）寫入 `shared.json` |
| 下游 | module_013（Update）讀同一 manifest 與分類 config |

從資料來源（module_026）建立的 DatasetManifest 開啟標注工作階段，逐張以 X-AnyLabeling 標注，並支援圖片快速分類。

---

## 架構

```
012_input.py   → 讀 shared.json 取 manifest_id，設定 annotation_labels / classification_labels
012_process.py → (passthrough) 彙整 manifest items，偵測現有標注
012_output.py  → 雙欄 UI：左欄圖片列表 + 右欄 Detail Panel（標注 + 分類）
_config.py     → 設定持久化 + manifest-scoped 分類/labels 檔
```

---

## 設定（`_config.py`）

### 設定檔路徑

```
{CIM_LOG_DIR}/config/module_012.json
```

```json
{
  "annotation_tool": "x-anylabeling",
  "annotation_labels": [],
  "classification_labels": ["A", "B"],
  "autorefresh_enabled": true,
  "autorefresh_seconds": 10,
  "last_manifest_id": "ad44a6e7..."
}
```

### Manifest 解析順序

`get_shared_manifest_id()` **只讀 `shared.json`**（由資料來源（module_026）寫入），不讀 `module_012.json` 自身的 `last_manifest_id`。這確保每次都對齊最新一次資料來源（module_026）執行的資料集。

```
{CIM_LOG_DIR}/config/shared.json
  → last_manifest_id  ← 資料來源（module_026）每次執行後更新
```

### Manifest-scoped 檔案

每個 manifest 有獨立的 config/state 檔，確保不同 session 的分類資料互不干擾：

```
{CIM_LOG_DIR}/config/module_012_classes_{manifest_id[:12]}.txt
{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json
{CIM_LOG_DIR}/xanylabeling_state/module_012_{manifest_id[:12]}/
```

---

## Input Page（`012_input.py`）

Input Page 是「開始標注前確認」頁，不是完整設定中心。主路徑只要求使用者確認資料集與標注類別，其他選項收進可選/進階區塊。

- **目前資料集**：自動從 `shared.json` 取 `last_manifest_id`，顯示 `目前資料集：<name>｜<N> 張圖片`；若資料集不正確，回資料來源（module_026）重新選取。
- **標注類別（annotation_labels）**：主要欄位，每行一個標注框類別；預設空白，避免 demo 類別被誤用。空白行會忽略，畫面會顯示將建立的類別數。
- **圖片快速分類（classification_labels）**：可選 expander，用於標注列表頁替整張圖片分類，不會寫入標注框 JSON。
- **進階設定**：包含 `X-AnyLabeling` / `LabelMe` 標注工具選擇，以及自動重新掃描標注 JSON 的設定。
- **自動重新掃描**：預設開啟，每 `10` 秒，範圍 `5-300` 秒。

回傳 result：

```python
{
    "manifest_id": str,
    "annotation_tool": str,       # x-anylabeling | labelme
    "labels": list[str],           # annotation_labels
    "classification_labels": list[str],
    "autorefresh_enabled": bool,
    "autorefresh_seconds": int,
}
```

---

## Output Page（`012_output.py`）

### 佈局

```
左欄（圖片列表）                   右欄（Detail Panel）
─────────────────────────────     ─────────────────────────────
[縮圖] [標注縮圖] 檔名             檔名 + 路徑（合併一列）
       ✅ 已標注  N 個 shape        🔆 對比 toggle
       🏷 分類標籤                  ─────────────────────────────
 [選取]  [🖊 標注工具]              [1] A / [2] B 分類 selectbox
                                   ─────────────────────────────
                                   圖片（或原圖 + 標注疊合）
                                   標注明細 expander
```

### 標注偵測

```python
# 查影像同目錄的同名 .json（X-AnyLabeling 預設輸出路徑）
ann_path = Path(img_path).with_suffix(".json")
```

只使用影像同目錄同名 JSON。

### 分類功能

- **Selectbox**：`on_change` callback 即時呼叫 `_save_clf()` 寫入磁碟，選完自動跳到下一張未分類
- **鍵盤快捷鍵**（Ghost Button 模式）：
  - `↑` / `K`：上一張
  - `↓` / `J`：下一張
  - `A`：開啟標注工具（X-AnyLabeling）
  - `C`：切換強化對比
  - `1`–`9`：依序選分類
- **Ghost Button**：以 Streamlit `st.button()` 渲染但用 JS `MutationObserver` 隱形化（`position:fixed; opacity:0; width:1px`），鍵盤快捷鍵用 `element.click()` 觸發

### 分類持久化

```python
def _save_clf(manifest_id: str, item_id: str, label: str, cache: dict) -> None:
    if not manifest_id:
        return
    cache[item_id] = label
    _cfg.save_classifications(manifest_id, cache)
```

分類檔存於 `{CIM_LOG_DIR}/config/module_012_classifications_{manifest_id[:12]}.json`，結構：

```json
{
  "77cb8b61d0344f58a15b5adc8d490e57": "A",
  "2c8c2a99b1e342f79fa4f2c5ad2e91e9": "B"
}
```

key 為 `item_id`（manifest DB 的 UUID），不是檔名。

### 標注縮圖（`_make_ann_thumb`）

```python
@st.cache_data(show_spinner=False, max_entries=500)
def _make_ann_thumb(file_path: str, ann_path: str) -> bytes | None:
    ...
```

在圖片列表中顯示標注後的縮圖（120×90，綠框 `#16a34a`）。

### 標注工具啟動

Output 頁的「🖊 標注工具」依 Input 頁的 `annotation_tool` 設定啟動：

- `x-anylabeling`：使用 repo-local `.venv-xanylabeling`，透過 WDAC-trusted Python 啟動 `anylabeling.app.main`
- `labelme`：優先使用 `LABELME_EXE`，其次偵測 sibling `LabelMe_Dino/.venv/Scripts/labelme.exe`，最後 fallback 到 PATH 的 `labelme`

兩者都輸出到**影像所在目錄同名 JSON**。

#### X-AnyLabeling security/runtime contract

請不要在未重新驗證前改動以下契約：

- 已驗證 X-AnyLabeling runtime：`x-anylabeling-cvhub[cpu]` `4.0.0-beta.7`
- 已驗證 Python：`3.11.9`
- `.venv-xanylabeling\Scripts\xanylabeling.exe` 只用來定位 venv，不直接執行
- 實際啟動需走 `py -3.11 -c "import sys; sys.path.insert(...); from anylabeling.app import main; main()"`
- 必須保留 `--nodata --autosave --no-auto-update-check`
- 若 classes file 存在，必須保留 `--labels <classes.txt> --validatelabel exact`

這些限制是為了避免 Windows WDAC 封鎖 uv trampoline、避免 GUI 啟動時連外更新檢查，並確保 labels 不會被輸入成非預期類別。回歸測試在 `012_output_test.py`。

### 強化圖批次標注 + sync 回原圖

當原圖對比/飽和度偏低、肉眼難以標注時，可在「⚙️ 強化圖批次標注（可選）」展開區產生強化圖後，以資料夾模式開啟 X-AnyLabeling 對強化圖標注，完成的 JSON 會自動同步回原圖目錄。

| 階段 | Helper | 說明 |
|------|--------|------|
| 產生 | `_generate_enhanced_batch()` | 對每張原圖套用對比 ×2.2、飽和度 ×1.8 寫入 `{CIM_LOG_DIR}/m012_enhanced/{manifest_id[:12]}/`（與原圖完全隔離）。既有且 mtime 較新者跳過 |
| 進度 | `_enhanced_progress()` | 回傳 `(已產生數, 總數)`，顯示於展開區標題「已產生 N/M」 |
| 同步 | `_sync_enhanced_annotations()` | 把強化圖目錄的 `.json` 回寫到原圖同名 JSON，並將 `imagePath` 改寫成原圖檔名；以 mtime 保證 `orig >= enh` → 冪等，不重複回寫 |

`render_output` 在每次 render（含 autorefresh）只要偵測到強化圖目錄存在 `.json` 就會跑一次 sync，因此使用者在 X-AnyLabeling 標完即自動回填，無需手動觸發。

完整 round-trip（產生 → 模擬標注 → sync → 冪等 → skip）回歸測試在 `012_output_test.py`（`test_generate_enhanced_batch_*` / `test_sync_enhanced_annotations_*` / `test_enhanced_progress_*`）。

### 自動更新

由 Input 頁設定：

- `autorefresh_enabled`
- `autorefresh_seconds`（5–300 秒）

Output 依設定呼叫 `st_autorefresh(interval=autorefresh_seconds * 1000)`。

---

## 指標說明（Output 頁頭）

| 指標 | 說明 |
|------|------|
| 總圖數 | Manifest 圖片總數 |
| ✅ 已標注 | `Path(fp).with_suffix(".json")` 存在的圖片數 |
| ⏳ 待標注 | 未標注圖片數 |
| 🏷 已分類 | `classifications.json` 中有記錄的圖片數（只有設定分類類別時顯示） |
| 完成率 | 已標注 / 總圖數 |

---

## 常見問題

### 分類後到 Update 看不到結果

原因：資料來源（module_026）重新執行會建立新的 `manifest_id`，因此分類 config key 不同。確認 Annotation 和 Update 都顯示同一個 manifest 名稱（info bar）。

### X-AnyLabeling 標注後沒更新

依 Input 頁設定的間隔等待自動更新，或在 Output 頁按「重新掃描標注」。
