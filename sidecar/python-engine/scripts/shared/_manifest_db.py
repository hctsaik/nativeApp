from __future__ import annotations

"""
shared/_manifest_db.py — SQLite3 DAL for DatasetManifest & annotation results.
無 Streamlit import，所有函式接受 db_path: Path 作第一個參數。
"""

import json
import sqlite3
from pathlib import Path

# ─── Schema ────────────────────────────────────────────────────────────────────

_DDL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS dataset_manifests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    manifest_id   TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    source_type   TEXT CHECK(source_type IN ('folder','db','api','iwsc','remote')) NOT NULL,
    source_config TEXT NOT NULL DEFAULT '{}',
    schema_version TEXT NOT NULL DEFAULT '1.0',
    item_count    INTEGER DEFAULT 0,
    status        TEXT CHECK(status IN ('draft','ready','error')) DEFAULT 'draft',
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS manifest_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    manifest_id TEXT NOT NULL REFERENCES dataset_manifests(manifest_id) ON DELETE CASCADE,
    item_id     TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    width       INTEGER,
    height      INTEGER,
    file_hash   TEXT,
    metadata    TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(manifest_id, item_id)
);

CREATE TABLE IF NOT EXISTS annotation_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT NOT NULL,
    manifest_id     TEXT NOT NULL,
    item_id         TEXT NOT NULL,
    annotation_json TEXT NOT NULL,
    label           TEXT,
    confidence      REAL,
    source          TEXT CHECK(source IN ('manual','model','tracking','xanylabeling')),
    annotator       TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(run_id, item_id)
);

CREATE TABLE IF NOT EXISTS annotation_exports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT NOT NULL,
    manifest_id   TEXT NOT NULL,
    export_format TEXT,
    export_path   TEXT,
    item_count    INTEGER DEFAULT 0,
    schema_version TEXT DEFAULT '1.0',
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sync_queue (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    manifest_id  TEXT NOT NULL,
    item_id      TEXT NOT NULL,
    remote_id    TEXT,
    payload_json TEXT NOT NULL,
    status       TEXT CHECK(status IN ('pending','synced','conflict','error')) DEFAULT 'pending',
    attempts     INTEGER DEFAULT 0,
    last_error   TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    synced_at    TEXT
);

CREATE TABLE IF NOT EXISTS annotation_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    manifest_id  TEXT NOT NULL,
    item_id      TEXT NOT NULL,
    trigger      TEXT NOT NULL,
    model_path   TEXT,
    annotator_id TEXT,
    created_at   TEXT DEFAULT (datetime('now')),
    label_json   TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_snapshots_manifest ON annotation_snapshots(manifest_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_item ON annotation_snapshots(manifest_id, item_id);
"""


# ─── 內部輔助 ──────────────────────────────────────────────────────────────────

def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows) -> list[dict]:
    return [dict(r) for r in rows]


# ─── 公開 API ──────────────────────────────────────────────────────────────────

def _migrate_export_format_constraint(conn: sqlite3.Connection) -> None:
    """移除 annotation_exports.export_format 的 CHECK 約束（允許新格式）。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='annotation_exports'"
    ).fetchone()
    if row is None:
        return
    sql = (row[0] or "").upper()
    if "CHECK" not in sql:
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _annotation_exports_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id        TEXT NOT NULL,
            manifest_id   TEXT NOT NULL,
            export_format TEXT,
            export_path   TEXT,
            item_count    INTEGER DEFAULT 0,
            schema_version TEXT DEFAULT '1.0',
            created_at    TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO _annotation_exports_new
            SELECT id, run_id, manifest_id, export_format, export_path,
                   item_count, schema_version, created_at
            FROM annotation_exports;
        DROP TABLE annotation_exports;
        ALTER TABLE _annotation_exports_new RENAME TO annotation_exports;
    """)
    conn.commit()


def _migrate_source_type_constraint(conn: sqlite3.Connection) -> None:
    """擴展 dataset_manifests.source_type 的 CHECK 約束，加入 'iwsc' 和 'remote'。"""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='dataset_manifests'"
    ).fetchone()
    if row is None:
        return
    sql = row[0] or ""
    # 如果已經包含 'iwsc'，代表已是新版 schema，不需 migrate
    if "'iwsc'" in sql or "\"iwsc\"" in sql:
        return
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS _dataset_manifests_new (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            manifest_id   TEXT NOT NULL UNIQUE,
            name          TEXT NOT NULL,
            source_type   TEXT CHECK(source_type IN ('folder','db','api','iwsc','remote')) NOT NULL,
            source_config TEXT NOT NULL DEFAULT '{}',
            schema_version TEXT NOT NULL DEFAULT '1.0',
            item_count    INTEGER DEFAULT 0,
            status        TEXT CHECK(status IN ('draft','ready','error')) DEFAULT 'draft',
            created_at    TEXT DEFAULT (datetime('now')),
            updated_at    TEXT DEFAULT (datetime('now'))
        );
        INSERT OR IGNORE INTO _dataset_manifests_new
            SELECT id, manifest_id, name, source_type, source_config,
                   schema_version, item_count, status, created_at, updated_at
            FROM dataset_manifests;
        DROP TABLE dataset_manifests;
        ALTER TABLE _dataset_manifests_new RENAME TO dataset_manifests;
    """)
    conn.commit()


