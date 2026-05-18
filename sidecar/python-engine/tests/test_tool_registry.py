from __future__ import annotations

import pytest
from pathlib import Path

from engine import MockToolAdapter, ToolRegistry, _derive_category


@pytest.fixture
def registry() -> ToolRegistry:
    return ToolRegistry(MockToolAdapter())


def test_list_tools_returns_tool_infos(registry: ToolRegistry) -> None:
    tools = registry.list_tools()
    assert len(tools) >= 1
    tool = tools[0]
    assert tool.tool_id
    assert tool.name
    assert tool.version


def test_list_tools_includes_category(registry: ToolRegistry) -> None:
    tools = registry.list_tools()
    for tool in tools:
        assert hasattr(tool, "category")
        assert tool.category in ("module", "sheet", "management", "external")


def test_get_returns_full_definition(registry: ToolRegistry) -> None:
    # MockToolAdapter seeds "sample-csv"
    tool = registry.get("sample-csv")
    assert tool.tool_id == "sample-csv"


def test_get_unknown_raises_key_error(registry: ToolRegistry) -> None:
    with pytest.raises(KeyError):
        registry.get("nonexistent-tool")


# ── _derive_category ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("tool_id,expected", [
    ("module_001", "module"),
    ("module_003", "module"),
    ("module_006", "module"),
    ("sheet-edge-analysis", "sheet"),
    ("sheet-anything", "sheet"),
    ("management-center", "management"),
    ("management-anything", "management"),
    ("labelme-dino", "external"),
])
def test_derive_category(tool_id: str, expected: str) -> None:
    assert _derive_category(tool_id) == expected
