# openSpec: module_013 — 🔄 Sync Back to Service

## 目標

將 module_013 從「整理圖片複製」重新定義為「**將標注結果同步回遠端 Service**」。
使用者在 module_012（標注）或 module_016（AI 預標注）完成後，於此頁選擇訓練格式、按送出，
即可將所有圖片的標注資料（bbox + 分類）批次推送至 Service，並附帶所選訓練格式的壓縮檔。

---

## 範圍

| 檔案 | 動作 |
|------|------|
| `scripts/module_013/_config.py` | 全新改寫 |
| `scripts/module_013/013_input.py` | 全新改寫 |
| `scripts/module_013/013_process.py` | 全新改寫 |
| `scripts/module_013/013_output.py` | 全新改寫 |
| `scripts/module_017/017_output.py` | 新增最後一次同步記錄區塊 |

不異動：`014_process.py`（只引用其 export 函式）、`_manifest_db.py`、`engine.py`。

---

## API 合約

### 端點一：逐筆推送標注

```
POST /api/v1/datasets/{dataset_id}/submissions
Content-Type: application/json

{
  "submit_id":     "550e8400-e29b-41d4-a716-446655440000",  // client-gen UUID，冪等鍵
  "scope":         "full" | "partial",                      // full = 全部圖片，partial = 僅已標注
  "chunk_index":   0,                                       // 0-based
  "total_chunks":  3,
  "items": [
    {
      "item_id":         "abc123",
      "file_name":       "img001.jpg",
      "classification":  "cat" | "",
      "shapes": [
        {
          "label":      "cat",
          "shape_type": "rectangle" | "polygon",
          "x1": 10.0, "y1": 20.0, "x2": 110.0, "y2": 120.0,
          "polygon_pts": []   // polygon 時填入 [[x,y],...]
        }
      ]
    }
  ]
}

→ 200 { "submit_id": "...", "received_items": 100 }
→ 4xx { "error": "..." }
```

Service 以 `(dataset_id, submit_id, item_id)` 做 upsert，天然冪等。

### 端點二：上傳訓練格式包

```
POST /api/v1/datasets/{dataset_id}/submissions/{submit_id}/exports
Content-Type: multipart/form-data

  format=coco_json                 // "coco_json" | "yolo_txt" | "none"
  file=<binary .zip>               // 記憶體中產生，不落地

→ 200 { "export_id": "...", "format": "coco_json", "size_bytes": 204800 }
→ 4xx { "error": "..." }
```

若使用者選「不上傳格式包」，跳過此端點。

---

## 資料組裝 Pipeline

```
manifest_id
    │
    ├─ _manifest_db.get_manifest_items()     → items list
    ├─ _config.load_classifications()        → {item_id: label}
    └─ 逐 item 讀 X-AnyLabeling JSON        → shapes_map
           （同 014_process._load_xany_annotation / _parse_shapes）

→ scope 計算
    full:    所有 items
    partial: 只有 shapes 非空 OR classification 非空的 items

→ 切 chunk（每 100 筆）→ 呼叫端點一

→ 格式產生（reuse 014_process 函式，寫入 BytesIO zip）
→ 呼叫端點二
```

---

## 格式產生策略

使用 `io.BytesIO` + `zipfile.ZipFile` 在記憶體中組裝，**不落地任何檔案**。

```python
import io, zipfile

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    # coco_json: 直接 json.dumps → zf.writestr("train.json", ...)
    # yolo_txt:  同上，labels/train/stem.txt + classes.txt + data.yaml
buf.seek(0)
# 作為 multipart file 上傳
```

**split_groups 固定為 `{"all": all_ids}`**，不做 train/val/test 拆分
（Service 端自行決定如何使用）。

---

## 本地狀態 & 歷史

### 同步狀態（每 manifest 一份）

路徑：`{CIM_LOG_DIR}/config/m013_sync_state_{manifest_key}.json`