def init_db(db_path: Path) -> None:
    """初始化資料庫，建立所有資料表。"""
    conn = _connect(db_path)
    try:
        conn.executescript(_DDL)
        _migrate_export_format_constraint(conn)
        _migrate_source_type_constraint(conn)
        conn.commit()
    finally:
        conn.close()


def create_manifest(
    db_path: Path,
    manifest_id: str,
    name: str,
    source_type: str,
    source_config: dict,
) -> dict:
    """建立新的 DatasetManifest 記錄，回傳建立後的 dict。"""
    init_db(db_path)
    source_config_str = json.dumps(source_config, ensure_ascii=False)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO dataset_manifests (manifest_id, name, source_type, source_config)
            VALUES (?, ?, ?, ?)
            """,
            (manifest_id, name, source_type, source_config_str),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM dataset_manifests WHERE manifest_id=?", (manifest_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def add_manifest_items(db_path: Path, manifest_id: str, items: list[dict]) -> int:
    """
    批次新增 manifest_items，回傳實際新增數量（跳過已存在的）。
    每個 item dict 應包含：item_id, file_path；可選：width, height, file_hash, metadata。
    """
    init_db(db_path)
    conn = _connect(db_path)
    inserted = 0
    try:
        for item in items:
            metadata_str = json.dumps(item.get("metadata", {}), ensure_ascii=False)
            try:
                conn.execute(
                    """
                    INSERT INTO manifest_items
                        (manifest_id, item_id, file_path, width, height, file_hash, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest_id,
                        item["item_id"],
                        item["file_path"],
                        item.get("width"),
                        item.get("height"),
                        item.get("file_hash"),
                        metadata_str,
                    ),
                )
                inserted += 1
            except sqlite3.IntegrityError:
                # 跳過已存在的 (manifest_id, item_id)
                pass

        # 更新 item_count 與 updated_at
        conn.execute(
            """
            UPDATE dataset_manifests
            SET item_count = (
                SELECT COUNT(*) FROM manifest_items WHERE manifest_id=?
            ),
            status = 'ready',
            updated_at = datetime('now')
            WHERE manifest_id=?
            """,
            (manifest_id, manifest_id),
        )
        conn.commit()
        return inserted
    finally:
        conn.close()


def get_manifest(db_path: Path, manifest_id: str) -> dict | None:
    """依 manifest_id 取得 DatasetManifest，不存在回傳 None。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM dataset_manifests WHERE manifest_id=?", (manifest_id,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def list_manifests(db_path: Path) -> list[dict]:
    """列出所有 DatasetManifest，依 created_at 倒序。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM dataset_manifests ORDER BY id DESC"
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def get_manifest_items(
    db_path: Path, manifest_id: str, limit: int | None = None
) -> list[dict]:
    """取得指定 manifest 的所有 items，可設定上限。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        sql = "SELECT * FROM manifest_items WHERE manifest_id=? ORDER BY id"
        params: tuple = (manifest_id,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (manifest_id, limit)
        rows = conn.execute(sql, params).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def delete_manifest(db_path: Path, manifest_id: str) -> None:
    """刪除 manifest 及其關聯的 items（CASCADE）。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            "DELETE FROM dataset_manifests WHERE manifest_id=?", (manifest_id,)
        )
        conn.commit()
    finally:
        conn.close()


