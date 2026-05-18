# OpenSpec: Dataset Pipeline Modules

版本: 1.0.0
日期: 2026-05-16
狀態: 已實作

---

## 1. 概覽

本規格定義 CIM 標注平台的資料管道模組架構，實現從資料來源到標注結果匯出的完整工作流。所有模組共用 `DatasetManifest` 作為資料傳遞的標準格式，透過 SQLite 資料庫持久化儲存，確保跨模組的資料一致性。

---

## 2. 系統架構

### 資料流

```
[Module 010: Data Feeder] ──DatasetManifest──▶ [Module 006: 標注] ──結果──▶ [Module 011: Result Sink]
                                  ↑
                        [Pipeline Sheet: 工作流編排]
```

### 模組清單

| 模組 | 名稱 | 職責 |
|------|------|------|
| Module 010 | Data Feeder | 從資料夾/DB/API 建立標準化圖片清單（DatasetManifest） |
| Module 006 | 動物影像標注專案 | 接受可選 Manifest，建立 X-AnyLabeling 標注專案 |
| Module 011 | Result Sink | 接收標注結果，分割資料集並匯出多種格式 |
| Pipeline Sheet | 工作流編排 | 線性步驟 UI，串聯上述各模組 |
| `shared/_manifest_db.py` | Manifest DB 存取層 | 統一的 SQLite CRUD 介面，供各模組共用 |

---

## 3. DatasetManifest 規格

### 3.1 資料庫位置

```
{CIM_LOG_DIR}/db/manifest.sqlite
```

`CIM_LOG_DIR` 預設值：`{PROJECT_ROOT}/tmp/cim_log`

### 3.2 Schema

#### 表 1：`manifests`（Manifest 主表）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `manifest_id` | TEXT PK | UUID hex 字串 |
| `name` | TEXT | 使用者自訂名稱 |
| `source_type` | TEXT | `folder` / `db` / `api` |
| `source_config` | TEXT | JSON 字串，來源設定 |
| `schema_version` | TEXT | 固定 `"1.0"` |
| `item_count` | INTEGER | 圖片筆數（快取值） |
| `status` | TEXT | `ready` / `processing` / `error` |
| `created_at` | TEXT | ISO 8601 時間戳 |
| `updated_at` | TEXT | ISO 8601 時間戳 |

#### 表 2：`manifest_items`（Manifest 圖片項目）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `item_id` | TEXT PK | UUID hex 字串 |
| `manifest_id` | TEXT FK | 對應 manifests.manifest_id |
| `file_path` | TEXT | 圖片絕對路徑 |
| `width` | INTEGER | 圖片寬度（像素），可為 NULL |
| `height` | INTEGER | 圖片高度（像素），可為 NULL |
| `file_hash` | TEXT | MD5 前 16 位，用於去重 |
| `metadata` | TEXT | JSON 字串，擴充欄位 |
| `created_at` | TEXT | ISO 8601 時間戳 |

#### 表 3：`pipeline_runs`（Pipeline 執行記錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `run_id` | TEXT PK | UUID hex 字串 |
| `manifest_id` | TEXT FK | 對應 manifests.manifest_id |
| `pipeline_name` | TEXT | Pipeline 顯示名稱 |
| `status` | TEXT | `running` / `done` / `failed` |
| `export_paths` | TEXT | JSON 字串，各格式匯出路徑 |
| `created_at` | TEXT | ISO 8601 時間戳 |
| `finished_at` | TEXT | ISO 8601 時間戳，可為 NULL |

#### 表 4：`export_records`（匯出記錄）

| 欄位 | 型別 | 說明 |
|------|------|------|
| `export_id` | TEXT PK | UUID hex 字串 |
| `run_id` | TEXT FK | 對應 pipeline_runs.run_id |
| `format` | TEXT | `coco` / `yolo-detection` / `csv` |
| `export_path` | TEXT | 匯出目錄絕對路徑 |
| `item_count` | INTEGER | 匯出圖片數量 |
| `created_at` | TEXT | ISO 8601 時間戳 |

### 3.3 DatasetManifest 物件格式

```json
{
  "manifest_id": "a1b2c3d4e5f6...",
  "name": "我的資料集",
  "source_type": "folder",
  "source_config": {
    "folder_path": "/path/to/images",
    "recursive": true,
    "extensions": [".jpg", ".jpeg", ".png", ".bmp"]
  },
  "schema_version": "1.0",
  "item_count": 120,
  "status": "ready",
  "created_at": "2026-05-16 10:00:00",
  "updated_at": "2026-05-16 10:00:05"
}
```

