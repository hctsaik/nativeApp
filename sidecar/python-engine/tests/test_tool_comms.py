from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import call, patch

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


# ── helpers ───────────────────────────────────────────────────────────────────

def _captured_html() -> list[str]:
    """Return list of html strings passed to components.html across calls."""
    return []


def _parse_posted(html: str) -> dict:
    """Extract the JSON object from the injected <script> tag."""
    start = html.index("postMessage(") + len("postMessage(")
    end = html.index(", '*')")
    return json.loads(html[start:end])


# ── _post internals ───────────────────────────────────────────────────────────

class TestPostInternals:
    def test_emits_script_tag(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("EXECUTE_START", {})
            args, kwargs = mock_html.call_args
            assert "<script>" in args[0]

    def test_emits_postMessage_to_window_top(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("EXECUTE_START", {})
            html = mock_html.call_args[0][0]
            assert "window.top.postMessage(" in html

    def test_height_is_zero(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("EXECUTE_START", {})
            _, kwargs = mock_html.call_args
            assert kwargs.get("height") == 0

    def test_payload_has_cim_flag(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("EXECUTE_START", {})
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data.get("_cim") is True

    def test_payload_type_matches(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("MY_TYPE", {"k": "v"})
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["type"] == "MY_TYPE"

    def test_payload_forwarded(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms._post("T", {"answer": 42})
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["payload"] == {"answer": 42}


# ── notify_start ──────────────────────────────────────────────────────────────

class TestNotifyStart:
    def test_sends_execute_start_type(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_start()
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["type"] == "EXECUTE_START"

    def test_payload_is_empty_dict(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_start()
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["payload"] == {}

    def test_calls_components_html_once(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_start()
            assert mock_html.call_count == 1


# ── notify_complete ───────────────────────────────────────────────────────────

class TestNotifyComplete:
    def test_sends_execute_complete_type(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete()
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["type"] == "EXECUTE_COMPLETE"

    def test_default_success_is_true(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete()
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["payload"]["success"] is True

    def test_success_false_propagates(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete(success=False)
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["payload"]["success"] is False

    def test_error_string_included_when_provided(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete(success=False, error="oops")
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert data["payload"]["error"] == "oops"

    def test_error_key_absent_on_success(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete(success=True)
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert "error" not in data["payload"]

    def test_empty_error_string_not_included(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete(success=True, error="")
            html = mock_html.call_args[0][0]
            data = _parse_posted(html)
            assert "error" not in data["payload"]

    def test_calls_components_html_once(self):
        with patch("streamlit.components.v1.html") as mock_html:
            import tool_comms
            tool_comms.notify_complete()
            assert mock_html.call_count == 1
