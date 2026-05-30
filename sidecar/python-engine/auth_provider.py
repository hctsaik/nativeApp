from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from management_store import ManagementStore, SQLiteManagementStore


class AuthProvider:
    """
    Placeholder auth layer. Currently always returns 'admin' role.
    Future: call a web service to exchange an API token for a role.
    """

    def __init__(self, db_path: Optional[Path] = None, store: ManagementStore | None = None) -> None:
        self._db_path = db_path
        self._store = store or (SQLiteManagementStore(db_path) if db_path is not None else None)

    def get_current_role(self) -> str:
        """Return the role of the current user.

        `CIM_USER_ROLE` is a local development/testing override. Production
        identity can replace this method without changing callers.
        """
        return (os.environ.get("CIM_USER_ROLE") or "admin").strip() or "admin"

    def check_permission(self, plugin_id: str, action: str) -> bool:
        """
        Check whether the current role can perform action on plugin_id.
        action: 'view' | 'execute'

        If no permission row exists for this (plugin_id, role_id) pair,
        the default is to ALLOW (open by default while permissions are not
        fully configured).
        """
        role_id = self.get_current_role()

        # Declarative RBAC: when a permissions.yaml policy exists it is the
        # source of truth (edit YAML to grant/revoke — no code, no GUI).
        try:
            from core.rbac import is_allowed, load_policy  # noqa: PLC0415
            policy = load_policy()
            if policy is not None:
                return is_allowed(policy, role_id, plugin_id, action)
        except Exception:
            pass

        # Fallback: per-(plugin, role) DB rows, else open by default.
        if self._db_path is None or not self._db_path.exists():
            return True
        try:
            permission = self._store.get_permission(plugin_id, role_id, action) if self._store else None
        except Exception:
            return True
        if permission is None:
            return True
        return permission
