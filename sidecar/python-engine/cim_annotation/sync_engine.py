from __future__ import annotations

"""
sync_engine.py — Offline-first sync between local annotation results and a remote connector.

Usage:
    engine = SyncEngine(push_connector, manifest_db_path, manifest_id)
    engine.enqueue(payload)            # buffer locally
    stats = engine.flush(batch_size=20)  # push pending to remote
    engine.retry_errors(max_attempts=3)  # retry error'd rows
"""

import json
import sys
from pathlib import Path

from .connectors.base import PushConnector
from .models import AnnotationPayload, PushResult

_HERE = Path(__file__).resolve()
_SHARED = _HERE.parents[1] / "scripts" / "shared" / "_manifest_db.py"


def _load_mdb():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_manifest_db_sync", _SHARED)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


class SyncEngine:
    """
    Offline-first sync engine.

    Buffers annotation payloads in the local `sync_queue` SQLite table and
    flushes them to the remote PushConnector on demand.

    Guarantees:
    - `enqueue()` is always fast and always local (never fails due to network).
    - `flush()` pushes in batches; partial failures are recorded per-row.
    - `retry_errors()` re-attempts rows that failed with < max_attempts.
    """

    def __init__(
        self,
        push: PushConnector,
        db_path: Path,
        manifest_id: str,
    ) -> None:
        self._push = push
        self._db_path = db_path
        self._manifest_id = manifest_id
        self._mdb = _load_mdb()

    def enqueue(self, payload: AnnotationPayload) -> None:
        """
        Serialize payload to JSON and insert into sync_queue with status='pending'.
        Never raises; safe to call with no network.
        """
        payload_json = json.dumps({
            "item_id": payload.item_id,
            "remote_id": payload.remote_id,
            "image_path": payload.image_path,
            "image_width": payload.image_width,
            "image_height": payload.image_height,
            "shapes": payload.shapes,
            "classification": payload.classification,
            "confidence": payload.confidence,
            "annotator": payload.annotator,
            "annotated_at": payload.annotated_at,
        }, ensure_ascii=False)
        self._mdb.enqueue_sync(
            self._db_path,
            self._manifest_id,
            payload.item_id,
            payload.remote_id,
            payload_json,
        )

    def flush(self, batch_size: int = 20) -> dict:
        """
        Push all pending rows to the remote connector.

        Returns a summary: {"attempted": int, "succeeded": int, "failed": int}.
        """
        pending = self._mdb.get_pending_sync(self._db_path, self._manifest_id, limit=batch_size)
        if not pending:
            return {"attempted": 0, "succeeded": 0, "failed": 0}

        payloads = []
        row_ids = []
        for row in pending:
            try:
                data = json.loads(row["payload_json"])
                payloads.append(AnnotationPayload(**data))
                row_ids.append(row["id"])
            except Exception:
                continue

        results: list[PushResult] = self._push.push_batch(payloads)
        succeeded = 0
        failed = 0
        for row_id, result in zip(row_ids, results):
            if result.success:
                self._mdb.mark_sync_result(self._db_path, row_id, success=True)
                succeeded += 1
            else:
                self._mdb.mark_sync_result(self._db_path, row_id, success=False, error=result.error)
                failed += 1

        return {"attempted": len(results), "succeeded": succeeded, "failed": failed}

    def retry_errors(self, max_attempts: int = 3) -> dict:
        """
        Reset 'error' rows with attempts < max_attempts back to 'pending' so
        flush() will retry them.

        Returns {"reset": int} — the number of rows reset.
        """
        import sqlite3
        conn = sqlite3.connect(str(self._db_path))
        try:
            cur = conn.execute(
                "UPDATE sync_queue SET status='pending' "
                "WHERE manifest_id=? AND status='error' AND attempts < ?",
                (self._manifest_id, max_attempts),
            )
            conn.commit()
            return {"reset": cur.rowcount}
        finally:
            conn.close()

    def stats(self) -> dict:
        """Return counts by status for this manifest's sync_queue."""
        return self._mdb.get_sync_stats(self._db_path, self._manifest_id)
