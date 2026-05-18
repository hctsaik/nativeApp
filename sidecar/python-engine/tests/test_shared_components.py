"""Tests for scripts/shared/ common components (non-Streamlit logic only)."""
from __future__ import annotations

import importlib.util
from datetime import date
from pathlib import Path

import pytest

# ── Load shared modules via path (avoids sys.path assumptions) ───────────────

def _load(name: str):
    path = Path(__file__).resolve().parent.parent / "scripts" / "shared" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── ui_components ────────────────────────────────────────────────────────────

class TestThreeMonthsAgo:
    def _fn(self):
        return _load("ui_components").three_months_ago

    def test_returns_date(self):
        result = self._fn()(date(2026, 5, 1))
        assert isinstance(result, date)

    def test_subtracts_3_months_same_day(self):
        assert self._fn()(date(2026, 5, 15)) == date(2026, 2, 15)

    def test_wraps_year_boundary(self):
        assert self._fn()(date(2026, 2, 1)) == date(2025, 11, 1)

    def test_clamps_day_overflow(self):
        # May 31 − 3 months = Feb 28 (2026 is not a leap year)
        result = self._fn()(date(2026, 5, 31))
        assert result == date(2026, 2, 28)

    def test_default_ref_is_today(self):
        result = self._fn()()
        today = date.today()
        assert result < today
        assert (today - result).days in range(88, 95)  # approx 90 days


class TestUiComponentsImportable:
    def test_module_loads(self):
        mod = _load("ui_components")
        assert mod is not None

    def test_functions_exist(self):
        mod = _load("ui_components")
        for fn in ("three_months_ago", "date_input_single", "date_input_range",
                   "parts_input", "save_success_toast", "download_image_button"):
            assert callable(getattr(mod, fn, None)), f"{fn} not callable"

    def test_no_streamlit_in_pure_logic(self):
        """three_months_ago must not call Streamlit — it's pure date logic."""
        import inspect
        mod = _load("ui_components")
        src = inspect.getsource(mod.three_months_ago)
        assert "st." not in src


# ── image_widget ─────────────────────────────────────────────────────────────

class TestImageWidgetImportable:
    def test_module_loads(self):
        mod = _load("image_widget")
        assert mod is not None

    def test_render_image_preview_exists(self):
        mod = _load("image_widget")
        assert callable(getattr(mod, "render_image_preview", None))

    def test_no_streamlit_in_process_layer(self):
        """image_widget may use streamlit (it is a UI module) — just confirm it loads."""
        mod = _load("image_widget")
        assert mod.render_image_preview is not None

    def test_constants_defined(self):
        mod = _load("image_widget")
        assert mod._THUMB_H  > 0
        assert mod._PREVIEW_H > 0
        assert mod._IFRAME_H  > mod._THUMB_H
