from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from management_schema import SQLiteManagementSchema
from management_store import SQLiteManagementStore


def _root() -> Path:
    return Path(__file__).resolve().parent


SCRIPTS_DIR = _root() / "scripts"


@dataclass
class PluginInfo:
    plugin_id: str
    name: str
    version: str
    category: str
    description: str = ""
    author: str = ""
    tags: list[str] = field(default_factory=list)
    runner: str = "cv_framework"
    enabled_dev: bool = True
    enabled_prod: bool = False

    @property
    def enabled(self) -> bool:
        return self.enabled_dev if _is_dev_mode() else self.enabled_prod


@dataclass
class SheetTabInfo:
    plugin_id: str
    label: str
    tab_order: int = 0


@dataclass
class SheetInfo:
    sheet_id: str
    name: str
    description: str
    tabs: list[SheetTabInfo] = field(default_factory=list)
    enabled_dev: bool = True
    enabled_prod: bool = False

    @property
    def enabled(self) -> bool:
        return self.enabled_dev if _is_dev_mode() else self.enabled_prod


@dataclass
class VersionInfo:
    version_id: int
    plugin_id: str
    version: str
    changelog: Optional[str]
    author: Optional[str]
    created_at: str
    is_active: bool
    source: str


@dataclass
class AuditEvent:
    event_id: int
    created_at: str
    actor: str
    action: str
    target_type: str
    target_id: str
    details: dict


def _load_plugin_yaml(folder: Path) -> Optional[PluginInfo]:
    manifest = folder / "plugin.yaml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        return PluginInfo(
            plugin_id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            category=data.get("category", "module"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            tags=data.get("tags", []),
            runner=data.get("runner", "cv_framework"),
        )
    except Exception:
        return None


def _load_sheet_yaml(folder: Path) -> Optional[SheetInfo]:
    manifest = folder / "sheet.yaml"
    if not manifest.exists():
        return None
    try:
        data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        tabs = [
            SheetTabInfo(
                plugin_id=t["plugin_id"],
                label=t.get("label", t["plugin_id"]),
                tab_order=i,
            )
            for i, t in enumerate(data.get("tabs", []))
        ]
        return SheetInfo(
            sheet_id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            tabs=tabs,
        )
    except Exception:
        return None


