"""Labeling → platform dependency contract (labeling independence plan P0).

Freezes the *exact* surface the Labeling plugin is allowed to depend on from the
host platform, so labeling can be developed/maintained independently — and later
vendored as a git submodule, like AI4BI — without its coupling silently widening.

Allowed surface (see docs/platform/labeling-independence-plan.md §2):
  * the ``core`` namespace (``core.*``), and
  * a small allowlist of platform-shared utility files, reached either by a bare
    import (via sys.path) or dynamically via ``importlib.spec_from_file_location``.

Any NEW dependency on a platform internal (e.g. ``import engine`` /
``management_store`` / ``plugin_registry``) fails this test. Intra-labeling
imports, the standard library, and third-party packages are unaffected. This is
the import-contract counterpart to AI4BI's process isolation: it is what keeps
labeling independently maintainable. Widen the allowlist deliberately (and update
the plan doc) before adding a new platform dependency.

Pairs with tests/test_architecture_boundaries.py (which guards the *direction*:
core must never depend on a plugin). This guards the *surface*: a plugin may only
reach the platform through the frozen contract.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
LABELING_DIR = ENGINE_DIR / "plugins" / "labeling"

# ── The frozen contract ───────────────────────────────────────────────────
ALLOWED_NAMESPACES = {"core"}                       # core.* (declared depends_on)
ALLOWED_SHARED_FILES = {                            # platform-shared util files
    "_config_base", "_help", "_manifest_db", "ui_components",  # scripts/shared/
    "db_utils",                                                 # tools/
}


def _platform_internal_roots() -> set[str]:
    """Top-level module names importable from labeling via sys.path that belong
    to the *platform* (engine root, tools/, scripts/shared/) — NOT third-party.

    Computed from disk so the guard stays accurate as platform files are added.
    """
    roots: set[str] = set()
    for d in (ENGINE_DIR, ENGINE_DIR / "tools", ENGINE_DIR / "scripts" / "shared"):
        for p in d.glob("*.py"):
            if p.stem != "__init__":
                roots.add(p.stem)
    roots.add("core")  # package directory, not a *.py file
    return roots


def _py_files() -> list[Path]:
    return [p for p in LABELING_DIR.rglob("*.py") if "__pycache__" not in p.parts]


def _parse(py: Path) -> ast.AST | None:
    try:
        return ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _static_import_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _dynamic_shared_loads(tree: ast.AST) -> set[str]:
    """Stems of platform-shared files loaded via ``spec_from_file_location``.

    A call is a *platform* load (vs an intra-labeling sibling load) iff one of its
    string literals is a path segment 'scripts', 'shared', or 'tools'. We then
    collect the ``*.py`` literal stems referenced anywhere in that call.
    """
    stems: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
        if name != "spec_from_file_location":
            continue
        literals = [n.value for n in ast.walk(node)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        if {"scripts", "shared", "tools"} & set(literals):
            for lit in literals:
                if lit.endswith(".py"):
                    stems.add(Path(lit).stem)
    return stems


def test_labeling_static_imports_within_contract() -> None:
    platform_roots = _platform_internal_roots()
    allowed = ALLOWED_NAMESPACES | ALLOWED_SHARED_FILES
    violations: list[str] = []
    for py in _py_files():
        tree = _parse(py)
        if tree is None:
            continue
        for bad in sorted((_static_import_roots(tree) & platform_roots) - allowed):
            violations.append(f"{py.relative_to(ENGINE_DIR)} statically imports platform module '{bad}'")
    assert not violations, (
        "labeling may only statically depend on the frozen platform contract "
        f"(namespaces={sorted(ALLOWED_NAMESPACES)}, shared={sorted(ALLOWED_SHARED_FILES)}). "
        "Widen the contract deliberately in docs/platform/labeling-independence-plan.md "
        "before adding new platform deps:\n  " + "\n  ".join(violations)
    )


def test_labeling_dynamic_shared_loads_within_contract() -> None:
    violations: list[str] = []
    for py in _py_files():
        tree = _parse(py)
        if tree is None:
            continue
        for bad in sorted(_dynamic_shared_loads(tree) - ALLOWED_SHARED_FILES):
            violations.append(f"{py.relative_to(ENGINE_DIR)} dynamically loads platform-shared file '{bad}.py'")
    assert not violations, (
        "labeling dynamically loads a platform-shared file outside the frozen "
        "contract (see docs/platform/labeling-independence-plan.md §2):\n  "
        + "\n  ".join(violations)
    )


def test_contract_allowlist_is_actually_exercised() -> None:
    """Guard against the contract rotting into a no-op: every allowlisted shared
    file (except the optional ``db_utils``) should still be loaded by labeling,
    so a stale entry surfaces instead of silently widening the allowed surface.
    """
    seen: set[str] = set()
    for py in _py_files():
        tree = _parse(py)
        if tree is None:
            continue
        seen |= _dynamic_shared_loads(tree)
        seen |= (_static_import_roots(tree) & ALLOWED_SHARED_FILES)
    unused = (ALLOWED_SHARED_FILES - {"db_utils"}) - seen
    assert not unused, (
        "these allowlisted shared files are no longer used by labeling — tighten "
        f"the contract by removing them: {sorted(unused)}"
    )
