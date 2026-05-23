from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "shared" / "_manifest_db.py"
_ENGINE_ROOT = _HERE.parents[2]

if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_manifest(cim_log: Path, mdb, mid: str, items: list[dict]):
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mdb.create_manifest(db_path, mid, f"Test {mid}", "folder", {})
    mdb.add_manifest_items(db_path, mid, items)
    return db_path


def _write_ann(img_path: Path, shapes: list[dict], classification: str = "") -> None:
    data: dict = {"shapes": shapes, "flags": {}}
    if classification:
        data["flags"]["classification"] = classification
    img_path.with_suffix(".json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def _read_ann(img_path: Path) -> dict:
    return json.loads(img_path.with_suffix(".json").read_text(encoding="utf-8"))


def _shape(label: str) -> dict:
    return {"label": label, "shape_type": "rectangle", "points": [[0, 0], [10, 10]]}


# ─── execute_logic ────────────────────────────────────────────────────────────

def test_execute_logic_empty_manifest_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "017_process.py", "_017_proc_a")
    result = proc.execute_logic({"manifest_id": ""})
    assert "error" in result
    assert result["label_map"] == {}


def test_execute_logic_returns_label_map(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_b")
    proc = _load(_HERE / "017_process.py", "_017_proc_b")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    _write_ann(img1, [_shape("cat"), _shape("dog")])
    _write_ann(img2, [_shape("cat")])

    mid = "m017_b"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 100, "height": 100},
        {"item_id": "i2", "file_path": str(img2), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid})
    assert result["label_map"]["cat"] == sorted([str(img1), str(img2)])
    assert result["label_map"]["dog"] == [str(img1)]


def test_execute_logic_near_dupes(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_c")
    proc = _load(_HERE / "017_process.py", "_017_proc_c")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    _write_ann(img1, [_shape("person")])
    _write_ann(img2, [_shape("persons")])

    mid = "m017_c"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 100, "height": 100},
        {"item_id": "i2", "file_path": str(img2), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid})
    assert len(result["near_dupes"]) == 1
    a, b, ratio = result["near_dupes"][0]
    assert {"person", "persons"} == {a, b}
    assert ratio > 0.8


def test_execute_logic_classification_included(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_d")
    proc = _load(_HERE / "017_process.py", "_017_proc_d")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [], classification="indoor")

    mid = "m017_d"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid})
    assert "indoor" in result["label_map"]


# ─── do_rename ────────────────────────────────────────────────────────────────

def test_do_rename_updates_shapes(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_e")
    proc = _load(_HERE / "017_process.py", "_017_proc_e")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [_shape("cat")])

    mid = "m017_e"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    n = proc.do_rename({"manifest_id": mid}, "cat", "kitten")
    assert n == 1
    data = _read_ann(img)
    assert data["shapes"][0]["label"] == "kitten"


def test_do_rename_updates_classification(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_f")
    proc = _load(_HERE / "017_process.py", "_017_proc_f")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [], classification="outdoor")

    mid = "m017_f"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    n = proc.do_rename({"manifest_id": mid}, "outdoor", "outside")
    assert n == 1
    data = _read_ann(img)
    assert data["flags"]["classification"] == "outside"


def test_do_rename_returns_zero_on_empty_manifest(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    proc = _load(_HERE / "017_process.py", "_017_proc_g")
    n = proc.do_rename({"manifest_id": ""}, "cat", "dog")
    assert n == 0


# ─── do_merge ─────────────────────────────────────────────────────────────────

def test_do_merge_collapses_sources(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_h")
    proc = _load(_HERE / "017_process.py", "_017_proc_h")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    _write_ann(img1, [_shape("Cat")])
    _write_ann(img2, [_shape("CAT")])

    mid = "m017_h"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 100, "height": 100},
        {"item_id": "i2", "file_path": str(img2), "width": 100, "height": 100},
    ])

    n = proc.do_merge({"manifest_id": mid}, ["Cat", "CAT"], "cat")
    assert n == 2
    assert _read_ann(img1)["shapes"][0]["label"] == "cat"
    assert _read_ann(img2)["shapes"][0]["label"] == "cat"


# ─── do_delete ────────────────────────────────────────────────────────────────

def test_do_delete_removes_shapes(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_i")
    proc = _load(_HERE / "017_process.py", "_017_proc_i")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [_shape("cat"), _shape("dog")])

    mid = "m017_i"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    n = proc.do_delete({"manifest_id": mid}, "cat")
    assert n == 1
    data = _read_ann(img)
    assert len(data["shapes"]) == 1
    assert data["shapes"][0]["label"] == "dog"


