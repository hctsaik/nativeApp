from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import streamlit as st

# ---------------------------------------------------------------------------
# 純函式層（無 Streamlit 依賴，可單元測試）
# ---------------------------------------------------------------------------

def apply_grayscale(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return image.copy()
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def apply_gaussian_blur(image: np.ndarray, kernel_size: int, sigma: float) -> np.ndarray:
    k = kernel_size if kernel_size % 2 == 1 else kernel_size + 1
    return cv2.GaussianBlur(image, (k, k), sigma)


def apply_canny(image: np.ndarray, threshold1: int, threshold2: int) -> np.ndarray:
    gray = apply_grayscale(image)
    return cv2.Canny(gray, threshold1, threshold2)


def apply_threshold(image: np.ndarray, value: int, use_otsu: bool) -> np.ndarray:
    gray = apply_grayscale(image)
    if use_otsu:
        _, result = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        _, result = cv2.threshold(gray, value, 255, cv2.THRESH_BINARY)
    return result


def apply_erosion(image: np.ndarray, kernel_size: int, iterations: int) -> np.ndarray:
    k = max(1, kernel_size)
    kernel = np.ones((k, k), np.uint8)
    return cv2.erode(image, kernel, iterations=iterations)


def apply_dilation(image: np.ndarray, kernel_size: int, iterations: int) -> np.ndarray:
    k = max(1, kernel_size)
    kernel = np.ones((k, k), np.uint8)
    return cv2.dilate(image, kernel, iterations=iterations)


def apply_sharpen(image: np.ndarray, intensity: float) -> np.ndarray:
    kernel = np.array([
        [0, -1, 0],
        [-1, 4, -1],
        [0, -1, 0],
    ], dtype=np.float32) * intensity
    kernel[1, 1] += 1
    sharpened = cv2.filter2D(image, -1, kernel)
    return np.clip(sharpened, 0, 255).astype(np.uint8)


def apply_sobel(image: np.ndarray, direction: str, ksize: int) -> np.ndarray:
    gray = apply_grayscale(image)
    k = ksize if ksize % 2 == 1 else ksize + 1
    k = max(1, k)
    if direction == "X":
        result = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=k)
    elif direction == "Y":
        result = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=k)
    else:
        sx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=k)
        sy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=k)
        result = np.hypot(sx, sy)
    result = np.clip(np.abs(result), 0, 255)
    return result.astype(np.uint8)


def apply_equalize_hist(image: np.ndarray) -> np.ndarray:
    gray = apply_grayscale(image)
    return cv2.equalizeHist(gray)


def apply_contour(image: np.ndarray, all_contours: bool, min_area: int) -> np.ndarray:
    gray = apply_grayscale(image)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mode = cv2.RETR_LIST if all_contours else cv2.RETR_EXTERNAL
    contours, _ = cv2.findContours(binary, mode, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= min_area]
    if len(image.shape) == 2:
        canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        canvas = image.copy()
    cv2.drawContours(canvas, contours, -1, (0, 255, 0), 2)
    return canvas


# ---------------------------------------------------------------------------
# 影像來源
# ---------------------------------------------------------------------------

_DEFAULT_IMAGE = Path(__file__).resolve().parent / "road.png"


def _host_image_paths() -> list[str]:
    path_file = os.environ.get("CIM_SELECTED_PATHS_FILE")
    if not path_file:
        return []
    try:
        data = json.loads(Path(path_file).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
    return [p for p in data.get("paths", []) if Path(p).suffix.lower() in exts]


def _load_bgr(path: Path | str) -> Optional[np.ndarray]:
    image = cv2.imread(str(path))
    return image


def _bgr_to_display(image: np.ndarray) -> np.ndarray:
    if len(image.shape) == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2RGB)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGB)


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

FUNCTIONS = [
    "原始影像",
    "灰階轉換",
    "高斯模糊",
    "Canny 邊緣偵測",
    "二值化",
    "侵蝕",
    "膨脹",
    "銳化",
    "Sobel 邊緣",
    "直方圖均衡化",
    "輪廓偵測",
]


