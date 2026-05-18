# module_009 — 統一標注平台

**版本**: 1.0.0  
**Runner**: `annotation_runner.py`  
**狀態**: 啟用

---

## 概觀

module_009 是一個同時兼顧影像資料集與影片的標注管理系統。  
以 SQLite DB 為 single source of truth，整合 DINOv2+LK 追蹤與 X-AnyLabeling。

### 解決的問題

| 問題 | 解決方式 |
|---|---|
| 資料狀態不透明 | Master Table 顯示所有資產進度 |
| 圖片與影片分開管理 | 統一 `(session_id, frame_idx)` 資料模型 |
| 無法多檔管理 | 資料夾一次載入，整體進度視野 |
| 追蹤結果難修正 | 單幀校正流程（不影響其他幀） |
| 無 process lock | SQLite row + psutil PID 驗證 |

---

## 架構

```
annotation_runner.py (Streamlit 單頁)
       │
       ▼
009_process.py (公開 API, 無 Streamlit)
  ├── _db.py (annotation.sqlite DAL)
  ├── _xany_launcher.py (X-AnyLabeling 啟動/監聽)
  └── _worker.py (DINOv2+LK 背景追蹤 subprocess)
```

---

## 資料庫

**路徑**: `{CIM_LOG_DIR}/db/annotation.sqlite`

### video_assets
儲存所有資料來源（影片 or 圖片資料夾）。`asset_type` ∈ `{video, image_dir}`。

### annotation_sessions
每個 asset 的標注工作階段。狀態機：

```
未標記 → 追蹤中 → 標記中 → 已標記 → 已同步
```

`xany_pid` 欄位作為 process lock，搭配 `psutil.pid_exists()` 驗證。

### frame_annotations
每幀的標注資料（X-AnyLabeling JSON v6.0.0）。圖片固定 `frame_idx=0`。  
`source` ∈ `{tracking, manual, xanylabeling}`。

---

## 追蹤流程

1. 使用者點「🛠️ 開啟標注」
2. `start_annotation()` 寫 `anchor_info.json`，啟動 `_worker.py` subprocess
3. Worker 執行 DINOv2+LK（無 torch → flow-only），INSERT INTO `frame_annotations`
4. Worker 完成 → UPDATE status='標記中'
5. UI 輪詢偵測到狀態變更 → `open_xanylabeling()` 啟動 X-AnyLabeling，acquire lock
6. 使用者標注完，關閉 X-AnyLabeling
7. PID 監聽偵測到進程死亡 → `update_after_xany_close()` UPSERT frame_annotations，release lock，status='已標記'
8. 自動聚焦下一個未標記 asset

---

## 信心分數計算

```
flow_conf = 追蹤到的 LK 點佔比（0~1）
dino_conf = anchor patch 與目標 patch 的 cosine similarity（0~1）
final_conf = 0.5 × flow_conf + 0.5 × dino_conf

無 torch → final_conf = flow_conf
```

---

## 公開 API（009_process.py）

```python
scan_folder(folder_path: str) -> list[dict]
load_assets(db_path_override=None) -> list[dict]
start_annotation(session_id: int, anchor_info: dict) -> dict
open_xanylabeling(session_id: int) -> dict
open_single_frame(session_id: int, frame_idx: int) -> dict
get_session_status(session_id: int) -> dict | None
update_after_xany_close(session_id: int) -> dict
update_after_single_close(session_id: int, frame_idx: int) -> dict
sync_to_db(session_ids: list[int]) -> dict
get_next_unannotated(db_path_override=None) -> int | None
generate_summary(session_id: int) -> dict
poll_tracking_status(session_id: int) -> dict
```

---

## 與其他模組的關係

| 模組 | 關係 |
|---|---|
| module_006 | 共享 X-AnyLabeling JSON v6.0.0 格式，不直接 import |
| module_008 | 追蹤核心邏輯移植自此；module_008 繼續維持原樣 |

---

## 測試

```bash
pytest scripts/module_009/009_process_test.py  # 14 tests
```

測試涵蓋：scan_folder、load_assets、process lock、summary 計算、
get_next_unannotated、update_after_xany_close、sync_to_db、
無 Streamlit import、X-AnyLabeling JSON 格式、flow-only 追蹤、單幀校正隔離性。
