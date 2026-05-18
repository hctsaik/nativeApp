# 設計：CV 邊緣模組套件（cv-edge-modules）

## 目錄架構

```
sidecar/python-engine/
├── scripts/
│   ├── shared/                          # ★ 新增：共用 UI 元件
│   │   ├── __init__.py
│   │   ├── ui_components.py             # 日期選擇、Parts 輸入、toast、下載按鈕
│   │   └── image_widget.py             # 縮圖 + hover + lightbox + 下載
│   ├── module_003/                      # 不規則邊框產生器
│   │   ├── __init__.py
│   │   ├── 003_input.py
│   │   ├── 003_process.py
│   │   ├── 003_output.py
│   │   └── 003_process_test.py
│   ├── module_004/                      # 邊緣完整度偵測
│   │   ├── __init__.py
│   │   ├── 004_input.py
│   │   ├── 004_process.py
│   │   ├── 004_output.py
│   │   └── 004_process_test.py
│   └── module_005/                      # 邊緣記錄查詢
│       ├── __init__.py
│       ├── 005_input.py
│       ├── 005_process.py
│       ├── 005_output.py
│       └── 005_process_test.py
└── tests/
    └── test_shared_components.py        # ★ 新增：共用模組測試
```

---

## module_003 — 不規則邊框產生器

### 介面契約

**Input 參數（`render_input() -> dict`）**

| 參數 | 型別 | 範圍/預設 | 說明 |
|------|------|-----------|------|
| width | int | 50–800, 預設 400 | 影像寬度（px） |
| height | int | 50–600, 預設 300 | 影像高度（px） |
| left_roughness | int | 0–80, 預設 20 | 左側粗糙度 |
| right_roughness | int | 0–80, 預設 20 | 右側粗糙度 |
| frequency | int | 1–200, 預設 30 | 紋理頻率 |
| intensity | int | 1–49, 預設 15 | 強度（% of width） |
| fit_offset_score | float | -1.00–1.00, 預設 0.00 | 貼合偏移；-1.00 = 內縮極不重合，0.00 = 完美重合，1.00 = 外突極不重合 |
| fit_gap_px | int | 0–20 | 由 `fit_offset_score` 換算出的偏差量，`abs(round(fit_offset_score * 20))` |
| fit_direction | str | 內縮 / 重合 / 外突 | 由 `fit_offset_score` 正負決定 |
| symmetric | bool | 預設 False | 是否左右對稱 |
| fill_color | color | 預設 #ffffff | 填色 |
| bg_color | color | 預設 #000000 | 背景色 |
| seed | int | 0–9999, 預設 42 | 隨機種子 |
| memo | str | — | 備註 |

**Process 輸出（`execute_logic(params) -> dict`）**

```python
{
    "image_b64":             str,    # base64 PNG
    "width":                 int,
    "height":                int,
    "memo":                  str,
    "fit_offset_score":      float | None,
    "fit_target":            float | None,  # 舊版相容：1 - abs(fit_offset_score)
    "fit_gap_px":            int | None,
    "fit_direction":         str | None,
    "gradient_dir_variance": float,  # 梯度方向圓形變異 [0, 1]
    "psd_energy_ratio":      float,  # PSD 高頻能量比 [0, 1]
}
```

**Output**：顯示生成的影像，含尺寸、備註與兩個新指標的 caption。

---

## module_004 — 邊緣完整度偵測

### 介面契約

**Input 參數**

| 參數 | 型別 | 說明 |
|------|------|------|
| uploaded_file | UploadedFile \| None | 上傳影像 |
| parts | str | Parts 編號 |

**Process 輸出**

