from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from management_store import ManagementStore, SQLiteManagementStore


def _is_dev_mode() -> bool:
    return (os.environ.get("CIM_DEV_MODE", "1") or "").strip() == "1"


def derive_category(tool_id: str) -> str:
    if tool_id == "labelme-dino":
        return "external"
    if tool_id.startswith("sheet-"):
        return "sheet"
    if tool_id.startswith("management-"):
        return "management"
    return "module"


@dataclass
class ToolReadiness:
    tool_id: str
    name: str
    category: str
    enabled: bool
    enabled_prod: bool
    active_version: str | None = None
    version_count: int = 0
    issues: list[str] = field(default_factory=list)

    @property
    def has_active_version(self) -> bool:
        return self.active_version is not None

    @property
    def prod_ready(self) -> bool:
        return not self.issues


@dataclass
class SheetIssue:
    sheet_id: str
    sheet_name: str
    plugin_id: str
    label: str
    issue: str


@dataclass
class ModulePreflight:
    plugin_id: str
    ok: bool
    checks: dict[str, bool]
    issues: list[str]


@dataclass
class IntegrityIssue:
    severity: str
    category: str
    target_id: str
    issue: str
    repair: str | None = None


@dataclass
class ModuleSnapshotDiff:
    plugin_id: str
    has_active_snapshot: bool
    current_file_count: int
    active_file_count: int
    added: list[str]
    removed: list[str]
    changed: list[str]
    unchanged: list[str]

    @property
    def changed_file_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.changed)

    def summary(self) -> dict[str, Any]:
        return {
            "has_active_snapshot": self.has_active_snapshot,
            "current_file_count": self.current_file_count,
            "active_file_count": self.active_file_count,
            "added": self.added,
            "removed": self.removed,
            "changed": self.changed,
            "unchanged_count": len(self.unchanged),
            "changed_file_count": self.changed_file_count,
        }


def _store(db_path: Path, store: ManagementStore | None = None) -> ManagementStore:
    return store or SQLiteManagementStore(db_path)


def collect_tool_readiness(db_path: Path, store: ManagementStore | None = None) -> list[ToolReadiness]:
    store = _store(db_path, store)
    if not store.database_exists():
        return []

    rows = store.list_tool_readiness_records()

    results: list[ToolReadiness] = []
    for row in rows:
        tool_id = row["tool_id"]
        category = derive_category(tool_id)
        enabled = bool(row["enabled"])
        enabled_prod = bool(row["enabled_prod"])
        active_version = row["active_version"]
        issues: list[str] = []

        if enabled_prod and not enabled:
            issues.append("Prod is enabled but the tool is archived.")
        if category == "module" and enabled_prod and active_version is None:
            issues.append("Prod is enabled but no active published snapshot exists.")
        if category == "module" and enabled_prod and active_version is not None:
            issues.extend(validate_module_snapshot_content(tool_id, store.get_active_snapshot_content(tool_id)))

        results.append(
            ToolReadiness(
                tool_id=tool_id,
                name=row["name"],
                category=category,
                enabled=enabled,
                enabled_prod=enabled_prod,
                active_version=active_version,
                version_count=int(row["version_count"] or 0),
                issues=issues,
            )
        )
    return results


def validate_sheet_references(db_path: Path, store: ManagementStore | None = None) -> list[SheetIssue]:
    return _validate_sheet_references(db_path, store=store)


def validate_sheet_prod_readiness(
    db_path: Path,
    sheet_id: str,
    store: ManagementStore | None = None,
) -> list[SheetIssue]:
    store = _store(db_path, store)
    sheet = store.get_sheet_row(sheet_id)
    if sheet is None:
        return [
            SheetIssue(
                sheet_id=sheet_id,
                sheet_name=sheet_id,
                plugin_id="",
                label="Sheet",
                issue="Sheet does not exist.",
            )
        ]
    tabs = store.list_sheet_tab_rows(sheet_id)
    if not tabs:
        return [
            SheetIssue(
                sheet_id=sheet_id,
                sheet_name=sheet.get("name") or sheet_id,
                plugin_id="",
                label="Sheet",
                issue="Sheet has no tabs.",
            )
        ]
    return _validate_sheet_references(db_path, sheet_id=sheet_id, require_prod=True, store=store)


