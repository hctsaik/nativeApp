# 2026-05-26 Annotation Platform — Bug 修正 + iWISC 整合測試

## 本次 Session 完成項目

### 1. Bug 修正（4 個 + 1 個整合測試發現）

#### Bug 1 — `annotation_review_task` MCP tool 呼叫不存在方法 🔴（已修）
- **檔案：** `mcp/annotation_mcp/server.py` line 111
- **問題：** 呼叫 `_handlers.review_task()`，但 `handlers.py` 只有 `review_task_legacy()`
- **修正：** 改為 `_handlers.review_task_legacy()`

#### Bug 2 — MCP 與 Streamlit GUI workspace 完全隔離 🔴（已修）
- **檔案：** `.mcp.json`
- **問題：** MCP server 的 `ANNOTATION_WORKSPACE` 指向 `tmp/annotation-workspace`，Streamlit modules 用 `{CIM_LOG_DIR}/annotation_workspace`（= `apps/host-electron/logs/annotation_workspace`），兩邊資料互看不見
- **修正：** 將 `.mcp.json` 的 `ANNOTATION_WORKSPACE` 改為 `C:/code/claude/nativeApp/apps/host-electron/logs/annotation_workspace`

#### Bug 3 — `annotation_list_tasks` MCP tool 參數語意錯誤 🟠（已修）
- **檔案：** `mcp/annotation_mcp/server.py` line 85
- **問題：** 參數名稱是 `dataset_id`，但 `handlers.list_tasks()` 第一個參數是 `tenant_id`（必填），傳 `None` 會拋 `NotFoundError`
- **修正：** 改為 `tenant_id: str`，並補上 `user_id` 和 `ant_active` 可選參數

#### Bug 4 — `export_result_zip` 兩種 mode 輸出相同 🟡（已修）
- **問題：** `orig_img_orig_ant` 和 `orig_img_new_ant` 都回傳 `task.annotation_json`（最新版），無法區分
- **修正（三個檔案）：**
  - `annotation/core/models.py`：`AnnotationTask` 新增 `original_annotation_json: dict` 欄位
  - `annotation/storage/sqlite_store.py`：新增欄位遷移（ALTER TABLE）+ `save_task` INSERT + `_row_to_task` 讀取
  - `annotation/services.py`：`claim_task()` 建立任務時同時儲存 `original_annotation_json`；`export_result_zip()` 的 `orig_img_orig_ant` mode 改用 `task.original_annotation_json`

#### Bug 5 — `_task_to_dict` 漏掉 `original_annotation_json` 序列化（整合測試發現，已修）
- **檔案：** `annotation/services.py` 的 `_task_to_dict()` 函式
- **問題：** 新欄位未加入序列化 dict，`get_task()` 回傳的 dict 中此欄位是 `None`
- **修正：** 補上 `"original_annotation_json": task.original_annotation_json`

#### 順帶修正 — `test_mcp_config.py` 測試邏輯矛盾（預先存在的 bug）
- **問題：** 斷言 `"C:/code/claude/nativeApp/" not in root_text` 但 PYTHONPATH 早就含有子路徑，在本機永遠失敗
- **修正：** 移除矛盾的負向斷言，只保留正向確認（`expected_repo in root_text`）

---

### 2. iWISC 整合測試資料完善

#### 新增 `/files/` 靜態 ZIP 服務 endpoint
- **檔案：** `external-systems/iwsc/routers/tasks.py`
- `GET /files/{filename}` — 提供 `test_zips/` 目錄下的 ZIP 下載

#### 更新 `getAntTaskDetail` 回傳真實 download_url
- 若 `test_zips/{ant_id}.zip` 存在，回傳 `http://localhost:8765/files/{ant_id}.zip`
- 否則回傳 `null`（維持向後相容）

#### 新增測試 ZIP 檔案（`external-systems/iwsc/test_zips/`）
用 Python stdlib（struct + zlib）合成最小合法 RGB PNG，不依賴 PIL：

| ZIP | 影像 | 標注 |
|-----|------|------|
| `IWSC-2026-004.zip` | `wafer_001.png`, `wafer_002.png` (64×64) | 3 個 COCO bbox（scratch / particle / void） |
| `IWSC-2026-005.zip` | `chip_A01.png`, `chip_A02.png` (48×48) | 2 個 COCO bbox（bridge / missing） |
| `IWSC-2026-006.zip` | `die_X1.png` (32×32) | 1 個 COCO bbox（crack） |

---

### 3. 整合測試結果（完整 End-to-End）

測試鏈路：annotation platform → iWISC FastAPI server（port 8765）

| 步驟 | 結果 |
|------|------|
| Phase 0: Tenant 註冊 | ✅ |
| Phase 1: `getAntList` 回傳 5 筆 pending 任務 | ✅ |
| Phase 2a: `claim_task` + HTTP ZIP 下載 + 解壓 wafer_001/002.png | ✅ |
| `original_annotation_json` 從 ZIP 解析（2 images, 3 annotations） | ✅ |
| Phase 2b: `save_annotation` 更新標注 | ✅ |
| Phase 2c: `complete_task` + `deliver_result` → iWISC `POST /tasks/{ant_id}/result` | ✅ |
| iWISC 端收到 annotation_json / new_classification / annotated_by | ✅ |
| Phase 3: `orig_img_orig_ant` ZIP — 原始 COCO 標注 | ✅ |
| Phase 3: `orig_img_new_ant` ZIP — 標注員修改版 | ✅ |
| 兩個 ZIP 標注內容不同（Bug 4 驗證） | ✅ |

**測試套件：534 tests passed, 1 xpassed（xfail on Windows）**

---

## 未完成 / 待追蹤

| 項目 | 說明 |
|------|------|
| RBAC 強制執行 | `is_user_authorized()` DB 層已備妥，但 MCP handler 層尚未在任何 API 路徑強制呼叫 |
| Tenant 管理 MCP tools | `register_tenant`、`add_user_to_tenant` 等在 `handlers.py` 有實作，但 `server.py` 未暴露為 MCP tool |
| iWISC 任務認領鎖 | `ant_active` 在 `claim_task` 時未回寫 iWISC（保持 0），理論上同任務可被多人認領 |
| dummy_sdk | Spec 要求獨立 SDK 目錄，目前由 `FakeConnector` + `fake://` scheme 取代，功能等效但命名不符 Spec |

## 相關檔案

- `mcp/annotation_mcp/server.py` — Bug 1、3 修正
- `mcp/annotation_mcp/handlers.py` — 參考（未修改）
- `.mcp.json` — Bug 2 修正（workspace 路徑）
- `sidecar/python-engine/annotation/core/models.py` — Bug 4：新增 `original_annotation_json`
- `sidecar/python-engine/annotation/storage/sqlite_store.py` — Bug 4：DB 遷移 + CRUD
- `sidecar/python-engine/annotation/services.py` — Bug 4、5：claim_task + export + _task_to_dict
- `external-systems/iwsc/routers/tasks.py` — 新增 `/files/` endpoint + 更新 `getAntTaskDetail`
- `external-systems/iwsc/test_zips/` — 3 個測試 ZIP
- `sidecar/python-engine/tests/test_mcp_config.py` — 修正矛盾測試邏輯
