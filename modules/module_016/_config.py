from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parents[3] / "scripts" / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "016"
_DEFAULTS: dict = {
    "model_type": "yolo",        # "yolo" | "classifier"
    "model_path": "",
    "conf_threshold": 0.25,
    "overwrite_existing": False,
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def get_shared_manifest_id() -> str:
    return _base.shared_manifest_id()


def get_progress_path() -> Path:
    p = _CIM_LOG_DIR / "progress"
    p.mkdir(parents=True, exist_ok=True)
    return p / "m016_progress.json"


def write_progress(done: int, total: int, current: str,
                   ok: int, skipped: int, errors: int,
                   started_at: str, running: bool) -> None:
    try:
        data = {
            "done": done, "total": total, "current": current,
            "ok": ok, "skipped": skipped, "errors": errors,
            "started_at": started_at, "running": running,
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