def _validate_sheet_references(
    db_path: Path,
    sheet_id: str | None = None,
    require_prod: bool = False,
    store: ManagementStore | None = None,
) -> list[SheetIssue]:
    store = _store(db_path, store)
    if not store.database_exists():
        return []

    rows = store.list_sheet_reference_records(sheet_id=sheet_id)

    issues: list[SheetIssue] = []
    for row in rows:
        sheet_prod = require_prod or bool(row["sheet_prod"])
        plugin_id = row["plugin_id"]
        base = {
            "sheet_id": row["sheet_id"],
            "sheet_name": row["sheet_name"],
            "plugin_id": plugin_id,
            "label": row["label"],
        }
        if row["tool_id"] is None:
            issues.append(SheetIssue(**base, issue="Referenced plugin does not exist in tools."))
            continue
        if not bool(row["enabled"]):
            issues.append(SheetIssue(**base, issue="Referenced plugin is archived."))
        if sheet_prod and not bool(row["enabled_prod"]):
            issues.append(SheetIssue(**base, issue="Prod sheet references a plugin not enabled in Prod."))
        if sheet_prod and derive_category(plugin_id) == "module" and row["active_version"] is None:
            issues.append(SheetIssue(**base, issue="Prod sheet references a module without an active snapshot."))
    return issues


def collect_dashboard_summary(db_path: Path, store: ManagementStore | None = None) -> dict[str, Any]:
    store = _store(db_path, store)
    tools = collect_tool_readiness(db_path, store=store)
    sheet_issues = validate_sheet_references(db_path, store=store)
    integrity_issues = collect_integrity_issues(db_path, store=store)
    visible = [t for t in tools if t.enabled]
    archived = [t for t in tools if not t.enabled]
    prod_enabled = [t for t in tools if t.enabled_prod]
    modules = [t for t in tools if t.category == "module"]
    published_modules = [t for t in modules if t.has_active_version]
    readiness_issues = [t for t in tools if t.issues]

    return {
        "mode": "DEV" if _is_dev_mode() else "PROD",
        "total_tools": len(tools),
        "visible_tools": len(visible),
        "archived_tools": len(archived),
        "prod_enabled_tools": len(prod_enabled),
        "published_modules": len(published_modules),
        "module_count": len(modules),
        "readiness_issue_count": len(readiness_issues),
        "sheet_issue_count": len(sheet_issues),
        "integrity_issue_count": len(integrity_issues),
    }


def collect_integrity_issues(db_path: Path, store: ManagementStore | None = None) -> list[IntegrityIssue]:
    store = _store(db_path, store)
    if not store.database_exists():
        return [IntegrityIssue("error", "database", str(db_path), "Database file does not exist.")]

    issues: list[IntegrityIssue] = []
    for tool in collect_tool_readiness(db_path, store=store):
        for issue in tool.issues:
            repair = "disable_tool_prod" if tool.enabled_prod else None
            issues.append(IntegrityIssue("warning", "tool", tool.tool_id, issue, repair=repair))
    for sheet_issue in validate_sheet_references(db_path, store=store):
        issues.append(
            IntegrityIssue(
                "warning",
                "sheet",
                sheet_issue.sheet_id,
                f"{sheet_issue.label} ({sheet_issue.plugin_id}): {sheet_issue.issue}",
                repair="disable_sheet_prod",
            )
        )

    multi_active = store.list_multiple_active_versions()
    orphan_versions = store.list_orphan_versions()

    for row in multi_active:
        issues.append(
            IntegrityIssue(
                "error",
                "versions",
                row["tool_id"],
                f"Tool has {row['active_count']} active versions.",
                repair="normalize_active_versions",
            )
        )
    for row in orphan_versions:
        issues.append(
            IntegrityIssue(
                "warning",
                "versions",
                row["tool_id"],
                f"{row['version_count']} version rows reference a missing tool.",
                repair="delete_orphan_versions",
            )
        )
    return issues


def _resolve_module_folder(scripts_dir: Path, plugin_id: str) -> Path:
    """Resolve a module folder across scripts/ AND plugins/*/modules/ (the Labeling
    GUI modules moved to plugins/labeling/modules/ in the platform restructure)."""
    direct = scripts_dir / plugin_id
    if direct.is_dir():
        return direct
    plugins_dir = scripts_dir.parent / "plugins"
    if plugins_dir.is_dir():
        for modroot in sorted(plugins_dir.glob("*/modules")):
            cand = modroot / plugin_id
            if cand.is_dir():
                return cand
    return direct


