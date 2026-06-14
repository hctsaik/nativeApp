"""Tests for the LV / VisualLatent 'app' tool — a self-contained external
Streamlit app embedded as a top-level tool in one iframe, vendored as a git
submodule at vendor/LV. Mirrors test_app_tool_type.py (AI4BI). See engine
_derive_category / _start_app, tools/lv_runner.py, plugins/lv/modules/app-lv.
"""
from __future__ import annotations

import yaml

from engine import ROOT_DIR, TOOLS_DIR, _derive_category, _read_tool_requires
from plugin_loader import find_module_folder


class TestLvAppWiring:
    def test_app_module_declares_lv_runner(self) -> None:
        p = ROOT_DIR / "plugins" / "lv" / "modules" / "app-lv" / "plugin.yaml"
        assert p.exists(), "LV app module plugin.yaml missing"
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        assert data["id"] == "app-lv"
        assert data["runner"] == "lv"
        assert data["slug"] == "lv"
        # tool_id 'app-lv' → category 'app' (top-level visible in the portal)
        assert _derive_category(data["id"]) == "app"

    def test_lv_runner_exists_and_launches_vendored_app(self) -> None:
        runner = TOOLS_DIR / "lv_runner.py"
        assert runner.exists(), "tools/lv_runner.py missing"
        text = runner.read_text(encoding="utf-8")
        # the thin runner runpy-executes LV's flat scripts/app.py from the submodule
        assert "vendor" in text and "LV" in text and "app.py" in text
        assert "runpy" in text

    def test_module_folder_resolves_so_per_tool_requires_are_read(self) -> None:
        # _start_app reads requires via find_module_folder(tool_id); the folder
        # must be named 'app-lv' for the direct match (LV needs its torch-class
        # deps installed into a per-tool venv — unlike AI4BI's editable install).
        folder = find_module_folder("app-lv")
        assert folder.name == "app-lv"
        reqs = _read_tool_requires("app-lv")
        assert reqs, "LV per-tool requires must be discoverable"
        assert any("torch" in r for r in reqs)

    def test_plugin_manifest_one_way_core_dependency(self) -> None:
        pm = yaml.safe_load(
            (ROOT_DIR / "plugins" / "lv" / "plugin.manifest.yaml").read_text("utf-8"))
        assert pm["id"] == "lv"
        assert pm["depends_on"] == ["core"]   # one-way: lv -> core, never core -> lv

    def test_submodule_registered_with_sentinel(self) -> None:
        from engine import _SUBMODULE_SENTINELS
        lv = next((s for s in _SUBMODULE_SENTINELS if s["id"] == "lv"), None)
        assert lv is not None, "LV not registered in _SUBMODULE_SENTINELS"
        assert lv["kind"] == "submodule"
        assert lv["sentinel"] == ROOT_DIR / "vendor" / "LV" / "scripts" / "app.py"
