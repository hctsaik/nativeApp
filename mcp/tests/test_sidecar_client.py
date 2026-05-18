from __future__ import annotations

import pytest
import respx
import httpx

from cim_gui_mcp.sidecar_client import SidecarClient, SidecarError

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def client() -> SidecarClient:
    return SidecarClient(base_url=BASE, timeout=2.0)


# ── health ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_ok(client: SidecarClient):
    with respx.mock:
        respx.get(f"{BASE}/health").mock(
            return_value=httpx.Response(200, json={"status": "ok"})
        )
        result = await client.health()
    assert result == "ok"


@pytest.mark.asyncio
async def test_health_connection_error(client: SidecarClient):
    with respx.mock:
        respx.get(f"{BASE}/health").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(SidecarError, match="health check failed"):
            await client.health()


@pytest.mark.asyncio
async def test_health_non_200(client: SidecarClient):
    with respx.mock:
        respx.get(f"{BASE}/health").mock(return_value=httpx.Response(503))
        with pytest.raises(SidecarError):
            await client.health()


# ── list_tools ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_tools_returns_list(client: SidecarClient):
    payload = [
        {"tool_id": "cvmod-003", "name": "003 - 不規則邊框", "version": "0.1.0", "category": "module"},
        {"tool_id": "workflow-edge-analysis", "name": "邊緣分析", "version": "1.0.0", "category": "workflow"},
    ]
    with respx.mock:
        respx.get(f"{BASE}/tools").mock(return_value=httpx.Response(200, json=payload))
        result = await client.list_tools()
    assert len(result) == 2
    assert result[0]["tool_id"] == "cvmod-003"


@pytest.mark.asyncio
async def test_list_tools_error(client: SidecarClient):
    with respx.mock:
        respx.get(f"{BASE}/tools").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(SidecarError, match="list_tools failed"):
            await client.list_tools()


# ── start_tool ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_tool_returns_urls(client: SidecarClient):
    payload = {
        "tool_id": "cvmod-003",
        "input_url": "http://127.0.0.1:51234",
        "output_url": "http://127.0.0.1:51235",
        "input_port": 51234,
        "output_port": 51235,
    }
    with respx.mock:
        respx.post(f"{BASE}/tools/cvmod-003/start").mock(
            return_value=httpx.Response(200, json=payload)
        )
        result = await client.start_tool("cvmod-003")
    assert result["input_url"] == "http://127.0.0.1:51234"
    assert result["output_url"] == "http://127.0.0.1:51235"


@pytest.mark.asyncio
async def test_start_tool_404(client: SidecarClient):
    with respx.mock:
        respx.post(f"{BASE}/tools/bad-tool/start").mock(
            return_value=httpx.Response(404, json={"detail": "Unknown tool: bad-tool"})
        )
        with pytest.raises(SidecarError, match="404"):
            await client.start_tool("bad-tool")


@pytest.mark.asyncio
async def test_start_tool_connection_error(client: SidecarClient):
    with respx.mock:
        respx.post(f"{BASE}/tools/cvmod-003/start").mock(
            side_effect=httpx.ConnectError("refused")
        )
        with pytest.raises(SidecarError, match="start_tool"):
            await client.start_tool("cvmod-003")


# ── stop_tool ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_stop_tool_ok(client: SidecarClient):
    with respx.mock:
        respx.post(f"{BASE}/tools/stop").mock(
            return_value=httpx.Response(200, json={"status": "stopped"})
        )
        result = await client.stop_tool()
    assert result == "stopped"


@pytest.mark.asyncio
async def test_stop_tool_error(client: SidecarClient):
    with respx.mock:
        respx.post(f"{BASE}/tools/stop").mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(SidecarError, match="stop_tool failed"):
            await client.stop_tool()