def upsert_annotation_result(
    db_path: Path,
    run_id: str,
    manifest_id: str,
    item_id: str,
    annotation_json: str,
    label: str | None,
    confidence: float | None,
    source: str | None,
) -> None:
    """新增或更新標注結果（以 run_id + item_id 為主鍵）。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO annotation_results
                (run_id, manifest_id, item_id, annotation_json, label, confidence, source, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(run_id, item_id) DO UPDATE SET
                annotation_json = excluded.annotation_json,
                label           = excluded.label,
                confidence      = excluded.confidence,
                source          = excluded.source,
                updated_at      = datetime('now')
            """,
            (run_id, manifest_id, item_id, annotation_json, label, confidence, source),
        )
        conn.commit()
    finally:
        conn.close()


def get_annotation_results(db_path: Path, run_id: str) -> list[dict]:
    """取得指定 run_id 的所有標注結果。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM annotation_results WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def create_export_record(
    db_path: Path,
    run_id: str,
    manifest_id: str,
    export_format: str,
    export_path: str,
    item_count: int,
) -> None:
    """記錄一次匯出作業。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO annotation_exports
                (run_id, manifest_id, export_format, export_path, item_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, manifest_id, export_format, export_path, item_count),
        )
        conn.commit()
    finally:
        conn.close()


def get_exports(db_path: Path, manifest_id: str) -> list[dict]:
    """取得指定 manifest 的所有匯出記錄。"""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM annotation_exports WHERE manifest_id=? ORDER BY created_at DESC",
            (manifest_id,),
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def get_manifest_annotation_counts(db_path: Path, manifest_id: str) -> dict:
    """
    回傳指定 manifest 的標注統計：
    {
      "total_items": int,
      "annotated_items": int,   # annotation_results 有記錄
      "label_counts": {label: count},  # bbox label 分布（aggregate from all run_ids）
      "classification_counts": {label: count},  # annotation_results.label 分布
    }
    """
    init_db(db_path)
    conn = _connect(db_path)
    try:
        total = conn.execute(
            "SELECT COUNT(*) FROM manifest_items WHERE manifest_id=?", (manifest_id,)
        ).fetchone()[0]

        annotated = conn.execute(
            "SELECT COUNT(DISTINCT item_id) FROM annotation_results WHERE manifest_id=?",
            (manifest_id,),
        ).fetchone()[0]

        # classification label 分布
        clf_rows = conn.execute(
            """
            SELECT label, COUNT(*) as cnt
            FROM annotation_results
            WHERE manifest_id=? AND label IS NOT NULL AND label != ''
            GROUP BY label
            ORDER BY cnt DESC
            """,
            (manifest_id,),
        ).fetchall()
        classification_counts = {r[0]: r[1] for r in clf_rows}

        return {
            "total_items": total,
            "annotated_items": annotated,
            "classification_counts": classification_counts,
        }
    finally:
        conn.close()


def get_all_manifests_stats(db_path: Path) -> list[dict]:
    """
    回傳所有 manifest 的統計摘要（用於 Dashboard）。
    每筆包含：manifest_id, name, created_at, total_items, annotated_items, export_count
    """
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT
                m.manifest_id,
                m.name,
                m.source_type,
                m.created_at,
                m.item_count AS total_items,
                COUNT(DISTINCT ar.item_id) AS annotated_items,
                (SELECT COUNT(*) FROM annotation_exports ae
                 WHERE ae.manifest_id = m.manifest_id) AS export_count
            FROM dataset_manifests m
            LEFT JOIN annotation_results ar ON ar.manifest_id = m.manifest_id
            GROUP BY m.manifest_id
            ORDER BY m.id DESC
            """
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


# ─── sync_queue DAL ────────────────────────────────────────────────────────────

def enqueue_sync(
    db_path: Path,
    manifest_id: str,
    item_id: str,
    remote_id: str | None,
    payload_json: str,
) -> None:
    """Add an annotation to the sync queue with status='pending'."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO sync_queue (manifest_id, item_id, remote_id, payload_json) "
            "VALUES (?, ?, ?, ?)",
            (manifest_id, item_id, remote_id, payload_json),
        )
        conn.commit()
    finally:
        conn.close()


