from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from annotation.services import AnnotationService
from annotation.storage.workspace import AnnotationWorkspace


# ── helpers ───────────────────────────────────────────────────────────────────

def _query_images(db_path: str, category: str) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if category == "ALL":
            rows = conn.execute(
                "SELECT id, filename, true_label FROM images ORDER BY id"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, filename, true_label FROM images WHERE true_label = ? ORDER BY id",
                (category,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── phase 1: prepare labeling project ────────────────────────────────────────

def _execute_phase1(params: dict) -> dict:
    t0 = time.perf_counter()
    root = Path(params["workspace_root"])
    root.mkdir(parents=True, exist_ok=True)
    tool = _normalize_tool(params.get("annotation_tool", params.get("tool", "x-anylabeling")))
    annotation_format = _format_for_tool(tool)
    project_name = _project_dir_name(tool)

    db_path = params.get("db_path", "")
    if not Path(db_path).exists():
        return {"mode": "labeling_phase1", "legacy_mode": "xany_phase1", "error": "db_not_found", "annotation_tool": tool}

    image_dir = Path(params.get("image_dir", ""))
    category = params.get("category", "ALL")
    labels = params.get("labels", ["貓", "狗", "大象"])

    rows = _query_images(db_path, category)
    if not rows:
        return {"mode": "labeling_phase1", "legacy_mode": "xany_phase1", "error": "no_images", "category": category, "annotation_tool": tool}

    image_paths = [str(image_dir / r["filename"]) for r in rows if (image_dir / r["filename"]).exists()]
    if not image_paths:
        return {"mode": "labeling_phase1", "legacy_mode": "xany_phase1", "error": "no_images_found", "category": category, "annotation_tool": tool}

    service = AnnotationService(AnnotationWorkspace(root / "workspace"))

    dataset_name = f"animals-{category}" if category != "ALL" else "animals-all"
    dataset = service.create_dataset(dataset_name, str(root))
    assets = service.ingest_assets(dataset["id"], image_paths)["assets"]

    label_defs = [
        {"id": lbl, "name": lbl, "allowed_geometry_types": ["bbox", "polygon"]}
        for lbl in labels
    ]
    schema = service.create_schema(f"{dataset_name}-schema", label_defs)

    project_dir = str(root / project_name)
    service.prepare_labeling_project(tool, dataset["id"], schema["id"], project_dir)

    tool_install = service.detect_labeling_tool(tool)
    tool_launch = None
    if params.get("launch_labeling_tool", params.get("launch_xany", False)):
        tool_launch = service.launch_labeling_project(tool, project_dir)

    labels_dir_name = "annotations" if tool == "isat" else "labels"
    session = {
        "dataset_id": dataset["id"],
        "schema_id": schema["id"],
        "annotation_tool": tool,
        "annotation_format": annotation_format,
        "project_dir": project_dir,
        "labels_dir": str(Path(project_dir) / labels_dir_name),
        "xany_dir": project_dir,
        "assets": [{"id": a["id"], "uri": a["uri"]} for a in assets],
    }
    (root / "session.json").write_text(
        json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    project_root = Path(project_dir)
    classes_file = project_root / ("categories.txt" if tool == "isat" else "classes.txt")
    return {
        "mode": "labeling_phase1",
        "legacy_mode": "xany_phase1",
        "phase": 1,
        "annotation_tool": tool,
        "annotation_format": annotation_format,
        "elapsed_ms": elapsed_ms,
        "workspace_root": str(root),
        "category": category,
        "dataset": dataset,
        "schema": schema,
        "assets": assets,
        "image_count": len(image_paths),
        "project_dir": project_dir,
        "labels_dir": str(Path(project_dir) / labels_dir_name),
        "tool_install": tool_install,
        "tool_launch": tool_launch,
        "xany_dir": project_dir,
        "xany_install": tool_install,
        "xany_launch": tool_launch,
        "session": session,
        "project_files": {
            "classes_txt": classes_file.read_text(encoding="utf-8").strip(),
            "images": [p.name for p in (project_root / "images").glob("*") if p.is_file()],
            "labels_dir": str(Path(project_dir) / labels_dir_name),
            "project_dir": project_dir,
        },
    }


# ── phase 2: import annotations ───────────────────────────────────────────────

def _execute_phase2(params: dict) -> dict:
    t0 = time.perf_counter()
    root = Path(params["workspace_root"])

    service = AnnotationService(AnnotationWorkspace(root / "workspace"))

    annotation_format = _normalize_format(params.get("annotation_format", params.get("input_format", "x-anylabeling")))
    result = service.import_project_labels(
        params["dataset_id"],
        params["schema_id"],
        annotation_format,
        params["labels_dir"],
    )
    annotation_set = result["annotation_set"]
    aset_id = annotation_set["id"]

    validation = service.validate_set(aset_id)

    review = None
    if params.get("approve", True) and validation["ok"]:
        service.submit_for_review(aset_id)
        review = service.review_task(
            aset_id, "approved",
            actor_id="module-006",
            comment="Approved via animal tagger",
        )
        annotation_set = review["annotation_set"]

    exports = {}
    export_root = root / "exports"
    for fmt in params.get("export_formats", ["coco", "yolo-detection"]):
        purpose = "training" if annotation_set.get("state") == "approved" else "preview"
        exports[fmt] = service.create_export(
            aset_id, fmt, str(export_root / fmt.replace("-", "_")), purpose=purpose
        )

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "mode": "labeling_phase2",
        "legacy_mode": "xany_phase2",
        "phase": 2,
        "annotation_format": annotation_format,
        "elapsed_ms": elapsed_ms,
        "workspace_root": str(root),
        "import_result": result,
        "annotation_set": annotation_set,
        "validation": validation,
        "review": review,
        "exports": exports,
        "export_root": str(export_root),
    }


# ── dispatcher ────────────────────────────────────────────────────────────────

def execute_logic(params: dict) -> dict:
    # ── Manifest 整合（選填）──────────────────────────────────────────────────
    # 若 render_input 傳入 manifest_id，預先載入圖片清單到 params，
    # 供後續 Phase 1 透過 params.get("_manifest_items") 取得。
    _manifest_id = params.get("manifest_id")
    if _manifest_id:
        try:
            import importlib.util as _ilu
            from pathlib import Path as _Path
            import os as _os
            _HERE = _Path(__file__).resolve().parent
            _spec = _ilu.spec_from_file_location(
                "_manifest_db",
                _HERE.parent / "shared" / "_manifest_db.py",
            )
            _mdb = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_mdb)
            _proj = _Path(__file__).resolve().parents[4]
            _cim = _Path(_os.environ.get(
                "CIM_LOG_DIR",
                str(_proj / "tmp" / "cim_log"),
            ))
            _db = _cim / "db" / "manifest.sqlite"
            _manifest = _mdb.get_manifest(_db, _manifest_id)
            _items = _mdb.get_manifest_items(_db, _manifest_id)
            params["_manifest_name"] = _manifest["name"] if _manifest else _manifest_id
            params["_manifest_items"] = _items
            params["_using_manifest"] = True
        except Exception as _e:
            params["_manifest_items"] = []
            params["_using_manifest"] = False

    mode = params.get("mode", "browse")
    if mode in {"xany_phase1", "labeling_phase1"}:
        return _execute_phase1(params)
    if mode in {"xany_phase2", "labeling_phase2"}:
        return _execute_phase2(params)
    # browse: pass-through with DB existence check
    db_path = params.get("db_path", "")
    if not Path(db_path).exists():
        return {**params, "error": "db_not_found"}
    return params


def _normalize_tool(value: str) -> str:
    tool = (value or "x-anylabeling").strip().lower().replace("_", "-")
    if tool == "xanylabeling":
        return "x-anylabeling"
    return tool


def _normalize_format(value: str) -> str:
    fmt = (value or "x-anylabeling").strip().lower().replace("_", "-")
    aliases = {
        "xanylabeling": "x-anylabeling",
        "yolo": "yolo-detection",
        "yolo-detect": "yolo-detection",
        "yolo-seg": "yolo-segmentation",
    }
    return aliases.get(fmt, fmt)


def _format_for_tool(tool: str) -> str:
    if tool == "isat":
        return "isat"
    return "x-anylabeling" if tool == "x-anylabeling" else "labelme"


def _project_dir_name(tool: str) -> str:
    return {
        "isat": "isat_project",
        "labelme": "labelme_project",
        "x-anylabeling": "xany_project",
    }.get(tool, f"{tool.replace('-', '_')}_project")
