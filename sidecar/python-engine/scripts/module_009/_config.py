from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]

_DEFAULT_CONFIG: dict = {
    "annotation_labels": ["眼睛", "鼻子", "嘴巴"],
    "default_before_sec": 1.0,
    "default_after_sec": 1.0,
    "auto_advance": True,
    "backup_after_sync": True,
}


def _config_path() -> Path:
    log_dir = Path(os.environ.get("CIM_LOG_DIR", _PROJECT_ROOT / "tmp" / "cim_log"))
    return log_dir / "config" / "module_009.json"


def load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return _DEFAULT_CONFIG.copy()
    try:
        return {**_DEFAULT_CONFIG, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULT_CONFIG.copy()


def save_config(config: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def get_annotation_labels() -> list[str]:
    return load_config().get("annotation_labels", _DEFAULT_CONFIG["annotation_labels"])


def set_annotation_labels(labels: list[str]) -> None:
    cfg = load_config()
    cfg["annotation_labels"] = labels
    save_config(cfg)


def get_db_path() -> Path:
    log_dir = Path(os.environ.get("CIM_LOG_DIR", _PROJECT_ROOT / "tmp" / "cim_log"))
    db_dir = log_dir / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "annotation.sqlite"
