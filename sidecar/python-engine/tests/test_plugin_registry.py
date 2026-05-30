from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("CIM_DEV_MODE", "1")

from plugin_registry import PluginInfo, PluginRegistry, SheetInfo, _is_dev_mode


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def scripts_dir(tmp_path: Path) -> Path:
    """Minimal scripts dir with two module folders and one sheet."""
    for mid, name in [("module_aaa", "模組 A"), ("module_bbb", "模組 B")]:
        folder = tmp_path / mid
        folder.mkdir()
        (folder / "__init__.py").write_text(f'MODULE_NAME = "{name}"', encoding="utf-8")
        (folder / f"{mid.split('_')[1]}_input.py").write_text("def render_input(): return {}", encoding="utf-8")
        manifest = {
            "id": mid,
            "name": name,
            "version": "1.0.0",
            "category": "module",
            "description": f"Test module {mid}",
            "author": "test",
            "tags": ["test"],
            "runner": "cv_framework",
        }
        (folder / "plugin.yaml").write_text(yaml.dump(manifest, allow_unicode=True), encoding="utf-8")

    sheets_dir = tmp_path / "sheets" / "sheet_one"
    sheets_dir.mkdir(parents=True)
    sheet_manifest = {
        "id": "sheet_one",
        "name": "套件一",
        "description": "Test sheet",
        "tabs": [
            {"plugin_id": "module_aaa", "label": "Step A"},
            {"plugin_id": "module_bbb", "label": "Step B"},
        ],
    }
    (sheets_dir / "sheet.yaml").write_text(yaml.dump(sheet_manifest, allow_unicode=True), encoding="utf-8")
    return tmp_path


@pytest.fixture()
def registry(tmp_path: Path, scripts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    db = tmp_path / "data" / "plugins.sqlite"
    return PluginRegistry(db_path=db, scripts_dir=scripts_dir)


# ── DB migration ────────────────────────────────────────────────────────────


def test_migration_creates_core_tables(registry: PluginRegistry) -> None:
    expected = {"roles", "users", "tool_versions", "sheets", "sheet_tabs", "plugin_permissions"}
    with registry._connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    actual = {r["name"] for r in rows}
    assert expected.issubset(actual)


def test_migration_creates_tools_table(registry: PluginRegistry) -> None:
    with registry._connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tools'").fetchall()
    assert len(rows) == 1


def test_legacy_plugins_table_dropped(registry: PluginRegistry) -> None:
    """plugins and plugin_versions tables must not exist after migration."""
    with registry._connect() as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('plugins','plugin_versions')"
        ).fetchall()
    assert rows == []


def test_migration_seeds_roles(registry: PluginRegistry) -> None:
    with registry._connect() as conn:
        rows = conn.execute("SELECT role_id FROM roles").fetchall()
    role_ids = {r["role_id"] for r in rows}
    assert role_ids == {"admin", "operator", "viewer"}


def test_migration_idempotent(registry: PluginRegistry) -> None:
    registry._migrate()
    with registry._connect() as conn:
        count = conn.execute("SELECT COUNT(*) FROM roles").fetchone()[0]
    assert count == 3


# ── Dev-mode: list_plugins ──────────────────────────────────────────────────


def test_list_plugins_dev_returns_all(registry: PluginRegistry) -> None:
    plugins = registry.list_plugins()
    assert len(plugins) == 2


def test_list_plugins_dev_has_correct_ids(registry: PluginRegistry) -> None:
    ids = {p.plugin_id for p in registry.list_plugins()}
    assert ids == {"module_aaa", "module_bbb"}


def test_list_plugins_dev_plugin_info(registry: PluginRegistry) -> None:
    plugins = {p.plugin_id: p for p in registry.list_plugins()}
    a = plugins["module_aaa"]
    assert a.name == "模組 A"
    assert a.version == "1.0.0"
    assert a.category == "module"
    assert a.runner == "cv_framework"


def test_list_plugins_dev_sorted(registry: PluginRegistry) -> None:
    ids = [p.plugin_id for p in registry.list_plugins()]
    assert ids == sorted(ids)


def test_list_plugins_dev_default_flags(registry: PluginRegistry) -> None:
    plugins = {p.plugin_id: p for p in registry.list_plugins()}
    assert plugins["module_aaa"].enabled_dev is True
    assert plugins["module_aaa"].enabled_prod is False


