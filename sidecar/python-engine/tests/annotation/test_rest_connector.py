"""
tests/annotation/test_rest_connector.py
----------------------------------------
RestConnector 單元測試，使用 respx 攔截 httpx 請求，不發起任何真實網路連線。
"""
from __future__ import annotations

import httpx
import pytest
import respx

from plugins.labeling.domain.integrations.connectors.rest_connector import RestConnector
from plugins.labeling.domain.integrations.contracts import AntTask, ConnectorHealth, TaskDetailResponse
from plugins.labeling.domain.integrations.profiles import SystemTenant

# ── 共用 fixture ───────────────────────────────────────────────────────────────

BASE = "http://test.local"

TENANT = SystemTenant(
    tenant_id="tenant-001",
    system_name="test-system",
    server_host_name=BASE,
    target_format="coco",
    api_token="tok-abc123",
)

ANT_LIST_PAYLOAD = [
    {
        "antID": "ANT-001",
        "antActive": 2,
        "antPeriod": "2025-01-01T00:00:00Z",
        "lot_id": "LOT-A",
    },
    {
        "antID": "ANT-002",
        "antActive": 0,
        "antPeriod": None,
    },
]


# ── get_ant_list ──────────────────────────────────────────────────────────────


def test_get_ant_list_success():
    """GET /getAntList 200 → 回傳正確的 AntTask 列表。"""
    with respx.mock:
        respx.get(f"{BASE}/getAntList").mock(
            return_value=httpx.Response(200, json=ANT_LIST_PAYLOAD)
        )
        connector = RestConnector(TENANT)
        result = connector.get_ant_list()

    assert isinstance(result, list)
    assert len(result) == 2

    first = result[0]
    assert isinstance(first, AntTask)
    assert first.ant_id == "ANT-001"
    assert first.ant_active == 2
    assert first.ant_period == "2025-01-01T00:00:00Z"
    # lot_id 應被透傳到 external_context
    assert first.external_context.get("lot_id") == "LOT-A"

    second = result[1]
    assert second.ant_id == "ANT-002"
    assert second.ant_active == 0


def test_get_ant_list_unauthorized():
    """GET /getAntList 401 → raise PermissionError。"""
    with respx.mock:
        respx.get(f"{BASE}/getAntList").mock(
            return_value=httpx.Response(401, json={"detail": "Unauthorized"})
        )
        connector = RestConnector(TENANT)
        with pytest.raises(PermissionError):
            connector.get_ant_list()


def test_get_ant_list_request_carries_auth_header():
    """GET /getAntList 應帶有正確的 Authorization header。"""
    with respx.mock:
        route = respx.get(f"{BASE}/getAntList").mock(
            return_value=httpx.Response(200, json=[])
        )
        connector = RestConnector(TENANT)
        connector.get_ant_list()

    sent_request = route.calls[0].request
    assert sent_request.headers.get("authorization") == "Bearer tok-abc123"


# ── get_ant_task_detail ───────────────────────────────────────────────────────


def test_get_ant_task_detail_success():
    """POST /getAntTaskDetail 200 → 回傳正確的 TaskDetailResponse.download_url。"""
    with respx.mock:
        respx.post(f"{BASE}/getAntTaskDetail").mock(
            return_value=httpx.Response(
                200,
                json={"download_url": "https://storage.example.com/task-001.zip"},
            )
        )
        connector = RestConnector(TENANT)
        result = connector.get_ant_task_detail("ANT-001", "coco")

    assert isinstance(result, TaskDetailResponse)
    assert result.download_url == "https://storage.example.com/task-001.zip"


def test_get_ant_task_detail_server_error():
    """POST /getAntTaskDetail 500 → raise RuntimeError（含 status code）。"""
    with respx.mock:
        respx.post(f"{BASE}/getAntTaskDetail").mock(
            return_value=httpx.Response(500, text="Internal Server Error")
        )
        connector = RestConnector(TENANT)
        with pytest.raises(RuntimeError) as exc_info:
            connector.get_ant_task_detail("ANT-001", "coco")

    assert "500" in str(exc_info.value)


def test_get_ant_task_detail_sends_correct_body():
    """POST /getAntTaskDetail 應傳送 {antID, format} JSON body。"""
    with respx.mock:
        route = respx.post(f"{BASE}/getAntTaskDetail").mock(
            return_value=httpx.Response(200, json={"download_url": "http://x/a.zip"})
        )
        connector = RestConnector(TENANT)
        connector.get_ant_task_detail("ANT-XYZ", "yolo-detection")

    import json as _json
    sent_body = _json.loads(route.calls[0].request.content)
    assert sent_body == {"antID": "ANT-XYZ", "format": "yolo-detection"}


# ── health_check ──────────────────────────────────────────────────────────────


def test_health_check_connected():
    """GET /getAntList 能連上 → connected=True，latency_ms 為非負整數。"""
    with respx.mock:
        respx.get(f"{BASE}/getAntList").mock(
            return_value=httpx.Response(200, json=[])
        )
        connector = RestConnector(TENANT)
        result = connector.health_check()

    assert isinstance(result, ConnectorHealth)
    assert result.connected is True
    assert result.latency_ms is not None
    assert result.latency_ms >= 0
    assert result.error is None


def test_health_check_disconnected():
    """連線發生例外 → connected=False，error 含錯誤訊息。"""
    with respx.mock:
        respx.get(f"{BASE}/getAntList").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        connector = RestConnector(TENANT)
        result = connector.health_check()

    assert isinstance(result, ConnectorHealth)
    assert result.connected is False
    assert result.error is not None
    assert len(result.error) > 0
