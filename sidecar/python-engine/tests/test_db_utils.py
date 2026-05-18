from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from db_utils import SimpleDAO


@pytest.fixture
def dao(tmp_path: Path) -> SimpleDAO:
    db = tmp_path / "test.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT, value INTEGER)")
    conn.executemany("INSERT INTO items (name, value) VALUES (?, ?)",
                     [("alpha", 10), ("beta", 20), ("gamma", 30)])
    conn.commit()
    conn.close()
    return SimpleDAO(db)


# ------------------------------------------------------------------
# query
# ------------------------------------------------------------------

class TestQuery:
    def test_returns_list_of_dicts(self, dao: SimpleDAO) -> None:
        rows = dao.query("SELECT * FROM items ORDER BY id")
        assert isinstance(rows, list)
        assert all(isinstance(r, dict) for r in rows)

    def test_returns_all_rows(self, dao: SimpleDAO) -> None:
        assert len(dao.query("SELECT * FROM items")) == 3

    def test_row_has_expected_keys(self, dao: SimpleDAO) -> None:
        row = dao.query("SELECT * FROM items LIMIT 1")[0]
        assert "id" in row and "name" in row and "value" in row

    def test_parametrised_filter(self, dao: SimpleDAO) -> None:
        rows = dao.query("SELECT * FROM items WHERE name = ?", ("beta",))
        assert len(rows) == 1
        assert rows[0]["value"] == 20

    def test_empty_result_returns_empty_list(self, dao: SimpleDAO) -> None:
        assert dao.query("SELECT * FROM items WHERE name = ?", ("nope",)) == []


# ------------------------------------------------------------------
# query_one
# ------------------------------------------------------------------

class TestQueryOne:
    def test_returns_dict_when_found(self, dao: SimpleDAO) -> None:
        row = dao.query_one("SELECT * FROM items WHERE name = ?", ("alpha",))
        assert row is not None
        assert row["value"] == 10

    def test_returns_none_when_not_found(self, dao: SimpleDAO) -> None:
        assert dao.query_one("SELECT * FROM items WHERE name = ?", ("nope",)) is None


# ------------------------------------------------------------------
# execute
# ------------------------------------------------------------------

class TestExecute:
    def test_update_returns_affected_row_count(self, dao: SimpleDAO) -> None:
        count = dao.execute("UPDATE items SET value = 99 WHERE name = ?", ("alpha",))
        assert count == 1

    def test_update_is_persisted(self, dao: SimpleDAO) -> None:
        dao.execute("UPDATE items SET value = 55 WHERE name = ?", ("beta",))
        row = dao.query_one("SELECT value FROM items WHERE name = 'beta'")
        assert row["value"] == 55

    def test_delete_returns_affected_row_count(self, dao: SimpleDAO) -> None:
        count = dao.execute("DELETE FROM items WHERE name = ?", ("gamma",))
        assert count == 1
        assert len(dao.query("SELECT * FROM items")) == 2

    def test_no_match_returns_zero(self, dao: SimpleDAO) -> None:
        assert dao.execute("UPDATE items SET value = 0 WHERE name = ?", ("nope",)) == 0


# ------------------------------------------------------------------
# execute_many
# ------------------------------------------------------------------

class TestExecuteMany:
    def test_inserts_multiple_rows(self, dao: SimpleDAO) -> None:
        dao.execute_many(
            "INSERT INTO items (name, value) VALUES (?, ?)",
            [("d", 40), ("e", 50)],
        )
        assert len(dao.query("SELECT * FROM items")) == 5

    def test_returns_total_affected(self, dao: SimpleDAO) -> None:
        count = dao.execute_many(
            "UPDATE items SET value = 0 WHERE name = ?",
            [("alpha",), ("beta",)],
        )
        assert count == 2

    def test_empty_sequence_affects_zero_rows(self, dao: SimpleDAO) -> None:
        assert dao.execute_many("INSERT INTO items (name,value) VALUES (?,?)", []) == 0


# ------------------------------------------------------------------
# last_insert_id
# ------------------------------------------------------------------

class TestLastInsertId:
    def test_returns_new_row_id(self, dao: SimpleDAO) -> None:
        rid = dao.last_insert_id(
            "INSERT INTO items (name, value) VALUES (?, ?)", ("new", 99)
        )
        assert isinstance(rid, int)
        assert rid > 0

    def test_inserted_row_is_queryable(self, dao: SimpleDAO) -> None:
        rid = dao.last_insert_id(
            "INSERT INTO items (name, value) VALUES (?, ?)", ("check", 77)
        )
        row = dao.query_one("SELECT * FROM items WHERE id = ?", (rid,))
        assert row is not None
        assert row["value"] == 77


# ------------------------------------------------------------------
# context manager
# ------------------------------------------------------------------

def test_context_manager_works(tmp_path: Path) -> None:
    db = tmp_path / "ctx.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE t (x TEXT)")
    conn.commit()
    conn.close()

    with SimpleDAO(db) as dao:
        dao.execute("INSERT INTO t VALUES (?)", ("hello",))
        rows = dao.query("SELECT * FROM t")
    assert rows[0]["x"] == "hello"
