from __future__ import annotations

"""
Tests for 013_process.py — Sync Back to Service
"""

import importlib.util
import io
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch


_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _setup_manifest(tmp_path, monkeypatch, manifest_id: str, items: list[dict]) -> tuple:
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load_module(_SHARED, f"_mdb_{manifest_id}")
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.create_manifest(db_path, manifest_id, "test manifest", "folder",
                        {"folder_path": str(tmp_path / "src"), "recursive": False})
    mdb.add_manifest_items(db_path, manifest_id, items)
    return cim_log, db_path


def test_chunk_splitting(tmp_path, monkeypatch):
    """101 items → 2 chunks（第一個 100，第二個 1）。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    src = tmp_path / "src"
    src.mkdir(parents=True)

    items_data = [
        {"item_id": f"item_{i:03d}", "file_path": str(src / f"img_{i:03d}.jpg"),
         "width": 100, "height": 100, "file_hash": "x", "metadata": {}}
        for i in range(101)
    ]
    _setup_manifest(tmp_path, monkeypatch, "mchunk", items_data)

    proc = _load_module(_HERE / "013_process.py", "_013_proc_chunk")

    posted_payloads = []

    def mock_post_json(url, payload, timeout=30):
        posted_payloads.append(payload)
        return {"ok": True}

    proc._post_json = mock_post_json

    result = proc.execute_logic({
        "manifest_id": "mchunk",
        "dataset_id": "ds-1",
        "service_url": "http://mock-service",
        "scope": "full",
        "export_format": "none",
    })

    assert len(posted_payloads) == 2
    assert posted_payloads[0]["chunk_index"] == 0
    assert posted_payloads[0]["total_chunks"] == 2
    assert len(posted_payloads[0]["items"]) == 100
    assert len(posted_payloads[1]["items"]) == 1
    assert result["ok_count"] == 101
    assert result["failed_count"] == 0


def test_scope_partial(tmp_path, monkeypatch):
    """scope=partial 只送有標注/分類的 items。"""
    src = tmp_path / "src"
    src.mkdir(parents=True)

    img1 = src / "img_001.jpg"
    img2 = src / "img_002.jpg"
    img1.write_bytes(b"fake")
    img2.write_bytes(b"fake")
    ann1 = src / "img_001.json"
    ann1.write_text(json.dumps({
        "shapes": [{"label": "cat", "shape_type": "rectangle",
                    "points": [[0, 0], [10, 10]]}]
    }), encoding="utf-8")

    cim_log, _ = _setup_manifest(tmp_path, monkeypatch, "mpartial", [
        {"item_id": "i1", "file_path": str(img1), "width": 100, "height": 100, "file_hash": "x", "metadata": {}},
        {"item_id": "i2", "file_path": str(img2), "width": 100, "height": 100, "file_hash": "x", "metadata": {}},
    ])

    proc = _load_module(_HERE / "013_process.py", "_013_proc_partial")

    sent_items = []

    def mock_post(url, payload, timeout=30):
        sent_items.extend(payload["items"])
        return {"ok": True}

    proc._post_json = mock_post

    result = proc.execute_logic({
        "manifest_id": "mpartial",
        "dataset_id": "ds-1",
        "service_url": "http://mock",
        "scope": "partial",
        "export_format": "none",
    })

    assert result["scope_count"] == 1
    assert sent_items[0]["item_id"] == "i1"


def test_validation_blocks_on_invalid_bbox(tmp_path, monkeypatch):
    """bbox 面積 ≤ 0 → validation_error，不送出。"""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    img = src / "bad.jpg"
    img.write_bytes(b"fake")
    ann = src / "bad.json"
    ann.write_text(json.dumps({
        "shapes": [{"label": "x", "shape_type": "rectangle",
                    "points": [[5, 5], [5, 5]]}]  # zero area
    }), encoding="utf-8")

    _setup_manifest(tmp_path, monkeypatch, "mval", [
        {"item_id": "bad", "file_path": str(img), "width": 100, "height": 100, "file_hash": "x", "metadata": {}}
    ])
    proc = _load_module(_HERE / "013_process.py", "_013_proc_val")

    called = []
    proc._post_json = lambda *a, **kw: called.append(1) or {}

    result = proc.execute_logic({
        "manifest_id": "mval",
        "dataset_id": "ds-1",
        "service_url": "http://mock",
        "scope": "full",
        "export_format": "none",
    })

    assert result["mode"] == "validation_error"
    assert not called


def test_coco_zip_structure(tmp_path, monkeypatch):
    """_build_coco_zip 產生的 zip 包含 annotations.json 且可正確讀取。"""
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load_module(_HERE / "013_process.py", "_013_proc_zip")

    items = [{"item_id": "i1", "file_path": "/data/img1.jpg", "width": 640, "height": 480}]
    shapes_map = {
        "i1": [{"label": "cat", "shape_type": "rectangle",
                "x1": 0.0, "y1": 0.0, "x2": 10.0, "y2": 10.0, "polygon_pts": []}]
    }

    zip_bytes = proc._build_coco_zip(items, shapes_map)
    assert zip_bytes

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "annotations.json" in names
        coco = json.loads(zf.read("annotations.json").decode("utf-8"))
        assert len(coco["images"]) == 1
        assert len(coco["annotations"]) == 1
        assert coco["categories"][0]["name"] == "cat"


def test_yolo_zip_structure(tmp_path, monkeypatch):
    """_build_yolo_zip 產生的 zip 包含 classes.txt + data.yaml + labels/。"""
    monkeypatch.setenv("CIM_LOG_DIR", str(tmp_path / "cim_log"))
    proc = _load_module(_HERE / "013_process.py", "_013_proc_yolo_zip")

    items = [{"item_id": "i1", "file_path": "/data/img1.jpg", "width": 640, "height": 480}]
    shapes_map = {
        "i1": [{"label": "dog", "shape_type": "rectangle",
                "x1": 0.0, "y1": 0.0, "x2": 64.0, "y2": 48.0, "polygon_pts": []}]
    }

    zip_bytes = proc._build_yolo_zip(items, shapes_map)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert "classes.txt" in names
        assert "data.yaml" in names
        assert any(n.startswith("labels/") for n in names)


def test_partial_chunk_failure_written_to_history(tmp_path, monkeypatch):
    """第一個 chunk 成功、第二個失敗 → mode=partial_fail，歷史記錄 status=partial_fail。"""
    src = tmp_path / "src"
    src.mkdir(parents=True)
    items_data = [
        {"item_id": f"it_{i}", "file_path": str(src / f"img_{i}.jpg"),
         "width": 10, "height": 10, "file_hash": "x", "metadata": {}}
        for i in range(150)
    ]
    cim_log, _ = _setup_manifest(tmp_path, monkeypatch, "mhist", items_data)

    proc = _load_module(_HERE / "013_process.py", "_013_proc_hist")
    call_count = [0]

    def mock_post(url, payload, timeout=30):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("network error")
        return {"ok": True}

    proc._post_json = mock_post

    result = proc.execute_logic({
        "manifest_id": "mhist",
        "dataset_id": "ds-x",
        "service_url": "http://mock",
        "scope": "full",
        "export_format": "none",
    })

    assert result["mode"] == "partial_fail"
    assert result["ok_count"] == 100
    assert result["failed_count"] == 50

    cfg = _load_module(_HERE / "_config.py", "_013_cfg_hist")
    hist = cfg.read_sync_history("mhist")
    assert hist[-1]["status"] == "partial_fail"
