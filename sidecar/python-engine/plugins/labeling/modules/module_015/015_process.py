from __future__ import annotations

"""
015_process.py — Dashboard 核心邏輯（無 Streamlit import）

掃描當前 manifest 的 X-AnyLabeling JSON 與分類結果，
回傳豐富的統計資料供 015_output.py 渲染。
"""

import importlib.util as _ilu
import json
import statistics
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent

_cfg_spec = _ilu.spec_from_file_location("_015_config", _HERE / "_config.py")
_cfg = _ilu.module_from_spec(_cfg_spec)
_cfg_spec.loader.exec_module(_cfg)

_mdb_spec = _ilu.spec_from_file_location(
    "_manifest_db", _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)


def _scan_annotations(items: list[dict]) -> dict:
    """
    掃描所有 item 的 X-AnyLabeling JSON 檔案。
    一次 pass 取得所有統計資料，避免重複 IO。
    """
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

    last_annotation_at = ""
    if last_mtime:
        last_annotation_at = datetime.fromtimestamp(last_mtime).strftime("%Y-%m-%d %H:%M:%S")

    return {
        "annotated_ids": annotated_ids,
        "annotated": len(annotated_ids),
        "no_json": no_json,
        "empty_json": empty_json,
        "label_counts": label_counts,
        "shapes_stats": shapes_stats,
        "last_annotation_at": last_annotation_at,
    }


def execute_logic(params: dict) -> dict:
    manifest_id: str = params.get("manifest_id", "")

    db_path = _cfg.get_manifest_db_path()

    if not manifest_id:
        return {"mode": "idle"}

    # ── Manifest 基本資料 ──────────────────────────────────────────────────
    try:
        manifest = _mdb.get_manifest(db_path, manifest_id)
    except Exception as exc:
        return {"mode": "error", "error": str(exc)}

    if manifest is None:
        return {"mode": "error", "error": f"找不到 Manifest：{manifest_id}"}

    items = _mdb.get_manifest_items(db_path, manifest_id)
    total = len(items)

    # ── 標注掃描（一次 IO pass）────────────────────────────────────────────
    ann = _scan_annotations(items)
    annotated_ids: set[str] = ann["annotated_ids"]

    # ── 分類 ────────────────────────────────────────────────────────────────
    classifications = _cfg.load_classifications(manifest_id)
    clf_counts: dict[str, int] = {}
    classified_ids: set[str] = set()
    for item_id, lbl in classifications.items():
        if lbl:
            clf_counts[lbl] = clf_counts.get(lbl, 0) + 1
            classified_ids.add(item_id)

    # 有 bbox 標注但尚未分類的圖數（只有在兩者都存在時才有意義）
    annotated_no_class = len(annotated_ids - classified_ids) if annotated_ids else 0

    # ── 來源資料夾 ──────────────────────────────────────────────────────────
    source_path = ""
    if items:
        fp0 = items[0].get("file_path", "")
        if fp0:
            source_path = str(Path(fp0).parent)

    # ── 匯出歷史 ────────────────────────────────────────────────────────────
    export_history = _mdb.get_exports(db_path, manifest_id)

    return {
        "mode": "done",
        "manifest_name": manifest.get("name", manifest_id),
        "manifest_created_at": (manifest.get("created_at") or "")[:10],
        "source_path": source_path,
        "total_items": total,
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
