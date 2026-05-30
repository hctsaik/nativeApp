from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from management_insights import (
    IntegrityIssue,
    SheetIssue,
    module_source_snapshot,
    module_snapshot_diff,
    module_preflight,
    validate_sheet_prod_readiness,
)
from management_package_importer import (
    ModulePackageError,
    PackageIssue,
    ModulePackageReport,
    analyze_module_package,
)
from management_store import ManagementStore
from plugin_registry import PluginRegistry


@dataclass
class PublishToolResult:
    version_id: int
    audit_event_id: int
    file_count: int
    includes_manifest: bool


@dataclass
class ImportModuleResult:
    version_id: int
    audit_event_id: int
    report: ModulePackageReport


@dataclass
class ScaffoldModuleResult:
    plugin_id: str
    folder: Path
    audit_event_id: int
    files: list[str]


@dataclass
class RepairResult:
    action: str
    target_type: str
    target_id: str
    audit_event_id: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeleteDraftToolResult:
    tool_id: str
    audit_event_id: int


class SheetProdReadinessError(RuntimeError):
    def __init__(self, sheet_id: str, issues: list[SheetIssue]) -> None:
        super().__init__(f"Sheet {sheet_id} is not ready for Prod")
        self.sheet_id = sheet_id
        self.issues = issues


