"""Declarative REST connector — pure mapping helpers + registry selection."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plugins.labeling.domain.core.models import SystemTenant
from plugins.labeling.domain.integrations import registry
from plugins.labeling.domain.integrations.connectors.configurable_rest_connector import (
    map_list_item,
    resolve_paths,
)


def test_resolve_paths_defaults_to_iwsc_contract():
    m = resolve_paths(None)
    assert m["list_path"] == "/getAntList"
    assert m["detail_path"] == "/getAntTaskDetail"
    assert m["fields"]["ant_id"] == "antID"


def test_resolve_paths_overrides_partial():
    m = resolve_paths({"list_path": "/v2/tasks", "fields": {"ant_id": "id"}})
    assert m["list_path"] == "/v2/tasks"
    assert m["detail_path"] == "/getAntTaskDetail"   # untouched default
    assert m["fields"]["ant_id"] == "id"             # overridden
    assert m["fields"]["ant_period"] == "antPeriod"  # default kept


def test_map_list_item_with_custom_fields():
    fields = resolve_paths({"fields": {"ant_id": "id", "ant_active": "status",
                                       "ant_period": "due"}})["fields"]
    task = map_list_item({"id": "T1", "status": 1, "due": "2026-01-01",
                          "lot": "L9"}, fields)
    assert task.ant_id == "T1"
    assert task.ant_active == 1
    assert task.ant_period == "2026-01-01"
    assert task.external_context == {"lot": "L9"}   # unmapped keys preserved


def test_map_list_item_default_shaped_payload_still_works():
    fields = resolve_paths(None)["fields"]
    task = map_list_item({"antID": "A1", "antActive": 0, "antPeriod": "p",
                          "eqp": "AOI"}, fields)
    assert task.ant_id == "A1" and task.ant_active == 0
    assert task.external_context == {"eqp": "AOI"}


def test_registry_uses_configurable_when_config_present():
    t = SystemTenant(
        tenant_id="t", system_name="acme", server_host_name="https://acme/api",
        target_format="coco", connector_config={"list_path": "/v2/tasks"})
    c = registry.build_connector(t)
    assert type(c).__name__ == "ConfigurableRestConnector"
    assert c._m["list_path"] == "/v2/tasks"


def test_registry_uses_plain_rest_when_no_config():
    t = SystemTenant(
        tenant_id="t", system_name="iwsc", server_host_name="http://localhost:8765",
        target_format="xanylabeling")
    assert type(registry.build_connector(t)).__name__ == "RestConnector"
