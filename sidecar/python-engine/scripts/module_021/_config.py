from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_MODULE_ID = "021"
_DEFAULTS: dict = {"url": ""}

# back-compat module-level names
_PROJECT_ROOT = _base.project_root()
_CIM_LOG_DIR = _base.log_dir()
_atomic_write = _base.atomic_write


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULTS)


def save_config(cfg: dict) -> None:
    _base.save_config(_MODULE_ID, cfg)
