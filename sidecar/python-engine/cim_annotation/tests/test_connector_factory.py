from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from cim_annotation.connectors.factory import build
from cim_annotation.connectors.local_file import LocalFileConnector


def test_build_returns_local_file_when_no_yaml():
    pull, push = build(None)
    assert isinstance(pull, LocalFileConnector)
    assert isinstance(push, LocalFileConnector)


def test_build_returns_local_file_when_yaml_missing(tmp_path):
    pull, push = build(tmp_path / "nonexistent.yaml")
    assert isinstance(pull, LocalFileConnector)
    assert isinstance(push, LocalFileConnector)


def test_build_local_file_explicit(tmp_path):
    yaml_path = tmp_path / "connector.yaml"
    yaml_path.write_text(
        "connector:\n  type: local_file\n  local_file:\n    image_root: ''\n",
        encoding="utf-8",
    )
    pull, push = build(yaml_path)
    assert isinstance(pull, LocalFileConnector)
    assert isinstance(push, LocalFileConnector)


def test_build_unknown_type_raises(tmp_path):
    yaml_path = tmp_path / "connector.yaml"
    yaml_path.write_text("connector:\n  type: ftp\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown connector type"):
        build(yaml_path)


def test_build_custom_type(tmp_path, monkeypatch):
    """Custom connector loaded via importlib."""
    import types

    # Create a fake module with a connector class
    fake_mod = types.ModuleType("my_connectors.fake")

    class FakeConnector(LocalFileConnector):
        def __init__(self, config):
            super().__init__()
            self.config = config

    fake_mod.FakeConnector = FakeConnector
    monkeypatch.setitem(sys.modules, "my_connectors.fake", fake_mod)

    yaml_path = tmp_path / "connector.yaml"
    yaml_path.write_text(
        "connector:\n"
        "  type: custom\n"
        "  custom:\n"
        "    module: my_connectors.fake\n"
        "    class: FakeConnector\n"
        "    config:\n"
        "      host: localhost\n",
        encoding="utf-8",
    )
    pull, push = build(yaml_path)
    assert isinstance(pull, FakeConnector)
    assert pull.config == {"host": "localhost"}
