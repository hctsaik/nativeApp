from __future__ import annotations

import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest

_PROCESS_FILE = Path(__file__).parent / "004_process.py"
_spec = importlib.util.spec_from_file_location("module_004_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic


def _make_rect_image(w: int = 200, h: int = 150, roughness: int = 0) -> bytes:
    """Generate a white rectangle on black background as PNG bytes."""
    arr = np.zeros((h, w), dtype=np.uint8)
    arr[20:h - 20, 30:w - 30] = 255
    if roughness > 0:
        rng = np.random.default_rng(42)
        for y in range(20, h - 20):
            offset = int(rng.integers(-roughness, roughness + 1))
            x0 = max(0, 30 + offset)
            arr[y, x0] = 255
    _, buf = cv2.imencode(".png", arr)
    return buf.tobytes()


def _make_fit_image(gap_px: int = 0, w: int = 400, h: int = 250) -> bytes:
    arr = np.full((h, w, 3), (120, 120, 120), dtype=np.uint8)
    left_end = 49 - gap_px
    right_beg = 350 + gap_px
    if left_end >= 0:
        arr[:, :left_end + 1] = (0, 0, 0)
    if right_beg < w:
        arr[:, right_beg:] = (0, 0, 0)
    cv2.rectangle(arr, (50, 10), (349, h - 11), (220, 100, 0), 3)
    _, buf = cv2.imencode(".png", arr)
    return buf.tobytes()


_RECT_BYTES  = _make_rect_image()
_ROUGH_BYTES = _make_rect_image(roughness=5)


@pytest.fixture
def result():
    return execute_logic({"image_bytes": _RECT_BYTES, "parts": "TEST-001"})


def test_returns_required_keys(result):
    for k in ("image_b64", "left_roughness", "right_roughness", "frequency",
              "intensity", "image_width", "image_height", "timestamp", "parts",
              "gradient_dir_variance", "psd_energy_ratio"):
        assert k in result


def test_image_b64_is_valid_base64(result):
    import base64
    raw = base64.b64decode(result["image_b64"])
    assert len(raw) > 0


def test_no_image_returns_none_b64():
    r = execute_logic({"image_bytes": None, "parts": ""})
    assert r["image_b64"] is None


def test_parts_passthrough(result):
    assert result["parts"] == "TEST-001"


def test_image_dimensions(result):
    assert result["image_width"] == 200
    assert result["image_height"] == 150


def test_roughness_non_negative(result):
    assert result["left_roughness"] >= 0
    assert result["right_roughness"] >= 0


def test_intensity_non_negative(result):
    assert result["intensity"] >= 0


def test_timestamp_format(result):
    from datetime import datetime
    datetime.strptime(result["timestamp"], "%Y-%m-%d %H:%M:%S")


def test_no_image_returns_zeros():
    r = execute_logic({"image_bytes": None, "parts": "X"})
    assert r["error"] == "no_image"
    assert r["image_width"] == 0


def test_rough_edge_higher_roughness_than_clean():
    r_clean = execute_logic({"image_bytes": _RECT_BYTES, "parts": ""})
    r_rough = execute_logic({"image_bytes": _ROUGH_BYTES, "parts": ""})
    assert r_rough["left_roughness"] >= r_clean["left_roughness"]


def test_image_name_passthrough():
    r = execute_logic({"image_bytes": _RECT_BYTES, "image_name": "test.png", "parts": ""})
    assert r["image_name"] == "test.png"


# ── fit score ──────────────────────────────────────────────

def test_fit_score_enabled_returns_consistent_kpis():
    r = execute_logic({"image_bytes": _make_fit_image(0), "enable_fit_score": True})
    assert r["fit_overall"] is not None
    assert r["fit_offset_score"] is not None
    assert 0.0 <= r["fit_overall"] <= 1.0
    assert -1.0 <= r["fit_offset_score"] <= 1.0
    assert r["fit_avg_dist"] is not None
    assert r["fit_left_signed_dist"] is not None
    assert r["fit_right_signed_dist"] is not None


def test_fit_score_drops_when_edge_shrinks_from_frame():
    perfect = execute_logic({"image_bytes": _make_fit_image(0), "enable_fit_score": True})
    shrunk = execute_logic({"image_bytes": _make_fit_image(12), "enable_fit_score": True})
    assert perfect["fit_overall"] >= shrunk["fit_overall"]
    assert perfect["fit_offset_score"] == pytest.approx(0.0)
    assert shrunk["fit_offset_score"] < 0.0
    assert shrunk["fit_avg_dist"] >= perfect["fit_avg_dist"]


def test_fit_score_reports_outward_protrusion_as_positive():
    protruded = execute_logic({"image_bytes": _make_fit_image(-12), "enable_fit_score": True})
    assert protruded["fit_offset_score"] > 0.0


# ── gradient_dir_variance ─────────────────────────────────

def test_gradient_dir_variance_in_range(result):
    assert 0.0 <= result["gradient_dir_variance"] <= 1.0


def test_gradient_dir_variance_present_on_no_image():
    r = execute_logic({"image_bytes": None, "parts": ""})
    assert "gradient_dir_variance" in r
    assert r["gradient_dir_variance"] == 0.0


def test_gradient_dir_variance_nonzero_on_real_image(result):
    # A rectangle has 4 edge directions → GDV is meaningfully non-zero
    assert result["gradient_dir_variance"] > 0.0


# ── psd_energy_ratio ──────────────────────────────────────

def test_psd_energy_ratio_in_range(result):
    assert 0.0 <= result["psd_energy_ratio"] <= 1.0


def test_psd_energy_ratio_present_on_no_image():
    r = execute_logic({"image_bytes": None, "parts": ""})
    assert "psd_energy_ratio" in r
    assert r["psd_energy_ratio"] == 0.0


# ── no streamlit ─────────────────────────────────────────

def test_no_streamlit_import():
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
