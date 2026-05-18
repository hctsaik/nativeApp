from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from log_utils import get_logger


@pytest.fixture(autouse=True)
def isolate_loggers():
    """Remove any loggers created during a test so they don't bleed across tests."""
    yield
    for name in list(logging.Logger.manager.loggerDict):
        if name.startswith("_test_"):
            logging.Logger.manager.loggerDict.pop(name, None)


class TestGetLogger:
    def test_returns_logger_instance(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_basic")
        assert isinstance(log, logging.Logger)

    def test_logger_name_matches(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_name")
        assert log.name == "_test_name"

    def test_has_two_handlers(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_handlers")
        assert len(log.handlers) == 2

    def test_one_stream_handler(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_stream")
        stream_handlers = [h for h in log.handlers if isinstance(h, logging.StreamHandler)
                           and not isinstance(h, logging.FileHandler)]
        assert len(stream_handlers) == 1

    def test_one_file_handler(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_file")
        file_handlers = [h for h in log.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1

    def test_log_file_created_in_cim_log_dir(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        get_logger("_test_path")
        assert (tmp_path / "_test_path.log").exists()

    def test_message_written_to_file(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_write")
        log.info("hello from test")
        # Flush all handlers
        for h in log.handlers:
            h.flush()
        content = (tmp_path / "_test_write.log").read_text(encoding="utf-8")
        assert "hello from test" in content

    def test_default_level_is_info(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_level")
        assert log.level == logging.INFO

    def test_custom_level_applied(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_debug", level=logging.DEBUG)
        assert log.level == logging.DEBUG

    def test_same_name_returns_cached_logger(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        a = get_logger("_test_cache")
        b = get_logger("_test_cache")
        assert a is b
        # Should not double-add handlers
        assert len(a.handlers) == 2

    def test_does_not_propagate(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
        log = get_logger("_test_propagate")
        assert log.propagate is False

    def test_log_dir_created_if_missing(self, tmp_path: Path, monkeypatch) -> None:
        new_dir = tmp_path / "deep" / "logs"
        monkeypatch.setenv("CIM_LOG_DIR", str(new_dir))
        get_logger("_test_mkdir")
        assert new_dir.is_dir()
