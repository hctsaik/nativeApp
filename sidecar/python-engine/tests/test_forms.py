"""Tests for core.forms — the declarative (no-code) input form layer."""

from __future__ import annotations

import pytest

from core import forms


# ─── schema validation (pure) ─────────────────────────────────────────────────

def test_normalize_schema_valid_mixed_fields():
    schema = [
        {"key": "threshold", "type": "number", "label": "閾值", "default": 0.5,
         "min": 0, "max": 1, "step": 0.05},
        {"key": "mode", "type": "select", "label": "模式", "options": ["fast", "accurate"], "default": "fast"},
        {"key": "name", "type": "text", "default": ""},
        {"key": "enabled", "type": "checkbox", "default": True},
    ]
    norm = forms.normalize_schema(schema)
    assert [f["key"] for f in norm] == ["threshold", "mode", "name", "enabled"]
    assert norm[2]["label"] == "name"  # label defaults to key


def test_normalize_schema_none_and_empty():
    assert forms.normalize_schema(None) == []
    assert forms.normalize_schema([]) == []


@pytest.mark.parametrize("bad,msg", [
    ("notalist", "list"),
    ([{"type": "text"}], "key"),
    ([{"key": "x", "type": "bogus"}], "不支援"),
    ([{"key": "x", "type": "select"}], "options"),
    ([{"key": "x", "type": "slider", "min": 0}], "min"),
    ([{"key": "a", "type": "text"}, {"key": "a", "type": "text"}], "重複"),
])
def test_normalize_schema_rejects_bad(bad, msg):
    with pytest.raises(forms.FormSchemaError) as exc:
        forms.normalize_schema(bad)
    assert msg in str(exc.value)


# ─── widget-call planning (pure) ──────────────────────────────────────────────

def test_widget_call_for_each_type():
    cases = {
        "text": ("text_input", "value"),
        "textarea": ("text_area", "value"),
        "checkbox": ("checkbox", "value"),
        "number": ("number_input", "value"),
        "select": ("selectbox", "options"),
        "multiselect": ("multiselect", "options"),
        "file": ("file_uploader", None),
    }
    for t, (method, key) in cases.items():
        f = {"key": "k", "type": t, "label": "L"}
        if t in ("select", "multiselect"):
            f["options"] = ["a", "b"]
        nf = forms.normalize_field(f)
        m, kwargs = forms.widget_call(nf)
        assert m == method
        if key:
            assert key in kwargs


def test_select_index_from_default():
    nf = forms.normalize_field({"key": "m", "type": "select", "options": ["a", "b", "c"], "default": "c"})
    _, kwargs = forms.widget_call(nf)
    assert kwargs["index"] == 2


def test_coerce_integer():
    f = forms.normalize_field({"key": "n", "type": "integer"})
    assert forms.coerce(f, 3.0) == 3 and isinstance(forms.coerce(f, 3.0), int)


# ─── render() with a fake streamlit ───────────────────────────────────────────

class _FakeSt:
    """Records widget calls and returns canned values keyed by widget method."""
    def __init__(self, returns: dict):
        self.returns = returns
        self.calls: list[tuple[str, dict]] = []

    def _mk(self, name):
        def _w(**kwargs):
            self.calls.append((name, kwargs))
            return self.returns.get(name)
        return _w

    def __getattr__(self, name):
        return self._mk(name)


def test_render_collects_values_and_coerces():
    schema = [
        {"key": "name", "type": "text", "default": "x"},
        {"key": "count", "type": "integer", "default": 1},
        {"key": "mode", "type": "select", "options": ["a", "b"], "default": "b"},
    ]
    st = _FakeSt({"text_input": "hello", "number_input": 4.0, "selectbox": "b"})
    params = forms.render(schema, st)
    assert params == {"name": "hello", "count": 4, "mode": "b"}
    assert isinstance(params["count"], int)
    # one widget call per field
    assert [c[0] for c in st.calls] == ["text_input", "number_input", "selectbox"]
