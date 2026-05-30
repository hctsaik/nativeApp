from __future__ import annotations

import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

# Load module under test without streamlit dependency
_PROCESS_FILE = Path(__file__).parent / "006_process.py"
_spec = importlib.util.spec_from_file_location("module_006_process", _PROCESS_FILE)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
execute_logic = _mod.execute_logic


# ?? fixtures ??????????????????????????????????????????????????????????????????

@pytest.fixture()
def animal_db(tmp_path: Path) -> tuple[Path, Path]:
    """Create a minimal animal DB + image files for testing."""
    img_dir = tmp_path / "images"
    img_dir.mkdir()

    filenames = ["cat1.jpg", "cat2.jpg", "dog1.jpg"]
    labels    = ["cat", "cat", "dog"]
    colors    = [(200, 100, 80), (80, 200, 100), (100, 80, 200)]
    for fname, label, color in zip(filenames, labels, colors):
        from PIL import ImageDraw
        img = Image.new("RGB", (100, 80), color=color)
        ImageDraw.Draw(img).text((2, 2), fname, fill=(0, 0, 0))
        img.save(img_dir / fname)

    db_path = tmp_path / "animals.db"
    conn = sqlite3.connect(db_path)
    conn.execute("""CREATE TABLE images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT, file_type TEXT, image_time TEXT,
        true_label TEXT, classification TEXT, tagged_at TEXT
    )""")
    for fname, label in zip(filenames, labels):
        conn.execute(
            "INSERT INTO images (filename, file_type, true_label) VALUES (?, ?, ?)",
            (fname, "jpg", label),
        )
    conn.commit()
    conn.close()
    return db_path, img_dir


def _phase1_params(tmp_path: Path, db_path: Path, img_dir: Path, **overrides) -> dict:
    return {
        "mode": "xany_phase1",
        "category": "ALL",
        "labels": ["cat", "dog"],
        "db_path": str(db_path),
        "image_dir": str(img_dir),
        "workspace_root": str(tmp_path / "workspace"),
        "launch_xany": False,
        **overrides,
    }


def _write_labelme_json(labels_dir: Path, image_name: str, label: str) -> None:
    payload = {
        "version": "5.0.1",
        "flags": {"classification_labels": []},
        "shapes": [
            {
                "label": label,
                "shape_type": "rectangle",
                "points": [[10, 10], [80, 60]],
                "flags": {},
                "group_id": None,
                "description": "",
            }
        ],
        "imagePath": image_name,
        "imageData": None,
        "imageHeight": 80,
        "imageWidth": 100,
    }
    labels_dir.mkdir(parents=True, exist_ok=True)
    (labels_dir / image_name.replace(".jpg", ".json")).write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _write_isat_json(labels_dir: Path, image_name: str, label: str) -> None:
    payload = {
        "info": {
            "description": "ISAT",
            "folder": "",
            "name": image_name,
            "width": 100,
            "height": 80,
            "depth": 3,
            "note": "",
        },
        "objects": [
            {
                "category": label,
                "group": 1,
                "segmentation": [[10, 10], [80, 10], [80, 60], [10, 60]],
                "area": 3500,
                "layer": 1.0,
                "bbox": [10, 10, 80, 60],
                "iscrowd": False,
                "note": "",
            }
        ],
    }
    labels_dir.mkdir(parents=True, exist_ok=True)
    (labels_dir / image_name.replace(".jpg", ".json")).write_text(
        json.dumps(payload), encoding="utf-8"
    )


# ?? browse mode tests ?????????????????????????????????????????????????????????

def test_browse_passthrough_with_valid_db(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic({"mode": "browse", "db_path": str(db_path), "image_dir": str(img_dir), "filter": "ALL"})
    assert result.get("error") is None
    assert result["db_path"] == str(db_path)


def test_browse_returns_error_when_db_missing(tmp_path: Path) -> None:
    result = execute_logic({"mode": "browse", "db_path": str(tmp_path / "nope.db"), "filter": "ALL"})
    assert result["error"] == "db_not_found"


# ?? phase 1 tests ?????????????????????????????????????????????????????????????

def test_phase1_creates_xany_project(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, db_path, img_dir))

    assert result["mode"] == "labeling_phase1"
    assert result["legacy_mode"] == "xany_phase1"
    assert result.get("error") is None
    assert result["image_count"] == 3
    xany = Path(result["xany_dir"])
    assert (xany / "manifest.json").exists()
    assert (xany / "classes.txt").exists()
    assert (xany / "images").is_dir()
    assert len(list((xany / "images").glob("*"))) == 3


def test_phase1_classes_txt_contains_labels(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, db_path, img_dir, labels=["cat", "dog", "bird"]))
    classes = set(result["project_files"]["classes_txt"].splitlines())
    assert classes == {"cat", "dog", "bird"}


