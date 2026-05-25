# CIM 平台外部系統整合規格

> **對象**：CIM 平台開發者。此文件為內部規格，定義平台與外部系統之間的完整介面契約，
> 供開發 downloader_client、實作真實外部系統對接，或進行 API 設計審查時參考。

---

## 1. 文件目的

本文件定義 CIM 平台（Hybrid Edge Platform）與外部系統（External System，又稱 Sponsor 系統）
之間的完整介面規格，涵蓋三個面向：

1. **平台側 API**：CIM 平台對外 expose 的 REST endpoints（供 downloader_client 或外部系統呼叫）
2. **外部系統側 API**：外部系統必須實作的 REST endpoints（供平台主動呼叫）
3. **ZIP 資料格式**：外部系統回傳的標注資料壓縮包格式規範

整合架構為「**Platform-Dictated**」模式——平台主動呼叫外部系統 API，
外部系統只需實作兩支固定 endpoint，無需理解平台內部邏輯。

---

## 2. 術語定義

| 術語 | 說明 |
|------|------|
| **antID** | 外部系統賦予標注任務的唯一識別碼（字串）。平台直接透傳，不自行產生。 |
| **antActive** | 任務狀態碼（整數）。0=Pending、1=Processing、2=Completed。詳見第 6 節。 |
| **AntTask** | 外部系統回傳的任務摘要物件（antID + antActive + antPeriod + 外部自訂欄位）。 |
| **SystemTenant** | 已向平台註冊的外部系統設定物件（tenant_id、system_name、server_host_name、target_format、api_token）。一個外部系統對應一個 Tenant。 |
| **CIM Sponsor** | 外部系統的操作者（Sponsor 角色）。負責查詢已完成標注結果並下載 ZIP。 |
| **Annotator** | 執行標注工作的使用者（Annotator 角色）。負責認領任務、使用標注工具、送出審核。 |

### 狀態機

```
0 (Pending)  →  1 (Processing)  →  2 (Completed)
```

- 流向為單向，**不可回退**。
- `0 → 1`：Annotator 執行 `claim_task`（認領）時由平台自動設定。
- `1 → 2`：Annotator 執行 `complete_task`（完成）時由平台自動設定。

---

## 3. 平台側 API（供外部系統 downloader_client 呼叫）

> **注意**：以下 API 為 **Phase 3 規劃中的對外端點，尚未實作**。
> `annotation/services.py` 已有對應的業務邏輯（`list_tasks`、`export_result_zip`），
> 但尚未在 FastAPI engine 中掛載對應 router。
> 現行 `engine.py` 僅 expose 內部 MCP 工具用途的 endpoints。

### 3.1 查詢已完成任務

```
GET /api/v1/tenants/{tenant_id}/tasks?ant_active=2
```

**Request**

| 欄位 | 說明 |
|------|------|
| Header: `Authorization: Bearer {api_token}` | Sponsor 持有的 API Token |
| Path: `tenant_id` | 外部系統的 Tenant UUID |
| Query: `ant_active` | 篩選狀態（建議值：2，即 Completed） |

**Response 200**

```json
[
  {
    "task_id": "uuid-of-task",
    "tenant_id": "uuid-of-tenant",
    "ant_id": "ANT-001",
    "ant_active": 2,
    "annotated_by": "user@example.com",
    "created_at": "2025-01-01T00:00:00Z",
    "updated_at": "2025-01-02T00:00:00Z"
  }
]
```

**Response 錯誤碼**

| 狀態碼 | 說明 |
|--------|------|
| 401 | api_token 無效或缺失 |
| 404 | tenant_id 不存在 |

---

### 3.2 下載標注結果 ZIP

```
GET /api/v1/tasks/{task_id}/export?mode=orig_img_new_ant
```

**Request**

| 欄位 | 說明 |
|------|------|
| Header: `Authorization: Bearer {api_token}` | Sponsor 持有的 API Token |
| Path: `task_id` | 平台內部 Task UUID（從 3.1 取得） |
| Query: `mode` | `orig_img_orig_ant`（原始標注）或 `orig_img_new_ant`（最新標注） |

**Response 200**

```
Content-Type: application/zip
Content-Disposition: attachment; filename="task_{task_id}.zip"

（ZIP binary，格式見第 5 節）
```

**Response 錯誤碼**

| 狀態碼 | 說明 |
|--------|------|
| 400 | 不支援的 mode |
| 401 | api_token 無效或缺失 |
| 404 | task_id 不存在 |

---

## 4. 外部系統側 API（外部系統必須實作）

外部系統必須自行實作以下兩支 endpoint。平台的 `RestConnector` 會主動呼叫這些 API。
詳細範例程式見 `sidecar/python-engine/external-system-reference/`。

### 4.1 GET /getAntList

列出外部系統中的所有標注任務。

**Request**

```
GET {server_host_name}/getAntList
Authorization: Bearer {api_token}
```

**Response 200**

