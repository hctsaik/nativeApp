from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from management_store import ManagementStore, SQLiteManagementStore

VALID_ROLES = ("admin", "operator", "viewer")


def default_identity_file() -> Path:
    """The no-env-plumbing identity file the role switcher writes to."""
    return Path(__file__).resolve().parent / "config" / "identity.json"


def set_identity(role: str, path: Path | None = None) -> Path:
    """Persist the current role to the identity file (used by the Management
    Center role switcher / CLI). Makes RBAC switchable without setting env vars.
    Returns the path written."""
    import json  # noqa: PLC0415
    role = str(role).strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"role must be one of {VALID_ROLES}, got {role!r}")
    target = path or default_identity_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"role": role}, ensure_ascii=False), encoding="utf-8")
    return target


class AuthProvider:
    """Auth layer: pluggable identity source + declarative RBAC enforcement.

    Identity resolution (see get_current_role): CIM_IDENTITY_FILE (JSON
    `{"role": ...}`, the SSO/IdP extension point) → CIM_USER_ROLE (dev override)
    → 'admin' default. Permissions come from config/permissions.yaml via
    check_permission(plugin_id, action), enforced by the runners
    (cv_framework_runner / sheet_runner / workflow_runner). Not a stub — RBAC is
    live and unit-tested (tests/test_rbac.py). The remaining production step is
    wiring CIM_IDENTITY_FILE to a real IdP and a role-assignment UI.
    """

    def __init__(self, db_path: Optional[Path] = None, store: ManagementStore | None = None) -> None:
        self._db_path = db_path
        self._store = store or (SQLiteManagementStore(db_path) if db_path is not None else None)

    def get_current_role(self) -> str:
        """Return the role of the current user via a pluggable identity source.

        Resolution order (first hit wins):
          1. CIM_IDENTITY_FILE — path to a JSON `{"role": "..."}` written by a
             production SSO/IdP integration (the supported extension point).
          2. The default identity file (config/identity.json) — written by the
             Management Center role switcher / `set_identity()`, so RBAC is
             switchable with NO env plumbing (the demonstrable dev/admin flow).
          3. CIM_USER_ROLE — local dev/test override.
          4. 'admin' default.
        """
        import json  # noqa: PLC0415
        for path in (os.environ.get("CIM_IDENTITY_FILE"), str(default_identity_file())):
            if not path:
                continue
            try:
                data = json.loads(Path(path).read_text(encoding="utf-8"))
                role = str(data.get("role") or "").strip()
                if role:
                    return role
            except Exception:
                continue
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
