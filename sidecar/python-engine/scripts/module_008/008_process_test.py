"""
Tests for module_008 process layer.
Run: pytest scripts/module_008/008_process_test.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

# Load process module without Streamlit dependency
_MODULE_DIR = Path(__file__).resolve().parent
if str(_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(_MODULE_DIR))

_spec = importlib.util.spec_from_file_location("_008_process", _MODULE_DIR / "008_process.py")
_proc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_proc)


# ── test helpers ──────────────────────────────────────────────────────────────

def _make_test_video(path: Path, n_frames: int = 10, w: int = 320, h: int = 240, fps: float = 10.0):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    for i in range(n_frames):
        color = int(i * 255 / n_frames)
        frame = np.full((h, w, 3), color, dtype=np.uint8)
        cv2.rectangle(frame, (50 + i * 2, 50), (150 + i * 2, 130), (0, 200, 0), -1)
        out.write(frame)
    out.release()


def _write_dummy_annotation(ann_dir: Path, frame_idx: int, labels: list[str], img_w: int = 320, img_h: int = 240):
    ann_dir.mkdir(parents=True, exist_ok=True)
    shapes = []
    for i, label in enumerate(labels):
        shapes.append({
            "label": label,
            "shape_type": "rectangle",
            "points": [[float(50 + i * 10), 50.0], [float(150 + i * 10), 130.0]],
            "description": f"confidence={0.85 - i * 0.1:.3f}",
            "flags": {},
            "group_id": None,
            "other_data": {},
        })
    data = {
        "version": "6.0.0",
        "imagePath": f"../frames/frame_{frame_idx:06d}.jpg",
        "imageHeight": img_h,
        "imageWidth": img_w,
        "imageData": None,
        "flags": {},
        "shapes": shapes,
    }
    (ann_dir / f"frame_{frame_idx:06d}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ── tests ─────────────────────────────────────────────────────────────────────

def test_load_session_returns_none_when_missing(tmp_path):
    assert _proc.load_session(tmp_path) is None


def test_load_session_reads_json(tmp_path):
    (tmp_path / "session.json").write_text(
        json.dumps({"video_path": "/test/v.mp4", "anchor_frame_idx": 5}), encoding="utf-8"
    )
    s = _proc.load_session(tmp_path)
    assert s["anchor_frame_idx"] == 5


def test_annotations_are_valid_xanylabeling_json(tmp_path):
    ann_dir = tmp_path / "annotations"
    _write_dummy_annotation(ann_dir, 3, ["眼睛", "鼻子"])
    p = ann_dir / "frame_000003.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == "6.0.0"
    assert "shapes" in data
    assert all(s["shape_type"] == "rectangle" for s in data["shapes"])
    assert len(data["shapes"]) == 2


def test_annotations_use_relative_image_path(tmp_path):
    ann_dir = tmp_path / "annotations"
    _write_dummy_annotation(ann_dir, 5, ["眼睛"])
    data = json.loads((ann_dir / "frame_000005.json").read_text(encoding="utf-8"))
    img_path = data["imagePath"]
    assert not img_path.startswith("/"), f"imagePath should be relative, got: {img_path}"
    assert not img_path.startswith("C:"), f"imagePath should be relative, got: {img_path}"


def test_confidence_stored_in_description(tmp_path):
    ann_dir = tmp_path / "annotations"
    _write_dummy_annotation(ann_dir, 2, ["眼睛"])
    data = json.loads((ann_dir / "frame_000002.json").read_text(encoding="utf-8"))
    for shape in data["shapes"]:
        assert "confidence=" in shape.get("description", ""), \
            f"Expected 'confidence=' in description, got: {shape.get('description')}"


def test_save_correction_updates_single_frame(tmp_path):
    (tmp_path / "session.json").write_text(
        json.dumps({"width": 320, "height": 240}), encoding="utf-8"
    )
    ann_dir = tmp_path / "annotations"
    _write_dummy_annotation(ann_dir, 4, ["眼睛"])
    _write_dummy_annotation(ann_dir, 5, ["鼻子"])

    _proc.save_correction(tmp_path, 4, [{"label": "眼睛", "x1": 10.0, "y1": 20.0, "x2": 80.0, "y2": 90.0}])

    corrected = json.loads((ann_dir / "frame_000004.json").read_text(encoding="utf-8"))
    pts = corrected["shapes"][0]["points"]
    assert pts[0][0] == pytest.approx(10.0)

    # Frame 5 must not be touched
    other = json.loads((ann_dir / "frame_000005.json").read_text(encoding="utf-8"))
    assert other["shapes"][0]["label"] == "鼻子"


def test_export_xanylabeling_creates_manifest(tmp_path):
    ann_dir = tmp_path / "annotations"
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for i in range(3):
        _write_dummy_annotation(ann_dir, i, ["眼睛"])
        (frames_dir / f"frame_{i:06d}.jpg").write_bytes(b"fake_jpg")

    result = _proc.export_xanylabeling(tmp_path)

    export_dir = Path(result["export_dir"])
    assert export_dir.exists()
    manifest_path = export_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["annotation_count"] == 3
    assert result["annotation_count"] == 3


def test_export_creates_correct_file_count(tmp_path):
    ann_dir = tmp_path / "annotations"
    frames_dir = tmp_path / "frames"
    frames_dir.mkdir()
    for i in range(5):
        _write_dummy_annotation(ann_dir, i, ["眼睛"])
        (frames_dir / f"frame_{i:06d}.jpg").write_bytes(b"fake")

    result = _proc.export_xanylabeling(tmp_path)
    export_dir = Path(result["export_dir"])
    json_files = list(export_dir.glob("frame_*.json"))
    assert len(json_files) == 5


def test_list_annotated_frames_returns_sorted_indices(tmp_path):
    ann_dir = tmp_path / "annotations"
    for i in [3, 1, 7, 0]:
        _write_dummy_annotation(ann_dir, i, ["眼睛"])

    indices = _proc.list_annotated_frames(tmp_path)
    assert indices == [0, 1, 3, 7]


def test_get_task_status_returns_idle_when_missing(tmp_path):
    status = _proc.get_task_status(tmp_path)
    assert status["state"] == "idle"


def test_no_streamlit_import_in_process():
    source = (_MODULE_DIR / "008_process.py").read_text(encoding="utf-8")
    assert "import streamlit" not in source, "008_process.py must not import streamlit"
    assert "from streamlit" not in source, "008_process.py must not import from streamlit"


def test_execute_logic_returns_error_when_no_bboxes():
    params = {"mode": "tracking", "session_dir": "/tmp/test", "video_path": "/v.mp4", "anchor_bboxes": []}
    result = _proc.execute_logic(params)
    assert result["mode"] == "tracking"
    assert "error" in result


def test_execute_logic_idle_passthrough():
    params = {"mode": "idle", "video_path": ""}
    result = _proc.execute_logic(params)
    assert result["mode"] == "idle"
    assert "error" not in result


def test_execute_logic_starts_propagation(tmp_path):
    (tmp_path / "frames").mkdir()
    params = {
        "mode": "tracking",
        "session_dir": str(tmp_path),
        "video_path": str(tmp_path / "fake.mp4"),
        "anchor_frame_idx": 0,
        "before_sec": 0.0,
        "after_sec": 0.0,
        "anchor_bboxes": [{"label": "眼睛", "x1": 10.0, "y1": 10.0, "x2": 50.0, "y2": 50.0}],
        "meta": {"fps": 10.0, "width": 320, "height": 240, "total_frames": 1},
        "labels": ["眼睛"],
    }
    result = _proc.execute_logic(params)
    assert result["mode"] == "tracking"
    assert "error" not in result
    session_json = tmp_path / "session.json"
    assert session_json.exists()
    data = json.loads(session_json.read_text(encoding="utf-8"))
    assert data["anchor_frame_idx"] == 0
    assert len(data["anchor_bboxes"]) == 1