```json
[
  {
    "antID": "ANT-001",
    "antActive": 2,
    "antPeriod": "2025-01-01T00:00:00Z",
    "lot_id": "LOT-A",
    "eqp_id": "EQP-01"
  },
  {
    "antID": "ANT-002",
    "antActive": 0,
    "antPeriod": null
  }
]
```

**欄位規格**

| 欄位 | 型別 | 必填 | 說明 |
|------|------|------|------|
| `antID` | string | 是 | 任務唯一識別碼，平台直接透傳 |
| `antActive` | integer | 是 | 狀態碼：0=Pending、1=Processing、2=Completed |
| `antPeriod` | string \| null | 否 | 任務期間（ISO 8601 datetime，可為 null） |
| 其他欄位 | any | 否 | 外部系統自訂欄位，平台透傳至 `external_context`，不解析 |

**錯誤碼**

| 狀態碼 | 平台行為 |
|--------|---------|
| 200 | 解析 JSON 陣列 |
| 401 | 拋出 `PermissionError`，中止流程 |
| 其他 | 拋出 `RuntimeError`（含 status code） |

---

### 4.2 POST /getAntTaskDetail

取得指定任務的標注資料下載連結。

**Request**

```
POST {server_host_name}/getAntTaskDetail
Authorization: Bearer {api_token}
Content-Type: application/json

{
  "antID": "ANT-001",
  "format": "coco"
}
```

**欄位規格**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `antID` | string | 要查詢的任務 ID |
| `format` | string | 平台期望的標注格式（`coco`、`yolo-detection`、`labelme`） |

**Response 200**

```json
{
  "download_url": "https://storage.example.com/ant-001-coco.zip"
}
```

**欄位規格**

| 欄位 | 型別 | 說明 |
|------|------|------|
| `download_url` | string | ZIP 下載 URL（http/https 或 file://），平台背景下載後解壓入庫 |

**ZIP 下載端點規格**

- 外部系統可提供任意 URL，平台用 `urllib.request.urlopen` 下載，支援 http/https/file scheme
- ZIP 內容格式詳見第 5 節
- 建議 URL 有效期至少 10 分鐘（考慮網路延遲）

**錯誤碼**

| 狀態碼 | 平台行為 |
|--------|---------|
| 200 | 解析 `download_url` 並下載 ZIP |
| 401 | 拋出 `PermissionError` |
| 其他 | 拋出 `RuntimeError`（含 status code） |

---

## 5. ZIP 資料格式規範

外部系統回傳的 ZIP 包含原始影像與標注資料。平台解壓後入庫，結構如下：

```
task-payload.zip
├── images/
│   ├── image_001.jpg
│   ├── image_002.png
│   └── ...
└── （標注檔，依 format 而異，見下方）
```

### 5.1 COCO 格式（`target_format: "coco"`）

標注檔：`annotations.json`

```json
{
  "images": [
    {
      "id": 1,
      "file_name": "image_001.jpg",
      "width": 1920,
      "height": 1080
    }
  ],
  "categories": [
    {
      "id": 1,
      "name": "defect",
      "supercategory": "object"
    }
  ],
  "annotations": [
    {
      "id": 1,
      "image_id": 1,
      "category_id": 1,
      "bbox": [100, 200, 50, 80],
      "area": 4000,
      "iscrowd": 0,
      "segmentation": []
    }
  ]
}
```

**欄位說明**

| 陣列 | 必要欄位 | 說明 |
|------|---------|------|
| `images` | `id`、`file_name`、`width`、`height` | `file_name` 須與 `images/` 目錄中的檔名對應 |
| `categories` | `id`、`name` | `supercategory` 為選填 |
| `annotations` | `id`、`image_id`、`category_id`、`bbox` | `bbox` 格式為 `[x, y, width, height]`（左上角座標，像素值） |

---

### 5.2 YOLO 格式（`target_format: "yolo-detection"`）

```
task-payload.zip
├── images/
│   └── image_001.jpg
├── labels/
│   └── image_001.txt
└── classes.txt
```

**`labels/*.txt`**（每行一個 bounding box）

```
0 0.512 0.481 0.104 0.148
1 0.230 0.370 0.060 0.090
```

格式：`{class_id} {cx} {cy} {w} {h}`

- 所有座標均為 0~1 正規化值（相對於影像寬高）
- `cx`、`cy` 為 bounding box 中心點
- `w`、`h` 為 bounding box 寬高

**`classes.txt`**（每行一個類別名稱，行號對應 class_id）

```
defect
scratch
contamination
```

---

### 5.3 LabelMe 格式（`target_format: "labelme"`）

每張影像對應一個同名 JSON 檔，與影像放在同一層目錄：

```
task-payload.zip
├── images/
│   ├── image_001.jpg
│   └── image_001.json
```

**`image_001.json`**

```json
{
  "version": "5.3.1",
  "flags": {},
  "shapes": [
    {
      "label": "defect",
      "points": [[100, 200], [150, 200], [150, 280], [100, 280]],
      "group_id": null,
      "shape_type": "polygon",
      "flags": {}
    }
  ],
  "imagePath": "image_001.jpg",
  "imageData": null,
  "imageHeight": 1080,
  "imageWidth": 1920
}
```

