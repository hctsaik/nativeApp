from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_HERE = Path(__file__).resolve().parent


class _Context:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeStreamlit:
    def __init__(self):
        self.session_state: dict = {}
        self.calls: list[tuple[str, object]] = []

    def subheader(self, text):
        self.calls.append(("subheader", text))

    def warning(self, text):
        self.calls.append(("warning", text))

    def info(self, text):
        self.calls.append(("info", text))

    def markdown(self, text):
        self.calls.append(("markdown", text))

    def success(self, text):
        self.calls.append(("success", text))

    def caption(self, text):
        self.calls.append(("caption", text))

    def text_area(self, label, *, key, height=None, placeholder=None, help=None):
        self.calls.append(("text_area", label))
        return self.session_state.get(key, "")

    def selectbox(self, label, options, *, index=0, help=None):
        self.calls.append(("selectbox", label))
        return options[index]

    def radio(self, label, options, *, index=0, horizontal=False, key=None):
        self.calls.append(("radio", label))
        if key:
            self.session_state[key] = options[index]
        return options[index]

    def checkbox(self, label, *, key, value=None, help=None):
        self.calls.append(("checkbox", label))
        return bool(self.session_state.get(key, value if value is not None else False))

    def text_input(self, label, *, key, placeholder=None):
        self.calls.append(("text_input", label))
        return self.session_state.get(key, "")

    def button(self, label, *, key=None, help=None):
        self.calls.append(("button", label))
        return False

    def slider(self, label, *, min_value=None, max_value=None, value=None, step=None, format=None, key=None):
        self.calls.append(("slider", label))
        if key:
            self.session_state[key] = value
        return value

    def write(self, text):
        self.calls.append(("write", text))

    def number_input(
        self, label, *, min_value=None, max_value=None, step=None, key, disabled=False
    ):
        self.calls.append(("number_input", label))
        return self.session_state.get(key, min_value)

    def expander(self, label, expanded=False):
        self.calls.append(("expander", (label, expanded)))
        return _Context()

    def columns(self, spec):
        self.calls.append(("columns", spec))
        return [_Context() for _ in spec]


class _FakeConfig:
    def __init__(self, config: dict | None = None):
        self.config = config or {}

    def get_manifest_db_path(self):
        return Path("fake.sqlite")

    def get_shared_manifest_id(self):
        return self.config.get("shared_manifest_id", "")

    def load_config(self):
        return dict(self.config)


class _FakeManifestDb:
    def __init__(self, manifests: list[dict]):
        self.manifests = manifests

    def list_manifests(self, db_path):
        return list(self.manifests)


def _load_input_module(fake_st: _FakeStreamlit):
    previous_streamlit = sys.modules.get("streamlit")
    sys.modules["streamlit"] = fake_st
    spec = importlib.util.spec_from_file_location(
        "_012_input_for_test", _HERE / "012_input.py"
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        if previous_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = previous_streamlit
    return mod


def test_render_input_without_manifest_returns_safe_defaults():
    fake_st = _FakeStreamlit()
    mod = _load_input_module(fake_st)
    mod._cfg = _FakeConfig()
    mod._mdb = _FakeManifestDb([])

    result = mod.render_input()

    assert result == {
        "manifest_id": "",
        "annotation_tool": "x-anylabeling",
        "labels": [],
        "classification_labels": [],
        "autorefresh_enabled": True,
        "autorefresh_seconds": 10,
    }


def test_render_input_preserves_contract_and_parses_lines():
    fake_st = _FakeStreamlit()
    mod = _load_input_module(fake_st)
    mod._cfg = _FakeConfig(
        {
            "shared_manifest_id": "manifest_2",
            "annotation_tool": "labelme",
            "annotation_labels": [" scratch ", "dent"],
            "classification_labels": ["OK"],
            "autorefresh_enabled": True,
            "autorefresh_seconds": 10,
        }
    )
    mod._mdb = _FakeManifestDb(
        [
            {"manifest_id": "manifest_1", "name": "old", "item_count": 1},
            {"manifest_id": "manifest_2", "name": "bull", "item_count": 16},
        ]
    )

    result = mod.render_input()

    assert result["manifest_id"] == "manifest_2"
    assert result["annotation_tool"] == "labelme"
    assert result["labels"] == ["scratch", "dent"]
    assert result["classification_labels"] == ["OK"]
    assert result["autorefresh_enabled"] is True
    assert result["autorefresh_seconds"] == 10


def test_render_input_defaults_labels_to_empty_for_new_config():
    fake_st = _FakeStreamlit()
    mod = _load_input_module(fake_st)
    mod._cfg = _FakeConfig({"autorefresh_enabled": True, "autorefresh_seconds": 10})
    mod._mdb = _FakeManifestDb(
        [{"manifest_id": "manifest_1", "name": "fresh", "item_count": 1}]
    )

    result = mod.render_input()

    assert result["labels"] == []
    assert fake_st.session_state["m012_labels_raw"] == ""
