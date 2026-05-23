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


def test_run_yolo_item_result_includes_max_conf(tmp_path, monkeypatch):
    """item_results 應包含 max_conf 與 item_id（給 execute_logic 寫回 metadata 用）。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    monkeypatch.setitem(sys.modules, "ultralytics", _fake_ultralytics(boxes=[
        {"x1": 0.0, "y1": 0.0, "x2": 50.0, "y2": 50.0, "cls_id": 1, "conf": 0.75},
    ]))
    proc = _load(_HERE / "016_process.py", "_016_proc_yolo_maxconf")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")

    result = proc._run_yolo(
        [{"item_id": "item-abc", "file_path": str(img)}],
        model_path="fake.pt", conf=0.25, overwrite=True,
    )
    ir = result["item_results"][0]
    assert ir["item_id"] == "item-abc"
    assert ir["max_conf"] == pytest.approx(0.75, abs=1e-3)


# ─── _run_classifier ──────────────────────────────────────────────────────────

def _fake_torch_modules(top_label: str = "cat", top_conf: float = 0.92,
                         num_classes: int = 2) -> dict:
    """Build fake torch / torchvision modules for classifier tests."""
    import types

    # ── torch ──────────────────────────────────────────────────────────────────
    torch_mod = types.ModuleType("torch")

    class _FakeTensor:
        def __init__(self, val):
            self._val = val
        def max(self, _dim):
            return self, self
        def __float__(self):
            return float(self._val)
        def __int__(self):
            return int(self._val)
        def unsqueeze(self, _dim):
            return self

    class _FakeModel:
        def __init__(self):
            self._called = False
        def eval(self):
            return self
        def __call__(self, _x):
            return _FakeTensor(top_conf)
        def load_state_dict(self, _state, strict=True):
            pass
        @property
        def fc(self):
            return self._fc
        @fc.setter
        def fc(self, val):
            self._fc = val

    class _FakeLinear:
        def __init__(self, _in, _out):
            self.in_features = _in

    torch_mod.nn = types.ModuleType("torch.nn")
    torch_mod.nn.Linear = _FakeLinear
    torch_mod.no_grad = lambda: _ctx()

    class _ctx:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def _softmax(tensor, dim):
        class _T:
            def __getitem__(self, _i): return _FakeTensor(top_conf)
        return _T()

    torch_mod.softmax = _softmax

    # state_dict stub
    class _FakeStateDict(dict):
        pass

    def _load(path, map_location=None, weights_only=False):
        sd = _FakeStateDict()
        sd["layer.weight"] = _FakeTensor(0)
        return sd

    torch_mod.load = _load

    # ── torchvision ────────────────────────────────────────────────────────────
    tv_mod = types.ModuleType("torchvision")
    tv_models = types.ModuleType("torchvision.models")

    class _FakeResNet:
        def __init__(self, weights=None):
            self._fc = _FakeLinear(2048, num_classes)
            self.fc = self._fc
        def eval(self): return self
        def __call__(self, _x): return _FakeTensor(top_conf)
        def load_state_dict(self, _s, strict=False): pass

    tv_models.resnet50 = lambda weights=None: _FakeResNet()
    tv_mod.models = tv_models

    tv_transforms = types.ModuleType("torchvision.transforms")

    class _FakeTransform:
        def __call__(self, img): return img
    class _FakeCompose:
        def __init__(self, *a): pass
        def __call__(self, img): return _FakeTensor(0)

    tv_transforms.Compose = _FakeCompose
    tv_transforms.Resize = lambda *a, **kw: _FakeTransform()
    tv_transforms.CenterCrop = lambda *a, **kw: _FakeTransform()
    tv_transforms.ToTensor = lambda: _FakeTransform()
    tv_transforms.Normalize = lambda *a, **kw: _FakeTransform()
    tv_mod.transforms = tv_transforms

    # ── PIL ────────────────────────────────────────────────────────────────────
    pil_mod = types.ModuleType("PIL")
    pil_image = types.ModuleType("PIL.Image")

    class _FakeImg:
        width = 640
        height = 480
        def convert(self, _mode): return self
        def __enter__(self): return self
        def __exit__(self, *a): pass

    pil_image.open = lambda _path: _FakeImg()
    pil_mod.Image = pil_image

    return {
        "torch": torch_mod,
        "torchvision": tv_mod,
        "torchvision.models": tv_models,
        "torchvision.transforms": tv_transforms,
        "PIL": pil_mod,
        "PIL.Image": pil_image,
    }


def test_run_classifier_writes_flags_json(tmp_path, monkeypatch):
    """Classifier 高信心度時應寫 flags.classification 到 .json。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    labels_file = tmp_path / "model.json"
    labels_file.write_text(json.dumps(["cat", "dog"]), encoding="utf-8")
    model_pt = tmp_path / "model.pt"
    model_pt.write_bytes(b"fake")

    for k, v in _fake_torch_modules("cat", top_conf=0.92).items():
        monkeypatch.setitem(sys.modules, k, v)

    proc = _load(_HERE / "016_process.py", "_016_proc_clf_ok")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")

    result = proc._run_classifier(
        [{"item_id": "i1", "file_path": str(img)}],
        model_path=str(model_pt), conf=0.5, overwrite=True, manifest_id="m1",
    )
    assert result["ok"] == 1
    ann = img.with_suffix(".json")
    assert ann.exists()
    data = json.loads(ann.read_text("utf-8"))
    assert data["flags"]["classification"] == "cat"


