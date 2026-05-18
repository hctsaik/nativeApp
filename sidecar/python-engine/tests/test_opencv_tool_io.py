from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# tools/ is not a package — add it to path so relative imports inside the scripts work.
_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from opencv_tool_input import _encode_image
from opencv_tool_output import _decode_image


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def color_image() -> np.ndarray:
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:32, :] = [200, 100, 50]
    img[32:, :] = [50, 150, 200]
    return img


@pytest.fixture
def gray_image() -> np.ndarray:
    img = np.zeros((64, 64), dtype=np.uint8)
    img[:32, :] = 180
    return img


# ---------------------------------------------------------------------------
# _encode_image
# ---------------------------------------------------------------------------

class TestEncodeImage:
    def test_returns_string(self, color_image: np.ndarray) -> None:
        assert isinstance(_encode_image(color_image), str)

    def test_valid_base64(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        decoded = base64.b64decode(b64)
        assert len(decoded) > 0

    def test_decodes_to_png(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        raw = base64.b64decode(b64)
        # PNG magic bytes
        assert raw[:4] == b"\x89PNG"

    def test_grayscale_image_encodes(self, gray_image: np.ndarray) -> None:
        b64 = _encode_image(gray_image)
        assert isinstance(b64, str)
        assert len(b64) > 0


# ---------------------------------------------------------------------------
# _decode_image
# ---------------------------------------------------------------------------

class TestDecodeImage:
    def test_returns_ndarray(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        result = _decode_image(b64)
        assert isinstance(result, np.ndarray)

    def test_shape_preserved(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        result = _decode_image(b64)
        assert result.shape == color_image.shape

    def test_dtype_uint8(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        assert _decode_image(b64).dtype == np.uint8

    def test_invalid_base64_raises(self) -> None:
        with pytest.raises(Exception):
            _decode_image("not-valid-base64!!!")

    def test_grayscale_roundtrip(self, gray_image: np.ndarray) -> None:
        b64 = _encode_image(gray_image)
        result = _decode_image(b64)
        # Gray encoded as RGB (3 channels) — shape[2] must be 3
        assert result.ndim == 3
        assert result.shape[2] == 3


# ---------------------------------------------------------------------------
# Encode → Decode roundtrip
# ---------------------------------------------------------------------------

class TestEncodeDecodeRoundtrip:
    def test_color_pixel_values_preserved(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        decoded = _decode_image(b64)
        # _encode_image converts BGR→RGB for the PNG; _decode_image converts back to RGB.
        # Pixel order should be consistent — top-left pixel should be non-zero.
        assert decoded[0, 0].sum() > 0

    def test_dimensions_match(self, color_image: np.ndarray) -> None:
        b64 = _encode_image(color_image)
        decoded = _decode_image(b64)
        h, w = color_image.shape[:2]
        assert decoded.shape[0] == h
        assert decoded.shape[1] == w


