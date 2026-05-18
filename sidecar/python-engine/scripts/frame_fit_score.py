"""
frame_fit_score.py
------------------
量測「黑色邊緣（Canny）」與「藍色框（Canny）」左右兩側的貼合程度。

前提：
  - 背景為灰色，黑色邊緣是純黑色，藍框是明顯藍色
  - 突出（黑壓藍）或內縮（黑離藍）都能偵測
  - 分數 1.0 = 完美重合，0.0 = 超出容忍距離

使用方式：
    python frame_fit_score.py <image_path>
    或 import 後呼叫 compute_fit_score(image)
"""

import sys
import cv2
import numpy as np


# ── 可調參數 ──────────────────────────────────────────────────────────────────

BLUE_HSV_LOWER = np.array([100, 60, 60])
BLUE_HSV_UPPER = np.array([135, 255, 255])
BLACK_LUMA_MAX = 40       # 亮度低於此值視為純黑
CANNY_LOW      = 30
CANNY_HIGH     = 100
MAX_GAP_PX     = 20       # 超過此像素距離分數歸零
ROW_MARGIN     = 0.15     # 忽略頂/底各 15% 的行（避免水平邊緣干擾）


# ── 核心函式 ──────────────────────────────────────────────────────────────────

def _side_score(blue_edges_half: np.ndarray, black_edges_half: np.ndarray,
                side: str) -> tuple[float, float, float]:
    """
    逐列比較黑色邊緣與藍框邊緣的 x 位置差距。

    side='left'  : 比較「黑色最右邊緣 x」vs「藍框最左邊緣 x」
    side='right' : 比較「黑色最左邊緣 x」vs「藍框最右邊緣 x」

    Returns (score 0~1, avg_abs_distance_px, avg_signed_distance_px).
    Signed distance > 0 表示黑邊內縮（有縫隙），< 0 表示黑邊突出（壓住藍框）。
    """
    h = blue_edges_half.shape[0]
    y_lo = int(h * ROW_MARGIN)
    y_hi = int(h * (1 - ROW_MARGIN))

    gaps = []
    for y in range(y_lo, y_hi):
        blue_xs  = np.where(blue_edges_half[y]  > 0)[0]
        black_xs = np.where(black_edges_half[y] > 0)[0]
        if len(blue_xs) == 0 or len(black_xs) == 0:
            continue

        if side == "left":
            # 黑色邊緣最右點 vs 藍框最左點
            gap = int(blue_xs.min()) - int(black_xs.max())
        else:
            # 藍框最右點 vs 黑色邊緣最左點
            gap = int(black_xs.min()) - int(blue_xs.max())

        gaps.append(gap)

    if not gaps:
        return 0.0, float(MAX_GAP_PX), float(MAX_GAP_PX)

    avg_signed_dist = float(np.mean(gaps))
    avg_abs_dist = float(np.mean(np.abs(gaps)))
    score = max(0.0, 1.0 - avg_abs_dist / MAX_GAP_PX)
    return round(score, 4), round(avg_abs_dist, 2), round(avg_signed_dist, 2)


def compute_fit_score(image: np.ndarray) -> dict:
    """
    Parameters
    ----------
    image : np.ndarray  BGR 格式，shape (H, W, 3)

    Returns
    -------
    dict 含 overall / left / right 分數（0.0~1.0）及各邊平均距離（px）
    """
    h, w = image.shape[:2]
    mid_x = w // 2

    # ── 1. 藍框 Canny edges ──────────────────────────────────────────────────
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    blue_mask  = cv2.inRange(hsv, BLUE_HSV_LOWER, BLUE_HSV_UPPER)
    blue_edges = cv2.Canny(blue_mask, CANNY_LOW, CANNY_HIGH)

    # ── 2. 黑色邊緣 Canny edges ──────────────────────────────────────────────
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    black_mask  = np.where(gray < BLACK_LUMA_MAX, 255, 0).astype(np.uint8)
    black_edges = cv2.Canny(black_mask, CANNY_LOW, CANNY_HIGH)

    # ── 3. 左右分側，逐列比較 ────────────────────────────────────────────────
    left_score, left_dist, left_signed_dist = _side_score(
        blue_edges[:, :mid_x], black_edges[:, :mid_x], "left")
    right_score, right_dist, right_signed_dist = _side_score(
        blue_edges[:, mid_x:], black_edges[:, mid_x:], "right")

    overall = round((left_score + right_score) / 2.0, 4)
    avg_abs_dist = round((left_dist + right_dist) / 2.0, 2)
    avg_signed_dist = round((left_signed_dist + right_signed_dist) / 2.0, 2)
    offset_score = round(float(np.clip(-avg_signed_dist / MAX_GAP_PX, -1.0, 1.0)), 4)

    return {
        "overall":             overall,
        "offset_score":        offset_score,
        "left":                left_score,
        "right":               right_score,
        "avg_dist_px":         avg_abs_dist,
        "avg_signed_dist_px":  avg_signed_dist,
        "left_dist_px":        left_dist,
        "right_dist_px":       right_dist,
        "left_signed_dist_px": left_signed_dist,
        "right_signed_dist_px": right_signed_dist,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python frame_fit_score.py <image_path>")
        sys.exit(1)

    path = sys.argv[1]
    img = cv2.imread(path)
    if img is None:
        print(f"無法讀取圖片: {path}")
        sys.exit(1)

    r = compute_fit_score(img)
    print(f"\n=== 藍框貼合度分析 ===")
    print(f"重合度 : {r['overall']:.4f}  (平均偏差: {r['avg_dist_px']} px)")
    print(f"貼合偏移 : {r['offset_score']:.4f}  (-1=內縮, 0=重合, 1=外突)")
    print(f"左邊分數 : {r['left']:.4f}  (偏差: {r['left_signed_dist_px']} px)")
    print(f"右邊分數 : {r['right']:.4f}  (偏差: {r['right_signed_dist_px']} px)")
