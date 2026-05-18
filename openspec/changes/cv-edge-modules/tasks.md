# 實作任務：CV 邊緣模組套件（cv-edge-modules）

## Phase 1 — module_003 不規則邊框產生器

- [x] 建立 `scripts/module_003/__init__.py`（MODULE_NAME = "不規則邊框產生器"）
- [x] 實作 `003_input.py`（尺寸、粗糙度、頻率、強度、對稱、填色、背景色、種子、備註滑桿）
- [x] 實作 `003_process.py`（純數學生成帶紋理矩形，回傳 image_b64）
- [x] 實作 `003_output.py`（顯示生成影像 + 尺寸備註）
- [x] 實作 `003_process_test.py`（pytest，base64 合法性、尺寸符合、memo 帶入）
- [x] `engine.py` 加入 cvmod-003 seed 與 re-enable

## Phase 2 — module_004 邊緣完整度偵測

- [x] 建立 `scripts/module_004/__init__.py`（MODULE_NAME = "邊緣完整度偵測"）
- [x] 實作 `004_input.py`（上傳影像、Parts 輸入）
- [x] 實作 `004_process.py`（Canny 偵測、計算左右粗糙度 / 頻率 / 強度、回傳量測值 + image_b64 + image_name）
- [x] 實作 `004_output.py`（顯示量測表格、儲存 SQLite 按鈕、`st.toast` 成功通知）
- [x] `_ensure_db()` 含 PRAGMA table_info 遷移邏輯（image_name / image_blob 欄位）
- [x] 實作 `004_process_test.py`（12 個測試，含 image_name_passthrough）
- [x] `engine.py` 加入 cvmod-004 seed 與 re-enable

## Phase 3 — module_005 邊緣記錄查詢

- [x] 建立 `scripts/module_005/__init__.py`（MODULE_NAME = "邊緣記錄查詢"）
- [x] 實作 `005_input.py`（From / To 雙欄日期選擇器，預設三個月區間）
- [x] 實作 `005_process.py`（查詢 edge_records.sqlite，回傳 records 列表，image_blob → image_b64）
- [x] 實作 `005_output.py`（表格顯示、點擊檔名 `@st.dialog` 放大預覽、🖼️ 下載按鈕）
- [x] 實作 `005_process_test.py`（11 個測試，含 monkeypatch CIM_LOG_DIR）
- [x] `engine.py` 加入 cvmod-005 seed 與 re-enable

## Phase 4 — scripts/shared/ 共用元件

- [x] 建立 `scripts/shared/__init__.py`（空）
- [x] 實作 `scripts/shared/ui_components.py`
  - [x] `three_months_ago(ref?)` — 純日期函式
  - [x] `date_input_single(label, default, key)` — 單日期選擇器
  - [x] `date_input_range(...)` — From / To 雙欄選擇器，From > To 顯示警告
  - [x] `parts_input(key, placeholder)` — Parts 一列輸入
  - [x] `save_success_toast(message?)` — toast 成功通知
  - [x] `save_error_toast(message?)` — toast 失敗通知
  - [x] `download_image_button(bytes, filename, label, key)` — 下載按鈕
- [x] 實作 `scripts/shared/image_widget.py`
  - [x] `render_image_preview(image_bytes, filename, thumb_width, key)`
  - [x] `_LIGHTBOX_SETUP` — 零高度 iframe 注入 parent DOM lightbox
  - [x] 縮圖 + hover 預覽（visibility:hidden 保留空間）
  - [x] 點擊縮圖 → `postMessage` → lightbox 在畫面中央放大
  - [x] `<a download>` HTML 下載（Electron 相容）
- [x] 建立 `tests/test_shared_components.py`（12 個測試）

## Phase 5 — 文件與技能更新

- [x] 建立 `openspec/changes/cv-edge-modules/proposal.md`
- [x] 建立 `openspec/changes/cv-edge-modules/design.md`
- [x] 建立 `openspec/changes/cv-edge-modules/tasks.md`（本檔）
- [x] 更新 `.claude/commands/new-cv-module.md`（補充 003–005 經驗：序列化規則、SQLite、image_bytes、DB 遷移、date range、toast、dialog、shared import）
- [x] 建立 `.claude/commands/common-component.md`（共用 UI 元件 skill）
- [x] 更新 `sidecar/python-engine/README.md`（CV Module Framework 章節）

## 驗收條件

- `pytest scripts/module_003/ scripts/module_004/ scripts/module_005/ tests/test_shared_components.py` 全數通過
- Portal 可啟動 cvmod-003 / cvmod-004 / cvmod-005
- module_004 儲存後 toast 出現 ✅ 一個符號
- module_005 點擊影像檔名後出現放大對話方塊
- module_005 每列可獨立下載原圖
- `005_process.py` / `003_process.py` 原始碼不含 `import streamlit`