# ── Dev-mode: get_plugin ────────────────────────────────────────────────────


def test_get_plugin_dev_found(registry: PluginRegistry) -> None:
    p = registry.get_plugin("module_aaa")
    assert isinstance(p, PluginInfo)
    assert p.plugin_id == "module_aaa"


def test_get_plugin_dev_not_found(registry: PluginRegistry) -> None:
    with pytest.raises(KeyError):
        registry.get_plugin("module_zzz")


# ── publish ─────────────────────────────────────────────────────────────────


def test_publish_creates_version(registry: PluginRegistry) -> None:
    vid = registry.publish("module_aaa", changelog="初版", author="test")
    assert isinstance(vid, int) and vid > 0


def test_publish_inserts_tools_row(registry: PluginRegistry) -> None:
    registry.publish("module_aaa")
    with registry._connect() as conn:
        row = conn.execute("SELECT tool_id FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row is not None


def test_publish_stores_content_json(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="test")
    with registry._connect() as conn:
        row = conn.execute(
            "SELECT content_json FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()
    assert row is not None
    content = json.loads(row["content_json"])
    assert any(k.endswith(".py") for k in content)


def test_publish_includes_plugin_yaml(registry: PluginRegistry) -> None:
    registry.publish("module_aaa")
    with registry._connect() as conn:
        row = conn.execute(
            "SELECT content_json FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()
    content = json.loads(row["content_json"])
    assert "plugin.yaml" in content


def test_publish_sets_enabled_prod_in_tools(registry: PluginRegistry) -> None:
    registry.publish("module_aaa")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_prod"] == 1


def test_publish_sets_is_active(registry: PluginRegistry) -> None:
    registry.publish("module_aaa")
    with registry._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()[0]
    assert count == 1


def test_publish_deactivates_previous(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1")
    registry.publish("module_aaa", changelog="v2")
    with registry._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()[0]
    assert count == 1


# ── MAX migration fix: publish persists across _migrate() re-runs ────────────


def test_enabled_prod_survives_remigrate(registry: PluginRegistry) -> None:
    """publish() sets enabled_prod=1; re-running _migrate() must not reset it to 0."""
    registry.publish("module_aaa")
    # Simulate re-instantiation (e.g. st.rerun triggers new PluginRegistry())
    registry._migrate()
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_prod"] == 1


def test_enabled_prod_not_downgraded_by_legacy_zero(
    registry: PluginRegistry,
) -> None:
    """If a stale plugins row with enabled_prod=0 exists at migration time,
    the tools.enabled_prod=1 set by publish() must not be overwritten."""
    registry.publish("module_aaa")  # sets tools.enabled_prod = 1

    # Artificially reintroduce the legacy table with enabled_prod=0 (simulates old DB)
    with registry._connect() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS plugins (
                plugin_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled_dev INTEGER NOT NULL DEFAULT 1,
                enabled_prod INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            "INSERT OR REPLACE INTO plugins (plugin_id, name, enabled_prod) VALUES (?, ?, 0)",
            ("module_aaa", "模組 A"),
        )

    registry._migrate()  # should use MAX, not COALESCE

    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    # MAX(1, COALESCE(0, 0)) = 1 → must stay 1
    assert row["enabled_prod"] == 1


# ── rollback ────────────────────────────────────────────────────────────────


def test_rollback_switches_active(registry: PluginRegistry) -> None:
    v1 = registry.publish("module_aaa", changelog="v1")
    registry.publish("module_aaa", changelog="v2")
    registry.rollback("module_aaa", v1)
    with registry._connect() as conn:
        row = conn.execute(
            "SELECT version_id FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()
    assert row["version_id"] == v1


# ── list_versions ───────────────────────────────────────────────────────────


def test_rollback_invalid_version_preserves_active_version(registry: PluginRegistry) -> None:
    v1 = registry.publish("module_aaa", changelog="v1")

    with pytest.raises(KeyError):
        registry.rollback("module_aaa", 999999)

    with registry._connect() as conn:
        row = conn.execute(
            "SELECT version_id FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchone()
    assert row["version_id"] == v1


def test_list_versions_empty_before_publish(registry: PluginRegistry) -> None:
    assert registry.list_versions("module_aaa") == []


def test_list_versions_after_publish(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1", author="alice")
    registry.publish("module_aaa", changelog="v2", author="bob")
    versions = registry.list_versions("module_aaa")
    assert len(versions) == 2
    assert versions[0].changelog == "v2"
    assert versions[1].changelog == "v1"


# ── audit events ────────────────────────────────────────────────────────────


def test_record_audit_event_returns_id(registry: PluginRegistry) -> None:
    event_id = registry.record_audit_event(
        "publish",
        "tool",
        "module_aaa",
        actor="alice",
        details={"version_id": 1},
    )
    assert event_id > 0


def test_list_audit_events_returns_newest_first(registry: PluginRegistry) -> None:
    registry.record_audit_event("publish", "tool", "module_aaa", actor="alice")
    registry.record_audit_event("rollback", "tool", "module_aaa", actor="bob")

    events = registry.list_audit_events(limit=10)

    assert [e.action for e in events[:2]] == ["rollback", "publish"]
    assert events[0].actor == "bob"
    assert events[0].target_id == "module_aaa"


# ── set_enabled ─────────────────────────────────────────────────────────────


def test_set_enabled_dev_disables(registry: PluginRegistry) -> None:
    registry.list_plugins()  # ensure row exists in tools
    registry.set_enabled("module_aaa", False, mode="dev")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_dev FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_dev"] == 0


def test_set_enabled_dev_re_enables(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", False, mode="dev")
    registry.set_enabled("module_aaa", True, mode="dev")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_dev FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_dev"] == 1


def test_set_enabled_prod(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", True, mode="prod")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_prod"] == 1


def test_set_enabled_prod_does_not_affect_dev(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", False, mode="prod")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_dev, enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_dev"] == 1   # unchanged
    assert row["enabled_prod"] == 0


def test_set_tool_prod_enabled_updates_any_tool(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_tool_prod_enabled("module_aaa", True)
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='module_aaa'").fetchone()
    assert row["enabled_prod"] == 1


def test_publish_stores_author_in_versions(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="init", author="alice")
    versions = registry.list_versions("module_aaa")
    assert versions[0].author == "alice"


def test_set_sheet_enabled_prod_syncs_tool_table(registry: PluginRegistry) -> None:
    # create_or_update_sheet creates the sheet tool row and keeps Prod state in sync.
    registry.create_or_update_sheet(
        "sheet_one", "Sheet One", "", [{"plugin_id": "module_aaa", "label": "A"}]
    )
    registry.set_sheet_enabled("sheet_one", True, mode="prod")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='sheet-sheet_one'").fetchone()
    assert row is not None and row["enabled_prod"] == 1


def test_set_sheet_enabled_prod_disable_clears_tool_table(registry: PluginRegistry) -> None:
    registry.create_or_update_sheet(
        "sheet_one", "Sheet One", "", [{"plugin_id": "module_aaa", "label": "A"}]
    )
    registry.set_sheet_enabled("sheet_one", True, mode="prod")
    registry.set_sheet_enabled("sheet_one", False, mode="prod")
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM tools WHERE tool_id='sheet-sheet_one'").fetchone()
    assert row is not None and row["enabled_prod"] == 0


def test_list_audit_events_stores_details_json(registry: PluginRegistry) -> None:
    registry.record_audit_event(
        "publish",
        "tool",
        "module_aaa",
        actor="alice",
        details={"version_id": 42, "file_count": 4, "has_plugin_yaml": True},
    )
    events = registry.list_audit_events(limit=1)
    assert events[0].details["version_id"] == 42
    assert events[0].details["has_plugin_yaml"] is True


def test_normalize_active_versions_noop_when_single_active(registry: PluginRegistry) -> None:
    v1 = registry.publish("module_aaa", changelog="v1")
    result = registry.normalize_active_versions("module_aaa")
    assert result["kept_version_id"] == v1
    assert result["updated_rows"] == 0


def test_delete_orphan_versions_skips_existing_tool(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1")
    deleted = registry.delete_orphan_versions("module_aaa")
    assert deleted == 0


def test_normalize_active_versions_keeps_newest(registry: PluginRegistry) -> None:
    v1 = registry.publish("module_aaa", changelog="v1")
    v2 = registry.publish("module_aaa", changelog="v2")
    with registry._connect() as conn:
        conn.execute("UPDATE tool_versions SET is_active=1 WHERE version_id=?", (v1,))

    result = registry.normalize_active_versions("module_aaa")

    assert result["kept_version_id"] == v2
    with registry._connect() as conn:
        active = conn.execute(
            "SELECT version_id FROM tool_versions WHERE tool_id='module_aaa' AND is_active=1"
        ).fetchall()
    assert [row["version_id"] for row in active] == [v2]


def test_delete_orphan_versions_removes_only_missing_tool_rows(registry: PluginRegistry) -> None:
    with registry._connect() as conn:
        conn.execute(
            """INSERT INTO tool_versions (tool_id, version, content_json, is_active, source)
               VALUES ('module_missing', '1.0.0', '{}', 0, 'filesystem')"""
        )

    deleted = registry.delete_orphan_versions("module_missing")

    assert deleted == 1
    with registry._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM tool_versions WHERE tool_id='module_missing'"
        ).fetchone()[0]
    assert count == 0


# ── enabled property ─────────────────────────────────────────────────────────


def test_plugin_enabled_property_dev_mode(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    plugin = registry.list_plugins()[0]
    assert plugin.enabled == plugin.enabled_dev


def test_plugin_enabled_property_prod_mode(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.publish("module_aaa")
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    plugin = registry.get_plugin("module_aaa")
    assert plugin.enabled == plugin.enabled_prod


# ── Prod-mode: list_plugins ──────────────────────────────────────────────────


def test_list_plugins_prod_empty_without_publish(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    assert registry.list_plugins() == []


def test_list_plugins_prod_shows_after_publish(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.publish("module_aaa")
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    ids = {p.plugin_id for p in registry.list_plugins()}
    assert "module_aaa" in ids
    assert "module_bbb" not in ids


def test_list_plugins_dev_reflects_disabled(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", False, mode="dev")
    plugins = {p.plugin_id: p for p in registry.list_plugins()}
    assert plugins["module_aaa"].enabled_dev is False


def test_plugin_from_db_reads_yaml_version(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.publish("module_aaa")
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    plugin = registry.get_plugin("module_aaa")
    assert plugin.version == "1.0.0"


def test_plugin_from_db_reads_yaml_name(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.publish("module_aaa")
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    plugin = registry.get_plugin("module_aaa")
    assert plugin.name == "模組 A"


def test_plugin_from_db_fallback_without_yaml(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Snapshot without plugin.yaml in content_json must not crash."""
    with registry._connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tools (tool_id, name, script_relative_path, version, enabled) VALUES (?,?,?,?,1)",
            ("module_aaa", "模組 A", "cv_framework_runner.py", "0.5.0"),
        )
        conn.execute(
            """INSERT INTO tool_versions (tool_id, version, content_json, is_active, source)
               VALUES (?, ?, ?, 1, 'filesystem')""",
            ("module_aaa", "0.5.0", json.dumps({"aaa_input.py": "def render_input(): return {}"})),
        )
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    plugin = registry.get_plugin("module_aaa")
    assert plugin is not None and plugin.plugin_id == "module_aaa"


# ── Sheets ───────────────────────────────────────────────────────────────────


def test_sync_sheets_inserts_rows(registry: PluginRegistry) -> None:
    synced = registry.sync_sheets()
    assert "sheet_one" in synced
    with registry._connect() as conn:
        row = conn.execute("SELECT sheet_id FROM sheets WHERE sheet_id='sheet_one'").fetchone()
    assert row is not None


def test_sync_sheets_inserts_tabs(registry: PluginRegistry) -> None:
    registry.sync_sheets()
    with registry._connect() as conn:
        rows = conn.execute(
            "SELECT plugin_id FROM sheet_tabs WHERE sheet_id='sheet_one' ORDER BY tab_order"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0]["plugin_id"] == "module_aaa"
    assert rows[1]["plugin_id"] == "module_bbb"


def test_sync_sheets_idempotent(registry: PluginRegistry) -> None:
    registry.sync_sheets()
    registry.sync_sheets()
    with registry._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM sheet_tabs WHERE sheet_id='sheet_one'"
        ).fetchone()[0]
    assert count == 2


def test_list_sheets_prod_empty_without_enable(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.sync_sheets()
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    sheets = registry.list_sheets()
    # Default enabled_prod=0 → not visible in PROD
    ids = [s.sheet_id for s in sheets]
    assert "sheet_one" not in ids


def test_list_sheets_prod_shows_after_enable(
    registry: PluginRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry.sync_sheets()
    with registry._connect() as conn:
        conn.execute("UPDATE sheets SET enabled_prod=1 WHERE sheet_id='sheet_one'")
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    ids = [s.sheet_id for s in registry.list_sheets()]
    assert "sheet_one" in ids


def test_sync_sheets_preserves_enabled_prod(registry: PluginRegistry) -> None:
    """Re-syncing must not reset enabled_prod back to 0."""
    registry.sync_sheets()
    with registry._connect() as conn:
        conn.execute("UPDATE sheets SET enabled_prod=1 WHERE sheet_id='sheet_one'")
    registry.sync_sheets()
    with registry._connect() as conn:
        row = conn.execute("SELECT enabled_prod FROM sheets WHERE sheet_id='sheet_one'").fetchone()
    assert row["enabled_prod"] == 1


# ── _is_dev_mode ─────────────────────────────────────────────────────────────


def test_dev_mode_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    assert _is_dev_mode() is True


def test_prod_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIM_DEV_MODE", "0")
    assert _is_dev_mode() is False


# ── Runner source-file sanity ─────────────────────────────────────────────────


def test_cv_framework_runner_imports_auth() -> None:
    src = (Path(__file__).parent.parent / "tools" / "cv_framework_runner.py").read_text(encoding="utf-8")
    assert "from auth_provider import AuthProvider" in src
    assert "check_permission" in src


def test_management_runner_has_layer_check() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "CIM_TOOL_LAYER" in src


def test_management_runner_uses_single_prod_control_panel() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "st.data_editor(" not in src
    # Prod toggle uses stable labels
    assert "Prod: ON" in src
    assert "Prod: OFF" in src
    # "Enable Prod" may appear as a readiness status label (not a button label)
    # "Turn off Prod" may appear as audit label; check button labels instead
    # Tools page uses tab-based layout
    assert "_render_module_detail_panel" in src
    assert "_render_modules_tab" in src
    assert "_render_sheets_tab" in src
    assert "_render_external_tab" in src
    assert "_get_module_to_sheets" in src
    # Old flat-list design artifacts removed
    assert "_render_selected_tool_actions" not in src
    assert "Tool Actions" not in src
    assert "tools_action_target" not in src
    # Publish actions renamed
    assert "Publish snapshot" in src
    assert "Publish & go live" in src
    assert 'selection_mode="single-row"' in src
    assert 'on_select="rerun"' in src
    assert "row_prod_on_" not in src
    assert "row_save_order_" not in src
    assert "row_archive_" not in src
    assert "Inactive Tools" in src
    assert "_render_inactive_tools" in src
    assert "Upload / New Module" in src
    assert "Upload as new module snapshot" in src
    assert "Create module scaffold" in src
    assert "Delete draft" in src
    assert 'st.warning("Needs attention") if issues else st.success("Passed")' not in src
def test_management_runner_has_workflow_tabs() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert '["Health", "Tools", "Runs & Usage", "Sheets", "Permissions", "Repairs", "Audit & Database"]' in src
    assert "Audit & Backup" not in src
    # the (previously dead) Permissions page is now wired into the nav as a
    # visual RBAC matrix editor + raw-YAML editor + external-system register form
    assert "_page_permissions(reg)" in src
    assert "視覺化權限編輯" in src
    assert "_render_external_system_register" in src


def test_management_runner_audit_database_is_backend_aware() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "_management_backend" in src
    assert "CIM_MANAGEMENT_BACKEND" in src
    assert "Audit & Database" in src
    assert "Local SQLite Backup" in src
    assert "Download local SQLite backup (JSON)" in src
    assert "Oracle production backups are managed outside Management Center" in src
    assert "External DBA / Oracle policy" in src
    assert "Disabled for non-SQLite backends" in src


def test_management_runner_guards_high_risk_actions() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "_confirm_rollback_dialog" in src
    assert "_confirm_archive_dialog" in src
    assert "_confirm_restore_dialog" in src
    assert "_confirm_delete_draft_tool_dialog" in src
    assert "_confirm_delete_sheet_dialog" in src
    assert "_confirm_repair_dialog" in src


def test_management_runner_routes_sheet_prod_through_sheet_gate() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "validate_sheet_prod_readiness(_DB_PATH, sheet_id)" in src
    assert "_render_sheets_tab" in src
    assert "set_sheet_prod_enabled(" in src
    assert "disabled=manage_disabled or (not sheet.enabled_prod and bool(prod_issues))," in src


def test_management_runner_has_sheet_steps_table_controls() -> None:
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "_sheet_steps_editor" in src
    assert "_sheet_readiness_summary" in src
    assert "_prepare_sheet_draft_steps" in src
    assert "_draft_id" in src
    assert "Add step" in src
    assert "Readiness" in src
    assert "Readiness details" not in src
    assert "Needs release" in src
    assert "Discard" in src
    assert "Dev: On" in src
    assert "Save Steps" in src
    assert "_up_" in src
    assert "_down_" in src
    assert "_sheet_tab_editor" not in src
    assert "edit_tabs_" not in src
    assert "editing_sheet_" not in src


def test_management_runner_preview_uses_postmessage_not_iframe() -> None:
    """Preview opens a full-screen portal modal via postMessage, not an inline iframe."""
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    # postMessage helper exists
    assert "_open_preview_modal" in src
    # Fires to the top-level portal window (across two iframe layers)
    assert "window.top.postMessage" in src
    # OPEN_PREVIEW message type matches shared-protocol
    assert "OPEN_PREVIEW" in src
    # No longer embeds module inside management-center with st.components.v1.iframe
    assert "components.iframe(" not in src
    # Preview expander still present; buttons renamed
    assert "▶ Start Preview" in src
    assert "↗ Reopen full-screen" in src
    assert "⏹ Stop preview" in src


def test_management_runner_modules_table_has_id_column() -> None:
    """Modules dataframe exposes the tool_id as a visible 'ID' column."""
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert '"ID": row["tool_id"]' in src
    assert '"ID": st.column_config.TextColumn("ID"' in src


def test_management_runner_modules_table_checkbox_init() -> None:
    """Table checkbox is initialised on first load and on filter-reset only.

    Setting session state before the widget on every rerun would override
    Streamlit's stored click interaction and cause the checkbox to snap back
    to row 0 after each user click — this test guards against that regression.
    """
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    # Initialise only when key is absent (first load)
    assert 'if "modules_table" not in st.session_state:' in src
    # Also reset when filter forces a new default selection
    assert 'st.session_state["modules_table"] = {"selection": {"rows": [0]' in src
    # Must NOT set session state unconditionally before the widget on every rerun
    assert "# Always sync the checkbox to the current selection before rendering." not in src


def test_engine_has_preview_endpoints() -> None:
    """Engine exposes side-preview HTTP endpoints that don't stop the active tool."""
    src = (Path(__file__).parent.parent / "engine.py").read_text(encoding="utf-8")
    assert "start_preview" in src
    assert "stop_preview" in src
    assert "preview_status" in src
    assert "/tools/preview/stop" in src
    assert "/tools/preview/status" in src
    assert "_preview_process" in src


def test_engine_has_log_module_run_endpoint() -> None:
    """Engine exposes POST /tools/runs/log for portal to record module executions."""
    src = (Path(__file__).parent.parent / "engine.py").read_text(encoding="utf-8")
    assert "/tools/runs/log" in src
    assert "log_module_execution" in src
    assert "plugin_id" in src
    assert "sheet_id" in src


def test_management_runner_runs_page_has_three_tabs() -> None:
    """_page_runs uses st.tabs with 模組使用率, Sheet 執行記錄, and 閒置建議."""
    src = (Path(__file__).parent.parent / "tools" / "management_runner.py").read_text(encoding="utf-8")
    assert "模組使用率" in src
    assert "Sheet 執行記錄" in src
    assert "閒置建議" in src
    assert "module_usage_by_sheet" in src
    assert "stale_modules" in src


def test_management_store_schema_has_context_sheet_id_migration() -> None:
    """_ALTER_MIGRATIONS must include the context_sheet_id column."""
    src = (Path(__file__).parent.parent / "management_schema.py").read_text(encoding="utf-8")
    assert "context_sheet_id" in src
