# Module 001：OpenCV 影像處理

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_001` |
| **版本** | 1.0.0 |
| **runner** | cv_framework |
| **用途** | 教學 / 驗證用的影像處理沙盒，支援 11 種 OpenCV 操作 |

---

## Input 層（001_input.py）

### 影像來源（三種，優先順序由高至低）

| 來源 | 說明 |
|---|---|
| Host 選擇 | Electron 透過 `CIM_SELECTED_PATHS_FILE` 環境變數傳遞已選擇的本機路徑清單 |
| 上傳圖片 | Streamlit `file_uploader` 支援 png/jpg/jpeg/bmp |
| 預設影像 | `tools/road.png`（當其他來源無法取得影像時自動降級）|

### 功能列表與參數

| 功能名稱 | 額外參數 |
|---|---|
| 原始影像 | 無 |
| 灰階轉換 | 無 |
| 高斯模糊 | `kernel_size`（1-31，奇數）、`sigma`（0.0-10.0）|
| Canny 邊緣偵測 | `threshold1`（0-255）、`threshold2`（0-255）|
| 二值化 | `use_otsu`（bool）、`value`（0-255，Otsu 關閉時）|
| 侵蝕 | `kernel_size`（1-21）、`iterations`（1-5）|
| 膨脹 | `kernel_size`（1-21）、`iterations`（1-5）|
| 銳化 | `intensity`（0.5-3.0）|
| Sobel 邊緣 | `direction`（X/Y/合併）、`ksize`（1/3/5/7）|
| 直方圖均衡化 | 無 |
| 輪廓偵測 | `all_contours`（bool）、`min_area`（0-1000 px）|

### render_input() 回傳格式

```python
{
    "image_bgr": np.ndarray,   # BGR 影像陣列（不序列化，直接傳遞）
    "func_name": str,          # 功能名稱
    "params": dict             # 功能相關參數（可為空 dict）
}
```

---

## Process 層（001_process.py）

### execute_logic 回傳格式

```python
{
    "original_bgr": np.ndarray,  # 原始影像（BGR）
    "result_bgr": np.ndarray,    # 處理後影像（可能為單通道灰階）
    "func_name": str,
    "elapsed_ms": float,         # 處理耗時（毫秒）
    "size": (int, int)           # (width, height)
}
```

---

## Output 層（001_output.py）

- 顯示 `尺寸 × 耗時` 說明文字
- 雙欄並排：左欄「原始影像」/ 右欄「處理後：{func_name}」
- 單通道（灰階）影像自動轉換為 RGB 再傳給 `st.image`
