# Tasks: Unified Annotation Platform (module_009)

**狀態**：✅ 全部完成（2026-05-16）  
**測試**：14 tests, 0 failures（`pytest scripts/module_009/009_process_test.py`）

---

## Phase 0 — 環境與骨架✅

- [x] 建立 `sidecar/python-engine/scripts/module_009/` 目錄
- [x] 建立 `plugin.yaml`（runner: annotation_runner, version: 1.0.0）
- [x] 在 `engine.py` 啟用 module_009（enable list + seed INSERT）
- [x] 建立 `tools/annotation_runner.py`（新 runner，載入 009_runner.py）
- [x] 建立骨架檔案：`_config.py`, `_db.py`, `_worker.py`, `_xany_launcher.py`, `009_process.py`, `009_runner.py`
- [x] 確認 `psutil` 已在 requirements.txt

---

## Phase 1 — 資料存取層（_db.py + 009_process.py）✅

- [x] 實作 `_db.py`：建立 annotation.sqlite，建立三張表（video_assets, annotation_sessions, frame_annotations）
- [x] `scan_folder(folder_path)` — 掃描資料夾，回傳影片/圖片清單，INSERT OR IGNORE
- [x] `load_assets(db_path)` — JOIN video_assets + annotation_sessions，回傳完整狀態清單
- [x] `get_session_status(session_id)` — 讀單一 session 狀態
- [x] `get_next_unannotated(db_path)` — 回傳下一個 status='未標記' 的 session_id
- [x] `generate_summary(session_id)` — 從 frame_annotations 計算幀數、物件數、平均信心
- [x] `acquire_lock / release_lock`（psutil PID 驗證）

---

## Phase 2 — 追蹤背景 Job（_worker.py）✅

- [x] 讀取追蹤參數（session_id → DB 查詢 asset + anchor_info.json）
- [x] 拆幀 → `{xany_project_dir}/frames/frame_{idx:06d}.jpg`
- [x] DINOv2 特徵提取（DINO_AVAILABLE fallback）
- [x] Lucas-Kanade optical flow（9 點網格，median displacement）
- [x] 合成信心：`0.5 × flow + 0.5 × dino`
- [x] 每幀輸出 X-AnyLabeling JSON → `{xany_project_dir}/annotations/`
- [x] INSERT INTO frame_annotations（source='tracking'）
- [x] 完成後 UPDATE annotation_sessions SET status='標記中'
- [x] 錯誤處理：UPDATE status='未標記'（rollback）

---

## Phase 3 — X-AnyLabeling 整合（_xany_launcher.py + 009_process.py）✅

- [x] `start_annotation(session_id, anchor_info)` — 啟動 _worker.py subprocess，設 status='追蹤中'
- [x] `open_xanylabeling(session_id)` — 從 frame_annotations 生成 classes.txt，啟動 X-AnyLabeling，acquire_lock
- [x] `open_single_frame(session_id, frame_idx)` — 單幀模式：只傳單幀 JSON，啟動 X-AnyLabeling
- [x] `update_after_xany_close(session_id)` — 掃描 annotations/，UPSERT frame_annotations，release_lock，status='已標記'
- [x] `update_after_single_close(session_id, frame_idx)` — 只更新單幀，不影響其他幀
- [x] `sync_to_db(session_ids)` — copytree 至 backup/，UPDATE status='已同步'
- [x] `poll_tracking_status(session_id)` — 偵測追蹤完成，自動啟動 X-AnyLabeling

---

## Phase 4 — Streamlit UI（009_runner.py + annotation_runner.py）✅

- [x] `annotation_runner.py`：新 runner 入口，直接載入並執行 `009_runner.py`
- [x] `009_runner.py`：單頁 Streamlit（不走 Input/Output 分頁）
  - [x] 頂部：DB 連線燈號、MCP 連線燈號
  - [x] 資料夾選擇列：text_input + 📂 瀏覽（tkinter）+ 載入按鈕
  - [x] 篩選列：狀態篩選 / 類型篩選（影片/圖片）/ 搜尋框
  - [x] Master Table：每列含狀態 badge、摘要 caption、操作按鈕
  - [x] 狀態 badge（⏳ 追蹤中 / 🟡 標記中 / 🟢 已標記 / 🔵 已同步 / ⬜ 未標記）
  - [x] 每列操作按鈕：`[🛠️ 開啟標注]` / `[⏳ 追蹤中...]`（disabled）/ `[🔒 標注中]`（disabled）/ `[🔍 修正]`
  - [x] 單幀校正展開區（點「🔍 修正」後展開縮圖列 + 選幀按鈕）
  - [x] 底部全域按鈕：`[💾 存檔備份（N 筆待同步）]`（含確認 dialog）
  - [x] 自動輪詢（`st_autorefresh(interval=2000)`）：更新追蹤進度 + PID 監聽
  - [x] 完成後自動聚焦下一個未標記 asset

---

## Phase 5 — 測試（009_process_test.py）✅ 14/14

- [x] `test_scan_folder_finds_videos_and_images`
- [x] `test_scan_folder_skips_existing_assets`
- [x] `test_load_assets_returns_correct_status`
- [x] `test_acquire_lock_prevents_duplicate`
- [x] `test_acquire_lock_releases_dead_pid`
- [x] `test_generate_summary_counts_frames_and_objects`
- [x] `test_get_next_unannotated_returns_first_untagged`
- [x] `test_get_next_unannotated_returns_none_when_all_done`
- [x] `test_update_after_xany_close_upserts_frames`
- [x] `test_sync_to_db_moves_temp_to_backup`
- [x] `test_no_streamlit_import_in_process`
- [x] `test_worker_outputs_xanylabeling_json_format`
- [x] `test_worker_flow_only_when_dino_unavailable`
- [x] `test_single_frame_correction_does_not_affect_other_frames`

---

## Phase 6 — 文件更新 ✅

- [x] 建立 `scripts/module_009/README.md`（開發者快速參考）
- [x] 更新 `docs/modules/README.md`（新增 module_009 列）
- [x] 建立 `docs/modules/module_009.md`（完整技術文件）
- [x] 更新 `engine.py`（module_009 in seed + enable lists）
- [ ] 建立 `scripts/module_009/guide.html`（使用者操作指南）— 可後續補充

---

## 依賴與風險

| 項目 | 說明 |
|---|---|
| `psutil` | 已加入 requirements.txt，已安裝 |
| DINOv2 / torch | 可選依賴，DINO_AVAILABLE fallback 已完整實作 |
| X-AnyLabeling MCP | `annotation_launch_xanylabeling_project` tool 可複用 |
| `annotation_runner.py` | 新 runner，engine.py 已更新 |
| `st_autorefresh` | 已在 requirements.txt |
