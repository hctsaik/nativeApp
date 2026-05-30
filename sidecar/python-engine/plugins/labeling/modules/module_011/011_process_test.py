from __future__ import annotations

"""
011_process_test.py — Module 011 Result Sink 單元測試
使用 pytest + tmp_path fixture。
"""

import importlib.util as _ilu
import json
import sys
from pathlib import Path

import pytest

# ─── 載入 011_process（不透過 package import，直接用 importlib）────────────────

_HERE = Path(__file__).resolve().parent
_PROCESS_PATH = _HERE / "011_process.py"

_spec = _ilu.spec_from_file_location("process_011", _PROCESS_PATH)
_proc = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_proc)  # type: ignore[union-attr]

# ─── 載入 _manifest_db ───────────────────────────────────────────────────────

_MDB_PATH = _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"
_mdb_spec = _ilu.spec_from_file_location("_manifest_db", _MDB_PATH)
_mdb = _ilu.module_from_spec(_mdb_spec)
_mdb_spec.loader.exec_module(_mdb)  # type: ignore[union-attr]


# ─── 輔助函式 ─────────────────────────────────────────────────────────────────


def _make_db(tmp_path: Path) -> Path:
    """初始化測試用 SQLite DB 並回傳路徑。"""
    db = tmp_path / "test_manifest.sqlite"
    _mdb.init_db(db)
    return db


def _insert_manifest(db: Path, manifest_id: str = "m001", name: str = "測試集") -> dict:
    return _mdb.create_manifest(
        db, manifest_id, name, "folder", {"path": "/tmp/images"}
    )


def _insert_items(db: Path, manifest_id: str, items: list[dict]) -> None:
    _mdb.add_manifest_items(db, manifest_id, items)


def _insert_result(
    db: Path,
    run_id: str,
    manifest_id: str,
    item_id: str,
    shapes: list[dict],
    label: str = "cat",
    confidence: float = 0.9,
) -> None:
    ann_json = json.dumps({"shapes": shapes})
    _mdb.upsert_annotation_result(
        db, run_id, manifest_id, item_id, ann_json, label, confidence, "manual"
    )