```python
# 成功路徑
{
    "image_b64":             str,    # base64 PNG（Canny 結果）
    "image_name":            str,    # 原始檔名
    "image_width":           int,
    "image_height":          int,
    "left_roughness":        float,
    "right_roughness":       float,
    "frequency":             float,
    "intensity":             float,
    "timestamp":             str,    # ISO 8601
    "parts":                 str,
    "gradient_dir_variance": float,  # 梯度方向圓形變異 [0, 1]
    "psd_energy_ratio":      float,  # PSD 高頻能量比 [0, 1]
    "fit_overall":           float | None,  # 重合度 [0, 1]
    "fit_offset_score":      float | None,  # -1=內縮, 0=重合, 1=外突
    "fit_left":              float | None,
    "fit_right":             float | None,
    "fit_avg_dist":          float | None,  # 平均絕對偏差 px
    "fit_avg_signed_dist":   float | None,  # 正=內縮，負=突出
    "fit_left_signed_dist":  float | None,
    "fit_right_signed_dist": float | None,
}
# 無影像路徑（所有數值欄位填 0.0）
{
    "error":                 "no_image",
    "gradient_dir_variance": 0.0,
    "psd_energy_ratio":      0.0,
}
```

**Output**：
- 顯示量測結果表格（含梯度方向變異、PSD 高頻能量比）
- 「儲存 SQLite」按鈕 → 成功時 `st.toast("儲存成功！", icon=":material/check_circle:")`
- SQLite 寫入 `$CIM_LOG_DIR/edge_records.sqlite`

### SQLite 結構

```sql
CREATE TABLE IF NOT EXISTS edge_records (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    parts                 TEXT,
    image_name            TEXT,
    image_blob            BLOB,
    left_roughness        REAL,
    right_roughness       REAL,
    frequency             REAL,
    intensity             REAL,
    image_width           INTEGER,
    image_height          INTEGER,
    timestamp             TEXT,
    gradient_dir_variance REAL,   -- 梯度方向變異 [0, 1]
    psd_energy_ratio      REAL,   -- PSD 高頻能量比 [0, 1]
    fit_overall           REAL,   -- 重合度 [0, 1]
    fit_offset_score      REAL,   -- -1=內縮, 0=重合, 1=外突
    fit_left              REAL,
    fit_right             REAL,
    fit_avg_dist          REAL,   -- 平均絕對偏差 px
    fit_avg_signed_dist   REAL,   -- 正=內縮，負=突出
    fit_left_signed_dist  REAL,
    fit_right_signed_dist REAL
);
```

**DB 遷移**：使用 `PRAGMA table_info` 確認欄位存在，不存在則 `ALTER TABLE ADD COLUMN`。所有欄位均可為 NULL（舊資料相容）。

---

## module_005 — 邊緣記錄查詢

### 介面契約

**Input 參數**

| 參數 | 型別 | 預設 | 說明 |
|------|------|------|------|
| date_from | str | 三個月前 | ISO 日期 |
| date_to | str | 今日 | ISO 日期 |

**Process 輸出**

```python
# 成功路徑
{
    "records": [
        {
            "id": int, "parts": str, "image_name": str,
            "image_b64": str,           # base64，從 BLOB 轉換
            "left_roughness": float, "right_roughness": float,
            "frequency": float, "intensity": float,
            "fit_overall": float | None,
            "fit_offset_score": float | None,
            "fit_avg_dist": float | None,
            "fit_left_signed_dist": float | None,
            "fit_right_signed_dist": float | None,
            "image_width": int, "image_height": int,
            "timestamp": str,
        },
        ...
    ],
    "date_from": str,
    "date_to": str,
}
# 錯誤路徑
{"error": "no_date"}   # 未選日期
{"error": "no_db"}     # DB 檔案不存在
```

**Output**：
- 表格顯示所有欄位（無影像 cell）
- 點擊「影像檔名」欄 → `@st.dialog("影像預覽", width="large")` 放大預覽
- 每列有獨立「🖼️」下載按鈕

---

## scripts/shared/ — 共用元件設計

### ui_components.py

純 Python 可測函式 + Streamlit 包裝：

