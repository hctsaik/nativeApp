from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "shared" / "_manifest_db.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─── _scan_annotations ────────────────────────────────────────────────────────

def test_scan_no_json_files(tmp_path):
    proc = _load(_HERE / "015_process.py", "_015_proc_a")
    items = [
        {"item_id": "i1", "file_path": str(tmp_path / "img1.jpg")},
        {"item_id": "i2", "file_path": str(tmp_path / "img2.jpg")},
    ]
    r = proc._scan_annotations(items)
    assert r["annotated"] == 0
    assert r["no_json"] == 2
    assert r["empty_json"] == 0
    assert r["label_counts"] == {}
    assert r["shapes_stats"] == {}
    assert r["last_annotation_at"] == ""


def test_scan_empty_json(tmp_path):
    proc = _load(_HERE / "015_process.py", "_015_proc_b")
    img = tmp_path / "img.jpg"
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [], "flags": {}}), encoding="utf-8"
    )
    r = proc._scan_annotations([{"item_id": "i1", "file_path": str(img)}])
    assert r["annotated"] == 0
    assert r["no_json"] == 0
    assert r["empty_json"] == 1


def test_scan_counts_labels(tmp_path):
    proc = _load(_HERE / "015_process.py", "_015_proc_c")
    items = []
    for i, label in enumerate(["cat", "cat", "dog"]):
        img = tmp_path / f"img{i}.jpg"
        img.with_suffix(".json").write_text(json.dumps({
            "shapes": [{"label": label, "shape_type": "rectangle",
                        "points": [[0, 0], [10, 10]]}],
        }), encoding="utf-8")
        items.append({"item_id": f"i{i}", "file_path": str(img)})
    r = proc._scan_annotations(items)
    assert r["annotated"] == 3
    assert r["label_counts"] == {"cat": 2, "dog": 1}
    assert r["last_annotation_at"] != ""


def test_scan_shapes_stats(tmp_path):
    proc = _load(_HERE / "015_process.py", "_015_proc_d")
    items = []
    for i, n_shapes in enumerate([1, 3, 5]):
        img = tmp_path / f"img{i}.jpg"
        shape = {"label": "obj", "shape_type": "rectangle", "points": [[0, 0], [10, 10]]}
        img.with_suffix(".json").write_text(
            json.dumps({"shapes": [shape] * n_shapes}), encoding="utf-8"
        )
        items.append({"item_id": f"i{i}", "file_path": str(img)})
    r = proc._scan_annotations(items)
    assert r["shapes_stats"]["min"] == 1
    assert r["shapes_stats"]["max"] == 5
    assert r["shapes_stats"]["mean"] == 3.0
    assert r["shapes_stats"]["median"] == 3.0


def test_scan_annotated_ids_contains_correct_items(tmp_path):
    proc = _load(_HERE / "015_process.py", "_015_proc_e")
    img_with = tmp_path / "with.jpg"
    img_without = tmp_path / "without.jpg"
    img_empty = tmp_path / "empty.jpg"

    img_with.with_suffix(".json").write_text(json.dumps({
        "shapes": [{"label": "x", "shape_type": "rectangle", "points": [[0,0],[1,1]]}]
    }), encoding="utf-8")
    img_empty.with_suffix(".json").write_text(json.dumps({"shapes": []}), encoding="utf-8")

    items = [
        {"item_id": "with", "file_path": str(img_with)},
        {"item_id": "without", "file_path": str(img_without)},
        {"item_id": "empty", "file_path": str(img_empty)},
    ]
    r = proc._scan_annotations(items)
    assert r["annotated_ids"] == {"with"}
    assert r["no_json"] == 1
    assert r["empty_json"] == 1


# ─── execute_logic ────────────────────────────────────────────────────────────

def test_execute_logic_idle_no_manifest_id(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_015_idle")
    proc = _load(_HERE / "015_process.py", "_015_proc_idle")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    assert proc.execute_logic({"manifest_id": ""})["mode"] == "idle"


def test_execute_logic_error_missing_manifest(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_015_miss")
    proc = _load(_HERE / "015_process.py", "_015_proc_miss")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    result = proc.execute_logic({"manifest_id": "nonexistent"})
    assert result["mode"] == "error"


def test_execute_logic_full_stats(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_015_full")
    proc = _load(_HERE / "015_process.py", "_015_proc_full")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")

    # img1: 2 shapes; img2: no annotation
    img1.with_suffix(".json").write_text(json.dumps({
        "shapes": [
            {"label": "cat", "shape_type": "rectangle", "points": [[0, 0], [10, 10]]},
            {"label": "cat", "shape_type": "rectangle", "points": [[20, 20], [30, 30]]},
        ]
    }), encoding="utf-8")

    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mid = "manifest_015_t"
    mdb.create_manifest(db_path, mid, "Test 015", "folder", {})
    mdb.add_manifest_items(db_path, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 640, "height": 480},
        {"item_id": "i2", "file_path": str(img2), "width": 640, "height": 480},
    ])

    clf_path = cim_log / "config" / f"module_012_classifications_{mid[:12]}.json"
    clf_path.parent.mkdir(parents=True, exist_ok=True)
    clf_path.write_text(json.dumps({"i1": "cat"}), encoding="utf-8")

    result = proc.execute_logic({"manifest_id": mid})

    assert result["mode"] == "done"
    assert result["total_items"] == 2
    assert result["annotated_xany"] == 1
    assert result["no_json_count"] == 1
    assert result["empty_json_count"] == 0
    assert result["classified_count"] == 1
    assert result["annotated_no_class"] == 0   # i1 has both bbox and classification
    assert result["label_counts"] == {"cat": 2}
    assert result["classification_counts"] == {"cat": 1}
    assert result["shapes_stats"]["min"] == 2
    assert result["shapes_stats"]["max"] == 2
    assert result["source_path"] == str(tmp_path)
    assert result["last_annotation_at"] != ""
    assert result["manifest_name"] == "Test 015"


def test_execute_logic_annotated_no_class(tmp_path, monkeypatch):
    """bbox 有標注但沒分類的圖片應被計入 annotated_no_class。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_015_anc")
    proc = _load(_HERE / "015_process.py", "_015_proc_anc")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(json.dumps({
        "shapes": [{"label": "dog", "shape_type": "rectangle", "points": [[0, 0], [10, 10]]}]
    }), encoding="utf-8")

    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mid = "manifest_015_anc"
    mdb.create_manifest(db_path, mid, "ANC Test", "folder", {})
    mdb.add_manifest_items(db_path, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 640, "height": 480},
    ])

    # 分類屬於 i2（不存在），i1 有 bbox 但沒有分類
    clf_path = cim_log / "config" / f"module_012_classifications_{mid[:12]}.json"
    clf_path.parent.mkdir(parents=True, exist_ok=True)
    clf_path.write_text(json.dumps({"i2": "cat"}), encoding="utf-8")

    result = proc.execute_logic({"manifest_id": mid})
    assert result["annotated_no_class"] == 1
