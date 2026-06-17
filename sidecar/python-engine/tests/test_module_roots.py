"""Guard: module resolution works across scripts/ AND plugins/*/modules/.

The platform restructure moved modules out of scripts/ into git-tracked plugins:
- Labeling GUI modules -> plugins/labeling/modules/ (junction, P6e).
- First-party CV modules -> plugins/cim-modules/modules/ (submodule; modules
  independence, see docs/platform/modules-independence-and-store-plan.md).

Several runtime paths used to hard-code scripts/ and broke silently (pytest/
pyinstaller did not catch them because they are Streamlit/admin-invoked). This
test pins the dual-root resolution so a relocated module stays discoverable +
loadable + manageable regardless of which plugin root it lives under.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
# A Labeling GUI module that physically lives under plugins/labeling/modules/.
RELOCATED = "module_012"
# A first-party CV module that now lives under plugins/cim-modules/modules/.
CIM_MODULE = "module_001"


def test_modules_live_under_plugins_roots():
    assert (ENGINE_DIR / "plugins" / "labeling" / "modules" / RELOCATED).is_dir()
    assert (ENGINE_DIR / "plugins" / "cim-modules" / "modules" / CIM_MODULE).is_dir()


def test_plugin_loader_resolves_both_roots():
    import plugin_loader

    relocated = plugin_loader.find_module_folder(RELOCATED)
    cim = plugin_loader.find_module_folder(CIM_MODULE)
    assert relocated.is_dir() and relocated.name == RELOCATED
    assert "plugins" in relocated.parts and "modules" in relocated.parts
    assert cim.is_dir() and cim.name == CIM_MODULE
    assert "plugins" in cim.parts and "modules" in cim.parts
    assert cim.parent.parent.name == "cim-modules"

    yaml_ids = {p.parent.name for p in plugin_loader.module_yaml_paths()}
    assert RELOCATED in yaml_ids, "relocated module missing from module_yaml_paths()"
    assert CIM_MODULE in yaml_ids, "cim-modules module missing from module_yaml_paths()"


def test_cv_framework_runner_discovers_relocated_module():
    import sys
    sys.path.insert(0, str(ENGINE_DIR / "tools"))
    import cv_framework_runner

    ids = set(cv_framework_runner.discover_modules().values())
    assert RELOCATED in ids, "cv_framework_runner.discover_modules() lost the relocated module"
    assert CIM_MODULE in ids, "cv_framework_runner.discover_modules() lost the cim-modules module"


def test_management_preflight_and_snapshot_resolve_relocated_module():
    from management_insights import module_preflight, module_source_snapshot

    scripts_dir = ENGINE_DIR / "scripts"
    pf = module_preflight(scripts_dir, RELOCATED)
    # plugin.yaml + process must be found at the relocated path
    assert pf.checks.get("plugin.yaml") is True, "preflight cannot find relocated plugin.yaml"
    assert pf.checks.get("process") is True, "preflight cannot find relocated process layer"

    snap = module_source_snapshot(scripts_dir, RELOCATED)
    assert "plugin.yaml" in snap and snap, "source snapshot empty for relocated module (publish would fail)"
