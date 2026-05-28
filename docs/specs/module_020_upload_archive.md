# openSpec: module_020 — 🗂️ 我的上傳記錄 (Upload Archive)

## 目標

讓使用者查詢自己透過 Sync Back（module_013）上傳過的標注批次，
選取其中一筆按下 Download，將對應的圖片 + 標注結果重新下載到本地 ZIP。

---

## 在工作流中的定位

```
... → 🔄 Sync Back (013) → 🗂️ 我的上傳記錄 (020) → 📤 Export (014) → ...
```

- **module_019（Data Downloader，已廢棄）**：下載「Service 上公共原始資料集」
- **module_020（Upload Archive）**：找回「我自己 Sync Back 過的標注批次」

---

## 範圍

| 檔案 | 動作 |
|------|------|
| `scripts/module_020/__init__.py` | 新建（空） |
| `scripts/module_020/plugin.yaml` | 新建 |
| `scripts/module_020/_config.py` | 新建 |
| `scripts/module_020/020_input.py` | 新建 |
| `scripts/module_020/020_process.py` | 新建 |
| `scripts/module_020/020_output.py` | 新建 |
| `sidecar/python-engine/sheets/annotation.yaml` | 新增 module_020 tab（tab_order=4，Sync Back 之後） |
| `engine.py` | DB migration 新增 module_020 tab |
| `config/tools.sqlite` | 直接更新（避免重啟等待） |

不異動：module_013、module_019、module_026。

---

## API 合約

### 端點一：查詢上傳記錄

```
GET /api/v1/submissions
    ?system_name=iWISC           // 必填
    &data_type=Simulation        // 可選
    &date_from=2026-04-24        // ISO date
    &date_to=2026-05-24          // ISO date
    &nt_account=HCTSAIK          // 自動帶入，不讓使用者修改
    &page=1                      // 預設 1
    &page_size=20                // 預設 20

→ 200
{
  "total": 42,
  "page": 1,
  "page_size": 20,
  "items": [
    {
      "submit_id":   "550e8400-e29b-41d4-a716-446655440000",
      "dataset_id":  "iWISC_Simulation_20260524",
      "system_name": "iWISC",
      "data_type":   "Simulation",
      "scope":       "full",
      "item_count":  38,
      "timestamp":   "2026-05-24 10:00:00",
      "description": "第一批瑕疵標注",
      "status":      "accepted"   // "accepted" | "pending" | "failed"
    }
  ]
}

→ 4xx { "error": "..." }
```

`nt_account` 由 client 帶入 query string，Service 做 ACL 過濾（只回傳該帳號的資料）。
`status` 讓使用者知道上傳是否被後端接受，`failed` 批次不提供下載。

### 端點二：下載批次

```
GET /api/v1/submissions/{submit_id}/download
    ?nt_account=HCTSAIK          // 與查詢同帳號驗證

→ 200
    Content-Type: application/zip
    Content-Disposition: attachment; filename="{submit_id}.zip"
    <binary stream>

ZIP 結構（由 Service 端合併各 chunk）：
    images/
      img001.jpg
      img002.jpg
    annotations/
      img001.json
      img002.json
    manifest.json        // { submit_id, dataset_id, item_count, timestamp, ... }

→ 4xx { "error": "..." }
```

Client 不感知 chunk 分片，Service 負責合併成完整 ZIP。
不使用 pre-signed URL（邊緣部署環境，無 S3）。

---

## 本地下載位置

```
{CIM_LOG_DIR}/downloads/archive/{submit_id}/
    {submit_id}.zip        ← 原始下載
    images/                ← 解壓後
    annotations/
    manifest.json
```

下載完成後，`_config.write_shared_suggested_folder()` 可選寫入 shared.json，
讓使用者透過「→ 送至資料來源」按鈕自動跳回 module_026。

---

## UI 設計

### 020_input.py（查詢條件）

```
🗂️ 我的上傳記錄

Service URL:  [text_input]   (從 config 讀取)

NT Account:   [HCTSAIK]      (disabled)

系統名稱:     [selectbox]    iWISC / SMM

資料類型:     [selectbox]    全部 / Simulation / Issue / Retrain
                              （「全部」= 不帶 data_type param）

日期區間:     [date_input]   From  [今天-30天]  To  [今天]

[🔍 查詢]
```

Input `render_input()` 回傳的 params 作為查詢條件，不觸發下載。

### 020_output.py（結果 + 下載）

```
查詢結果（共 N 筆）

[Radio 選一筆]
  ○  2026-05-24 10:00  |  iWISC / Simulation  |  38 張  |  ✅ accepted  |  第一批瑕疵標注
  ○  2026-05-23 15:30  |  iWISC / Issue       |  12 張  |  ✅ accepted  |
  ○  ...

[Download 選取的批次]   （選中才 enable）

─────── 下載進度 ───────
  ⬇ 下載中... 204 KB / ?
  ✅ 下載完成 → {CIM_LOG_DIR}/downloads/archive/{submit_id}/

[→ 送至資料來源（module_026）]   （可選，下載完成後才顯示）

─────── 分頁 ───────
  << 上一頁   第 1 / 3 頁   下一頁 >>
```

---

## 020_process.py 邏輯

```python
def list_submissions(params: dict) -> dict:
    """
    打 GET /api/v1/submissions，回傳查詢結果。
    params: service_url, nt_account, system_name, data_type,
            date_from, date_to, page, page_size
    """

def download_submission(params: dict) -> dict:
    """
    打 GET /api/v1/submissions/{submit_id}/download。
    串流寫入 tmp 檔，完成後 atomic rename 到 target path，
    解壓 ZIP 到同目錄。
    params: service_url, nt_account, submit_id
    returns: { mode, zip_path, extract_dir, size_bytes, error }
    """
```

`list_submissions` 由 output 頁自行呼叫（不走 EXECUTE 流程），  
`download_submission` 由 EXECUTE 觸發（input 傳 `submit_id` 給 process）。

---

## 分頁機制

- 每頁 20 筆（可在 `_config.py` 的 `PAGE_SIZE` 調整）
- `list_submissions` 帶 `page` 參數，output 頁管理 `st.session_state["m020_page"]`
- 切頁不重新執行 EXECUTE，而是直接再呼叫 `list_submissions`

---

## 錯誤處理

| 情境 | 處理 |
|------|------|
| Service 回 4xx/5xx | 顯示錯誤訊息，提供重試按鈕 |
| 查詢結果為空 | 顯示「查無符合條件的上傳記錄」，建議調整篩選 |
| 下載 failed 批次 | Download 按鈕 disabled + tooltip「此批次上傳失敗，無法下載」|
| 下載中斷 | 刪除 tmp 檔，顯示錯誤，提供重試 |
| ZIP 解壓失敗 | 保留原始 zip，顯示警告，讓使用者自行解壓 |

---

## 測試檢核項

1. `020_process.py` 可獨立 import（無 streamlit）
2. mock HTTP，驗證 `list_submissions` 正確組裝 query string（特別是 data_type=all 時不帶參數）
3. mock binary stream，驗證 `download_submission` 正確寫入並 atomic rename
4. 驗證 ZIP 解壓後目錄結構符合預期
5. 驗證 Service 4xx 時 mode="error" 且不建立目錄
