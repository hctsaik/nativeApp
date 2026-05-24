from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol


class ManagementStore(Protocol):
    """Port for Management Center persistence.

    The application layer should depend on these behaviors instead of direct
    sqlite3 calls. Concrete adapters can map the same behavior to SQLite,
    Oracle, or another database.
    """

    def database_exists(self) -> bool: ...
    def list_tool_readiness_records(self) -> list[dict[str, Any]]: ...
    def list_sheet_reference_records(self, sheet_id: str | None = None) -> list[dict[str, Any]]: ...
    def list_sheet_tab_rows(self, sheet_id: str) -> list[dict[str, Any]]: ...
    def count_sheets(self) -> int: ...
    def list_sheet_ids(self, prod_only: bool = False) -> list[str]: ...
    def get_sheet_row(self, sheet_id: str) -> dict[str, Any] | None: ...
    def list_sheet_tabs_with_order(self, sheet_id: str) -> list[dict[str, Any]]: ...
    def upsert_sheet(self, sheet_id: str, name: str, description: str, tabs: list[dict[str, Any]]) -> None: ...
    def delete_sheet(self, sheet_id: str) -> None: ...
    def set_sheet_enabled(self, sheet_id: str, enabled: bool, mode: str = "dev") -> None: ...
    def list_multiple_active_versions(self) -> list[dict[str, Any]]: ...
    def list_orphan_versions(self) -> list[dict[str, Any]]: ...
    def get_active_snapshot_content(self, tool_id: str) -> dict[str, str] | None: ...
    def upsert_plugin_catalog_entry(
        self,
        plugin_id: str,
        name: str,
        version: str,
        description: str = "",
    ) -> dict[str, Any]: ...
    def list_prod_module_tool_ids(self) -> list[str]: ...
    def get_tool_catalog_row(self, tool_id: str) -> dict[str, Any] | None: ...
    def publish_tool_snapshot(
        self,
        plugin_id: str,
        name: str,
        version: str,
        content_json: str,
        changelog: str,
        author: str,
        source: str = "filesystem",
        activate: bool = True,
        enable_prod: bool = True,
    ) -> int: ...
    def activate_tool_version(self, plugin_id: str, version_id: int) -> None: ...
    def list_version_rows(self, plugin_id: str) -> list[dict[str, Any]]: ...
    def list_visible_tool_rows(self) -> list[dict[str, Any]]: ...
    def list_archived_tool_rows(self) -> list[dict[str, Any]]: ...
    def list_enabled_tool_definition_rows(self) -> list[dict[str, Any]]: ...
    def get_enabled_tool_definition_row(self, tool_id: str) -> dict[str, Any] | None: ...
    def list_tools_with_prod_flags(self) -> list[tuple[str, str, bool, bool]]: ...
    def set_tool_enabled(self, tool_id: str, enabled: bool) -> None: ...
    def set_tool_prod_enabled(self, tool_id: str, enabled: bool) -> None: ...
    def update_tool_order(self, order_changes: dict[str, int]) -> None: ...
    def set_plugin_enabled(self, plugin_id: str, enabled: bool, mode: str = "dev") -> None: ...
    def normalize_active_versions(self, tool_id: str) -> dict[str, Any]: ...
    def delete_orphan_versions(self, tool_id: str) -> int: ...
    def record_audit_event(
        self,
        action: str,
        target_type: str,
        target_id: str,
        actor: str = "admin",
        details: dict | None = None,
    ) -> int: ...
    def list_audit_event_rows(self, limit: int = 50) -> list[dict[str, Any]]: ...
    def start_tool_run(
        self,
        tool_id: str,
        category: str,
        mode: str,
        actor: str = "system",
        input_port: int = 0,
        output_port: int = 0,
        pid: int | None = None,
        log_path: str | None = None,
        run_id: str | None = None,
    ) -> str: ...
    def finish_tool_run(self, run_id: str, status: str, error_summary: str | None = None) -> None: ...
    def list_tool_run_rows(self, limit: int = 50, tool_id: str | None = None) -> list[dict[str, Any]]: ...
    def usage_summary(self, days: int = 30) -> list[dict[str, Any]]: ...
    def log_module_execution(
        self,
        plugin_id: str,
        sheet_id: str | None,
        success: bool,
        duration_ms: int | None,
        actor: str = "user",
    ) -> str: ...
    def module_usage_by_sheet(self, sheet_id: str, days: int = 90) -> list[dict[str, Any]]: ...
    def stale_modules(self, days: int = 90) -> list[dict[str, Any]]: ...
    def delete_draft_tool(self, tool_id: str) -> None: ...
    def get_permission(self, plugin_id: str, role_id: str, action: str) -> bool | None: ...
    def list_role_rows(self) -> list[dict[str, Any]]: ...
    def list_permission_rows(self) -> list[dict[str, Any]]: ...
    def dump_all_tables(self) -> dict[str, list[dict[str, Any]]]: ...


