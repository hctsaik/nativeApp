from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

sa = pytest.importorskip("sqlalchemy", reason="sqlalchemy not installed")

from cim_annotation.connectors.sql_connector import SqlConnector
from cim_annotation.models import AnnotationPayload


def _setup_db(tmp_path: Path) -> tuple[str, Path]:
    """Create a SQLite db with an images table and return (dsn, db_path)."""
    db_path = tmp_path / "test.sqlite"
    dsn = f"sqlite:///{db_path}"
    engine = sa.create_engine(dsn, future=True)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "CREATE TABLE images (id TEXT PRIMARY KEY, file_path TEXT, "
            "image_url TEXT, width INTEGER, height INTEGER)"
        ))
        conn.execute(sa.text(
            "CREATE TABLE annotations (image_id TEXT PRIMARY KEY, "
            "xanylabeling_json TEXT, updated_at TEXT)"
        ))
    return dsn, db_path


def _insert_images(dsn: str, rows: list[dict]) -> None:
    engine = sa.create_engine(dsn, future=True)
    with engine.begin() as conn:
        for r in rows:
            conn.execute(sa.text(
                "INSERT INTO images VALUES (:id, :file_path, :image_url, :width, :height)"
            ), r)


def _make_connector(dsn: str, extra: dict | None = None) -> SqlConnector:
    cfg = {
        "dsn": dsn,
        "pull_query": "SELECT id, file_path, image_url, width, height FROM images",
        "push_table": "annotations",
        "push_id_column": "image_id",
        "push_json_column": "xanylabeling_json",
        "push_updated_at_column": "updated_at",
    }
    if extra:
        cfg.update(extra)
    return SqlConnector(cfg)


# ─── fetch_page ───────────────────────────────────────────────────────────────

def test_fetch_page_empty_db(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    c = _make_connector(dsn)
    assert c.fetch_page(0, 10) == []


def test_fetch_page_returns_items(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    _insert_images(dsn, [
        {"id": "i1", "file_path": "/a.jpg", "image_url": None, "width": 640, "height": 480},
        {"id": "i2", "file_path": "/b.jpg", "image_url": None, "width": 320, "height": 240},
    ])
    c = _make_connector(dsn)
    page = c.fetch_page(0, 10)
    assert len(page) == 2
    ids = {it.item_id for it in page}
    assert ids == {"i1", "i2"}


def test_fetch_page_pagination(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    _insert_images(dsn, [
        {"id": f"i{i}", "file_path": f"/img{i}.jpg", "image_url": None, "width": 100, "height": 100}
        for i in range(5)
    ])
    c = _make_connector(dsn)
    p0 = c.fetch_page(0, 3)
    p1 = c.fetch_page(3, 3)
    assert len(p0) == 3
    assert len(p1) == 2
    all_ids = {it.item_id for it in p0 + p1}
    assert len(all_ids) == 5


def test_fetch_page_item_fields(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    _insert_images(dsn, [
        {"id": "x1", "file_path": "/foo.png", "image_url": "http://example.com/foo.png",
         "width": 800, "height": 600},
    ])
    c = _make_connector(dsn)
    items = c.fetch_page(0, 10)
    assert len(items) == 1
    it = items[0]
    assert it.item_id == "x1"
    assert it.file_path == "/foo.png"
    assert it.image_url == "http://example.com/foo.png"
    assert it.width == 800
    assert it.height == 600


# ─── resolve_image ────────────────────────────────────────────────────────────

def test_resolve_image_existing_local_file(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    img = tmp_path / "real.jpg"
    img.write_bytes(b"\xff\xd8\xff")
    _insert_images(dsn, [
        {"id": "r1", "file_path": str(img), "image_url": None, "width": 100, "height": 100},
    ])
    c = _make_connector(dsn)
    items = c.fetch_page(0, 10)
    resolved = c.resolve_image(items[0], tmp_path)
    assert resolved == img


# ─── push_batch ───────────────────────────────────────────────────────────────

def test_push_batch_writes_to_db(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    c = _make_connector(dsn)

    payload = AnnotationPayload(
        item_id="p1",
        remote_id="p1",
        image_path="/img.jpg",
        image_width=640,
        image_height=480,
        shapes=[{"label": "cat", "shape_type": "rectangle",
                 "points": [[0, 0], [100, 100]], "group_id": None,
                 "description": "", "difficult": False, "flags": {}}],
        classification="indoor",
        confidence=0.9,
        annotator="manual",
        annotated_at="2026-01-01T00:00:00Z",
    )
    results = c.push_batch([payload])
    assert len(results) == 1
    assert results[0].success is True

    engine = sa.create_engine(dsn, future=True)
    with engine.connect() as conn:
        row = conn.execute(sa.text("SELECT xanylabeling_json FROM annotations WHERE image_id='p1'")).fetchone()
    assert row is not None
    data = json.loads(row[0])
    assert data["flags"]["classification"] == "indoor"
    assert len(data["shapes"]) == 1


def test_push_batch_upserts_on_conflict(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    c = _make_connector(dsn)

    def _payload(clf: str) -> AnnotationPayload:
        return AnnotationPayload("p1", "p1", "/img.jpg", 100, 100, [], clf, None, "manual", "2026-01-01T00:00:00Z")

    c.push_batch([_payload("outdoor")])
    c.push_batch([_payload("indoor")])

    engine = sa.create_engine(dsn, future=True)
    with engine.connect() as conn:
        count = conn.execute(sa.text("SELECT COUNT(*) FROM annotations WHERE image_id='p1'")).scalar()
        row = conn.execute(sa.text("SELECT xanylabeling_json FROM annotations WHERE image_id='p1'")).fetchone()
    assert count == 1
    data = json.loads(row[0])
    assert data["flags"]["classification"] == "indoor"


# ─── check_remote_version ─────────────────────────────────────────────────────

def test_check_remote_version_returns_empty_without_query(tmp_path):
    dsn, _ = _setup_db(tmp_path)
    c = _make_connector(dsn)
    assert c.check_remote_version(["i1", "i2"]) == {}