```json
{
  "manifest_id": "...",
  "items": {
    "abc123": { "status": "ok",      "submit_id": "uuid-A", "synced_at": "2026-05-23T10:00:00" },
    "def456": { "status": "failed",  "submit_id": "uuid-A", "error": "timeout" },
    "ghi789": { "status": "pending", "submit_id": null }
  }
}
```

### 同步歷史（append-only JSONL）

路徑：`{CIM_LOG_DIR}/config/m013_sync_history_{manifest_key}.jsonl`

每次送出成功/失敗各 append 一行：

```jsonl
{"submit_id":"uuid-A","dataset_id":"ds-1","scope":"full","scope_count":120,"ok_count":118,"failed_count":2,"formats":["coco_json"],"started_at":"2026-05-23T10:00:00","finished_at":"2026-05-23T10:00:45","status":"partial_fail"}
```

`status` 值：`"ok"` | `"partial_fail"` | `"fail"`

---

## Validation 規則

| 嚴重度 | 規則 | 阻擋送出？ |
|--------|------|-----------|
| error  | bbox 面積 ≤ 0 | **是** |
| error  | shapes 中有空 label | **是** |
| warning | classification 存在但無 shapes（純分類項） | 否，顯示提醒 |
| warning | 超過 30% 項目完全無標注（shapes=[] AND classification=""） | 否，顯示提醒 |
| info   | scope=partial 但 partial_count = 0 | 禁止送出並提示 |

---

## UI 設計

### 013_input.py

```
🔄 Sync Back — 同步標注結果至 Service

[當前 Manifest 資訊 banner]

Service URL: [text_input]  （從 config 讀取，可覆蓋後自動存回）

資料集 ID:   [text_input]  （從 shared.json 讀取 dataset_id，可覆蓋）

送出範圍:
  ◉ 全部圖片（full）
  ○ 僅已標注（partial）

訓練格式：
  ◉ COCO JSON
  ○ YOLO TXT
  ○ 不上傳格式包

[驗證摘要 expander]
  ✅ N 張可送出
  ⚠️  M 張有警告
  ❌ K 張有錯誤（阻擋送出）

[執行] 按鈕
```

### 013_output.py

```
[送出進度] — 區塊一：整體狀態 bar
  已傳 X / N 筆（Chunk Y / Z）

[每 chunk 狀態列表]
  chunk 0: ✅ 100 筆 ok
  chunk 1: ⚠️  98 ok / 2 failed
  ...

[格式包上傳狀態]
  coco_json: ✅ 204 KB 已上傳

[歷史記錄 expander]
  最近 10 筆（從 JSONL 讀取）
  submit_id | 時間 | scope | ok/total | 格式 | 狀態
```

---

## module_017 整合

`017_output.py` 在 Export History 下方新增「**最後同步**」區塊：

```
最後同步到 Service
  時間：2026-05-23 10:00
  scope：full  100/120 筆成功  格式：coco_json
  [展開歷史]
```

讀取 `m013_sync_history_{manifest_key}.jsonl` 最後一行。

---

## 錯誤處理策略

- **chunk 送出失敗（HTTP 4xx/5xx or timeout）**：記錄到 sync_state，繼續送下一 chunk
- **全部 chunk 失敗**：output 顯示錯誤 banner；不寫歷史
- **格式包上傳失敗**：獨立記錄，不影響 per-item 狀態；output 顯示警告
- **部分 chunk 失敗**：歷史 status = `"partial_fail"`；output 提供「重試失敗項」按鈕

---

## 測試檢核項

1. `013_process.py` 可獨立 import（無 streamlit）
2. mock HTTP 端點，驗證 chunk 切割邏輯（101 筆 → 2 chunks）
3. 驗證 scope=partial 時僅包含有標注 / 分類的 items
4. 驗證格式 zip 記憶體產生後 `zipfile.ZipFile` 可正確讀取
5. 驗證 validation error（invalid_bbox）時 `execute_logic` 回傳 `mode="validation_error"`
