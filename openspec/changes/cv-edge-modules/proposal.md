# 變更：CV 邊緣模組套件（cv-edge-modules）

## 為何需要此變更

為了驗證 CV 模組框架在「需要持久儲存」與「跨模組查詢」場景下的完整能力，
並建立可供所有模組重用的共用 UI 元件庫，本次變更以邊緣偵測領域為範例，
實作三個新模組與一個共用元件目錄。

## 變更內容

### module_003 — 不規則邊框產生器

以純數學方式生成帶有可控凹凸紋理的矩形影像，供邊緣偵測測試使用。
參數涵蓋：尺寸、左右粗糙度（0–80）、頻率（1–200）、強度（1–49%）、對稱性、填色、背景色、種子值。

### module_004 — 邊緣完整度偵測

上傳影像 → Canny 邊緣偵測 → 計算左右粗糙度、主頻、強度。
量測結果可儲存至 SQLite（`edge_records.sqlite`），含原始影像 BLOB。
儲存成功以 `st.toast` 通知（不污染頁面佈局）。

### module_005 — 邊緣記錄查詢

從 `edge_records.sqlite` 依日期區間（From～To，預設最近三個月）查詢量測記錄。
結果以表格呈現，點擊影像檔名開啟 `st.dialog` 放大預覽（原始尺寸）並提供下載。

### scripts/shared/ — 共用 UI 元件

- `image_widget.py`：縮圖 + hover CSS 預覽 + st.dialog 放大 + `<a download>` 下載
- `ui_components.py`：日期選擇器（單一 / 區間）、Parts 輸入、儲存成功 toast、下載按鈕等標準化函式

## 範圍

**納入：**
- 三個 cvmod（003 / 004 / 005）的完整三層實作與 pytest 測試
- `scripts/shared/` 目錄初建
- `engine.py` 新增 cvmod-003 / cvmod-004 / cvmod-005 seed 與 re-enable
- `tests/test_shared_components.py` 測試共用模組

**不納入：**
- E2E 測試
- 前端 Portal 改動
