from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parents[3] / "scripts" / "shared" / "_manifest_db.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_execute_logic_detects_same_directory_xanylabeling_json(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load_module(_SHARED, "_manifest_db_for_012_test")
    proc = _load_module(_HERE / "012_process.py", "_012_process_for_test")

    img = source_dir / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")
    img.with_suffix(".json").write_text(
        json.dumps(
            {
                "imagePath": img.name,
                "shapes": [{"label": "defect", "points": [[1, 2], [3, 4]]}],
            }
        ),
        encoding="utf-8",
    )

    manifest_id = "manifest_012"
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.create_manifest(
        db_path,
        manifest_id,
        "test manifest",
        "folder",
        {"folder_path": str(source_dir), "recursive": False},
    )
    mdb.add_manifest_items(
        db_path,
        manifest_id,
        [
            {
                "item_id": "item_001",
                "file_path": str(img),
                "width": 10,
                "height": 10,
                "file_hash": "hash",
                "metadata": {},
            }
        ],
    )

    result = proc.execute_logic(
        {
            "manifest_id": manifest_id,
            "annotation_tool": "labelme",
            "labels": ["defect"],
            "classification_labels": ["A"],
            "autorefresh_enabled": False,
            "autorefresh_seconds": 45,
        }
    )

    assert result["mode"] == "ready"
    assert result["annotation_tool"] == "labelme"
    assert result["autorefresh_enabled"] is False
    assert result["autorefresh_seconds"] == 45
    assert result["annotated"] == 1
    assert result["items"][0]["has_ann"] is True
    assert result["items"][0]["ann_path"] == str(img.with_suffix(".json"))
    assert result["items"][0]["shape_count"] == 1


def test_execute_logic_defaults_autorefresh_to_10_seconds(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load_module(_SHARED, "_manifest_db_for_012_default_refresh_test")
    proc = _load_module(_HERE / "012_process.py", "_012_process_for_default_refresh_test")

    img = source_dir / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")

    manifest_id = "manifest_default_refresh"
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.create_manifest(
        db_path,
        manifest_id,
        "test manifest",
        "folder",
        {"folder_path": str(source_dir), "recursive": False},
    )
    mdb.add_manifest_items(
        db_path,
        manifest_id,
        [
            {
                "item_id": "item_001",
                "file_path": str(img),
                "width": 10,
                "height": 10,
                "file_hash": "hash",
                "metadata": {},
            }
        ],
    )

    result = proc.execute_logic(
        {
            "manifest_id": manifest_id,
            "labels": ["defect"],
            "classification_labels": [],
        }
    )

    assert result["mode"] == "ready"
    assert result["annotation_tool"] == "x-anylabeling"
    assert result["autorefresh_enabled"] is True
    assert result["autorefresh_seconds"] == 10


def test_execute_logic_detects_labelme_exe_from_env(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    labelme_exe = tmp_path / "labelme.exe"
    labelme_exe.write_bytes(b"fake exe")
    monkeypatch.setenv("LABELME_EXE", str(labelme_exe))

    mdb = _load_module(_SHARED, "_manifest_db_for_012_labelme_test")
    proc = _load_module(_HERE / "012_process.py", "_012_process_for_labelme_test")

    img = source_dir / "frame_000001.jpg"
    img.write_bytes(b"fake image bytes")

    manifest_id = "manifest_labelme"
    db_path = cim_log / "db" / "manifest.sqlite"
    mdb.create_manifest(
        db_path,
        manifest_id,
        "test manifest",
        "folder",
        {"folder_path": str(source_dir), "recursive": False},
    )
    mdb.add_manifest_items(
        db_path,
        manifest_id,
        [
            {
                "item_id": "item_001",
                "file_path": str(img),
                "width": 10,
                "height": 10,
                "file_hash": "hash",
                "metadata": {},
            }
        ],
    )

    result = proc.execute_logic(
        {
            "manifest_id": manifest_id,
            "annotation_tool": "labelme",
            "labels": ["defect"],
            "classification_labels": [],
        }
    )

    assert result["mode"] == "ready"
    assert result["annotation_tool"] == "labelme"
    assert result["labelme_exe"] == str(labelme_exe)
