from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


def _root() -> Path:
    return Path(__file__).resolve().parent


SCRIPTS_DIR = _root() / "scripts"

_MIGRATION_SQL = """
CREATE TABLE IF NOT EXISTS tools (
    tool_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    script_relative_path TEXT NOT NULL DEFAULT 'cv_framework_runner.py',
    version              TEXT NOT NULL DEFAULT '1.0.0',
    signature            TEXT,
    source_commit        TEXT,
    author               TEXT,
    approved_at          TEXT,
    enabled              INTEGER NOT NULL DEFAULT 1,
    enabled_prod         INTEGER NOT NULL DEFAULT 0,
    enabled_dev          INTEGER NOT NULL DEFAULT 1,
    order_index          INTEGER NOT NULL DEFAULT 0,
    description          TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    role_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS users (
    user_id    TEXT PRIMARY KEY,
    username   TEXT NOT NULL UNIQUE,
    role_id    TEXT REFERENCES roles(role_id),
    api_token  TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tool_versions (
    version_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    tool_id      TEXT NOT NULL,
    version      TEXT NOT NULL,
    content_json TEXT NOT NULL,
    changelog    TEXT,
    author       TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    is_active    INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'filesystem'
);

CREATE TABLE IF NOT EXISTS sheets (
    sheet_id    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    enabled_dev  INTEGER NOT NULL DEFAULT 1,
    enabled_prod INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sheet_tabs (
    tab_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    sheet_id   TEXT NOT NULL REFERENCES sheets(sheet_id),
    tab_order  INTEGER NOT NULL,
    plugin_id  TEXT NOT NULL,
    label      TEXT NOT NULL,
    UNIQUE(sheet_id, tab_order)
);

CREATE TABLE IF NOT EXISTS plugin_permissions (
    perm_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id   TEXT NOT NULL,
    role_id     TEXT NOT NULL REFERENCES roles(role_id),
    can_view    INTEGER NOT NULL DEFAULT 1,
    can_execute INTEGER NOT NULL DEFAULT 1,
    UNIQUE(plugin_id, role_id)
);
"""

_ALTER_MIGRATIONS = [
    "ALTER TABLE tools ADD COLUMN enabled_dev INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE tools ADD COLUMN description TEXT",
]

