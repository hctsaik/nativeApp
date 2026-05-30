"""Declarative external-system (tenant) registration (no-code).

Declare external task systems (iWISC, SMM, …) in a YAML file instead of
calling register_tenant from code or a GUI. The data-source module syncs the
declared systems into the workspace on load, so editing the YAML makes them
appear in the 「外部系統」 picker — no code, no rebuild.

Policy location (highest priority first): {CIM_LOG_DIR}/config/external_systems.yaml
then repo sidecar/python-engine/config/external_systems.yaml.

Schema:
    systems:
      - system_name: iWISC
        server_host_name: http://localhost:8765
        target_format: xanylabeling
        api_token_env: IWSC_TOKEN      # token read from this env var (never in YAML)
"""

from __future__ import annotations

import os
from pathlib import Path


def config_paths() -> list[Path]:
    out: list[Path] = []
    log_dir = os.environ.get("CIM_LOG_DIR")
    if log_dir:
        out.append(Path(log_dir) / "config" / "external_systems.yaml")
    out.append(Path(__file__).resolve().parents[1] / "config" / "external_systems.yaml")
    return out


def load_declared_systems(path: Path | None = None) -> list[dict]:
    """Return the declared external systems list (or [] if none)."""
    try:
        import yaml  # noqa: PLC0415
    except ImportError:
        return []
    for p in ([path] if path is not None else config_paths()):
        if p and p.exists():
            try:
                data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
                systems = data.get("systems", [])
                return systems if isinstance(systems, list) else []
            except Exception:
                return []
    return []
