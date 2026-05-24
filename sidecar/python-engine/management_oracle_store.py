from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


class OracleManagementStore:
    """Oracle adapter for the ManagementStore port.

    The Oracle driver is optional at import time. Production code can pass a
    connection factory explicitly, or configure this adapter with user/password
    and DSN when `oracledb` is installed.
    """

    def __init__(
        self,
        *,
        user: str | None = None,
        password: str | None = None,
        dsn: str | None = None,
        connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._user = user
        self._password = password
        self._dsn = dsn
        self._connection_factory = connection_factory

    def database_exists(self) -> bool:
        try:
            with self._connect():
                return True
        except Exception:
            return False

    def _connect(self):
        if self._connection_factory is not None:
            return self._connection_factory()
        try:
            import oracledb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "OracleManagementStore requires the optional 'oracledb' package "
                "or an explicit connection_factory."
            ) from exc
        if not (self._user and self._password and self._dsn):
            raise RuntimeError("OracleManagementStore requires user, password, and dsn.")
        return oracledb.connect(user=self._user, password=self._password, dsn=self._dsn)

    @staticmethod
    def _bool(value: bool) -> int:
        return 1 if value else 0

    @staticmethod
    def _read_lob(value: Any) -> Any:
        if hasattr(value, "read"):
            return value.read()
        return value

    @classmethod
    def _rows(cls, cursor: Any) -> list[dict[str, Any]]:
        columns = [str(col[0]).lower() for col in (cursor.description or [])]
        return [
            {name: cls._read_lob(value) for name, value in zip(columns, row)}
            for row in cursor.fetchall()
        ]

    @classmethod
    def _one(cls, cursor: Any) -> dict[str, Any] | None:
        columns = [str(col[0]).lower() for col in (cursor.description or [])]
        row = cursor.fetchone()
        if row is None:
            return None
        return {name: cls._read_lob(value) for name, value in zip(columns, row)}

    @staticmethod
    def _var(cursor: Any):
        try:
            import oracledb  # type: ignore[import-not-found]

            return cursor.var(oracledb.NUMBER)
        except Exception:
            return cursor.var(int)

    @staticmethod
    def _var_value(var: Any) -> int:
        value = var.getvalue()
        if isinstance(value, list):
            value = value[0]
        return int(value)

    def list_tool_readiness_records(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT t.tool_id, t.name, t.enabled, t.enabled_prod,
                          tv.version AS active_version,
                          (SELECT COUNT(*) FROM tool_versions tvc WHERE tvc.tool_id = t.tool_id) AS version_count
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   ORDER BY t.order_index, t.name"""
            )
            return self._rows(cursor)

    def list_sheet_reference_records(self, sheet_id: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE s.sheet_id = :sheet_id" if sheet_id else ""
        params = {"sheet_id": sheet_id} if sheet_id else {}
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""SELECT s.sheet_id, s.name AS sheet_name, s.enabled_prod AS sheet_prod,
                          st.plugin_id, st.label,
                          t.tool_id, t.enabled, t.enabled_prod,
                          tv.version AS active_version
                   FROM sheets s
                   JOIN sheet_tabs st ON st.sheet_id = s.sheet_id
                   LEFT JOIN tools t ON t.tool_id = st.plugin_id
                   LEFT JOIN tool_versions tv ON tv.tool_id = st.plugin_id AND tv.is_active = 1
                   {where}
                   ORDER BY s.name, st.tab_order""",
                params,
            )
            return self._rows(cursor)

    def list_sheet_tab_rows(self, sheet_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plugin_id, label FROM sheet_tabs WHERE sheet_id = :sheet_id ORDER BY tab_order",
                {"sheet_id": sheet_id},
            )
            return self._rows(cursor)

    def count_sheets(self) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) AS c FROM sheets")
            row = self._one(cursor)
            return int(row["c"] if row else 0)

    def list_sheet_ids(self, prod_only: bool = False) -> list[str]:
        sql = "SELECT sheet_id FROM sheets WHERE enabled_prod=1 ORDER BY name" if prod_only else "SELECT sheet_id FROM sheets ORDER BY name"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            return [row["sheet_id"] for row in self._rows(cursor)]

    def get_sheet_row(self, sheet_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT sheet_id, name, description, enabled_dev, enabled_prod FROM sheets WHERE sheet_id=:sheet_id",
                {"sheet_id": sheet_id},
            )
            return self._one(cursor)

    def list_sheet_tabs_with_order(self, sheet_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plugin_id, label, tab_order FROM sheet_tabs WHERE sheet_id=:sheet_id ORDER BY tab_order",
                {"sheet_id": sheet_id},
            )
            return self._rows(cursor)

    def upsert_sheet(self, sheet_id: str, name: str, description: str, tabs: list[dict[str, Any]]) -> None:
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """MERGE INTO sheets s
                   USING (SELECT :sheet_id AS sheet_id FROM dual) src
                   ON (s.sheet_id = src.sheet_id)
                   WHEN MATCHED THEN UPDATE SET name=:name, description=:description
                   WHEN NOT MATCHED THEN INSERT (sheet_id, name, description, enabled_dev, enabled_prod)
                   VALUES (:sheet_id, :name, :description, 1, 0)""",
                {"sheet_id": sheet_id, "name": name, "description": description},
            )
            cursor.execute("DELETE FROM sheet_tabs WHERE sheet_id=:sheet_id", {"sheet_id": sheet_id})
            for i, tab in enumerate(tabs):
                cursor.execute(
                    """INSERT INTO sheet_tabs (sheet_id, tab_order, plugin_id, label)
                       VALUES (:sheet_id, :tab_order, :plugin_id, :label)""",
                    {
                        "sheet_id": sheet_id,
                        "tab_order": i,
                        "plugin_id": tab["plugin_id"],
                        "label": tab["label"],
                    },
                )
            cursor.execute(
                """MERGE INTO tools t
                   USING (SELECT :tool_id AS tool_id FROM dual) src
                   ON (t.tool_id = src.tool_id)
                   WHEN MATCHED THEN UPDATE SET name=:name, enabled=1
                   WHEN NOT MATCHED THEN INSERT (tool_id, name, script_relative_path, version, enabled, enabled_prod, order_index)
                   VALUES (:tool_id, :name, 'sheet_runner.py', '1.0.0', 1, 0, 0)""",
                {"tool_id": tool_id, "name": name},
            )
            conn.commit()

    def delete_sheet(self, sheet_id: str) -> None:
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sheet_tabs WHERE sheet_id=:sheet_id", {"sheet_id": sheet_id})
            cursor.execute("DELETE FROM sheets WHERE sheet_id=:sheet_id", {"sheet_id": sheet_id})
            cursor.execute("UPDATE tools SET enabled=0 WHERE tool_id=:tool_id", {"tool_id": tool_id})
            conn.commit()

    def set_sheet_enabled(self, sheet_id: str, enabled: bool, mode: str = "dev") -> None:
        if mode not in {"dev", "prod"}:
            raise ValueError(f"Unsupported sheet mode: {mode}")
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        tool_id = f"sheet-{sheet_id}"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"UPDATE sheets SET {col}=:enabled WHERE sheet_id=:sheet_id",
                {"enabled": self._bool(enabled), "sheet_id": sheet_id},
            )
            if mode == "prod":
                cursor.execute(
                    "UPDATE tools SET enabled_prod=:enabled WHERE tool_id=:tool_id",
                    {"enabled": self._bool(enabled), "tool_id": tool_id},
                )
            conn.commit()

    def list_multiple_active_versions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT tool_id, COUNT(*) AS active_count
                   FROM tool_versions
                   WHERE is_active = 1
                   GROUP BY tool_id
                   HAVING COUNT(*) > 1"""
            )
            return self._rows(cursor)

    def list_orphan_versions(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT tv.tool_id, COUNT(*) AS version_count
                   FROM tool_versions tv
                   LEFT JOIN tools t ON t.tool_id = tv.tool_id
                   WHERE t.tool_id IS NULL
                   GROUP BY tv.tool_id"""
            )
            return self._rows(cursor)

    def get_active_snapshot_content(self, tool_id: str) -> dict[str, str] | None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT content_json FROM tool_versions WHERE tool_id=:tool_id AND is_active=1",
                {"tool_id": tool_id},
            )
            row = self._one(cursor)
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
            cursor = conn.cursor()
            cursor.execute(
                """MERGE INTO tools t
                   USING (SELECT :plugin_id AS tool_id FROM dual) src
                   ON (t.tool_id = src.tool_id)
                   WHEN MATCHED THEN UPDATE SET
                       description = CASE WHEN :description IS NOT NULL THEN COALESCE(t.description, :description) ELSE t.description END
                   WHEN NOT MATCHED THEN INSERT
                       (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod, description)
                   VALUES (:plugin_id, :name, 'cv_framework_runner.py', :version, 1, 1, 0, :description)""",
                {"plugin_id": plugin_id, "name": name, "version": version, "description": description or None},
            )
            conn.commit()
        return self.get_tool_catalog_row(plugin_id) or {}

    def list_prod_module_tool_ids(self) -> list[str]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tool_id FROM tools WHERE enabled_prod=1 AND tool_id LIKE 'module_%' ORDER BY tool_id"
            )
            return [row["tool_id"] for row in self._rows(cursor)]

    def get_tool_catalog_row(self, tool_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tool_id, name, enabled_dev, enabled_prod, description FROM tools WHERE tool_id=:tool_id",
                {"tool_id": tool_id},
            )
            return self._one(cursor)

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
            cursor = conn.cursor()
            cursor.execute(
                """MERGE INTO tools t
                   USING (SELECT :plugin_id AS tool_id FROM dual) src
                   ON (t.tool_id = src.tool_id)
                   WHEN NOT MATCHED THEN INSERT
                       (tool_id, name, script_relative_path, version, enabled, enabled_dev, enabled_prod)
                   VALUES (:plugin_id, :name, 'cv_framework_runner.py', :version, 1, 1, 0)""",
                {"plugin_id": plugin_id, "name": name, "version": version},
            )
            cursor.execute(
                "UPDATE tools SET name=:name, version=:version, enabled=1, enabled_dev=1 WHERE tool_id=:plugin_id",
                {"plugin_id": plugin_id, "name": name, "version": version},
            )
            if activate:
                cursor.execute("UPDATE tool_versions SET is_active=0 WHERE tool_id=:plugin_id", {"plugin_id": plugin_id})
            version_id = self._var(cursor)
            cursor.execute(
                """INSERT INTO tool_versions
                   (tool_id, version, content_json, changelog, author, is_active, source)
                   VALUES (:plugin_id, :version, :content_json, :changelog, :author, :is_active, :source)
                   RETURNING version_id INTO :version_id""",
                {
                    "plugin_id": plugin_id,
                    "version": version,
                    "content_json": content_json,
                    "changelog": changelog,
                    "author": author,
                    "is_active": 1 if activate else 0,
                    "source": source,
                    "version_id": version_id,
                },
            )
            if enable_prod:
                cursor.execute("UPDATE tools SET enabled_prod=1 WHERE tool_id=:plugin_id", {"plugin_id": plugin_id})
            conn.commit()
            return self._var_value(version_id)

    def activate_tool_version(self, plugin_id: str, version_id: int) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 AS found FROM tool_versions WHERE version_id=:version_id AND tool_id=:plugin_id",
                {"version_id": version_id, "plugin_id": plugin_id},
            )
            if self._one(cursor) is None:
                raise KeyError(f"No version {version_id} for {plugin_id}")
            cursor.execute("UPDATE tool_versions SET is_active=0 WHERE tool_id=:plugin_id", {"plugin_id": plugin_id})
            cursor.execute(
                "UPDATE tool_versions SET is_active=1 WHERE version_id=:version_id AND tool_id=:plugin_id",
                {"version_id": version_id, "plugin_id": plugin_id},
            )
            conn.commit()

    def list_version_rows(self, plugin_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT version_id, tool_id, version, changelog, author,
                          created_at, is_active, source
                   FROM tool_versions WHERE tool_id=:plugin_id ORDER BY version_id DESC""",
                {"plugin_id": plugin_id},
            )
            return self._rows(cursor)

    def list_visible_tool_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT t.tool_id, t.name, t.enabled, t.enabled_prod, t.order_index,
                          tv.version AS active_version, tv.created_at AS published_at
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   WHERE t.enabled = 1 AND t.tool_id NOT LIKE 'management-%'
                   ORDER BY t.order_index, t.name"""
            )
            return self._rows(cursor)

    def list_archived_tool_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT t.tool_id, t.name, t.enabled_prod, t.order_index,
                          tv.version AS active_version
                   FROM tools t
                   LEFT JOIN tool_versions tv ON tv.tool_id = t.tool_id AND tv.is_active = 1
                   WHERE t.enabled = 0 AND t.tool_id NOT LIKE 'management-%'
                   ORDER BY t.name"""
            )
            return self._rows(cursor)

    def list_enabled_tool_definition_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT tool_id, name, script_relative_path, version, signature,
                          source_commit, author, approved_at
                   FROM tools
                   WHERE enabled = 1
                   ORDER BY order_index, name"""
            )
            return self._rows(cursor)

    def get_enabled_tool_definition_row(self, tool_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT tool_id, name, script_relative_path, version, signature,
                          source_commit, author, approved_at
                   FROM tools
                   WHERE tool_id = :tool_id AND enabled = 1""",
                {"tool_id": tool_id},
            )
            return self._one(cursor)

    def list_tools_with_prod_flags(self) -> list[tuple[str, str, bool, bool]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT tool_id, name, enabled, enabled_prod FROM tools ORDER BY name")
            return [
                (r["tool_id"], r["name"], bool(r["enabled"]), bool(r["enabled_prod"]))
                for r in self._rows(cursor)
            ]

    def set_tool_enabled(self, tool_id: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.cursor().execute(
                "UPDATE tools SET enabled=:enabled WHERE tool_id=:tool_id",
                {"enabled": self._bool(enabled), "tool_id": tool_id},
            )
            conn.commit()

    def set_tool_prod_enabled(self, tool_id: str, enabled: bool) -> None:
        with self._connect() as conn:
            conn.cursor().execute(
                "UPDATE tools SET enabled_prod=:enabled WHERE tool_id=:tool_id",
                {"enabled": self._bool(enabled), "tool_id": tool_id},
            )
            conn.commit()

    def update_tool_order(self, order_changes: dict[str, int]) -> None:
        with self._connect() as conn:
            cursor = conn.cursor()
            for tool_id, order_index in order_changes.items():
                cursor.execute(
                    "UPDATE tools SET order_index=:order_index WHERE tool_id=:tool_id",
                    {"order_index": int(order_index), "tool_id": tool_id},
                )
            conn.commit()

    def set_plugin_enabled(self, plugin_id: str, enabled: bool, mode: str = "dev") -> None:
        if mode not in {"dev", "prod"}:
            raise ValueError(f"Unsupported plugin mode: {mode}")
        col = "enabled_dev" if mode == "dev" else "enabled_prod"
        with self._connect() as conn:
            conn.cursor().execute(
                f"UPDATE tools SET {col}=:enabled WHERE tool_id=:plugin_id",
                {"enabled": self._bool(enabled), "plugin_id": plugin_id},
            )
            conn.commit()

    def normalize_active_versions(self, tool_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """SELECT version_id FROM tool_versions
                   WHERE tool_id=:tool_id AND is_active=1
                   ORDER BY version_id DESC""",
                {"tool_id": tool_id},
            )
            rows = self._rows(cursor)
            if len(rows) <= 1:
                return {"kept_version_id": rows[0]["version_id"] if rows else None, "updated_rows": 0}
            keep = int(rows[0]["version_id"])
            cursor.execute(
                "UPDATE tool_versions SET is_active=0 WHERE tool_id=:tool_id AND version_id<>:keep",
                {"tool_id": tool_id, "keep": keep},
            )
            updated = int(cursor.rowcount or 0)
            conn.commit()
            return {"kept_version_id": keep, "updated_rows": updated}

    def delete_orphan_versions(self, tool_id: str) -> int:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 AS found FROM tools WHERE tool_id=:tool_id", {"tool_id": tool_id})
            if self._one(cursor):
                return 0
            cursor.execute("DELETE FROM tool_versions WHERE tool_id=:tool_id", {"tool_id": tool_id})
            deleted = int(cursor.rowcount or 0)
            conn.commit()
            return deleted

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
            cursor = conn.cursor()
            event_id = self._var(cursor)
            cursor.execute(
                """INSERT INTO audit_events
                   (actor, action, target_type, target_id, details_json)
                   VALUES (:actor, :action, :target_type, :target_id, :details_json)
                   RETURNING event_id INTO :event_id""",
                {
                    "actor": actor or "admin",
                    "action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                    "details_json": details_json,
                    "event_id": event_id,
                },
            )
            conn.commit()
            return self._var_value(event_id)

    def list_audit_event_rows(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"""SELECT event_id, created_at, actor, action, target_type, target_id, details_json
                    FROM audit_events
                    ORDER BY event_id DESC
                    FETCH FIRST {safe_limit} ROWS ONLY"""
            )
            return self._rows(cursor)

    def get_permission(self, plugin_id: str, role_id: str, action: str) -> bool | None:
        col = "can_view" if action == "view" else "can_execute"
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT {col} FROM plugin_permissions WHERE plugin_id=:plugin_id AND role_id=:role_id",
                {"plugin_id": plugin_id, "role_id": role_id},
            )
            row = self._one(cursor)
        if row is None:
            return None
        return bool(row[col])

    def list_role_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT role_id, name, description FROM roles")
            return self._rows(cursor)

    def list_permission_rows(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT plugin_id, role_id, can_view, can_execute FROM plugin_permissions ORDER BY plugin_id, role_id"
            )
            return self._rows(cursor)

    def dump_all_tables(self) -> dict[str, list[dict[str, Any]]]:
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT table_name AS name FROM user_tables ORDER BY table_name")
            table_names = [row["name"] for row in self._rows(cursor)]
            dump: dict[str, list[dict[str, Any]]] = {}
            for name in table_names:
                cursor.execute(f"SELECT * FROM {name}")
                dump[name.lower()] = self._rows(cursor)
            return dump