def module_preflight(scripts_dir: Path, plugin_id: str) -> ModulePreflight:
    folder = _resolve_module_folder(scripts_dir, plugin_id)
    short_id = plugin_id.split("_", 1)[1] if "_" in plugin_id else plugin_id
    files = {
        "plugin.yaml": folder / "plugin.yaml",
        "input": folder / f"{short_id}_input.py",
        "process": folder / f"{short_id}_process.py",
        "output": folder / f"{short_id}_output.py",
    }
    # No-code layers: a module may declare its input fields in plugin.yaml `form:`
    # (no *_input.py) and/or its output blocks in `output:` (no *_output.py).
    declarative_input = declarative_output = external_gui = False
    if files["plugin.yaml"].exists():
        try:
            import yaml  # noqa: PLC0415
            _meta = yaml.safe_load(files["plugin.yaml"].read_text(encoding="utf-8")) or {}
            declarative_input = bool(_meta.get("form"))
            declarative_output = bool(_meta.get("output"))
            external_gui = bool(_meta.get("external_gui"))
        except Exception:
            pass
    # An external-GUI launcher tool (the Label-tool pattern) ships no
    # input/process/output code — the framework renders a launch button from the
    # `external_gui:` block — so only plugin.yaml is required.
    if external_gui:
        required = {"plugin.yaml"}
    else:
        required = {"plugin.yaml", "process"}
        if not declarative_input:
            required.add("input")
        if not declarative_output:
            required.add("output")
    checks = {name: path.exists() for name, path in files.items()}
    issues = [f"Missing {name} file." for name, path in files.items()
              if name in required and not path.exists()]

    process_path = files["process"]
    no_streamlit_import = True
    if process_path.exists():
        source = process_path.read_text(encoding="utf-8", errors="replace")
        no_streamlit_import = "import streamlit" not in source and "from streamlit" not in source
        if not no_streamlit_import:
            issues.append("Process layer imports Streamlit.")
    checks["process_no_streamlit"] = no_streamlit_import

    return ModulePreflight(plugin_id=plugin_id, ok=not issues, checks=checks, issues=issues)


def module_source_snapshot(scripts_dir: Path, plugin_id: str) -> dict[str, str]:
    folder = _resolve_module_folder(scripts_dir, plugin_id)
    if not folder.is_dir():
        return {}
    content: dict[str, str] = {}
    for py_file in sorted(folder.glob("*.py")):
        content[py_file.name] = py_file.read_text(encoding="utf-8")
    manifest = folder / "plugin.yaml"
    if manifest.exists():
        content["plugin.yaml"] = manifest.read_text(encoding="utf-8")
    return content


def active_snapshot_content(
    db_path: Path,
    plugin_id: str,
    store: ManagementStore | None = None,
) -> dict[str, str] | None:
    return _store(db_path, store).get_active_snapshot_content(plugin_id)


def validate_module_snapshot_content(plugin_id: str, content: dict[str, str] | None) -> list[str]:
    if content is None:
        return ["Publish an active snapshot before enabling Prod visibility."]
    if not content:
        return ["Active snapshot content is empty or unreadable."]
    short_id = plugin_id.removeprefix("module_")
    required = ["plugin.yaml", f"{short_id}_input.py", f"{short_id}_process.py", f"{short_id}_output.py"]
    return [f"Active snapshot is missing {name}." for name in required if name not in content]


def module_snapshot_diff(
    scripts_dir: Path,
    db_path: Path,
    plugin_id: str,
    store: ManagementStore | None = None,
) -> ModuleSnapshotDiff:
    current = module_source_snapshot(scripts_dir, plugin_id)
    active = active_snapshot_content(db_path, plugin_id, store=store)
    active_map = active or {}
    current_names = set(current)
    active_names = set(active_map)

    added = sorted(current_names - active_names)
    removed = sorted(active_names - current_names)
    common = current_names & active_names
    changed = sorted(name for name in common if current[name] != active_map[name])
    unchanged = sorted(name for name in common if current[name] == active_map[name])

    return ModuleSnapshotDiff(
        plugin_id=plugin_id,
        has_active_snapshot=active is not None,
        current_file_count=len(current),
        active_file_count=len(active_map),
        added=added,
        removed=removed,
        changed=changed,
        unchanged=unchanged,
    )


def preflight_all_modules(scripts_dir: Path, plugin_ids: list[str]) -> list[ModulePreflight]:
    return [module_preflight(scripts_dir, plugin_id) for plugin_id in plugin_ids]
