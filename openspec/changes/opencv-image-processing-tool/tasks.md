# 任務：OpenCV 影像處理工具

## 1. 規劃

- [x] 撰寫 proposal.md — 定義工具目的與範圍
- [x] 撰寫 design.md — 定義架構、UI 佈局、模組結構、支援功能
- [x] 撰寫 tasks.md（本文件）

## 2. 影像資產

- [x] 將 `testData/road.png` 複製至 `sidecar/python-engine/tools/road.png`
  作為工具預設內建影像

## 3. 工具實作

- [x] 實作純函式層（無 streamlit 依賴）：
  - [x] `apply_grayscale`
  - [x] `apply_gaussian_blur`
  - [x] `apply_canny`
  - [x] `apply_threshold`
  - [x] `apply_erosion`
  - [x] `apply_dilation`
  - [x] `apply_sharpen`
  - [x] `apply_sobel`
  - [x] `apply_equalize_hist`
  - [x] `apply_contour`
- [x] 實作影像來源載入邏輯（host 路徑 > 上傳 > 預設）
- [x] 實作 Streamlit sidebar（功能選擇 + 動態參數）
- [x] 實作主畫面並排顯示（原圖 + 處理後）
- [x] 顯示影像尺寸與處理耗時

## 4. 工具登錄

- [x] 在 `engine.py` `SQLiteToolAdapter._initialize()` 新增 `opencv-tool` seed 條目

## 5. 單元測試

- [x] 撰寫 `tests/test_opencv_tool.py`，覆蓋所有純函式（46 項測試全部通過）：
  - [x] 各功能輸出形狀正確
  - [x] 各功能輸出 dtype 合理
  - [x] 邊界輸入（全黑、全白、最小 kernel）不崩潰
  - [x] 參數邊界值測試

## 6. 驗證

- [x] 在 portal Mode 1 從工具下拉選單啟動 opencv-tool
- [x] 功能切換與參數調整即時生效
- [x] host 選擇圖片後工具能正確讀取
- [x] pytest 單元測試全部通過（78/78 含既有測試）
