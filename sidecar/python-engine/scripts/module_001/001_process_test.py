from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

# Load 001_process.py via importlib (filename starts with digit → not a regular import)
_PROCESS_FILE = Path(__file__).parent / "001_process.py"
_spec = importlib.util.spec_from_file_location("module_001_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic


def _bgr(h: int = 100, w: int = 120) -> np.ndarray:
    return np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _run(func_name: str, params: dict, image: np.ndarray | None = None) -> dict:
    if image is None:
        image = _bgr()
    return execute_logic({"image_bgr": image, "func_name": func_name, "params": params})


# ── Output shape & type ───────────────────────────────────

def test_grayscale_output_is_2d():
    assert _run("灰階轉換", {})["result_bgr"].ndim == 2


def test_original_passthrough():
    img = _bgr()
    assert _run("原始影像", {}, img)["result_bgr"] is img


def test_gaussian_blur_same_shape():
    result = _run("高斯模糊", {"kernel_size": 5, "sigma": 1.0})
    assert result["result_bgr"].shape == result["original_bgr"].shape


def test_canny_is_2d():
    assert _run("Canny 邊緣偵測", {"threshold1": 50, "threshold2": 150})["result_bgr"].ndim == 2


def test_threshold_manual_binary():
    unique = np.unique(_run("二值化", {"value": 128, "use_otsu": False})["result_bgr"])
    assert set(unique).issubset({0, 255})


def test_threshold_otsu_binary():
    unique = np.unique(_run("二值化", {"value": 0, "use_otsu": True})["result_bgr"])
    assert set(unique).issubset({0, 255})


def test_erosion_dtype_preserved():
    assert _run("侵蝕", {"kernel_size": 3, "iterations": 1})["result_bgr"].dtype == np.uint8


def test_dilation_dtype_preserved():
    assert _run("膨脹", {"kernel_size": 3, "iterations": 1})["result_bgr"].dtype == np.uint8


def test_sharpen_output_dtype():
    assert _run("銳化", {"intensity": 1.0})["result_bgr"].dtype == np.uint8


def test_sobel_is_2d():
    assert _run("Sobel 邊緣", {"direction": "X", "ksize": 3})["result_bgr"].ndim == 2


def test_equalize_hist_is_2d():
    assert _run("直方圖均衡化", {})["result_bgr"].ndim == 2


def test_contour_is_3d():
    assert _run("輪廓偵測", {"all_contours": False, "min_area": 10})["result_bgr"].ndim == 3


# ── Metadata ─────────────────────────────────────────────

def test_elapsed_ms_is_nonnegative_float():
    result = _run("灰階轉換", {})
    assert isinstance(result["elapsed_ms"], float)
    assert result["elapsed_ms"] >= 0


def test_size_matches_image_dimensions():
    img = _bgr(80, 90)
    assert _run("原始影像", {}, img)["size"] == (90, 80)


# ── No streamlit import in process layer ──────────────────

def test_no_streamlit_import():
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
