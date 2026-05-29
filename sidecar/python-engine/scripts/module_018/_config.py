from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()


def get_manifest_db_path() -> Path:
    return _base.manifest_db_path()


def get_shared_manifest_id() -> str:
    return _base.shared_manifest_id()
