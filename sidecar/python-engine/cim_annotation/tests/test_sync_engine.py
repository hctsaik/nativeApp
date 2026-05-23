from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_ENGINE_ROOT = Path(__file__).resolve().parents[2]
if str(_ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(_ENGINE_ROOT))

from cim_annotation.sync_engine import SyncEngine
from cim_annotation.models import AnnotationPayload, PushResult
from cim_annotation.connectors.base import PushConnector

_SHARED = _ENGINE_ROOT / "scripts" / "shared" / "_manifest_db.py"


def _load_mdb():
    spec = importlib.util.spec_from_file_location("_mdb_sync_test", _SHARED)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _payload(item_id: str = "i1", clf: str = "indoor") -> AnnotationPayload:
    return AnnotationPayload(
        item_id=item_id,
        remote_id=item_id,
        image_path=f"/img/{item_id}.jpg",
        image_width=640,
        image_height=480,
        shapes=[],
        classification=clf,
        confidence=None,
        annotator="test",
        annotated_at="2026-01-01T00:00:00Z",
    )


class AlwaysSucceedPush(PushConnector):
    def __init__(self):
        self.received: list[AnnotationPayload] = []

    def push_batch(self, payloads):
        self.received.extend(payloads)
        return [PushResult(p.item_id, True, p.remote_id, None) for p in payloads]

    def check_remote_version(self, item_ids):
        return {}


class AlwaysFailPush(PushConnector):
    def push_batch(self, payloads):
        return [PushResult(p.item_id, False, None, "network error") for p in payloads]

    def check_remote_version(self, item_ids):
        return {}


# ─── enqueue ─────────────────────────────────────────────────────────────────

def test_enqueue_adds_to_pending(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysSucceedPush(), db, "m1")
    engine.enqueue(_payload("i1"))
    pending = mdb.get_pending_sync(db, "m1")
    assert len(pending) == 1
    assert pending[0]["item_id"] == "i1"


def test_enqueue_multiple_items(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysSucceedPush(), db, "m2")
    for i in range(5):
        engine.enqueue(_payload(f"i{i}"))
    pending = mdb.get_pending_sync(db, "m2")
    assert len(pending) == 5


# ─── flush ───────────────────────────────────────────────────────────────────

def test_flush_success(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    push = AlwaysSucceedPush()
    engine = SyncEngine(push, db, "m3")
    engine.enqueue(_payload("i1"))
    engine.enqueue(_payload("i2"))
    stats = engine.flush()
    assert stats["attempted"] == 2
    assert stats["succeeded"] == 2
    assert stats["failed"] == 0
    assert len(push.received) == 2


def test_flush_marks_synced(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysSucceedPush(), db, "m4")
    engine.enqueue(_payload("i1"))
    engine.flush()
    pending = mdb.get_pending_sync(db, "m4")
    assert pending == []


def test_flush_failure_marks_error(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysFailPush(), db, "m5")
    engine.enqueue(_payload("i1"))
    stats = engine.flush()
    assert stats["failed"] == 1
    s = engine.stats()
    assert s.get("error", 0) == 1


def test_flush_empty_queue(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysSucceedPush(), db, "m6")
    stats = engine.flush()
    assert stats == {"attempted": 0, "succeeded": 0, "failed": 0}


# ─── retry_errors ─────────────────────────────────────────────────────────────

def test_retry_errors_resets_error_rows(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysFailPush(), db, "m7")
    engine.enqueue(_payload("i1"))
    engine.flush()
    assert engine.stats().get("error", 0) == 1

    result = engine.retry_errors(max_attempts=3)
    assert result["reset"] == 1
    assert mdb.get_pending_sync(db, "m7")[0]["item_id"] == "i1"


def test_retry_errors_respects_max_attempts(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysFailPush(), db, "m8")
    engine.enqueue(_payload("i1"))
    engine.flush()
    engine.flush()
    engine.flush()
    # After 3 flushes it's in 'error' with attempts=3 (or more, depending on reset)
    # With max_attempts=2, it should NOT be reset
    result = engine.retry_errors(max_attempts=1)
    assert result["reset"] == 0


# ─── stats ───────────────────────────────────────────────────────────────────

def test_stats_returns_counts(tmp_path):
    mdb = _load_mdb()
    db = tmp_path / "db" / "manifest.sqlite"
    mdb.init_db(db)
    engine = SyncEngine(AlwaysSucceedPush(), db, "m9")
    engine.enqueue(_payload("i1"))
    engine.enqueue(_payload("i2"))
    engine.flush()
    s = engine.stats()
    assert s.get("synced", 0) == 2
    assert s.get("pending", 0) == 0
