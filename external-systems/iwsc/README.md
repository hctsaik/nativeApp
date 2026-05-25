# iWISC 外部 AOI 系統模擬服務

這個服務模擬 iWISC AOI 外部系統，供 CIM Hybrid Edge Platform 整合測試使用。
服務使用 FastAPI + SQLite，**獨立運行**，不依賴 CIM platform 任何程式碼。

---

## 快速啟動

### 1. 安裝相依套件

```bash
pip install -r requirements.txt
```

### 2. 啟動服務（port 8765）

```bash
uvicorn main:app --port 8765 --reload
```

服務啟動後會自動：
- 建立 SQLite 資料庫 `iwsc.db`
- 寫入 5 筆種子 AOI 任務（若 DB 為空）

### 3. Swagger UI

開啟瀏覽器前往：

```
http://localhost:8765/docs
```

---

## API 端點總覽

| 方法 | 路徑 | 說明 |
|------|------|------|
| `GET` | `/tasks` | 回傳所有待標注任務（`ant_active=0`） |
| `POST` | `/tasks/{ant_id}/result` | 接收平台回傳的標注結果，並將任務標記為已完成 |
| `GET` | `/tasks/{ant_id}/result` | 查詢該任務已收到的標注結果（debug 用） |
| `GET` | `/admin/tasks` | 回傳所有任務（含所有狀態，debug 用） |
| `GET` | `/health` | 健康檢查 |

### `ant_active` 狀態說明

| 值 | 意義 |
|----|------|
| `0` | 待標注（平台可拉取） |
| `1` | 已派送（保留欄位，目前未使用） |
| `2` | 已完成（平台已回傳結果） |

---

## 種子資料

服務啟動時，若資料庫為空，會自動寫入以下 5 筆任務：

| ant_id | lot_id | eqp_id | recipe | ant_period |
|--------|--------|--------|--------|------------|
| IWSC-2026-001 | L001 | AOI-A3 | DRAM_256G | 2026-05-26 |
| IWSC-2026-002 | L002 | AOI-B1 | NAND_512G | 2026-05-27 |
| IWSC-2026-003 | L003 | AOI-A3 | DRAM_256G | 2026-05-28 |
| IWSC-2026-004 | L004 | AOI-B1 | NAND_512G | 2026-05-29 |
| IWSC-2026-005 | L005 | AOI-A3 | DRAM_256G | 2026-05-30 |

---

## 資料庫結構

資料庫檔案：`./iwsc.db`（與執行目錄同層）

### `iwsc_tasks`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `ant_id` | TEXT PK | 任務唯一識別碼 |
| `ant_period` | TEXT | 任務時間（UTC ISO8601） |
| `external_context` | TEXT | JSON 字串，含 lot_id / eqp_id / recipe |
| `ant_active` | INTEGER | 0=待標注 / 1=已派送 / 2=已完成 |
| `created_at` | TEXT | 建立時間（UTC ISO8601） |
| `updated_at` | TEXT | 最後更新時間（UTC ISO8601） |

### `iwsc_results`

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | INTEGER PK | 自動遞增 |
| `ant_id` | TEXT | 對應的任務 ID |
| `platform_task_id` | TEXT | CIM 平台的 task UUID |
| `annotation_json` | TEXT | 標注結果（JSON 字串） |
| `new_classification` | TEXT | 最終分類（如 OK / NG） |
| `annotated_by` | TEXT | 標注者 |
| `received_at` | TEXT | 接收時間（UTC ISO8601） |

---

## 重置資料庫

若需重新初始化（清空所有資料並重新種入種子）：

```bash
# 刪除資料庫檔案後重新啟動服務即可
rm iwsc.db
uvicorn main:app --port 8765 --reload
```
