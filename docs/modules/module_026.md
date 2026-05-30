# module_026 — 資料來源

> 最後更新：2026-05-29

## 概覽

| 欄位 | 值 |
|------|-----|
| ID | `module_026` |
| Slug | `data-source` |
| Runner | `cv_framework` |
| Sheet | `sheet-annotation`（🐜 影像標註 Tab 1） |
| Domain | `annotation` |
| 狀態 | ✅ 啟用 |
| 上游依賴 | 無（此為 sheet 的第一個 tab） |
| 下游 | module_012（讀 shared.json 取 manifest_id） |

統一資料來源入口，支援**本地資料夾**與**外部任務系統（iWISC）**兩種模式，
建立 DatasetManifest 並寫入 `shared.json`，供後續標注 tab 使用。

---

## 架構

```
026_input.py    → 模式切換 UI（本地資料夾 / 外部任務系統）+ 任務清單瀏覽
026_process.py  → 建立 DatasetManifest、認領 iWISC 任務、寫入 shared.json
026_output.py   → 顯示 manifest 建立結果（圖片數、預覽清單）
_config.py      → 設定持久化（module_026.json）+ shared.json 讀寫 + 路徑管理
```

---

## 兩種模式

### 📁 本地資料夾

1. 使用者填入（或透過「📂 瀏覽」按鈕選取）本地圖片資料夾路徑
2. 可選「遞迴掃描子資料夾」與允許的圖片副檔名（預設 `.jpg/.jpeg/.png/.bmp/.webp/.tiff`）
3. 按「執行」後，`026_process.py` 呼叫 `module_010` 的 `scan_folder()`，掃描所有符合副檔名的圖片，建立 DatasetManifest

### 🔌 外部任務系統（iWISC）

1. 使用者選擇已在管理中心登錄的 SystemTenant（外部系統連線）
2. 填入「使用者 ID（工號）」後點「查看任務清單」，從外部系統拉取公海任務（ant_active = 0 或 1）
3. 從清單中點「✋ 選取」（待認領）或「🔄 繼續」（已認領），按「執行」後：
   - 呼叫 `AnnotationService.claim_task()`：認領任務（ant_active 0→1）、下載任務 ZIP、解壓影像至 workspace
   - 儲存 `original_annotation_json`（不可覆蓋的原始快照）
   - 建立 DatasetManifest，指向解壓後的影像目錄

> iWISC 是外部任務系統的其中一種實作，透過
> `annotation/integrations/connectors/rest_connector.py` 實作
> `cim_platform/ExternalSystemConnector` ABC。
> 只要實作相同 ABC，任何 AOI/MES 系統都可以接入。

---

## 設定（`_config.py`）

### 設定檔路徑

```
{CIM_LOG_DIR}/config/module_026.json
```

```json
{
  "last_mode": "local",
  "last_folder_path": "",
  "recursive_scan": true,
  "image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"],
  "service_url": ""
}
```

### shared.json 寫出欄位

| 欄位 | 類型 | 說明 |
|------|------|------|
| `last_manifest_id` | str | 新建立的 manifest UUID（hex） |
| `source_type` | str | `"local"` 或 `"iwsc"` |
| `iwsc_tenant_id` | str | （iWISC 模式）Tenant UUID |
| `iwsc_task_id` | str | （iWISC 模式）annotation-core Task UUID |
| `iwsc_ant_id` | str | （iWISC 模式）外部任務系統的 ant_id |
| `pending_reload` | bool | 固定寫 `false` |

---

## Input Page（`026_input.py`）

- **模式選擇**：以 `st.radio` horizontal 切換「📁 本地資料夾」/ 「🔌 外部任務系統」
- **本地模式**：路徑輸入 + 📂 瀏覽按鈕（tkinter filedialog subprocess）、遞迴選項、副檔名 multiselect
- **外部任務系統模式**：
  - Tenant 下拉選單（從 `AnnotationService.list_tenants()` 取得）
  - 使用者 ID 輸入
  - 「🔄 查看任務清單」按鈕（呼叫 `AnnotationService.get_ant_list()`）
  - 任務清單分頁顯示（PAGE_SIZE = 50），每筆顯示任務 ID、狀態圖示、外部 context
  - 「✋ 選取」/ 「🔄 繼續」按鈕選取目標任務
  - 已選取任務以 `st.success` 確認，按「執行」觸發 process

回傳 params 範例（本地模式）：

```python
{
    "mode": "local",
    "folder_path": "C:/images/lot_001",
    "recursive": True,
    "extensions": [".jpg", ".png"],
    "manifest_name": "lot_001",
}
```