| 函式 | 回傳 | 說明 |
|------|------|------|
| `three_months_ago(ref?)` | `date` | 純日期計算，無 Streamlit 呼叫 |
| `date_input_single(label, default, key)` | `date` | 單日期選擇器 |
| `date_input_range(key_from, key_to, default_from, default_to)` | `tuple[date, date]` | 雙欄 From/To 選擇器，From > To 顯示警告 |
| `parts_input(key, placeholder)` | `str` | Parts 輸入欄（label + field 一列） |
| `save_success_toast(message?)` | `None` | `st.toast(icon="✅")` |
| `save_error_toast(message?)` | `None` | `st.toast(icon="❌")` |
| `download_image_button(bytes, filename, label, key)` | `None` | `st.download_button` |

**重要**：`three_months_ago` 不得呼叫 `st.*`，供測試直接驗證。

### image_widget.py

```
render_image_preview(image_bytes, filename, thumb_width, key) -> None
```

架構：
1. 注入一次 `_LIGHTBOX_SETUP`（零高度 iframe → `window.parent` DOM 操作）
2. 內嵌 iframe（`_IFRAME_H ≈ 220px`）包含：
   - 縮圖（`_THUMB_H = 72px`）
   - hover 時顯示 preview（`_PREVIEW_H = 110px`，`visibility: hidden` 保留空間）
   - `<a download>` 下載按鈕（Electron 相容）
3. 點擊縮圖 → `window.parent.postMessage({type:'cim:open', src:'data:image/png;base64,...'}, '*')` 觸發 lightbox

**Lightbox**（`#cim-lb`）：
- Fixed 覆蓋全畫面，`z-index: 2147483647`
- `P.__cimLbReady` 旗標防止重複注入
- 點擊任意處關閉

---

## 邊緣品質指標演算法

### 梯度方向變異（gradient_dir_variance）

**目標**：量測邊緣法向量方向的一致性。值越大代表邊緣方向越不規則。

**計算流程（module_004，真實影像）**：
1. 對灰階影像計算 Sobel Gx、Gy（kernel size=3）
2. 取 Canny 邊緣遮罩上的所有像素，計算 `angles = arctan2(Gy, Gx)`
3. 使用 **雙角度技巧**（double-angle trick）處理 180° 週期性：
   - `sin_mean = mean(sin(2θ))`，`cos_mean = mean(cos(2θ))`
   - 合力向量長度 `R = √(sin_mean² + cos_mean²)` ∈ [0, 1]
4. `gradient_dir_variance = 1 − R`（0 = 方向完全一致，1 = 完全隨機）

**計算流程（module_003，合成影像）**：
從 offset 陣列直接計算（無需 Canny）：
1. `diffs = diff(offsets)` — 每列的邊緣位移量
2. 法向量角度 `angles = arctan2(-diffs, 1.0)`
3. 同上雙角度技巧

**注意**：GDV 是對整幅影像所有邊緣方向計算，受邊緣形狀影響。對含四個方向的封閉矩形，GDV 本身就偏高；適合同類型物件間相互比較，而非絕對值判斷。

---

### PSD 高頻能量比（psd_energy_ratio）

**目標**：量測邊緣輪廓的頻率組成。低頻能量主導代表平滑長波起伏；高頻能量主導代表細密鋸齒或隨機粗糙。

**計算流程**：
1. 取左/右邊緣的逐列 x 座標序列（1D profile）
2. 去趨勢（detrend）：用一階多項式擬合後相減，消除整體斜度
3. rfft → 功率頻譜 `PSD[k] = |FFT[k]|²`
4. 排除 DC（k=0）
5. `psd_energy_ratio = Σ PSD[k > N/2] / Σ PSD[k > 0]`
   - 分子：上半頻段（高頻）能量
   - 分母：全頻段能量
6. 左右各算一次，取平均

**值域**：0.0（能量集中在低頻，平滑）→ 1.0（能量散佈到高頻，粗糙）

---

### 貼合偏移（fit_offset_score）與重合度（fit_overall）

**目標**：用單一 signed 指標表達偏差方向，並保留 0～1 重合度作為品質分數。

