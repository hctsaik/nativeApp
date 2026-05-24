from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_021_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


def execute_logic(params: dict) -> dict:
    url = (params.get("url") or "").strip()
    if not url:
        return {"success": False, "error": "URL 不可為空"}
    if not url.startswith("https://"):
        return {"success": False, "error": "URL 必須以 https:// 開頭"}
    cfg = _cfg.load_config()
    cfg["url"] = url
    _cfg.save_config(cfg)
    return {"success": True, "url": url}
