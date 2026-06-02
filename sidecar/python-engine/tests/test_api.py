from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import subprocess

import pytest
from fastapi.testclient import TestClient

from engine import (
    MockToolAdapter,
    SelectedPathStore,
    SQLiteToolAdapter,
    ToolDefinition,
    ToolProcessManager,
    ToolRegistry,
    ToolStartResponse,
    create_app,
    resolve_tools_db_path,
)
from management_store import SQLiteManagementStore


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(MockToolAdapter())
    db_path = tmp_path / "data" / "tools.sqlite"
    manager = ToolProcessManager(tmp_path, tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)
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
    # Submodule guard surfaces here so the portal can show a banner; empty list
    # in this checked-out repo, list-of-descriptors when submodules are missing.
    assert isinstance(body["missing_submodules"], list)


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

    manager = ToolProcessManager(
        tmp_path / "logs",
        tmp_path / "selected_paths.json",
        tmp_path / "data" / "tools.sqlite",
    )
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


def test_sheet_start_is_lazy_and_can_start_tab_on_demand(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(MockToolAdapter())
    app = create_app(manager, registry, selected_paths, db_path)
    client = TestClient(app, raise_server_exceptions=False)

    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO sheets (sheet_id, name) VALUES (?, ?)", ("lazy_sheet", "Lazy Sheet"))
        conn.executemany(
            "INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label) VALUES (?, ?, ?, ?)",
            [
                ("lazy_sheet", 0, "module_a", "Module A"),
                ("lazy_sheet", 1, "module_b", "Module B"),
            ],
        )

    script = tmp_path / "lazy_sheet.py"
    script.write_text("print('ok')", encoding="utf-8")
    tool = ToolDefinition("sheet-lazy_sheet", "Lazy Sheet", script, "0.1.0")

    processes = []
    for pid in range(100, 106):
        proc = MagicMock()
        proc.pid = pid
        proc.poll.return_value = None
        processes.append(proc)

    with (
        patch.object(manager, "_spawn", side_effect=processes) as spawn,
        patch("engine.wait_for_port", return_value=True),
        patch("engine.threading.Thread") as thread_cls,
    ):
        thread_cls.return_value.start.return_value = None
        result = manager.start(tool)

        assert spawn.call_count == 2
        assert result.sheet_tabs[0].plugin_id == "module_a"
        assert result.sheet_tabs[0].ready is True
        assert result.sheet_tabs[1].plugin_id == "module_b"
        assert result.sheet_tabs[1].ready is False
        assert result.sheet_tabs[1].input_url == ""

        status = client.get("/tools/active/status").json()
        assert status["sheet_tab_ready"] == {"module_a": True, "module_b": False}

        response = client.post("/tools/active/sheet-tab/module_b/start")
        assert response.status_code == 200
        assert response.json()["ready"] is True
        assert spawn.call_count == 4

        status = client.get("/tools/active/status").json()
        assert status["sheet_tab_ready"] == {"module_a": True, "module_b": True}
        assert "module_b" in status["sheet_tab_urls"]

    manager.stop()


def test_app_tool_status_reports_single_process_alive(tmp_path: Path) -> None:
    """An 'app' tool (e.g. AI4BI) runs ONE Streamlit process — _start_app sets
    _input_process only, never _output_process. The status endpoint must report
    output_alive from that single process, not from the never-spawned output
    process; otherwise the portal poller shows a false 'Output 程序已停止' banner
    even though the app is running fine. Regression for the AI4BI integration.
    """
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(MockToolAdapter())
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)
    client = TestClient(app, raise_server_exceptions=False)

    # Simulate a live app tool: single process, no output pane.
    proc = MagicMock()
    proc.poll.return_value = None  # alive
    manager._tool_id = "app-ai4bi"
    manager._input_process = proc
    manager._output_process = None  # app tools never spawn one
    manager._input_port = 59812
    manager._run_id = "run-app"

    status = client.get("/tools/active/status").json()
    assert status["active"] is True
    assert status["category"] == "app"
    assert status["input_alive"] is True
    assert status["output_alive"] is True  # NOT false despite _output_process is None
    assert status["input_url"] == status["output_url"] == "http://127.0.0.1:59812"

    manager.stop()


# ---------------------------------------------------------------------------
# Management DB path
# ---------------------------------------------------------------------------


def test_resolve_tools_db_path_defaults_to_log_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIM_TOOLS_DB", raising=False)
    assert resolve_tools_db_path(tmp_path) == (tmp_path / "data" / "tools.sqlite").resolve()


def test_resolve_tools_db_path_uses_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "custom.sqlite"
    monkeypatch.setenv("CIM_TOOLS_DB", str(override))
    assert resolve_tools_db_path(tmp_path) == override.resolve()


