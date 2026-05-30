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


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def _manifest_key(manifest_id: str) -> str:
    return _base.manifest_key(manifest_id)


def get_shared_manifest_id() -> str:
    return _base.shared_manifest_id()


def load_classifications(manifest_id: str) -> dict[str, str]:
    p = _CIM_LOG_DIR / "config" / f"module_012_classifications_{_manifest_key(manifest_id)}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