def test_phase1_category_filter_reduces_images(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, db_path, img_dir, category="cat"))
    assert result["image_count"] == 2  # only cat1.jpg + cat2.jpg


def test_phase1_creates_isat_project(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, db_path, img_dir, annotation_tool="isat"))

    assert result["mode"] == "labeling_phase1"
    assert result["annotation_tool"] == "isat"
    project = Path(result["project_dir"])
    assert (project / "manifest.json").exists()
    assert (project / "categories.txt").exists()
    assert (project / "annotations").is_dir()


def test_phase1_saves_session_json(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, db_path, img_dir))
    session_file = Path(result["workspace_root"]) / "session.json"
    assert session_file.exists()
    session = json.loads(session_file.read_text(encoding="utf-8"))
    assert session["dataset_id"] == result["dataset"]["id"]
    assert session["schema_id"] == result["schema"]["id"]


def test_phase1_returns_error_when_db_missing(tmp_path: Path, animal_db) -> None:
    _, img_dir = animal_db
    result = execute_logic(_phase1_params(tmp_path, Path("nope.db"), img_dir))
    assert result["error"] == "db_not_found"


# ?? phase 2 tests ?????????????????????????????????????????????????????????????

def test_phase2_imports_and_exports(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    # Phase 1
    p1 = execute_logic(_phase1_params(tmp_path, db_path, img_dir))
    xany = Path(p1["xany_dir"])
    labels_dir = xany / "labels"

    image_names = [p.name for p in (xany / "images").glob("*")]
    _write_labelme_json(labels_dir, image_names[0], p1["schema"]["labels"][0]["name"])
    if len(image_names) > 1:
        _write_labelme_json(labels_dir, image_names[1], p1["schema"]["labels"][1]["name"])

    # Phase 2
    p2 = execute_logic({
        "mode": "xany_phase2",
        "workspace_root": p1["workspace_root"],
        "dataset_id": p1["dataset"]["id"],
        "schema_id": p1["schema"]["id"],
        "labels_dir": str(labels_dir),
        "annotation_format": "x-anylabeling",
        "approve": True,
        "export_formats": ["coco", "yolo-detection"],
    })

    assert p2["mode"] == "labeling_phase2"
    assert p2["legacy_mode"] == "xany_phase2"
    assert p2["import_result"]["matched_count"] >= 1
    assert p2["import_result"]["unmatched_files"] == []
    assert p2["validation"]["ok"] is True
    assert p2["annotation_set"]["state"] == "approved"
    assert "coco" in p2["exports"]
    assert "yolo-detection" in p2["exports"]
    coco_path = Path(p2["export_root"]) / "coco" / "annotations.json"
    assert coco_path.exists()


def test_phase2_without_approve_stays_draft(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    p1 = execute_logic(_phase1_params(tmp_path, db_path, img_dir))
    xany = Path(p1["xany_dir"])
    labels_dir = xany / "labels"
    image_names = [p.name for p in (xany / "images").glob("*")]
    _write_labelme_json(labels_dir, image_names[0], p1["schema"]["labels"][0]["name"])

    p2 = execute_logic({
        "mode": "xany_phase2",
        "workspace_root": p1["workspace_root"],
        "dataset_id": p1["dataset"]["id"],
        "schema_id": p1["schema"]["id"],
        "labels_dir": str(labels_dir),
        "approve": False,
        "export_formats": ["coco"],
    })

    assert p2["annotation_set"]["state"] == "draft"
    assert p2["review"] is None


def test_phase2_imports_isat_project_labels(tmp_path: Path, animal_db) -> None:
    db_path, img_dir = animal_db
    p1 = execute_logic(_phase1_params(tmp_path, db_path, img_dir, annotation_tool="isat"))
    project = Path(p1["project_dir"])
    labels_dir = project / "annotations"
    image_names = [p.name for p in (project / "images").glob("*")]
    _write_isat_json(labels_dir, image_names[0], p1["schema"]["labels"][0]["name"])

    p2 = execute_logic({
        "mode": "labeling_phase2",
        "workspace_root": p1["workspace_root"],
        "dataset_id": p1["dataset"]["id"],
        "schema_id": p1["schema"]["id"],
        "labels_dir": str(labels_dir),
        "annotation_format": "isat",
        "approve": True,
        "export_formats": ["isat", "yolo-segmentation"],
    })

    assert p2["mode"] == "labeling_phase2"
    assert p2["annotation_format"] == "isat"
    assert p2["import_result"]["matched_count"] >= 1
    assert "isat" in p2["exports"]
    assert "yolo-segmentation" in p2["exports"]


def test_no_streamlit_import_in_process() -> None:
    src = _PROCESS_FILE.read_text(encoding="utf-8")
    assert "import streamlit" not in src
    assert "from streamlit" not in src
