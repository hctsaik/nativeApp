from __future__ import annotations

import json
import os
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS: dict = {
    "last_mode": "local",
    "last_folder_path": "",
    "recursive_scan": True,
    "image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"],
    "service_url": "",
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_026.json"


def _shared_path() -> Path:
    return _CIM_LOG_DIR / "config" / "shared.json"


def load_config() -> dict:
    p = _config_path()
    if not p.exists():
        return _DEFAULTS.copy()
    try:
        return {**_DEFAULTS, **json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(cfg, ensure_ascii=False, indent=2))


def get_manifest_db_path() -> Path:
    db_dir = _CIM_LOG_DIR / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


def read_shared() -> dict:
    p = _shared_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


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
    return Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log"))) / "annotation_workspace"