def _rect_shape(label: str, x1=10, y1=20, x2=100, y2=80) -> dict:
    return {
        "label": label,
        "points": [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        "shape_type": "rectangle",
    }


# ─── Test 1：解析 bbox ────────────────────────────────────────────────────────


def test_parse_bbox_from_shapes():
    shapes = [
        _rect_shape("cat", 10, 20, 100, 80),
        _rect_shape("dog", 200, 50, 350, 150),
        # 非 rectangle 應被忽略
        {"label": "bird", "points": [[0, 0]], "shape_type": "polygon"},
    ]
    bboxes = _proc._parse_bbox_from_shapes(shapes)
    assert len(bboxes) == 2
    assert bboxes[0]["label"] == "cat"
    assert bboxes[0]["x1"] == 10.0
    assert bboxes[0]["y1"] == 20.0
    assert bboxes[0]["x2"] == 100.0
    assert bboxes[0]["y2"] == 80.0
    assert bboxes[1]["label"] == "dog"


# ─── Test 2：stratified_split 正常比例 ───────────────────────────────────────


def test_stratified_split_basic():
    item_ids = [f"img_{i:03d}" for i in range(30)]
    # 3 類各 10 筆
    item_labels = {}
    for i, iid in enumerate(item_ids):
        item_labels[iid] = ["cat", "dog", "bird"][i % 3]

    ratios = {"train": 0.7, "val": 0.15, "test": 0.15}
    result = _proc.stratified_split(item_ids, item_labels, ratios)

    assert set(result.keys()) == {"train", "val", "test"}
    total = sum(len(v) for v in result.values())
    assert total == 30

    # train 應佔最多
    assert len(result["train"]) > len(result["val"])
    assert len(result["train"]) > len(result["test"])

    # 不重複
    all_ids = result["train"] + result["val"] + result["test"]
    assert len(set(all_ids)) == len(all_ids)


# ─── Test 3：stratified_split 樣本不足（< 3）────────────────────────────────


def test_stratified_split_insufficient():
    item_ids = ["a", "b", "c", "d", "e"]
    item_labels = {
        "a": "rare",   # 只有 1 筆的罕見類別
        "b": "common",
        "c": "common",
        "d": "common",
        "e": "common",
    }
    ratios = {"train": 0.7, "val": 0.15, "test": 0.15}

    # 不應 crash
    result = _proc.stratified_split(item_ids, item_labels, ratios)
    total = sum(len(v) for v in result.values())
    assert total == 5

    # 確保沒有重複
    all_ids = result["train"] + result["val"] + result["test"]
    assert len(set(all_ids)) == len(all_ids)


# ─── Test 4：export_coco_json 建立檔案 ────────────────────────────────────────


def test_export_coco_json_creates_files(tmp_path):
    items = [
        {"item_id": "i1", "file_path": "/img/a.jpg", "width": 640, "height": 480},
        {"item_id": "i2", "file_path": "/img/b.jpg", "width": 640, "height": 480},
        {"item_id": "i3", "file_path": "/img/c.jpg", "width": 640, "height": 480},
    ]
    results = [
        {
            "item_id": "i1",
            "annotation_json": json.dumps({"shapes": [_rect_shape("cat")]}),
        },
        {
            "item_id": "i2",
            "annotation_json": json.dumps({"shapes": [_rect_shape("dog")]}),
        },
    ]
    split_groups = {"train": ["i1", "i2"], "val": ["i3"], "test": []}
    out_dir = tmp_path / "coco"

    paths = _proc.export_coco_json(items, results, split_groups, out_dir)

    assert "train" in paths
    assert "val" in paths
    assert Path(paths["train"]).exists()
    assert Path(paths["val"]).exists()


# ─── Test 5：export_coco_json 結構驗證 ────────────────────────────────────────


def test_export_coco_json_structure(tmp_path):
    items = [
        {"item_id": "i1", "file_path": "/img/a.jpg", "width": 640, "height": 480},
        {"item_id": "i2", "file_path": "/img/b.jpg", "width": 640, "height": 480},
    ]
    results = [
        {
            "item_id": "i1",
            "annotation_json": json.dumps({"shapes": [_rect_shape("cat", 10, 20, 100, 80)]}),
        },
        {
            "item_id": "i2",
            "annotation_json": json.dumps({"shapes": [_rect_shape("dog", 5, 5, 50, 50)]}),
        },
    ]
    split_groups = {"train": ["i1", "i2"], "val": [], "test": []}
    out_dir = tmp_path / "coco2"

    paths = _proc.export_coco_json(items, results, split_groups, out_dir)

    train_json = json.loads(Path(paths["train"]).read_text(encoding="utf-8"))

    # 必須有 images / annotations / categories
    assert "images" in train_json
    assert "annotations" in train_json
    assert "categories" in train_json

    # 2 張圖片
    assert len(train_json["images"]) == 2

    # 2 個標注
    assert len(train_json["annotations"]) == 2

    # 標注的 bbox 格式 [x, y, w, h]
    ann = train_json["annotations"][0]
    assert len(ann["bbox"]) == 4
    x, y, w, h = ann["bbox"]
    assert w > 0 and h > 0


# ─── Test 6：export_yolo_txt 建立標注檔 ──────────────────────────────────────


def test_export_yolo_txt_creates_labels(tmp_path):
    items = [
        {"item_id": "i1", "file_path": "/img/a.jpg", "width": 640, "height": 480},
        {"item_id": "i2", "file_path": "/img/b.jpg", "width": 640, "height": 480},
    ]
    results = [
        {
            "item_id": "i1",
            "annotation_json": json.dumps(
                {"shapes": [_rect_shape("cat", 0, 0, 320, 240)]}
            ),
        },
        {
            "item_id": "i2",
            "annotation_json": json.dumps(
                {"shapes": [_rect_shape("dog", 100, 100, 500, 400)]}
            ),
        },
    ]
    split_groups = {"train": ["i1", "i2"], "val": [], "test": []}
    out_dir = tmp_path / "yolo"

    paths = _proc.export_yolo_txt(items, results, split_groups, out_dir)

    # classes.txt 存在
    assert "classes_txt" in paths
    assert Path(paths["classes_txt"]).exists()

    # labels/train/ 存在
    lbl_dir = out_dir / "labels" / "train"
    assert lbl_dir.exists()

    # 每個有標注的 item 都有對應的 txt
    assert (lbl_dir / "a.txt").exists()
    assert (lbl_dir / "b.txt").exists()

    # YOLO 格式驗證
    lines = (lbl_dir / "a.txt").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 1
    parts = lines[0].split()
    assert len(parts) == 5  # class_id cx cy w h
    # 所有值都是數字
    for p in parts:
        float(p)


# ─── Test 7：export_csv 欄位正確 ─────────────────────────────────────────────


def test_export_csv_correct_columns(tmp_path):
    import csv

    items = [
        {"item_id": "i1", "file_path": "/img/a.jpg", "width": 640, "height": 480},
    ]
    results = [
        {
            "item_id": "i1",
            "annotation_json": json.dumps(
                {"shapes": [_rect_shape("cat", 10, 20, 100, 80)]}
            ),
            "confidence": 0.95,
            "label": "cat",
        }
    ]
    out_dir = tmp_path / "csv_out"

    csv_path_str = _proc.export_csv(items, results, out_dir)
    csv_path = Path(csv_path_str)

    assert csv_path.exists()

    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    expected_cols = {"item_id", "file_path", "label", "confidence", "x1", "y1", "x2", "y2"}
    assert expected_cols.issubset(set(reader.fieldnames or []))

    assert len(rows) >= 1
    assert rows[0]["item_id"] == "i1"
    assert rows[0]["label"] == "cat"
    assert float(rows[0]["x1"]) == 10.0
    assert float(rows[0]["y2"]) == 80.0


# ─── Test 8：execute_logic — manifest 不存在 ─────────────────────────────────


def test_execute_logic_no_manifest(tmp_path, monkeypatch):
    """manifest_id 不存在 → mode='error'"""
    db = _make_db(tmp_path)

    # monkeypatch get_manifest_db_path to use tmp db
    _cfg_spec = _ilu.spec_from_file_location("module_011._config", _HERE / "_config.py")
    _cfg = _ilu.module_from_spec(_cfg_spec)
    _cfg_spec.loader.exec_module(_cfg)  # type: ignore[union-attr]

    monkeypatch.setattr(_cfg, "get_manifest_db_path", lambda: db)
    # 同步 patch 到 process 模組內使用的 _config 參考
    import sys as _sys
    _sys.modules["module_011._config"] = _cfg

    result = _proc.execute_logic(
        {
            "manifest_id": "nonexistent_manifest_xyz",
            "run_id": "run_abc",
            "export_formats": ["coco_json"],
            "export_dir": str(tmp_path / "exports"),
            "split_train": 70,
            "split_val": 15,
            "split_test": 15,
            "stratified": False,
        }
    )

    assert result["mode"] == "error"
    assert "nonexistent_manifest_xyz" in result.get("error", "")


# ─── Test 9：execute_logic — 無標注仍可匯出 ──────────────────────────────────


def test_execute_logic_empty_annotations(tmp_path, monkeypatch):
    """無標注記錄 → mode='done', annotation_count=0"""
    db = _make_db(tmp_path)
    _insert_manifest(db, manifest_id="m_empty", name="空標注集")
    _insert_items(
        db,
        "m_empty",
        [
            {"item_id": "i1", "file_path": "/img/a.jpg"},
            {"item_id": "i2", "file_path": "/img/b.jpg"},
        ],
    )

    _cfg_spec = _ilu.spec_from_file_location("module_011._config", _HERE / "_config.py")
    _cfg = _ilu.module_from_spec(_cfg_spec)
    _cfg_spec.loader.exec_module(_cfg)  # type: ignore[union-attr]

    monkeypatch.setattr(_cfg, "get_manifest_db_path", lambda: db)
    import sys as _sys
    _sys.modules["module_011._config"] = _cfg

    result = _proc.execute_logic(
        {
            "manifest_id": "m_empty",
            "run_id": "run_empty_001",
            "export_formats": ["coco_json", "csv"],
            "export_dir": str(tmp_path / "exports_empty"),
            "split_train": 70,
            "split_val": 15,
            "split_test": 15,
            "stratified": False,
        }
    )

    assert result["mode"] == "done"
    assert result["annotation_count"] == 0
    assert result["total_items"] == 2
    assert result["error"] is None

    # COCO JSON 應仍被建立
    export_paths = result.get("export_paths", {})
    assert "coco_json" in export_paths
    assert "csv" in export_paths

    # 驗證 COCO train.json 存在
    for split_name, path_str in export_paths["coco_json"].items():
        if path_str:
            assert Path(path_str).exists(), f"{split_name}.json 不存在: {path_str}"
