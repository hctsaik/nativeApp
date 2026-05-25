"""
database.py — SQLite initialization and connection helpers for iWISC service.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "iwsc.db"


def get_connection() -> sqlite3.Connection:
    """Return a SQLite connection with row_factory set to Row."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create tables if they do not exist."""
    conn = get_connection()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS iwsc_tasks (
                ant_id          TEXT PRIMARY KEY,
                ant_period      TEXT,
                external_context TEXT,
                ant_active      INTEGER DEFAULT 0,
                created_at      TEXT,
                updated_at      TEXT
            );

            CREATE TABLE IF NOT EXISTS iwsc_results (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                ant_id          TEXT NOT NULL,
                platform_task_id TEXT,
                annotation_json TEXT,
                new_classification TEXT,
                annotated_by    TEXT,
                received_at     TEXT
            );
        """)
        conn.commit()
    finally:
        conn.close()
