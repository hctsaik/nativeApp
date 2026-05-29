from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_MODULE_ID = "011"
_PROJECT_ROOT = _base.project_root()  # nativeApp

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
    """載入設定，若不存在則回傳預設值。"""
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(config: dict) -> None:
    """儲存設定至 JSON 檔。"""
    _base.save_config(_MODULE_ID, config)


def get_manifest_db_path() -> Path:
    """回傳 manifest SQLite 資料庫路徑。"""
    return _base.manifest_db_path()
