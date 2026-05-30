"""Architecture dependency-direction guard (platform restructure P3).

Codifies the boundary the restructure is converging on (see
docs/platform/architecture-restructure-discussion.md): platform *core*
infrastructure must never depend on a feature *plugin*. The rule today, on the
current package names:

  * core-candidate packages (cim_platform, management_*, auth_provider,
    plugin_loader/registry, tools/ shared utils) must NOT import the labeling
    domain ``annotation`` nor any GUI module ``scripts.module_*`` nor the
    half-dead ``cim_annotation``.
  * the labeling domain ``annotation`` must NOT import GUI modules
    ``scripts.module_*`` nor ``cim_annotation``.

When P5/P6 physically rename these into core/ and plugins/labeling/, update the
name lists here — the *direction* rule is permanent and import-linter-style.
"""

from __future__ import annotations

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[1]


def _imported_roots(py: Path) -> set[str]:
    """Root package names imported by a file (e.g. 'annotation.services' → 'annotation').

    ``from __future__ import annotations`` resolves to module '__future__', so it
    is never confused with the ``annotation`` package.
    """
    roots: set[str] = set()
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return roots
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def _scripts_module_imports(py: Path) -> set[str]:
    """Imports that target scripts.module_* (GUI tools)."""
    hits: set[str] = set()
    try:
        tree = ast.parse(py.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return hits
    for node in ast.walk(tree):
        mod = None
        if isinstance(node, ast.ImportFrom) and node.level == 0:
            mod = node.module
        elif isinstance(node, ast.Import):
            mod = node.names[0].name if node.names else None
        if mod and (mod == "scripts" or mod.startswith("scripts.")) and "module_" in mod:
            hits.add(mod)
    return hits


def _files(*relpaths: str) -> list[Path]:
    out: list[Path] = []
    for rel in relpaths:
        target = ENGINE_DIR / rel
        if target.is_dir():
            out.extend(p for p in target.rglob("*.py") if "__pycache__" not in p.parts)
        elif target.exists():
            out.append(target)
    return out


CORE_CANDIDATE_FILES = _files(
    "core",
    "management_insights.py", "management_oracle_store.py",
    "management_package_importer.py", "management_schema.py",
    "management_store.py", "management_use_cases.py",
    "auth_provider.py", "plugin_loader.py", "plugin_registry.py",
    "tools/db_utils.py", "tools/log_utils.py",
    "tools/tool_result.py", "tools/tool_comms.py",
)

FORBIDDEN_FOR_CORE = {"plugins", "annotation", "cim_annotation"}


def test_core_candidates_do_not_depend_on_plugins():
    violations: list[str] = []
    for py in CORE_CANDIDATE_FILES:
        roots = _imported_roots(py)
        bad = roots & FORBIDDEN_FOR_CORE
        for b in bad:
            violations.append(f"{py.relative_to(ENGINE_DIR)} imports plugin package '{b}'")
        for s in _scripts_module_imports(py):
            violations.append(f"{py.relative_to(ENGINE_DIR)} imports GUI module '{s}'")
    assert not violations, (
        "platform core must not depend on a feature plugin (core → plugin is "
        "forbidden):\n  " + "\n  ".join(violations)
    )


def test_annotation_domain_does_not_depend_on_gui_or_dead_pkg():
    annotation_files = _files("plugins/labeling/domain")
    assert annotation_files, "annotation domain package not found"
    violations: list[str] = []
    for py in annotation_files:
        if "cim_annotation" in _imported_roots(py):
            violations.append(f"{py.relative_to(ENGINE_DIR)} imports dead pkg 'cim_annotation'")
        for s in _scripts_module_imports(py):
            violations.append(f"{py.relative_to(ENGINE_DIR)} imports GUI module '{s}'")
    assert not violations, (
        "labeling domain (annotation) must not depend on GUI modules or the "
        "half-dead cim_annotation:\n  " + "\n  ".join(violations)
    )
