from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from auth_provider import AuthProvider


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "data" / "tools.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE roles (
                role_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE plugins (
                plugin_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT 'module', enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE plugin_permissions (
                perm_id     INTEGER PRIMARY KEY AUTOINCREMENT,
                plugin_id   TEXT NOT NULL,
                role_id     TEXT NOT NULL,
                can_view    INTEGER NOT NULL DEFAULT 1,
                can_execute INTEGER NOT NULL DEFAULT 1,
                UNIQUE(plugin_id, role_id)
            )
        """)
        conn.execute("INSERT INTO roles VALUES ('admin', '管理員', NULL)")
        conn.execute("INSERT INTO roles VALUES ('viewer', '觀察員', NULL)")
        conn.execute("INSERT INTO plugins VALUES ('plugin_a', 'Plugin A', 'module', 1)")
        conn.execute("INSERT INTO plugins VALUES ('plugin_b', 'Plugin B', 'module', 1)")
        # admin: full access to plugin_a
        conn.execute(
            "INSERT INTO plugin_permissions (plugin_id, role_id, can_view, can_execute) VALUES (?, ?, ?, ?)",
            ("plugin_a", "admin", 1, 1),
        )
        # viewer: view only for plugin_b
        conn.execute(
            "INSERT INTO plugin_permissions (plugin_id, role_id, can_view, can_execute) VALUES (?, ?, ?, ?)",
            ("plugin_b", "viewer", 1, 0),
        )
    return path


@pytest.fixture()
def auth(db_path: Path) -> AuthProvider:
    return AuthProvider(db_path=db_path)


@pytest.fixture()
def auth_no_db() -> AuthProvider:
    return AuthProvider(db_path=None)


# ── get_current_role ─────────────────────────────────────────────────────────


def test_get_current_role_returns_admin(auth: AuthProvider) -> None:
    assert auth.get_current_role() == "admin"


def test_get_current_role_no_db(auth_no_db: AuthProvider) -> None:
    assert auth_no_db.get_current_role() == "admin"


def test_get_current_role_uses_env_override(
    auth: AuthProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_USER_ROLE", "viewer")
    assert auth.get_current_role() == "viewer"


# ── check_permission: no DB ──────────────────────────────────────────────────


def test_no_db_allows_view(auth_no_db: AuthProvider) -> None:
    assert auth_no_db.check_permission("any_plugin", "view") is True


def test_no_db_allows_execute(auth_no_db: AuthProvider) -> None:
    assert auth_no_db.check_permission("any_plugin", "execute") is True


def test_missing_db_file_allows_all(tmp_path: Path) -> None:
    auth = AuthProvider(db_path=tmp_path / "nonexistent.sqlite")
    assert auth.check_permission("plugin_a", "view") is True
    assert auth.check_permission("plugin_a", "execute") is True


# ── check_permission: with DB ─────────────────────────────────────────────────


def test_admin_can_view_plugin_a(auth: AuthProvider) -> None:
    assert auth.check_permission("plugin_a", "view") is True


def test_admin_can_execute_plugin_a(auth: AuthProvider) -> None:
    assert auth.check_permission("plugin_a", "execute") is True


def test_no_permission_row_defaults_to_allow(auth: AuthProvider) -> None:
    # plugin_b has no row for 'admin' → default allow
    assert auth.check_permission("plugin_b", "view") is True
    assert auth.check_permission("plugin_b", "execute") is True


def test_completely_unknown_plugin_defaults_to_allow(auth: AuthProvider) -> None:
    assert auth.check_permission("plugin_zzz", "view") is True
    assert auth.check_permission("plugin_zzz", "execute") is True


# ── check_permission: viewer role (manual test via subclass) ──────────────────


class _ViewerAuth(AuthProvider):
    def get_current_role(self) -> str:
        return "viewer"


def test_viewer_can_view_plugin_b(db_path: Path) -> None:
    auth = _ViewerAuth(db_path=db_path)
    assert auth.check_permission("plugin_b", "view") is True


def test_viewer_cannot_execute_plugin_b(db_path: Path) -> None:
    auth = _ViewerAuth(db_path=db_path)
    assert auth.check_permission("plugin_b", "execute") is False


# ── management role gate (mirrors _can_manage() in management_runner.py) ─────


def test_admin_role_can_manage(auth: AuthProvider) -> None:
    # Default env: no CIM_USER_ROLE set → role is 'admin'
    assert auth.get_current_role() == "admin"


def test_viewer_role_cannot_manage(
    auth: AuthProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_USER_ROLE", "viewer")
    assert auth.get_current_role() != "admin"


def test_operator_role_cannot_manage(
    auth: AuthProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_USER_ROLE", "operator")
    assert auth.get_current_role() != "admin"


def test_empty_env_falls_back_to_admin(
    auth: AuthProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_USER_ROLE", "")
    assert auth.get_current_role() == "admin"


def test_whitespace_env_falls_back_to_admin(
    auth: AuthProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CIM_USER_ROLE", "   ")
    assert auth.get_current_role() == "admin"


# ── set_identity + default identity file (no-env-plumbing role switch) ────────


def test_set_identity_via_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import auth_provider
    target = tmp_path / "identity.json"
    auth_provider.set_identity("operator", path=target)
    monkeypatch.setenv("CIM_IDENTITY_FILE", str(target))
    assert AuthProvider().get_current_role() == "operator"


def test_default_identity_file_resolves_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Writing the DEFAULT identity file switches role with no env var set."""
    import auth_provider
    default = tmp_path / "config" / "identity.json"
    monkeypatch.setattr(auth_provider, "default_identity_file", lambda: default)
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("CIM_USER_ROLE", raising=False)
    auth_provider.set_identity("viewer")  # writes the (patched) default path
    assert AuthProvider().get_current_role() == "viewer"


def test_default_identity_file_precedes_user_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import auth_provider
    default = tmp_path / "config" / "identity.json"
    monkeypatch.setattr(auth_provider, "default_identity_file", lambda: default)
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    auth_provider.set_identity("viewer")
    monkeypatch.setenv("CIM_USER_ROLE", "admin")  # default file wins over this
    assert AuthProvider().get_current_role() == "viewer"


def test_set_identity_rejects_bad_role(tmp_path: Path) -> None:
    import auth_provider
    with pytest.raises(ValueError):
        auth_provider.set_identity("superuser", path=tmp_path / "id.json")


def test_set_role_cli_writes_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import auth_provider
    import importlib.util
    default = tmp_path / "config" / "identity.json"
    monkeypatch.setattr(auth_provider, "default_identity_file", lambda: default)
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    monkeypatch.delenv("CIM_USER_ROLE", raising=False)
    spec = importlib.util.spec_from_file_location(
        "_set_role_cli", Path(__file__).resolve().parents[1] / "tools" / "set_role.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["operator"]) == 0
    assert AuthProvider().get_current_role() == "operator"
    assert mod.main(["bogus"]) == 2  # invalid role rejected
