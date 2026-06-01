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


def test_scaffold_requires_emits_active_block(tmp_path):
    """--requires → an active per-tool-deps `requires:` block (#7); yaml still parses."""
    import yaml  # noqa: PLC0415

    folder = scaffold.scaffold_module("047", "需相依工具", "cimcore", "cv", "system",
                                      full=False, base=tmp_path,
                                      requires=["shapely>=2.0", "scikit-image"])
    meta = yaml.safe_load((folder / "plugin.yaml").read_text(encoding="utf-8"))
    assert meta["requires"] == ["shapely>=2.0", "scikit-image"]
    # still a valid runnable form-first module
    pf = module_preflight(tmp_path, "module_047")
    assert pf.ok, pf.issues


def test_scaffold_without_requires_has_no_active_requires(tmp_path):
    """No --requires → only a commented example, so `requires` is absent (zero cost)."""
    import yaml  # noqa: PLC0415

    folder = scaffold.scaffold_module("048", "無相依工具", "cimcore", "cv", "system",
                                      full=False, base=tmp_path)
    meta = yaml.safe_load((folder / "plugin.yaml").read_text(encoding="utf-8"))
    assert "requires" not in meta


def test_scaffold_rejects_bad_id(tmp_path):
    with pytest.raises(SystemExit):
        scaffold.scaffold_module("9", "x", "v", "d", "a", full=False, base=tmp_path)


def test_scaffold_plugin(tmp_path):
    folder = scaffold.scaffold_plugin("qc", "cimcore", "quality", base=tmp_path)
    assert (folder / "plugin.manifest.yaml").exists()
    for sub in ("modules", "sheets", "mcp", "domain", "docs"):
        assert (folder / sub).is_dir()


def test_scaffold_plugin_is_runnable_not_empty_shell(tmp_path):
    """A new plugin must ship a runnable starter module + domain service + sheet,
    not an empty directory tree (R1 gap: scaffold plugin produced empty shell)."""
    folder = scaffold.scaffold_plugin("qc", "cimcore", "quality", base=tmp_path)
    # domain service stub
    assert (folder / "domain" / "services.py").exists()
    # at least one runnable starter module with a process layer
    starters = list((folder / "modules").glob("module_*/"))
    assert starters, "plugin scaffold left modules/ empty"
    starter = starters[0]
    assert (starter / "plugin.yaml").exists()
    assert list(starter.glob("*_process.py")), "starter module has no process layer"
    # a starter workflow sheet wiring the module
    assert (folder / "sheets" / "qc-workflow.yaml").exists()


def test_scaffold_external_gui_module(tmp_path):
    """external-GUI tool: declarative plugin.yaml only, no input/process/output."""
    import yaml
    folder = scaffold.scaffold_module("044", "量測GUI", "cimcore", "metro", "system",
                                      full=False, base=tmp_path, external_gui=True)
    assert (folder / "plugin.yaml").exists()
    assert not list(folder.glob("044_*.py")), "external-gui tool must ship no layer code"
    meta = yaml.safe_load((folder / "plugin.yaml").read_text(encoding="utf-8"))
    assert "external_gui" in meta
    # the declared block must be valid per core.external_gui
    from core.external_gui import normalize_spec
    normalize_spec(meta["external_gui"])  # raises if malformed
    # preflight treats external-gui tools as requiring only plugin.yaml
    pf = module_preflight(tmp_path, "module_044")
    assert pf.ok, pf.issues


def test_scaffold_module_auto_picks_free_id(tmp_path):
    """Omitting the id auto-picks the next free module_NNN."""
    folder = scaffold.scaffold_module(None, "自動", "cimcore", "cv", "system",
                                      full=False, base=tmp_path)
    assert folder.name.startswith("module_") and folder.name[7:].isdigit()


def test_full_output_template_bakes_perf_rules(tmp_path):
    """The --full output template must embed the performance skeleton (pagination
    + the 3 rules), not leave them only in docs (R3 gap S2)."""
    folder = scaffold.scaffold_module("045", "效能", "cimcore", "cv", "system",
                                      full=True, base=tmp_path)
    out = (folder / "045_output.py").read_text(encoding="utf-8")
    assert "PAGE_SIZE" in out
    assert "mtime" in out and "index dict" in out.lower() or "idx_by_id" in out


