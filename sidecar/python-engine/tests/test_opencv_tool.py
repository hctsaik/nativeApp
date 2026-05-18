from __future__ import annotations

import numpy as np
import pytest

from tools.opencv_tool import (
    apply_canny,
    apply_contour,
    apply_dilation,
    apply_equalize_hist,
    apply_erosion,
    apply_gaussian_blur,
    apply_grayscale,
    apply_sharpen,
    apply_sobel,
    apply_threshold,
)


# ---------------------------------------------------------------------------
# 共用 fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def color_image() -> np.ndarray:
    """64x64 三通道彩色影像（BGR），含漸層以便邊緣函式有輸出。"""
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:32, :] = [200, 100, 50]
    img[32:, :] = [50, 150, 200]
    return img


@pytest.fixture
def gray_image() -> np.ndarray:
    """64x64 單通道灰階影像。"""
    img = np.zeros((64, 64), dtype=np.uint8)
    img[:32, :] = 200
    img[32:, :] = 50
    return img


@pytest.fixture
def black_image() -> np.ndarray:
    """全黑彩色影像，用於邊界值測試。"""
    return np.zeros((32, 32, 3), dtype=np.uint8)


@pytest.fixture
def white_image() -> np.ndarray:
    """全白彩色影像，用於邊界值測試。"""
    return np.full((32, 32, 3), 255, dtype=np.uint8)


# ---------------------------------------------------------------------------
# 灰階轉換
# ---------------------------------------------------------------------------

class TestApplyGrayscale:
    def test_color_to_gray_shape(self, color_image: np.ndarray) -> None:
        result = apply_grayscale(color_image)
        assert result.shape == (64, 64)

    def test_gray_input_unchanged(self, gray_image: np.ndarray) -> None:
        result = apply_grayscale(gray_image)
        assert result.shape == gray_image.shape

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_grayscale(color_image).dtype == np.uint8

    def test_black_stays_black(self, black_image: np.ndarray) -> None:
        result = apply_grayscale(black_image)
        assert result.max() == 0

    def test_white_stays_white(self, white_image: np.ndarray) -> None:
        result = apply_grayscale(white_image)
        assert result.min() == 255


# ---------------------------------------------------------------------------
# 高斯模糊
# ---------------------------------------------------------------------------

class TestApplyGaussianBlur:
    def test_output_shape_preserved(self, color_image: np.ndarray) -> None:
        result = apply_gaussian_blur(color_image, 5, 1.0)
        assert result.shape == color_image.shape

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_gaussian_blur(color_image, 5, 1.0).dtype == np.uint8

    def test_even_kernel_corrected_to_odd(self, color_image: np.ndarray) -> None:
        # 即使傳入偶數 kernel，函式應自動修正，不應拋出例外
        result = apply_gaussian_blur(color_image, 4, 1.0)
        assert result.shape == color_image.shape

    def test_kernel_size_one_no_change(self, color_image: np.ndarray) -> None:
        result = apply_gaussian_blur(color_image, 1, 0.0)
        np.testing.assert_array_equal(result, color_image)

    def test_large_sigma_increases_blur(self, color_image: np.ndarray) -> None:
        low = apply_gaussian_blur(color_image, 5, 0.1)
        high = apply_gaussian_blur(color_image, 5, 5.0)
        # 高 sigma 應產生更均勻的輸出（標準差更小）
        assert high.std() <= low.std() + 1


# ---------------------------------------------------------------------------
# Canny 邊緣偵測
# ---------------------------------------------------------------------------

class TestApplyCanny:
    def test_output_shape_is_2d(self, color_image: np.ndarray) -> None:
        result = apply_canny(color_image, 50, 150)
        assert result.ndim == 2

    def test_output_shape_matches_input_hw(self, color_image: np.ndarray) -> None:
        result = apply_canny(color_image, 50, 150)
        assert result.shape == (64, 64)

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_canny(color_image, 50, 150).dtype == np.uint8

    def test_high_thresholds_produce_fewer_edges(self, color_image: np.ndarray) -> None:
        low_edges = apply_canny(color_image, 1, 2).sum()
        high_edges = apply_canny(color_image, 254, 255).sum()
        assert high_edges <= low_edges

    def test_detects_edges_in_gradient_image(self, color_image: np.ndarray) -> None:
        result = apply_canny(color_image, 10, 50)
        # 有強邊緣的影像（水平分界線）應該有至少一個邊緣像素
        assert result.sum() > 0


# ---------------------------------------------------------------------------
# 二值化
# ---------------------------------------------------------------------------

class TestApplyThreshold:
    def test_output_is_binary(self, color_image: np.ndarray) -> None:
        result = apply_threshold(color_image, 127, False)
        unique = set(result.flatten().tolist())
        assert unique.issubset({0, 255})

    def test_output_shape_2d(self, color_image: np.ndarray) -> None:
        result = apply_threshold(color_image, 127, False)
        assert result.ndim == 2

    def test_otsu_mode_also_binary(self, color_image: np.ndarray) -> None:
        result = apply_threshold(color_image, 0, True)
        unique = set(result.flatten().tolist())
        assert unique.issubset({0, 255})

    def test_threshold_zero_all_white(self, color_image: np.ndarray) -> None:
        result = apply_threshold(color_image, 0, False)
        assert result.min() == 255

    def test_threshold_255_all_black(self, color_image: np.ndarray) -> None:
        result = apply_threshold(color_image, 255, False)
        assert result.max() == 0


