from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter1d

FILL_COLORS: dict[str, tuple[int, int, int]] = {
    "藍色": (40, 80, 160),
    "紅色": (180, 40, 40),
    "綠色": (40, 150, 80),
    "黑色": (30, 30, 30),
    "橙色": (200, 100, 30),
    "紫色": (120, 60, 180),
}
BG_COLORS: dict[str, tuple[int, int, int]] = {
    "白色": (255, 255, 255),
    "淺灰": (220, 220, 220),
    "深色": (30, 30, 35),
}
DEFAULT_FILL = (40, 80, 160)
DEFAULT_BG = (255, 255, 255)
FIT_MAX_GAP_PX = 20


def _smooth_offsets(
    rng: np.random.Generator,
    roughness: int,
    frequency: int,
    height: int,
    max_indent: int,
    *,
    bidirectional: bool = False,
) -> np.ndarray:
    """Per-row offset, tapered to 0 at top & bottom edges.

    max_indent sets the amplitude ceiling (from intensity slider).
    roughness (0-80) scales how much of that ceiling is used.
    bidirectional=True allows negative values (both inward and outward);
    bidirectional=False clips to [0, max_indent] (inward only).
    """
    noise = rng.standard_normal(height)
    sigma = max(height / (frequency * 2.0), 0.5)
    smoothed = gaussian_filter1d(noise, sigma=sigma)
    norm = smoothed / (np.max(np.abs(smoothed)) + 1e-9)   # [-1, 1]
    window = np.sin(np.linspace(0, np.pi, height))
    amplitude = max_indent * (roughness / 80.0)
    raw = norm * window * amplitude
    if bidirectional:
        return np.clip(raw.astype(int), -max_indent, max_indent)
    return np.clip(raw.astype(int), 0, max_indent)


def _gradient_dir_variance(offsets: np.ndarray) -> float:
    """Circular variance [0, 1] of edge normal directions from a 1D offset profile.

    Derived from consecutive differences: Δoffset defines the edge tangent, so
    the normal direction angle = atan2(-Δoffset, 1).
    0 = perfectly consistent (smooth), 1 = maximally random (rough).
    """
    if len(offsets) < 4:
        return 0.0
    diffs = np.diff(offsets.astype(float))
    angles = np.arctan2(-diffs, 1.0)
    # Double-angle trick handles 180° periodicity of edge normals
    sin_m = np.mean(np.sin(2.0 * angles))
    cos_m = np.mean(np.cos(2.0 * angles))
    R = np.hypot(sin_m, cos_m)
    return round(float(1.0 - R), 4)


def _psd_energy_ratio(offsets: np.ndarray) -> float:
    """Fraction of PSD energy in the upper half of the frequency band (post-detrend).

    0 = energy concentrated in low frequencies (smooth / long-wave undulation).
    1 = energy spread into high frequencies (random / fine-grained roughness).
    """
    arr = offsets.astype(float)
    n = len(arr)
    if n < 8:
        return 0.0
    trend = np.polyval(np.polyfit(np.arange(n), arr, 1), np.arange(n))
    psd = np.abs(np.fft.rfft(arr - trend)) ** 2
    psd_no_dc = psd[1:]
    total = float(psd_no_dc.sum())
    if total == 0.0:
        return 0.0
    mid = len(psd_no_dc) // 2
    return round(float(psd_no_dc[mid:].sum() / total), 4)


