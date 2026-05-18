# 變更：OpenCV 影像處理工具

## 為何需要此變更

CIM 平台需要一個可互動的影像處理工具，讓使用者能夠透過 Streamlit GUI
直接在本機端套用常見的 OpenCV 影像處理演算法，並即時調整參數觀察效果。
此工具同時作為 CIM 動態工具載入機制（SQLite 工具登錄表）的第二個範例，
驗證多工具並存與動態切換的能力。

## 變更內容

新增一個 Streamlit 工具 `opencv_tool.py`，整合以下 OpenCV 功能：

- 灰階轉換
- 高斯模糊（可調整 kernel size 與 sigma）
- Canny 邊緣偵測（可調整雙閾值）
- 二值化（可選 Binary / Otsu 模式，可調閾值）
- 侵蝕與膨脹（可調整 kernel size 與迭代次數）
- 銳化（可調整強度）
- Sobel 邊緣偵測（可選 X / Y / 合併方向）
- 直方圖均衡化
- 輪廓偵測（疊加在原圖上顯示）

工具應：
- 以 `road.png` 作為預設內建影像
- 支援 host 選擇的任意圖片路徑（透過 `CIM_SELECTED_PATHS_FILE`）
- 支援直接在 Streamlit 內上傳圖片
- 並排顯示原始影像與處理後影像
- 顯示處理耗時與影像尺寸資訊
- 在 SQLite 工具登錄表中自動 seed，可從 portal 動態啟動

## 範圍

納入範圍：
- `sidecar/python-engine/tools/opencv_tool.py` 實作
- `sidecar/python-engine/tools/road.png` 預設影像（複製自 testData）
- `engine.py` SQLite seed 新增 `opencv-tool` 條目
- 單元測試覆蓋工具的邏輯函式

不納入範圍：
- 即時影像串流（webcam）
- 批次影像處理
- 結果影像匯出
- GPU 加速

## 影響

- 新增第二個可在 portal Mode 1 啟動的 Streamlit 工具
- 驗證 SQLite 動態工具登錄表支援多工具
- 展示 OpenCV headless 套件在本機端的實際應用
