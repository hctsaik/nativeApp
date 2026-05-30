from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parents[3] / "scripts" / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "020"
PAGE_SIZE = 20
_NT_ACCOUNT = "HCTSAIK"
_SYSTEM_OPTIONS = ["iWISC", "SMM"]
_DATA_TYPE_OPTIONS = ["Simulation", "Issue", "Retrain"]

_DEFAULTS: dict = {"service_url": ""}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)


def get_archive_dir(submit_id: str) -> Path:
    d = _CIM_LOG_DIR / "downloads" / "archive" / submit_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_service_url_from_013() -> str:
    """Reuse the service URL saved by module_013 if available."""
    p = _CIM_LOG_DIR / "config" / "module_013.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("service_url", "")
    except Exception:
        return ""


def write_shared_suggested_folder(folder_path: str) -> None:
    """Write download path to shared.json so Data Feeder can pick it up."""
    p = _CIM_LOG_DIR / "config" / "shared.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        existing = {}
    existing["suggested_folder_path"] = folder_path
    existing["pending_reload"] = True
    _atomic_write(p, json.dumps(existing, ensure_ascii=False, indent=2))
