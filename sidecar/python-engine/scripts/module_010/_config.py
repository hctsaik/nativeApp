from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()  # nativeApp
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "010"
_DEFAULTS: dict = {
    "last_source_type": "folder",
    "last_folder_path": "",
    "recursive_scan": True,
    "image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"],
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(config: dict) -> None:
    _base.save_config(_MODULE_ID, config)


def get_manifest_db_path() -> Path:
    """回傳 manifest SQLite 資料庫路徑。"""
    return _base.manifest_db_path()


def write_shared_manifest_id(manifest_id: str) -> None:
    """將最新建立的 manifest_id 寫入 shared.json，供 module_012 自動銜接。"""
    p = _CIM_LOG_DIR / "config" / "shared.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        existing = {}
    existing["last_manifest_id"] = manifest_id
    # 010 執行完成，清除 module_019 留下的旗標
    existing.pop("suggested_folder_path", None)
    existing["pending_reload"] = False
    _atomic_write(p, json.dumps(existing, ensure_ascii=False, indent=2))


def read_shared_suggested_folder() -> str:
    """讀取 module_019 建議的資料夾路徑（若存在）。"""
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("suggested_folder_path", "")
    except Exception:
        return ""
