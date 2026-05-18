from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from animal_tagger_output import (
    ANNOTATION_LABELS,
    _ann_path,
    _load_annotations,
    _next_untagged_index,
    _query_records,
    _render_annotated_preview,
    _save_annotations,
    _update_tag,
)


# ---------------------------------------------------------------------------
# Fixture: fresh in-memory-style SQLite DB (tmp_path)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> str:
    path = str(tmp_path / "animals.db")
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            file_type TEXT NOT NULL,
            image_time TEXT NOT NULL,
            true_label TEXT NOT NULL,
            classification TEXT,
            tagged_at TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO images (filename, file_type, image_time, true_label) VALUES (?, ?, ?, ?)",
        [
            ("c1.jpg", "JPG", "2026-01-01 00:00:00", "貓"),
            ("c2.jpg", "JPG", "2026-01-01 00:00:01", "貓"),
            ("d1.jpg", "JPG", "2026-01-01 00:00:02", "狗"),
            ("d2.jpg", "JPG", "2026-01-01 00:00:03", "狗"),
            ("e1.jpg", "JPG", "2026-01-01 00:00:04", "大象"),
        ],
    )
    conn.commit()
    conn.close()
    return path


# ---------------------------------------------------------------------------
# _query_records
# ---------------------------------------------------------------------------

