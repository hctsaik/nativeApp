from __future__ import annotations

import importlib
import sys


def _reload_config(monkeypatch, **env_vars):
    for k, v in env_vars.items():
        monkeypatch.setenv(k, v)
    # Force reimport so env vars are re-read
    if "cim_gui_mcp.config" in sys.modules:
        del sys.modules["cim_gui_mcp.config"]
    return importlib.import_module("cim_gui_mcp.config")


def test_default_sidecar_port(monkeypatch):
    monkeypatch.delenv("CIM_SIDECAR_PORT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.SIDECAR_PORT == 8765


def test_custom_sidecar_port(monkeypatch):
    cfg = _reload_config(monkeypatch, CIM_SIDECAR_PORT="9999")
    assert cfg.SIDECAR_PORT == 9999


def test_sidecar_base_url(monkeypatch):
    cfg = _reload_config(monkeypatch, CIM_SIDECAR_PORT="1234")
    assert cfg.SIDECAR_BASE == "http://127.0.0.1:1234"


def test_default_headless(monkeypatch):
    monkeypatch.delenv("CIM_MCP_HEADLESS", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.BROWSER_HEADLESS is True


def test_headless_off(monkeypatch):
    cfg = _reload_config(monkeypatch, CIM_MCP_HEADLESS="0")
    assert cfg.BROWSER_HEADLESS is False


def test_default_timeout(monkeypatch):
    monkeypatch.delenv("CIM_MCP_TIMEOUT", raising=False)
    cfg = _reload_config(monkeypatch)
    assert cfg.DEFAULT_TIMEOUT == 10000


def test_custom_timeout(monkeypatch):
    cfg = _reload_config(monkeypatch, CIM_MCP_TIMEOUT="30000")
    assert cfg.DEFAULT_TIMEOUT == 30000
