from __future__ import annotations

import importlib.util as _ilu
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ENGINE_ROOT = _HERE.parents[2]

if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parent / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)

_cfg_spec = _ilu.spec_from_file_location("_017_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

from cim_annotation.label_ops import (
    scan_labels,
    find_near_duplicates,
    rename_label,
    merge_labels,
    delete_label,
)


def execute_logic(params: dict) -> dict:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return {"error": "No manifest selected", "label_map": {}, "near_dupes": []}

    db_path = _cfg.get_manifest_db_path()
    items = _mdb.get_manifest_items(db_path, manifest_id)

    label_map = scan_labels(items)
    labels = sorted(label_map.keys())
    near_dupes = find_near_duplicates(labels)

    return {
        "manifest_id": manifest_id,
        "label_map": label_map,
        "near_dupes": near_dupes,
        "items": items,
    }


def do_rename(params: dict, old: str, new: str) -> int:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return 0
    db_path = _cfg.get_manifest_db_path()
    items = _mdb.get_manifest_items(db_path, manifest_id)
    return rename_label(items, old, new)


def do_merge(params: dict, sources: list[str], target: str) -> int:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return 0
    db_path = _cfg.get_manifest_db_path()
    items = _mdb.get_manifest_items(db_path, manifest_id)
    return merge_labels(items, sources, target)


def do_delete(params: dict, label: str) -> int:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return 0
    db_path = _cfg.get_manifest_db_path()
    items = _mdb.get_manifest_items(db_path, manifest_id)
    return delete_label(items, label)
