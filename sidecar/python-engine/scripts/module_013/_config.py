from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write

_MODULE_ID = "013"
_DEFAULTS: dict = {
    "service_url": "",
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def _manifest_key(manifest_id: str) -> str:
    return _base.manifest_key(manifest_id)


def load_classifications(manifest_id: str) -> dict[str, str]:
    p = _CIM_LOG_DIR / "config" / f"module_012_classifications_{_manifest_key(manifest_id)}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_sync_state_path(manifest_id: str) -> Path:
    return _CIM_LOG_DIR / "config" / f"m013_sync_state_{_manifest_key(manifest_id)}.json"


def get_sync_history_path(manifest_id: str) -> Path:
    return _CIM_LOG_DIR / "config" / f"m013_sync_history_{_manifest_key(manifest_id)}.jsonl"


def load_sync_state(manifest_id: str) -> dict:
    p = get_sync_state_path(manifest_id)
    if not p.exists():
        return {"manifest_id": manifest_id, "items": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"manifest_id": manifest_id, "items": {}}


def save_sync_state(manifest_id: str, state: dict) -> None:
    p = get_sync_state_path(manifest_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(p, json.dumps(state, ensure_ascii=False, indent=2))


def append_sync_history(manifest_id: str, entry: dict) -> None:
    p = get_sync_history_path(manifest_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_sync_history(manifest_id: str, limit: int = 10) -> list[dict]:
    p = get_sync_history_path(manifest_id)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").strip().splitlines()
    entries: list[dict] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return entries[-limit:]


def get_shared_manifest_id() -> str:
    return _base.shared_manifest_id()


def get_shared_dataset_id() -> str:
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("dataset_id", "")
    except Exception:
        return ""
