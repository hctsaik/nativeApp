from __future__ import annotations

import importlib.util
import json
import os
import sys
import types
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent


SCRIPTS_DIR = _root() / "scripts"


def module_roots() -> list[Path]:
    """All roots that contain module folders: scripts/ (platform/other modules)
    + each plugin's modules dir (plugins/<plugin>/modules/)."""
    return [SCRIPTS_DIR] + sorted((_root() / "plugins").glob("*/modules"))


def module_yaml_paths() -> list[Path]:
    """Every module's plugin.yaml across all roots (scripts/ + plugins/*/modules/)."""
    out: list[Path] = []
    for root in module_roots():
        out += sorted(root.glob("*/plugin.yaml"))
    return out


def iter_module_folders(scripts_dir: Path | None = None) -> list[Path]:
    """Every `module_*` folder across all roots (scripts/ + plugins/*/modules/).

    `scripts_dir` is overridable so callers that inject a custom scripts root
    (e.g. tests, the management registry) still get dual-root scanning relative
    to *that* root's sibling `plugins/` dir.
    """
    base = scripts_dir or SCRIPTS_DIR
    roots = [base] + sorted((base.parent / "plugins").glob("*/modules"))
    out: list[Path] = []
    for root in roots:
        if root.is_dir():
            out += sorted(root.glob("module_*"))
    return out


def find_module_folder(plugin_id: str) -> Path:
    """Public dual-root folder resolver (scripts/ + plugins/*/modules/)."""
    return _find_folder(plugin_id, SCRIPTS_DIR)


class PluginLoader:
    """Load a module layer (input / process / output) in dev or prod mode."""

    @staticmethod
    def is_dev_mode() -> bool:
        return os.environ.get("CIM_DEV_MODE", "1").strip() == "1"

    @staticmethod
    def load_module(plugin_id: str, layer: str, content_json: dict | None = None) -> types.ModuleType:
        """Dispatch to dev or prod loader based on CIM_DEV_MODE."""
        if PluginLoader.is_dev_mode():
            return PluginLoader.load_module_dev(plugin_id, layer)
        if content_json is None:
            raise ValueError("content_json is required in prod mode")
        return PluginLoader.load_module_prod(plugin_id, layer, content_json)

    @staticmethod
    def load_module_dev(plugin_id: str, layer: str, scripts_dir: Path = SCRIPTS_DIR) -> types.ModuleType:
        """Load from filesystem.  plugin_id == 'module_003', layer == 'input'."""
        folder = _find_folder(plugin_id, scripts_dir)
        # Derive the numeric/short id for filenames: module_003 → 003
        short_id = folder.name.split("_", 1)[1]
        file = folder / f"{short_id}_{layer}.py"
        if not file.exists():
            raise FileNotFoundError(f"Layer file not found: {file}")
        return _load_from_file(file, f"plugin.{plugin_id}.{layer}")

    @staticmethod
    def load_module_prod(plugin_id: str, layer: str, content_json: dict) -> types.ModuleType:
        """Load from content_json snapshot (in-memory exec, no filesystem writes)."""
        short_id = plugin_id.split("_", 1)[1] if "_" in plugin_id else plugin_id
        filename = f"{short_id}_{layer}.py"
        if filename not in content_json:
            raise KeyError(f"{filename} not found in content_json for {plugin_id}")
        source = content_json[filename]
        _sandbox_check(source, filename)  # raises SandboxViolation when enforce
        module_name = f"plugin.{plugin_id}.{layer}"
        mod = types.ModuleType(module_name)
        mod.__file__ = f"<db:{plugin_id}/{filename}>"
        sys.modules[module_name] = mod
        exec(compile(source, mod.__file__, "exec"), mod.__dict__)  # noqa: S102
        return mod


# ── helpers ─────────────────────────────────────────────────────────────────


def _find_folder(plugin_id: str, scripts_dir: Path) -> Path:
    """Locate the module folder for a given plugin_id.

    Searches scripts/ (platform/other modules) and each plugin's modules dir
    (plugins/<plugin>/modules/, e.g. the relocated Labeling GUI modules).
    """
    roots = [scripts_dir] + sorted((_root() / "plugins").glob("*/modules"))
    # Direct match: plugin_id is 'module_003'
    for root in roots:
        direct = root / plugin_id
        if direct.is_dir():
            return direct
    # Scan all module_* folders for a matching plugin.yaml id
    import yaml  # noqa: PLC0415
    for root in roots:
        for folder in root.glob("module_*"):
            manifest = folder / "plugin.yaml"
            if manifest.exists():
                try:
                    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
                    if data.get("id") == plugin_id:
                        return folder
                except Exception:
                    pass
    raise FileNotFoundError(f"No folder found for plugin_id '{plugin_id}'")


def _sandbox_check(source: str, filename: str) -> None:
    """Run the load-time plugin sandbox (deny-list). Raises on enforce mode."""
    try:
        from core.sandbox import check_source  # noqa: PLC0415
    except Exception:
        return
    check_source(source, filename)


def _load_from_file(file: Path, module_name: str) -> types.ModuleType:
    try:
        source = file.read_text(encoding="utf-8")
    except Exception:
        source = None
    if source is not None:
        _sandbox_check(source, file.name)  # raises SandboxViolation when enforce
    spec = importlib.util.spec_from_file_location(module_name, file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod
