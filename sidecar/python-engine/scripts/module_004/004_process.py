from __future__ import annotations

import base64
from datetime import datetime
import sys
from pathlib import Path

import cv2
import numpy as np

try:
    _SCRIPTS_DIR = Path(__file__).resolve().parent.parent
    if str(_SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(_SCRIPTS_DIR))
    from frame_fit_score import compute_fit_score as _compute_fit_score
    _FIT_SCORE_AVAILABLE = True
except ImportError:
    _FIT_SCORE_AVAILABLE = False


def _edge_metrics(edge_positions: list[int]) -> tuple[float, float]:
    """Return (roughness_std, frequency_dominant) for a sequence of edge x-positions."""
    if len(edge_positions) < 4:
        return 0.0, 0.0
    arr = np.array(edge_positions, dtype=float)
    roughness = round(float(np.std(arr)), 2)
    deviation = arr - arr.mean()
    fft_mag = np.abs(np.fft.rfft(deviation))
    dominant_idx = int(np.argmax(fft_mag[1:]) + 1)
    frequency = round(float(dominant_idx / len(arr) * 100), 2)
    return roughness, frequency


def _gradient_dir_variance(gray: np.ndarray, edge_mask: np.ndarray) -> float:
    """Circular variance [0, 1] of gradient directions at edge pixels.

    Uses the double-angle trick to handle the 180° periodicity of edge normals.
    0 = all normals point the same way (smooth straight edge).
    1 = normals point in random directions (jagged / irregular edge).
    """
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    angles = np.arctan2(gy[edge_mask > 0], gx[edge_mask > 0])
    if len(angles) < 4:
        return 0.0
    sin_m = np.mean(np.sin(2.0 * angles))
    cos_m = np.mean(np.cos(2.0 * angles))
    R = np.hypot(sin_m, cos_m)
    return round(float(1.0 - R), 4)


def _psd_energy_ratio(edge_positions: list[int]) -> float:
    """Fraction of PSD energy in the upper half of the frequency band (post-detrend).

    0 = smooth / long-wave undulation (low-freq dominant).
    1 = fine-grained / random roughness (high-freq dominant).
    """
    n = len(edge_positions)
    if n < 8:
        return 0.0
    arr = np.array(edge_positions, dtype=float)
    trend = np.polyval(np.polyfit(np.arange(n), arr, 1), np.arange(n))
    psd = np.abs(np.fft.rfft(arr - trend)) ** 2
    psd_no_dc = psd[1:]
    total = float(psd_no_dc.sum())
    if total == 0.0:
        return 0.0
    mid = len(psd_no_dc) // 2
    return round(float(psd_no_dc[mid:].sum() / total), 4)


def execute_logic(params: dict) -> dict:
    image_bytes: bytes | None = params.get("image_bytes")
    image_name: str = str(params.get("image_name", ""))
    parts: str = str(params.get("parts", ""))

    if not image_bytes:
        return {
            "error": "no_image",
            "image_name": image_name,
            "image_b64": None,
            "left_roughness": 0.0,
            "right_roughness": 0.0,
            "frequency": 0.0,
            "intensity": 0.0,
            "image_width": 0,
            "image_height": 0,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parts": parts,
            "gradient_dir_variance": 0.0,
            "psd_energy_ratio": 0.0,
            "fit_overall": None,
            "fit_offset_score": None,
            "fit_left": None,
            "fit_right": None,
            "fit_avg_dist": None,
            "fit_avg_signed_dist": None,
            "fit_left_dist": None,
            "fit_right_dist": None,
            "fit_left_signed_dist": None,
            "fit_right_signed_dist": None,
        }

    arr = np.frombuffer(image_bytes, np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    img = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = img.shape

    edges = cv2.Canny(img, 50, 150)

    left_positions: list[int] = []
    right_positions: list[int] = []
    for y in range(h):
        nonzero = np.where(edges[y] > 0)[0]
        if len(nonzero) >= 2:
            left_positions.append(int(nonzero[0]))
            right_positions.append(int(nonzero[-1]))

    left_rough, left_freq = _edge_metrics(left_positions)
    right_rough, right_freq = _edge_metrics(right_positions)
    frequency = round((left_freq + right_freq) / 2, 2)

    all_positions = left_positions + right_positions
    if all_positions:
        arr_all = np.array(all_positions, dtype=float)
        intensity = round(float(np.max(np.abs(arr_all - arr_all.mean()))), 2)
    else:
        intensity = 0.0

    # ── Edge quality metrics ──────────────────────────────────────────────────
    gradient_dir_variance = _gradient_dir_variance(img, edges)

    left_psd  = _psd_energy_ratio(left_positions)
    right_psd = _psd_energy_ratio(right_positions)
    psd_energy_ratio = round((left_psd + right_psd) / 2, 4)

    # ── 藍框貼合度分析 ────────────────────────────────────────────────────────
    fit_overall = fit_offset_score = fit_left = fit_right = None
    fit_avg_dist = fit_avg_signed_dist = None
    fit_left_dist = fit_right_dist = None
    fit_left_signed_dist = fit_right_signed_dist = None
    if params.get("enable_fit_score") and _FIT_SCORE_AVAILABLE:
        try:
            fit = _compute_fit_score(bgr)
            fit_overall = fit["overall"]
            fit_offset_score = fit.get("offset_score")
            fit_left = fit["left"]
            fit_right = fit["right"]
            fit_avg_dist = fit.get("avg_dist_px")
            fit_avg_signed_dist = fit.get("avg_signed_dist_px")
            fit_left_dist = fit["left_dist_px"]
            fit_right_dist = fit["right_dist_px"]
            fit_left_signed_dist = fit.get("left_signed_dist_px")
            fit_right_signed_dist = fit.get("right_signed_dist_px")
        except Exception:
            pass

    return {
        "image_b64":             base64.b64encode(image_bytes).decode("ascii"),
        "image_name":            image_name,
        "left_roughness":        left_rough,
        "right_roughness":       right_rough,
        "frequency":             frequency,
        "intensity":             intensity,
        "image_width":           w,
        "image_height":          h,
        "timestamp":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "parts":                 parts,
        "gradient_dir_variance": gradient_dir_variance,
        "psd_energy_ratio":      psd_energy_ratio,
        "fit_overall":           fit_overall,
        "fit_offset_score":      fit_offset_score,
        "fit_left":              fit_left,
        "fit_right":             fit_right,
        "fit_avg_dist":          fit_avg_dist,
        "fit_avg_signed_dist":   fit_avg_signed_dist,
        "fit_left_dist":         fit_left_dist,
        "fit_right_dist":        fit_right_dist,
        "fit_left_signed_dist":  fit_left_signed_dist,
        "fit_right_signed_dist": fit_right_signed_dist,
    }
