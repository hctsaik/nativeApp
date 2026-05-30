"""
tests/annotation/test_integration_profile.py
---------------------------------------------
整合層單元測試：
- SystemTenant 載入與驗證
- FakeConnector（get_ant_list / get_ant_task_detail / health_check）
- FileConnector（本地檔案模擬外部系統）
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.labeling.domain.integrations.connectors.fake_connector import FakeConnector
from plugins.labeling.domain.integrations.connectors.file_connector import FileConnector
from plugins.labeling.domain.integrations.profiles import SystemTenant, load_profile, load_profile_from_file


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _valid_tenant_dict(**overrides) -> dict:
    base = {
        "tenant_id": "tenant-001",
        "system_name": "AOI-System-A",
        "server_host_name": "https://aoi.internal",
        "target_format": "coco",
    }
    base.update(overrides)
    return base


def _fake_connector(n: int = 2) -> FakeConnector:
    tasks = [
        {
            "antID": f"TASK_{i:03d}",
            "antActive": 0,
            "antPeriod": "2026-05-26T08:00:00Z",
            "external_context": {"lot_id": f"L{i}", "eqp_id": "AOI-01"},
        }
        for i in range(n)
    ]
    return FakeConnector(tasks=tasks, download_url="file:///fake/payload.zip")


# ---------------------------------------------------------------------------
# SystemTenant — 正常載入
# ---------------------------------------------------------------------------

def test_load_valid_tenant():
    tenant = load_profile(_valid_tenant_dict())
    assert tenant.tenant_id == "tenant-001"
    assert tenant.system_name == "AOI-System-A"
    assert tenant.server_host_name == "https://aoi.internal"
    assert tenant.target_format == "coco"
    assert tenant.api_token is None


def test_load_strips_trailing_slash():
    tenant = load_profile(_valid_tenant_dict(server_host_name="https://aoi.internal/"))
    assert tenant.server_host_name == "https://aoi.internal"


def test_load_api_token_optional():
    tenant = load_profile(_valid_tenant_dict(api_token="secret-token"))
    assert tenant.api_token == "secret-token"


# ---------------------------------------------------------------------------
# SystemTenant — 必填欄位驗證
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field", [
    "tenant_id", "system_name", "server_host_name", "target_format"
])
def test_load_missing_required_raises(missing_field: str):
    data = _valid_tenant_dict()
    del data[missing_field]
    with pytest.raises(ValueError, match=missing_field):
        load_profile(data)


@pytest.mark.parametrize("empty_field", [
    "tenant_id", "system_name", "server_host_name", "target_format"
])
def test_load_empty_string_raises(empty_field: str):
    data = _valid_tenant_dict(**{empty_field: "   "})
    with pytest.raises(ValueError, match=empty_field):
        load_profile(data)


# ---------------------------------------------------------------------------
# SystemTenant — 從檔案載入
# ---------------------------------------------------------------------------

def test_load_from_file(tmp_path: Path):
    profile_file = tmp_path / "tenant.json"
    profile_file.write_text(json.dumps(_valid_tenant_dict(system_name="file-system")))
    tenant = load_profile_from_file(profile_file)
    assert tenant.system_name == "file-system"


def test_load_from_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_profile_from_file(tmp_path / "nonexistent.json")


# ---------------------------------------------------------------------------
# FakeConnector — get_ant_list
# ---------------------------------------------------------------------------

def test_fake_get_ant_list_returns_all_tasks():
    connector = _fake_connector(n=3)
    tasks = connector.get_ant_list()
    assert len(tasks) == 3


def test_fake_get_ant_list_maps_ant_id():
    connector = _fake_connector(n=2)
    tasks = connector.get_ant_list()
    assert tasks[0].ant_id == "TASK_000"
    assert tasks[1].ant_id == "TASK_001"


def test_fake_get_ant_list_preserves_external_context():
    connector = _fake_connector(n=1)
    tasks = connector.get_ant_list()
    assert tasks[0].external_context["lot_id"] == "L0"
    assert tasks[0].external_context["eqp_id"] == "AOI-01"


def test_fake_get_ant_list_ant_active_default_zero():
    connector = FakeConnector(tasks=[{"antID": "T1"}])
    tasks = connector.get_ant_list()
    assert tasks[0].ant_active == 0


# ---------------------------------------------------------------------------
# FakeConnector — get_ant_task_detail
# ---------------------------------------------------------------------------

def test_fake_get_ant_task_detail_returns_download_url():
    connector = _fake_connector()
    resp = connector.get_ant_task_detail("TASK_000", "coco")
    assert resp.download_url == "file:///fake/payload.zip"


def test_fake_get_ant_task_detail_records_calls():
    connector = _fake_connector()
    connector.get_ant_task_detail("TASK_000", "coco")
    connector.get_ant_task_detail("TASK_001", "yolo-detection")
    calls = connector.get_detail_calls()
    assert len(calls) == 2
    assert calls[0] == {"ant_id": "TASK_000", "format": "coco"}
    assert calls[1] == {"ant_id": "TASK_001", "format": "yolo-detection"}


# ---------------------------------------------------------------------------
# FakeConnector — health_check
# ---------------------------------------------------------------------------

def test_fake_health_check_always_connected():
    connector = _fake_connector()
    health = connector.health_check()
    assert health.connected is True
    assert health.latency_ms == 0
    assert health.error is None


# ---------------------------------------------------------------------------
# FileConnector — get_ant_list
# ---------------------------------------------------------------------------

def test_file_connector_get_ant_list(tmp_path: Path):
    ant_list = [
        {"antID": "ANT_001", "antActive": 0, "antPeriod": "2026-05-26T08:00:00Z"},
        {"antID": "ANT_002", "antActive": 1, "external_context": {"lot_id": "L99"}},
    ]
    list_file = tmp_path / "ant_list.json"
    list_file.write_text(json.dumps(ant_list), encoding="utf-8")

    tenant = load_profile(_valid_tenant_dict())
    connector = FileConnector(tenant, ant_list_path=str(list_file))
    tasks = connector.get_ant_list()

    assert len(tasks) == 2
    assert tasks[0].ant_id == "ANT_001"
    assert tasks[1].external_context["lot_id"] == "L99"


def test_file_connector_get_ant_list_missing_file(tmp_path: Path):
    tenant = load_profile(_valid_tenant_dict())
    connector = FileConnector(tenant, ant_list_path=str(tmp_path / "missing.json"))
    with pytest.raises(FileNotFoundError):
        connector.get_ant_list()


# ---------------------------------------------------------------------------
# FileConnector — get_ant_task_detail
# ---------------------------------------------------------------------------

def test_file_connector_get_ant_task_detail_returns_file_url(tmp_path: Path):
    tenant = load_profile(_valid_tenant_dict())
    connector = FileConnector(tenant, zip_root=str(tmp_path))
    resp = connector.get_ant_task_detail("ANT_001", "coco")
    assert "ANT_001.zip" in resp.download_url
    assert resp.download_url.startswith("file:///")


# ---------------------------------------------------------------------------
# FileConnector — health_check
# ---------------------------------------------------------------------------

def test_file_connector_health_connected(tmp_path: Path):
    list_file = tmp_path / "ant_list.json"
    list_file.write_text("[]")
    tenant = load_profile(_valid_tenant_dict())
    connector = FileConnector(tenant, ant_list_path=str(list_file))
    health = connector.health_check()
    assert health.connected is True


def test_file_connector_health_disconnected(tmp_path: Path):
    tenant = load_profile(_valid_tenant_dict())
    connector = FileConnector(tenant, ant_list_path=str(tmp_path / "missing.json"))
    health = connector.health_check()
    assert health.connected is False
    assert health.error is not None
