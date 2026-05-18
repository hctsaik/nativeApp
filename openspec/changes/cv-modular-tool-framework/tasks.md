# 實作任務：共用 CV 模組框架

## Phase 1 — 框架骨架與示範模組（module_001）

- [x] 建立 `sidecar/python-engine/scripts/__init__.py`
- [x] 建立 `sidecar/python-engine/scripts/module_001/` 資料夾
- [x] 實作 `module_001/__init__.py`（MODULE_NAME = "OpenCV 影像處理"）
- [x] 實作 `module_001/001_input.py`（render_input → 來源選擇、功能下拉、參數滑桿）
- [x] 實作 `module_001/001_process.py`（execute_logic → 呼叫現有 opencv 純函式）
- [x] 實作 `module_001/001_output.py`（render_output → 並排原圖/處理後影像）
- [x] 實作 `module_001/001_process_test.py`（pytest 測試 execute_logic）

## Phase 2 — Framework Runner

- [x] 實作 `sidecar/python-engine/cv_framework_runner.py`
  - [x] `discover_modules()` 掃描邏輯
  - [x] `load_layer()` 動態載入邏輯
  - [x] `main()` Streamlit UI 流程
- [x] 在 `engine.py` SQLite seed 加入 `cv-framework` 工具條目
- [x] 手動測試：從 portal 啟動 `cv-framework`，確認 module_001 可被選取與執行

## Phase 3 — Claude Code Skill

- [x] 建立 `.claude/commands/new-cv-module.md` skill 定義
  - [x] 定義輸入參數（ID、名稱、輸入/運算/輸出描述）
  - [x] 定義生成邏輯（5 個檔案的模板）
  - [x] 定義完成後的提示訊息
- [x] 以 `/new-cv-module` 生成 `module_002`（影像資訊讀取）作為驗收測試

## 驗收條件

- `npm run test:python` 通過所有 `001_process_test.py` 測試
- 從 portal 可啟動 `cv-framework` 並使用 module_001 執行影像處理
- 使用 `/new-cv-module` 生成 module_002 後，不修改任何生成的程式碼即可在框架中運行
- `module_001/001_process.py` 中無任何 `import streamlit` 陳述