class PluginRegistry:
    def __init__(self, db_path: Path, scripts_dir: Path = SCRIPTS_DIR) -> None:
        self._db_path = db_path
        self._scripts_dir = scripts_dir
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._schema = SQLiteManagementSchema(self._db_path)
        self._store = SQLiteManagementStore(self._db_path)
        self._migrate()

    def _connect(self):
        return self._schema.connect()

    def _migrate(self) -> None:
        self._schema.ensure_current()

    # ?? Filesystem scanning ????????????????????????????????????????????????

    def _module_folders(self) -> list[Path]:
        """All `module_*` folders across scripts/ AND plugins/*/modules/.

        The benchmark Labeling modules physically live under
        plugins/labeling/modules/, so the publish/preflight layer must scan both
        roots — otherwise plugin-located modules are invisible to the management
        center (they can be developed but never published). Mirrors the engine's
        DEV runtime scan (plugin_loader.module_roots)."""
        from plugin_loader import iter_module_folders  # noqa: PLC0415
        return iter_module_folders(self._scripts_dir)

    def _scan_plugins_fs(self) -> list[PluginInfo]:
        plugins: list[PluginInfo] = []
        for folder in self._module_folders():
            if folder.is_dir():
                info = _load_plugin_yaml(folder)
                if info:
                    plugins.append(info)
        return plugins

    def _scan_sheets_fs(self) -> list[SheetInfo]:
        sheets_dir = self._scripts_dir / "sheets"
        sheets: list[SheetInfo] = []
        if sheets_dir.is_dir():
            for folder in sorted(sheets_dir.iterdir()):
                if folder.is_dir():
                    info = _load_sheet_yaml(folder)
                    if info:
                        sheets.append(info)
        return sheets

    # ?? Plugin API (uses tools + tool_versions) ????????????????????????????

    def list_plugins(self) -> list[PluginInfo]:
        if _is_dev_mode():
            raw = self._scan_plugins_fs()
            result = []
            for p in raw:
                row = self._store.upsert_plugin_catalog_entry(
                    p.plugin_id,
                    p.name,
                    p.version,
                    description=p.description,
                )
                result.append(PluginInfo(
                    plugin_id=p.plugin_id, name=p.name, version=p.version,
                    category=p.category, description=p.description,
                    author=p.author, tags=p.tags, runner=p.runner,
                    enabled_dev=bool(row["enabled_dev"]) if row else True,
                    enabled_prod=bool(row["enabled_prod"]) if row else False,
                ))
            return result
        return [p for tool_id in self._store.list_prod_module_tool_ids() for p in [self._plugin_from_db(tool_id)] if p]

    def get_plugin(self, plugin_id: str) -> PluginInfo:
        if _is_dev_mode():
            for folder in self._module_folders():
                if folder.is_dir():
                    info = _load_plugin_yaml(folder)
                    if info and info.plugin_id == plugin_id:
                        return info
            raise KeyError(plugin_id)
        info = self._plugin_from_db(plugin_id)
        if info is None:
            raise KeyError(plugin_id)
        return info

    def get_plugin_content(self, plugin_id: str) -> dict:
        content = self._store.get_active_snapshot_content(plugin_id)
        if content is None:
            raise KeyError(f"No active version for {plugin_id}")
        return content

    def publish(self, plugin_id: str, changelog: str = "", author: str = "system") -> int:
        plugin = self.get_plugin(plugin_id)
        actual_folder = None
        for f in self._module_folders():
            info = _load_plugin_yaml(f)
            if info and info.plugin_id == plugin_id:
                actual_folder = f
                break
        if actual_folder is None:
            raise FileNotFoundError(f"Folder for plugin {plugin_id} not found")

        content: dict[str, str] = {}
        for py_file in sorted(actual_folder.glob("*.py")):
            content[py_file.name] = py_file.read_text(encoding="utf-8")
        manifest = actual_folder / "plugin.yaml"
        if manifest.exists():
            content["plugin.yaml"] = manifest.read_text(encoding="utf-8")
        content_json = json.dumps(content, ensure_ascii=False)
        return self._store.publish_tool_snapshot(
            plugin_id,
            plugin.name,
            plugin.version,
            content_json,
            changelog,
            author,
        )

    def rollback(self, plugin_id: str, version_id: int) -> None:
        self._store.activate_tool_version(plugin_id, version_id)

    def set_enabled(self, plugin_id: str, enabled: bool, mode: str = "dev") -> None:
        self._store.set_plugin_enabled(plugin_id, enabled, mode=mode)

    def set_tool_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        self._store.set_tool_prod_enabled(tool_id, enabled)

    def normalize_active_versions(self, tool_id: str) -> dict:
        return self._store.normalize_active_versions(tool_id)

    def delete_orphan_versions(self, tool_id: str) -> int:
        return self._store.delete_orphan_versions(tool_id)

    def list_versions(self, plugin_id: str) -> list[VersionInfo]:
        rows = self._store.list_version_rows(plugin_id)
        return [
            VersionInfo(
                version_id=r["version_id"],
                plugin_id=r["tool_id"],
                version=r["version"],
                changelog=r["changelog"],
                author=r["author"],
                created_at=r["created_at"],
                is_active=bool(r["is_active"]),
                source=r["source"],
            )
            for r in rows
        ]

    # ?? Audit API ?????????????????????????????????????????????????????????

    def record_audit_event(
        self,
        action: str,
        target_type: str,
        target_id: str,
        actor: str = "admin",
        details: dict | None = None,
    ) -> int:
        return self._store.record_audit_event(action, target_type, target_id, actor=actor, details=details)

    def list_audit_events(self, limit: int = 50) -> list[AuditEvent]:
        rows = self._store.list_audit_event_rows(limit=limit)
        events: list[AuditEvent] = []
        for row in rows:
            try:
                details = json.loads(row["details_json"] or "{}")
            except Exception:
                details = {}
            events.append(
                AuditEvent(
                    event_id=int(row["event_id"]),
                    created_at=row["created_at"],
                    actor=row["actor"],
                    action=row["action"],
                    target_type=row["target_type"],
                    target_id=row["target_id"],
                    details=details,
                )
            )
        return events

    # ?? Sheet API ??????????????????????????????????????????????????????????

    def list_sheets(self) -> list[SheetInfo]:
        if self._store.count_sheets() == 0:
            self.sync_sheets()
        sheet_ids = self._store.list_sheet_ids(prod_only=not _is_dev_mode())
        return [s for sheet_id in sheet_ids for s in [self._sheet_from_db(sheet_id)] if s]

    def get_sheet(self, sheet_id: str) -> SheetInfo:
        s = self._sheet_from_db(sheet_id)
        if s is None:
            self.sync_sheets()
            s = self._sheet_from_db(sheet_id)
        if s is None:
            raise KeyError(sheet_id)
        return s

    def create_or_update_sheet(self, sheet_id: str, name: str, description: str, tabs: list[dict]) -> None:
        self._store.upsert_sheet(sheet_id, name, description, tabs)

    def delete_sheet(self, sheet_id: str) -> None:
        self._store.delete_sheet(sheet_id)

    def set_sheet_enabled(self, sheet_id: str, enabled: bool, mode: str = "dev") -> None:
        self._store.set_sheet_enabled(sheet_id, enabled, mode=mode)

    def sync_sheets(self) -> list[str]:
        synced: list[str] = []
        for sheet in self._scan_sheets_fs():
            self._store.upsert_sheet(
                sheet.sheet_id,
                sheet.name,
                sheet.description,
                [
                    {"plugin_id": tab.plugin_id, "label": tab.label}
                    for tab in sorted(sheet.tabs, key=lambda item: item.tab_order)
                ],
            )
            synced.append(sheet.sheet_id)
        return synced

    # ?? Private helpers ????????????????????????????????????????????????????

    def _plugin_from_db(self, plugin_id: str) -> Optional[PluginInfo]:
        row = self._store.get_tool_catalog_row(plugin_id)
        if row is None:
            return None
        active_content = self._store.get_active_snapshot_content(plugin_id)

        name = row["name"]
        description = row["description"] or ""
        version = "unknown"
        category = "module"
        tags: list[str] = []
        runner = "cv_framework"

        if active_content is not None:
            try:
                if "plugin.yaml" in active_content:
                    data = yaml.safe_load(active_content["plugin.yaml"])
                    name = data.get("name", name)
                    category = data.get("category", category)
                    version = data.get("version", version)
                    description = data.get("description", description)
                    tags = data.get("tags", tags)
                    runner = data.get("runner", runner)
            except Exception:
                pass

        return PluginInfo(
            plugin_id=row["tool_id"],
            name=name,
            category=category,
            version=version,
            description=description,
            tags=tags,
            runner=runner,
            enabled_dev=bool(row["enabled_dev"]),
            enabled_prod=bool(row["enabled_prod"]),
        )

    def _sheet_from_db(self, sheet_id: str) -> Optional[SheetInfo]:
        row = self._store.get_sheet_row(sheet_id)
        if row is None:
            return None
        tab_rows = self._store.list_sheet_tabs_with_order(sheet_id)
        tabs = [
            SheetTabInfo(plugin_id=t["plugin_id"], label=t["label"], tab_order=t["tab_order"])
            for t in tab_rows
        ]
        return SheetInfo(
            sheet_id=row["sheet_id"],
            name=row["name"],
            description=row["description"] or "",
            tabs=tabs,
            enabled_dev=bool(row["enabled_dev"]),
            enabled_prod=bool(row["enabled_prod"]),
        )


def _is_dev_mode() -> bool:
    return (os.environ.get("CIM_DEV_MODE", "1") or "").strip() == "1"
