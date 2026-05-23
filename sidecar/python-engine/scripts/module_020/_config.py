from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

PAGE_SIZE = 20
_NT_ACCOUNT = "HCTSAIK"
_SYSTEM_OPTIONS = ["iWISC", "SMM"]
_DATA_TYPE_OPTIONS = ["Simulation", "Issue", "Retrain"]


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_020.json"


_DEFAULTS: dict = {"service_url": ""}


def load_config() -> dict:
    p = _config_path()
    if not p.exists():
        return _DEFAULTS.copy()
    try:
        return {**_DEFAULTS, **json.loads(p.read_text(encoding="utf-8"))}
    except Exception:
        return _DEFAULTS.copy()


def save_config(cfg: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(cfg, ensure_ascii=False, indent=2))


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
