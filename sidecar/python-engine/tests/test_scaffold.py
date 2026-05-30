"""Tests for the platform-native scaffolding CLI (tools/scaffold.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_DIR / "tools"))
import scaffold  # noqa: E402

from management_insights import module_preflight  # noqa: E402


def _load_process(folder: Path, mid: str):
    spec = importlib.util.spec_from_file_location(f"_{mid}p", folder / f"{mid}_process.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scaffold_no_code_form_first_module(tmp_path):
    folder = scaffold.scaffold_module("042", "我的工具", "cimcore", "cv", "system",
                                      full=False, base=tmp_path)
    # form-first → no input/output .py
    assert (folder / "plugin.yaml").exists()
    assert (folder / "042_process.py").exists()
    assert not (folder / "042_input.py").exists()
    assert not (folder / "042_output.py").exists()
    # preflight passes (declarative input+output)
    pf = module_preflight(tmp_path, "module_042")
    assert pf.ok, pf.issues
    # process runs
    mod = _load_process(folder, "042")
    out = mod.execute_logic({"text": "ab", "count": 3})
    assert out["echo"] == "ababab" and out["count"] == 3


def test_scaffold_full_split_tool_module(tmp_path):
    folder = scaffold.scaffold_module("043", "全手寫", "cimcore", "cv", "system",
                                      full=True, base=tmp_path)
    for f in ("plugin.yaml", "043_input.py", "043_process.py", "043_output.py"):
        assert (folder / f).exists()
    pf = module_preflight(tmp_path, "module_043")
    assert pf.ok, pf.issues


def test_scaffold_rejects_bad_id(tmp_path):
    with pytest.raises(SystemExit):
        scaffold.scaffold_module("9", "x", "v", "d", "a", full=False, base=tmp_path)


def test_scaffold_plugin(tmp_path):
    folder = scaffold.scaffold_plugin("qc", "cimcore", "quality", base=tmp_path)
    assert (folder / "plugin.manifest.yaml").exists()
    for sub in ("modules", "sheets", "mcp", "domain", "docs"):
        assert (folder / sub).is_dir()
