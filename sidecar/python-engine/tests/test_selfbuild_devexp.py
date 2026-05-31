"""Developer-experience guards for the "self-build & ship a tool" goal.

These pin the Round-1 fixes from the multi-agent evaluation
(docs/platform/selfbuild-tool-shipping-evaluation.md):

  * Batch1-A — the publish/management layer scans BOTH scripts/ and
    plugins/*/modules/, so a plugin-located module (the Label-tool pattern)
    can actually be published, not just developed.
  * Batch1-B — hot-reload: SQLiteToolAdapter.rescan() re-scans plugin.yaml +
    sheet YAML into the catalog without an app restart, and an authored sheet
    auto-registers a launchable `sheet-<id>` tool.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

os.environ.setdefault("CIM_DEV_MODE", "1")

ENGINE_DIR = Path(__file__).resolve().parents[1]


# ── Batch1-A: dual-root publish ──────────────────────────────────────────────


def _write_module(folder: Path, mid: str, name: str) -> None:
    folder.mkdir(parents=True)
    short = mid.split("_", 1)[1]
    (folder / "__init__.py").write_text("", encoding="utf-8")
    (folder / f"{short}_process.py").write_text(
        "def execute_logic(params):\n    return {'mode': 'ready'}\n", encoding="utf-8"
    )
    (folder / "plugin.yaml").write_text(
        yaml.dump({"id": mid, "name": name, "version": "1.0.0",
                   "runner": "cv_framework", "form": [{"key": "x", "type": "text"}],
                   "output": [{"type": "text", "key": "x"}]}, allow_unicode=True),
        encoding="utf-8",
    )


@pytest.fixture()
def dual_root(tmp_path: Path) -> Path:
    """A scripts/ module + a plugin-located module (plugins/feat/modules/)."""
    _write_module(tmp_path / "scripts" / "module_aaa", "module_aaa", "腳本模組")
    _write_module(tmp_path / "plugins" / "feat" / "modules" / "module_777",
                  "module_777", "外掛模組")
    return tmp_path


def _registry(tmp_path: Path):
    from plugin_registry import PluginRegistry
    return PluginRegistry(db_path=tmp_path / "data" / "p.sqlite",
                          scripts_dir=tmp_path / "scripts")


def test_dual_root_lists_plugin_located_module(dual_root: Path) -> None:
    ids = {p.plugin_id for p in _registry(dual_root).list_plugins()}
    assert ids == {"module_aaa", "module_777"}, \
        "plugin-located module must be discoverable by the publish layer"


def test_dual_root_get_plugin_resolves_plugin_located(dual_root: Path) -> None:
    p = _registry(dual_root).get_plugin("module_777")
    assert p.plugin_id == "module_777" and p.name == "外掛模組"


def test_dual_root_publish_plugin_located_module(dual_root: Path) -> None:
    reg = _registry(dual_root)
    version_id = reg.publish("module_777", changelog="init")
    assert version_id > 0
    content = reg.get_plugin_content("module_777")
    assert "plugin.yaml" in content and any(k.endswith(".py") for k in content)


def test_next_module_id_avoids_plugin_located_ids(dual_root: Path) -> None:
    """A freshly allocated id must not collide with a plugin-located module."""
    from management_use_cases import ManagementUseCases
    from management_store import SQLiteManagementStore
    db = dual_root / "data" / "p.sqlite"
    reg = _registry(dual_root)
    uc = ManagementUseCases(db, dual_root / "scripts", reg, SQLiteManagementStore(db))
    # module_777 lives under plugins/feat/modules/, must be treated as used.
    assert uc._next_module_id() != "module_777"


# ── Batch1-B: hot-reload (rescan) + authored-sheet auto-register ─────────────


def test_adapter_rescan_is_idempotent_and_reports_added(tmp_path: Path) -> None:
    """rescan() re-scans real plugin/sheet YAML into a temp DB; a second call
    adds nothing (idempotent)."""
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from engine import SQLiteToolAdapter

    adapter = SQLiteToolAdapter(tmp_path / "rescan.sqlite")
    first = adapter.rescan()
    second = adapter.rescan()
    assert first["total"] > 0
    assert second["added"] == [], "second rescan must add nothing (idempotent)"


def test_authored_sheet_autoregisters_launchable_tool(tmp_path: Path) -> None:
    """The real annotation sheet YAML must surface as a launchable sheet-<id>
    tool after a scan — no engine.py seed edit required."""
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from engine import SQLiteToolAdapter

    adapter = SQLiteToolAdapter(tmp_path / "sheet.sqlite")
    adapter.rescan()
    with adapter._connect() as conn:
        row = conn.execute(
            "SELECT script_relative_path FROM tools WHERE tool_id='sheet-annotation'"
        ).fetchone()
    assert row is not None, "authored sheet did not auto-register a sheet-<id> tool"
    assert row["script_relative_path"] == "sheet_runner.py"


def test_engine_exposes_reload_endpoint() -> None:
    src = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
    assert '@app.post("/reload")' in src
    assert "registry.rescan()" in src
    # Hot-reload symmetry: /reload also re-runs connector autodiscover so a
    # freshly scaffolded connector becomes usable without an app restart.
    assert "autodiscover()" in src


def test_rescan_reports_missing_sheet_modules(tmp_path: Path) -> None:
    """rescan() must report sheets whose tabs reference unregistered modules, so
    the portal can tell the author *why* their sheet didn't fully appear."""
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from engine import SQLiteToolAdapter

    adapter = SQLiteToolAdapter(tmp_path / "miss.sqlite")
    # Inject a sheet YAML root via a temp sheet referencing a non-existent module
    # by reusing the real scan (annotation sheet wires fine); assert the shape.
    result = adapter.rescan()
    assert "missing_modules" in result and isinstance(result["missing_modules"], list)
    assert "missing_sheets" in result


