# 設計：OpenCV 影像處理工具

## 架構概覽

工具以單一 Python 檔案 `opencv_tool.py` 實作，
遵循現有 `sample_csv_tool.py` 的慣例，
透過 `CIM_SELECTED_PATHS_FILE` 環境變數讀取 host 選擇的圖片路徑。

```text
portal (Mode 1)
  → 使用者點選 "Start Tool" 選擇 opencv-tool
  → Electron 呼叫 /tools/opencv-tool/start
  → sidecar 啟動 Streamlit subprocess
  → iframe 載入 Streamlit UI
    ├── 影像來源選擇（預設 / host 路徑 / 上傳）
    ├── 處理功能選擇（下拉選單）
    ├── 功能參數控制（滑桿 / 選項）
    └── 並排顯示：原圖 | 處理後影像
```

## 影像來源優先順序

1. host 透過 Electron 選檔後同步到 `CIM_SELECTED_PATHS_FILE` 的圖片路徑（最高優先）
2. Streamlit file uploader 直接上傳
3. 預設內建影像 `road.png`（與工具同目錄）

## 支援的 OpenCV 功能

| 功能 | 函式 | 可調參數 |
|------|------|----------|
| 灰階轉換 | `cv2.cvtColor` | — |
| 高斯模糊 | `cv2.GaussianBlur` | kernel size (1–31 奇數), sigma (0–10) |
| Canny 邊緣偵測 | `cv2.Canny` | threshold1 (0–255), threshold2 (0–255) |
| 二值化 | `cv2.threshold` | 閾值 (0–255), 模式 (Binary / Otsu) |
| 侵蝕 | `cv2.erode` | kernel size (1–21), 迭代次數 (1–5) |
| 膨脹 | `cv2.dilate` | kernel size (1–21), 迭代次數 (1–5) |
| 銳化 | `cv2.filter2D` | 強度 (0.5–3.0) |
| Sobel 邊緣 | `cv2.Sobel` | 方向 (X / Y / 合併), kernel size (1–7 奇數) |
| 直方圖均衡化 | `cv2.equalizeHist` | — |
| 輪廓偵測 | `cv2.findContours` | 模式 (外輪廓 / 所有輪廓), 最小面積 (0–1000) |

## UI 佈局

```
┌─ Sidebar ─────────────────────────────────────────┐
│  影像來源                                           │
│  ├── [預設 road.png]                               │
│  ├── [Host 選擇路徑]（有時才出現）                  │
│  └── [上傳圖片]                                    │
│                                                    │
│  處理功能  [下拉選單]                               │
│  參數控制  [動態滑桿/選項，依功能顯示]               │
└────────────────────────────────────────────────────┘

┌─ 主畫面 ──────────────────────────────────────────┐
│  ℹ️ 尺寸 WxH  |  ⏱ 處理耗時 Xms                  │
│                                                    │
│  原始影像              處理後影像                   │
│  [image]               [image]                     │
└────────────────────────────────────────────────────┘
```

## 工具登錄

在 `engine.py` `SQLiteToolAdapter._initialize()` 的 seed 中新增：

```sql
INSERT OR IGNORE INTO tools (tool_id, name, script_relative_path, version,
    signature, source_commit, author, approved_at, enabled)
VALUES ('opencv-tool', 'OpenCV 影像處理', 'opencv_tool.py', '0.1.0',
    NULL, 'seed', 'system', NULL, 1)
```

## 模組結構

`opencv_tool.py` 拆分為純函式（可測試）與 Streamlit UI 層：

```python
# 純函式（無 streamlit 依賴，可單元測試）
def apply_gaussian_blur(image, kernel_size, sigma) -> np.ndarray
def apply_canny(image, threshold1, threshold2) -> np.ndarray
def apply_threshold(image, value, mode) -> np.ndarray
def apply_erosion(image, kernel_size, iterations) -> np.ndarray
def apply_dilation(image, kernel_size, iterations) -> np.ndarray
def apply_sharpen(image, intensity) -> np.ndarray
def apply_sobel(image, direction, ksize) -> np.ndarray
def apply_equalize_hist(image) -> np.ndarray
def apply_contour(image, mode, min_area) -> np.ndarray
def apply_grayscale(image) -> np.ndarray

# Streamlit UI（主流程）
def load_image(source) -> np.ndarray
def render_sidebar() -> tuple[str, dict]
def main()
```

## 測試策略

針對純函式撰寫 pytest 單元測試：

- 輸入：合成的小尺寸 numpy array（避免依賴檔案系統）
- 驗證：輸出形狀、dtype、數值範圍合理性
- 不測試 Streamlit UI 層（需要 runtime 環境）
