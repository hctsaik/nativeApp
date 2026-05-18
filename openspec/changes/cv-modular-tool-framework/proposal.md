# 變更：共用 CV 模組框架（cv-modular-tool-framework）

## 為何需要此變更

現有的工具（`opencv_tool.py`、`sample_csv_tool.py`）是單檔案 Streamlit 應用，
將輸入 UI、運算邏輯、輸出 UI 混寫在一起。這帶來以下問題：

1. **可測試性低**：邏輯和 Streamlit UI 耦合，無法在沒有 GUI 的情況下單獨測試運算核心。
2. **AI 開發效率低**：每次請 AI 新增功能時，需要在一個大型檔案中定位與修改，容易誤改其他邏輯。
3. **無法被 C# API 呼叫**：混有 `st.xxx` 的邏輯層無法直接作為純函式被外部服務呼叫。
4. **新模組開發重複成本高**：開發者每次都要從頭建立相同的結構樣板。

## 變更目標

1. 定義標準化的三層模組結構（Input / Process / Output）。
2. 建立主框架執行器（Framework Runner），能自動探索並執行任意符合規範的模組。
3. 設計一個 Claude Code Skill（`/new-cv-module`），讓開發者只需描述需求，AI 即可自動生成完整模組骨架。

## 範圍

**納入範圍：**
- `sidecar/python-engine/scripts/` 目錄結構規範
- 三層介面契約定義（`render_input` / `execute_logic` / `render_output`）
- Framework Runner Streamlit 工具（`cv_framework_runner.py`）
- 自動模組探索機制（掃描 `scripts/module_*` 資料夾）
- engine.py SQLite seed 新增 `cv-framework` 工具條目
- pytest 測試策略規範
- Claude Code Skill 設計規格（`/new-cv-module`）

**不納入範圍：**
- 現有工具（`opencv_tool.py`）的遷移（保持向後相容）
- DB 動態載入模式（exec() 從資料庫執行）
- 即時串流、批次處理
- GPU 加速

## 影響

- 新增一個可從 portal Mode 1 啟動的 Framework Runner 工具
- 現有工具不受影響，與新框架並存
- 開發新 CV 模組的工時從數小時降至數分鐘
