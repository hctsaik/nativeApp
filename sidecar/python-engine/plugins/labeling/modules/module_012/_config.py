from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

# Delegate shared boilerplate (project root / log dir / atomic write / config /
# shared / manifest helpers) to the single source of truth, like every other
# module's _config.py. Module-012-specific helpers (classifications, classes.txt,
# enhanced dir, xany work dir) stay here. Paths are byte-for-byte identical
# because _base.log_dir() resolves to the same CIM_LOG_DIR.
_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parents[3] / "scripts" / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()         # nativeApp
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write
_manifest_key = _base.manifest_key

_MODULE_ID = "012"

_DEFAULTS: dict = {
    "annotation_tool": "x-anylabeling",
    "annotation_labels": [],
    "classification_labels": [],
    "autorefresh_enabled": True,
    "autorefresh_seconds": 10,
    "last_manifest_id": "",
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def _shared_path() -> Path:
    return _base.shared_path()


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(config: dict) -> None:
    _base.save_config(_MODULE_ID, config)


def get_shared_manifest_id() -> str:
    """回傳 Data Feeder 最後建立的 manifest_id（從 shared.json 讀取）。"""
    return _base.shared_manifest_id()


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


# ── module-012-specific helpers ───────────────────────────────────────────────


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
    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))


def get_classes_path(manifest_id: str) -> Path:
    """X-AnyLabeling labels file path, stored under log config."""
    return _CIM_LOG_DIR / "config" / f"module_012_classes_{_manifest_key(manifest_id)}.txt"


def get_xany_work_dir(manifest_id: str) -> Path:
    """X-AnyLabeling GUI state directory, stored under logs."""
    path = _CIM_LOG_DIR / "xanylabeling_state" / f"module_012_{_manifest_key(manifest_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_enhanced_dir(manifest_id: str) -> Path:
    """強化圖批次標注的工作資料夾（每個 manifest 獨立、與原圖完全隔離）。"""
    path = _CIM_LOG_DIR / "m012_enhanced" / _manifest_key(manifest_id)
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
    _atomic_write(p, json.dumps(data, ensure_ascii=False, indent=2))