回傳 params 範例（iWISC 模式）：

```python
{
    "mode": "iwsc",
    "tenant_id": "xxxxxxxx-...",
    "user_id": "user001",
    "ant_id": "ANT-2026-001",
}
```

---

## Process（`026_process.py`）

### 主流程

```
execute_logic(params)
  ├─ mode == "local"  → _run_local()
  │     └─ scan_folder() → _save_manifest() → write_shared()
  ├─ mode == "iwsc"   → _run_iwsc()
  │     └─ AnnotationService.claim_task() → scan_folder() → _save_manifest() → write_shared()
  └─ mode == "remote" → _run_remote()（保留相容，實際不在 UI 中暴露）
```

### DatasetManifest 建立

`_save_manifest()` 呼叫 `scripts/shared/_manifest_db.py`，在
`{CIM_LOG_DIR}/db/manifest.sqlite` 建立 manifest 記錄並批次插入 items。

### iWISC 任務認領

```python
service = AnnotationService(AnnotationWorkspace(ws_path))
task = service.claim_task(tenant_id, ant_id, user_id)
# → 認領（ant_active 0→1）+ 下載 ZIP + 解壓影像 + 儲存 original_annotation_json
images_dir = service.workspace.task_images_dir(task["task_id"])
```

---

## Output Page（`026_output.py`）

- 顯示 manifest 名稱、manifest_id（前 12 碼）
- 圖片總數 + 前 20 筆預覽清單（檔名、尺寸）
- iWISC 模式額外顯示：task_id、ant_id、已認領狀態
- 統一引導訊息：「✅ 已建立資料集，請切換至下一個 Tab 開始標注。」

---

## 資料流

```
使用者選擇來源
        │
        ▼
026_process.execute_logic()
  ├─ 本地模式：scan_folder() → DatasetManifest（manifest.sqlite）
  └─ iWISC 模式：claim_task() → 下載解壓 → DatasetManifest（manifest.sqlite）
        │
        ▼
shared.json（{CIM_LOG_DIR}/config/）
  ├─ last_manifest_id  ← module_012/018/014 讀取
  ├─ source_type
  ├─ iwsc_tenant_id（iWISC 模式）
  └─ iwsc_task_id（iWISC 模式）
        │
        ▼
module_012（標注工作台） → module_018（審查） → module_014（匯出/回傳）
```

---

## 相關檔案

| 類型 | 路徑 |
|------|------|
| Input UI | `sidecar/python-engine/scripts/module_026/026_input.py` |
| Process | `sidecar/python-engine/scripts/module_026/026_process.py` |
| Output UI | `sidecar/python-engine/scripts/module_026/026_output.py` |
| 設定 | `sidecar/python-engine/scripts/module_026/_config.py` |
| Plugin YAML | `sidecar/python-engine/scripts/module_026/plugin.yaml` |
| Sheet 配置 | `sidecar/python-engine/sheets/annotation.yaml` |
| Annotation Service | `sidecar/python-engine/annotation/services.py` |
| RestConnector | `sidecar/python-engine/annotation/integrations/connectors/rest_connector.py` |
| Manifest DB | `sidecar/python-engine/scripts/shared/_manifest_db.py` |

---

## 整合廢棄模組對照

| 廢棄模組 | 整合至 module_026 的哪個模式 |
|---------|--------------------------|
| `module_010` Data Feeder | 本地資料夾模式（`scan_folder()` 直接複用 010_process 邏輯） |
| `module_019` Data Downloader | （remote 模式，目前在 UI 中不暴露，邏輯保留作相容） |
| `module_023` 待認領任務 | 外部任務系統模式（iWISC 任務清單瀏覽與認領） |

---

## 常見問題

### 查看任務清單按下後顯示「無法載入 Tenant 清單」

原因：尚無已在管理中心登錄的 SystemTenant。前往「管理中心 → 標註權限管理」新增外部系統後再試。

### 按「執行」後顯示「認領失敗」

可能原因：
1. 使用者 ID 沒有權限認領此任務（任務有使用者限制）
2. 外部系統回傳 HTTP 4xx/5xx
3. 任務已被其他人認領（ant_active 已非 0）

### 本地資料夾按「執行」後圖片數為 0

確認：
1. 路徑存在且包含圖片
2. 圖片副檔名在允許清單中（預設不含 `.gif`、`.heic` 等）
3. 若圖片在子資料夾，確認「遞迴掃描」已勾選