### 3.4 ManifestItem 物件格式

```json
{
  "item_id": "f1e2d3c4b5a6...",
  "manifest_id": "a1b2c3d4e5f6...",
  "file_path": "/absolute/path/to/image.jpg",
  "width": 1920,
  "height": 1080,
  "file_hash": "5d41402abc4b",
  "metadata": {},
  "created_at": "2026-05-16 10:00:01"
}
```

---

## 4. 模組介面

### 4.1 Module 010: Data Feeder

**檔案位置：** `scripts/module_010/010_process.py`

#### `execute_logic(params: dict) -> dict`

**輸入 params：**

```json
{
  "source_type": "folder",
  "folder_path": "/path/to/images",
  "manifest_name": "我的資料集",
  "recursive": true,
  "extensions": [".jpg", ".jpeg", ".png"]
}
```

**回傳（成功）：**

```json
{
  "ok": true,
  "manifest_id": "a1b2c3d4...",
  "manifest_name": "我的資料集",
  "item_count": 120,
  "elapsed_ms": 234.5
}
```

**回傳（失敗）：**

```json
{
  "ok": false,
  "error": "folder_not_found | no_images_found | db_error",
  "message": "人類可讀的錯誤說明"
}
```

**支援的 source_type：**

| 值 | 說明 | 必要欄位 |
|----|------|---------|
| `folder` | 掃描本機資料夾 | `folder_path` |
| `db` | 從 SQLite 讀取圖片路徑 | `db_path`, `table`, `path_column` |
| `api` | 從 REST API 拉取清單 | `api_url`, `auth_token`（選填） |

---

### 4.2 Module 011: Result Sink

**檔案位置：** `scripts/module_011/011_process.py`

#### `execute_logic(params: dict) -> dict`

**輸入 params：**

```json
{
  "manifest_id": "a1b2c3d4...",
  "run_id": "f9e8d7c6...",
  "export_formats": ["coco", "yolo-detection", "csv"],
  "export_dir": "/path/to/output",
  "split": {
    "train": 0.70,
    "val": 0.15,
    "test": 0.15
  }
}
```

**回傳（成功）：**

```json
{
  "ok": true,
  "run_id": "f9e8d7c6...",
  "export_paths": {
    "coco": "/path/to/output/coco",
    "yolo-detection": "/path/to/output/yolo_detection",
    "csv": "/path/to/output/csv"
  },
  "split_counts": {
    "train": 84,
    "val": 18,
    "test": 18
  },
  "elapsed_ms": 1823.4
}
```

**回傳（失敗）：**

```json
{
  "ok": false,
  "error": "manifest_not_found | no_annotations | export_failed",
  "message": "人類可讀的錯誤說明"
}
```

**支援的匯出格式：**

| 格式 | 說明 | 輸出結構 |
|------|------|---------|
| `coco` | COCO JSON 格式 | `{export_dir}/coco/{train,val,test}/` |
| `yolo-detection` | YOLO txt 格式 | `{export_dir}/yolo_detection/{train,val,test}/` |
| `csv` | 純 CSV 標注表格 | `{export_dir}/csv/annotations.csv` |

---

## 5. Module 006 整合

Module 006 接受可選的 `manifest_id` 參數，優先使用 Manifest 中的圖片清單取代預設的 SQLite animals.db 查詢。

### 5.1 params 擴充欄位

`render_input()` 的回傳 dict 加入：

```json
{
  "manifest_id": "a1b2c3d4... 或 null"
}
```

`execute_logic(params)` 前處理後，params 會新增：

```json
{
  "_using_manifest": true,
  "_manifest_name": "我的資料集",
  "_manifest_items": [
    { "item_id": "...", "file_path": "/path/to/image.jpg", ... }
  ]
}
```

### 5.2 Phase 1 整合建議

Phase 1（`_execute_phase1`）可透過以下模式使用 Manifest 圖片清單：

```python
manifest_items = params.get("_manifest_items")
if manifest_items:
    image_paths = [item["file_path"] for item in manifest_items
                   if Path(item["file_path"]).exists()]
else:
    # 原有邏輯：從 animals.db 查詢
    rows = _query_images(db_path, category)
    image_paths = [str(image_dir / r["filename"]) for r in rows ...]
```

> 注意：目前 Phase 1 核心邏輯未修改，Manifest 整合僅預先注入 `params["_manifest_items"]`，待後續版本按需採用。

