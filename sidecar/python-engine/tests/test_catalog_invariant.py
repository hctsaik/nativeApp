"""Catalog launchability invariant — the CI gate that turns "I claim the fix
works" into PASS/FAIL.

Core invariant: an ENABLED ``sheet-*`` tool MUST have wired tabs, and launching
it MUST inject both ``CIM_SHEET_ID`` and ``CIM_PLUGIN_ID`` (exactly the two
env vars ``sheet_runner.py`` checks). If anyone reintroduces an orphan sheet
(seed without a backing definition), these tests go red before it ships.

Also guards the orphan auto-converge: any enabled sheet tool with no tabs is
auto-disabled on init/reload so it can never reach the portal dropdown.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import engine

ENGINE_DIR = Path(engine.__file__).resolve().parent


def _fresh_adapter(tmp_path) -> engine.SQLiteToolAdapter:
    db = tmp_path / "data" / "tools.sqlite"
    return engine.SQLiteToolAdapter(db)


def _enabled_sheet_tool_ids(db_path: Path) -> list[str]:
    con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT tool_id FROM tools WHERE tool_id LIKE 'sheet-%' AND enabled = 1"
    ).fetchall()
    con.close()
    return [r["tool_id"] for r in rows]


def test_every_enabled_sheet_tool_is_launchable(tmp_path, monkeypatch):
    """Fresh DB via the real init path: every enabled sheet tool has wired tabs
    AND _make_env injects CIM_SHEET_ID + CIM_PLUGIN_ID. This is the exact
    condition sheet_runner.py:74 checks — proving 'Missing CIM_SHEET_ID or
    CIM_PLUGIN_ID' is unreachable for any catalog-visible sheet tool."""
    adapter = _fresh_adapter(tmp_path)
    db_path = adapter._db_path
    from management_store import SQLiteManagementStore
    store = SQLiteManagementStore(db_path)

    mgr = engine.ToolProcessManager(tmp_path, tmp_path / "sp.json", db_path)
    # Don't let per-tool dependency resolution build venvs during the test.
    monkeypatch.setattr(engine, "_read_tool_requires", lambda *a, **k: [])

    sheet_ids = _enabled_sheet_tool_ids(db_path)
    assert sheet_ids, "expected at least one enabled sheet tool (e.g. edge-analysis/annotation)"

    for tool_id in sheet_ids:
        sid = tool_id[len("sheet-"):]
        tabs = store.list_sheet_tab_rows(sid)
        assert tabs, f"{tool_id} is an ORPHAN (enabled but no wired tabs) — a regression"

        tool = adapter.get_tool(tool_id)
        plugin_id = tabs[0]["plugin_id"]
        env = mgr._make_env(tool, plugin_id)
        assert env.get("CIM_SHEET_ID") == sid, f"{tool_id}: CIM_SHEET_ID not injected"
        assert env.get("CIM_PLUGIN_ID") == plugin_id, f"{tool_id}: CIM_PLUGIN_ID not injected"


def test_edge_analysis_is_enabled_and_wired(tmp_path):
    adapter = _fresh_adapter(tmp_path)
    assert "sheet-edge-analysis" in _enabled_sheet_tool_ids(adapter._db_path)


def test_orphan_sheet_is_auto_disabled_on_reinit(tmp_path):
    """Inject an enabled sheet tool with no tabs (an orphan), then re-init (==
    a restart / reload). The orphan auto-converge must disable it so it can
    never reach the dropdown — no per-id blacklist needed."""
    adapter = _fresh_adapter(tmp_path)
    db_path = adapter._db_path

    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT OR REPLACE INTO tools (tool_id,name,script_relative_path,version,enabled)"
        " VALUES ('sheet-injected-orphan','Injected Orphan','sheet_runner.py','1.0.0',1)"
    )
    con.commit(); con.close()

    # Re-init = what a restart/reload does (both run _reconcile_sheets_from_yaml).
    adapter2 = engine.SQLiteToolAdapter(db_path)

    assert "sheet-injected-orphan" not in _enabled_sheet_tool_ids(db_path)
    assert "sheet-injected-orphan" in adapter2.orphan_sheets_disabled


def test_garbage_chinese_sheet_seed_is_not_in_source():
    # The old garbage seed must not be reintroduced into the seed INSERT list,
    # and is no longer hard-DELETEd by id (the general converge handles it).
    src = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
    assert "INSERT OR IGNORE INTO tools" in src  # sanity: seed block present
    assert "sheet-共用標註功能_-_套件" not in src, (
        "garbage sheet id should not be hard-coded anymore — orphans are handled generically"
    )


def test_engine_commit_is_reported():
    commit = engine.engine_commit()
    assert isinstance(commit, str) and commit  # non-empty (a hash or 'unknown')
