from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add engine root to sys.path so cim_annotation is importable
_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from cim_annotation.connectors.local_file import LocalFileConnector
from cim_annotation.models import AnnotationPayload


def _make_images(tmp_path: Path, names: list[str]) -> None:
    for n in names:
        (tmp_path / n).write_bytes(b"\xff\xd8\xff")  # minimal JPEG header


# ─── fetch_page ───────────────────────────────────────────────────────────────

def test_fetch_page_empty_dir(tmp_path):
    c = LocalFileConnector(source_dir=tmp_path)
    assert c.fetch_page(0, 10) == []


def test_fetch_page_returns_images(tmp_path):
    _make_images(tmp_path, ["a.jpg", "b.jpg", "c.png"])
    (tmp_path / "notes.txt").write_text("skip me")
    c = LocalFileConnector(source_dir=tmp_path)
    items = c.fetch_page(0, 10)
    assert len(items) == 3
    names = {Path(it.file_path).name for it in items}
    assert names == {"a.jpg", "b.jpg", "c.png"}


def test_fetch_page_pagination(tmp_path):
    _make_images(tmp_path, [f"img{i}.jpg" for i in range(5)])
    c = LocalFileConnector(source_dir=tmp_path)
    page0 = c.fetch_page(0, 2)
    page1 = c.fetch_page(2, 2)
    page2 = c.fetch_page(4, 2)
    assert len(page0) == 2
    assert len(page1) == 2
    assert len(page2) == 1
    all_ids = [it.item_id for it in page0 + page1 + page2]
    assert len(set(all_ids)) == 5  # all unique


def test_fetch_page_beyond_end(tmp_path):
    _make_images(tmp_path, ["a.jpg"])
    c = LocalFileConnector(source_dir=tmp_path)
    assert c.fetch_page(10, 10) == []


def test_fetch_all_yields_all(tmp_path):
    _make_images(tmp_path, [f"x{i}.jpg" for i in range(7)])
    c = LocalFileConnector(source_dir=tmp_path)
    items = list(c.fetch_all(tmp_path, page_size=3))
    assert len(items) == 7


# ─── resolve_image ────────────────────────────────────────────────────────────

def test_resolve_image_returns_existing_path(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    c = LocalFileConnector(source_dir=tmp_path)
    from cim_annotation.models import FetchedItem
    item = FetchedItem("id1", str(img), None, None, None, None)
    resolved = c.resolve_image(item, tmp_path)
    assert resolved == img


# ─── push_batch ───────────────────────────────────────────────────────────────

def test_push_batch_writes_json(tmp_path):
    img = tmp_path / "frame.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    c = LocalFileConnector()
    payload = AnnotationPayload(
        item_id="i1",
        remote_id="r1",
        image_path=str(img),
        image_width=640,
        image_height=480,
        shapes=[{"label": "cat", "shape_type": "rectangle",
                 "points": [[0, 0], [100, 100], [100, 0], [0, 100]],
                 "group_id": None, "description": "", "difficult": False, "flags": {}}],
        classification="indoor",
        confidence=0.95,
        annotator="manual",
        annotated_at="2026-01-01T00:00:00Z",
    )
    results = c.push_batch([payload])
    assert len(results) == 1
    assert results[0].success is True

    ann = img.with_suffix(".json")
    assert ann.exists()
    data = json.loads(ann.read_text(encoding="utf-8"))
    assert data["imagePath"] == "frame.jpg"
    assert data["imageWidth"] == 640
    assert data["imageHeight"] == 480
    assert len(data["shapes"]) == 1
    assert data["flags"]["classification"] == "indoor"


def test_push_batch_partial_failure(tmp_path):
    c = LocalFileConnector()
    good = tmp_path / "good.jpg"
    good.write_bytes(b"\xff\xd8\xff")
    bad_path = str(tmp_path / "nonexistent_dir" / "bad.jpg")

    def _payload(item_id, path):
        return AnnotationPayload(item_id, "r", path, 100, 100, [], None, None, "manual", "2026-01-01T00:00:00Z")

    results = c.push_batch([_payload("g", str(good)), _payload("b", bad_path)])
    assert results[0].success is True
    assert results[1].success is False
    assert results[1].error is not None


def test_push_batch_atomic_no_tmp_on_success(tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    c = LocalFileConnector()
    payload = AnnotationPayload("i1", "r1", str(img), 100, 100, [], None, None, "manual", "2026-01-01T00:00:00Z")
    c.push_batch([payload])
    assert not (tmp_path / "img.tmp").exists()
    assert (tmp_path / "img.json").exists()


# ─── check_remote_version ─────────────────────────────────────────────────────

def test_check_remote_version_returns_empty():
    c = LocalFileConnector()
    assert c.check_remote_version(["id1", "id2"]) == {}
