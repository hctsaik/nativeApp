from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "026"
_DEFAULTS: dict = {
    "last_mode": "local",
    "last_folder_path": "",
    "recursive_scan": True,
    "image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"],
    "service_url": "",
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def _shared_path() -> Path:
    return _base.shared_path()


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def read_shared() -> dict:
    return _base.load_shared()


def write_shared(updates: dict) -> None:
    """Merge updates into shared.json atomically."""
    p = _shared_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        existing = {}
    existing.update(updates)
    _atomic_write(p, json.dumps(existing, ensure_ascii=False, indent=2))


def get_annotation_workspace_path() -> Path:
    return _CIM_LOG_DIR / "annotation_workspace"