**產生流程（module_003，藍框貼合測試）**：
1. User 選 `fit_offset_score`，範圍 -1.00～1.00。
2. `offset_px = round(fit_offset_score * 20)`。
3. `offset_px < 0` 表示黑邊內縮，`offset_px = 0` 表示黑邊與藍框邊緣重合，`offset_px > 0` 表示黑邊外突。
4. 鋸齒振幅同步乘上 `abs(fit_offset_score)`，因此 `fit_offset_score = 0` 時即使粗糙度/鋸齒深度 slider 很高，也必須產生直線且重合的左右邊緣。
5. `fit_offset_score = 0` 的測試圖應讓黑邊 Canny 與藍框 Canny 在左右邊緣取得 0px 平均偏差。

**偵測流程（module_004）**：
1. 對藍色遮罩與黑色遮罩分別做 Canny。
2. 左右分側逐列找藍框邊緣與黑邊邊緣的位置差。
3. `fit_side = max(0, 1 - mean(abs(distance_px)) / 20)`。
4. `fit_overall = mean(fit_left, fit_right)`，代表重合度，1.0 是最佳。
5. 偵測端 signed distance 原始定義為正值內縮、負值外突；輸出 `fit_offset_score = -avg_signed_distance / 20`，轉成與 UI 一致的 -1 內縮、0 重合、1 外突。

---

## engine.py 整合

```python
# INSERT OR IGNORE seed
("cvmod-003", "003 - 不規則邊框產生器", "cv_framework_runner.py", "0.1.0", ...),
("cvmod-004", "004 - 邊緣完整度偵測",   "cv_framework_runner.py", "0.1.0", ...),
("cvmod-005", "005 - 邊緣記錄查詢",     "cv_framework_runner.py", "0.1.0", ...),

# re-enable UPDATE
WHERE tool_id IN ("cv-framework", "cvmod-002", "cvmod-003", "cvmod-004", "cvmod-005")
```

`CIM_MODULE_ID` 環境變數由 `engine.py _make_env()` 注入，格式為 `cvmod-NNN`，
Framework Runner 依此選取模組（去掉 `cvmod-` 前綴後取 3 位數字）。

---

## 資料序列化限制

`execute_logic()` 的回傳值透過 JSON 序列化傳給 `render_output()`：

- **允許**：`str`, `int`, `float`, `bool`, `list`, `dict`, `None`
- **禁止**：`bytes`（改用 `base64.b64encode(...).decode("ascii")`）、`numpy.ndarray`、`datetime`（改用 `str`）

---

## 測試策略

| 目標 | 測試檔 | 方式 |
|------|--------|------|
| module_003 process | `003_process_test.py` | 合成輸入，驗證 image_b64 為合法 base64 PNG |
| module_004 process | `004_process_test.py` | 合成 bytes 模擬上傳，驗證量測值範圍、image_name 帶入 |
| module_005 process | `005_process_test.py` | `monkeypatch.setenv("CIM_LOG_DIR", tmp_path)` 建立測試 DB |
| shared/ui_components | `tests/test_shared_components.py` | 直接測試 `three_months_ago`，不啟動 Streamlit |
| shared/image_widget | `tests/test_shared_components.py` | 確認 module 可載入、常數定義正確 |

---

## 設計決策說明

| 決策 | 選擇 | 理由 |
|------|------|------|
| 影像在表格中的呈現 | 完全移除，改用點擊對話方塊 | iframe 在 Streamlit columns 中高度不一致，破壞格線 |
| 對話方塊實作 | `@st.dialog("...", width="large")` | Streamlit 原生支援，不需自製 overlay |
| 全畫面放大 | iframe → `postMessage` → parent DOM lightbox | `window.open("data:...")` 在 Chromium/Electron 中被封鎖 |
| 下載按鈕 | `<a download>` in iframe | `st.download_button` 在 iframe 行列中造成排版不一致 |
| DB 路徑 | `_db_path()` 函式（呼叫時解析） | import 時就解析會讓 `monkeypatch.setenv` 無效 |
| 成功通知 | `st.toast(icon="✅")` | `st.success()` 佔據頁面空間；icon 欄位已有符號，message 不需再加 emoji |
