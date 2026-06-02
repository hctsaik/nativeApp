"""Orphaned-sheet guard + edge-analysis sheet wiring tests.

A "sheet-*" tool whose sheet has no tabs (missing sheets/*.yaml definition, or
modules not registered) used to silently fall back to _start_regular, which
launched sheet_runner.py WITHOUT a plugin_id and produced the cryptic
"Missing CIM_SHEET_ID or CIM_PLUGIN_ID environment variable." in the iframe.
_start_sheet now fails loudly with a greppable [CIM-PREFLIGHT] message.

The edge-analysis sheet lost its YAML during the sheet->YAML migration; the new
sheets/edge-analysis.yaml restores it so fresh installs rebuild the 3-tab sheet.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pytest

import engine

ENGINE_DIR = Path(engine.__file__).resolve().parent


def test_orphan_sheet_raises_clear_error(tmp_path, monkeypatch, caplog):
    mgr = engine.ToolProcessManager(
        tmp_path, tmp_path / "selected_paths.json", tmp_path / "data" / "tools.sqlite"
    )
    # Simulate an orphaned sheet: tool row exists but the sheet has no tabs.
    monkeypatch.setattr(mgr, "_get_sheet_tabs", lambda sid: [])
    tool = engine.ToolDefinition(
        tool_id="sheet-orphan-xyz",
        name="Orphan",
        script_path=ENGINE_DIR / "tools" / "sheet_runner.py",
        version="1.0.0",
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as excinfo:
            mgr._start_sheet(tool)

    # The error names the offending tool and is greppable for pasting to an AI.
    assert "sheet-orphan-xyz" in str(excinfo.value)
    assert "orphan-xyz" in str(excinfo.value)
    assert any("[CIM-PREFLIGHT]" in r.getMessage() for r in caplog.records)


def test_edge_analysis_sheet_yaml_is_restored_and_wireable():
    import yaml

    yaml_path = ENGINE_DIR / "sheets" / "edge-analysis.yaml"
    assert yaml_path.exists(), "edge-analysis sheet YAML must exist so fresh installs rebuild it"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))

    assert data["sheet_id"] == "edge-analysis"
    module_ids = [t["module_id"] for t in data["tabs"]]
    assert module_ids == ["module_003", "module_004", "module_005"]

    # Each referenced module must exist as a real plugin so reconcile wires the
    # tabs on a fresh install (otherwise the sheet would re-orphan).
    for mid in module_ids:
        assert (ENGINE_DIR / "scripts" / mid / "plugin.yaml").exists(), f"{mid} plugin.yaml missing"


def test_garbage_sheet_seed_is_gone_from_engine_source():
    # Guard against the orphaned garbage seed being reintroduced into the seed
    # list. (The DELETE cleanup may legitimately reference the id once.)
    src = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
    assert 'INSERT OR IGNORE INTO tools' in src  # sanity: seed block still present
    assert src.count("sheet-共用標註功能_-_套件") <= 1, (
        "the garbage sheet seed should only appear in the idempotent DELETE cleanup"
    )
