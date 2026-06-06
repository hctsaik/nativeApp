"""Packaging / dynamic-load guard tests.

These guard the two blind spots that the architecture-restructure discussion
flagged (docs/platform/architecture-restructure-discussion.md):

1. engine.spec hiddenimports is a hand-maintained whitelist. If a module is
   renamed/moved/added without updating the spec, the PyInstaller bundle breaks
   — but DEV mode never notices (only ``/package-build`` would). test_engine_spec
   _hiddenimports_are_importable front-loads that check into dev-runnable pytest.

2. Modules dynamically load each other and shared code via
   ``importlib.util.spec_from_file_location`` with *string paths* (e.g.
   ``_HERE.parent / "shared" / "_help.py"``). These dependencies are invisible
   to static analysis and only fail at runtime if a file moves.
   test_spec_from_file_location_targets_exist statically resolves the common
   anchor-based path expressions and asserts the target files still exist.
"""

from __future__ import annotations

import ast
import importlib
import re
from pathlib import Path

import pytest

ENGINE_DIR = Path(__file__).resolve().parents[1]
SPEC_FILE = ENGINE_DIR / "engine.spec"


# ─── Test A: engine.spec hiddenimports stay importable ────────────────────────

def _parse_spec_hiddenimports(spec_text: str) -> list[str]:
    """Extract the hiddenimports list literal from engine.spec without exec()."""
    m = re.search(r"hiddenimports\s*=\s*\[(.*?)\]", spec_text, re.DOTALL)
    assert m, "could not locate hiddenimports=[...] in engine.spec"
    return re.findall(r"['\"]([\w.]+)['\"]", m.group(1))


def test_engine_spec_hiddenimports_are_importable():
    names = _parse_spec_hiddenimports(SPEC_FILE.read_text(encoding="utf-8"))
    assert names, "engine.spec hiddenimports is empty — parse failure?"
    failed: list[str] = []
    for name in names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - we want to report any failure
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    assert not failed, (
        "engine.spec lists hiddenimports that no longer import — the PyInstaller "
        "bundle would break (dev mode would not catch this). Fix the module or "
        "update engine.spec:\n  " + "\n  ".join(failed)
    )


# ─── Test A2: the platform spec stays lean (no plugin heavy deps baked in) ────

def test_engine_spec_does_not_bundle_plugin_heavy_deps():
    """The platform stays pure: plugin-specific heavy deps (torch for labeling,
    plotly/duckdb/ai4bi for AI4BI) must NOT be baked into the core engine.exe.
    Each plugin (a separate git submodule) owns its deps; they install into
    per-tool venvs at runtime (core/tool_deps.py, #7). If someone re-adds a
    collect_all('ai4bi'/'torch'/…) to couple the platform to a plugin, this fails."""
    spec_text = SPEC_FILE.read_text(encoding="utf-8")
    for pkg in ("ai4bi", "torch", "plotly", "duckdb", "ultralytics"):
        assert f"collect_all('{pkg}'" not in spec_text and f'collect_all("{pkg}"' not in spec_text, (
            f"engine.spec bundles plugin dep {pkg!r} into the core platform — "
            "keep the platform lean; let the plugin own it (per-tool venv)."
        )


# ─── Test B: spec_from_file_location string-path targets exist ────────────────

_PY_FILES = [
    p for p in ENGINE_DIR.rglob("*.py")
    if "__pycache__" not in p.parts
    and "build" not in p.parts
    and "dist" not in p.parts
]


def _eval_path_node(node: ast.AST, file_dir: Path, assigns: dict[str, ast.AST]):
    """Best-effort static eval of a Path-building expression → Path, else None.

    Handles the anchor patterns actually used in this repo:
      _HERE / "x.py", _HERE.parent / "shared" / "y.py",
      Path(__file__).resolve().parent / "z.py", and one level of variable
      indirection (e.g. _PROCESS_FILE = _HERE / "012_process.py").
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _eval_path_node(node.left, file_dir, assigns)
        if left is None:
            return None
        if isinstance(node.right, ast.Constant) and isinstance(node.right.value, str):
            return left / node.right.value
        return None
    if isinstance(node, ast.Subscript):
        # handle X.parents[N]  → go up N levels from X
        val = node.value
        if isinstance(val, ast.Attribute) and val.attr == "parents":
            base = _eval_path_node(val.value, file_dir, assigns)
            if base is None:
                return None
            idx_node = node.slice
            if isinstance(idx_node, ast.Constant) and isinstance(idx_node.value, int):
                try:
                    return base.parents[idx_node.value]
                except IndexError:
                    return None
        return None
    if isinstance(node, ast.Attribute):
        base = _eval_path_node(node.value, file_dir, assigns)
        if base is None:
            return None
        if node.attr == "parent":
            return base.parent
        if node.attr == "resolve":
            return base  # .resolve()() handled by Call below
        return None
    if isinstance(node, ast.Call):
        # Path(__file__) → file path;  <expr>.resolve() → same path
        if isinstance(node.func, ast.Name) and node.func.id == "Path":
            if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
                return file_dir / "__placeholder__.py"  # only .parent is ever used
            return None
        if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve":
            return _eval_path_node(node.func.value, file_dir, assigns)
        return None
    if isinstance(node, ast.Name):
        # anchors that resolve to the file's own directory
        if node.id in {"_HERE", "_MODULE_DIR", "HERE"}:
            return file_dir
        if node.id in assigns:  # one level of indirection
            return _eval_path_node(assigns[node.id], file_dir, assigns)
        return None
    return None


def _collect_module_assignments(tree: ast.Module) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
            out[stmt.targets[0].id] = stmt.value
    return out


def test_spec_from_file_location_targets_exist():
    missing: list[str] = []
    checked = 0
    for py in _PY_FILES:
        try:
            tree = ast.parse(py.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        assigns = _collect_module_assignments(tree)
        for call in ast.walk(tree):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "spec_from_file_location"):
                continue
            if len(call.args) < 2:
                continue
            resolved = _eval_path_node(call.args[1], py.parent, assigns)
            if resolved is None:
                continue  # expression we can't statically resolve — skip
            checked += 1
            if not resolved.exists():
                missing.append(f"{py.relative_to(ENGINE_DIR)}:{call.lineno} → {resolved}")
    assert checked > 0, "resolver matched no spec_from_file_location targets — resolver regressed?"
    assert not missing, (
        "spec_from_file_location references a file that does not exist — a dynamic "
        "cross-module/shared load would fail at runtime:\n  " + "\n  ".join(missing)
    )
