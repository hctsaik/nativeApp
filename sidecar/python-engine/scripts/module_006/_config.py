from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_spec = _ilu.spec_from_file_location("_config_base", _HERE.parent / "shared" / "_config_base.py")
_base = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_base)

_MODULE_ID = "006"
_PROJECT_ROOT = _base.project_root()
_DEFAULT_CONFIG: dict = {
    "annotation_labels": ["眼睛", "鼻子", "嘴巴"],
}


def _config_path() -> Path:
    return _base.config_path(_MODULE_ID)


def load_config() -> dict:
    return _base.load_config(_MODULE_ID, _DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    _base.save_config(_MODULE_ID, config)


def get_annotation_labels() -> list[str]:
    return load_config().get("annotation_labels", _DEFAULT_CONFIG["annotation_labels"])


def set_annotation_labels(labels: list[str]) -> None:
    cfg = load_config()
    cfg["annotation_labels"] = labels
    save_config(cfg)
