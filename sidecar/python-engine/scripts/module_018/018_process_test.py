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


def _shape(label: str) -> dict:
    return {"label": label, "shape_type": "rectangle", "points": [[0, 0], [10, 10]]}


# ─── execute_logic ────────────────────────────────────────────────────────────

def test_execute_logic_empty_manifest_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "018_process.py", "_018_proc_a")
    result = proc.execute_logic({"manifest_id": ""})
    assert "error" in result
    assert result["items"] == []


def test_execute_logic_all_items_returned(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_b")
    proc = _load(_HERE / "018_process.py", "_018_proc_b")

    imgs = [tmp_path / f"img{i}.jpg" for i in range(4)]
    for img in imgs:
        img.write_bytes(b"img")
    _write_ann(imgs[0], [_shape("cat")])
    _write_ann(imgs[1], [], classification="indoor")
    # imgs[2]: no annotation file
    # imgs[3]: empty shapes
    _write_ann(imgs[3], [])

    mid = "m018_b"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": f"i{i}", "file_path": str(img), "width": 100, "height": 100}
        for i, img in enumerate(imgs)
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "全部"})
    assert result["total_raw"] == 4
    assert len(result["items"]) == 4


def test_filter_has_bbox(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_c")
    proc = _load(_HERE / "018_process.py", "_018_proc_c")

    img_with = tmp_path / "with.jpg"
    img_without = tmp_path / "without.jpg"
    img_with.write_bytes(b"img")
    img_without.write_bytes(b"img")
    _write_ann(img_with, [_shape("dog")])
    _write_ann(img_without, [])

    mid = "m018_c"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "a", "file_path": str(img_with), "width": 100, "height": 100},
        {"item_id": "b", "file_path": str(img_without), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "已標注 (有 BBox)"})
    assert len(result["items"]) == 1
    assert result["items"][0]["item_id"] == "a"


def test_filter_unannotated(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_d")
    proc = _load(_HERE / "018_process.py", "_018_proc_d")

    img_ann = tmp_path / "ann.jpg"
    img_no = tmp_path / "no.jpg"
    img_ann.write_bytes(b"img")
    img_no.write_bytes(b"img")
    _write_ann(img_ann, [_shape("cat")])
    # img_no: no JSON at all

    mid = "m018_d"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "a", "file_path": str(img_ann), "width": 100, "height": 100},
        {"item_id": "b", "file_path": str(img_no), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "未標注"})
    assert len(result["items"]) == 1
    assert result["items"][0]["item_id"] == "b"


def test_filter_classified(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_e")
    proc = _load(_HERE / "018_process.py", "_018_proc_e")

    img_clf = tmp_path / "clf.jpg"
    img_no = tmp_path / "no.jpg"
    img_clf.write_bytes(b"img")
    img_no.write_bytes(b"img")
    _write_ann(img_clf, [], classification="indoor")
    _write_ann(img_no, [_shape("cat")])

    mid = "m018_e"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "a", "file_path": str(img_clf), "width": 100, "height": 100},
        {"item_id": "b", "file_path": str(img_no), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "已分類"})
    assert len(result["items"]) == 1
    assert result["items"][0]["has_classification"] is True


def test_label_filter(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_f")
    proc = _load(_HERE / "018_process.py", "_018_proc_f")

    img_cat = tmp_path / "cat.jpg"
    img_dog = tmp_path / "dog.jpg"
    img_cat.write_bytes(b"img")
    img_dog.write_bytes(b"img")
    _write_ann(img_cat, [_shape("cat")])
    _write_ann(img_dog, [_shape("dog")])

    mid = "m018_f"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "a", "file_path": str(img_cat), "width": 100, "height": 100},
        {"item_id": "b", "file_path": str(img_dog), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "全部", "label_filter": "cat"})
    assert len(result["items"]) == 1
    assert "cat" in result["items"][0]["labels"]


def test_item_fields_present(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_018_g")
    proc = _load(_HERE / "018_process.py", "_018_proc_g")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    _write_ann(img, [_shape("cat"), _shape("dog")], classification="outdoor")

    mid = "m018_g"
    _make_manifest(cim_log, mdb, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({"manifest_id": mid, "filter": "全部"})
    assert len(result["items"]) == 1
    it = result["items"][0]
    assert it["item_id"] == "i1"
    assert it["has_bbox"] is True
    assert it["has_classification"] is True
    assert it["shape_count"] == 2
    assert set(it["labels"]) == {"cat", "dog"}
    assert it["classification"] == "outdoor"
    assert it["ann_path"].endswith(".json")
