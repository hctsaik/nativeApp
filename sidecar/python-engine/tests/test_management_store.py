from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from management_store import SQLiteManagementStore
from plugin_registry import PluginRegistry


@pytest.fixture()
def scripts_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "module_aaa"
    folder.mkdir()
    manifest = {
        "id": "module_aaa",
        "name": "Module A",
        "version": "1.0.0",
        "category": "module",
        "runner": "cv_framework",
    }
    (folder / "plugin.yaml").write_text(yaml.dump(manifest), encoding="utf-8")
    (folder / "aaa_input.py").write_text("def render_input(): return {}\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def db_path(tmp_path: Path, scripts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    path = tmp_path / "data" / "tools.sqlite"
    registry = PluginRegistry(db_path=path, scripts_dir=scripts_dir)
    registry.list_plugins()
    return path


@pytest.fixture()
def store(db_path: Path) -> SQLiteManagementStore:
    return SQLiteManagementStore(db_path)


def test_store_reports_database_exists(store: SQLiteManagementStore) -> None:
    assert store.database_exists() is True


def test_store_lists_tool_readiness_records(store: SQLiteManagementStore) -> None:
    rows = store.list_tool_readiness_records()

    assert rows[0]["tool_id"] == "module_aaa"
    assert rows[0]["active_version"] is None
    assert rows[0]["version_count"] == 0


def test_store_updates_tool_visibility_and_prod(store: SQLiteManagementStore) -> None:
    store.set_tool_enabled("module_aaa", False)
    store.set_tool_prod_enabled("module_aaa", True)

    rows = store.list_archived_tool_rows()

    assert rows[0]["tool_id"] == "module_aaa"
    assert rows[0]["enabled_prod"] == 1


def test_store_updates_plugin_mode_flag(store: SQLiteManagementStore) -> None:
    store.set_plugin_enabled("module_aaa", True, mode="prod")

    rows = store.list_tool_readiness_records()

    assert rows[0]["enabled_prod"] == 1


def test_store_rejects_unknown_plugin_mode(store: SQLiteManagementStore) -> None:
    with pytest.raises(ValueError):
        store.set_plugin_enabled("module_aaa", True, mode="qa")


def test_store_updates_tool_order(store: SQLiteManagementStore) -> None:
    store.update_tool_order({"module_aaa": 42})

    rows = store.list_visible_tool_rows()

    assert rows[0]["order_index"] == 42


def test_store_returns_enabled_tool_definition_rows(store: SQLiteManagementStore) -> None:
    rows = store.list_enabled_tool_definition_rows()

    assert rows[0]["tool_id"] == "module_aaa"
    assert rows[0]["script_relative_path"] == "cv_framework_runner.py"


def test_store_gets_enabled_tool_definition_row(store: SQLiteManagementStore) -> None:
    row = store.get_enabled_tool_definition_row("module_aaa")

    assert row is not None
    assert row["tool_id"] == "module_aaa"


def test_store_lists_tools_with_prod_flags(store: SQLiteManagementStore) -> None:
    rows = store.list_tools_with_prod_flags()

    assert ("module_aaa", "Module A", True, False) in rows


def test_store_contract_publishes_and_activates_versions(store: SQLiteManagementStore) -> None:
    v1 = store.publish_tool_snapshot(
        "module_aaa",
        "Module A",
        "1.0.0",
        '{"plugin.yaml": "name: Module A"}',
        "v1",
        "alice",
    )
    v2 = store.publish_tool_snapshot(
        "module_aaa",
        "Module A",
        "1.0.1",
        '{"plugin.yaml": "name: Module A"}',
        "v2",
        "bob",
    )

    rows = store.list_version_rows("module_aaa")
    active = [row for row in rows if row["is_active"]]

    assert [row["version_id"] for row in active] == [v2]
    store.activate_tool_version("module_aaa", v1)
    rows = store.list_version_rows("module_aaa")
    active = [row for row in rows if row["is_active"]]
    assert [row["version_id"] for row in active] == [v1]


def test_store_contract_invalid_activate_preserves_active_version(store: SQLiteManagementStore) -> None:
    v1 = store.publish_tool_snapshot("module_aaa", "Module A", "1.0.0", "{}", "v1", "alice")

    with pytest.raises(KeyError):
        store.activate_tool_version("module_aaa", 999999)

    active = [row for row in store.list_version_rows("module_aaa") if row["is_active"]]
    assert [row["version_id"] for row in active] == [v1]


def test_store_contract_manages_sheet_lifecycle(store: SQLiteManagementStore) -> None:
    store.upsert_sheet(
        "sheet_one",
        "Sheet One",
        "Demo",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )

    assert store.count_sheets() == 1
    assert store.list_sheet_ids() == ["sheet_one"]
    assert store.get_sheet_row("sheet_one")["name"] == "Sheet One"
    assert store.list_sheet_tabs_with_order("sheet_one")[0]["plugin_id"] == "module_aaa"

    store.set_sheet_enabled("sheet_one", True, mode="prod")
    assert store.list_sheet_ids(prod_only=True) == ["sheet_one"]

    store.delete_sheet("sheet_one")
    assert store.list_sheet_ids() == []


def test_store_reorders_sheet_tabs_by_input_list_order(store: SQLiteManagementStore) -> None:
    store.upsert_sheet(
        "sheet_one",
        "Sheet One",
        "Demo",
        [
            {"plugin_id": "module_aaa", "label": "A"},
            {"plugin_id": "module_bbb", "label": "B"},
            {"plugin_id": "module_ccc", "label": "C"},
        ],
    )

    store.upsert_sheet(
        "sheet_one",
        "Sheet One",
        "Demo",
        [
            {"plugin_id": "module_ccc", "label": "C"},
            {"plugin_id": "module_aaa", "label": "A"},
        ],
    )

    rows = store.list_sheet_tabs_with_order("sheet_one")
    assert [(row["tab_order"], row["plugin_id"], row["label"]) for row in rows] == [
        (0, "module_ccc", "C"),
        (1, "module_aaa", "A"),
    ]


def test_store_contract_lists_prod_module_ids(store: SQLiteManagementStore) -> None:
    store.set_plugin_enabled("module_aaa", True, mode="prod")

    assert store.list_prod_module_tool_ids() == ["module_aaa"]


def test_store_records_and_lists_audit_events(store: SQLiteManagementStore) -> None:
    event_id = store.record_audit_event(
        "publish",
        "tool",
        "module_aaa",
        actor="alice",
        details={"version_id": 7},
    )

    rows = store.list_audit_event_rows(limit=1)

    assert event_id > 0
    assert rows[0]["actor"] == "alice"
    assert rows[0]["details_json"]


def test_store_get_permission_returns_none_for_missing_row(store: SQLiteManagementStore) -> None:
    assert store.get_permission("module_aaa", "viewer", "execute") is None


def test_store_get_permission_reads_existing_row(store: SQLiteManagementStore, db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO plugin_permissions (plugin_id, role_id, can_view, can_execute)
               VALUES (?, ?, ?, ?)""",
            ("module_aaa", "viewer", 1, 0),
        )

    assert store.get_permission("module_aaa", "viewer", "view") is True
    assert store.get_permission("module_aaa", "viewer", "execute") is False


def test_store_lists_sheet_tabs(store: SQLiteManagementStore, db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO sheets (sheet_id, name, description) VALUES (?, ?, ?)",
            ("sheet_one", "Sheet One", ""),
        )
        conn.execute(
            "INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label) VALUES (?, ?, ?, ?)",
            ("sheet_one", 0, "module_aaa", "Step A"),
        )

    rows = store.list_sheet_tab_rows("sheet_one")

    assert rows == [{"plugin_id": "module_aaa", "label": "Step A"}]


def test_store_dumps_all_tables(store: SQLiteManagementStore) -> None:
    dump = store.dump_all_tables()

    assert "tools" in dump
    assert any(row["tool_id"] == "module_aaa" for row in dump["tools"])


def test_store_records_tool_runs_and_usage(store: SQLiteManagementStore) -> None:
    run_id = store.start_tool_run(
        "module_aaa",
        "module",
        "iframe",
        actor="alice",
        input_port=1001,
        output_port=1002,
        pid=123,
    )

    rows = store.list_tool_run_rows()
    assert rows[0]["run_id"] == run_id
    assert rows[0]["status"] == "running"
    assert rows[0]["actor"] == "alice"

    store.finish_tool_run(run_id, "stopped")

    rows = store.list_tool_run_rows(tool_id="module_aaa")
    assert rows[0]["status"] == "stopped"
    assert rows[0]["ended_at"] is not None
    summary = store.usage_summary(days=1)
    assert summary[0]["tool_id"] == "module_aaa"
    assert summary[0]["run_count"] == 1
    assert summary[0]["stopped_count"] == 1


def test_store_log_module_execution_and_query(store: SQLiteManagementStore) -> None:
    # Seed a sheet so context_sheet_id makes sense
    store.upsert_sheet("wf_test", "Test WF", "", [{"plugin_id": "module_aaa", "label": "A"}])

    run_id = store.log_module_execution(
        plugin_id="module_aaa",
        sheet_id="wf_test",
        success=True,
        duration_ms=2500,
        actor="user",
    )
    assert run_id

    # module_usage_by_sheet should pick it up
    rows = store.module_usage_by_sheet("wf_test", days=1)
    assert rows[0]["plugin_id"] == "module_aaa"
    assert rows[0]["run_count"] == 1
    assert rows[0]["completed_count"] == 1

    # failed execution
    store.log_module_execution("module_aaa", "wf_test", success=False, duration_ms=None)
    rows2 = store.module_usage_by_sheet("wf_test", days=1)
    assert rows2[0]["failed_count"] == 1


def test_store_stale_modules_detects_unused(store: SQLiteManagementStore) -> None:
    # module_aaa exists but has no module_exec runs → should appear as stale
    stale = store.stale_modules(days=1)
    tool_ids = [r["tool_id"] for r in stale]
    assert "module_aaa" in tool_ids


def test_store_delete_draft_tool_blocks_versions_and_references(store: SQLiteManagementStore) -> None:
    store.publish_tool_snapshot("module_aaa", "Module A", "1.0.0", "{}", "v1", "alice", enable_prod=False)

    with pytest.raises(ValueError, match="snapshots"):
        store.delete_draft_tool("module_aaa")


def test_store_delete_draft_tool_removes_unpublished_catalog_entry(store: SQLiteManagementStore) -> None:
    store.upsert_plugin_catalog_entry("module_999", "Draft", "0.1.0")

    store.delete_draft_tool("module_999")

    assert store.get_tool_catalog_row("module_999") is None