def _sidebar_params(func_name: str) -> dict:
    params: dict = {}
    if func_name == "高斯模糊":
        params["kernel_size"] = st.sidebar.slider("Kernel Size（奇數）", 1, 31, 5, step=2)
        params["sigma"] = st.sidebar.slider("Sigma", 0.0, 10.0, 1.0, step=0.1)

    elif func_name == "Canny 邊緣偵測":
        params["threshold1"] = st.sidebar.slider("Threshold 1（低閾值）", 0, 255, 50)
        params["threshold2"] = st.sidebar.slider("Threshold 2（高閾值）", 0, 255, 150)

    elif func_name == "二值化":
        params["use_otsu"] = st.sidebar.checkbox("使用 Otsu 自動閾值", value=False)
        if not params["use_otsu"]:
            params["value"] = st.sidebar.slider("閾值", 0, 255, 127)
        else:
            params["value"] = 0

    elif func_name in ("侵蝕", "膨脹"):
        params["kernel_size"] = st.sidebar.slider("Kernel Size", 1, 21, 3)
        params["iterations"] = st.sidebar.slider("迭代次數", 1, 5, 1)

    elif func_name == "銳化":
        params["intensity"] = st.sidebar.slider("銳化強度", 0.5, 3.0, 1.0, step=0.1)

    elif func_name == "Sobel 邊緣":
        params["direction"] = st.sidebar.selectbox("方向", ["X", "Y", "合併"])
        params["ksize"] = st.sidebar.select_slider("Kernel Size", [1, 3, 5, 7], value=3)

    elif func_name == "輪廓偵測":
        params["all_contours"] = st.sidebar.checkbox("偵測所有輪廓（含內部）", value=False)
        params["min_area"] = st.sidebar.slider("最小輪廓面積（像素）", 0, 1000, 100)

    return params


def _process(image: np.ndarray, func_name: str, params: dict) -> np.ndarray:
    if func_name == "原始影像":
        return image
    if func_name == "灰階轉換":
        return apply_grayscale(image)
    if func_name == "高斯模糊":
        return apply_gaussian_blur(image, params["kernel_size"], params["sigma"])
    if func_name == "Canny 邊緣偵測":
        return apply_canny(image, params["threshold1"], params["threshold2"])
    if func_name == "二值化":
        return apply_threshold(image, params["value"], params["use_otsu"])
    if func_name == "侵蝕":
        return apply_erosion(image, params["kernel_size"], params["iterations"])
    if func_name == "膨脹":
        return apply_dilation(image, params["kernel_size"], params["iterations"])
    if func_name == "銳化":
        return apply_sharpen(image, params["intensity"])
    if func_name == "Sobel 邊緣":
        return apply_sobel(image, params["direction"], params["ksize"])
    if func_name == "直方圖均衡化":
        return apply_equalize_hist(image)
    if func_name == "輪廓偵測":
        return apply_contour(image, params["all_contours"], params["min_area"])
    return image


def main() -> None:
    st.set_page_config(page_title="OpenCV 影像處理", layout="wide")
    st.title("OpenCV 影像處理工具")

    # ── 影像來源選擇 ──────────────────────────────────────────────
    st.sidebar.header("影像來源")
    host_paths = _host_image_paths()

    source_options = ["預設影像（road.png）"]
    if host_paths:
        source_options = [f"Host 選擇：{Path(p).name}" for p in host_paths] + source_options
    source_options.append("上傳圖片")

    source_choice = st.sidebar.selectbox("選擇來源", source_options)

    image_bgr: Optional[np.ndarray] = None

    if source_choice.startswith("Host 選擇："):
        idx = [f"Host 選擇：{Path(p).name}" for p in host_paths].index(source_choice)
        image_bgr = _load_bgr(host_paths[idx])
        if image_bgr is None:
            st.sidebar.error("無法讀取 Host 選擇的圖片")

    elif source_choice == "上傳圖片":
        uploaded = st.sidebar.file_uploader("選擇圖片", type=["png", "jpg", "jpeg", "bmp"])
        if uploaded is not None:
            file_bytes = np.frombuffer(uploaded.read(), np.uint8)
            image_bgr = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)

    if image_bgr is None:
        image_bgr = _load_bgr(_DEFAULT_IMAGE)

    if image_bgr is None:
        st.error("無法載入影像，請確認 road.png 存在於工具目錄。")
        st.stop()

    # ── 功能選擇與參數 ────────────────────────────────────────────
    st.sidebar.divider()
    st.sidebar.header("處理功能")
    func_name = st.sidebar.selectbox("選擇功能", FUNCTIONS)
    params = _sidebar_params(func_name)

    # ── 處理 ─────────────────────────────────────────────────────
    t0 = time.perf_counter()
    result = _process(image_bgr, func_name, params)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    h, w = image_bgr.shape[:2]
    st.caption(f"尺寸：{w} × {h} 像素　｜　處理耗時：{elapsed_ms:.1f} ms")

    # ── 並排顯示 ──────────────────────────────────────────────────
    col_left, col_right = st.columns(2)
    with col_left:
        st.subheader("原始影像")
        st.image(_bgr_to_display(image_bgr), use_container_width=True)
    with col_right:
        st.subheader(f"處理後：{func_name}")
        st.image(_bgr_to_display(result), use_container_width=True)


if __name__ == "__main__":
    main()
