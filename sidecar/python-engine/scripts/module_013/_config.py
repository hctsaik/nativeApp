from __future__ import annotations
import json, os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR  = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS = {
    "copy_annotations": True,   # B
    "organize_images":  True,   # C
}

def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_013.json"

def load_config() -> dict:
    p = _config_path()
    if not p.exists(): return _DEFAULTS.copy()
    try: return {**_DEFAULTS, **json.loads(p.read_text(encoding="utf-8"))}
    except: return _DEFAULTS.copy()

def save_config(cfg: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def get_manifest_db_path() -> Path:
    d = _CIM_LOG_DIR / "db"; d.mkdir(parents=True, exist_ok=True)
    return d / "manifest.sqlite"

def get_workspace_dir_for_manifest(manifest_id: str) -> Path:
    """與 module_012 相同的 workspace 路徑，用來讀取標注和分類結果。"""
    return _CIM_LOG_DIR / "annotation_workspaces" / f"module_012_{manifest_id[:12]}"

def get_shared_manifest_id() -> str:
    """回傳 Data Feeder 最後建立的 manifest_id（從 shared.json 讀取）。"""
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
    except Exception:
        return ""
