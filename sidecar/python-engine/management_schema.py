from __future__ import annotations

import sqlite3
from pathlib import Path


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

CREATE TABLE IF NOT EXISTS audit_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TEXT DEFAULT (datetime('now')),
    actor       TEXT NOT NULL,
    action      TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id   TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tool_runs (
    run_id        TEXT PRIMARY KEY,
    tool_id       TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'module',
    mode          TEXT NOT NULL DEFAULT 'iframe',
    actor         TEXT NOT NULL DEFAULT 'system',
    status        TEXT NOT NULL DEFAULT 'running',
    started_at    TEXT DEFAULT (datetime('now')),
    ended_at      TEXT,
    duration_ms   INTEGER,
    input_port    INTEGER NOT NULL DEFAULT 0,
    output_port   INTEGER NOT NULL DEFAULT 0,
    pid           INTEGER,
    log_path      TEXT,
    error_summary TEXT
);
"""

_ALTER_MIGRATIONS = [
    "ALTER TABLE tools ADD COLUMN enabled_dev INTEGER NOT NULL DEFAULT 1",
    "ALTER TABLE tools ADD COLUMN description TEXT",
    "ALTER TABLE tools ADD COLUMN slug TEXT",
    "ALTER TABLE tool_runs ADD COLUMN context_sheet_id TEXT",
]

_SEED_SQL = """
INSERT OR IGNORE INTO roles VALUES ('admin',    '管理員', '完整存取所有外掛');
INSERT OR IGNORE INTO roles VALUES ('operator', '操作員', '可執行，不可管理');
INSERT OR IGNORE INTO roles VALUES ('viewer',   '觀察員', '唯讀，不可執行');
"""


class SQLiteManagementSchema:
    """SQLite schema/migration owner for the platform management database."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def ensure_current(self) -> None:
        with self.connect() as conn:
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
            self._migrate_legacy_plugin_tables(conn)

    def _migrate_legacy_plugin_tables(self, conn: sqlite3.Connection) -> None:
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
        try:
            conn.execute("""
                UPDATE tools SET
                    enabled_dev  = MAX(enabled_dev,  COALESCE((SELECT enabled_dev  FROM plugins WHERE plugin_id = tools.tool_id), 0)),
                    enabled_prod = MAX(enabled_prod, COALESCE((SELECT enabled_prod FROM plugins WHERE plugin_id = tools.tool_id), 0))
                WHERE tool_id LIKE 'module_%'
            """)
        except Exception:
            pass
        try:
            conn.execute("DROP TABLE IF EXISTS plugin_versions")
            conn.execute("DROP TABLE IF EXISTS plugins")
        except Exception:
            pass
