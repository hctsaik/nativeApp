# module_010 — Data Feeder（資料集來源建立）

> ⚠️ **此模組已廢棄**（deprecated_at: 2026-05-29）
> 功能已整合至 [module_026（資料來源）](module_026.md) 的「本地資料夾」模式。

> 最後更新：2026-05-19

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_010` |
| Runner | `cv_framework` |
| Sheet | （廢棄，原 `sheet-annotation`）（與 module_012、module_013 組合） |
| 下游 | module_012 讀取 `shared.json` 的 `last_manifest_id` |

Data Feeder 負責把圖片來源整理成 DatasetManifest。後續 Annotation Session 和 Update 都以這份 manifest 作為同一批資料的基準。

---

## 架構

```
010_input.py   → 選擇來源：folder / db / api
010_process.py → 掃描或查詢圖片，建立 manifest 與 items
010_output.py  → 顯示建立結果與前 20 筆預覽
_config.py     → 設定持久化、manifest DB 路徑、shared.json 寫入
```

---

## 支援來源

| source_type | 說明 |
|-------------|------|
| `folder` | 掃描資料夾圖片，可設定遞迴與副檔名 |
| `db` | 執行 SQLite SQL，結果需含 `file_path` 欄位 |
| `api` | 呼叫 HTTP API，從 dot-path 取出圖片 URL/path 清單 |

每個 item 會寫入：

```json
{
  "item_id": "uuid",
  "file_path": "C:/data/image001.jpg",
  "width": 1920,
  "height": 1080,
  "file_hash": "md5-prefix",
  "metadata": {}
}
```

---

## shared.json

建立 manifest 成功後，`010_process.py` 會呼叫 `_config.write_shared_manifest_id()`：

```json
{
  "last_manifest_id": "ad44a6e7..."
}
```

路徑：

```
{CIM_LOG_DIR}/config/shared.json
```

module_012 和 module_013 只讀這個檔案取得目前資料集，避免使用者在每一頁重選 manifest。

---

## Manifest DB

路徑：

```
{CIM_LOG_DIR}/db/manifest.sqlite
```

主要資料表：

| table | 用途 |
|-------|------|
| `dataset_manifests` | manifest 基本資料、來源設定、item_count |
| `manifest_items` | 每張圖片的路徑、尺寸、hash、metadata |
| `annotation_results` | 預留給標注結果寫入 |
| `annotation_exports` | 預留給匯出紀錄 |

---

## 與標注流程的關係

```
module_010
  ├─ 建立 manifest.sqlite
  └─ 寫入 shared.json:last_manifest_id
        │
        ├─ module_012 讀取圖片清單、準備 X-AnyLabeling labels/config
        └─ module_013 讀取同一批圖片、整理標注與分類結果
```