**欄位說明**

| 欄位 | 說明 |
|------|------|
| `shapes` | 標注形狀陣列，`shape_type` 可為 `polygon`、`rectangle`、`circle` |
| `points` | 多邊形頂點列表（像素座標），rectangle 只有左上、右下兩點 |
| `imagePath` | 對應影像的相對路徑 |
| `imageData` | 建議設為 `null`（不嵌入 base64 圖像，節省空間） |

---

## 6. antActive 狀態機說明

### 流程圖

```
外部系統
  ├─ 建立任務，antActive = 0 (Pending)
  │
平台（Annotator 操作）
  ├─ claim_task → antActive = 1 (Processing)
  │   Platform 從外部系統下載 ZIP，解壓入庫，建立 AnnotationTask 記錄
  │
  ├─ （Annotator 使用標注工具編輯標注）
  │
  └─ complete_task → antActive = 2 (Completed)
      Platform 更新 AnnotationTask.ant_active = 2

外部系統 downloader_client（Phase 3）
  └─ 輪詢 GET /api/v1/tenants/{id}/tasks?ant_active=2
      └─ 下載 GET /api/v1/tasks/{id}/export?mode=orig_img_new_ant
```

### 各狀態轉換觸發條件

| 轉換 | 觸發者 | 觸發條件 | API |
|------|--------|---------|-----|
| 建立（外部系統自行管理） | 外部系統 | 有新任務需標注時 | 外部系統自行維護 |
| 0 → 1 | Annotator（透過平台 MCP）| `claim_task` 成功下載並入庫 | `annotation_claim_task` |
| 1 → 2 | Annotator（透過平台 MCP）| 標注完成，`complete_task` 被呼叫 | `annotation_complete_task` |

**重要限制**：

- 狀態轉換**單向不可逆**，平台不提供回退機制。
- 同一個 `antID` 只能被 claim 一次（平台在 `claim_task` 內做防重複認領檢查）。
- 外部系統的 `antActive` 欄位僅供平台讀取，平台不會回寫外部系統的狀態。

---

## 7. 認證機制

### api_token 格式與傳遞方式

- 格式：不限制，建議使用隨機產生的 UUID v4 或 Base64 編碼字串（最少 32 bytes）
- 傳遞方式：HTTP Header `Authorization: Bearer {api_token}`
- 適用範圍：平台側 API（第 3 節）與外部系統側 API（第 4 節）均使用相同傳遞方式

### Token 核發流程（Phase 0）

1. 外部系統管理者向 CIM 平台管理員申請 Tenant 帳號
2. 平台管理員執行 `register_tenant`，系統產生 `tenant_id` 與 `api_token`
3. 外部系統管理者將 `api_token` 設定至外部系統的設定檔（供 `/getAntList` 驗證用）
4. 平台管理員將相同的 `api_token` 記錄在 `SystemTenant.api_token`（供 `RestConnector` 呼叫外部 API 時帶入 header）

> 目前 Phase 0 尚無 Token Rotation 機制；Token 一旦設定即長期有效，直到人工更換。

### 安全建議

- `api_token` 不應出現在 URL query string 或 log 中，應僅在 header 傳遞
- 外部系統的 `/getAntList` 與 `/getAntTaskDetail` 應驗證 token，回傳 401 表示驗證失敗
- 生產環境應使用 HTTPS，防止 token 在傳輸過程中被截取
- 建議外部系統的 download_url 加入時效性簽名（如 pre-signed URL），避免連結被濫用

---

## 8. 已知限制與後續工作

### 目前已實作

- `RestConnector`（`annotation/integrations/connectors/rest_connector.py`）：完整實作，使用 httpx，支援 GET /getAntList、POST /getAntTaskDetail、health_check
- `FakeConnector`（`annotation/integrations/connectors/fake_connector.py`）：測試用，不發起網路請求
- `AnnotationService._get_connector`：已更新，非 `fake://` scheme 一律使用 RestConnector

### 尚未實作 / 待補功能

| 項目 | 說明 | 優先級 |
|------|------|--------|
| 平台側 export API router | `services.py` 已有 `list_tasks` + `export_result_zip`，但 FastAPI engine 尚未掛載對應 router（`/api/v1/tenants/...`） | Phase 3 |
| downloader_client | 外部系統側的下載客戶端（目前為 placeholder），應輪詢平台 API 並下載 ZIP | Phase 3 |
| RBAC（角色分離） | Sponsor vs Annotator 角色分離尚未實作；目前 api_token 沒有角色區分 | Phase 4 |
| Token Rotation | api_token 無法過期或輪換，需補上 Token 管理機制 | Phase 4 |
| 非同步 ZIP 下載 | 目前 `claim_task` 同步下載 ZIP，大型任務可能 timeout；應改為背景下載 + 輪詢 job status | Phase 4 |
| 外部系統 antActive 回寫 | 平台目前不通知外部系統任務狀態變更；外部系統只能透過 antID 對應自行推斷 | 待討論 |
