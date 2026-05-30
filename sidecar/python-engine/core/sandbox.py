"""Lightweight load-time plugin sandbox (AST deny-list).

Scans module source for obviously-dangerous constructs (process/network/shell,
dynamic code execution) so a third-party module can't silently run them. Used by
plugin_loader BEFORE exec. Enforcement is configurable via CIM_PLUGIN_SANDBOX:

    CIM_PLUGIN_SANDBOX=enforce   → refuse to load a module with violations
    CIM_PLUGIN_SANDBOX=warn      → log violations but load (default)
    CIM_PLUGIN_SANDBOX=off       → skip the scan

This is a guard rail, not a full security sandbox (real isolation needs process/
container boundaries) — but it turns the previously upload-only check into a
load-time check so a hand-placed/imported module is screened too.
"""

from __future__ import annotations

import ast
import os

BLOCKED_IMPORTS = {"subprocess", "socket", "ctypes", "multiprocessing"}
BLOCKED_CALLS = {"eval", "exec", "compile", "__import__", "os.system", "os.popen"}


def _policy_overrides() -> tuple[set, set]:
    """No-code extension: read extra/allowed rules from config/sandbox_policy.yaml.

        blocked_imports: [requests]      # add to the deny-list
        blocked_calls:   [open]
        allow_imports:   [socket]        # remove from the deny-list (trusted)
        allow_calls:     [compile]
    """
    blocked_i, blocked_c = set(BLOCKED_IMPORTS), set(BLOCKED_CALLS)
    try:
        import yaml  # noqa: PLC0415
        for p in (_cfg_dir() / "sandbox_policy.yaml",):
            if p.exists():
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                blocked_i |= set(data.get("blocked_imports") or [])
                blocked_c |= set(data.get("blocked_calls") or [])
                blocked_i -= set(data.get("allow_imports") or [])
                blocked_c -= set(data.get("allow_calls") or [])
    except Exception:
        pass
    return blocked_i, blocked_c


def _cfg_dir():
    from pathlib import Path  # noqa: PLC0415
    log_dir = os.environ.get("CIM_LOG_DIR")
    if log_dir and (Path(log_dir) / "config" / "sandbox_policy.yaml").exists():
        return Path(log_dir) / "config"
    return Path(__file__).resolve().parents[1] / "config"


def scan_source(source: str, filename: str = "<module>") -> list[str]:
    """Return a list of human-readable violations (empty = clean). Pure (reads the
    optional declarative sandbox_policy.yaml for no-code rule overrides)."""
    blocked_imports, blocked_calls = _policy_overrides()
    violations: list[str] = []
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as exc:
        return [f"{filename}: 語法錯誤無法解析：{exc}"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in blocked_imports:
                    violations.append(f"{filename}:{node.lineno}: 禁用模組 import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in blocked_imports:
                violations.append(f"{filename}:{node.lineno}: 禁用模組 from {node.module} import …")
        elif isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in blocked_calls:
                violations.append(f"{filename}:{node.lineno}: 禁用呼叫 {name}(…)")
    return violations


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return ""


def mode() -> str:
    """Enforcement mode: CIM_PLUGIN_SANDBOX env wins; else `mode:` in
    config/sandbox_policy.yaml (GUI-settable from the Management Center); else 'warn'."""
    env = os.environ.get("CIM_PLUGIN_SANDBOX")
    if env:
        return env.strip().lower()
    try:
        import yaml  # noqa: PLC0415
        p = _cfg_dir() / "sandbox_policy.yaml"
        if p.exists():
            m = (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("mode")
            if m:
                return str(m).strip().lower()
    except Exception:
        pass
    return "warn"


class SandboxViolation(RuntimeError):
    """Raised when CIM_PLUGIN_SANDBOX=enforce and a module has violations."""


def check_source(source: str, filename: str = "<module>", *, logger=None) -> list[str]:
    """Scan + apply the configured policy. Returns violations (after logging);
    raises SandboxViolation when mode == enforce and violations exist."""
    m = mode()
    if m == "off":
        return []
    violations = scan_source(source, filename)
    if violations:
        msg = f"plugin sandbox: {filename} 有 {len(violations)} 個違規：\n  " + "\n  ".join(violations)
        if logger is not None:
            logger.warning(msg)
        if m == "enforce":
            raise SandboxViolation(msg)
    return violations
