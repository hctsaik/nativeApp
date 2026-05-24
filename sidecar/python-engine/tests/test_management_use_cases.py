from __future__ import annotations

import io
import sqlite3
import zipfile
from pathlib import Path

import pytest
import yaml

from management_insights import IntegrityIssue
from management_package_importer import ModulePackageError
from management_store import SQLiteManagementStore
from management_use_cases import ManagementUseCases, SheetProdReadinessError
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
    (folder / "aaa_process.py").write_text("def execute_logic(params): return {}\n", encoding="utf-8")
    (folder / "aaa_output.py").write_text("def render_output(result): return None\n", encoding="utf-8")
    return tmp_path


@pytest.fixture()
def registry(tmp_path: Path, scripts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> PluginRegistry:
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    reg = PluginRegistry(tmp_path / "data" / "tools.sqlite", scripts_dir=scripts_dir)
    reg.list_plugins()
    return reg


@pytest.fixture()
def store(registry: PluginRegistry) -> SQLiteManagementStore:
    return SQLiteManagementStore(registry._db_path)


@pytest.fixture()
def use_cases(
    registry: PluginRegistry,
    store: SQLiteManagementStore,
    scripts_dir: Path,
) -> ManagementUseCases:
    return ManagementUseCases(registry._db_path, scripts_dir, registry, store)


def test_publish_tool_to_prod_records_snapshot_and_audit(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    result = use_cases.publish_tool_to_prod(
        "module_aaa",
        "module_aaa",
        changelog="release",
        author="alice",
        actor="operator-a",
        diff_summary={"changed_file_count": 4},
    )

    versions = registry.list_versions("module_aaa")
    events = registry.list_audit_events(limit=1)

    assert result.version_id == versions[0].version_id
    assert result.file_count == 4
    assert result.includes_manifest is True
    assert events[0].action == "publish"
    assert events[0].actor == "operator-a"
    assert events[0].details["version_id"] == result.version_id


def test_create_snapshot_from_filesystem_does_not_enable_prod(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
    store: SQLiteManagementStore,
) -> None:
    result = use_cases.create_snapshot_from_filesystem(
        "module_aaa",
        "module_aaa",
        changelog="draft snapshot",
        author="alice",
        actor="operator-a",
    )

    row = store.get_tool_catalog_row("module_aaa")
    events = registry.list_audit_events(limit=1)

    assert result.version_id
    assert row["enabled_prod"] == 0
    assert events[0].action == "create_snapshot"


def test_rollback_tool_version_records_audit(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    v1 = registry.publish("module_aaa", changelog="v1", author="alice")
    registry.publish("module_aaa", changelog="v2", author="bob")

    event_id = use_cases.rollback_tool_version("module_aaa", v1, actor="operator-a")

    active = [version for version in registry.list_versions("module_aaa") if version.is_active]
    events = registry.list_audit_events(limit=1)

    assert active[0].version_id == v1
    assert events[0].event_id == event_id
    assert events[0].action == "rollback"


def test_set_sheet_prod_enabled_blocks_unready_sheet(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )

    with pytest.raises(SheetProdReadinessError) as exc:
        use_cases.set_sheet_prod_enabled("sheet_one", True, actor="operator-a")

    assert exc.value.sheet_id == "sheet_one"
    assert exc.value.issues


def test_set_sheet_prod_enabled_passes_ready_sheet(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    registry.publish("module_aaa", changelog="release", author="alice")
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )

    event_id = use_cases.set_sheet_prod_enabled("sheet_one", True, actor="operator-a")

    sheet = registry.get_sheet("sheet_one")
    events = registry.list_audit_events(limit=1)

    assert sheet.enabled_prod is True
    assert events[0].event_id == event_id
    assert events[0].action == "prod_enable"


def test_sheet_crud_use_cases_write_audit(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    create_event = use_cases.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
        actor="operator-a",
        action="create",
    )
    dev_event = use_cases.set_sheet_dev_enabled("sheet_one", False, actor="operator-a")
    delete_event = use_cases.delete_sheet("sheet_one", "Sheet One", actor="operator-a")

    events = registry.list_audit_events(limit=3)

    assert [event.event_id for event in reversed(events)] == [create_event, dev_event, delete_event]
    assert [event.action for event in reversed(events)] == ["create", "dev_disable", "delete"]


def test_repair_integrity_issue_normalizes_versions(
    use_cases: ManagementUseCases,
    registry: PluginRegistry,
) -> None:
    v1 = registry.publish("module_aaa", changelog="v1", author="alice")
    v2 = registry.publish("module_aaa", changelog="v2", author="bob")
    with sqlite3.connect(registry._db_path) as conn:
        conn.execute("UPDATE tool_versions SET is_active=1 WHERE version_id=?", (v1,))

    result = use_cases.repair_integrity_issue(
        IntegrityIssue(
            severity="error",
            category="versions",
            target_id="module_aaa",
            issue="Tool has multiple active versions.",
            repair="normalize_active_versions",
        ),
        actor="operator-a",
    )

    active = [version for version in registry.list_versions("module_aaa") if version.is_active]
    events = registry.list_audit_events(limit=1)

    assert [version.version_id for version in active] == [v2]
    assert result.details["kept_version_id"] == v2
    assert events[0].action == "repair_normalize_active_versions"


def _module_zip(plugin_id: str = "module_012", version: str = "1.2.3") -> bytes:
    short_id = plugin_id.removeprefix("module_")
    files = {
        f"{plugin_id}/plugin.yaml": yaml.safe_dump({
            "id": plugin_id,
            "name": "Uploaded Module",
            "version": version,
            "category": "module",
            "runner": "cv_framework",
        }),
        f"{plugin_id}/{short_id}_input.py": "def render_input():\n    return {}\n",
        f"{plugin_id}/{short_id}_process.py": "def execute_logic(params):\n    return params\n",
        f"{plugin_id}/{short_id}_output.py": "def render_output(result):\n    return None\n",
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, source in files.items():
            zf.writestr(name, source)
    return buffer.getvalue()


def test_import_module_package_creates_snapshot_without_prod(
    use_cases: ManagementUseCases,
    store: SQLiteManagementStore,
    registry: PluginRegistry,
) -> None:
    result = use_cases.import_module_package(
        _module_zip(),
        "module_012.zip",
        changelog="initial upload",
        author="alice",
        actor="operator-a",
    )

    row = store.get_tool_catalog_row("module_012")
    versions = store.list_version_rows("module_012")
    events = registry.list_audit_events(limit=1)

    assert result.report.plugin_id == "module_012"
    assert versions[0]["source"] == "upload"
    assert row["enabled_prod"] == 0
    assert events[0].action == "import_module_create"
    assert events[0].details["package_hash"] == result.report.package_hash


def test_import_module_package_requires_explicit_update(
    use_cases: ManagementUseCases,
) -> None:
    use_cases.import_module_package(
        _module_zip("module_012", "1.2.3"),
        "module_012.zip",
        changelog="initial upload",
        author="alice",
        actor="operator-a",
    )

    with pytest.raises(ModulePackageError) as exc:
        use_cases.import_module_package(
            _module_zip("module_012", "1.2.4"),
            "module_012.zip",
            changelog="update",
            author="alice",
            actor="operator-a",
            allow_update=False,
        )

    assert any(issue.code == "MODULE_ID_EXISTS" for issue in exc.value.report.issues)


def test_create_module_scaffold_writes_files_and_catalog(
    use_cases: ManagementUseCases,
    scripts_dir: Path,
    store: SQLiteManagementStore,
    registry: PluginRegistry,
) -> None:
    result = use_cases.create_module_scaffold(
        name="New Module",
        description="Draft",
        author="alice",
        actor="operator-a",
        plugin_id="module_012",
    )

    assert result.plugin_id == "module_012"
    assert (scripts_dir / "module_012" / "012_input.py").exists()
    assert store.get_tool_catalog_row("module_012")["enabled_prod"] == 0
    assert registry.list_audit_events(limit=1)[0].action == "create_module_scaffold"


def test_delete_draft_tool_records_audit(
    use_cases: ManagementUseCases,
    store: SQLiteManagementStore,
    registry: PluginRegistry,
) -> None:
    store.upsert_plugin_catalog_entry("module_012", "Draft", "0.1.0")

    result = use_cases.delete_draft_tool("module_012", actor="operator-a")

    assert store.get_tool_catalog_row("module_012") is None
    assert result.tool_id == "module_012"
    assert registry.list_audit_events(limit=1)[0].action == "delete_draft"