_SEED_SQL = """
INSERT OR IGNORE INTO roles VALUES ('admin',    '管理員', '完整存取所有外掛');
INSERT OR IGNORE INTO roles VALUES ('operator', '操作員', '可執行，不可管理');
INSERT OR IGNORE INTO roles VALUES ('viewer',   '觀察員', '唯讀，不可執行');
"""


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
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _migrate(self) -> None:
        with self._connect() as conn:
            for statement in _MIGRATION_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)
            for statement in _SEED_SQL.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(stmt)
            for stmt in _ALTER_MIGRATIONS:
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError:
                    pass
            # One-time: migrate plugin_versions → tool_versions
            try:
                count = conn.execute("SELECT COUNT(*) as c FROM tool_versions").fetchone()["c"]
                legacy = conn.execute("SELECT COUNT(*) as c FROM plugin_versions").fetchone()["c"]
                if count == 0 and legacy > 0:
                    conn.execute("""
                        INSERT INTO tool_versions
                            (tool_id, version, content_json, changelog, author, created_at, is_active, source)
                        SELECT plugin_id, version, content_json, changelog, author, created_at, is_active, source
                        FROM plugin_versions
                    """)
            except Exception:
                pass
            # One-time: copy enabled states from plugins → tools (MAX: only upgrade, never downgrade)
            try:
                conn.execute("""
                    UPDATE tools SET
                        enabled_dev  = MAX(enabled_dev,  COALESCE((SELECT enabled_dev  FROM plugins WHERE plugin_id = tools.tool_id), 0)),
                        enabled_prod = MAX(enabled_prod, COALESCE((SELECT enabled_prod FROM plugins WHERE plugin_id = tools.tool_id), 0))
                    WHERE tool_id LIKE 'module_%'
                """)
            except Exception:
                pass
            # Drop legacy tables — data is fully in tools/tool_versions
            try:
                conn.execute("DROP TABLE IF EXISTS plugin_versions")
                conn.execute("DROP TABLE IF EXISTS plugins")
            except Exception:
                pass

    # ── Filesystem scanning ────────────────────────────────────────────────

    def _scan_plugins_fs(self) -> list[PluginInfo]:
        plugins: list[PluginInfo] = []
        for folder in sorted(self._scripts_dir.glob("module_*")):
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

    # ── Plugin API (uses tools + tool_versions) ────────────────────────────

    def list_plugins(self) -> list[PluginInfo]:
        if _is_dev_mode():
            raw = self._scan_plugins_fs()
            result = []
            with self._connect() as conn:
                for p in raw:
                    conn.execute(
                        """INSERT OR IGNORE INTO tools
                           (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod, description)
                           VALUES (?, ?, 'cv_framework_runner.py', ?, 1, 1, 0, ?)""",
                        (p.plugin_id, p.name, p.version, p.description),
                    )
                    if p.description:
                        conn.execute(
                            "UPDATE tools SET description=? WHERE tool_id=? AND (description IS NULL OR description='')",
                            (p.description, p.plugin_id),
                        )
                    row = conn.execute(
                        "SELECT enabled_dev, enabled_prod FROM tools WHERE tool_id=?",
                        (p.plugin_id,),
                    ).fetchone()
                    result.append(PluginInfo(
                        plugin_id=p.plugin_id, name=p.name, version=p.version,
                        category=p.category, description=p.description,
                        author=p.author, tags=p.tags, runner=p.runner,
                        enabled_dev=bool(row["enabled_dev"]) if row else True,
                        enabled_prod=bool(row["enabled_prod"]) if row else False,
                    ))
            return result
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool_id FROM tools WHERE enabled_prod=1 AND tool_id LIKE 'module_%' ORDER BY tool_id"
            ).fetchall()
        return [p for row in rows for p in [self._plugin_from_db(row["tool_id"])] if p]

    def get_plugin(self, plugin_id: str) -> PluginInfo:
        if _is_dev_mode():
            for folder in self._scripts_dir.glob("module_*"):
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
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content_json FROM tool_versions WHERE tool_id=? AND is_active=1",
                (plugin_id,),
            ).fetchone()
        if row is None:
            raise KeyError(f"No active version for {plugin_id}")
        return json.loads(row["content_json"])

    def publish(self, plugin_id: str, changelog: str = "", author: str = "system") -> int:
        plugin = self.get_plugin(plugin_id)
        actual_folder = None
        for f in self._scripts_dir.glob("module_*"):
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

        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tools (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod) VALUES (?, ?, 'cv_framework_runner.py', ?, 1, 1, 0)",
                (plugin_id, plugin.name, plugin.version),
            )
            conn.execute(
                "UPDATE tool_versions SET is_active=0 WHERE tool_id=?",
                (plugin_id,),
            )
            cursor = conn.execute(
                """INSERT INTO tool_versions
                   (tool_id, version, content_json, changelog, author, is_active, source)
                   VALUES (?, ?, ?, ?, ?, 1, 'filesystem')""",
                (plugin_id, plugin.version, content_json, changelog, author),
            )
            conn.execute("UPDATE tools SET enabled_prod=1 WHERE tool_id=?", (plugin_id,))
            return cursor.lastrowid

    def rollback(self, plugin_id: str, version_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tool_versions SET is_active=0 WHERE tool_id=?", (plugin_id,))
            conn.execute(
                "UPDATE tool_versions SET is_active=1 WHERE version_id=? AND tool_id=?",
                (version_id, plugin_id),
            )

    def set_enabled(self, plugin_id: str, enabled: bool, mode: str = "dev") -> None:
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        with self._connect() as conn:
            conn.execute(
                f"UPDATE tools SET {col}=? WHERE tool_id=?",  # noqa: S608
                (1 if enabled else 0, plugin_id),
            )

    def list_versions(self, plugin_id: str) -> list[VersionInfo]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT version_id, tool_id, version, changelog, author,
                          created_at, is_active, source
                   FROM tool_versions WHERE tool_id=? ORDER BY version_id DESC""",
                (plugin_id,),
            ).fetchall()
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

    # ── Sheet API ──────────────────────────────────────────────────────────

    def list_sheets(self) -> list[SheetInfo]:
        with self._connect() as conn:
            count = conn.execute("SELECT COUNT(*) as c FROM sheets").fetchone()["c"]
        if count == 0:
            self.sync_sheets()
        with self._connect() as conn:
            if _is_dev_mode():
                rows = conn.execute("SELECT sheet_id FROM sheets ORDER BY name").fetchall()
            else:
                rows = conn.execute(
                    "SELECT sheet_id FROM sheets WHERE enabled_prod=1 ORDER BY name"
                ).fetchall()
        return [s for row in rows for s in [self._sheet_from_db(row["sheet_id"])] if s]

    def get_sheet(self, sheet_id: str) -> SheetInfo:
        s = self._sheet_from_db(sheet_id)
        if s is None:
            self.sync_sheets()
            s = self._sheet_from_db(sheet_id)
        if s is None:
            raise KeyError(sheet_id)
        return s

    def create_or_update_sheet(self, sheet_id: str, name: str, description: str, tabs: list[dict]) -> None:
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO sheets (sheet_id, name, description, enabled_dev, enabled_prod) VALUES (?, ?, ?, 1, 0)",
                (sheet_id, name, description),
            )
            conn.execute(
                "UPDATE sheets SET name=?, description=? WHERE sheet_id=?",
                (name, description, sheet_id),
            )
            conn.execute("DELETE FROM sheet_tabs WHERE sheet_id=?", (sheet_id,))
            for i, tab in enumerate(tabs):
                conn.execute(
                    "INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label) VALUES (?, ?, ?, ?)",
                    (sheet_id, i, tab["plugin_id"], tab["label"]),
                )
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO tools
                       (tool_id, name, script_relative_path, version, enabled, enabled_prod, order_index)
                       VALUES (?, ?, 'sheet_runner.py', '1.0.0', 1, 0, 0)""",
                    (tool_id, name),
                )
                conn.execute("UPDATE tools SET name=?, enabled=1 WHERE tool_id=?", (name, tool_id))
            except Exception:
                pass

    def delete_sheet(self, sheet_id: str) -> None:
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            conn.execute("DELETE FROM sheet_tabs WHERE sheet_id=?", (sheet_id,))
            conn.execute("DELETE FROM sheets WHERE sheet_id=?", (sheet_id,))
            try:
                conn.execute("UPDATE tools SET enabled=0 WHERE tool_id=?", (tool_id,))
            except Exception:
                pass

    def set_sheet_enabled(self, sheet_id: str, enabled: bool, mode: str = "dev") -> None:
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            conn.execute(
                f"UPDATE sheets SET {col}=? WHERE sheet_id=?",  # noqa: S608
                (1 if enabled else 0, sheet_id),
            )
            if mode == "prod":
                try:
                    conn.execute(
                        "UPDATE tools SET enabled_prod=? WHERE tool_id=?",
                        (1 if enabled else 0, tool_id),
                    )
                except Exception:
                    pass

    def sync_sheets(self) -> list[str]:
        synced: list[str] = []
        for sheet in self._scan_sheets_fs():
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO sheets (sheet_id, name, description, enabled_dev, enabled_prod) VALUES (?, ?, ?, 1, 0)",
                    (sheet.sheet_id, sheet.name, sheet.description),
                )
                conn.execute(
                    "UPDATE sheets SET name=?, description=? WHERE sheet_id=?",
                    (sheet.name, sheet.description, sheet.sheet_id),
                )
                conn.execute("DELETE FROM sheet_tabs WHERE sheet_id=?", (sheet.sheet_id,))
                for tab in sheet.tabs:
                    conn.execute(
                        "INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label) VALUES (?, ?, ?, ?)",
                        (sheet.sheet_id, tab.tab_order, tab.plugin_id, tab.label),
                    )
            synced.append(sheet.sheet_id)
        return synced

    # ── Private helpers ────────────────────────────────────────────────────

    def _plugin_from_db(self, plugin_id: str) -> Optional[PluginInfo]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tool_id, name, enabled_dev, enabled_prod, description FROM tools WHERE tool_id=?",
                (plugin_id,),
            ).fetchone()
            if row is None:
                return None
            ver_row = conn.execute(
                "SELECT content_json FROM tool_versions WHERE tool_id=? AND is_active=1",
                (plugin_id,),
            ).fetchone()

        name = row["name"]
        description = row["description"] or ""
        version = "unknown"
        category = "module"
        tags: list[str] = []
        runner = "cv_framework"

        if ver_row:
            try:
                content = json.loads(ver_row["content_json"])
                if "plugin.yaml" in content:
                    data = yaml.safe_load(content["plugin.yaml"])
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
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sheet_id, name, description, enabled_dev, enabled_prod FROM sheets WHERE sheet_id=?",
                (sheet_id,),
            ).fetchone()
            if row is None:
                return None
            tab_rows = conn.execute(
                "SELECT plugin_id, label, tab_order FROM sheet_tabs WHERE sheet_id=? ORDER BY tab_order",
                (sheet_id,),
            ).fetchall()
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
