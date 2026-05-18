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


def test_list_versions_empty_before_publish(registry: PluginRegistry) -> None:
    assert registry.list_versions("module_aaa") == []


def test_list_versions_after_publish(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1", author="alice")
    registry.publish("module_aaa", changelog="v2", author="bob")
    versions = registry.list_versions("module_aaa")
    assert len(versions) == 2
    assert versions[0].changelog == "v2"
    assert versions[1].changelog == "v1"


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