class TestQueryRecords:
    def test_all_returns_every_record(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        assert len(records) == 5

    def test_cat_filter_returns_only_cats(self, db_path: str) -> None:
        records = _query_records(db_path, "貓")
        assert len(records) == 2
        assert all(r["true_label"] == "貓" for r in records)

    def test_dog_filter_returns_only_dogs(self, db_path: str) -> None:
        records = _query_records(db_path, "狗")
        assert len(records) == 2
        assert all(r["true_label"] == "狗" for r in records)

    def test_elephant_filter_returns_only_elephants(self, db_path: str) -> None:
        records = _query_records(db_path, "大象")
        assert len(records) == 1
        assert records[0]["true_label"] == "大象"

    def test_unknown_filter_returns_empty(self, db_path: str) -> None:
        records = _query_records(db_path, "兔子")
        assert records == []

    def test_record_has_expected_keys(self, db_path: str) -> None:
        record = _query_records(db_path, "ALL")[0]
        for key in ("id", "filename", "file_type", "image_time", "true_label", "classification", "tagged_at"):
            assert key in record

    def test_untagged_records_have_none_classification(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        assert all(r["classification"] is None for r in records)

    def test_results_ordered_by_id(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        ids = [r["id"] for r in records]
        assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# _update_tag
# ---------------------------------------------------------------------------

class TestUpdateTag:
    def test_sets_classification(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        record_id = records[0]["id"]
        _update_tag(db_path, record_id, "貓")
        updated = _query_records(db_path, "ALL")
        assert updated[0]["classification"] == "貓"

    def test_sets_tagged_at_timestamp(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        record_id = records[0]["id"]
        _update_tag(db_path, record_id, "狗")
        updated = _query_records(db_path, "ALL")
        assert updated[0]["tagged_at"] is not None

    def test_tagged_at_format(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        _update_tag(db_path, records[0]["id"], "大象")
        updated = _query_records(db_path, "ALL")
        ts = updated[0]["tagged_at"]
        # Expect "YYYY-MM-DD HH:MM:SS"
        import re
        assert re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", ts)

    def test_overwrite_existing_tag(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        rid = records[0]["id"]
        _update_tag(db_path, rid, "貓")
        _update_tag(db_path, rid, "unknown")
        updated = _query_records(db_path, "ALL")
        assert updated[0]["classification"] == "unknown"

    def test_only_target_record_updated(self, db_path: str) -> None:
        records = _query_records(db_path, "ALL")
        _update_tag(db_path, records[0]["id"], "貓")
        updated = _query_records(db_path, "ALL")
        assert all(r["classification"] is None for r in updated[1:])


# ---------------------------------------------------------------------------
# _next_untagged_index
# ---------------------------------------------------------------------------

class TestNextUntaggedIndex:
    def _make_records(self, classifications: list) -> list[dict]:
        return [{"id": i, "classification": c} for i, c in enumerate(classifications)]

    def test_finds_next_untagged_after_current(self) -> None:
        records = self._make_records([None, None, None])
        assert _next_untagged_index(records, 0) == 1

    def test_wraps_around_to_beginning(self) -> None:
        # All tagged except index 0; current is 2 → should wrap to 0
        records = self._make_records(["貓", None, "狗"])
        assert _next_untagged_index(records, 2) == 1

    def test_skips_already_tagged(self) -> None:
        records = self._make_records([None, "貓", None])
        assert _next_untagged_index(records, 0) == 2

    def test_all_tagged_advances_by_one(self) -> None:
        records = self._make_records(["貓", "狗", "大象"])
        assert _next_untagged_index(records, 1) == 2

    def test_all_tagged_wraps_on_last(self) -> None:
        records = self._make_records(["貓", "狗", "大象"])
        assert _next_untagged_index(records, 2) == 0

    def test_single_record_stays_at_zero(self) -> None:
        records = self._make_records(["貓"])
        assert _next_untagged_index(records, 0) == 0


# ---------------------------------------------------------------------------
# Annotation helpers: _ann_path, _save_annotations, _load_annotations
# ---------------------------------------------------------------------------

@pytest.fixture()
def image_dir(tmp_path: Path) -> Path:
    """Create a minimal test image in a temp directory."""
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    img[10:40, 5:35] = (120, 80, 200)
    cv2.imwrite(str(tmp_path / "cat1.jpg"), img)
    return tmp_path


class TestAnnPath:
    def test_returns_json_sibling(self, image_dir: Path) -> None:
        p = _ann_path(image_dir, "cat1.jpg")
        assert p == image_dir / "cat1_annotations.json"

    def test_stem_without_extension(self, image_dir: Path) -> None:
        p = _ann_path(image_dir, "dog.png")
        assert p.name == "dog_annotations.json"


class TestSaveAnnotations:
    def test_creates_file(self, image_dir: Path) -> None:
        _save_annotations(image_dir, "cat1.jpg", [[5, 5, 20, 20]], [0])
        assert _ann_path(image_dir, "cat1.jpg").exists()

    def test_content_matches_input(self, image_dir: Path) -> None:
        bboxes = [[1, 2, 30, 40], [50, 5, 10, 10]]
        labels = [0, 2]
        _save_annotations(image_dir, "cat1.jpg", bboxes, labels)
        data = json.loads(_ann_path(image_dir, "cat1.jpg").read_text(encoding="utf-8"))
        assert data["bboxes"] == bboxes
        assert data["labels"] == labels
        assert data["label_list"] == ANNOTATION_LABELS
        assert "updated_at" in data

    def test_overwrite_clears_previous(self, image_dir: Path) -> None:
        _save_annotations(image_dir, "cat1.jpg", [[1, 1, 10, 10]], [0])
        _save_annotations(image_dir, "cat1.jpg", [], [])
        data = json.loads(_ann_path(image_dir, "cat1.jpg").read_text(encoding="utf-8"))
        assert data["bboxes"] == []
        assert data["labels"] == []

    def test_returns_path(self, image_dir: Path) -> None:
        p = _save_annotations(image_dir, "cat1.jpg", [], [])
        assert isinstance(p, Path)
        assert p.exists()


class TestLoadAnnotations:
    def test_returns_empty_when_no_file(self, image_dir: Path) -> None:
        data = _load_annotations(image_dir, "nofile.jpg")
        assert data == {"bboxes": [], "labels": [], "label_list": ANNOTATION_LABELS}

    def test_returns_saved_data(self, image_dir: Path) -> None:
        _save_annotations(image_dir, "cat1.jpg", [[10, 20, 30, 40]], [1])
        data = _load_annotations(image_dir, "cat1.jpg")
        assert data["bboxes"] == [[10, 20, 30, 40]]
        assert data["labels"] == [1]

    def test_returns_empty_on_corrupt_json(self, image_dir: Path) -> None:
        _ann_path(image_dir, "cat1.jpg").write_text("not json", encoding="utf-8")
        data = _load_annotations(image_dir, "cat1.jpg")
        assert data == {"bboxes": [], "labels": [], "label_list": ANNOTATION_LABELS}


# ---------------------------------------------------------------------------
# _render_annotated_preview
# ---------------------------------------------------------------------------

class TestRenderAnnotatedPreview:
    def test_returns_rgb_array(self, image_dir: Path) -> None:
        result = _render_annotated_preview(image_dir / "cat1.jpg", [[5, 5, 20, 20]], [0])
        assert result is not None
        assert result.shape == (80, 80, 3)

    def test_returns_none_for_missing_image(self, image_dir: Path) -> None:
        result = _render_annotated_preview(image_dir / "ghost.jpg", [], [])
        assert result is None

    def test_empty_bboxes_returns_plain_image(self, image_dir: Path) -> None:
        result = _render_annotated_preview(image_dir / "cat1.jpg", [], [])
        assert result is not None
        assert result.shape == (80, 80, 3)

    def test_multiple_bboxes(self, image_dir: Path) -> None:
        bboxes = [[5, 5, 15, 15], [40, 40, 20, 20]]
        labels = [0, 1]
        result = _render_annotated_preview(image_dir / "cat1.jpg", bboxes, labels)
        assert result is not None
