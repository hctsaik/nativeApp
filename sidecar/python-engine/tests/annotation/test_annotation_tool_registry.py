from __future__ import annotations

import pytest

from plugins.labeling.domain.tools.contracts import RuntimeStatus, ToolDescriptor
from plugins.labeling.domain.tools.registry import ToolRegistry, get_tool_registry, reset_tool_registry


# ── Helpers ──────────────────────────────────────────────────────────────────


def _fresh() -> ToolRegistry:
    r = ToolRegistry()

    class _NoopAdapter:
        def detect(self, executable_override=None):
            return RuntimeStatus(True, "noop", None, None, "ok")
        def launch_project(self, project_dir, options): return {"launched": True}
        def launch_file(self, file_path, options): return None
        def get_executable(self, executable_override=None): return "noop"

    r.register(ToolDescriptor("mytool", "My Tool", "labelme", aliases=["my-tool", "my_tool"]), _NoopAdapter())
    r.register(ToolDescriptor("notool", "No Tool", "isat", supports_project_mode=False), _NoopAdapter())
    return r


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_register_and_get_by_id() -> None:
    r = _fresh()
    desc, _ = r.get("mytool")
    assert desc.tool_id == "mytool"
    assert desc.display_name == "My Tool"


def test_get_by_alias_normalizes() -> None:
    r = _fresh()
    desc, _ = r.get("my-tool")
    assert desc.tool_id == "mytool"
    desc2, _ = r.get("my_tool")
    assert desc2.tool_id == "mytool"


def test_unknown_tool_raises_value_error() -> None:
    r = _fresh()
    with pytest.raises(ValueError, match="Unsupported"):
        r.get("nonexistent")


def test_isat_supports_project_mode_false() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    desc, _ = reg.get("isat")
    assert desc.supports_project_mode is False


def test_all_builtins_registered() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    for tid in ("x-anylabeling", "labelme", "isat"):
        desc, adapter = reg.get(tid)
        assert desc.tool_id == tid


def test_xanylabeling_aliases() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    assert reg.get("xanylabeling")[0].tool_id == "x-anylabeling"
    assert reg.get("x-any")[0].tool_id == "x-anylabeling"
    assert reg.get("x_anylabeling")[0].tool_id == "x-anylabeling"


def test_isat_alias() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    assert reg.get("isat-sam")[0].tool_id == "isat"


def test_list_supported_contains_all_tools() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    tools = reg.list_supported()
    ids = {t["id"] for t in tools}
    assert {"x-anylabeling", "labelme", "isat"}.issubset(ids)
    for t in tools:
        assert "supports_project_mode" in t
        assert "supports_file_mode" in t


def test_normalize_underscore() -> None:
    reset_tool_registry()
    reg = get_tool_registry()
    assert reg.normalize("x_anylabeling") == "x-anylabeling"


def test_list_labeling_tools_via_service(tmp_path) -> None:
    from plugins.labeling.domain.services import AnnotationService
    from plugins.labeling.domain.storage.workspace import AnnotationWorkspace
    reset_tool_registry()
    svc = AnnotationService(AnnotationWorkspace(tmp_path / "ws"))
    tools = svc.list_labeling_tools()
    assert any(t["id"] == "x-anylabeling" for t in tools)
    assert any(t["id"] == "isat" for t in tools)
