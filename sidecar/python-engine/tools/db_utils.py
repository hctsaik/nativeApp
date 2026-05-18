from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class SimpleDAO:
    """Lightweight SQLite DAO.

    Usage:
        dao = SimpleDAO("path/to/db.sqlite")
        rows = dao.query("SELECT * FROM images WHERE true_label = ?", ("貓",))
        dao.execute("UPDATE images SET classification = ? WHERE id = ?", ("狗", 1))
        dao.execute_many("INSERT INTO logs (msg) VALUES (?)", [("a",), ("b",)])

    Also usable as a context manager — no practical difference since connections
    are opened and closed per operation, but makes intent explicit:
        with SimpleDAO(db_path) as dao:
            dao.execute(...)
    """

    def __init__(self, db_path: str | Path) -> None:
        self._path = str(Path(db_path))

    # ------------------------------------------------------------------
    # Context manager (optional convenience)
    # ------------------------------------------------------------------

    def __enter__(self) -> SimpleDAO:
        return self

    def __exit__(self, *_: object) -> None:
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        """Run a SELECT statement and return results as a list of dicts."""
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_one(self, sql: str, params: tuple | list = ()) -> dict | None:
        """Run a SELECT and return the first row as a dict, or None."""
        with self._connect() as conn:
            row = conn.execute(sql, params).fetchone()
        return dict(row) if row is not None else None

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        """Run an INSERT / UPDATE / DELETE.  Returns the number of affected rows."""
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
        return cur.rowcount

    def execute_many(self, sql: str, params_seq: list[tuple | list]) -> int:
        """Run a batch INSERT / UPDATE / DELETE.  Returns total affected rows."""
        with self._connect() as conn:
            cur = conn.executemany(sql, params_seq)
            conn.commit()
        return cur.rowcount

    def last_insert_id(self, sql: str, params: tuple | list = ()) -> Any:
        """Run an INSERT and return the rowid of the new row."""
        with self._connect() as conn:
            cur = conn.execute(sql, params)
            conn.commit()
        return cur.lastrowid
