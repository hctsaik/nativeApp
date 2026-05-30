"""Tests for declarative RBAC (core.rbac) + auth_provider enforcement."""

from __future__ import annotations

import pytest

from core import rbac

POLICY = {
    "default_policy": "deny",
    "roles": {
        "admin": {"all": True},
        "operator": {"view": ["*"], "execute": ["module_012", "module_026"]},
        "viewer": {"view": ["*"]},
    },
}


@pytest.mark.parametrize("role,plugin,action,expected", [
    ("admin", "module_999", "execute", True),    # all: true
    ("operator", "module_012", "execute", True),  # listed
    ("operator", "module_999", "execute", False), # not listed
    ("operator", "module_999", "view", True),     # view: ["*"]
    ("viewer", "module_012", "view", True),       # view all
    ("viewer", "module_012", "execute", False),   # no execute rule → deny
    ("ghost", "module_012", "execute", False),    # unknown role + default deny
])
def test_is_allowed(role, plugin, action, expected):
    assert rbac.is_allowed(POLICY, role, plugin, action) is expected


def test_unknown_role_default_allow():
    pol = {"default_policy": "allow", "roles": {"admin": {"all": True}}}
    assert rbac.is_allowed(pol, "ghost", "module_012", "execute") is True


def test_no_policy_is_open():
    assert rbac.is_allowed(None, "anyone", "module_012", "execute") is True
    assert rbac.is_allowed({}, "anyone", "module_012", "execute") is True


def test_load_policy_from_log_dir(tmp_path, monkeypatch):
    import yaml
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "permissions.yaml").write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    pol = rbac.load_policy()
    assert pol and pol["roles"]["operator"]["execute"] == ["module_012", "module_026"]


def test_auth_provider_enforces_declarative_policy(tmp_path, monkeypatch):
    import yaml
    from auth_provider import AuthProvider
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "permissions.yaml").write_text(yaml.safe_dump(POLICY), encoding="utf-8")
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))

    monkeypatch.setenv("CIM_USER_ROLE", "viewer")
    auth = AuthProvider(db_path=None)
    assert auth.check_permission("module_012", "view") is True
    assert auth.check_permission("module_012", "execute") is False

    monkeypatch.setenv("CIM_USER_ROLE", "operator")
    assert auth.check_permission("module_026", "execute") is True
    assert auth.check_permission("module_999", "execute") is False
