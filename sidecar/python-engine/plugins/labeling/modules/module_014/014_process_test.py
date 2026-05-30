from __future__ import annotations

import importlib.util
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_manifest(tmp_path, mdb, monkeypatch, images: list[dict]):
    """Helper: 建立 manifest + items，回傳 (db_path, manifest_id)。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mid = "manifest_014_test"
    mdb.create_manifest(db_path, mid, "Test Manifest", "folder", {})
    mdb.add_manifest_items(db_path, mid, images)
    return db_path, mid


# ─── _parse_shapes ────────────────────────────────────────────────────────────

def test_parse_shapes_rectangle():
    proc = _load(_HERE / "014_process.py", "_014_proc_a")
    shapes = proc._parse_shapes([{
        "label": "cat",
        "shape_type": "rectangle",
        "points": [[10, 20], [100, 80]],
    }])
    assert len(shapes) == 1
    assert shapes[0]["label"] == "cat"
    assert shapes[0]["x1"] == 10.0
    assert shapes[0]["y1"] == 20.0
    assert shapes[0]["x2"] == 100.0
    assert shapes[0]["y2"] == 80.0


def test_parse_shapes_polygon():
    proc = _load(_HERE / "014_process.py", "_014_proc_b")
    shapes = proc._parse_shapes([{
        "label": "dog",
        "shape_type": "polygon",
        "points": [[0, 0], [50, 0], [50, 50], [0, 50]],
    }])
    assert len(shapes) == 1
    assert shapes[0]["shape_type"] == "polygon"
    assert len(shapes[0]["polygon_pts"]) == 4


def test_parse_shapes_skips_point():
    proc = _load(_HERE / "014_process.py", "_014_proc_c")
    shapes = proc._parse_shapes([{
        "label": "kp",
        "shape_type": "point",
        "points": [[10, 10]],
    }])
    assert shapes == []


# ─── export_coco_json ─────────────────────────────────────────────────────────

def test_export_coco_json_creates_three_splits(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_coco")

    items = [{"item_id": f"img{i}", "file_path": f"/p/img{i}.jpg",
               "width": 640, "height": 480} for i in range(6)]
    shapes_map = {
        "img0": [{"label": "cat", "x1": 10, "y1": 10, "x2": 50, "y2": 50,
                  "shape_type": "rectangle", "polygon_pts": []}],
        "img1": [],
    }
    split_groups = {
        "train": ["img0", "img1", "img2", "img3"],
        "val": ["img4"],
        "test": ["img5"],
    }
    out = tmp_path / "coco"
    paths = proc.export_coco_json(items, shapes_map, split_groups, out)

    assert set(paths.keys()) == {"train", "val", "test"}
    train_data = json.loads(Path(paths["train"]).read_text(encoding="utf-8"))
    assert len(train_data["images"]) == 4
    assert len(train_data["annotations"]) == 1
    assert train_data["categories"][0]["name"] == "cat"


# ─── export_yolo_txt ──────────────────────────────────────────────────────────

def test_export_yolo_txt_creates_data_yaml(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_yolo")

    items = [{"item_id": "a", "file_path": str(tmp_path / "a.jpg"),
               "width": 100, "height": 100}]
    (tmp_path / "a.jpg").write_bytes(b"img")
    shapes_map = {"a": [{"label": "dog", "x1": 10, "y1": 10, "x2": 50, "y2": 50,
                          "shape_type": "rectangle", "polygon_pts": []}]}
    split_groups = {"train": ["a"], "val": [], "test": []}
    out = tmp_path / "yolo"
    paths = proc.export_yolo_txt(items, shapes_map, split_groups, out)

    assert (out / "data.yaml").exists()
    assert (out / "classes.txt").read_text(encoding="utf-8").strip() == "dog"
    lbl_file = out / "labels" / "train" / "a.txt"
    assert lbl_file.exists()
    line = lbl_file.read_text(encoding="utf-8").strip()
    parts = line.split()
    assert parts[0] == "0"  # class_id
    assert abs(float(parts[1]) - 0.3) < 0.05  # cx ≈ 0.3


# ─── export_pascal_voc ────────────────────────────────────────────────────────

def test_export_pascal_voc_xml_structure(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_voc")

    img_path = tmp_path / "frame.jpg"
    img_path.write_bytes(b"img")
    items = [{"item_id": "f1", "file_path": str(img_path),
               "width": 800, "height": 600}]
    shapes_map = {"f1": [{"label": "bird", "x1": 100, "y1": 50, "x2": 300, "y2": 200,
                           "shape_type": "rectangle", "polygon_pts": []}]}
    split_groups = {"train": ["f1"], "val": [], "test": []}
    out = tmp_path / "voc"
    paths = proc.export_pascal_voc(items, shapes_map, split_groups, out)

    xml_path = out / "Annotations" / "frame.xml"
    assert xml_path.exists()
    tree = ET.parse(str(xml_path))
    root = tree.getroot()
    assert root.tag == "annotation"
    obj = root.find("object")
    assert obj is not None
    assert obj.find("name").text == "bird"
    assert obj.find("bndbox/xmin").text == "100"
    assert obj.find("bndbox/ymax").text == "200"

    train_txt = out / "ImageSets" / "Main" / "train.txt"
    assert "frame" in train_txt.read_text(encoding="utf-8")


# ─── export_imagefolder ───────────────────────────────────────────────────────

def test_export_imagefolder_copies_by_label(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_imgf")

    src1 = tmp_path / "cat001.jpg"
    src2 = tmp_path / "dog001.jpg"
    src1.write_bytes(b"cat")
    src2.write_bytes(b"dog")
    items = [
        {"item_id": "c1", "file_path": str(src1)},
        {"item_id": "d1", "file_path": str(src2)},
    ]
    classifications = {"c1": "cat", "d1": "dog"}
    split_groups = {"train": ["c1", "d1"], "val": [], "test": []}
    out = tmp_path / "imgfolder"
    paths = proc.export_imagefolder(items, classifications, split_groups, out)

    assert (out / "train" / "cat" / "cat001.jpg").exists()
    assert (out / "train" / "dog" / "dog001.jpg").exists()


def test_export_imagefolder_skips_no_label(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_imgf2")

    src = tmp_path / "img.jpg"
    src.write_bytes(b"img")
    items = [{"item_id": "x", "file_path": str(src)}]
    classifications: dict = {}
    split_groups = {"train": ["x"], "val": [], "test": []}
    out = tmp_path / "imgfolder2"
    paths = proc.export_imagefolder(items, classifications, split_groups, out)
    assert paths["_skipped"] == "1"


# ─── export_csv ───────────────────────────────────────────────────────────────

def test_export_csv_has_all_columns(tmp_path, monkeypatch):
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load(_HERE / "014_process.py", "_014_proc_csv")

    items = [{"item_id": "p1", "file_path": "/data/p1.jpg"}]
    shapes_map = {"p1": [{"label": "leaf", "x1": 5, "y1": 5, "x2": 20, "y2": 20,
                           "shape_type": "rectangle", "polygon_pts": []}]}
    classifications = {"p1": "healthy"}
    out = tmp_path / "csv_out"
    csv_path = proc.export_csv(items, shapes_map, classifications, out)

    import csv
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))
    assert len(rows) == 1
    assert rows[0]["label"] == "leaf"
    assert rows[0]["classification"] == "healthy"
    assert rows[0]["x1"] == "5.00"


# ─── execute_logic（整合）────────────────────────────────────────────────────

def test_execute_logic_full_pipeline(tmp_path, monkeypatch):
    # 必須先 setenv，再 load module（_CIM_LOG_DIR 在 module-level 被捕捉）
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load(_SHARED, "_mdb_014_int")
    proc = _load(_HERE / "014_process.py", "_014_proc_full")

    src = tmp_path / "img001.jpg"
    src.write_bytes(b"img")
    ann = src.with_suffix(".json")
    ann.write_text(json.dumps({
        "imagePath": "img001.jpg",
        "shapes": [{"label": "cat", "shape_type": "rectangle",
                    "points": [[0, 0], [100, 80]]}],
    }), encoding="utf-8")

    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mid = "manifest_014_test"
    mdb.create_manifest(db_path, mid, "Test Manifest", "folder", {})
    mdb.add_manifest_items(db_path, mid,
        [{"item_id": "i1", "file_path": str(src), "width": 640, "height": 480}])

    # 寫分類結果
    clf_path = cim_log / "config" / f"module_012_classifications_{mid[:12]}.json"
    clf_path.parent.mkdir(parents=True, exist_ok=True)
    clf_path.write_text(json.dumps({"i1": "cat"}), encoding="utf-8")

    result = proc.execute_logic({
        "manifest_id": mid,
        "export_formats": ["coco_json", "yolo_txt", "pascal_voc", "imagefolder", "csv"],
        "export_dir": str(tmp_path / "export"),
        "split_train": 100,
        "split_val": 0,
        "split_test": 0,
        "stratified": False,
    })

    assert result["mode"] == "done"
    assert result["total_items"] == 1
    assert result["annotated_items"] == 1
    assert result["classified_items"] == 1
    assert "coco_json" in result["export_paths"]
    assert "yolo_txt" in result["export_paths"]
    assert "pascal_voc" in result["export_paths"]
    assert "imagefolder" in result["export_paths"]
    assert "csv" in result["export_paths"]


def test_execute_logic_missing_manifest(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load(_SHARED, "_mdb_014_miss")
    proc = _load(_HERE / "014_process.py", "_014_proc_miss")

    mdb.init_db(cim_log / "db" / "manifest.sqlite")

    result = proc.execute_logic({"manifest_id": "nonexistent"})
    assert result["mode"] == "error"


# ─── validate_pre_export ──────────────────────────────────────────────────────

def test_validate_no_json_file(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_a")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    shapes_map: dict = {"i1": []}
    issues = proc.validate_pre_export(items, shapes_map, {}, ["coco_json"])
    codes = [v.code for v in issues]
    assert "no_json_file" in codes


def test_validate_empty_shapes(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_b")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [], "flags": {}}), encoding="utf-8"
    )
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    shapes_map: dict = {"i1": []}
    issues = proc.validate_pre_export(items, shapes_map, {}, ["coco_json"])
    codes = [v.code for v in issues]
    assert "empty_shapes" in codes
    assert "no_json_file" not in codes


def test_validate_invalid_bbox(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_c")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [{"label": "cat", "shape_type": "rectangle",
                                "points": [[10, 10], [10, 50]]}]}),
        encoding="utf-8",
    )
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    bad_shape = {"label": "cat", "x1": 10.0, "y1": 10.0, "x2": 10.0, "y2": 50.0,
                 "shape_type": "rectangle", "polygon_pts": []}
    shapes_map = {"i1": [bad_shape]}
    issues = proc.validate_pre_export(items, shapes_map, {}, ["coco_json"])
    codes = [v.code for v in issues]
    assert "invalid_bbox" in codes
    assert any(v.severity == "error" for v in issues if v.code == "invalid_bbox")


def test_validate_empty_label(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_d")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [{"label": "", "shape_type": "rectangle",
                                "points": [[0, 0], [10, 10]]}]}),
        encoding="utf-8",
    )
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    shapes_map = {"i1": [{"label": "", "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0,
                          "shape_type": "rectangle", "polygon_pts": []}]}
    issues = proc.validate_pre_export(items, shapes_map, {}, ["coco_json"])
    codes = [v.code for v in issues]
    assert "empty_label" in codes


def test_validate_no_classification_for_imagefolder(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_e")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [], "flags": {}}), encoding="utf-8"
    )
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    shapes_map: dict = {"i1": []}
    issues = proc.validate_pre_export(items, shapes_map, {}, ["imagefolder"])
    codes = [v.code for v in issues]
    assert "no_classification" in codes


def test_validate_clean_item_has_no_issues(tmp_path):
    proc = _load(_HERE / "014_process.py", "_014_proc_val_f")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [{"label": "cat", "shape_type": "rectangle",
                                "points": [[0, 0], [50, 50]]}]}),
        encoding="utf-8",
    )
    items = [{"item_id": "i1", "file_path": str(img), "width": 100, "height": 100}]
    shapes_map = {"i1": [{"label": "cat", "x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 50.0,
                          "shape_type": "rectangle", "polygon_pts": []}]}
    issues = proc.validate_pre_export(items, shapes_map, {"i1": "outdoor"}, ["coco_json"])
    assert issues == []


def test_execute_logic_blocked_on_error(tmp_path, monkeypatch):
    """Invalid bbox causes execute_logic to return validation_error mode."""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_014_blk")
    proc = _load(_HERE / "014_process.py", "_014_proc_blk")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    # Zero-width box: x1==x2
    img.with_suffix(".json").write_text(
        json.dumps({"shapes": [{"label": "cat", "shape_type": "rectangle",
                                "points": [[10, 10], [10, 50]]}]}),
        encoding="utf-8",
    )
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mid = "m014_blk"
    mdb.create_manifest(db_path, mid, "Block Test", "folder", {})
    mdb.add_manifest_items(db_path, mid, [
        {"item_id": "i1", "file_path": str(img), "width": 100, "height": 100},
    ])

    result = proc.execute_logic({
        "manifest_id": mid,
        "export_formats": ["coco_json"],
        "export_dir": str(tmp_path / "export"),
        "split_train": 100, "split_val": 0, "split_test": 0,
    })
    assert result["mode"] == "validation_error"
    assert any(v["code"] == "invalid_bbox" for v in result["validation_issues"])