def _generate_fit_image(params: dict) -> dict:
    """藍框貼合測試圖生成：灰色背景 + 鋸齒黑色邊緣 + 藍色矩形框。

    黑色區塊從圖像左右邊緣往內延伸，內側邊緣具有可控鋸齒感。
    fit_offset_score = -1.0 → 內縮極不重合；0.0 → 完美重合；1.0 → 外突極不重合。
    offset > 0 → 突出（黑邊壓住藍框）；offset < 0 → 內縮（灰色縫隙可見）
    """
    width: int        = int(params.get("width",  400))
    height: int       = int(params.get("height", 250))
    frame_margin: int = int(params.get("frame_margin", 50))   # 藍框距圖像邊緣的距離
    frame_thickness: int = int(params.get("frame_thickness", 3))
    if "fit_offset_score" in params:
        fit_offset_score = max(-1.0, min(1.0, float(params.get("fit_offset_score", 0.0))))
    else:
        # Backward compatibility for the previous 0..1 target + direction contract.
        fit_target = max(0.0, min(1.0, float(params.get("fit_target", 1.0))))
        fit_gap_px = int(round((1.0 - fit_target) * FIT_MAX_GAP_PX))
        fit_direction = str(params.get("fit_direction", "內縮"))
        fit_offset_score = (1.0 if fit_direction == "外突" else -1.0) * (fit_gap_px / FIT_MAX_GAP_PX)
    default_offset = int(round(fit_offset_score * FIT_MAX_GAP_PX))
    fit_gap_px = abs(default_offset)
    fit_direction = "內縮" if default_offset < 0 else ("外突" if default_offset > 0 else "重合")
    left_offset: int = int(params.get("left_offset", default_offset))
    right_offset: int = int(params.get("right_offset", default_offset))
    roughness: int       = int(params.get("roughness",       15))
    right_roughness: int = int(params.get("right_roughness", roughness))
    frequency: int       = int(params.get("frequency",        5))
    intensity: int       = int(params.get("intensity",       20))
    seed: int            = int(params.get("seed", 0))

    GRAY  = (120, 120, 120)
    BLACK = (0,   0,   0)
    BLUE  = (0, 100, 220)   # RGB

    # 藍框的固定位置
    fx1 = frame_margin                  # 左邊外緣
    fx2 = width - frame_margin - 1     # 右邊外緣
    fy1 = max(frame_thickness, 10)
    fy2 = height - max(frame_thickness, 10) - 1

    # 鋸齒振幅跟 signed 貼合偏移一起縮放，確保 0.0 產生真正重合的直線邊緣。
    max_jagged = int(round(frame_margin * intensity / 100 * abs(fit_offset_score)))

    rng = np.random.default_rng(seed)
    left_jagged  = _smooth_offsets(rng, roughness,       frequency, height, max_jagged, bidirectional=True)
    right_jagged = _smooth_offsets(rng, right_roughness, frequency, height, max_jagged, bidirectional=True)

    # 灰色背景
    arr = np.full((height, width, 3), GRAY, dtype=np.uint8)

    # 黑色邊緣（先畫，後面再疊藍框）
    # 左側：從 x=0 填到 (fx1 - 1 + left_offset + jagged[y])
    # 右側：從 (fx2 + 1 - right_offset - jagged[y]) 填到 x=width-1
    # offset > 0 → 突出（黑邊壓住藍框）；offset < 0 → 內縮（灰色縫隙）
    for y in range(height):
        left_end  = fx1 - 1 + left_offset  + int(left_jagged[y])
        right_beg = fx2 + 1 - right_offset - int(right_jagged[y])
        if left_end >= 0:
            arr[y, :min(left_end + 1, width)] = BLACK
        if right_beg < width:
            arr[y, max(right_beg, 0):]        = BLACK

    # 藍框（疊在黑色之上）
    img = Image.fromarray(arr, mode="RGB")
    ImageDraw.Draw(img).rectangle(
        [(fx1, fy1), (fx2, fy2)], outline=BLUE, width=frame_thickness
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")

    return {
        "mode":            "藍框貼合測試",
        "image_b64":       base64.b64encode(buf.getvalue()).decode("ascii"),
        "width":           width,
        "height":          height,
        "frame_margin":    frame_margin,
        "frame_thickness": frame_thickness,
        "left_offset":     left_offset,
        "right_offset":    right_offset,
        "fit_offset_score": fit_offset_score,
        "fit_target":      round(1.0 - abs(fit_offset_score), 4),
        "fit_gap_px":      fit_gap_px,
        "fit_direction":   fit_direction,
        "roughness":       roughness,
        "right_roughness": right_roughness,
        "frequency":       frequency,
        "intensity":       intensity,
        "seed":            seed,
    }


def execute_logic(params: dict) -> dict:
    if params.get("mode") == "藍框貼合測試":
        return _generate_fit_image(params)

    width: int = int(params.get("width", 400))
    height: int = int(params.get("height", 250))
    left_roughness: int = int(params.get("left_roughness", 15))
    right_roughness: int = int(params.get("right_roughness", 15))
    frequency: int = int(params.get("frequency", 5))
    symmetry: bool = bool(params.get("symmetry", False))
    fill_name: str = str(params.get("fill_color", "黑色"))
    bg_name: str = str(params.get("bg_color", "白色"))
    seed: int = int(params.get("seed", 0))

    intensity: int = int(params.get("intensity", 33))
    fill = FILL_COLORS.get(fill_name, DEFAULT_FILL)
    bg = BG_COLORS.get(bg_name, DEFAULT_BG)
    max_indent = max(1, int(width * intensity / 100))

    rng = np.random.default_rng(seed)
    arr = np.full((height, width, 3), bg, dtype=np.uint8)

    left_offsets = _smooth_offsets(rng, left_roughness, frequency, height, max_indent)
    if symmetry:
        right_offsets = left_offsets.copy()
    else:
        right_offsets = _smooth_offsets(rng, right_roughness, frequency, height, max_indent)

    for y in range(height):
        x_left = int(left_offsets[y])
        x_right = width - 1 - int(right_offsets[y])
        if x_left <= x_right:
            arr[y, x_left : x_right + 1] = fill

    img = Image.fromarray(arr, mode="RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    image_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    # ── Edge quality metrics ──────────────────────────────────────────────────
    left_gdv  = _gradient_dir_variance(left_offsets)
    right_gdv = _gradient_dir_variance(right_offsets)
    gradient_dir_variance = round((left_gdv + right_gdv) / 2, 4)

    left_psd  = _psd_energy_ratio(left_offsets)
    right_psd = _psd_energy_ratio(right_offsets)
    psd_energy_ratio = round((left_psd + right_psd) / 2, 4)

    return {
        "mode":                 "不規則邊框",
        "image_b64":            image_b64,
        "width":                width,
        "height":               height,
        "left_roughness":       left_roughness,
        "right_roughness":      right_roughness,
        "frequency":            frequency,
        "intensity":            intensity,
        "symmetry":             symmetry,
        "fill_color":           fill_name,
        "bg_color":             bg_name,
        "seed":                 seed,
        "gradient_dir_variance": gradient_dir_variance,
        "psd_energy_ratio":     psd_energy_ratio,
    }
