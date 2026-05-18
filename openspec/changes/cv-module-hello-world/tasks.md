# 任務：CV 框架 Hello World 範本模組（module_002）

## Phase 1 — 建立 module_002

- [x] 建立 `sidecar/python-engine/scripts/module_002/` 資料夾
- [x] 實作 `module_002/__init__.py`（MODULE_NAME = "影像資訊讀取"）
- [x] 實作 `module_002/002_input.py`
  - [x] 載入 `road.png`（固定路徑，`tools/road.png`）
  - [x] 顯示圖片預覽（`st.image`）
  - [x] 一個 `st.text_input("Memo / 備註")`
  - [x] `render_input() -> dict` 回傳 `{ image_path, memo }`
- [x] 實作 `module_002/002_process.py`
  - [x] `execute_logic(params) -> dict`
  - [x] 用 `PIL.Image.open` 讀解析度
  - [x] 用 `os.path.getsize` 讀檔案大小
  - [x] 回傳 `{ filename, resolution, file_size_bytes, file_size_kb, memo }`
  - [x] **禁止** `import streamlit`
- [x] 實作 `module_002/002_output.py`
  - [x] `render_output(result) -> None`
  - [x] 顯示 `st.table` 或 `st.dataframe`，欄位：檔案名稱、解析度、檔案大小、Memo

## Phase 2 — Unit Test

- [x] 實作 `module_002/002_process_test.py`
  - [x] 測試：給定 `road.png` 真實路徑，`execute_logic` 回傳 dict 包含正確欄位
  - [x] 測試：`resolution` 是 tuple of int，`(width, height)`
  - [x] 測試：`file_size_bytes > 0`
  - [x] 測試：`file_size_kb == round(file_size_bytes / 1024, 2)`
  - [x] 測試：`memo` 原樣帶入
  - [x] 測試：`002_process.py` 原始碼不含 `import streamlit`
- [x] 執行 `pytest scripts/module_002/` 確認全部通過

## Phase 3 — /new-cv-module Skill

- [x] 建立 `.claude/commands/new-cv-module.md`
  - [x] 說明框架三層契約（render_input / execute_logic / render_output）
  - [x] 以 module_002 為範本，說明每個檔案的標準結構
  - [x] Skill 執行流程：詢問參數 → 生成 5 個檔案 → 提示確認
  - [x] 輸入參數：模組 ID（3 位數字）、模組名稱、輸入描述、運算描述、輸出描述
  - [x] 生成檔案清單：`__init__.py`、`{ID}_input.py`、`{ID}_process.py`、`{ID}_output.py`、`{ID}_process_test.py`

## Phase 4 — 文件更新

- [x] 更新 `openspec/changes/cv-modular-tool-framework/design.md`
  - [x] 新增「快速開始」段落，以 module_002 為例說明建立新模組的步驟
  - [x] 新增「框架契約摘要表」（函數簽名 + 回傳型別 + 禁止事項）

## 驗收條件

- `pytest scripts/module_002/` 全部通過
- 從 portal 啟動 `cv-framework`，選擇「影像資訊讀取」，輸入 Memo 並執行，Output 頁籤顯示正確表格
- `/new-cv-module` skill 可以生成 module_003 骨架，執行後不需修改即可在 cv-framework 中被選取
