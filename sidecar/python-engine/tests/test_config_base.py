"""Characterization + regression tests for module _config.py common helpers.

The 20+ scripts/module_*/_config.py files historically duplicated the same
boilerplate (project root, CIM_LOG_DIR, atomic_write, load/save config,
manifest db path, shared manifest id, manifest key). P2 of the platform
restructure extracts that into scripts/shared/_config_base.py and makes each
_config.py delegate.

These tests pin the *observable behavior* of those common functions so the
delegation cannot silently change paths or semantics.
"""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ENGINE_DIR / "scripts"

# Modules live under scripts/ (platform/other) and plugins/*/modules/ (e.g. the
# relocated Labeling GUI modules) — scan both so every module _config.py is covered.
_CONFIG_FILES = (
    sorted(SCRIPTS_DIR.glob("module_*/_config.py"))
    + sorted(ENGINE_DIR.glob("plugins/*/modules/module_*/_config.py"))
)
_MODULE_IDS = [p.parent.name.split("_", 1)[1] for p in _CONFIG_FILES]


def _load_config_module(path: Path, log_dir: Path, name: str):
    """Load a module _config.py fresh with CIM_LOG_DIR pointed at log_dir."""
    os.environ["CIM_LOG_DIR"] = str(log_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("cfg_path", _CONFIG_FILES, ids=_MODULE_IDS)
def test_config_common_helpers_behavior(cfg_path, tmp_path, monkeypatch):
    module_id = cfg_path.parent.name.split("_", 1)[1]
    log_dir = tmp_path / "cim_log"
    mod = _load_config_module(cfg_path, log_dir, f"_cfgtest_{module_id}")

    # _config_path / load_config / save_config — config file lives at
    # CIM_LOG_DIR/config/module_<id>.json and round-trips
    if hasattr(mod, "_config_path"):
        cp = mod._config_path()
        assert cp.name == f"module_{module_id}.json", f"{module_id}: config filename"
        assert cp.parent == log_dir / "config", f"{module_id}: config dir"

    if hasattr(mod, "load_config"):
        cfg = mod.load_config()
        assert isinstance(cfg, dict)

    if hasattr(mod, "load_config") and hasattr(mod, "save_config"):
        cfg = mod.load_config()
        cfg["__probe__"] = "xyz"
        mod.save_config(cfg)
        assert mod.load_config().get("__probe__") == "xyz", f"{module_id}: save/load round-trip"

    # get_manifest_db_path → CIM_LOG_DIR/db/manifest.sqlite
    if hasattr(mod, "get_manifest_db_path"):
        assert mod.get_manifest_db_path() == log_dir / "db" / "manifest.sqlite", \
            f"{module_id}: manifest db path"

    # _manifest_key → first 12 chars or "default"
    if hasattr(mod, "_manifest_key"):
        assert mod._manifest_key("abcdef0123456789") == "abcdef012345", f"{module_id}: manifest key"
        assert mod._manifest_key("") == "default", f"{module_id}: manifest key empty"

    # get_shared_manifest_id → reads CIM_LOG_DIR/config/shared.json last_manifest_id
    if hasattr(mod, "get_shared_manifest_id"):
        assert mod.get_shared_manifest_id() == "", f"{module_id}: shared id default empty"
        shared = log_dir / "config" / "shared.json"
        shared.parent.mkdir(parents=True, exist_ok=True)
        shared.write_text(json.dumps({"last_manifest_id": "mani-123"}), encoding="utf-8")
        assert mod.get_shared_manifest_id() == "mani-123", f"{module_id}: shared id read"
