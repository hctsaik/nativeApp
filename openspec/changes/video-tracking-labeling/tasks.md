# Tasks: Video Tracking Labeling (module_008)

> **狀態**：✅ 全部完成（2026-05-16）
> **測試**：14 tests, 0 failures（`pytest scripts/module_008/008_process_test.py`）

---

## Phase 0 — 環境與骨架 ✅

- [x] 建立 `sidecar/python-engine/scripts/module_008/` 目錄與空白檔案
- [x] 寫 `plugin.yaml`（runner: cv_framework, version: 0.1.0）
- [x] 在 `engine.py` 啟用 module_008（enable list + prod-enable list）
- [x] 在 DB seed 插入 module_008 row（含 migration 更新舊名稱）

## Phase 1 — 核心 Process 層 ✅

- [x] 寫 `_config.py`（獨立設定，讀寫 `{CIM_LOG_DIR}/config/module_008.json`，不依賴 module_006）
- [x] 寫 `_worker.py` — propagation subprocess worker
  - [x] 讀 session.json，載入 video_path、anchor_frame_idx、anchor_bboxes、time_range_sec
  - [x] 拆幀（JPEG 快取到 `frames/`）
  - [x] DINOv2 特徵提取（anchor 鄰域完整 grid；其他幀 bbox ROI 快取）
  - [x] DINO_AVAILABLE fallback（無 torch → flow-only，Output 頁顯示 warning）
  - [x] Lucas-Kanade optical flow（`cv2.calcOpticalFlowPyrLK`，9 點網格，median displacement）
  - [x] 0.5×flow + 0.5×dino weighted 信心分數
  - [x] 每幀完成後更新 `task.json`（progress, current_frame, total_frames, dino_available）
  - [x] 每幀結果寫入 `annotations/{frame_idx:06d}.json`（X-AnyLabeling JSON v6.0.0，相對 imagePath）
- [x] 寫 `008_process.py`
  - [x] `execute_logic(params)` — 若 anchor_bboxes 非空則呼叫 start_propagation()
  - [x] `start_propagation(session_dir, session_data)` — 建立 session.json，啟動 _worker subprocess
  - [x] `re_propagate(session_dir, from_frame_idx)` — 刪除 task.json，重啟 worker
  - [x] `save_correction(session_dir, frame_idx, bboxes)` — 更新單幀 annotation JSON（confidence=1.000）
  - [x] `export_xanylabeling(session_dir)` — annotations/ 複製到 exports/xanylabeling/，寫 manifest.json
  - [x] `list_annotated_frames(session_dir)` → list[int]
  - [x] `get_task_status(session_dir)` → dict
  - [x] `load_session / load_annotation / get_xany_exe`

## Phase 2 — Input 頁面（008_input.py）✅

- [x] 影片檔選擇（text_input 路徑 + 存在檢查）
- [x] 📂 瀏覽按鈕（tkinter filedialog，topmost 視窗）
- [x] anchor frame slider（讀 video fps + total_frames，顯示秒數）
- [x] 影格預覽縮圖（擷取 anchor frame，PIL 顯示）
- [x] 「🖊 在 X-AnyLabeling 畫框」按鈕（啟動 X-AnyLabeling，autosave）
- [x] st_autorefresh 偵測 `anchor_labels/` → 讀回 shapes[]，PIL 疊合預覽
- [x] 標注類別顯示（從 module_008 自己的 config 讀取）
- [x] 時間範圍設定（before_sec / after_sec，預設 1.0）
- [x] 移除「▶ 開始追蹤傳播」自訂按鈕（改由 cv_framework_runner 的「▶ 執行」觸發）
- [x] render_input() 回傳 anchor_bboxes + meta + labels（供 execute_logic 使用）
- [x] 📖 使用說明 expander（嵌入 guide.html）

## Phase 3 — Output 頁面（008_output.py）✅

- [x] 讀 session.json；不存在時顯示提示
- [x] task.json 輪詢（`st_autorefresh(interval=1500)`）
  - [x] state == "running"：progress bar + 當前幀 / 總幀數
  - [x] state == "error"：顯示錯誤訊息
  - [x] state == "done"：停止 autorefresh，顯示完成狀態
- [x] 時間軸縮圖列（8 張/列，anchor frame 標★，信心分數 🟢🟡🔴）
- [x] 大圖預覽 + PIL bbox 疊合（CJK 字型支援）
- [x] 手動校正 UI（label 選單 + x1/y1/x2/y2 數值輸入）
- [x] 「✅ 確認校正」→ `process.save_correction()`
- [x] 「🔄 從此幀重新傳播」→ `process.re_propagate()` + rerun
- [x] DINO_AVAILABLE == False 時顯示 warning banner
- [x] 「📤 匯出整個時間段 X-AnyLabeling JSON」→ `process.export_xanylabeling()` + 顯示輸出路徑

## Phase 4 — 測試（008_process_test.py）✅ 14/14

- [x] `test_load_session_returns_none_when_missing`
- [x] `test_load_session_reads_json`
- [x] `test_annotations_are_valid_xanylabeling_json`
- [x] `test_annotations_use_relative_image_path`
- [x] `test_confidence_stored_in_description`
- [x] `test_save_correction_updates_single_frame`
- [x] `test_export_xanylabeling_creates_manifest`
- [x] `test_export_creates_correct_file_count`
- [x] `test_list_annotated_frames_returns_sorted_indices`
- [x] `test_get_task_status_returns_idle_when_missing`
- [x] `test_no_streamlit_import_in_process`
- [x] `test_execute_logic_returns_error_when_no_bboxes`
- [x] `test_execute_logic_idle_passthrough`
- [x] `test_execute_logic_starts_propagation`

## Phase 5 — 文件更新 ✅

- [x] 更新 `docs/MODULES.md`（改為索引，指向 docs/modules/）
- [x] 建立 `docs/modules/module_008.md`（完整技術文件，含最新 execute_logic 行為）
- [x] 建立 `docs/modules/module_006.md`（含獨立設定系統）
- [x] 建立 `docs/platform/`、`docs/components/`（文件分層結構）
- [x] 建立 `docs/modules/README.md`（模組索引）
- [x] 建立 `scripts/module_008/README.md`（開發者快速參考）
- [x] 建立 `scripts/module_006/README.md`（開發者快速參考）
- [x] 建立 `scripts/module_008/guide.html`（使用者操作指南，含 SVG 流程圖）
- [x] 建立 `scripts/module_006/guide.html`（使用者操作指南，含 SVG 流程圖）
- [x] 嵌入 guide.html 至 008_input.py 和 006_input.py（📖 使用說明 expander）
