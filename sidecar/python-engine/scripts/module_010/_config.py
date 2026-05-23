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
    "last_source_type": "folder",
    "last_folder_path": "",
    "recursive_scan": True,
    "image_extensions": [".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"],
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_010.json"


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
    """回傳 manifest SQLite 資料庫路徑。"""
    db_dir = _CIM_LOG_DIR / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


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
