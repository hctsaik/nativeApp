# 任務：Standalone Split-Tool 架構

## Phase 1 — 核心機制

- [x] `engine.py` 新增 `_split_scripts(tool)` — 偵測 `{stem}_input.py` / `{stem}_output.py`
- [x] `ToolProcessManager._spawn()` 注入 `CIM_TOOL_LAYER` 環境變數（`"input"` / `"output"`）
- [x] `ToolProcessManager.start()` 在啟動前清除舊結果檔（`result_file.unlink(missing_ok=True)`）
- [x] Portal `main.jsx` tab iframe 改為 CSS `display:none` 常駐，不再 unmount

## Phase 2 — 參考實作：opencv-tool

- [x] 建立 `tools/opencv_tool_input.py`
  - [x] sidebar：影像來源 + 功能選擇 + 參數
  - [x] 主畫面右上角：caption + ▶ 執行按鈕（同行，不被圖遮蔽）
  - [x] 預覽原始影像（`ui_utils.show_image`，支援 RWD + lightbox）
  - [x] 執行：`_encode_image`（BGR→RGB→PNG→base64）→ 寫結果信封 → notify_complete
- [x] 建立 `tools/opencv_tool_output.py`
  - [x] 靜態渲染（無 polling loop）
  - [x] `_decode_image`（base64→PNG→ndarray→RGB）
  - [x] 並排顯示原始影像 + 處理後影像
  - [x] 顯示功能名稱、尺寸、耗時、參數

## Phase 3 — 進階示範：animal-tagger

- [x] 建立 `testData/animal/animals.db`（12 張影像，欄位：id / filename / file_type / image_time / true_label / classification / tagged_at）
- [x] 建立 `tools/animal_tagger.py`（stub，供 engine _split_scripts 推導路徑）
- [x] 建立 `tools/animal_tagger_input.py`
  - [x] 類別篩選下拉（ALL / 貓 / 狗 / 大象）
  - [x] 進階路徑設定（DB 路徑 / 影像目錄）
  - [x] ▶ 載入資料 → 寫信封 JSON（user_input 含 filter/db_path/image_dir）→ notify_complete
- [x] 建立 `tools/animal_tagger_output.py`
  - [x] 讀結果信封 → 從 `user_input` 取 db_path / filter
  - [x] `st.dataframe` grid（單行選取，支援 Streamlit ≥ 1.35 on_select，舊版 fallback to number_input）
  - [x] 標記列：分類下拉 + Submit → UPDATE DB → 自動跳下一筆未標記記錄
  - [x] 影像預覽（`ui_utils.show_image`）
- [x] `engine.py` seed 新增 `animal-tagger` 條目

## Phase 4 — 共用工具程式庫

- [x] 建立 `tools/ui_utils.py` — `show_image(source, caption)` RWD 圖片 + lightbox
- [x] 建立 `tools/db_utils.py` — `SimpleDAO` SQLite DAO（query / execute / execute_many / last_insert_id）
- [x] 建立 `tools/log_utils.py` — `get_logger(name)` 雙輸出 logging（stdout + file）
- [x] 建立 `tools/tool_result.py` — `write_result` / `read_result` 結果信封（user_input + process_result）
- [x] 建立 `tools/tool_comms.py` — `notify_start` / `notify_complete` postMessage 封裝
- [x] 重構 `opencv_tool_input.py` / `animal_tagger_input.py` 使用以上共用模組

## Phase 5 — Portal 驅動 Output Reload

- [x] 移除 output page 的 polling loop（`time.sleep` + `st.rerun()`）
- [x] `main.jsx` `EXECUTE_COMPLETE` handler 新增 `setOutputNonce(n + 1)`
- [x] output iframe src 加上 `?_r={nonce}` cache-bust，觸發瀏覽器 reload
- [x] output page 改為靜態渲染：`read_result()` → 無資料時顯示提示並 return

## Phase 6 — 測試

- [x] `test_tool_comms.py` — 16 tests：`notify_start` / `notify_complete` JSON 格式、`_cim` flag、height=0
- [x] `test_tool_result.py` — 16 tests：`write_result` / `read_result` 信封格式、舊格式退化為 None
- [x] `test_split_scripts.py` — `_split_scripts` fallback + 實際檔案存在性
- [x] `test_opencv_tool_io.py` — encode/decode roundtrip + `_file_mtime`
- [x] `test_animal_tagger.py` — `_query_records` / `_update_tag` / `_next_untagged_index`
- [x] `test_db_utils.py` — 17 tests：`SimpleDAO` 全部 method
- [x] `test_log_utils.py` — 12 tests：handler 數量、檔案建立、level、caching
- [x] `test_sqlite_adapter.py` — 更新為 opencv-tool + animal-tagger seed；確認 sample-csv / cv-framework disabled
- [x] 全套 pytest 通過

## Phase 7 — 文件

- [x] 建立本 spec（`openspec/changes/standalone-split-tool-architecture/`）
- [x] 更新 `design.md`：反映信封格式、Portal reload 機制、共用工具庫
- [x] 更新 `README.md`：新增「開發新工具」章節，說明 `/new-split-tool` skill 使用方式
- [x] 建立 `.claude/commands/new-split-tool.md` skill：引導開發者產生完整工具骨架
- [ ] Puppeteer E2E 測試通過（`scripts/run-opencv-tool.js`）— CDP 連線問題待解

## 驗收條件

- [x] 切換 Output tab 再切回 Input tab，sidebar 選項不遺失
- [x] 執行後 Portal 自動切至 Output tab，output page 顯示新結果（Portal reload 機制）
- [x] 第二次執行，Output tab 自動顯示新結果（nonce cache-bust）
- [x] Output page 完全靜止，不再有週期性畫面更新
- [x] portal 下拉只顯示 opencv-tool 和 animal-tagger（sample-csv / cv-framework 隱藏）
- [x] `npm run test:python` 全部通過
- [ ] Puppeteer E2E 完整驗收
