# module_012 — Annotation Session（標注作業管理）

> 最後更新：2026-05-19

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_012` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation_workflow`（與 module_010、module_013 組合） |
| 上游依賴 | module_010（Data Feeder）寫入 `shared.json` |
| 下游 | module_013（Update）讀同一 workspace |

從 Data Feeder 建立的 DatasetManifest 開啟標注工作階段，逐張以 X-AnyLabeling 標注，並支援圖片快速分類。

---

## 架構

```
012_input.py   → 讀 shared.json 取 manifest_id，設定 annotation_labels / classification_labels
012_process.py → (passthrough) 彙整 manifest items，偵測現有標注
012_output.py  → 雙欄 UI：左欄圖片列表 + 右欄 Detail Panel（標注 + 分類）
_config.py     → 設定持久化 + workspace 路徑管理
```

---

## 設定（`_config.py`）

### 設定檔路徑

```
{CIM_LOG_DIR}/config/module_012.json
```

```json
{
  "annotation_labels": ["物件A", "物件B", "物件C"],
  "classification_labels": ["A", "B"],
  "last_manifest_id": "ad44a6e7..."
}
```

### Manifest 解析順序

`get_shared_manifest_id()` **只讀 `shared.json`**（由 Data Feeder 寫入），不讀 `module_012.json` 自身的 `last_manifest_id`。這確保每次都對齊最新一次 Data Feeder 執行的資料集。

```
{CIM_LOG_DIR}/config/shared.json
  → last_manifest_id  ← Data Feeder 每次執行後更新
```

### Workspace 路徑

每個 manifest 有獨立的 workspace，確保不同 session 的分類資料互不干擾：

```
{CIM_LOG_DIR}/annotation_workspaces/module_012_{manifest_id[:12]}/
  classes.txt           ← X-AnyLabeling 類別清單
  classifications.json  ← 分類結果 {item_id: label}
  .xanylabeling/        ← X-AnyLabeling 工作目錄
```

---

## Input Page（`012_input.py`）

- **不顯示 Manifest 選擇器**：自動從 `shared.json` 取 `last_manifest_id`，以 info bar 顯示（`📦 bull 16 張 ｜ 若要切換請回 Data Feeder 重新執行`）
- **標注類別（annotation_labels）**：每行一個，存入 `module_012.json` 與 `classes.txt`
- **分類類別（classification_labels）**：可選。Output 頁面的快速分類下拉選項，與 X-AnyLabeling 標注框無關

回傳 result：

```python
{
    "manifest_id": str,
    "labels": list[str],           # annotation_labels
    "classification_labels": list[str],
    "workspace_dir": str,
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

不使用 `workspace/annotations/` 舊路徑。

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
def _save_clf(workspace_dir: str, item_id: str, label: str, cache: dict) -> None:
    if not workspace_dir:   # guard: 避免寫到 CWD
        return
    cache[item_id] = label
    _cfg.save_classifications(workspace_dir, cache)
```

`classifications.json` 結構：

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

### X-AnyLabeling 啟動

```python
# 繞過 Windows WDAC 對 .exe 的封鎖
python_exe = Path(xany_exe).parent / "python.exe"
if python_exe.exists():
    cmd = [str(python_exe), "-c", "from anylabeling.app import main; main()", *xany_args]
else:
    cmd = [xany_exe, *xany_args]
```

X-AnyLabeling 輸出到**影像所在目錄**（`--output str(out_dir)`），不輸出到 workspace。

### 自動更新

`st_autorefresh(interval=30_000)` 固定 30 秒更新（偵測新標注）。

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

原因：Data Feeder 重新執行會建立新的 `manifest_id`，導致 workspace 不同。確認 Annotation 和 Update 都顯示同一個 manifest 名稱（info bar）。

### X-AnyLabeling 標注後沒更新

等 30 秒自動更新，或重新執行 Input 頁的 `▶ 執行`。
