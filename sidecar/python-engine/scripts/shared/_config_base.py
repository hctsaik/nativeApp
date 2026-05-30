"""Shared config / paths helper for scripts/module_*/_config.py.

Historically every module _config.py duplicated the same boilerplate:
project-root resolution, CIM_LOG_DIR, atomic JSON write, load/save config,
manifest db path, shared-manifest-id lookup, manifest key. This module is the
single source of truth for that boilerplate; each _config.py loads it (via the
established spec_from_file_location pattern) and delegates, keeping only its own
``_DEFAULTS`` and module-specific helpers.

Behavior is intentionally byte-for-byte compatible with the previous inline
implementations (see tests/test_config_base.py).
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def project_root() -> Path:
    """Repo root (nativeApp). Matches the legacy ``parents[4]`` from a module's
    scripts/module_NNN/_config.py — this file at scripts/shared/_config_base.py
    is the same number of levels deep."""
    return Path(__file__).resolve().parents[4]


def log_dir() -> Path:
    """CIM_LOG_DIR (engine-injected) or the dev default under the repo."""
    return Path(os.environ.get("CIM_LOG_DIR", str(project_root() / "tmp" / "cim_log")))


def atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def config_dir() -> Path:
    return log_dir() / "config"


def config_path(module_id: str) -> Path:
    """CIM_LOG_DIR/config/module_<id>.json"""
    return config_dir() / f"module_{module_id}.json"


def load_config(module_id: str, defaults: dict) -> dict:
    path = config_path(module_id)
    if not path.exists():
        return {**defaults}
    try:
        return {**defaults, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return {**defaults}


def save_config(module_id: str, config: dict) -> None:
    path = config_path(module_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(config, ensure_ascii=False, indent=2))


def manifest_db_path() -> Path:
    db_dir = log_dir() / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


def manifest_key(manifest_id: str) -> str:
    return manifest_id[:12] or "default"


def shared_path() -> Path:
    return config_dir() / "shared.json"


def shared_manifest_id() -> str:
    """Last manifest_id written by the data-source module (shared.json)."""
    p = shared_path()
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
    except Exception:
        return ""


def load_shared() -> dict:
    p = shared_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
