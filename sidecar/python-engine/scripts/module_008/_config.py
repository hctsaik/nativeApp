from __future__ import annotations

import json
import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_CONFIG: dict = {
    "annotation_labels": ["眼睛", "鼻子", "嘴巴"],
}


def _config_path() -> Path:
    log_dir = Path(os.environ.get("CIM_LOG_DIR", _PROJECT_ROOT / "tmp" / "cim_log"))
    return log_dir / "config" / "module_008.json"


def load_config() -> dict:
    p = _config_path()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            return {**_DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return dict(_DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    p = _config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def get_annotation_labels() -> list[str]:
    return load_config().get("annotation_labels", _DEFAULT_CONFIG["annotation_labels"])


def set_annotation_labels(labels: list[str]) -> None:
    cfg = load_config()
    cfg["annotation_labels"] = labels
    save_config(cfg)
