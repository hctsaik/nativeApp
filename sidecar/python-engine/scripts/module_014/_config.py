from __future__ import annotations

import json
import os
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS: dict = {
    "default_export_formats": ["coco_json"],
    "split_train": 70,
    "split_val": 15,
    "split_test": 15,
    "stratified_split": True,
    "default_export_dir": "",
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_014.json"


def load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return _DEFAULTS.copy()
    try:
        return {**_DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULTS.copy()


def save_config(config: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(config, ensure_ascii=False, indent=2))


def get_manifest_db_path() -> Path:
    db_dir = _CIM_LOG_DIR / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


def read_shared() -> dict:
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_shared_manifest_id() -> str:
    return read_shared().get("last_manifest_id", "")


def _manifest_key(manifest_id: str) -> str:
    return manifest_id[:12] or "default"


def get_classification_path(manifest_id: str) -> Path:
    return _CIM_LOG_DIR / "config" / f"module_012_classifications_{_manifest_key(manifest_id)}.json"


def load_classifications(manifest_id: str) -> dict[str, str]:
    p = get_classification_path(manifest_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_default_export_dir(manifest_id: str) -> Path:
    path = _CIM_LOG_DIR / "exports" / f"module_014_{_manifest_key(manifest_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path
