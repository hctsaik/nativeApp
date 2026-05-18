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
