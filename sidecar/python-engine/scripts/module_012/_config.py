from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]  # nativeApp
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS: dict = {
    "annotation_labels": ["物件A", "物件B", "物件C"],
    "classification_labels": [],
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
    """
    決定 module_012 input 預選的 manifest_id。
    優先用 module_012 自己上次 session 用的 manifest（module_012.json），
    確保 Update 後回到 module_012 仍選同一個 manifest，標注不會消失。
    Fallback 才用 Data Feeder 最後建的（shared.json）。
    """
    # 1. 優先：module_012 自己上次用的
    own = load_config().get("last_manifest_id", "")
    if own:
        return own
    # 2. Fallback：Data Feeder 最後建的
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


def get_workspace_dir(manifest_id: str) -> Path:
    ws = _CIM_LOG_DIR / "annotation_workspaces" / f"module_012_{manifest_id[:12]}"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def get_classification_path(workspace_dir: str) -> Path:
    """分類結果儲存檔（每個 manifest 的 workspace 獨立一份）。"""
    return Path(workspace_dir) / "classifications.json"


def load_classifications(workspace_dir: str) -> dict[str, str]:
    """載入分類結果 dict：{item_id → label}。"""
    p = get_classification_path(workspace_dir)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_classifications(workspace_dir: str, data: dict[str, str]) -> None:
    """儲存分類結果。"""
    p = get_classification_path(workspace_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