class SQLiteManagementStore:
    """SQLite adapter for the ManagementStore port."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    @property
    def db_path(self) -> Path:
        return self._db_path

    def database_exists(self) -> bool:
        return self._db_path.exists()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def list_tool_readiness_records(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT t.tool_id, t.name, t.enabled, t.enabled_prod,
                          tv.version AS active_version,
                          (SELECT COUNT(*) FROM tool_versions tvc WHERE tvc.tool_id = t.tool_id) AS version_count
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   ORDER BY t.order_index, t.name"""
            ).fetchall()
        return self._rows(rows)

    def list_sheet_reference_records(self, sheet_id: str | None = None) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        where = "WHERE s.sheet_id = ?" if sheet_id else ""
        params = (sheet_id,) if sheet_id else ()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT s.sheet_id, s.name AS sheet_name, s.enabled_prod AS sheet_prod,
                          st.plugin_id, st.label,
                          t.tool_id, t.enabled, t.enabled_prod,
                          tv.version AS active_version
                   FROM sheets s
                   JOIN sheet_tabs st ON st.sheet_id = s.sheet_id
                   LEFT JOIN tools t ON t.tool_id = st.plugin_id
                   LEFT JOIN tool_versions tv ON tv.tool_id = st.plugin_id AND tv.is_active = 1
                   {where}
                   ORDER BY s.name, st.tab_order""".format(where=where),
                params,
            ).fetchall()
        return self._rows(rows)

    def list_sheet_tab_rows(self, sheet_id: str) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT plugin_id, label FROM sheet_tabs WHERE sheet_id = ? ORDER BY tab_order",
                (sheet_id,),
            ).fetchall()
        return self._rows(rows)

    def count_sheets(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS c FROM sheets").fetchone()
        return int(row["c"] if row else 0)

    def list_sheet_ids(self, prod_only: bool = False) -> list[str]:
        with self._connect() as conn:
            if prod_only:
                rows = conn.execute("SELECT sheet_id FROM sheets WHERE enabled_prod=1 ORDER BY name").fetchall()
            else:
                rows = conn.execute("SELECT sheet_id FROM sheets ORDER BY name").fetchall()
        return [row["sheet_id"] for row in rows]

    def get_sheet_row(self, sheet_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sheet_id, name, description, enabled_dev, enabled_prod FROM sheets WHERE sheet_id=?",
                (sheet_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_sheet_tabs_with_order(self, sheet_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT plugin_id, label, tab_order FROM sheet_tabs WHERE sheet_id=? ORDER BY tab_order",
                (sheet_id,),
            ).fetchall()
        return self._rows(rows)

    def upsert_sheet(self, sheet_id: str, name: str, description: str, tabs: list[dict[str, Any]]) -> None:
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
            conn.execute(
                """INSERT OR IGNORE INTO tools
                   (tool_id, name, script_relative_path, version, enabled, enabled_prod, order_index)
                   VALUES (?, ?, 'sheet_runner.py', '1.0.0', 1, 0, 0)""",
                (tool_id, name),
            )
            conn.execute("UPDATE tools SET name=?, enabled=1 WHERE tool_id=?", (name, tool_id))

    def delete_sheet(self, sheet_id: str) -> None:
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            conn.execute("DELETE FROM sheet_tabs WHERE sheet_id=?", (sheet_id,))
            conn.execute("DELETE FROM sheets WHERE sheet_id=?", (sheet_id,))
            conn.execute("UPDATE tools SET enabled=0 WHERE tool_id=?", (tool_id,))

    def set_sheet_enabled(self, sheet_id: str, enabled: bool, mode: str = "dev") -> None:
        if mode not in {"dev", "prod"}:
            raise ValueError(f"Unsupported sheet mode: {mode}")
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            conn.execute(
                f"UPDATE sheets SET {col}=? WHERE sheet_id=?",  # noqa: S608
                (1 if enabled else 0, sheet_id),
            )
            if mode == "prod":
                conn.execute(
                    "UPDATE tools SET enabled_prod=? WHERE tool_id=?",
                    (1 if enabled else 0, tool_id),
                )

    def list_multiple_active_versions(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tool_id, COUNT(*) AS active_count
                   FROM tool_versions
                   WHERE is_active = 1
                   GROUP BY tool_id
                   HAVING COUNT(*) > 1"""
            ).fetchall()
        return self._rows(rows)

    def list_orphan_versions(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tv.tool_id, COUNT(*) AS version_count
                   FROM tool_versions tv
                   LEFT JOIN tools t ON t.tool_id = tv.tool_id
                   WHERE t.tool_id IS NULL
                   GROUP BY tv.tool_id"""
            ).fetchall()
        return self._rows(rows)

    def get_active_snapshot_content(self, tool_id: str) -> dict[str, str] | None:
        if not self.database_exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT content_json FROM tool_versions WHERE tool_id=? AND is_active=1",
                (tool_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            data = json.loads(row["content_json"])
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def upsert_plugin_catalog_entry(
        self,
        plugin_id: str,
        name: str,
        version: str,
        description: str = "",
    ) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO tools
                   (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod, description)
                   VALUES (?, ?, 'cv_framework_runner.py', ?, 1, 1, 0, ?)""",
                (plugin_id, name, version, description),
            )
            if description:
                conn.execute(
                    "UPDATE tools SET description=? WHERE tool_id=? AND (description IS NULL OR description='')",
                    (description, plugin_id),
                )
            row = conn.execute(
                "SELECT tool_id, name, enabled_dev, enabled_prod, description FROM tools WHERE tool_id=?",
                (plugin_id,),
            ).fetchone()
        return dict(row) if row else {}

    def list_prod_module_tool_ids(self) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool_id FROM tools WHERE enabled_prod=1 AND tool_id LIKE 'module_%' ORDER BY tool_id"
            ).fetchall()
        return [row["tool_id"] for row in rows]

    def get_tool_catalog_row(self, tool_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT tool_id, name, enabled_dev, enabled_prod, description FROM tools WHERE tool_id=?",
                (tool_id,),
            ).fetchone()
        return dict(row) if row else None

    def publish_tool_snapshot(
        self,
        plugin_id: str,
        name: str,
        version: str,
        content_json: str,
        changelog: str,
        author: str,
        source: str = "filesystem",
        activate: bool = True,
        enable_prod: bool = True,
    ) -> int:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO tools (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod) VALUES (?, ?, 'cv_framework_runner.py', ?, 1, 1, 0)",
                (plugin_id, name, version),
            )
            conn.execute(
                "UPDATE tools SET name=?, version=?, enabled=1, enabled_dev=1 WHERE tool_id=?",
                (name, version, plugin_id),
            )
            if activate:
                conn.execute("UPDATE tool_versions SET is_active=0 WHERE tool_id=?", (plugin_id,))
            cursor = conn.execute(
                """INSERT INTO tool_versions
                   (tool_id, version, content_json, changelog, author, is_active, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (plugin_id, version, content_json, changelog, author, 1 if activate else 0, source),
            )
            if enable_prod:
                conn.execute("UPDATE tools SET enabled_prod=1 WHERE tool_id=?", (plugin_id,))
            return int(cursor.lastrowid)

    def activate_tool_version(self, plugin_id: str, version_id: int) -> None:
        with self._connect() as conn:
            target = conn.execute(
                "SELECT 1 FROM tool_versions WHERE version_id=? AND tool_id=?",
                (version_id, plugin_id),
            ).fetchone()
            if target is None:
                raise KeyError(f"No version {version_id} for {plugin_id}")
            conn.execute("UPDATE tool_versions SET is_active=0 WHERE tool_id=?", (plugin_id,))
            conn.execute(
                "UPDATE tool_versions SET is_active=1 WHERE version_id=? AND tool_id=?",
                (version_id, plugin_id),
            )

    def list_version_rows(self, plugin_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT version_id, tool_id, version, changelog, author,
                          created_at, is_active, source
                   FROM tool_versions WHERE tool_id=? ORDER BY version_id DESC""",
                (plugin_id,),
            ).fetchall()
        return self._rows(rows)

    def list_visible_tool_rows(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT t.tool_id, t.name, t.enabled, t.enabled_prod, t.order_index,
                          tv.version AS active_version, tv.created_at AS published_at
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   WHERE t.enabled = 1 AND t.tool_id NOT LIKE 'management-%'
                   ORDER BY t.order_index, t.name"""
            ).fetchall()
        return self._rows(rows)

    def list_archived_tool_rows(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT t.tool_id, t.name, t.enabled_prod, t.order_index,
                          tv.version AS active_version
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   WHERE t.enabled = 0 AND t.tool_id NOT LIKE 'management-%'
                   ORDER BY t.name"""
            ).fetchall()
        return self._rows(rows)

    def list_enabled_tool_definition_rows(self) -> list[dict[str, Any]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tool_id, name, script_relative_path, version, signature,
                          source_commit, author, approved_at, slug
                   FROM tools
                   WHERE enabled = 1
                   ORDER BY order_index, name"""
            ).fetchall()
        return self._rows(rows)

    def get_enabled_tool_definition_row(self, tool_id: str) -> dict[str, Any] | None:
        if not self.database_exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                """SELECT tool_id, name, script_relative_path, version, signature,
                          source_commit, author, approved_at, slug
                   FROM tools
                   WHERE tool_id = ? AND enabled = 1""",
                (tool_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tools_with_prod_flags(self) -> list[tuple[str, str, bool, bool]]:
        if not self.database_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT tool_id, name, enabled, enabled_prod FROM tools ORDER BY name"
            ).fetchall()
        return [(r["tool_id"], r["name"], bool(r["enabled"]), bool(r["enabled_prod"])) for r in rows]

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tools SET enabled=? WHERE tool_id=?", (1 if enabled else 0, tool_id))

    def set_tool_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE tools SET enabled_prod=? WHERE tool_id=?", (1 if enabled else 0, tool_id))

    def update_tool_order(self, order_changes: dict[str, int]) -> None:
        with self._connect() as conn:
            for tool_id, order_index in order_changes.items():
                conn.execute("UPDATE tools SET order_index=? WHERE tool_id=?", (int(order_index), tool_id))

    def set_plugin_enabled(self, plugin_id: str, enabled: bool, mode: str = "dev") -> None:
        if mode not in {"dev", "prod"}:
            raise ValueError(f"Unsupported plugin mode: {mode}")
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        with self._connect() as conn:
            conn.execute(
                f"UPDATE tools SET {col}=? WHERE tool_id=?",  # noqa: S608
                (1 if enabled else 0, plugin_id),
            )

    def normalize_active_versions(self, tool_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT version_id FROM tool_versions
                   WHERE tool_id=? AND is_active=1
                   ORDER BY version_id DESC""",
                (tool_id,),
            ).fetchall()
            if len(rows) <= 1:
                return {"kept_version_id": rows[0]["version_id"] if rows else None, "updated_rows": 0}
            keep = int(rows[0]["version_id"])
            cursor = conn.execute(
                "UPDATE tool_versions SET is_active=0 WHERE tool_id=? AND version_id<>?",
                (tool_id, keep),
            )
            return {"kept_version_id": keep, "updated_rows": int(cursor.rowcount or 0)}

    def delete_orphan_versions(self, tool_id: str) -> int:
        with self._connect() as conn:
            exists = conn.execute("SELECT 1 FROM tools WHERE tool_id=?", (tool_id,)).fetchone()
            if exists:
                return 0
            cursor = conn.execute("DELETE FROM tool_versions WHERE tool_id=?", (tool_id,))
            return int(cursor.rowcount or 0)

    def record_audit_event(
        self,
        action: str,
        target_type: str,
        target_id: str,
        actor: str = "admin",
        details: dict | None = None,
    ) -> int:
        details_json = json.dumps(details or {}, ensure_ascii=False, default=str)
        with self._connect() as conn:
            cursor = conn.execute(
                """INSERT INTO audit_events
                   (actor, action, target_type, target_id, details_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (actor or "admin", action, target_type, target_id, details_json),
            )
            return int(cursor.lastrowid)

    def list_audit_event_rows(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT event_id, created_at, actor, action, target_type, target_id, details_json
                   FROM audit_events
                   ORDER BY event_id DESC
                   LIMIT ?""",
                (safe_limit,),
            ).fetchall()
        return self._rows(rows)

    def start_tool_run(
        self,
        tool_id: str,
        category: str,
        mode: str,
        actor: str = "system",
        input_port: int = 0,
        output_port: int = 0,
        pid: int | None = None,
        log_path: str | None = None,
        run_id: str | None = None,
    ) -> str:
        run_id = run_id or uuid.uuid4().hex[:12]
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tool_runs
                   (run_id, tool_id, category, mode, actor, status,
                    input_port, output_port, pid, log_path)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?, ?)""",
                (run_id, tool_id, category, mode, actor or "system", int(input_port), int(output_port), pid, log_path),
            )
        return run_id

    def finish_tool_run(self, run_id: str, status: str, error_summary: str | None = None) -> None:
        safe_status = status if status in {"completed", "failed", "stopped"} else "stopped"
        with self._connect() as conn:
            conn.execute(
                """UPDATE tool_runs
                   SET status=?,
                       ended_at=datetime('now'),
                       duration_ms=CAST((julianday(datetime('now')) - julianday(started_at)) * 86400000 AS INTEGER),
                       error_summary=?
                   WHERE run_id=? AND ended_at IS NULL""",
                (safe_status, error_summary, run_id),
            )

    def list_tool_run_rows(self, limit: int = 50, tool_id: str | None = None) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        if tool_id:
            sql = """SELECT run_id, tool_id, category, mode, actor, status,
                            started_at, ended_at, duration_ms, input_port,
                            output_port, pid, log_path, error_summary
                     FROM tool_runs
                     WHERE tool_id=?
                     ORDER BY started_at DESC, run_id DESC
                     LIMIT ?"""
            params: tuple[Any, ...] = (tool_id, safe_limit)
        else:
            sql = """SELECT run_id, tool_id, category, mode, actor, status,
                            started_at, ended_at, duration_ms, input_port,
                            output_port, pid, log_path, error_summary
                     FROM tool_runs
                     ORDER BY started_at DESC, run_id DESC
                     LIMIT ?"""
            params = (safe_limit,)
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return self._rows(rows)

    def usage_summary(self, days: int = 30) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 365))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tool_id,
                          COUNT(*) AS run_count,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_count,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count,
                          SUM(CASE WHEN status='stopped' THEN 1 ELSE 0 END) AS stopped_count,
                          AVG(duration_ms) AS avg_duration_ms,
                          MAX(started_at) AS last_started_at
                   FROM tool_runs
                   WHERE started_at >= datetime('now', ?)
                   GROUP BY tool_id
                   ORDER BY run_count DESC, tool_id""",
                (f"-{safe_days} days",),
            ).fetchall()
        return self._rows(rows)

    def log_module_execution(
        self,
        plugin_id: str,
        sheet_id: str | None,
        success: bool,
        duration_ms: int | None,
        actor: str = "user",
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        status = "completed" if success else "failed"
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO tool_runs
                   (run_id, tool_id, category, mode, actor, status,
                    context_sheet_id, duration_ms, ended_at)
                   VALUES (?, ?, 'module_exec', 'iframe', ?, ?, ?, ?, datetime('now'))""",
                (run_id, plugin_id, actor or "user", status, sheet_id, duration_ms),
            )
        return run_id

    def module_usage_by_sheet(self, sheet_id: str, days: int = 90) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 365))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT tool_id AS plugin_id,
                          COUNT(*) AS run_count,
                          SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS completed_count,
                          SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) AS failed_count,
                          AVG(duration_ms) AS avg_duration_ms,
                          MAX(started_at) AS last_used_at
                   FROM tool_runs
                   WHERE context_sheet_id = ?
                     AND category = 'module_exec'
                     AND started_at >= datetime('now', ?)
                   GROUP BY tool_id
                   ORDER BY run_count DESC""",
                (sheet_id, f"-{safe_days} days"),
            ).fetchall()
        return self._rows(rows)

    def stale_modules(self, days: int = 90) -> list[dict[str, Any]]:
        safe_days = max(1, min(int(days), 365))
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT t.tool_id, t.name,
                          MAX(tr.started_at) AS last_used_at,
                          COUNT(tr.run_id) AS total_runs
                   FROM tools t
                   LEFT JOIN tool_runs tr
                     ON tr.tool_id = t.tool_id
                    AND tr.category = 'module_exec'
                   WHERE t.enabled = 1
                     AND t.tool_id LIKE 'module_%'
                   GROUP BY t.tool_id, t.name
                   HAVING last_used_at IS NULL
                      OR last_used_at < datetime('now', ?)
                   ORDER BY last_used_at ASC NULLS FIRST""",
                (f"-{safe_days} days",),
            ).fetchall()
        return self._rows(rows)

    def delete_draft_tool(self, tool_id: str) -> None:
        with self._connect() as conn:
            tool = conn.execute(
                "SELECT enabled_prod FROM tools WHERE tool_id=?",
                (tool_id,),
            ).fetchone()
            if tool is None:
                raise KeyError(tool_id)
            if bool(tool["enabled_prod"]):
                raise ValueError("Draft delete is blocked while Prod visibility is on.")
            versions = conn.execute(
                "SELECT COUNT(*) AS c FROM tool_versions WHERE tool_id=?",
                (tool_id,),
            ).fetchone()["c"]
            if int(versions or 0) > 0:
                raise ValueError("Draft delete is allowed only before snapshots exist.")
            refs = conn.execute(
                "SELECT COUNT(*) AS c FROM sheet_tabs WHERE plugin_id=?",
                (tool_id,),
            ).fetchone()["c"]
            if int(refs or 0) > 0:
                raise ValueError("Draft delete is blocked while Sheets reference this module.")
            conn.execute("DELETE FROM tools WHERE tool_id=?", (tool_id,))

    def get_permission(self, plugin_id: str, role_id: str, action: str) -> bool | None:
        col = "can_view" if action == "view" else "can_execute"
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {col} FROM plugin_permissions WHERE plugin_id=? AND role_id=?",  # noqa: S608
                (plugin_id, role_id),
            ).fetchone()
        if row is None:
            return None
        return bool(row[col])

    def list_role_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT role_id, name, description FROM roles").fetchall()
        return self._rows(rows)

    def list_permission_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT plugin_id, role_id, can_view, can_execute FROM plugin_permissions ORDER BY plugin_id, role_id"
            ).fetchall()
        return self._rows(rows)

    def dump_all_tables(self) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as conn:
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
            dump: dict[str, list[dict[str, Any]]] = {}
            for table in tables:
                name = table["name"]
                rows = conn.execute(f"SELECT * FROM [{name}]").fetchall()  # noqa: S608
                dump[name] = self._rows(rows)
        return dump
