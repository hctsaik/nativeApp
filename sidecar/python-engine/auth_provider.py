from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional


class AuthProvider:
    """
    Placeholder auth layer. Currently always returns 'admin' role.
    Future: call a web service to exchange an API token for a role.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self._db_path = db_path

    def get_current_role(self) -> str:
        """Return the role of the current user. Placeholder: always 'admin'."""
        return "admin"

    def check_permission(self, plugin_id: str, action: str) -> bool:
        """
        Check whether the current role can perform action on plugin_id.
        action: 'view' | 'execute'

        If no permission row exists for this (plugin_id, role_id) pair,
        the default is to ALLOW (open by default while permissions are not
        fully configured).
        """
        role_id = self.get_current_role()
        if self._db_path is None or not self._db_path.exists():
            return True

        col = "can_view" if action == "view" else "can_execute"
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    f"SELECT {col} FROM plugin_permissions WHERE plugin_id=? AND role_id=?",  # noqa: S608
                    (plugin_id, role_id),
                ).fetchone()
        except sqlite3.Error:
            return True

        if row is None:
            return True
        return bool(row[col])
