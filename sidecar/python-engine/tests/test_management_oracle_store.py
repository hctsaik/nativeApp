from __future__ import annotations

import pytest

from management_oracle_store import OracleManagementStore


class _FakeVar:
    def __init__(self) -> None:
        self.value = [0]

    def setvalue(self, index: int, value: int) -> None:
        self.value[index] = value

    def getvalue(self):
        return self.value


class _FakeCursor:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection
        self.description = []
        self.rowcount = 0

    def var(self, _type):
        return _FakeVar()

    def execute(self, sql: str, params: dict | None = None):
        params = params or {}
        self.connection.statements.append((sql, params))
        normalized = " ".join(sql.lower().split())
        self.description = []
        self.connection.rows = []
        self.rowcount = 0

        if "returning version_id into" in normalized:
            params["version_id"].setvalue(0, 101)
        elif "returning event_id into" in normalized:
            params["event_id"].setvalue(0, 202)
        elif normalized.startswith("select tool_id from tools where enabled_prod=1"):
            self.description = [("TOOL_ID",)]
            self.connection.rows = [("module_aaa",)]
        elif normalized.startswith("select can_execute from plugin_permissions"):
            self.description = [("CAN_EXECUTE",)]
            self.connection.rows = [(0,)]
        elif normalized.startswith("select can_view from plugin_permissions"):
            self.description = [("CAN_VIEW",)]
            self.connection.rows = [(1,)]
        elif normalized.startswith("select event_id, created_at"):
            self.description = [
                ("EVENT_ID",),
                ("CREATED_AT",),
                ("ACTOR",),
                ("ACTION",),
                ("TARGET_TYPE",),
                ("TARGET_ID",),
                ("DETAILS_JSON",),
            ]
            self.connection.rows = [(202, "now", "alice", "publish", "tool", "module_aaa", "{}")]
        elif normalized.startswith("select 1 as found from tool_versions"):
            self.description = [("FOUND",)]
            self.connection.rows = [(1,)]
        elif normalized.startswith("select version_id from tool_versions"):
            self.description = [("VERSION_ID",)]
            self.connection.rows = [(2,), (1,)]
        elif normalized.startswith("update tool_versions set is_active=0 where tool_id=:tool_id and version_id<>"):
            self.rowcount = 1
        return self

    def fetchall(self):
        return list(self.connection.rows)

    def fetchone(self):
        return self.connection.rows.pop(0) if self.connection.rows else None


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list[tuple[str, dict]] = []
        self.rows = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1


@pytest.fixture()
def fake_conn() -> _FakeConnection:
    return _FakeConnection()


@pytest.fixture()
def store(fake_conn: _FakeConnection) -> OracleManagementStore:
    return OracleManagementStore(connection_factory=lambda: fake_conn)


def test_oracle_store_requires_driver_or_factory() -> None:
    store = OracleManagementStore()

    with pytest.raises(RuntimeError):
        store.list_prod_module_tool_ids()


def test_oracle_publish_uses_named_binds_and_returning(
    store: OracleManagementStore,
    fake_conn: _FakeConnection,
) -> None:
    version_id = store.publish_tool_snapshot("module_aaa", "Module A", "1.0.0", "{}", "release", "alice")

    assert version_id == 101
    assert fake_conn.commits == 1
    assert any(":plugin_id" in sql for sql, _ in fake_conn.statements)
    assert any("RETURNING version_id INTO :version_id" in sql for sql, _ in fake_conn.statements)


def test_oracle_audit_uses_returning(
    store: OracleManagementStore,
    fake_conn: _FakeConnection,
) -> None:
    event_id = store.record_audit_event("publish", "tool", "module_aaa", actor="alice")

    assert event_id == 202
    assert fake_conn.commits == 1
    assert any("RETURNING event_id INTO :event_id" in sql for sql, _ in fake_conn.statements)


def test_oracle_permission_maps_numeric_bool(store: OracleManagementStore) -> None:
    assert store.get_permission("module_aaa", "viewer", "execute") is False
    assert store.get_permission("module_aaa", "viewer", "view") is True


def test_oracle_list_rows_are_lowercase_dicts(store: OracleManagementStore) -> None:
    assert store.list_prod_module_tool_ids() == ["module_aaa"]
    assert store.list_audit_event_rows(limit=1)[0]["target_id"] == "module_aaa"


def test_oracle_normalize_active_versions_returns_update_count(
    store: OracleManagementStore,
) -> None:
    result = store.normalize_active_versions("module_aaa")

    assert result == {"kept_version_id": 2, "updated_rows": 1}