# ---------------------------------------------------------------------------
# 侵蝕
# ---------------------------------------------------------------------------

class TestApplyErosion:
    def test_output_shape_preserved(self, color_image: np.ndarray) -> None:
        result = apply_erosion(color_image, 3, 1)
        assert result.shape == color_image.shape

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_erosion(color_image, 3, 1).dtype == np.uint8

    def test_black_image_unchanged(self, black_image: np.ndarray) -> None:
        result = apply_erosion(black_image, 3, 1)
        np.testing.assert_array_equal(result, black_image)

    def test_more_iterations_reduces_bright_area(self, color_image: np.ndarray) -> None:
        r1 = apply_erosion(color_image, 3, 1)
        r3 = apply_erosion(color_image, 3, 3)
        assert r3.sum() <= r1.sum()


# ---------------------------------------------------------------------------
# 膨脹
# ---------------------------------------------------------------------------

class TestApplyDilation:
    def test_output_shape_preserved(self, color_image: np.ndarray) -> None:
        result = apply_dilation(color_image, 3, 1)
        assert result.shape == color_image.shape

    def test_white_image_unchanged(self, white_image: np.ndarray) -> None:
        result = apply_dilation(white_image, 3, 1)
        np.testing.assert_array_equal(result, white_image)

    def test_more_iterations_increases_bright_area(self, color_image: np.ndarray) -> None:
        r1 = apply_dilation(color_image, 3, 1)
        r3 = apply_dilation(color_image, 3, 3)
        assert r3.sum() >= r1.sum()


# ---------------------------------------------------------------------------
# 銳化
# ---------------------------------------------------------------------------

class TestApplySharpen:
    def test_output_shape_preserved(self, color_image: np.ndarray) -> None:
        result = apply_sharpen(color_image, 1.0)
        assert result.shape == color_image.shape

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_sharpen(color_image, 1.0).dtype == np.uint8

    def test_output_values_in_range(self, color_image: np.ndarray) -> None:
        result = apply_sharpen(color_image, 3.0)
        assert result.min() >= 0
        assert result.max() <= 255

    def test_intensity_zero_near_identity(self, color_image: np.ndarray) -> None:
        # intensity=0 時 kernel 為 identity（中心=1, 其餘=0），結果應接近原圖
        result = apply_sharpen(color_image, 0.0)
        diff = np.abs(result.astype(int) - color_image.astype(int))
        assert diff.max() <= 5


# ---------------------------------------------------------------------------
# Sobel 邊緣
# ---------------------------------------------------------------------------

class TestApplySobel:
    @pytest.mark.parametrize("direction", ["X", "Y", "合併"])
    def test_output_shape_2d(self, color_image: np.ndarray, direction: str) -> None:
        result = apply_sobel(color_image, direction, 3)
        assert result.ndim == 2

    @pytest.mark.parametrize("direction", ["X", "Y", "合併"])
    def test_output_dtype_uint8(self, color_image: np.ndarray, direction: str) -> None:
        assert apply_sobel(color_image, direction, 3).dtype == np.uint8

    def test_detects_horizontal_edge_in_y_direction(self, color_image: np.ndarray) -> None:
        # 影像有水平邊緣，Y 方向 Sobel 應有較強回應
        result = apply_sobel(color_image, "Y", 3)
        assert result.sum() > 0

    def test_values_in_range(self, color_image: np.ndarray) -> None:
        result = apply_sobel(color_image, "合併", 3)
        assert result.min() >= 0
        assert result.max() <= 255


# ---------------------------------------------------------------------------
# 直方圖均衡化
# ---------------------------------------------------------------------------

class TestApplyEqualizeHist:
    def test_output_shape_2d(self, color_image: np.ndarray) -> None:
        result = apply_equalize_hist(color_image)
        assert result.ndim == 2

    def test_output_dtype_uint8(self, color_image: np.ndarray) -> None:
        assert apply_equalize_hist(color_image).dtype == np.uint8

    def test_output_uses_full_range(self, color_image: np.ndarray) -> None:
        result = apply_equalize_hist(color_image)
        # 均衡化後應使用接近完整的 0–255 範圍
        assert result.max() > 200
        assert result.min() < 50


# ---------------------------------------------------------------------------
# 輪廓偵測
# ---------------------------------------------------------------------------

class TestApplyContour:
    def test_output_shape_is_3channel(self, color_image: np.ndarray) -> None:
        result = apply_contour(color_image, False, 0)
        assert result.ndim == 3
        assert result.shape[2] == 3

    def test_output_shape_matches_input_hw(self, color_image: np.ndarray) -> None:
        result = apply_contour(color_image, False, 0)
        assert result.shape[:2] == color_image.shape[:2]

    def test_gray_input_returns_color_output(self, gray_image: np.ndarray) -> None:
        result = apply_contour(gray_image, False, 0)
        assert result.ndim == 3

    def test_large_min_area_reduces_contours(self, color_image: np.ndarray) -> None:
        # 超大 min_area 應濾掉所有輪廓，畫面上不會有綠色
        result_all = apply_contour(color_image, True, 0)
        result_none = apply_contour(color_image, True, 99999)
        green_all = result_all[:, :, 1].sum()
        green_none = result_none[:, :, 1].sum()
        assert green_none <= green_all
