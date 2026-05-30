"""Tests for the ConfigurableRestConnector envelope helpers (dig / extract_list /
resolve_paths). These let a no-code REST system declare where the task array
lives inside a wrapped response (`list_root: data.items`) — R6/R7 gap: the
functions existed but had no test coverage.
"""

from __future__ import annotations

from plugins.labeling.domain.integrations.connectors import (
    configurable_rest_connector as c,
)


def test_dig_walks_nested_dict():
    assert c.dig({"data": {"items": [1, 2]}}, "data.items") == [1, 2]


def test_dig_returns_none_on_miss():
    assert c.dig({"a": 1}, "x.y") is None


def test_extract_list_from_envelope():
    data = {"data": {"items": [{"id": "A"}, {"id": "B"}]}}
    assert c.extract_list(data, "data.items") == [{"id": "A"}, {"id": "B"}]


def test_extract_list_falls_back_to_bare_list():
    # list_root misses but the response itself is already the array → use it.
    assert c.extract_list([{"id": "X"}], "data.items") == [{"id": "X"}]


def test_extract_list_bare_response_no_root():
    assert c.extract_list([{"id": "Y"}], "") == [{"id": "Y"}]


def test_extract_list_non_list_returns_empty():
    assert c.extract_list({"foo": 1}, "") == []


def test_resolve_paths_carries_list_root_and_paths():
    rp = c.resolve_paths({"list_root": "data.items", "list_path": "/v2/tasks"})
    assert rp["list_root"] == "data.items"
    assert rp["list_path"] == "/v2/tasks"


def test_resolve_paths_defaults_when_empty():
    rp = c.resolve_paths(None)
    assert rp["list_root"] == ""  # default: response is the array
    assert rp["detail_root"] == ""
    assert "fields" in rp


def test_resolve_paths_carries_detail_root():
    rp = c.resolve_paths({"detail_root": "data"})
    assert rp["detail_root"] == "data"


def test_detail_envelope_dig_extracts_download_url():
    # mirrors get_ant_task_detail's envelope handling (detail_root='data')
    body = {"data": {"download_url": "http://x/y.zip"}}
    root = c.dig(body, "data")
    assert isinstance(root, dict) and root["download_url"] == "http://x/y.zip"


def test_coerce_active_tolerates_arbitrary_status():
    # numeric (int / numeric string) pass through
    assert c.coerce_active(2) == 2
    assert c.coerce_active("1") == 1
    # known status words map to 0/1/2
    assert c.coerce_active("pending") == 0
    assert c.coerce_active("Processing") == 1
    assert c.coerce_active("completed") == 2
    assert c.coerce_active("已標記") == 2
    # unknown / None never raises → 0 (a weird status must not break the list)
    assert c.coerce_active("weird-status") == 0
    assert c.coerce_active(None) == 0


def test_map_list_item_with_non_numeric_status():
    task = c.map_list_item({"antID": "A1", "antActive": "open"},
                           c.resolve_paths(None)["fields"])
    assert task.ant_id == "A1" and task.ant_active == 0  # no ValueError
