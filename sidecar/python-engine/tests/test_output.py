"""Tests for core.output — the declarative (no-code) output layer."""

from __future__ import annotations

import pytest

from core import output


def test_normalize_schema_valid():
    schema = [
        {"type": "text", "label": "標題", "key": "title"},
        {"type": "metric", "label": "行數", "key": "count"},
        {"type": "list", "key": "lines"},
        {"type": "markdown", "value": "## hi"},
    ]
    norm = output.normalize_schema(schema)
    assert [b["type"] for b in norm] == ["text", "metric", "list", "markdown"]


def test_normalize_schema_none():
    assert output.normalize_schema(None) == []


@pytest.mark.parametrize("bad,msg", [
    ("notalist", "list"),
    ([{"type": "bogus", "key": "x"}], "不支援"),
    ([{"type": "text"}], "key"),
])
def test_normalize_schema_rejects_bad(bad, msg):
    with pytest.raises(output.OutputSchemaError) as exc:
        output.normalize_schema(bad)
    assert msg in str(exc.value)


class _FakeSt:
    def __init__(self):
        self.calls: list[tuple] = []

    def __getattr__(self, name):
        def _w(*args, **kwargs):
            self.calls.append((name, args, kwargs))
        return _w


def test_render_dispatches_blocks_to_widgets():
    schema = [
        {"type": "text", "label": "標題", "key": "title"},
        {"type": "metric", "label": "行數", "key": "count"},
        {"type": "list", "key": "lines"},
        {"type": "json", "key": "data"},
        {"type": "markdown", "value": "## hi"},
    ]
    result = {"title": "HI", "count": 2, "lines": ["a", "b"], "data": {"k": 1}}
    st = _FakeSt()
    output.render(schema, result, st)
    methods = [c[0] for c in st.calls]
    assert methods[0] == "write"      # text
    assert "metric" in methods
    # list → 2 writes; json → st.json; markdown → st.markdown
    assert methods.count("write") >= 3
    assert "json" in methods and "markdown" in methods


def test_render_value_literal_and_missing_key():
    st = _FakeSt()
    output.render([{"type": "markdown", "value": "X"},
                   {"type": "list", "key": "missing"}], {}, st)
    assert ("markdown", ("X",), {}) in st.calls  # literal value rendered
    # missing list key → no crash, renders nothing for the list
