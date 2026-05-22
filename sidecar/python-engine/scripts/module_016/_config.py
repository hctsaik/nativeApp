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
    "model_type": "yolo",        # "yolo" | "classifier"
    "model_path": "",
    "conf_threshold": 0.25,
    "overwrite_existing": False,
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_016.json"


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


def get_manifest_db_path() -> Path:
    db_dir = _CIM_LOG_DIR / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


def get_shared_manifest_id() -> str:
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
    except Exception:
        return ""
