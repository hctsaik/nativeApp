# CIM 標注平台 — 外部系統對接指南

本目錄是給外部系統開發者（AOI 機台、MES、ERP）的對接參考實作。  
所有程式碼完全獨立，不依賴 CIM 平台內部模組，可直接複製使用。

---

## 架構概覽

CIM 標注平台採用「**平台強勢主導**」架構——  
平台主動拉取資料，**外部系統不需要主動推送**，僅需實作兩支 REST API。

```
┌─────────────────────────────────────────────────────────────┐
│                     CIM 標注平台                             │
│                                                             │
│   定時 Poller ──► GET  /getAntList        ──► 取得任務列表    │
│                                                             │
│   任務建立器  ──► POST /getAntTaskDetail  ──► 取得 ZIP URL   │
│              ──► GET  <download_url>     ──► 下載影像資料    │
│                                                             │
│   完工通知    ──► 更新 antActive = 2                         │
└─────────────────────────────────────────────────────────────┘
            ▲ 平台主動呼叫                │
            │                           │ 平台完工後
┌───────────┴───────────────┐            ▼
│      外部系統              │  ┌─────────────────────────┐
│  (AOI 機台 / MES)          │  │  外部系統（下載端）       │
│                           │  │                         │
│  GET  /getAntList         │  │  GET  /api/v1/tasks     │
│  POST /getAntTaskDetail   │  │  GET  /api/v1/tasks/:id │
│  GET  /files/:task.zip    │  │       /export           │
└───────────────────────────┘  └─────────────────────────┘
```

---

## 外部系統必須實作的 API 契約

### 1. `GET /getAntList` — 回傳任務摘要列表

**Request Header：**
```
Authorization: Bearer <api_token>
```

**Response（HTTP 200，JSON Array）：**
```json
[
  {
    "antID":    "TASK_001",
    "antActive": 0,
    "antPeriod": "2026-05-26T08:00:00Z",
    "external_context": {
      "lot_id":  "L001",
      "eqp_id":  "AOI-01",
      "product": "PANEL-A"
    }
  }
]
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `antID` | string | 任務唯一識別碼（外部系統自訂） |
| `antActive` | int | 0=待標注、1=標注中、2=已完成 |
| `antPeriod` | string | 任務建立時間（ISO 8601 UTC） |
| `external_context` | object | 自定義欄位（平台原樣儲存，不解析） |

**驗證失敗：** HTTP 401

---

### 2. `POST /getAntTaskDetail` — 回傳任務 ZIP 下載連結

**Request Header：**
```
Authorization: Bearer <api_token>
Content-Type: application/json
```

**Request Body：**
```json
{ "antID": "TASK_001", "format": "coco" }
```

| 欄位 | 型別 | 說明 |
|------|------|------|
| `antID` | string | 任務 ID |
| `format` | string | 標注格式：`"coco"` 或 `"yolo"` |

**Response（HTTP 200）：**
```json
{ "download_url": "http://your-server/files/TASK_001.zip" }
```

平台收到 `download_url` 後，會以 HTTP GET 下載 ZIP 並帶上相同的 Authorization header。

---

## ZIP 目錄結構規範

### COCO 格式
```
TASK_001.zip
├── images/
│   ├── img_001.png
│   └── img_002.png
└── annotations.json     ← COCO 格式標注
```

`annotations.json` 最小必要結構：
```json
{
  "images":      [{"id": 1, "file_name": "img_001.png", "width": 1920, "height": 1080}],
  "categories":  [{"id": 1, "name": "defect"}],
  "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [x, y, w, h], "area": 100, "iscrowd": 0}]
}
```

### YOLO 格式
```
TASK_001.zip
├── images/
│   ├── img_001.png
│   └── img_002.png
├── labels/
│   └── img_001.txt      ← 每行: class_id cx cy w h（0~1 正規化座標）
└── classes.txt          ← 每行一個類別名稱
```

---

## 快速啟動（Mock Server）

```bash
# 1. 安裝相依套件
pip install -r requirements.txt

# 2. 啟動模擬伺服器（Port 9000）
uvicorn mock_server:app --port 9000 --reload

# 3. 測試 API（另開終端機）
curl -H "Authorization: Bearer test-token-123" http://localhost:9000/getAntList

# 4. 查詢任務詳情
curl -X POST http://localhost:9000/getAntTaskDetail \
  -H "Authorization: Bearer test-token-123" \
  -H "Content-Type: application/json" \
  -d '{"antID": "TASK_001", "format": "coco"}'

# 5. 下載 ZIP
curl -H "Authorization: Bearer test-token-123" \
  http://localhost:9000/files/TASK_001.zip -o TASK_001.zip
```

---

## 示範腳本使用方式

### payload_builder.py — 打包 ZIP 給平台
```bash
# 執行示範，自動在 sample_data/zips/ 產生三個示範 ZIP
python payload_builder.py
```

也可在程式中呼叫：
```python
from payload_builder import build_coco_zip, build_yolo_zip
from pathlib import Path

build_coco_zip(
    images_dir=Path("my_images/"),
    coco_json=my_coco_dict,
    output_path=Path("output/TASK_001.zip"),
)
```

### downloader_client.py — 下載平台完工結果
```bash
# 示範完整下載流程（平台 API 不可用時自動 fallback 至 mock_server）
python downloader_client.py
```

---

## API Token 說明

**Phase 0（當前）：**
- Token 由 CIM 平台管理員核發，格式為任意字串
- 每個 tenant（租戶）一組 Token
- 設定於外部系統的啟動設定中
- Mock Server 的測試 Token：`test-token-123`

**安全建議：**
- Token 不應寫死在程式碼中，建議從環境變數或設定檔讀取
- 正式環境應使用 HTTPS 傳輸

---

## 目錄結構

```
external-system-reference/
├── README.md               ← 本文件
├── requirements.txt        ← 相依套件（fastapi, uvicorn, httpx, pillow）
├── mock_server.py          ← 外部系統 Mock Server（FastAPI）
├── payload_builder.py      ← ZIP 打包工具
├── downloader_client.py    ← 平台結果下載客戶端
└── sample_data/
    ├── ant_list.json       ← /getAntList 回應範例
    ├── task_detail.json    ← /getAntTaskDetail 回應範例
    └── zips/               ← 執行 payload_builder.py 後產生的示範 ZIP
```
