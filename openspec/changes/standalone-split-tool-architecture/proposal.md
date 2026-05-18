# 變更：Standalone Split-Tool 架構

## 為何需要此變更

原有的 cv-framework 採用單一 Framework Runner 程序動態載入所有模組，
造成以下問題：

1. **工具之間耦合**：所有模組共用同一個 Streamlit 程序，一個模組出錯影響全部
2. **Input/Output 生命週期混亂**：單一程序同時管理輸入收集與輸出呈現，
   切換 tab 時 Streamlit session 被重置，使用者輸入的參數遺失
3. **難以獨立測試**：模組必須透過 Framework Runner 才能執行
4. **Output 不會自動更新**：再次執行後 Output tab 仍顯示舊結果

## 變更內容

將每個工具拆分為兩支獨立的 Streamlit 程序：

- `{tool_id}_input.py` — 負責收集使用者輸入、執行運算、寫入結果
- `{tool_id}_output.py` — 負責輪詢結果檔、呈現執行結果

工具透過 SQLite 工具登錄表獨立登錄，由 Portal 的工具下拉選單直接選取，
不再依賴任何中間框架。

## 適用對象

- 所有需要「輸入 → 執行 → 輸出」流程的工具
- 輸出需要在不同執行間保留顯示（不因 tab 切換而重置）
- 工具之間需要完全隔離的場景

## 範圍

納入範圍：
- `engine.py` `_split_scripts()` 機制設計與實作
- `opencv_tool_input.py` / `opencv_tool_output.py` 作為參考實作
- `animal_tagger_input.py` / `animal_tagger_output.py` 作為進階示範（含 DB 互動）
- Portal `main.jsx` tab iframe 常駐機制（CSS show/hide）
- 結果序列化規範（JSON + base64 影像）

不納入範圍：
- 多工具同時執行（目前每次只執行一個工具）
- 工具間通訊
- 結果檔案的版本管理或歷史記錄
