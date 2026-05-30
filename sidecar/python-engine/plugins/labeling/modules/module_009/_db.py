from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

import psutil


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> None:
    with _connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS video_assets (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path     TEXT NOT NULL UNIQUE,
                asset_type    TEXT CHECK(asset_type IN ('video', 'image_dir')) NOT NULL,
                file_hash     TEXT,
                fps           REAL,
                total_frames  INTEGER,
                duration_s    REAL,
                display_name  TEXT,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS annotation_sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id          INTEGER NOT NULL REFERENCES video_assets(id),
                status            TEXT CHECK(status IN (
                                      '未標記', '追蹤中', '標記中', '已標記', '已同步'
                                  )) DEFAULT '未標記',
                xany_project_dir  TEXT,
                tracking_job_pid  INTEGER,
                xany_pid          INTEGER,
                locked_at         TEXT,
                annotation_count  INTEGER DEFAULT 0,
                last_summary      TEXT,
                last_updated      TEXT DEFAULT (datetime('now')),
                synced_at         TEXT
            );

            CREATE TABLE IF NOT EXISTS frame_annotations (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id      INTEGER NOT NULL REFERENCES annotation_sessions(id),
                frame_idx       INTEGER NOT NULL,
                annotation_json TEXT NOT NULL,
                confidence_avg  REAL,
                source          TEXT CHECK(source IN ('tracking', 'manual', 'xanylabeling', 'labelme', 'isat')),
                created_at      TEXT DEFAULT (datetime('now')),
                updated_at      TEXT DEFAULT (datetime('now')),
                UNIQUE(session_id, frame_idx)
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_asset ON annotation_sessions(asset_id);
            CREATE INDEX IF NOT EXISTS idx_frames_session ON frame_annotations(session_id, frame_idx);
        """)


def scan_folder(db_path: Path, folder_path: str) -> list[dict]:
    import hashlib
    import cv2

    folder = Path(folder_path)
    if not folder.exists():
        return []

    video_exts = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".m4v"}
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}

    results: list[dict] = []

    init_db(db_path)
    with _connect(db_path) as conn:
        for item in sorted(folder.iterdir()):
            if item.is_file() and item.suffix.lower() in video_exts:
                file_hash = hashlib.sha256(item.read_bytes()).hexdigest()[:16]
                cap = cv2.VideoCapture(str(item))
                fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total / fps if fps else 0.0
                cap.release()

                conn.execute(
                    """INSERT OR IGNORE INTO video_assets
                       (file_path, asset_type, file_hash, fps, total_frames, duration_s, display_name)
                       VALUES (?, 'video', ?, ?, ?, ?, ?)""",
                    (str(item), file_hash, fps, total, duration, item.name),
                )
                row = conn.execute(
                    "SELECT id FROM video_assets WHERE file_path=?", (str(item),)
                ).fetchone()
                asset_id = row["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO annotation_sessions (asset_id) VALUES (?)",
                    (asset_id,),
                )
                results.append({"file_path": str(item), "asset_type": "video", "asset_id": asset_id})

            elif item.is_dir():
                images = [f for f in item.iterdir() if f.suffix.lower() in image_exts]
                if not images:
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO video_assets
                       (file_path, asset_type, total_frames, display_name)
                       VALUES (?, 'image_dir', ?, ?)""",
                    (str(item), len(images), item.name),
                )
                row = conn.execute(
                    "SELECT id FROM video_assets WHERE file_path=?", (str(item),)
                ).fetchone()
                asset_id = row["id"]
                conn.execute(
                    "INSERT OR IGNORE INTO annotation_sessions (asset_id) VALUES (?)",
                    (asset_id,),
                )
                results.append({"file_path": str(item), "asset_type": "image_dir", "asset_id": asset_id})

    return results


def load_assets(db_path: Path) -> list[dict]:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute("""
            SELECT
                va.id AS asset_id,
                va.file_path,
                va.asset_type,
                va.display_name,
                va.fps,
                va.total_frames,
                va.duration_s,
                s.id AS session_id,
                s.status,
                s.xany_project_dir,
                s.tracking_job_pid,
                s.xany_pid,
                s.annotation_count,
                s.last_summary,
                s.last_updated,
                s.synced_at
            FROM video_assets va
            JOIN annotation_sessions s ON s.asset_id = va.id
            ORDER BY va.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]


def get_session_status(db_path: Path, session_id: int) -> Optional[dict]:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM annotation_sessions WHERE id=?", (session_id,)
        ).fetchone()
        return dict(row) if row else None


def get_next_unannotated(db_path: Path) -> Optional[int]:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute("""
            SELECT s.id FROM annotation_sessions s
            JOIN video_assets va ON va.id = s.asset_id
            WHERE s.status = '未標記'
            ORDER BY va.created_at ASC
            LIMIT 1
        """).fetchone()
        return row["id"] if row else None


def generate_summary(db_path: Path, session_id: int) -> dict:
    init_db(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT annotation_json, confidence_avg FROM frame_annotations WHERE session_id=?",
            (session_id,),
        ).fetchall()

        frame_count = len(rows)
        confs = [r["confidence_avg"] for r in rows if r["confidence_avg"] is not None]
        avg_conf = sum(confs) / len(confs) if confs else 0.0

        object_counts: dict[str, int] = {}
        for row in rows:
            try:
                data = json.loads(row["annotation_json"])
                for shape in data.get("shapes", []):
                    label = shape.get("label", "?")
                    object_counts[label] = object_counts.get(label, 0) + 1
            except Exception:
                pass

        return {
            "frame_count": frame_count,
            "avg_confidence": round(avg_conf, 3),
            "object_counts": object_counts,
        }


def acquire_lock(db_path: Path, session_id: int, pid: int) -> bool:
    init_db(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT xany_pid FROM annotation_sessions WHERE id=?", (session_id,)
        ).fetchone()
        if row and row["xany_pid"]:
            if psutil.pid_exists(row["xany_pid"]):
                return False
        conn.execute(
            "UPDATE annotation_sessions SET xany_pid=?, locked_at=datetime('now') WHERE id=?",
            (pid, session_id),
        )
    return True


def release_lock(db_path: Path, session_id: int) -> None:
    init_db(db_path)
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE annotation_sessions SET xany_pid=NULL, locked_at=NULL WHERE id=?",
            (session_id,),
        )


def update_session(db_path: Path, session_id: int, **kwargs) -> None:
    if not kwargs:
        return
    cols = ", ".join(f"{k}=?" for k in kwargs)
    vals = list(kwargs.values()) + [session_id]
    with _connect(db_path) as conn:
        conn.execute(
            f"UPDATE annotation_sessions SET {cols}, last_updated=datetime('now') WHERE id=?",
            vals,
        )


def upsert_frame_annotation(
    db_path: Path,
    session_id: int,
    frame_idx: int,
    annotation_json: str,
    confidence_avg: Optional[float],
    source: str,
) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """INSERT INTO frame_annotations
               (session_id, frame_idx, annotation_json, confidence_avg, source)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(session_id, frame_idx) DO UPDATE SET
                   annotation_json=excluded.annotation_json,
                   confidence_avg=excluded.confidence_avg,
                   source=excluded.source,
                   updated_at=datetime('now')""",
            (session_id, frame_idx, annotation_json, confidence_avg, source),
        )


def get_frame_annotations(db_path: Path, session_id: int) -> list[dict]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM frame_annotations WHERE session_id=? ORDER BY frame_idx",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
