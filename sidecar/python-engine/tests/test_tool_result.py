from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from tool_result import read_result, write_result


class TestWriteResult:
    def test_creates_file(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"a": 1}, {"b": 2})
        assert f.exists()

    def test_envelope_has_user_input_key(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"x": 10}, {})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "user_input" in data

    def test_envelope_has_process_result_key(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {}, {"y": 20})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert "process_result" in data

    def test_user_input_values_preserved(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"func": "erode", "size": 3}, {})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["user_input"] == {"func": "erode", "size": 3}

    def test_process_result_values_preserved(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {}, {"elapsed_ms": 42.5, "score": 0.9})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["process_result"] == {"elapsed_ms": 42.5, "score": 0.9}

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"v": 1}, {})
        write_result(f, {"v": 2}, {})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["user_input"]["v"] == 2

    def test_unicode_preserved(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"label": "貓"}, {})
        data = json.loads(f.read_text(encoding="utf-8"))
        assert data["user_input"]["label"] == "貓"


class TestReadResult:
    def test_returns_dict_with_correct_keys(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"a": 1}, {"b": 2})
        data = read_result(f)
        assert data is not None
        assert "user_input" in data and "process_result" in data

    def test_user_input_roundtrip(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {"key": "val"}, {})
        data = read_result(f)
        assert data["user_input"]["key"] == "val"

    def test_process_result_roundtrip(self, tmp_path: Path) -> None:
        f = tmp_path / "result.json"
        write_result(f, {}, {"score": 99})
        data = read_result(f)
        assert data["process_result"]["score"] == 99

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert read_result(tmp_path / "nonexistent.json") is None

    def test_invalid_json_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("not json", encoding="utf-8")
        assert read_result(f) is None

    def test_old_format_without_envelope_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "old.json"
        f.write_text(json.dumps({"func_name": "erode", "original_b64": "abc"}), encoding="utf-8")
        assert read_result(f) is None

    def test_partial_envelope_missing_process_result_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"user_input": {}}), encoding="utf-8")
        assert read_result(f) is None

    def test_partial_envelope_missing_user_input_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "partial.json"
        f.write_text(json.dumps({"process_result": {}}), encoding="utf-8")
        assert read_result(f) is None

    def test_empty_dicts_are_valid(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.json"
        write_result(f, {}, {})
        data = read_result(f)
        assert data is not None
        assert data["user_input"] == {}
        assert data["process_result"] == {}
