"""cim-modules → platform dependency contract (modules independence plan P0).

Freezes the *exact* surface the first-party CV modules (now the cim-modules git
submodule under plugins/cim-modules/) are allowed to depend on from the host
platform, so the modules repo can be developed/maintained/published independently
without its coupling silently widening.

Allowed surface (see docs/platform/modules-independence-and-store-plan.md §4.4):
  * the ``core`` namespace (``core.*``) — reserved for future use, and
  * a SMALL allowlist of platform-shared util files reached either by a bare
    import (via sys.path) or dynamically via ``importlib.spec_from_file_location``.

Measured real surface of the 7 active modules: only ``_config_base`` and
``_help`` (both via module_021). Everything else (``ui_components``,
``_manifest_db``, ``db_utils``, ``log_utils``, ``tool_result``, ``tool_comms``)
is currently UNUSED, so the allowlist is intentionally minimal — widen it
deliberately (and update the plan doc) before adding a new platform dependency.

Note: ``frame_fit_score`` is CV-domain shared code that lives INSIDE the modules
repo (modules/_shared/), reached via the path segment ``_shared`` (not the host
``shared``), so it is correctly NOT a platform dependency.

Pairs with tests/test_labeling_platform_contract.py — same mechanism, the second
plugin root to be frozen as an independent submodule.
"""
from __future__ import annotations

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]
CIM_MODULES_DIR = ENGINE_DIR / "plugins" / "cim-modules"

# ── The frozen contract ───────────────────────────────────────────────────
ALLOWED_NAMESPACES = {"core"}              # core.* (reserved; not required to be used)
ALLOWED_SHARED_FILES = {                   # platform-shared util files actually used
    "_config_base", "_help",               # scripts/shared/ (both via module_021)
}


def _platform_internal_roots() -> set[str]:
    """Top-level module names importable via sys.path that belong to the
    *platform* (engine root, tools/, scripts/shared/) — NOT third-party.
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
    return [p for p in CIM_MODULES_DIR.rglob("*.py") if "__pycache__" not in p.parts]


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

    A call is a *platform* load (vs an intra-modules sibling/_shared load) iff one
    of its string literals is a host path segment 'scripts', 'shared', or 'tools'.
    The intra-repo ``_shared`` segment deliberately does NOT match.
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


def test_modules_static_imports_within_contract() -> None:
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
        "cim-modules may only statically depend on the frozen platform contract "
        f"(namespaces={sorted(ALLOWED_NAMESPACES)}, shared={sorted(ALLOWED_SHARED_FILES)}). "
        "Widen the contract deliberately in docs/platform/modules-independence-and-store-plan.md "
        "before adding new platform deps:\n  " + "\n  ".join(violations)
    )


def test_modules_dynamic_shared_loads_within_contract() -> None:
    violations: list[str] = []
    for py in _py_files():
        tree = _parse(py)
        if tree is None:
            continue
        for bad in sorted(_dynamic_shared_loads(tree) - ALLOWED_SHARED_FILES):
            violations.append(f"{py.relative_to(ENGINE_DIR)} dynamically loads platform-shared file '{bad}.py'")
    assert not violations, (
        "cim-modules dynamically loads a platform-shared file outside the frozen "
        "contract (see docs/platform/modules-independence-and-store-plan.md §4.4):\n  "
        + "\n  ".join(violations)
    )


def test_contract_allowlist_is_actually_exercised() -> None:
    """Guard against the contract rotting into a no-op: every allowlisted shared
    file should still be loaded by cim-modules, so a stale entry surfaces instead
    of silently widening the allowed surface.
    """
    seen: set[str] = set()
    for py in _py_files():
        tree = _parse(py)
        if tree is None:
            continue
        seen |= _dynamic_shared_loads(tree)
        seen |= (_static_import_roots(tree) & ALLOWED_SHARED_FILES)
    unused = ALLOWED_SHARED_FILES - seen
    assert not unused, (
        "these allowlisted shared files are no longer used by cim-modules — tighten "
        f"the contract by removing them: {sorted(unused)}"
    )
