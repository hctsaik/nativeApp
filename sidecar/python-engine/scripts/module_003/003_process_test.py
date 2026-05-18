from __future__ import annotations

import base64
import importlib.util
import io
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

_PROCESS_FILE = Path(__file__).parent / "003_process.py"
_spec = importlib.util.spec_from_file_location("module_003_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic

_FIT_SCORE_FILE = Path(__file__).parents[1] / "frame_fit_score.py"
_fit_spec = importlib.util.spec_from_file_location("frame_fit_score", _FIT_SCORE_FILE)
_fit_mod = importlib.util.module_from_spec(_fit_spec)
_fit_spec.loader.exec_module(_fit_mod)
compute_fit_score = _fit_mod.compute_fit_score


def _run(**kwargs) -> dict:
    defaults = dict(width=400, height=250, left_roughness=15, right_roughness=15,
                    frequency=5, symmetry=False, fill_color="藍色", bg_color="白色", seed=0)
    defaults.update(kwargs)
    return execute_logic(defaults)


def _img(result: dict) -> np.ndarray:
    return np.array(Image.open(io.BytesIO(base64.b64decode(result["image_b64"]))))


# ── required keys ─────────────────────────────────────────

def test_returns_required_keys():
    r = _run()
    for k in ("image_b64", "width", "height", "left_roughness", "right_roughness",
               "frequency", "symmetry", "fill_color", "bg_color", "seed",
               "gradient_dir_variance", "psd_energy_ratio"):
        assert k in r


# ── image size ────────────────────────────────────────────

def test_image_dimensions_default():
    r = _run()
    img = Image.open(io.BytesIO(base64.b64decode(r["image_b64"])))
    assert img.size == (400, 250)


def test_image_dimensions_custom():
    r = _run(width=300, height=150)
    img = Image.open(io.BytesIO(base64.b64decode(r["image_b64"])))
    assert img.size == (300, 150)


# ── reproducibility ───────────────────────────────────────

def test_seed_reproducible():
    assert _run(seed=7)["image_b64"] == _run(seed=7)["image_b64"]


def test_different_seeds_differ():
    assert _run(seed=1)["image_b64"] != _run(seed=2)["image_b64"]


# ── edge constraints ──────────────────────────────────────

def test_top_row_fully_filled():
    arr = _img(_run(left_roughness=40, right_roughness=40, seed=3))
    fill = np.array([40, 80, 160])
    assert np.all(arr[0] == fill)


def test_bottom_row_fully_filled():
    arr = _img(_run(left_roughness=40, right_roughness=40, seed=3))
    fill = np.array([40, 80, 160])
    assert np.all(arr[-1] == fill)


def test_roughness_zero_middle_fully_filled():
    arr = _img(_run(left_roughness=0, right_roughness=0))
    fill = np.array([40, 80, 160])
    assert np.all(arr[arr.shape[0] // 2] == fill)


# ── symmetry ─────────────────────────────────────────────

def test_symmetry_produces_mirror():
    arr = _img(_run(left_roughness=20, symmetry=True, seed=5))
    mid = arr.shape[0] // 2
    row = arr[mid, :, 0]
    assert np.array_equal(row, row[::-1])


# ── colour presets ────────────────────────────────────────

def test_fill_color_red():
    arr = _img(_run(fill_color="紅色", left_roughness=0, right_roughness=0))
    mid = arr.shape[0] // 2
    assert arr[mid, arr.shape[1] // 2, 0] == 180


def test_bg_color_gray():
    r = _run(bg_color="淺灰", left_roughness=0, right_roughness=0)
    assert _img(r) is not None


# ── frequency ─────────────────────────────────────────────

def test_high_frequency_differs_from_low():
    r_low = _run(frequency=1, seed=10)
    r_high = _run(frequency=200, seed=10)
    assert r_low["image_b64"] != r_high["image_b64"]


# ── fit target ─────────────────────────────────────────────

def test_negative_fit_offset_maps_to_inward_gap():
    r = _run(mode="藍框貼合測試", fit_offset_score=-0.5)
    assert r["fit_offset_score"] == pytest.approx(-0.5)
    assert r["fit_gap_px"] == 10
    assert r["fit_direction"] == "內縮"
    assert r["left_offset"] == -10
    assert r["right_offset"] == -10


def test_positive_fit_offset_maps_to_outward_gap():
    r = _run(mode="藍框貼合測試", fit_offset_score=0.5)
    assert r["fit_offset_score"] == pytest.approx(0.5)
    assert r["fit_gap_px"] == 10
    assert r["fit_direction"] == "外突"
    assert r["left_offset"] == 10
    assert r["right_offset"] == 10


def test_zero_fit_offset_has_no_gap():
    r = _run(mode="藍框貼合測試", fit_offset_score=0.0)
    assert r["fit_offset_score"] == pytest.approx(0.0)
    assert r["fit_gap_px"] == 0
    assert r["fit_direction"] == "重合"
    assert r["left_offset"] == 0
    assert r["right_offset"] == 0


def test_zero_fit_offset_generates_detected_edge_overlap():
    rgb = _img(_run(mode="藍框貼合測試", fit_offset_score=0.0, roughness=80, right_roughness=80, intensity=49))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    score = compute_fit_score(bgr)
    assert score["overall"] == pytest.approx(1.0)
    assert score["offset_score"] == pytest.approx(0.0)
    assert score["avg_dist_px"] == pytest.approx(0.0)


def test_zero_fit_offset_generates_straight_overlapped_edges_even_with_roughness():
    arr = _img(_run(mode="藍框貼合測試", fit_offset_score=0.0, roughness=80, right_roughness=80, intensity=49))
    black = np.all(arr == np.array([0, 0, 0]), axis=2)
    blue = np.all(arr == np.array([0, 100, 220]), axis=2)
    for y in range(20, arr.shape[0] - 20):
        left_black = np.where(black[y, : arr.shape[1] // 2])[0]
        left_blue = np.where(blue[y, : arr.shape[1] // 2])[0]
        right_black = np.where(black[y, arr.shape[1] // 2 :])[0] + arr.shape[1] // 2
        right_blue = np.where(blue[y, arr.shape[1] // 2 :])[0] + arr.shape[1] // 2
        assert left_black.max() == left_blue.min() - 1
        assert right_black.min() == right_blue.max() + 1


# ── gradient_dir_variance ─────────────────────────────────

def test_gradient_dir_variance_in_range():
    r = _run()
    assert 0.0 <= r["gradient_dir_variance"] <= 1.0


def test_smooth_edge_lower_gdv_than_rough():
    r_smooth = _run(left_roughness=0, right_roughness=0)
    r_rough  = _run(left_roughness=80, right_roughness=80, frequency=100, seed=42)
    assert r_rough["gradient_dir_variance"] >= r_smooth["gradient_dir_variance"]


def test_gradient_dir_variance_zero_roughness_near_zero():
    r = _run(left_roughness=0, right_roughness=0)
    assert r["gradient_dir_variance"] < 0.05


# ── psd_energy_ratio ──────────────────────────────────────

def test_psd_energy_ratio_in_range():
    r = _run()
    assert 0.0 <= r["psd_energy_ratio"] <= 1.0


def test_high_frequency_roughness_has_higher_psd_ratio():
    r_low_freq  = _run(left_roughness=40, frequency=1,   seed=7)
    r_high_freq = _run(left_roughness=40, frequency=200, seed=7)
    assert r_high_freq["psd_energy_ratio"] >= r_low_freq["psd_energy_ratio"]


# ── no streamlit ─────────────────────────────────────────

def test_no_streamlit_import():
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