class ManagementUseCases:
    """Application use cases for Management Center write workflows."""

    def __init__(
        self,
        db_path: Path,
        scripts_dir: Path,
        registry: PluginRegistry,
        store: ManagementStore,
    ) -> None:
        self._db_path = db_path
        self._scripts_dir = scripts_dir
        self._registry = registry
        self._store = store

    def publish_tool_to_prod(
        self,
        plugin_id: str,
        tool_id: str,
        changelog: str,
        author: str,
        actor: str,
        diff_summary: dict[str, Any],
    ) -> PublishToolResult:
        snapshot = module_source_snapshot(self._scripts_dir, plugin_id)
        version_id = self._registry.publish(plugin_id, changelog=changelog, author=author)
        self._store.set_tool_prod_enabled(tool_id, True)
        audit_event_id = self._store.record_audit_event(
            "publish",
            "tool",
            tool_id,
            actor=actor,
            details={
                "version_id": version_id,
                "changelog": changelog,
                "author": author,
                "file_count": len(snapshot),
                "includes_manifest": "plugin.yaml" in snapshot,
                "diff": diff_summary,
            },
        )
        return PublishToolResult(
            version_id=version_id,
            audit_event_id=audit_event_id,
            file_count=len(snapshot),
            includes_manifest="plugin.yaml" in snapshot,
        )

    def create_snapshot_from_filesystem(
        self,
        plugin_id: str,
        tool_id: str,
        changelog: str,
        author: str,
        actor: str,
    ) -> PublishToolResult:
        preflight = module_preflight(self._scripts_dir, plugin_id)
        if not preflight.ok:
            raise ValueError("; ".join(preflight.issues))
        plugin = self._registry.get_plugin(plugin_id)
        snapshot = module_source_snapshot(self._scripts_dir, plugin_id)
        version_id = self._store.publish_tool_snapshot(
            plugin_id,
            plugin.name,
            plugin.version,
            json.dumps(snapshot, ensure_ascii=False),
            changelog,
            author,
            source="filesystem",
            activate=True,
            enable_prod=False,
        )
        diff = module_snapshot_diff(self._scripts_dir, self._db_path, plugin_id, store=self._store).summary()
        audit_event_id = self._store.record_audit_event(
            "create_snapshot",
            "tool",
            tool_id,
            actor=actor,
            details={
                "version_id": version_id,
                "changelog": changelog,
                "author": author,
                "file_count": len(snapshot),
                "includes_manifest": "plugin.yaml" in snapshot,
                "diff": diff,
            },
        )
        return PublishToolResult(
            version_id=version_id,
            audit_event_id=audit_event_id,
            file_count=len(snapshot),
            includes_manifest="plugin.yaml" in snapshot,
        )

    def analyze_module_package(self, package_bytes: bytes, package_name: str) -> ModulePackageReport:
        probe = analyze_module_package(package_bytes, package_name)
        existing_tool = self._store.get_tool_catalog_row(probe.plugin_id) if probe.plugin_id else None
        existing_content = self._store.get_active_snapshot_content(probe.plugin_id) if probe.plugin_id else None
        return analyze_module_package(
            package_bytes,
            package_name,
            existing_content=existing_content,
            existing_tool=existing_tool,
        )

    def import_module_package(
        self,
        package_bytes: bytes,
        package_name: str,
        changelog: str,
        author: str,
        actor: str,
        allow_update: bool = False,
    ) -> ImportModuleResult:
        report = self.analyze_module_package(package_bytes, package_name)
        if report.is_update and not allow_update:
            report.issues.append(
                PackageIssue(
                    "MODULE_ID_EXISTS",
                    "error",
                    "A module with this id already exists.",
                    file="plugin.yaml",
                    how_to_fix="Choose Update existing module or change the module id.",
                )
            )
            report.ok = False
        existing_versions = self._store.list_version_rows(report.plugin_id) if report.plugin_id else []
        if any(row["version"] == report.version for row in existing_versions):
            report.issues.append(
                PackageIssue(
                    "VERSION_ALREADY_EXISTS",
                    "error",
                    "This module version already exists.",
                    file="plugin.yaml",
                    how_to_fix="Increase plugin.yaml version before importing.",
                )
            )
            report.ok = False
        if not report.ok:
            raise ModulePackageError(report)

        version_id = self._store.publish_tool_snapshot(
            report.plugin_id,
            report.name or report.plugin_id,
            report.version,
            json.dumps(report.content, ensure_ascii=False),
            changelog,
            author,
            source="upload",
            activate=True,
            enable_prod=False,
        )
        audit_event_id = self._store.record_audit_event(
            "import_module_update" if report.is_update else "import_module_create",
            "tool",
            report.plugin_id,
            actor=actor,
            details={
                "version_id": version_id,
                "package_name": package_name,
                "package_hash": report.package_hash,
                "changelog": changelog,
                "author": author,
                "report": report.public_dict(),
            },
        )
        return ImportModuleResult(version_id=version_id, audit_event_id=audit_event_id, report=report)

    def create_module_scaffold(
        self,
        name: str,
        description: str,
        author: str,
        actor: str,
        plugin_id: str | None = None,
    ) -> ScaffoldModuleResult:
        plugin_id = plugin_id or self._next_module_id()
        if not re.match(r"^module_[0-9]{3}$", plugin_id):
            raise ValueError("Module id must match module_NNN.")
        folder = self._scripts_dir / plugin_id
        if folder.exists() or self._store.get_tool_catalog_row(plugin_id):
            raise ValueError(f"Module already exists: {plugin_id}")

        short_id = plugin_id.removeprefix("module_")
        folder.mkdir(parents=True, exist_ok=False)
        manifest = {
            "id": plugin_id,
            "name": name,
            "version": "0.1.0",
            "category": "module",
            "runner": "cv_framework",
            "enabled": True,
            "author": author,
            "description": description,
        }
        files = {
            "plugin.yaml": yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True),
            f"{short_id}_input.py": "def render_input():\n    return {}\n",
            f"{short_id}_process.py": "def execute_logic(params):\n    return params\n",
            f"{short_id}_output.py": "def render_output(result):\n    return None\n",
            "README.md": f"# {name}\n\n{description}\n",
        }
        for filename, source in files.items():
            (folder / filename).write_text(source, encoding="utf-8")

        self._store.upsert_plugin_catalog_entry(plugin_id, name, "0.1.0", description)
        audit_event_id = self._store.record_audit_event(
            "create_module_scaffold",
            "tool",
            plugin_id,
            actor=actor,
            details={"name": name, "description": description, "files": sorted(files)},
        )
        return ScaffoldModuleResult(plugin_id=plugin_id, folder=folder, audit_event_id=audit_event_id, files=sorted(files))

    def rollback_tool_version(
        self,
        plugin_id: str,
        version_id: int,
        actor: str,
    ) -> int:
        self._registry.rollback(plugin_id, version_id)
        return self._store.record_audit_event(
            "rollback",
            "tool",
            plugin_id,
            actor=actor,
            details={"version_id": version_id},
        )

    def set_tool_prod_enabled(
        self,
        tool_id: str,
        enabled: bool,
        actor: str,
        source: str = "management_center",
    ) -> int:
        self._store.set_tool_prod_enabled(tool_id, enabled)
        return self._store.record_audit_event(
            "prod_enable" if enabled else "prod_disable",
            "tool",
            tool_id,
            actor=actor,
            details={"source": source},
        )

    def set_sheet_prod_enabled(
        self,
        sheet_id: str,
        enabled: bool,
        actor: str,
    ) -> int:
        if enabled:
            issues = validate_sheet_prod_readiness(self._db_path, sheet_id, store=self._store)
            if issues:
                raise SheetProdReadinessError(sheet_id, issues)
        self._store.set_sheet_enabled(sheet_id, enabled, mode="prod")
        return self._store.record_audit_event(
            "prod_enable" if enabled else "prod_disable",
            "sheet",
            sheet_id,
            actor=actor,
        )

    def set_sheet_dev_enabled(self, sheet_id: str, enabled: bool, actor: str) -> int:
        self._store.set_sheet_enabled(sheet_id, enabled, mode="dev")
        return self._store.record_audit_event(
            "dev_enable" if enabled else "dev_disable",
            "sheet",
            sheet_id,
            actor=actor,
        )

    def create_or_update_sheet(
        self,
        sheet_id: str,
        name: str,
        description: str,
        tabs: list[dict[str, Any]],
        actor: str,
        action: str = "update",
    ) -> int:
        self._store.upsert_sheet(sheet_id, name, description, tabs)
        return self._store.record_audit_event(
            action,
            "sheet",
            sheet_id,
            actor=actor,
            details={"name": name, "tab_count": len(tabs)},
        )

    def delete_sheet(self, sheet_id: str, name: str, actor: str) -> int:
        self._store.delete_sheet(sheet_id)
        return self._store.record_audit_event(
            "delete",
            "sheet",
            sheet_id,
            actor=actor,
            details={"name": name},
        )

    def delete_draft_tool(self, tool_id: str, actor: str) -> DeleteDraftToolResult:
        self._store.delete_draft_tool(tool_id)
        audit_event_id = self._store.record_audit_event(
            "delete_draft",
            "tool",
            tool_id,
            actor=actor,
            details={"policy": "no_prod_visibility_no_snapshots_no_sheet_references"},
        )
        return DeleteDraftToolResult(tool_id=tool_id, audit_event_id=audit_event_id)

    def repair_integrity_issue(self, issue: IntegrityIssue, actor: str) -> RepairResult:
        if not issue.repair:
            raise ValueError(f"No repair action is available for {issue.target_id}")

        details: dict[str, Any] = {"issue": issue.issue, "repair": issue.repair}
        if issue.repair == "disable_tool_prod":
            self._store.set_tool_prod_enabled(issue.target_id, False)
        elif issue.repair == "disable_sheet_prod":
            self._store.set_sheet_enabled(issue.target_id, False, mode="prod")
        elif issue.repair == "normalize_active_versions":
            details.update(self._store.normalize_active_versions(issue.target_id))
        elif issue.repair == "delete_orphan_versions":
            details["deleted_rows"] = self._store.delete_orphan_versions(issue.target_id)
        else:
            raise ValueError(f"Unsupported repair action: {issue.repair}")

        action = f"repair_{issue.repair}"
        audit_event_id = self._store.record_audit_event(
            action,
            issue.category,
            issue.target_id,
            actor=actor,
            details=details,
        )
        return RepairResult(
            action=action,
            target_type=issue.category,
            target_id=issue.target_id,
            audit_event_id=audit_event_id,
            details=details,
        )

    def _next_module_id(self) -> str:
        used: set[int] = set()
        # Scan scripts/ AND plugins/*/modules/ so a freshly allocated id never
        # collides with a plugin-located module (e.g. Labeling's module_006+).
        from plugin_loader import iter_module_folders  # noqa: PLC0415
        for folder in iter_module_folders(self._scripts_dir):
            if re.match(r"^module_[0-9]{3}$", folder.name):
                used.add(int(folder.name.removeprefix("module_")))
        for row in self._store.list_tool_readiness_records():
            tool_id = row.get("tool_id", "")
            if re.match(r"^module_[0-9]{3}$", tool_id):
                used.add(int(tool_id.removeprefix("module_")))
        next_id = 1
        while next_id in used:
            next_id += 1
        return f"module_{next_id:03d}"
