from __future__ import annotations

import json
import os
from pathlib import Path


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_CIM_LOG_DIR = Path(os.environ.get("CIM_LOG_DIR", str(_PROJECT_ROOT / "tmp" / "cim_log")))

_DEFAULTS: dict = {
    "service_url": "",
}


def _config_path() -> Path:
    return _CIM_LOG_DIR / "config" / "module_013.json"


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


def get_manifest_db_path() -> Path:
    d = _CIM_LOG_DIR / "db"
    d.mkdir(parents=True, exist_ok=True)
    return d / "manifest.sqlite"


def _manifest_key(manifest_id: str) -> str:
    return manifest_id[:12] or "default"


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
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_manifest_id", "")
    except Exception:
        return ""


def get_shared_dataset_id() -> str:
    p = _CIM_LOG_DIR / "config" / "shared.json"
    if not p.exists():
        return ""
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("dataset_id", "")
    except Exception:
        return ""
