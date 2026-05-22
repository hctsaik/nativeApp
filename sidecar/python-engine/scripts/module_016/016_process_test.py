from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "shared" / "_manifest_db.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fake_ultralytics(boxes: list[dict] | None = None):
    """
    Build a minimal fake `ultralytics` module.
    boxes: list of {"xyxy": [x1,y1,x2,y2], "cls": cls_id, "conf": score}
    """
    mock_mod = types.ModuleType("ultralytics")

    class _FakeBox:
        def __init__(self, x1, y1, x2, y2, cls_id, conf):
            self.xyxy = [[x1, y1, x2, y2]]
            self.cls = [cls_id]
            self.conf = [conf]

    class _FakeResult:
        def __init__(self, bxs, h, w):
            self.orig_shape = (h, w)
            self.boxes = [_FakeBox(**b) for b in bxs]

    class _FakeYOLO:
        def __init__(self, path):
            self.names = {0: "cat", 1: "dog"}
            self._boxes = boxes or []

        def __call__(self, fp, conf, verbose):
            return [_FakeResult(self._boxes, 480, 640)]

    mock_mod.YOLO = _FakeYOLO
    return mock_mod


# ─── _xany_rect ───────────────────────────────────────────────────────────────

def test_xany_rect_structure():
    proc = _load(_HERE / "016_process.py", "_016_proc_rect")
    r = proc._xany_rect("cat", 10.0, 20.0, 100.0, 80.0, score=0.95)
    assert r["label"] == "cat"
    assert r["shape_type"] == "rectangle"
    assert r["score"] == 0.9500
    assert r["points"] == [[10.0, 20.0], [100.0, 20.0], [100.0, 80.0], [10.0, 80.0]]
    assert r["flags"] == {}


def test_xany_rect_no_score():
    proc = _load(_HERE / "016_process.py", "_016_proc_rect2")
    r = proc._xany_rect("dog", 0, 0, 50, 50)
    assert r["score"] is None


# ─── _write_xany_json ─────────────────────────────────────────────────────────

def test_write_xany_json_shapes(tmp_path):
    proc = _load(_HERE / "016_process.py", "_016_proc_write")
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"img")
    shapes = [proc._xany_rect("cat", 0, 0, 100, 100, 0.9)]
    proc._write_xany_json(str(img), shapes, 640, 480)

    data = json.loads(img.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["imagePath"] == "frame.jpg"
    assert data["imageWidth"] == 640
    assert data["imageHeight"] == 480
    assert len(data["shapes"]) == 1
    assert data["shapes"][0]["label"] == "cat"
    assert data["flags"] == {}


def test_write_xany_json_flags(tmp_path):
    proc = _load(_HERE / "016_process.py", "_016_proc_write2")
    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    proc._write_xany_json(str(img), [], 100, 100,
                          flags={"classification": "dog", "confidence": 0.88})
    data = json.loads(img.with_suffix(".json").read_text(encoding="utf-8"))
    assert data["flags"]["classification"] == "dog"
    assert data["shapes"] == []


# ─── execute_logic 驗證 ───────────────────────────────────────────────────────

def test_execute_logic_error_no_manifest_id(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_016_a")
    proc = _load(_HERE / "016_process.py", "_016_proc_a")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    result = proc.execute_logic({"manifest_id": "", "model_path": "/x.pt"})
    assert result["mode"] == "error"
    assert "Manifest" in result["error"]


def test_execute_logic_error_no_model_path(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_016_b")
    proc = _load(_HERE / "016_process.py", "_016_proc_b")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    result = proc.execute_logic({"manifest_id": "mid", "model_path": ""})
    assert result["mode"] == "error"
    assert "模型" in result["error"]


def test_execute_logic_error_model_file_missing(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_016_c")
    proc = _load(_HERE / "016_process.py", "_016_proc_c")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    result = proc.execute_logic(
        {"manifest_id": "mid", "model_path": str(tmp_path / "nonexistent.pt")}
    )
    assert result["mode"] == "error"


def test_execute_logic_error_manifest_not_found(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    mdb = _load(_SHARED, "_mdb_016_d")
    proc = _load(_HERE / "016_process.py", "_016_proc_d")
    mdb.init_db(cim_log / "db" / "manifest.sqlite")
    fake_model = tmp_path / "model.pt"
    fake_model.write_bytes(b"model")
    result = proc.execute_logic(
        {"manifest_id": "nonexistent", "model_path": str(fake_model)}
    )
    assert result["mode"] == "error"


# ─── _run_yolo ────────────────────────────────────────────────────────────────

def test_run_yolo_no_ultralytics(tmp_path, monkeypatch):
    """ultralytics 未安裝時應回傳 error_detail 而非 crash。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    monkeypatch.setitem(sys.modules, "ultralytics", None)  # type: ignore
    proc = _load(_HERE / "016_process.py", "_016_proc_nopkg")

    result = proc._run_yolo([], model_path="fake.pt", conf=0.25, overwrite=False)
    assert "error_detail" in result
    assert "ultralytics" in result["error_detail"]


def test_run_yolo_skips_existing_annotation(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_ultralytics())
    proc = _load(_HERE / "016_process.py", "_016_proc_yolo_skip")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    img.with_suffix(".json").write_text("{}", encoding="utf-8")  # 已有標注

    result = proc._run_yolo(
        [{"item_id": "i1", "file_path": str(img)}],
        model_path="fake.pt", conf=0.25, overwrite=False,
    )
    assert result["skipped"] == 1
    assert result["ok"] == 0


def test_run_yolo_error_on_missing_file(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_ultralytics())
    proc = _load(_HERE / "016_process.py", "_016_proc_yolo_err")

    result = proc._run_yolo(
        [{"item_id": "i1", "file_path": str(tmp_path / "nonexistent.jpg")}],
        model_path="fake.pt", conf=0.25, overwrite=False,
    )
    assert result["errors"] == 1
    assert result["item_results"][0]["status"] == "error"


def test_run_yolo_writes_annotation(tmp_path, monkeypatch):
    """YOLO 推論結果應寫成 X-AnyLabeling JSON。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_ultralytics(boxes=[
        {"x1": 10.0, "y1": 20.0, "x2": 100.0, "y2": 80.0, "cls_id": 0, "conf": 0.92},
    ]))
    proc = _load(_HERE / "016_process.py", "_016_proc_yolo_write")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")

    result = proc._run_yolo(
        [{"item_id": "i1", "file_path": str(img)}],
        model_path="fake.pt", conf=0.25, overwrite=True,
    )
    assert result["ok"] == 1
    assert result["errors"] == 0

    ann = img.with_suffix(".json")
    assert ann.exists()
    data = json.loads(ann.read_text(encoding="utf-8"))
    assert len(data["shapes"]) == 1
    assert data["shapes"][0]["label"] == "cat"
    assert data["shapes"][0]["shape_type"] == "rectangle"
