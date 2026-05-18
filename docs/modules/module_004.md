# Module 004：邊緣完整度偵測

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_004` |
| **用途** | 上傳真實工件影像，以 Canny 邊緣偵測計算邊緣粗糙度指標，並可手動儲存至 SQLite |
| **持久化** | `{CIM_LOG_DIR}/edge_records.sqlite`（table: `edge_records`）|

---

## Input 層（004_input.py）

```python
render_input() → {
    "image_bytes": bytes | None,
    "image_name": str,
    "parts": str
}
```

---

## Process 層（004_process.py）

### 邊緣偵測流程

1. 解碼 `image_bytes` → `cv2.imdecode(arr, GRAYSCALE)`
2. `cv2.Canny(img, 50, 150)` 得到 edge mask
3. 逐列掃描邊緣像素：記錄每列最左（left_positions）與最右（right_positions）的邊緣 x 座標

### 計算指標

| 指標 | 欄位名 | 計算方式 |
|---|---|---|
| 左邊粗糙度 | `left_roughness` | `np.std(left_positions)` |
| 右邊粗糙度 | `right_roughness` | `np.std(right_positions)` |
| 粗糙頻率 | `frequency` | FFT dominant frequency（左右平均）|
| 粗糙強度 | `intensity` | 所有邊緣位置相對均值的最大偏差 |
| 梯度方向變異 | `gradient_dir_variance` | Sobel 梯度圓形方向變異數 |
| PSD 高頻能量比 | `psd_energy_ratio` | 去趨勢後 FFT 高頻佔比 |

---

## Output 層（004_output.py）

### SQLite 結構（edge_records）

```sql
CREATE TABLE IF NOT EXISTS edge_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    left_roughness REAL, right_roughness REAL,
    frequency REAL, intensity REAL,
    image_width INTEGER, image_height INTEGER,
    timestamp TEXT, parts TEXT, image_name TEXT,
    image_blob BLOB,
    gradient_dir_variance REAL, psd_energy_ratio REAL
);
```

- 顯示 `st.table` 展示所有計算指標
- 「儲存此筆記錄至 SQLite」按鈕
- 未上傳影像時顯示 `st.warning`
