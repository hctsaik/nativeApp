from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from engine import SQLiteToolAdapter


@pytest.fixture
def adapter(tmp_path: Path) -> SQLiteToolAdapter:
    return SQLiteToolAdapter(tmp_path / "data" / "tools.sqlite")


# ---------------------------------------------------------------------------
# Seeded active modules
# ---------------------------------------------------------------------------

def test_module_001_appears_in_list(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "module_001" in ids


def test_module_006_appears_in_list(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "module_006" in ids


def test_all_active_modules_present(adapter: SQLiteToolAdapter) -> None:
    ids = {t.tool_id for t in adapter.list_tools()}
    expected = {
        "module_001", "module_003",
        "module_004", "module_005", "module_006", "module_008",
        "sheet-edge-analysis", "management-center",
    }
    assert expected.issubset(ids)


def test_annotation_workflow_tabs_include_dashboard_and_ai(adapter: SQLiteToolAdapter, tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT plugin_id FROM sheet_tabs WHERE sheet_id='annotation' ORDER BY tab_order"
        ).fetchall()

    plugin_ids = [row[0] for row in rows]
    # Unified annotation sheet (4 tabs replacing old 11-tab + 4-tab sheets)
    assert "module_026" in plugin_ids  # 資料來源（統一入口）
    assert "module_012" in plugin_ids  # 標注工作台
    assert "module_018" in plugin_ids  # 審查
    assert "module_014" in plugin_ids  # 匯出 / 回傳


def test_module_002_is_hidden_from_portal(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "module_002" not in ids


def test_module_002_seed_row_exists_in_db(adapter: SQLiteToolAdapter) -> None:
    # module_002 is disabled (hidden from portal) but seed row must exist for sheet use
    with pytest.raises(KeyError):
        adapter.get_tool("module_002")


def test_module_001_metadata(adapter: SQLiteToolAdapter) -> None:
    tool = adapter.get_tool("module_001")
    assert tool.tool_id == "module_001"
    assert tool.name == "OpenCV 影像處理"
    assert tool.version == "1.0.0"
    assert tool.script_path.name == "cv_framework_runner.py"


def test_module_006_metadata(adapter: SQLiteToolAdapter) -> None:
    tool = adapter.get_tool("module_006")
    assert tool.tool_id == "module_006"
    assert tool.name == "動物影像標記"
    assert tool.version == "1.0.0"
    assert tool.script_path.name == "cv_framework_runner.py"


def test_management_center_metadata(adapter: SQLiteToolAdapter) -> None:
    tool = adapter.get_tool("management-center")
    assert tool.tool_id == "management-center"
    assert tool.script_path.name == "management_runner.py"


def test_sample_csv_is_disabled(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "sample-csv" not in ids


def test_legacy_opencv_tool_not_present(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "opencv-tool" not in ids


def test_legacy_cv_framework_not_present(adapter: SQLiteToolAdapter) -> None:
    ids = [t.tool_id for t in adapter.list_tools()]
    assert "cv-framework" not in ids


def test_get_disabled_tool_raises_key_error(adapter: SQLiteToolAdapter) -> None:
    with pytest.raises(KeyError):
        adapter.get_tool("sample-csv")


def test_get_unknown_tool_raises_key_error(adapter: SQLiteToolAdapter) -> None:
    with pytest.raises(KeyError):
        adapter.get_tool("does-not-exist")


# ---------------------------------------------------------------------------
# Enable / disable
# ---------------------------------------------------------------------------

def test_disabled_tool_excluded_from_list(adapter: SQLiteToolAdapter, tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tools SET enabled = 0 WHERE tool_id = 'module_001'")

    ids = [t.tool_id for t in adapter.list_tools()]
    assert "module_001" not in ids


def test_disabled_tool_not_returned_by_get(adapter: SQLiteToolAdapter, tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "tools.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE tools SET enabled = 0 WHERE tool_id = 'module_001'")

    with pytest.raises(KeyError):
        adapter.get_tool("module_001")


# ---------------------------------------------------------------------------
# prod-enabled flag
# ---------------------------------------------------------------------------

def test_set_prod_enabled_true(adapter: SQLiteToolAdapter) -> None:
    adapter.set_prod_enabled("module_006", True)
    rows = adapter.list_tools_with_prod()
    row = next(r for r in rows if r[0] == "module_006")
    assert row[3] is True


def test_set_prod_enabled_false(adapter: SQLiteToolAdapter) -> None:
    adapter.set_prod_enabled("module_006", True)
    adapter.set_prod_enabled("module_006", False)
    rows = adapter.list_tools_with_prod()
    row = next(r for r in rows if r[0] == "module_006")
    assert row[3] is False


def test_list_tools_with_prod_includes_all_tools(adapter: SQLiteToolAdapter) -> None:
    rows = adapter.list_tools_with_prod()
    ids = {r[0] for r in rows}
    assert "module_001" in ids
    assert "module_006" in ids
