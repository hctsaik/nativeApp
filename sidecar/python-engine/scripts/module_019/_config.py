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
    "service_url": "",
    "last_dataset_id": "",
    "last_dataset_name": "",
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_019.json"


def load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return _DEFAULTS.copy()
    try:
        return {**_DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(path, json.dumps(cfg, ensure_ascii=False, indent=2))


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
