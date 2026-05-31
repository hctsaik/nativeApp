"""Tests for the 'app' tool type — a self-contained external Streamlit app
embedded as a top-level tool in one iframe (e.g. AI4BI). See engine
_derive_category / _start_app and plugins/bi/modules/ai4bi.
"""
from __future__ import annotations

import yaml

from engine import ROOT_DIR, TOOLS_DIR, _derive_category


class TestAppToolCategory:
    def test_app_prefix_is_top_level_app_category(self) -> None:
        assert _derive_category("app-ai4bi") == "app"
        assert _derive_category("app-anything") == "app"

    def test_existing_categories_unchanged(self) -> None:
        assert _derive_category("sheet-annotation") == "sheet"
        assert _derive_category("management-center") == "management"
        assert _derive_category("labelme-dino") == "external"
        assert _derive_category("module_026") == "module"


class TestAi4biAppWiring:
    """AI4BI is wired so the engine registers a top-level 'app' tool that runs
    tools/bi_runner.py (runner: bi → {runner}_runner.py)."""

    def test_app_module_declares_bi_runner(self) -> None:
        p = ROOT_DIR / "plugins" / "bi" / "modules" / "ai4bi" / "plugin.yaml"
        assert p.exists(), "AI4BI app module plugin.yaml missing"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert data["id"] == "app-ai4bi"
        assert data["runner"] == "bi"
        # tool_id 'app-ai4bi' → category 'app' (top-level visible in the portal)
        assert _derive_category(data["id"]) == "app"

    def test_bi_runner_exists_and_launches_ai4bi(self) -> None:
        runner = TOOLS_DIR / "bi_runner.py"
        assert runner.exists(), "tools/bi_runner.py missing"
        text = runner.read_text(encoding="utf-8")
        # the thin runner launches AI4BI's Streamlit app module
        assert "ai4bi.ui.app" in text
