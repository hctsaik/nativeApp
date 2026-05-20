from __future__ import annotations

import importlib.util
import json
from pathlib import Path


_HERE = Path(__file__).resolve().parent
_SHARED = _HERE.parent / "shared" / "_manifest_db.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_execute_logic_writes_update_result_to_source_folder_and_confirms_same_json(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load_module(_SHARED, "_manifest_db_for_013_test")
    proc = _load_module(_HERE / "013_process.py", "_013_process_for_test")

    img = source_dir / "image_001.jpg"
    img.write_bytes(b"fake image bytes")
    ann = source_dir / "image_001.json"
    ann.write_text(
        json.dumps({"shapes": [{"label": "defect", "points": [[1, 2], [3, 4]]}]}),
        encoding="utf-8",
    )

    manifest_id = "manifest_001"
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
            "export_dir": str(tmp_path / "export"),
            "copy_annotations": True,
            "organize_images": False,
            "dry_run": False,
        }
    )

    assert result["mode"] == "done"
    assert result["summary"]["b_copied"] == 1
    assert result["summary"]["errors"] == 0
    assert result["source_folder"] == str(source_dir)

    output_path = Path(result["output_json_path"])
    assert output_path.parent == source_dir
    assert output_path.name.startswith("update_result_")


def test_infer_source_folder_normalizes_file_source_path(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))
    proc = _load_module(_HERE / "013_process.py", "_013_process_for_source_path_test")

    img = tmp_path / "source" / "one.jpg"
    img.parent.mkdir()
    img.write_bytes(b"fake")

    assert proc._infer_source_folder({"source_path": str(img)}, []) == str(img.parent)


def test_execute_logic_reads_manifest_scoped_classification_config(tmp_path, monkeypatch):
    cim_log = tmp_path / "cim_log"
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    monkeypatch.setenv("CIM_LOG_DIR", str(cim_log))

    mdb = _load_module(_SHARED, "_manifest_db_for_013_classification_test")
    proc = _load_module(_HERE / "013_process.py", "_013_process_for_classification_test")

    img = source_dir / "image_001.jpg"
    img.write_bytes(b"fake image bytes")

    manifest_id = "manifest_classification"
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

    classification_path = cim_log / "config" / f"module_012_classifications_{manifest_id[:12]}.json"
    classification_path.parent.mkdir(parents=True)
    classification_path.write_text(json.dumps({"item_001": "A"}), encoding="utf-8")

    result = proc.execute_logic(
        {
            "manifest_id": manifest_id,
            "copy_annotations": False,
            "organize_images": True,
            "dry_run": True,
        }
    )

    assert result["mode"] == "preview"
    assert result["items"][0]["classification"] == "A"
    assert result["items"][0]["c_action"] == "copy"
    assert "exports" in result["export_dir"]