def test_scaffold_connector_implements_protocol(tmp_path):
    """Non-REST connector skeleton must really subclass + satisfy the platform
    ExternalSystemConnector ABC (get_ant_list / get_ant_task_detail / health_check)
    so it can actually be instantiated and registered — not a duck-typed stub."""
    import importlib.util
    from core.integrations.connector import (
        ConnectorHealth, ExternalSystemConnector, ExternalTaskDetail,
    )
    path = scaffold.scaffold_connector("opcua-fab", base=tmp_path)
    spec = importlib.util.spec_from_file_location("_conn", path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    inst = mod.OpcuaFabConnector()  # instantiable → all abstractmethods implemented
    assert isinstance(inst, ExternalSystemConnector)
    assert inst.get_ant_list() == []
    assert isinstance(inst.get_ant_task_detail("t1", "coco"), ExternalTaskDetail)
    assert isinstance(inst.health_check(), ConnectorHealth)


def test_scaffold_connector_registration_loop_works(tmp_path):
    """The template's documented registration path must actually work end-to-end
    (R5 gap: docstring pointed at a non-existent module). The module exposes a
    register() that autodiscover() calls; build_connector then resolves it."""
    from core.integrations import registry
    path = scaffold.scaffold_connector("secsgem-eqp", base=tmp_path)
    # autodiscover imports the file and calls its register()
    discovered = registry.autodiscover(tmp_path)
    assert path.stem in discovered
    assert registry.is_registered("secsgem-eqp")
    conn = registry.build_connector("secsgem-eqp", tenant=None)
    from core.integrations.connector import ExternalSystemConnector
    assert isinstance(conn, ExternalSystemConnector)


def test_scaffolded_connector_reachable_via_live_labeling_path(tmp_path):
    """End-to-end through the LIVE consumer path: a scaffolded non-REST connector
    registered in the platform (core) registry must be resolvable by the labeling
    build_connector that AnnotationService actually uses (R6 gap: the two
    registries were disconnected → scaffolded connectors were unreachable)."""
    from core.integrations import registry as core_reg
    from plugins.labeling.domain.integrations import registry as lab_reg
    from core.integrations.connector import ExternalSystemConnector

    scaffold.scaffold_connector("opcua-live", base=tmp_path)
    core_reg.autodiscover(tmp_path)  # registers into the platform registry

    class _Tenant:  # minimal tenant carrying a declarative connector_type
        connector_type = "opcua-live"
        server_host_name = "opc.tcp://tool01:4840"

    conn = lab_reg.build_connector(_Tenant())  # the path AnnotationService uses
    assert isinstance(conn, ExternalSystemConnector)
    assert "opcua-live" in lab_reg.available_types()


def test_scaffold_sheet_writes_tabs(tmp_path):
    import yaml
    path = scaffold.scaffold_sheet("defect-review", "缺陷複判",
                                   ["module_042", "module_043"], base=tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["sheet_id"] == "defect-review"
    assert [t["module_id"] for t in data["tabs"]] == ["module_042", "module_043"]
    assert [t["order"] for t in data["tabs"]] == [0, 1]


def test_scaffold_sheet_create_stubs_makes_runnable_modules(tmp_path):
    """--create-stubs scaffolds a runnable module for each missing tab so the
    multi-tab tool is launchable immediately (R6 T3 gap)."""
    sheets_dir = tmp_path / "sheets"
    mods_dir = tmp_path / "scripts"
    scaffold.scaffold_sheet("inline-flow", "內聯流程",
                            ["module_810", "module_811"], base=sheets_dir,
                            create_stubs=True, modules_base=mods_dir)
    for mid in ("module_810", "module_811"):
        assert (mods_dir / mid / "plugin.yaml").exists()
        assert list((mods_dir / mid).glob("*_process.py")), f"{mid} stub not runnable"


def test_forms_supports_date_and_time():
    """Declarative form supports date/time fields; values coerce to ISO strings
    (JSON-serializable for execute_logic/output)."""
    import datetime as _dt
    from core import forms
    norm = forms.normalize_schema([
        {"key": "d", "type": "date"}, {"key": "t", "type": "time"},
    ])
    assert [f["type"] for f in norm] == ["date", "time"]
    m_date, _ = forms.widget_call(norm[0]); m_time, _ = forms.widget_call(norm[1])
    assert m_date == "date_input" and m_time == "time_input"
    assert forms.coerce(norm[0], _dt.date(2026, 5, 31)) == "2026-05-31"
    assert forms.coerce(norm[1], _dt.time(8, 30)) == "08:30:00"
