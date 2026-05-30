"""Declarative role-based access control (no-code RBAC).

Permissions are declared in a YAML policy (default: `{CIM_LOG_DIR}/config/
permissions.yaml`, falling back to repo `config/permissions.yaml`) instead of
being hard-coded or requiring a GUI. Edit the YAML to grant/revoke — no Python,
no rebuild.

Policy schema:

    default_policy: allow            # allow | deny  (for roles with no rule)
    roles:
      admin:    { all: true }                       # full access
      operator:
        view:    ["*"]                               # all modules
        execute: [module_012, module_026]            # only these
      viewer:
        view:    ["*"]

Semantics (is_allowed, pure + unit-tested):
  * role with `all: true`            → allow everything
  * action list contains plugin_id   → allow
  * action list contains "*"         → allow
  * role present but action not listed → DENY (explicit role = scoped)
  * role absent from policy           → default_policy (allow/deny)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def policy_paths() -> list[Path]:
    """Candidate policy locations, highest priority first."""
    out: list[Path] = []
    log_dir = os.environ.get("CIM_LOG_DIR")
    if log_dir:
        out.append(Path(log_dir) / "config" / "permissions.yaml")
    # repo default: sidecar/python-engine/config/permissions.yaml
    out.append(Path(__file__).resolve().parents[1] / "config" / "permissions.yaml")
    return out


def load_policy(path: Path | None = None) -> dict | None:
    """Load the RBAC policy dict, or None if no policy file exists."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return None
    candidates = [path] if path is not None else policy_paths()
    for p in candidates:
        if p and p.exists():
            try:
                return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                return None
    return None


def is_allowed(policy: dict | None, role: str, plugin_id: str, action: str) -> bool:
    """Pure policy evaluation. With no policy → allow (open by default)."""
    if not policy:
        return True
    roles: dict[str, Any] = policy.get("roles", {}) or {}
    rule = roles.get(role)
    if rule is None:
        return str(policy.get("default_policy", "allow")).lower() != "deny"
    if isinstance(rule, dict):
        if rule.get("all") is True:
            return True
        allowed = rule.get(action)
        if isinstance(allowed, list):
            return plugin_id in allowed or "*" in allowed
        if allowed is True:
            return True
    return False  # role explicitly present but action not granted → deny