---

## 6. Pipeline Sheet

**檔案位置：** `scripts/sheets/pipeline_sheet.py`

Pipeline Sheet 是獨立的 Streamlit 頁面，不提供 `execute_logic` 介面，直接以 `st.set_page_config` 為入口。

### 6.1 線性步驟

| 步驟 | 名稱 | 動作 |
|------|------|------|
| Step 1 | 資料來源 | 選擇現有 Manifest 或掃描資料夾建立新 Manifest |
| Step 2 | 標注 | 引導使用者切換至 Module 006 進行標注 |
| Step 3 | 匯出 | 設定格式/分割比例，呼叫 Module 011 匯出 |

### 6.2 Session State 鍵值

| Key | 型別 | 說明 |
|-----|------|------|
| `pl_step` | int | 當前步驟（1/2/3） |
| `pl_manifest_id` | str\|None | 選取的 Manifest ID |
| `pl_manifest_name` | str | Manifest 顯示名稱 |
| `pl_manifest_item_count` | int | Manifest 圖片數 |
| `pl_run_id` | str\|None | 本次執行 UUID |
| `pl_name` | str | Pipeline 使用者自訂名稱 |
| `pl_history` | list | 本 Session 執行歷史記錄 |

### 6.3 動態模組載入

Pipeline Sheet 以 `importlib` 動態載入 `010_process` 與 `011_process`，模組不存在時優雅降級顯示錯誤訊息，不崩潰。

---

## 7. MVP vs Phase 2

| 功能 | MVP（已實作） | Phase 2（計畫中） |
|------|:---:|:---:|
| 資料夾來源（Module 010） | ✅ | |
| DB 來源（Module 010） | ✅ | |
| API 來源（Module 010） | ✅ | |
| Module 006 Manifest 整合（UI） | ✅ | |
| Module 006 Phase 1 Manifest 圖片替換 | | ✅ |
| COCO JSON 匯出 | ✅ | |
| YOLO txt 匯出 | ✅ | |
| CSV 匯出 | ✅ | |
| Pipeline Sheet 線性流程 | ✅ | |
| 執行歷史記錄 | ✅ | |
| 雲端儲存（S3/GCS） | | ✅ |
| DAG 非線性執行引擎 | | ✅ |
| 多人協作與審核流程 | | ✅ |
| Webhook/通知 | | ✅ |

---

## 8. 決策記錄（ADR）

### ADR-001: SQLite 作為主儲存層

**決策：** 使用 `{CIM_LOG_DIR}/db/manifest.sqlite` 作為 Manifest 的主要儲存。

**原因：**
- 桌面 Electron 應用無法依賴外部資料庫服務
- SQLite WAL 模式可處理多 Python worker 的讀寫競爭
- 檔案型儲存易於備份、遷移與除錯
- 無需額外安裝依賴

**取捨：** 不支援多機分散式部署，Phase 2 如需雲端共用需另行評估。

---

### ADR-002: 線性 Pipeline 優先

**決策：** Pipeline Sheet MVP 只實作線性三步驟（資料來源 → 標注 → 匯出），不做 DAG。

**原因：**
- PM 決定 MVP 降低複雜度，加快交付
- 90% 使用案例為單一批次線性流程
- DAG 引擎需要額外的任務排程基礎設施

**取捨：** 無法平行執行多個標注任務，Phase 2 再引入 Celery 或 Ray。

---

### ADR-003: Module 006 最小侵入性整合

**決策：** Module 006 的 Manifest 整合僅在 `execute_logic` 前處理注入 `_manifest_items`，不修改 Phase 1 核心邏輯。

**原因：**
- 保持 Module 006 現有功能完整不受影響
- Manifest 功能為「選填」，不應成為必要依賴
- `shared/_manifest_db.py` 尚未安裝時應優雅降級

**取捨：** Phase 1 目前仍使用 animals.db 查詢，`_manifest_items` 尚未真正替換圖片清單，待 Module 010 穩定後補完。

---

### ADR-004: importlib 動態載入跨模組依賴

**決策：** Pipeline Sheet 與 Module 006 均以 `importlib.util` 動態載入跨模組依賴（`_manifest_db`、`010_process`、`011_process`），不使用靜態 import。

**原因：**
- 各模組目錄不在標準 Python path 中
- 避免循環依賴與安裝複雜度
- 模組未安裝時可優雅降級，不影響其他功能

---

*本文件由 CIM 開發團隊維護。如有變更，請同步更新版本號與日期。*
