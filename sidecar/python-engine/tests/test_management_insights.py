from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from management_insights import (
    collect_dashboard_summary,
    collect_integrity_issues,
    collect_tool_readiness,
    module_snapshot_diff,
    module_source_snapshot,
    module_preflight,
    validate_sheet_prod_readiness,
    validate_sheet_references,
)
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
    return PluginRegistry(db_path=tmp_path / "data" / "tools.sqlite", scripts_dir=scripts_dir)


def test_tool_readiness_flags_prod_module_without_snapshot(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", True, mode="prod")

    rows = {row.tool_id: row for row in collect_tool_readiness(registry._db_path)}

    assert rows["module_aaa"].enabled_prod is True
    assert rows["module_aaa"].has_active_version is False
    assert rows["module_aaa"].prod_ready is False
    assert "active published snapshot" in rows["module_aaa"].issues[0]


def test_tool_readiness_accepts_published_prod_module(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="release", author="test")

    rows = {row.tool_id: row for row in collect_tool_readiness(registry._db_path)}

    assert rows["module_aaa"].enabled_prod is True
    assert rows["module_aaa"].active_version == "1.0.0"
    assert rows["module_aaa"].prod_ready is True


def test_dashboard_summary_counts_readiness_issues(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.set_enabled("module_aaa", True, mode="prod")

    summary = collect_dashboard_summary(registry._db_path)

    assert summary["mode"] == "DEV"
    assert summary["prod_enabled_tools"] == 1
    assert summary["readiness_issue_count"] == 1


def test_integrity_reports_multiple_active_versions(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1", author="test")
    with registry._connect() as conn:
        conn.execute(
            """INSERT INTO tool_versions (tool_id, version, content_json, is_active, source)
               VALUES (?, ?, ?, 1, 'filesystem')""",
            ("module_aaa", "1.0.1", "{}"),
        )

    issues = collect_integrity_issues(registry._db_path)

    assert any(issue.category == "versions" and "active versions" in issue.issue for issue in issues)
    assert any(issue.repair == "normalize_active_versions" for issue in issues)


def test_integrity_reports_orphan_versions(registry: PluginRegistry) -> None:
    with registry._connect() as conn:
        conn.execute(
            """INSERT INTO tool_versions (tool_id, version, content_json, is_active, source)
               VALUES (?, ?, ?, 0, 'filesystem')""",
            ("module_missing", "1.0.0", "{}"),
        )

    issues = collect_integrity_issues(registry._db_path)

    assert any(issue.target_id == "module_missing" and "missing tool" in issue.issue for issue in issues)
    assert any(issue.repair == "delete_orphan_versions" for issue in issues)


def test_sheet_reference_validation_reports_missing_prod_snapshot(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )
    registry.set_sheet_enabled("sheet_one", True, mode="prod")
    registry.set_enabled("module_aaa", True, mode="prod")

    issues = validate_sheet_references(registry._db_path)

    assert len(issues) == 1
    assert issues[0].sheet_id == "sheet_one"
    assert "active snapshot" in issues[0].issue


def test_sheet_prod_readiness_checks_before_prod_enabled(registry: PluginRegistry) -> None:
    registry.list_plugins()
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )

    issues = validate_sheet_prod_readiness(registry._db_path, "sheet_one")

    assert len(issues) == 2
    issue_text = " ".join(issue.issue for issue in issues)
    assert "not enabled in Prod" in issue_text
    assert "active snapshot" in issue_text


def test_sheet_prod_readiness_passes_published_prod_module(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="release", author="test")
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )

    assert validate_sheet_prod_readiness(registry._db_path, "sheet_one") == []


def test_module_preflight_passes_complete_module(scripts_dir: Path) -> None:
    result = module_preflight(scripts_dir, "module_aaa")

    assert result.ok is True
    assert result.checks["plugin.yaml"] is True
    assert result.checks["process_no_streamlit"] is True


def test_module_preflight_blocks_streamlit_process_import(scripts_dir: Path) -> None:
    process_file = scripts_dir / "module_aaa" / "aaa_process.py"
    process_file.write_text("import streamlit as st\n", encoding="utf-8")

    result = module_preflight(scripts_dir, "module_aaa")

    assert result.ok is False
    assert "Process layer imports Streamlit." in result.issues


def test_module_source_snapshot_includes_layers_and_manifest(scripts_dir: Path) -> None:
    snapshot = module_source_snapshot(scripts_dir, "module_aaa")

    assert set(snapshot) == {"aaa_input.py", "aaa_process.py", "aaa_output.py", "plugin.yaml"}


def test_module_snapshot_diff_without_active_snapshot_marks_all_added(
    registry: PluginRegistry,
    scripts_dir: Path,
) -> None:
    diff = module_snapshot_diff(scripts_dir, registry._db_path, "module_aaa")

    assert diff.has_active_snapshot is False
    assert diff.active_file_count == 0
    assert sorted(diff.added) == ["aaa_input.py", "aaa_output.py", "aaa_process.py", "plugin.yaml"]


def test_module_snapshot_diff_detects_changed_file(
    registry: PluginRegistry,
    scripts_dir: Path,
) -> None:
    registry.publish("module_aaa", changelog="release", author="test")
    (scripts_dir / "module_aaa" / "aaa_process.py").write_text(
        "def execute_logic(params): return {'changed': True}\n",
        encoding="utf-8",
    )

    diff = module_snapshot_diff(scripts_dir, registry._db_path, "module_aaa")

    assert diff.has_active_snapshot is True
    assert diff.changed == ["aaa_process.py"]
    assert diff.changed_file_count == 1


def test_module_snapshot_diff_detects_removed_file(
    registry: PluginRegistry,
    scripts_dir: Path,
) -> None:
    registry.publish("module_aaa", changelog="release", author="test")
    (scripts_dir / "module_aaa" / "aaa_input.py").unlink()

    diff = module_snapshot_diff(scripts_dir, registry._db_path, "module_aaa")

    assert "aaa_input.py" in diff.removed
    assert diff.changed_file_count == 1


def test_module_preflight_reports_missing_layer_files(scripts_dir: Path) -> None:
    (scripts_dir / "module_aaa" / "aaa_process.py").unlink()
    (scripts_dir / "module_aaa" / "aaa_output.py").unlink()

    result = module_preflight(scripts_dir, "module_aaa")

    assert result.ok is False
    assert result.checks["process"] is False
    assert result.checks["output"] is False
    assert any("process" in issue.lower() for issue in result.issues)
    assert any("output" in issue.lower() for issue in result.issues)


def test_collect_integrity_issues_empty_when_clean(registry: PluginRegistry) -> None:
    registry.publish("module_aaa", changelog="v1", author="test")

    issues = collect_integrity_issues(registry._db_path)

    assert issues == []


def test_validate_sheet_references_no_issue_for_non_prod_sheet_with_unpublished_module(
    registry: PluginRegistry,
) -> None:
    registry.list_plugins()
    registry.create_or_update_sheet(
        "sheet_one",
        "Sheet One",
        "",
        [{"plugin_id": "module_aaa", "label": "Step A"}],
    )
    # Sheet is NOT Prod-enabled, module_aaa has no snapshot

    issues = validate_sheet_references(registry._db_path)

    # A non-Prod sheet with an unpublished module should have no issues
    assert issues == []


def test_module_snapshot_diff_summary_structure(
    registry: PluginRegistry,
    scripts_dir: Path,
) -> None:
    registry.publish("module_aaa", changelog="release", author="test")
    (scripts_dir / "module_aaa" / "aaa_process.py").write_text(
        "def execute_logic(params): return {'new': True}\n",
        encoding="utf-8",
    )

    diff = module_snapshot_diff(scripts_dir, registry._db_path, "module_aaa")
    summary = diff.summary()

    assert "has_active_snapshot" in summary
    assert "added" in summary
    assert "removed" in summary
    assert "changed" in summary
    assert "unchanged_count" in summary
    assert summary["has_active_snapshot"] is True
    assert summary["changed_file_count"] == 1
