from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PROCESS_FILE = Path(__file__).parent / "002_process.py"
_spec = importlib.util.spec_from_file_location("module_002_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic

_ROAD_PNG = Path(__file__).resolve().parent.parent.parent / "tools" / "road.png"


@pytest.fixture
def result():
    return execute_logic({"image_path": str(_ROAD_PNG), "memo": "test memo"})


def test_filename(result):
    assert result["filename"] == "road.png"


def test_resolution_is_tuple_of_int(result):
    w, h = result["resolution"]
    assert isinstance(w, int)
    assert isinstance(h, int)
    assert w > 0 and h > 0


def test_file_size_bytes_positive(result):
    assert result["file_size_bytes"] > 0


def test_file_size_kb_matches(result):
    expected = round(result["file_size_bytes"] / 1024, 2)
    assert result["file_size_kb"] == expected


def test_memo_passthrough():
    r = execute_logic({"image_path": str(_ROAD_PNG), "memo": "hello"})
    assert r["memo"] == "hello"


def test_memo_empty():
    r = execute_logic({"image_path": str(_ROAD_PNG), "memo": ""})
    assert r["memo"] == ""


def test_no_streamlit_import():
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
