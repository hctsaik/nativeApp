from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_MDB_PATH = _HERE / "_manifest_db.py"


def _load():
    spec = importlib.util.spec_from_file_location("_manifest_db", _MDB_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _make_db(tmp_path: Path):
    mdb = _load()
    db = tmp_path / "test.sqlite"
    mdb.init_db(db)
    mdb.create_manifest(db, "m1", "Test Manifest", "folder", {"path": "/tmp"})
    mdb.add_manifest_items(db, "m1", [
        {"item_id": "i1", "file_path": "/tmp/a.jpg"},
        {"item_id": "i2", "file_path": "/tmp/b.jpg"},
    ])
    return mdb, db


# ─── save_snapshot / save_snapshots_bulk ──────────────────────────────────────

def test_save_snapshot_single(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.save_snapshot(db, "m1", "i1", "pre_label",
                      label_json='{"shapes":[]}', model_path="yolo.pt")
    rows = mdb.get_snapshots(db, "m1")
    assert len(rows) == 1
    assert rows[0]["item_id"] == "i1"
    assert rows[0]["trigger"] == "pre_label"
    assert rows[0]["model_path"] == "yolo.pt"
    assert json.loads(rows[0]["label_json"]) == {"shapes": []}


def test_save_snapshots_bulk(tmp_path):
    mdb, db = _make_db(tmp_path)
    rows = [
        {"item_id": "i1", "trigger": "pre_label", "label_json": '{"shapes":[]}', "model_path": "m.pt"},
        {"item_id": "i2", "trigger": "pre_label", "label_json": "{}"},
    ]
    mdb.save_snapshots_bulk(db, "m1", rows)
    result = mdb.get_snapshots(db, "m1")
    assert len(result) == 2
    item_ids = {r["item_id"] for r in result}
    assert item_ids == {"i1", "i2"}


def test_save_snapshots_bulk_empty_list(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.save_snapshots_bulk(db, "m1", [])
    assert mdb.get_snapshots(db, "m1") == []


def test_save_snapshots_bulk_optional_fields(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.save_snapshots_bulk(db, "m1", [
        {"item_id": "i1", "trigger": "pre_sync", "label_json": "{}", "annotator_id": "NT001"},
    ])
    result = mdb.get_snapshots(db, "m1")
    assert result[0]["annotator_id"] == "NT001"
    assert result[0]["model_path"] is None


# ─── get_snapshots filters ────────────────────────────────────────────────────

def test_get_snapshots_filter_by_item_id(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.save_snapshots_bulk(db, "m1", [
        {"item_id": "i1", "trigger": "pre_label", "label_json": "{}"},
        {"item_id": "i2", "trigger": "pre_label", "label_json": "{}"},
    ])
    result = mdb.get_snapshots(db, "m1", item_id="i1")
    assert len(result) == 1
    assert result[0]["item_id"] == "i1"


def test_get_snapshots_filter_by_trigger(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.save_snapshots_bulk(db, "m1", [
        {"item_id": "i1", "trigger": "pre_label", "label_json": "{}"},
        {"item_id": "i1", "trigger": "pre_sync", "label_json": "{}"},
    ])
    result = mdb.get_snapshots(db, "m1", trigger="pre_sync")
    assert len(result) == 1
    assert result[0]["trigger"] == "pre_sync"


def test_get_snapshots_limit(tmp_path):
    mdb, db = _make_db(tmp_path)
    for i in range(10):
        mdb.save_snapshot(db, "m1", "i1", "pre_label")
    result = mdb.get_snapshots(db, "m1", limit=3)
    assert len(result) == 3


def test_get_snapshots_different_manifest_isolated(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.create_manifest(db, "m2", "Other", "folder", {})
    mdb.add_manifest_items(db, "m2", [{"item_id": "x1", "file_path": "/x.jpg"}])
    mdb.save_snapshot(db, "m1", "i1", "pre_label")
    mdb.save_snapshot(db, "m2", "x1", "pre_label")
    assert len(mdb.get_snapshots(db, "m1")) == 1
    assert len(mdb.get_snapshots(db, "m2")) == 1


# ─── update_item_metadata ─────────────────────────────────────────────────────

def test_update_item_metadata_merge(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.update_item_metadata(db, "m1", "i1", {"max_conf": 0.87, "ai_model": "yolo.pt"})
    items = mdb.get_manifest_items(db, "m1")
    item = next(i for i in items if i["item_id"] == "i1")
    meta = json.loads(item["metadata"])
    assert meta["max_conf"] == 0.87
    assert meta["ai_model"] == "yolo.pt"


def test_update_item_metadata_preserves_existing(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.update_item_metadata(db, "m1", "i1", {"key_a": 1})
    mdb.update_item_metadata(db, "m1", "i1", {"key_b": 2})
    items = mdb.get_manifest_items(db, "m1")
    item = next(i for i in items if i["item_id"] == "i1")
    meta = json.loads(item["metadata"])
    assert meta["key_a"] == 1
    assert meta["key_b"] == 2


def test_update_item_metadata_overwrite_key(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.update_item_metadata(db, "m1", "i1", {"max_conf": 0.5})
    mdb.update_item_metadata(db, "m1", "i1", {"max_conf": 0.9})
    items = mdb.get_manifest_items(db, "m1")
    item = next(i for i in items if i["item_id"] == "i1")
    meta = json.loads(item["metadata"])
    assert meta["max_conf"] == 0.9


def test_update_item_metadata_nonexistent_item_no_crash(tmp_path):
    mdb, db = _make_db(tmp_path)
    mdb.update_item_metadata(db, "m1", "nonexistent", {"key": "val"})
