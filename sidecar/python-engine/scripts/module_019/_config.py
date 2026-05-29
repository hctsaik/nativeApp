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

_MODULE_ID = "019"
_DEFAULTS: dict = {
    "service_url": "",
    "last_dataset_id": "",
    "last_dataset_name": "",
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)


def get_downloads_dir() -> Path:
    p = _CIM_LOG_DIR / "downloads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_progress_path() -> Path:
    p = _CIM_LOG_DIR / "progress"
    p.mkdir(parents=True, exist_ok=True)
    return p / "m019_progress.json"


def write_progress(done: int, total: int, current: str,
                   phase: str, running: bool,
                   error: str = "") -> None:
    try:
        data = {
            "done": done, "total": total, "current": current,
            "phase": phase, "running": running, "error": error,
        }
        _atomic_write(get_progress_path(), json.dumps(data))
    except Exception:
        pass


def read_progress() -> dict | None:
    p = get_progress_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _shared_json_path() -> Path:
    return _CIM_LOG_DIR / "config" / "shared.json"


def read_shared() -> dict:
    p = _shared_json_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_shared_fields(fields: dict) -> None:
    """原子更新 shared.json 的指定欄位，不覆蓋其他欄位。"""
    p = _shared_json_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        existing = {}
    existing.update(fields)
    _atomic_write(p, json.dumps(existing, ensure_ascii=False, indent=2))
