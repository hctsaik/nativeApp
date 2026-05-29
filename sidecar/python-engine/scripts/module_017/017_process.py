from __future__ import annotations

import importlib.util as _ilu
import json
import statistics
import sys
from datetime import datetime
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

from annotation.label_ops import (
    delete_label,
    find_near_duplicates,
    merge_labels,
    rename_label,
    scan_labels,
)


def _scan_annotations(items: list[dict]) -> dict:
    """一次 IO pass 掃描所有 item 的標注 JSON，回傳 Dashboard 所需統計。"""
    annotated_ids: set[str] = set()
    no_json: int = 0
    empty_json: int = 0
    label_counts: dict[str, int] = {}
    shapes_per_image: list[int] = []
    last_mtime: float = 0.0

    for it in items:
        fp = it.get("file_path", "")
        item_id = it.get("item_id", "")
        if not fp:
            continue
        ann_path = Path(fp).with_suffix(".json")
        if not ann_path.exists():
            no_json += 1
            continue
        try:
            mtime = ann_path.stat().st_mtime
            if mtime > last_mtime:
                last_mtime = mtime
            data = json.loads(ann_path.read_text(encoding="utf-8"))
            shapes = data.get("shapes", [])
            if shapes:
                annotated_ids.add(item_id)
                shapes_per_image.append(len(shapes))
                for s in shapes:
                    lbl = s.get("label", "")
                    if lbl:
                        label_counts[lbl] = label_counts.get(lbl, 0) + 1
            else:
                empty_json += 1
        except Exception:
            empty_json += 1

    shapes_stats: dict = {}
    if shapes_per_image:
        shapes_stats = {
            "min": min(shapes_per_image),
            "max": max(shapes_per_image),
            "mean": round(statistics.mean(shapes_per_image), 1),
            "median": round(statistics.median(shapes_per_image), 1),
        }

    return {
        "annotated_ids": annotated_ids,
        "annotated": len(annotated_ids),
        "no_json": no_json,
        "empty_json": empty_json,
        "label_counts": label_counts,
        "shapes_stats": shapes_stats,
        "last_annotation_at": (
            datetime.fromtimestamp(last_mtime).strftime("%Y-%m-%d %H:%M:%S")
            if last_mtime else ""
        ),
    }


def execute_logic(params: dict) -> dict:
    manifest_id = params.get("manifest_id", "")
    if not manifest_id:
        return {"error": "No manifest selected", "label_map": {}, "near_dupes": []}

    db_path = _cfg.get_manifest_db_path()
    items = _mdb.get_manifest_items(db_path, manifest_id)

    # ── Label Manager ─────────────────────────────────────────────────────
    label_map = scan_labels(items)
    labels = sorted(label_map.keys())
    near_dupes = find_near_duplicates(labels)

    # ── Dashboard 統計（與 label scan 共用同一批 items，不重複 IO）────────
    ann = _scan_annotations(items)

    classifications = _cfg.load_classifications(manifest_id)
    clf_counts: dict[str, int] = {}
    classified_ids: set[str] = set()
    for item_id, lbl in classifications.items():
        if lbl:
            clf_counts[lbl] = clf_counts.get(lbl, 0) + 1
            classified_ids.add(item_id)

    annotated_no_class = (
        len(ann["annotated_ids"] - classified_ids) if ann["annotated_ids"] else 0
    )

    source_path = ""
    if items:
        fp0 = items[0].get("file_path", "")
        if fp0:
            source_path = str(Path(fp0).parent)

    try:
        manifest = _mdb.get_manifest(db_path, manifest_id)
    except Exception:
        manifest = None

    export_history = _mdb.get_exports(db_path, manifest_id)

    return {
        # Label Manager
        "manifest_id": manifest_id,
        "label_map": label_map,
        "near_dupes": near_dupes,
        "items": items,
        # Dashboard
        "manifest_name": manifest.get("name", manifest_id) if manifest else manifest_id,
        "manifest_created_at": (manifest.get("created_at") or "")[:10] if manifest else "",
        "source_path": source_path,
        "total_items": len(items),
        "annotated_xany": ann["annotated"],
        "no_json_count": ann["no_json"],
        "empty_json_count": ann["empty_json"],
        "classified_count": len(classified_ids),
        "annotated_no_class": annotated_no_class,
        "export_count": len(export_history),
        "label_counts": ann["label_counts"],
        "classification_counts": clf_counts,
        "shapes_stats": ann["shapes_stats"],
        "last_annotation_at": ann["last_annotation_at"],
        "export_history": export_history,
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
