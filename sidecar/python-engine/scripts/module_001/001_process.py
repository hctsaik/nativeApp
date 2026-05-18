from __future__ import annotations

import time

import cv2
import numpy as np


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
    return np.clip(np.abs(result), 0, 255).astype(np.uint8)


def apply_equalize_hist(image: np.ndarray) -> np.ndarray:
    gray = apply_grayscale(image)
    return cv2.equalizeHist(gray)


def apply_contour(image: np.ndarray, all_contours: bool, min_area: int) -> np.ndarray:
    gray = apply_grayscale(image)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    mode = cv2.RETR_LIST if all_contours else cv2.RETR_EXTERNAL
    contours, _ = cv2.findContours(binary, mode, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= min_area]
    canvas = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if len(image.shape) == 2 else image.copy()
    cv2.drawContours(canvas, contours, -1, (0, 255, 0), 2)
    return canvas


def execute_logic(params: dict) -> dict:
    """
    Run opencv processing on the image described by params.

    params keys:
        image_bgr  : np.ndarray  (BGR)
        func_name  : str
        params     : dict        (function-specific parameters)

    Returns result dict with:
        original_bgr  : np.ndarray
        result_bgr    : np.ndarray  (may be single-channel; caller converts for display)
        func_name     : str
        elapsed_ms    : float
        size          : (width, height)
    """
    image: np.ndarray = params["image_bgr"]
    func_name: str = params["func_name"]
    p: dict = params.get("params", {})

    t0 = time.perf_counter()

    if func_name == "原始影像":
        result = image
    elif func_name == "灰階轉換":
        result = apply_grayscale(image)
    elif func_name == "高斯模糊":
        result = apply_gaussian_blur(image, p["kernel_size"], p["sigma"])
    elif func_name == "Canny 邊緣偵測":
        result = apply_canny(image, p["threshold1"], p["threshold2"])
    elif func_name == "二值化":
        result = apply_threshold(image, p["value"], p["use_otsu"])
    elif func_name == "侵蝕":
        result = apply_erosion(image, p["kernel_size"], p["iterations"])
    elif func_name == "膨脹":
        result = apply_dilation(image, p["kernel_size"], p["iterations"])
    elif func_name == "銳化":
        result = apply_sharpen(image, p["intensity"])
    elif func_name == "Sobel 邊緣":
        result = apply_sobel(image, p["direction"], p["ksize"])
    elif func_name == "直方圖均衡化":
        result = apply_equalize_hist(image)
    elif func_name == "輪廓偵測":
        result = apply_contour(image, p["all_contours"], p["min_area"])
    else:
        result = image

    elapsed_ms = (time.perf_counter() - t0) * 1000
    h, w = image.shape[:2]

    return {
        "original_bgr": image,
        "result_bgr": result,
        "func_name": func_name,
        "elapsed_ms": elapsed_ms,
        "size": (w, h),
    }