def get_pending_sync(db_path: Path, manifest_id: str, limit: int = 50) -> list[dict]:
    """Return pending sync_queue entries for a manifest."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM sync_queue WHERE manifest_id=? AND status='pending' "
            "ORDER BY id LIMIT ?",
            (manifest_id, limit),
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def mark_sync_result(
    db_path: Path,
    queue_id: int,
    success: bool,
    error: str | None = None,
) -> None:
    """Update a sync_queue row after a push attempt."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        if success:
            conn.execute(
                "UPDATE sync_queue SET status='synced', synced_at=datetime('now') WHERE id=?",
                (queue_id,),
            )
        else:
            conn.execute(
                "UPDATE sync_queue SET status='error', attempts=attempts+1, last_error=? WHERE id=?",
                (error, queue_id),
            )
        conn.commit()
    finally:
        conn.close()


def get_sync_stats(db_path: Path, manifest_id: str) -> dict:
    """Return counts by status for the sync_queue."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS cnt FROM sync_queue WHERE manifest_id=? GROUP BY status",
            (manifest_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}
    finally:
        conn.close()


# ─── annotation_snapshots DAL ──────────────────────────────────────────────────

def save_snapshot(
    db_path: Path,
    manifest_id: str,
    item_id: str,
    trigger: str,
    label_json: str = "{}",
    model_path: str | None = None,
    annotator_id: str | None = None,
) -> None:
    """Save a pre-operation annotation snapshot for audit trail."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.execute(
            "INSERT INTO annotation_snapshots "
            "(manifest_id, item_id, trigger, model_path, annotator_id, label_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (manifest_id, item_id, trigger, model_path, annotator_id, label_json),
        )
        conn.commit()
    finally:
        conn.close()


def save_snapshots_bulk(
    db_path: Path,
    manifest_id: str,
    rows: list[dict],
) -> None:
    """Bulk-save snapshots. Each row: {item_id, trigger, label_json, model_path?, annotator_id?}."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        conn.executemany(
            "INSERT INTO annotation_snapshots "
            "(manifest_id, item_id, trigger, model_path, annotator_id, label_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    manifest_id,
                    r["item_id"],
                    r["trigger"],
                    r.get("model_path"),
                    r.get("annotator_id"),
                    r.get("label_json", "{}"),
                )
                for r in rows
            ],
        )
        conn.commit()
    finally:
        conn.close()


def get_snapshots(
    db_path: Path,
    manifest_id: str,
    item_id: str | None = None,
    trigger: str | None = None,
    limit: int = 100,
) -> list[dict]:
    """Retrieve annotation snapshots, optionally filtered by item_id and trigger."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        clauses = ["manifest_id=?"]
        params: list = [manifest_id]
        if item_id:
            clauses.append("item_id=?")
            params.append(item_id)
        if trigger:
            clauses.append("trigger=?")
            params.append(trigger)
        params.append(limit)
        rows = conn.execute(
            f"SELECT * FROM annotation_snapshots WHERE {' AND '.join(clauses)} "
            f"ORDER BY id DESC LIMIT ?",
            params,
        ).fetchall()
        return _rows_to_list(rows)
    finally:
        conn.close()


def update_item_metadata(
    db_path: Path,
    manifest_id: str,
    item_id: str,
    updates: dict,
) -> None:
    """Merge updates dict into the existing metadata JSON for a manifest item."""
    init_db(db_path)
    conn = _connect(db_path)
    try:
        row = conn.execute(
            "SELECT metadata FROM manifest_items WHERE manifest_id=? AND item_id=?",
            (manifest_id, item_id),
        ).fetchone()
        if row is None:
            return
        meta = json.loads(row[0] or "{}")
        meta.update(updates)
        conn.execute(
            "UPDATE manifest_items SET metadata=? WHERE manifest_id=? AND item_id=?",
            (json.dumps(meta, ensure_ascii=False), manifest_id, item_id),
        )
        conn.commit()
    finally:
        conn.close()
