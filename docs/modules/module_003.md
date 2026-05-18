# Module 003：不規則邊框產生器

## 概要

| 項目 | 值 |
|---|---|
| **plugin_id** | `module_003` |
| **用途** | 以參數化方式產生左右邊緣不規則的合成影像，作為 module_004 的輸入素材，同時輸出邊緣品質量化指標 |

---

## Input 層（003_input.py）

| 參數 | 類型 | 範圍 | 說明 |
|---|---|---|---|
| `width` | int | 100-800 | 影像寬度（px）|
| `height` | int | 100-600 | 影像高度（px）|
| `left_roughness` | int | 0-80 | 左邊粗糙度 |
| `right_roughness` | int | 0-80 | 右邊粗糙度（對稱模式時等於左邊）|
| `symmetry` | bool | — | 勾選後右邊鏡射左邊 |
| `frequency` | int | 1-200 | 凹凸頻率 |
| `intensity` | int | 1-49 | 縮進強度 % |
| `fill_color` | str | 藍/紅/綠/黑/橙/紫 | 填充色 |
| `bg_color` | str | 白色/淺灰/深色 | 背景色 |
| `seed` | int | 0-99 | 隨機種子 |

---

## Process 層（003_process.py）

### 核心演算法

1. 以 `np.random.default_rng(seed)` 建立可重現的隨機數生成器
2. 對每側邊緣呼叫 `_smooth_offsets()`：正態噪音 → Gaussian 平滑 → sin 窗函數 → 振幅乘以 roughness
3. 逐列繪製：從 `x_left` 到 `x_right` 填入填充色

### 邊緣品質指標

| 指標 | 含義 |
|---|---|
| `gradient_dir_variance` | 邊緣法線方向圓形變異數，0=光滑，1=極不規則 |
| `psd_energy_ratio` | 去線性趨勢後 FFT 高頻能量佔比 |

### execute_logic 回傳格式

```python
{
    "image_b64": str,             # PNG 影像的 Base64 編碼
    "width": int, "height": int,
    "left_roughness": int, "right_roughness": int,
    "frequency": int, "intensity": int,
    "symmetry": bool, "fill_color": str, "bg_color": str, "seed": int,
    "gradient_dir_variance": float,
    "psd_energy_ratio": float
}
```

---

## Output 層（003_output.py）

- `st.caption` 顯示完整參數摘要與兩項品質指標
- `st.image` 直接從 Base64 bytes 顯示
- `st.download_button` 下載 PNG，檔名格式：`shape_r{left}-{right}_f{freq}_s{seed}.png`
