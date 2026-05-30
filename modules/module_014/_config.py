from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parents[3] / "scripts" / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()  # nativeApp
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "014"
_DEFAULTS: dict = {
    "default_export_formats": ["coco_json"],
    "split_train": 70,
    "split_val": 15,
    "split_test": 15,
    "stratified_split": True,
    "default_export_dir": "",
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(config: dict) -> None:
    _base.save_config(_MODULE_ID, config)


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def read_shared() -> dict:
    return _base.load_shared()


def get_shared_manifest_id() -> str:
    return read_shared().get("last_manifest_id", "")


def _manifest_key(manifest_id: str) -> str:
    return _base.manifest_key(manifest_id)


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