def test_do_delete_clears_classification(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_j")
    proc = _load(_HERE / "017_process.py", "_017_proc_j")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [], classification="indoor")

    mid = "m017_j"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    n = proc.do_delete({"manifest_id": mid}, "indoor")
    assert n == 1
    data = _read_ann(img)
    assert data["flags"]["classification"] == ""


# ─── Dashboard 統計（合併自 module_015）────────────────────────────────────────

def test_execute_logic_dashboard_stats(tmp_path, monkeypatch):
    """execute_logic 應同時回傳 Dashboard 所需的統計欄位。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_dash")
    proc = _load(_HERE / "017_process.py", "_017_proc_dash")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    _write_ann(img1, [_shape("cat"), _shape("cat")])
    # img2: 無標注

    mid = "m017_dash"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 640, "height": 480},
        {"item_id": "i2", "file_path": str(img2), "width": 640, "height": 480},
    ])

    result = proc.execute_logic({"manifest_id": mid})

    assert result["total_items"] == 2
    assert result["annotated_xany"] == 1
    assert result["no_json_count"] == 1
    assert result["empty_json_count"] == 0
    assert result["label_counts"] == {"cat": 2}
    assert result["shapes_stats"]["min"] == 2
    assert result["shapes_stats"]["max"] == 2
    assert result["shapes_stats"]["mean"] == 2.0
    assert result["source_path"] == str(tmp_path)
    assert result["last_annotation_at"] != ""
    assert result["manifest_name"] == f"Test {mid}"


def test_execute_logic_dashboard_classifications(tmp_path, monkeypatch):
    """classified_count 與 annotated_no_class 應正確計算。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_clf")
    proc = _load(_HERE / "017_process.py", "_017_proc_clf")

    img1 = tmp_path / "img1.jpg"
    img2 = tmp_path / "img2.jpg"
    img1.write_bytes(b"img")
    img2.write_bytes(b"img")
    _write_ann(img1, [_shape("dog")])  # bbox 有，但沒分類
    _write_ann(img2, [_shape("cat")])  # bbox + 分類

    mid = "m017_clf"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img1), "width": 640, "height": 480},
        {"item_id": "i2", "file_path": str(img2), "width": 640, "height": 480},
    ])

    clf_path = cim_log / "config" / f"module_012_classifications_{mid[:12]}.json"
    clf_path.parent.mkdir(parents=True, exist_ok=True)
    clf_path.write_text(json.dumps({"i2": "cat"}), encoding="utf-8")

    result = proc.execute_logic({"manifest_id": mid})

    assert result["classified_count"] == 1
    assert result["classification_counts"] == {"cat": 1}
    assert result["annotated_no_class"] == 1   # i1: bbox 有，分類無


def test_execute_logic_dashboard_export_history(tmp_path, monkeypatch):
    """export_count 與 export_history 應反映 manifest DB 的匯出記錄。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_017_exp")
    proc = _load(_HERE / "017_process.py", "_017_proc_exp")

    mid = "m017_exp"
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mdb.create_manifest(db_path, mid, "Export Test", "folder", {})

    # 寫入兩筆匯出記錄
    for i, fmt in enumerate(("COCO", "YOLO")):
        mdb.create_export_record(db_path, f"run_{i}", mid, fmt, "/tmp/out", 10)

    result = proc.execute_logic({"manifest_id": mid})

    assert result["export_count"] == 2
    assert len(result["export_history"]) == 2
    formats = {e["export_format"] for e in result["export_history"]}
    assert formats == {"COCO", "YOLO"}


def test_scan_annotations_no_json(tmp_path, monkeypatch):
    """_scan_annotations 在無 JSON 時應正確計 no_json。"""
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "017_process.py", "_017_scan_a")
    items = [
        {"item_id": "i1", "file_path": str(tmp_path / "a.jpg")},
        {"item_id": "i2", "file_path": str(tmp_path / "b.jpg")},
    ]
    r = proc._scan_annotations(items)
    assert r["annotated"] == 0
    assert r["no_json"] == 2
    assert r["label_counts"] == {}
    assert r["shapes_stats"] == {}


def test_scan_annotations_shapes_stats(tmp_path, monkeypatch):
    """_scan_annotations 應正確計算 min/max/mean/median。"""
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "017_process.py", "_017_scan_b")

    items = []
    for i, n in enumerate([1, 3, 5]):
        img = tmp_path / f"img{i}.jpg"
        img.with_suffix(".json").write_text(json.dumps({
            "shapes": [_shape("x")] * n
        }), encoding="utf-8")
        items.append({"item_id": f"i{i}", "file_path": str(img)})

    r = proc._scan_annotations(items)
    assert r["annotated"] == 3
    assert r["shapes_stats"]["min"] == 1
    assert r["shapes_stats"]["max"] == 5
    assert r["shapes_stats"]["mean"] == 3.0
