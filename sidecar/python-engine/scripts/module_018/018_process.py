from __future__ import annotations

import importlib.util as _ilu
import json
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

_cfg_spec = _ilu.spec_from_file_location("_018_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)


def _read_annotation(file_path: str) -> dict | None:
    ann = Path(file_path).with_suffix(".json")
    if not ann.exists():
        return None
    try:
        return json.loads(ann.read_text(encoding="utf-8"))
    except Exception:
        return None


def _classify_item(ann: dict | None) -> dict:
    if ann is None:
        return {"has_json": False, "has_bbox": False, "has_classification": False, "labels": [], "shape_count": 0}
    shapes = ann.get("shapes", [])
    labels = [s.get("label", "") for s in shapes if s.get("label")]
    clf = ann.get("flags", {}).get("classification", "")
    return {
        "has_json": True,
        "has_bbox": len(shapes) > 0,
        "has_classification": bool(clf),
        "labels": labels,
        "shape_count": len(shapes),
        "classification": clf,
    }


def _passes_filter(info: dict, filter_val: str, label_filter: str) -> bool:
    if filter_val == "已標注 (有 BBox)" and not info["has_bbox"]:
        return False
    if filter_val == "未標注" and info["has_bbox"]:
        return False
    if filter_val == "已分類" and not info["has_classification"]:
        return False
    if filter_val == "未分類" and info["has_classification"]:
        return False
    if label_filter:
        if label_filter not in info.get("labels", []):
            return False
    return True


def execute_logic(params: dict) -> dict:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return {"error": "No manifest selected", "items": []}

    db_path = _cfg.get_manifest_db_path()
    raw_items = _mdb.get_manifest_items(db_path, manifest_id)

    filter_val = params.get("filter", "全部")
    label_filter = params.get("label_filter", "").strip()

    enriched = []
    for it in raw_items:
        fp = it.get("file_path", "")
        ann = _read_annotation(fp)
        info = _classify_item(ann)
        if not _passes_filter(info, filter_val, label_filter):
            continue
        enriched.append({
            "item_id": it["item_id"],
            "file_path": fp,
            "has_json": info["has_json"],
            "has_bbox": info["has_bbox"],
            "has_classification": info["has_classification"],
            "labels": info.get("labels", []),
            "shape_count": info["shape_count"],
            "classification": info.get("classification", ""),
            "ann_path": str(Path(fp).with_suffix(".json")) if fp else "",
        })

    total = len(raw_items)
    annotated = sum(1 for it in enriched if it["has_bbox"])

    return {
        "manifest_id": manifest_id,
        "items": enriched,
        "total_raw": total,
        "filter": filter_val,
        "label_filter": label_filter,
    }
