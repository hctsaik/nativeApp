from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp

_DEFAULTS: dict = {
    "default_export_formats": ["coco_json"],
    "split_train": 70,
    "split_val": 15,
    "split_test": 15,
    "stratified_split": True,
    "default_export_dir": "",
}


def _config_path() -> Path:
    log_dir = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))
    return log_dir / "config" / "module_011.json"


def load_config() -> dict:
    """載入設定，若不存在則回傳預設值。"""
    path = _config_path()
    if not path.exists():
        return _DEFAULTS.copy()
    try:
        return {**_DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULTS.copy()


def save_config(config: dict) -> None:
    """儲存設定至 JSON 檔。"""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def get_manifest_db_path() -> Path:
    """回傳 manifest SQLite 資料庫路徑。"""
    _CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))
    return _CIM_LOG_DIR / "db" / "manifest.sqlite"