def test_run_classifier_low_conf_skipped(tmp_path, monkeypatch):
    """信心度低於門檻時 → 不寫 .json，status=low_conf。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    labels_file = tmp_path / "model.json"
    labels_file.write_text(json.dumps(["cat", "dog"]), encoding="utf-8")
    model_pt = tmp_path / "model.pt"
    model_pt.write_bytes(b"fake")

    for k, v in _fake_torch_modules("cat", top_conf=0.3).items():
        monkeypatch.setitem(sys.modules, k, v)

    proc = _load(_HERE / "016_process.py", "_016_proc_clf_lowconf")

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")

    result = proc._run_classifier(
        [{"item_id": "i1", "file_path": str(img)}],
        model_path=str(model_pt), conf=0.5, overwrite=False, manifest_id="m1",
    )
    assert result["ok"] == 0
    assert result["skipped"] == 1
    assert result["item_results"][0]["status"] == "low_conf"
    assert not img.with_suffix(".json").exists()


# ─── execute_logic pre-label snapshot ─────────────────────────────────────────

def test_execute_logic_saves_pre_label_snapshots(tmp_path, monkeypatch):
    """overwrite=True かつ既存 .json → execute_logic が snapshot を保存する。"""
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load(_SHARED, "_mdb_016_snap")
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.init_db(db_path)
    mdb.create_manifest(db_path, "m_snap", "snap test", "folder", {})

    img = tmp_path / "img.jpg"
    img.write_bytes(b"img")
    ann = img.with_suffix(".json")
    ann.write_text('{"shapes":[{"label":"old"}]}', encoding="utf-8")
    mdb.add_manifest_items(db_path, "m_snap", [{"item_id": "i1", "file_path": str(img)}])

    monkeypatch.setitem(sys.modules, "ultralytics", _fake_ultralytics(boxes=[
        {"x1": 0, "y1": 0, "x2": 10, "y2": 10, "cls_id": 0, "conf": 0.9},
    ]))

    fake_model = tmp_path / "model.pt"
    fake_model.write_bytes(b"fake")

    proc = _load(_HERE / "016_process.py", "_016_proc_snap")
    result = proc.execute_logic({
        "manifest_id": "m_snap",
        "model_type": "yolo",
        "model_path": str(fake_model),
        "conf_threshold": 0.25,
        "overwrite_existing": True,
    })
    assert result["mode"] == "done"

    snaps = mdb.get_snapshots(db_path, "m_snap", trigger="pre_label")
    assert len(snaps) == 1
    assert snaps[0]["item_id"] == "i1"
    snap_data = json.loads(snaps[0]["label_json"])
    assert snap_data["shapes"][0]["label"] == "old"
