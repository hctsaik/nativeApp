from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS: dict = {
    "annotation_tool": "x-anylabeling",
    "annotation_labels": [],
    "classification_labels": [],
    "autorefresh_enabled": True,
    "autorefresh_seconds": 10,
    "last_manifest_id": "",
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_012.json"


def _shared_path() -> Path:
    return _CIM_LOG_DIR / "config" / "shared.json"


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
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def get_shared_manifest_id() -> str:
    """回傳 Data Feeder 最後建立的 manifest_id（從 shared.json 讀取）。"""
    p = _shared_path()
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
    except Exception:
        return ""


def get_manifest_db_path() -> Path:
    db_dir = _CIM_LOG_DIR / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "manifest.sqlite"


def _manifest_key(manifest_id: str) -> str:
    return manifest_id[:12] or "default"


def get_classification_path(manifest_id: str) -> Path:
    """分類結果儲存檔（每個 manifest 獨立一份，存於 log config）。"""
    return _CIM_LOG_DIR / "config" / f"module_012_classifications_{_manifest_key(manifest_id)}.json"


def load_classifications(manifest_id: str) -> dict[str, str]:
    """載入分類結果 dict：{item_id → label}。"""
    p = get_classification_path(manifest_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_classifications(manifest_id: str, data: dict[str, str]) -> None:
    """儲存分類結果。"""
    p = get_classification_path(manifest_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_classes_path(manifest_id: str) -> Path:
    """X-AnyLabeling labels file path, stored under log config."""
    return _CIM_LOG_DIR / "config" / f"module_012_classes_{_manifest_key(manifest_id)}.txt"


def get_xany_work_dir(manifest_id: str) -> Path:
    """X-AnyLabeling GUI state directory, stored under logs."""
    path = _CIM_LOG_DIR / "xanylabeling_state" / f"module_012_{_manifest_key(manifest_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_filepath_classifications_path() -> Path:
    """分類結果的 file_path 索引（跨 manifest 存活，key 為 file_path）。"""
    return _CIM_LOG_DIR / "config" / "module_012_classifications_by_path.json"


def load_classifications_by_path() -> dict[str, str]:
    """載入以 file_path 為 key 的分類 dict：{file_path → label}。"""
    p = get_filepath_classifications_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_classifications_by_path(data: dict[str, str]) -> None:
    """儲存以 file_path 為 key 的分類 dict。"""
    p = get_filepath_classifications_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
