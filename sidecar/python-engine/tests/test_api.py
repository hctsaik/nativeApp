from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import pytest
from fastapi.testclient import TestClient

from engine import (
    MockToolAdapter,
    SelectedPathStore,
    ToolDefinition,
    ToolProcessManager,
    ToolRegistry,
    ToolStartResponse,
    create_app,
)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(MockToolAdapter())
    manager = ToolProcessManager(tmp_path, tmp_path / "selected_paths.json")
    app = create_app(manager, registry, selected_paths)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_runtime_endpoint_reports_sidecar_shape(client: TestClient) -> None:
    with patch.object(ToolProcessManager, "_labelme_dino_probe", return_value={"ok": False, "error": "missing"}):
        response = client.get("/runtime")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert "python" in body
    assert "paths" in body
    assert body["labelme_dino"]["ok"] is False


def test_diagnostics_endpoint_reports_active_tool_shape(client: TestClient) -> None:
    with patch.object(ToolProcessManager, "_labelme_dino_probe", return_value={"ok": False, "error": "missing"}):
        response = client.get("/diagnostics")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["active_tool"] == {"active": False}
    assert "runtime" in body


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

def test_list_tools_returns_registered_tools(client: TestClient) -> None:
    response = client.get("/tools")
    assert response.status_code == 200
    tools = response.json()
    assert isinstance(tools, list)
    assert any(t["tool_id"] == "sample-csv" for t in tools)


def test_list_tools_response_shape(client: TestClient) -> None:
    tools = client.get("/tools").json()
    for tool in tools:
        assert "tool_id" in tool
        assert "name" in tool
        assert "version" in tool
        assert "category" in tool


def test_list_tools_category_values(client: TestClient) -> None:
    tools = client.get("/tools").json()
    valid = {"module", "workflow", "management", "tool", "external"}
    for tool in tools:
        assert tool["category"] in valid


# ---------------------------------------------------------------------------
# Tool start
# ---------------------------------------------------------------------------

def test_start_unknown_tool_returns_404(client: TestClient) -> None:
    response = client.post("/tools/does-not-exist/start")
    assert response.status_code == 404


def test_start_tool_returns_input_output_urls(client: TestClient, tmp_path: Path) -> None:
    fake_response = ToolStartResponse(
        tool_id="sample-csv",
        input_url="http://127.0.0.1:9998",
        output_url="http://127.0.0.1:9999",
        input_port=9998,
        output_port=9999,
    )
    with patch.object(ToolProcessManager, "start", return_value=fake_response):
        response = client.post("/tools/sample-csv/start")
    assert response.status_code == 200
    body = response.json()
    assert body["tool_id"] == "sample-csv"
    assert body["input_url"] == "http://127.0.0.1:9998"
    assert body["output_url"] == "http://127.0.0.1:9999"
    assert body["input_port"] == 9998
    assert body["output_port"] == 9999


def test_start_tool_missing_script_returns_500(client: TestClient) -> None:
    with patch.object(ToolProcessManager, "start", side_effect=FileNotFoundError("missing")):
        response = client.post("/tools/sample-csv/start")
    assert response.status_code == 500


def test_start_tool_readiness_timeout_returns_500(client: TestClient) -> None:
    with patch.object(ToolProcessManager, "start", side_effect=RuntimeError("did not become ready")):
        response = client.post("/tools/sample-csv/start")
    assert response.status_code == 500


def test_external_labelme_dino_start_returns_external_window(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    exe = tmp_path / "LabelMe_Dino.exe"
    exe.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("LABELME_DINO_EXE", str(exe))

    fake_proc = MagicMock()
    fake_proc.pid = 1234
    fake_proc.poll.return_value = None

    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json")
    tool = ToolDefinition(
        tool_id="labelme-dino",
        name="video_annotator",
        script_path=Path("external_labelme_dino"),
        version="0.1.0",
    )

    completed = subprocess.CompletedProcess(
        args=[str(exe), "--probe-runtime"],
        returncode=0,
        stdout='{"ok": true, "python": "3.11"}\n',
        stderr="",
    )

    with (
        patch("subprocess.run", return_value=completed) as run,
        patch("subprocess.Popen", return_value=fake_proc) as popen,
        patch.object(ToolProcessManager, "_wait_for_ready_file", return_value={"ok": True}),
    ):
        result = manager.start(tool)

    assert result.category == "external"
    assert result.mode == "external-window"
    assert result.pid == 1234
    assert result.ready is True
    assert result.run_id
    assert result.log_path
    run.assert_called_once()
    popen.assert_called_once()
    manager.stop()


# ---------------------------------------------------------------------------
# Tool stop
# ---------------------------------------------------------------------------

def test_stop_tool_when_idle_returns_stopped(client: TestClient) -> None:
    response = client.post("/tools/stop")
    assert response.status_code == 200
    assert response.json()["status"] == "stopped"


def test_stop_tool_calls_manager_stop(client: TestClient) -> None:
    with patch.object(ToolProcessManager, "stop") as mock_stop:
        response = client.post("/tools/stop")
    assert response.status_code == 200
    mock_stop.assert_called_once()


# ---------------------------------------------------------------------------
# Selected paths
# ---------------------------------------------------------------------------

def test_get_selected_paths_initially_empty(client: TestClient) -> None:
    response = client.get("/selected-paths")
    assert response.status_code == 200
    assert response.json()["paths"] == []


def test_set_selected_paths_round_trips(client: TestClient) -> None:
    paths = [r"C:\data\a.csv", r"C:\data\b.csv"]
    post_response = client.post("/selected-paths", json={"paths": paths})
    assert post_response.status_code == 200

    get_response = client.get("/selected-paths")
    result = get_response.json()["paths"]
    assert len(result) == len(paths)


def test_set_empty_paths_clears_previous(client: TestClient) -> None:
    client.post("/selected-paths", json={"paths": [r"C:\file.csv"]})
    client.post("/selected-paths", json={"paths": []})
    assert client.get("/selected-paths").json()["paths"] == []


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def test_shutdown_returns_shutting_down(client: TestClient) -> None:
    # Patch threading.Timer so the deferred os.kill never fires during tests.
    with patch("threading.Timer") as mock_timer:
        mock_timer.return_value = MagicMock()
        response = client.post("/shutdown")
    assert response.status_code == 200
    assert response.json()["status"] == "shutting_down"
    mock_timer.assert_called_once()
