"""
pytest tests for module_009 process layer.
Run: pytest scripts/module_009/009_process_test.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import _db as db


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_db(tmp_path):
    db_path = tmp_path / "test_annotation.sqlite"
    db.init_db(db_path)
    return db_path


@pytest.fixture
def tmp_folder(tmp_path):
    folder = tmp_path / "media"
    folder.mkdir()
    return folder


def _insert_asset(db_path: Path, file_path: str, asset_type: str = "video") -> tuple[int, int]:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """INSERT INTO video_assets (file_path, asset_type, display_name, total_frames)
               VALUES (?, ?, ?, ?)""",
            (file_path, asset_type, Path(file_path).name, 100),
        )
        asset_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute("INSERT INTO annotation_sessions (asset_id) VALUES (?)", (asset_id,))
        session_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    return asset_id, session_id


# ── scan_folder tests ──────────────────────────────────────────────────────────

def test_scan_folder_finds_videos_and_images(tmp_db, tmp_folder):
    (tmp_folder / "video.mp4").write_bytes(b"\x00" * 8)
    img_dir = tmp_folder / "images"
    img_dir.mkdir()
    (img_dir / "frame.jpg").write_bytes(b"\xff\xd8\xff")  # JPEG magic

    with patch("cv2.VideoCapture") as mock_cap:
        instance = MagicMock()
        instance.isOpened.return_value = True
        instance.get.side_effect = lambda prop: {1: 30.0, 7: 90, 3: 640, 4: 480}.get(prop, 0)
        mock_cap.return_value = instance

        results = db.scan_folder(tmp_db, str(tmp_folder))

    types = {r["asset_type"] for r in results}
    assert "video" in types
    assert "image_dir" in types


def test_scan_folder_skips_existing_assets(tmp_db, tmp_folder):
    (tmp_folder / "clip.mp4").write_bytes(b"\x00" * 8)

    with patch("cv2.VideoCapture") as mock_cap:
        instance = MagicMock()
        instance.isOpened.return_value = True
        instance.get.side_effect = lambda prop: {1: 30.0, 7: 60, 3: 1280, 4: 720}.get(prop, 0)
        mock_cap.return_value = instance

        first = db.scan_folder(tmp_db, str(tmp_folder))
        second = db.scan_folder(tmp_db, str(tmp_folder))

    # Total DB rows should not double
    with sqlite3.connect(str(tmp_db)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM video_assets").fetchone()[0]
    assert count == len(first)
    assert len(second) == len(first)


# ── load_assets tests ──────────────────────────────────────────────────────────

def test_load_assets_returns_correct_status(tmp_db):
    _insert_asset(tmp_db, "/fake/a.mp4")
    _insert_asset(tmp_db, "/fake/b.mp4")

    assets = db.load_assets(tmp_db)
    assert len(assets) == 2
    for a in assets:
        assert a["status"] == "未標記"
        assert "session_id" in a
        assert "asset_id" in a


# ── acquire / release lock tests ───────────────────────────────────────────────

def test_acquire_lock_prevents_duplicate(tmp_db):
    _, sid = _insert_asset(tmp_db, "/fake/v.mp4")

    with patch("psutil.pid_exists", return_value=True):
        ok1 = db.acquire_lock(tmp_db, sid, 9999)
        ok2 = db.acquire_lock(tmp_db, sid, 8888)

    assert ok1 is True
    assert ok2 is False  # 9999 is "still alive"


def test_acquire_lock_releases_dead_pid(tmp_db):
    _, sid = _insert_asset(tmp_db, "/fake/v2.mp4")

    with patch("psutil.pid_exists", return_value=True):
        db.acquire_lock(tmp_db, sid, 9999)

    with patch("psutil.pid_exists", return_value=False):
        ok = db.acquire_lock(tmp_db, sid, 8888)

    assert ok is True  # dead PID was auto-released


# ── generate_summary tests ─────────────────────────────────────────────────────

def test_generate_summary_counts_frames_and_objects(tmp_db):
    _, sid = _insert_asset(tmp_db, "/fake/s.mp4")

    for fidx in range(3):
        shapes = [
            {"label": "眼睛", "shape_type": "rectangle",
             "points": [[0, 0], [10, 10]], "description": "confidence=0.90", "flags": {}, "group_id": None, "other_data": {}},
        ]
        ann_json = json.dumps({"version": "6.0.0", "shapes": shapes, "imagePath": f"../frames/frame_{fidx:06d}.jpg",
                               "imageHeight": 720, "imageWidth": 1280, "imageData": None, "flags": {}})
        db.upsert_frame_annotation(tmp_db, sid, fidx, ann_json, 0.90, "tracking")

    summary = db.generate_summary(tmp_db, sid)
    assert summary["frame_count"] == 3
    assert summary["object_counts"].get("眼睛") == 3
    assert abs(summary["avg_confidence"] - 0.90) < 0.01


# ── get_next_unannotated tests ─────────────────────────────────────────────────

def test_get_next_unannotated_returns_first_untagged(tmp_db):
    _, sid1 = _insert_asset(tmp_db, "/fake/first.mp4")
    _, sid2 = _insert_asset(tmp_db, "/fake/second.mp4")

    db.update_session(tmp_db, sid1, status="已標記")

    next_sid = db.get_next_unannotated(tmp_db)
    assert next_sid == sid2


def test_get_next_unannotated_returns_none_when_all_done(tmp_db):
    _, sid = _insert_asset(tmp_db, "/fake/done.mp4")
    db.update_session(tmp_db, sid, status="已標記")

    assert db.get_next_unannotated(tmp_db) is None


# ── upsert / frame_annotation tests ───────────────────────────────────────────

def test_update_after_xany_close_upserts_frames(tmp_db, tmp_path):
    _, sid = _insert_asset(tmp_db, "/fake/xany.mp4")
    xany_dir = tmp_path / "sessions" / "session_0001"
    ann_dir = xany_dir / "annotations"
    ann_dir.mkdir(parents=True)

    shapes = [{"label": "鼻子", "shape_type": "rectangle",
               "points": [[5, 5], [15, 15]], "description": "confidence=0.75",
               "flags": {}, "group_id": None, "other_data": {}}]
    ann_data = {"version": "6.0.0", "shapes": shapes, "imagePath": "../frames/frame_000000.jpg",
                "imageHeight": 480, "imageWidth": 640, "imageData": None, "flags": {}}
    (ann_dir / "frame_000000.json").write_text(json.dumps(ann_data), encoding="utf-8")

    db.update_session(tmp_db, sid, xany_project_dir=str(xany_dir))

    sys.path.insert(0, str(_HERE))
    import _xany_launcher as launcher
    result = launcher.update_after_xany_close(tmp_db, sid)

    assert result["ok"] is True
    assert result["frames_upserted"] == 1

    frames = db.get_frame_annotations(tmp_db, sid)
    assert len(frames) == 1
    assert frames[0]["source"] == "xanylabeling"


# ── sync_to_db tests ───────────────────────────────────────────────────────────

def test_sync_to_db_moves_temp_to_backup(tmp_db, tmp_path):
    _, sid = _insert_asset(tmp_db, "/fake/sync.mp4")
    xany_dir = tmp_path / "sessions" / "session_sync"
    xany_dir.mkdir(parents=True)
    (xany_dir / "dummy.txt").write_text("test")

    db.update_session(tmp_db, sid, status="已標記", xany_project_dir=str(xany_dir))

    sys.path.insert(0, str(_HERE))
    import _xany_launcher as launcher
    result = launcher.sync_to_db(tmp_db, [sid])

    assert sid in result["synced_session_ids"]
    backup = xany_dir.parent / "backup" / xany_dir.name
    assert backup.exists()

    session = db.get_session_status(tmp_db, sid)
    assert session["status"] == "已同步"


# ── no Streamlit import guard ──────────────────────────────────────────────────

def test_no_streamlit_import_in_process():
    process_src = (_HERE / "009_process.py").read_text(encoding="utf-8")
    assert "import streamlit" not in process_src
    assert "from streamlit" not in process_src


# ── _worker output format tests ────────────────────────────────────────────────

def test_worker_outputs_xanylabeling_json_format(tmp_db, tmp_path):
    _, sid = _insert_asset(tmp_db, "/fake/worker_video.mp4")
    xany_dir = tmp_path / "session_w"
    ann_dir = xany_dir / "annotations"
    ann_dir.mkdir(parents=True)

    ann_json = json.dumps({
        "version": "6.0.0",
        "imagePath": "../frames/frame_000000.jpg",
        "imageHeight": 480,
        "imageWidth": 640,
        "imageData": None,
        "flags": {},
        "shapes": [
            {"label": "眼睛", "shape_type": "rectangle",
             "points": [[10.0, 10.0], [50.0, 50.0]],
             "description": "confidence=0.85",
             "flags": {}, "group_id": None, "other_data": {}}
        ],
    })
    db.upsert_frame_annotation(tmp_db, sid, 0, ann_json, 0.85, "tracking")

    frames = db.get_frame_annotations(tmp_db, sid)
    assert len(frames) == 1
    data = json.loads(frames[0]["annotation_json"])
    assert data["version"] == "6.0.0"
    assert data["shapes"][0]["shape_type"] == "rectangle"
    assert "confidence=" in data["shapes"][0]["description"]


def test_frame_annotation_source_accepts_labelme_and_isat(tmp_db):
    _, sid = _insert_asset(tmp_db, "/fake/source.mp4")
    ann_json = json.dumps({"version": "6.0.0", "shapes": [], "imagePath": "frame.jpg"})

    db.upsert_frame_annotation(tmp_db, sid, 0, ann_json, None, "labelme")
    db.upsert_frame_annotation(tmp_db, sid, 1, ann_json, None, "isat")

    sources = {row["source"] for row in db.get_frame_annotations(tmp_db, sid)}
    assert {"labelme", "isat"} <= sources


def test_worker_flow_only_when_dino_unavailable(tmp_db, tmp_path):
    from _worker import DINO_AVAILABLE, _optical_flow_track
    import numpy as np

    src = np.zeros((480, 640, 3), dtype=np.uint8)
    tgt = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw something to track
    src[100:150, 100:150] = 255
    tgt[102:152, 103:153] = 255

    bbox, conf = _optical_flow_track(src, (100, 100, 150, 150), tgt, 640, 480)
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0


def test_single_frame_correction_does_not_affect_other_frames(tmp_db, tmp_path):
    _, sid = _insert_asset(tmp_db, "/fake/correction.mp4")
    xany_dir = tmp_path / "session_c"
    db.update_session(tmp_db, sid, xany_project_dir=str(xany_dir))

    for fidx in [0, 1, 2]:
        shapes = [{"label": "眼睛", "shape_type": "rectangle",
                   "points": [[0, 0], [10, 10]], "description": "confidence=0.80",
                   "flags": {}, "group_id": None, "other_data": {}}]
        ann = json.dumps({"version": "6.0.0", "shapes": shapes,
                          "imagePath": f"../frames/frame_{fidx:06d}.jpg",
                          "imageHeight": 480, "imageWidth": 640, "imageData": None, "flags": {}})
        db.upsert_frame_annotation(tmp_db, sid, fidx, ann, 0.80, "tracking")

    # Simulate single-frame correction on frame 1
    single_dir = xany_dir / "single_frame_correction"
    single_dir.mkdir(parents=True)
    corrected_shapes = [{"label": "嘴巴", "shape_type": "rectangle",
                         "points": [[20, 20], [30, 30]], "description": "confidence=1.000",
                         "flags": {}, "group_id": None, "other_data": {}}]
    corrected_ann = json.dumps({"version": "6.0.0", "shapes": corrected_shapes,
                                "imagePath": "../frames/frame_000001.jpg",
                                "imageHeight": 480, "imageWidth": 640, "imageData": None, "flags": {}})
    (single_dir / "frame_000001.json").write_text(corrected_ann, encoding="utf-8")

    sys.path.insert(0, str(_HERE))
    import _xany_launcher as launcher
    result = launcher.update_after_single_close(tmp_db, sid, 1, single_dir)
    assert result["ok"] is True

    frames = {r["frame_idx"]: json.loads(r["annotation_json"]) for r in db.get_frame_annotations(tmp_db, sid)}
    assert frames[1]["shapes"][0]["label"] == "嘴巴"
    assert frames[0]["shapes"][0]["label"] == "眼睛"
    assert frames[2]["shapes"][0]["label"] == "眼睛"