def test_prod_enabled_endpoint_blocks_unpublished_module(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)

    response = TestClient(app, raise_server_exceptions=False).patch(
        "/tools/module_001/prod-enabled",
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "Module cannot be shown in Prod yet."
    assert "Publish an active snapshot" in response.json()["detail"]["issues"][0]


def test_prod_enabled_endpoint_blocks_malformed_module_snapshot(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    store = SQLiteManagementStore(db_path)
    store.publish_tool_snapshot("module_001", "Module 001", "1.0.0", "{}", "bad", "tester")
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)

    response = TestClient(app, raise_server_exceptions=False).patch(
        "/tools/module_001/prod-enabled",
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert "Active snapshot content is empty" in response.json()["detail"]["issues"][0]


def test_prod_enabled_endpoint_uses_sheet_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    store = SQLiteManagementStore(db_path)
    store.upsert_sheet(
        "blocked",
        "Blocked Sheet",
        "",
        [{"plugin_id": "module_001", "label": "Unpublished Module"}],
    )
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)

    response = TestClient(app, raise_server_exceptions=False).patch(
        "/tools/sheet-blocked/prod-enabled",
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["message"] == "Sheet cannot be shown in Prod yet."
    assert store.get_sheet_row("blocked")["enabled_prod"] == 0
    assert store.get_tool_catalog_row("sheet-blocked")["enabled_prod"] == 0


def test_prod_enabled_endpoint_blocks_empty_sheet(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    store = SQLiteManagementStore(db_path)
    store.upsert_sheet("empty", "Empty Sheet", "", [])
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)

    response = TestClient(app, raise_server_exceptions=False).patch(
        "/tools/sheet-empty/prod-enabled",
        json={"enabled": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["issues"][0]["issue"] == "Sheet has no tabs."
    assert store.get_sheet_row("empty")["enabled_prod"] == 0


def test_prod_enabled_endpoint_rejects_unknown_tool(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)

    response = TestClient(app, raise_server_exceptions=False).patch(
        "/tools/does-not-exist/prod-enabled",
        json={"enabled": True},
    )

    assert response.status_code == 404


def test_runs_and_usage_endpoints_return_management_store_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    store = SQLiteManagementStore(db_path)
    run_id = store.start_tool_run("module_001", "module", "iframe", actor="tester")
    store.finish_tool_run(run_id, "stopped")
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)
    client = TestClient(app, raise_server_exceptions=False)

    runs = client.get("/runs").json()
    usage = client.get("/usage/summary").json()

    assert runs[0]["run_id"] == run_id
    assert usage[0]["tool_id"] == "module_001"
    assert usage[0]["run_count"] == 1


def test_startup_sync_does_not_enable_prod_from_yaml(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    SQLiteToolAdapter(db_path)
    store = SQLiteManagementStore(db_path)
    store.set_tool_prod_enabled("module_001", False)

    SQLiteToolAdapter(db_path)

    assert store.get_tool_catalog_row("module_001")["enabled_prod"] == 0


def test_prod_tools_list_hides_invalid_prod_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    selected_paths = SelectedPathStore(tmp_path / "selected_paths.json")
    registry = ToolRegistry(SQLiteToolAdapter(db_path))
    store = SQLiteManagementStore(db_path)
    store.publish_tool_snapshot("module_001", "Module 001", "1.0.0", json.dumps({}), "bad", "tester")
    manager = ToolProcessManager(tmp_path / "logs", tmp_path / "selected_paths.json", db_path)
    app = create_app(manager, registry, selected_paths, db_path)
    monkeypatch.setenv("CIM_DEV_MODE", "0")

    response = TestClient(app, raise_server_exceptions=False).get("/tools")

    assert response.status_code == 200
    assert "module_001" not in {tool["tool_id"] for tool in response.json()}


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
# Hot-reload + RBAC role endpoints (behavioral, not string-assertion guards)
# ---------------------------------------------------------------------------

def test_reload_endpoint_rescans_catalog(client: TestClient) -> None:
    response = client.post("/reload")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "total" in body and isinstance(body.get("added"), list)
    assert "connectors" in body  # autodiscover ran (symmetry with module/sheet reload)


def test_whoami_reports_role_and_roles(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import auth_provider
    monkeypatch.setattr(auth_provider, "default_identity_file", lambda: tmp_path / "absent.json")
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("CIM_USER_ROLE", raising=False)
    body = client.get("/whoami").json()
    assert body["role"] == "admin"
    assert set(body["roles"]) == {"admin", "operator", "viewer"}


def test_set_role_then_whoami_roundtrip(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import auth_provider
    monkeypatch.setattr(auth_provider, "default_identity_file", lambda: tmp_path / "id.json")
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("CIM_USER_ROLE", raising=False)
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    assert client.post("/set-role", json={"role": "operator"}).status_code == 200
    assert client.get("/whoami").json()["role"] == "operator"
    # invalid role rejected
    assert client.post("/set-role", json={"role": "bogus"}).status_code == 400


def test_set_role_blocked_in_prod(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    assert client.post("/set-role", json={"role": "operator"}).status_code == 403


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
