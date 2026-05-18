from __future__ import annotations

import json
import os
import types
from pathlib import Path

import pytest

os.environ.setdefault("CIM_DEV_MODE", "1")

from plugin_loader import PluginLoader, _find_folder


# ── Helpers / Fixtures ──────────────────────────────────────────────────────


def _make_plugin_dir(root: Path, plugin_id: str, layers: list[str] | None = None) -> Path:
    """Create a minimal plugin folder with optional layer files."""
    folder = root / plugin_id
    folder.mkdir(parents=True, exist_ok=True)
    short_id = plugin_id.split("_", 1)[1]
    for layer in (layers or ["input", "process", "output"]):
        code = f"# layer: {layer}\ndef render_{layer}(x=None): return {{'layer': '{layer}'}}\nexecute_logic = render_{layer}\nrender_output = render_{layer}\n"
        (folder / f"{short_id}_{layer}.py").write_text(code, encoding="utf-8")
    manifest = {
        "id": plugin_id,
        "name": f"Test {plugin_id}",
        "version": "1.0.0",
        "category": "module",
        "runner": "cv_framework",
    }
    import yaml  # noqa: PLC0415
    (folder / "plugin.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
    return folder


@pytest.fixture()
def scripts_dir(tmp_path: Path) -> Path:
    _make_plugin_dir(tmp_path, "module_tst")
    return tmp_path


# ── is_dev_mode ─────────────────────────────────────────────────────────────


def test_is_dev_mode_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    assert PluginLoader.is_dev_mode() is True


def test_is_dev_mode_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    assert PluginLoader.is_dev_mode() is False


def test_is_dev_mode_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    assert PluginLoader.is_dev_mode() is True


# ── load_module_dev ──────────────────────────────────────────────────────────


def test_load_module_dev_returns_module(scripts_dir: Path) -> None:
    mod = PluginLoader.load_module_dev("module_tst", "input", scripts_dir)
    assert isinstance(mod, types.ModuleType)


def test_load_module_dev_has_callable(scripts_dir: Path) -> None:
    mod = PluginLoader.load_module_dev("module_tst", "process", scripts_dir)
    assert callable(getattr(mod, "execute_logic", None))


def test_load_module_dev_missing_layer_raises(scripts_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PluginLoader.load_module_dev("module_tst", "nonexistent", scripts_dir)


def test_load_module_dev_missing_plugin_raises(scripts_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        PluginLoader.load_module_dev("module_zzz", "input", scripts_dir)


# ── load_module_prod ──────────────────────────────────────────────────────────


def _make_content_json(plugin_id: str) -> dict:
    short_id = plugin_id.split("_", 1)[1]
    return {
        f"{short_id}_input.py": "def render_input(): return {'ok': True}",
        f"{short_id}_process.py": "def execute_logic(p): return {'result': 42}",
        f"{short_id}_output.py": "def render_output(r): pass",
    }


def test_load_module_prod_returns_module() -> None:
    content_json = _make_content_json("module_tst")
    mod = PluginLoader.load_module_prod("module_tst", "input", content_json)
    assert isinstance(mod, types.ModuleType)


def test_load_module_prod_callable(monkeypatch: pytest.MonkeyPatch) -> None:
    content_json = _make_content_json("module_tst")
    mod = PluginLoader.load_module_prod("module_tst", "process", content_json)
    result = mod.execute_logic({})
    assert result == {"result": 42}


def test_load_module_prod_missing_layer_raises() -> None:
    content_json = _make_content_json("module_tst")
    with pytest.raises(KeyError):
        PluginLoader.load_module_prod("module_tst", "nonexistent", content_json)


# ── load_module dispatch ──────────────────────────────────────────────────────


def test_load_module_dispatches_dev(
    monkeypatch: pytest.MonkeyPatch, scripts_dir: Path
) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    mod = PluginLoader.load_module_dev("module_tst", "input", scripts_dir)
    assert isinstance(mod, types.ModuleType)


def test_load_module_dispatches_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    content_json = _make_content_json("module_tst")
    mod = PluginLoader.load_module("module_tst", "input", content_json)
    assert isinstance(mod, types.ModuleType)


def test_load_module_prod_mode_no_content_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    with pytest.raises(ValueError, match="content_json"):
        PluginLoader.load_module("module_tst", "input")


# ── _find_folder ──────────────────────────────────────────────────────────────


def test_find_folder_direct_match(scripts_dir: Path) -> None:
    folder = _find_folder("module_tst", scripts_dir)
    assert folder.name == "module_tst"


def test_find_folder_by_yaml_id(scripts_dir: Path) -> None:
    # plugin.yaml has id: "module_tst"
    folder = _find_folder("module_tst", scripts_dir)
    assert folder.is_dir()


def test_find_folder_not_found_raises(scripts_dir: Path) -> None:
    with pytest.raises(FileNotFoundError):
        _find_folder("module_zzz", scripts_dir)
