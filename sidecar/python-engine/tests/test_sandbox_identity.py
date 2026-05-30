"""Tests for the load-time plugin sandbox (core.sandbox) + pluggable identity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import sandbox


# ─── sandbox AST deny-list (pure) ─────────────────────────────────────────────

def test_scan_clean_source():
    assert sandbox.scan_source("def f(x):\n    return x + 1\n") == []


@pytest.mark.parametrize("src,frag", [
    ("import subprocess\n", "subprocess"),
    ("from socket import socket\n", "socket"),
    ("eval('1+1')\n", "eval"),
    ("import os\nos.system('ls')\n", "os.system"),
    ("__import__('os')\n", "__import__"),
])
def test_scan_flags_dangerous(src, frag):
    violations = sandbox.scan_source(src)
    assert violations and any(frag in v for v in violations)


def test_check_source_enforce_raises(monkeypatch):
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "enforce")
    with pytest.raises(sandbox.SandboxViolation):
        sandbox.check_source("import subprocess\n", "evil.py")


def test_check_source_warn_does_not_raise(monkeypatch):
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "warn")
    # returns violations but does not raise
    assert sandbox.check_source("import subprocess\n", "x.py")


def test_check_source_off_skips(monkeypatch):
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "off")
    assert sandbox.check_source("import subprocess\n", "x.py") == []


def test_declarative_sandbox_policy_overrides(tmp_path, monkeypatch):
    """No-code rule editing: config/sandbox_policy.yaml extends/relaxes the deny-list."""
    import importlib
    import yaml
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sandbox_policy.yaml").write_text(
        yaml.safe_dump({"blocked_imports": ["requests"], "allow_imports": ["socket"]}),
        encoding="utf-8")
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    importlib.reload(sandbox)
    assert sandbox.scan_source("import requests\n")       # newly blocked via YAML
    assert sandbox.scan_source("import socket\n") == []    # relaxed via allow_imports
    assert sandbox.scan_source("import subprocess\n")      # built-in still blocked


def test_sandbox_mode_from_config_yaml(tmp_path, monkeypatch):
    """GUI-settable: `mode:` in sandbox_policy.yaml drives enforcement when no env var."""
    import importlib
    import yaml
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "sandbox_policy.yaml").write_text(yaml.safe_dump({"mode": "enforce"}), encoding="utf-8")
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("CIM_PLUGIN_SANDBOX", raising=False)
    importlib.reload(sandbox)
    assert sandbox.mode() == "enforce"
    with pytest.raises(sandbox.SandboxViolation):
        sandbox.check_source("import subprocess\n", "x.py")
    # env var still wins over the config file
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "off")
    assert sandbox.mode() == "off"


def test_plugin_loader_enforces_sandbox(tmp_path, monkeypatch):
    """plugin_loader refuses to load a module with violations when enforce."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from plugin_loader import _load_from_file
    from core.sandbox import SandboxViolation

    evil = tmp_path / "evil.py"
    evil.write_text("import subprocess\nX = 1\n", encoding="utf-8")
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "enforce")
    with pytest.raises(SandboxViolation):
        _load_from_file(evil, "_evil_test")

    # warn mode → loads fine
    monkeypatch.setenv("CIM_PLUGIN_SANDBOX", "warn")
    mod = _load_from_file(evil, "_evil_test2")
    assert mod.X == 1


# ─── pluggable identity ───────────────────────────────────────────────────────

def test_identity_file_overrides_role(tmp_path, monkeypatch):
    from auth_provider import AuthProvider
    idf = tmp_path / "identity.json"
    idf.write_text(json.dumps({"role": "operator"}), encoding="utf-8")
    monkeypatch.setenv("CIM_IDENTITY_FILE", str(idf))
    monkeypatch.setenv("CIM_USER_ROLE", "viewer")  # should be overridden by file
    assert AuthProvider(db_path=None).get_current_role() == "operator"


def test_identity_falls_back_to_env_then_admin(tmp_path, monkeypatch):
    from auth_provider import AuthProvider
    monkeypatch.delenv("CIM_IDENTITY_FILE", raising=False)
    monkeypatch.setenv("CIM_USER_ROLE", "viewer")
    assert AuthProvider(db_path=None).get_current_role() == "viewer"
    monkeypatch.delenv("CIM_USER_ROLE", raising=False)
    assert AuthProvider(db_path=None).get_current_role() == "admin"