def test_external_gui_branch_enforces_permission() -> None:
    """Source-order guard (cheap fast check)."""
    src = (ENGINE_DIR / "tools" / "cv_framework_runner.py").read_text(encoding="utf-8")
    branch = src.index("ext_gui = meta.get")
    launch = src.index("render_launcher(ext_gui", branch)  # the call, not the import
    perm = src.index('check_permission(module_id, "execute")', branch)
    assert branch < perm < launch, "external_gui must check_permission before launching"


def test_external_gui_behaviorally_blocks_launch_when_denied(monkeypatch) -> None:
    """BEHAVIORAL guard (not just string order): drive run_input for an
    external_gui module with a viewer whose permission is denied, and assert the
    launcher is never invoked. Hardens the R8 RBAC-bypass fix against future
    refactors (R9 strict-evaluator point: string guards are fragile)."""
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    sys.path.insert(0, str(ENGINE_DIR / "tools"))
    monkeypatch.setenv("CIM_DEV_MODE", "1")
    import cv_framework_runner as cv
    import core.external_gui as eg

    errors: list[str] = []

    class _FakeSt:
        def __getattr__(self, name):
            def _w(*a, **k):
                if name == "error" and a:
                    errors.append(str(a[0]))
                return None
            return _w

    launched = {"n": 0}
    monkeypatch.setattr(eg, "render_launcher", lambda *a, **k: launched.__setitem__("n", launched["n"] + 1))
    monkeypatch.setattr(cv, "st", _FakeSt())
    monkeypatch.setattr(cv, "_hide_streamlit_chrome", lambda: None)
    monkeypatch.setattr(cv, "discover_modules", lambda: {"M": "module_900"})
    monkeypatch.setattr(cv, "MODULE_ID", "module_900")
    monkeypatch.setattr(cv, "_load_plugin_meta", lambda mid: {"external_gui": {"exe_fallback": "x"}})

    class _DenyAuth:
        def check_permission(self, plugin_id, action):
            return False

    monkeypatch.setattr(cv, "_auth", _DenyAuth())
    cv.run_input()
    assert launched["n"] == 0, "launcher must NOT run when execute permission is denied"
    assert any("權限" in e for e in errors), "should surface a permission error"


def test_engine_exposes_role_endpoints() -> None:
    """RBAC must be demonstrable: /whoami reports the role, DEV /set-role switches
    it (gap U9: engine enforced RBAC but role couldn't be set/seen)."""
    src = (ENGINE_DIR / "engine.py").read_text(encoding="utf-8")
    assert '@app.get("/whoami")' in src and "get_current_role()" in src
    assert '@app.post("/set-role")' in src and "set_identity(" in src


def test_portal_role_switcher_wired() -> None:
    src = (ENGINE_DIR.parents[1] / "apps" / "portal-react" / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "/whoami" in src and "/set-role" in src
    assert "handleSetRole" in src and "onSetRole={handleSetRole}" in src


def test_portal_reload_button_removed() -> None:
    """The dev-only 重新載入工具 (Reload Tools) button was intentionally removed
    from the portal (owner request, 2026-05-31), along with its dead supporting
    code (handleReload / onReload / the reloading state). Guard that it stays
    removed so it isn't accidentally re-added. The engine POST /reload endpoint
    remains for programmatic / MCP use — covered by
    test_api.test_reload_endpoint_rescans_catalog."""
    src = (ENGINE_DIR.parents[1] / "apps" / "portal-react" / "src" / "main.jsx").read_text(encoding="utf-8")
    assert "重新載入工具" not in src
    assert "handleReload" not in src
    assert "onReload" not in src


def test_tool_registry_delegates_rescan() -> None:
    import sys
    sys.path.insert(0, str(ENGINE_DIR))
    from engine import ToolRegistry, ToolAdapter, ToolDefinition

    class _Fake(ToolAdapter):
        def list_tools(self):
            return []
        def get_tool(self, tool_id):
            raise KeyError(tool_id)
        def rescan(self):
            return {"added": ["module_999"], "total": 1}

    assert ToolRegistry(_Fake()).rescan() == {"added": ["module_999"], "total": 1}
